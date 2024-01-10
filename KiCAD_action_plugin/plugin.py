"""
    Main plugin class
    This class is being instantiated in plugin_action.py for KiCAD,
    or in __main__ for standalone plugin execution.
"""
import pcbnew

import hashlib
import json
import logging
import logging.config
import os
import socket
import sys
import threading
import wx

from API_scripts.pcb_scanner import PcbScanner
from API_scripts.pcb_updater import PcbUpdater
from Config.config_loader import ConfigLoader
from plugin_gui import PluginGui


# Get the path to log file because configparsed doesn't search for the file in same directory where module is saved
# in file system. (it searches in directory where script is executed)
directory_path = os.path.dirname(os.path.realpath(__file__))
# Backslash is replaced with forwardslash, otherwise the file paths don't work
logging_config_file = os.path.join(directory_path, "Config", "logging.ini").replace("\\", "/")
# Define directory path for /Logs
log_files_directory = os.path.join(directory_path, "Logs").replace("\\", "/")
# Configure logging module with .ini file, pass /Logs directory as argument (part of formatted string in .ini)
logging.config.fileConfig(logging_config_file, defaults={"log_directory": log_files_directory})

# Initialize logger and log basic system info:
logger = logging.getLogger()
logger.info("Plugin executed on: " + repr(sys.platform))
logger.info("Plugin executed with python version: " + repr(sys.version))
logger.info("KiCad build version: " + str(pcbnew.GetBuildVersion()))


# Define event IDS for Client, ConnectionHandler and startUpdater thread events
EVT_CONNECTED_ID = wx.NewId()
EVT_RECEIVED_HASH = wx.NewId()
EVT_DISCONNECT_ID = wx.NewId()
EVT_START_UPDATER_ID = wx.NewId()


# Define wx event for cross-thread communication (Client --(socket)--> main)
# If data is None (by convention), connection failed
class ClientConnectedEvent(wx.PyEvent):
    """Event to carry socket object when connection to server accurs."""
    def __init__(self, data):
        super().__init__()
        self.SetEventType(EVT_CONNECTED_ID)
        self.socket = data


# Define wx event for cross-thread communication (ConnectionHander --(message)--> main)
class ReceivedHashEvent(wx.PyEvent):
    """Event to carry status message"""
    def __init__(self, data):
        super().__init__()
        self.SetEventType(EVT_RECEIVED_HASH)
        self.message = data


# Event for connecting function when disconnect message is received
class ReceivedDisconnectMessageEvent(wx.PyEvent):
    """Event to carry status message"""
    def __init__(self, data):
        super().__init__()
        self.SetEventType(EVT_DISCONNECT_ID)
        self.message = data


# Define wx event for cross-thread communication (ConnectionHander --(diff dictionary)--> main)
class ReceivedDiffEvent(wx.PyEvent):
    """Event to carry status message"""
    def __init__(self, data):
        super().__init__()
        self.SetEventType(EVT_START_UPDATER_ID)
        self.diff = data



class Client(threading.Thread):
    """Worker Thread that handels socket connection."""
    def __init__(self, notify_window, config):
        super().__init__()
        self.config = config
        # This port get changed
        self.port = self.config.port
        self._notify_window = notify_window
        self._want_abort = False

    def run(self):
        """Worker thread for starting Socket and connecting to server"""
        connected = False
        # Instantiate CLIENT Socket
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        logger.debug("[CLIENT] Socket created")

        while not self._want_abort:
            try:
                logger.debug(f"[CLIENT] Trying to connect on port {self.port}")
                # Try to connect
                client_socket.connect((self.config.host, self.port))
                connected = True
                break
            except ConnectionRefusedError:
                logger.debug(f"[CLIENT] Connection failed")
                # Increment port number and try again
                self.port += 1

            if self.port > (self.config.port + self.config.max_port_search_range):
                connected = False
                break

        # If successfully connected:
        if connected:
            logger.info(f"[CLIENT] Connected to {self.config.host}, {self.port}")
            # Send socket object to main thread
            wx.PostEvent(self._notify_window, ClientConnectedEvent(client_socket))
        else:
            # Post same event with None argument signaling connection has failed
            wx.PostEvent(self._notify_window, ClientConnectedEvent(None))

    def abort(self):
        # Method used by main thread to signal abort
        self._want_abort = True


class ConnectionHandler(threading.Thread):
    """ Worker Thread class that handles messaging via socket."""
    def __init__(self, notify_window, connection_socket, config):
        super().__init__()
        self.config = config
        self.socket = connection_socket
        self._notify_window = notify_window
        self._want_abort = False

    def run(self):
        """ Worker thread for receiving messages from client """
        logger.info(f"[CONNECTION] ConnectionHandler running")
        data = None
        connected = True
        while connected and not self._want_abort:
            # Receive first message
            first_msg = self.socket.recv(self.config.header).decode(self.config.format)
            # Check if anything was actually sent, skip if not
            if not first_msg:
                continue
            # Split first message -> first half is type (pcb, diff, disconnect), second is length
            msg_type = first_msg.split('_')[0]
            msg_length = first_msg.split('_')[1]
            # Receive second message
            msg_length = int(msg_length)
            data_raw = self.socket.recv(msg_length).decode(self.config.format)
            data = json.loads(data_raw)
            logger.debug(f"[CONNECTION] Message: {msg_type} {data}")

            # Check for disconnect message
            if msg_type == "!DIS":
                connected = False

            elif msg_type == "DIF":
                if not isinstance(data, dict):
                    continue
                logger.info(f"[CONNECTION] Diff Dictionary received: {data}")
                # Post event that stars updater
                wx.PostEvent(self._notify_window, ReceivedDiffEvent(data))

            elif msg_type == "HASH":
                logger.info(f"[CONNECTION] Hash(pcb) received: {data}")
                wx.PostEvent(self._notify_window, ReceivedHashEvent(data))


        self._want_abort = False
        self.socket.close()
        logger.debug("[CONNECTION] Socket closed")
        # Post event that disconnect happened
        wx.PostEvent(self._notify_window, ReceivedDisconnectMessageEvent(data))

    def abort(self):
        """ Method used by main thread to signal abort (condition is checked in While loop) """
        self._want_abort = True


class Plugin(PluginGui):

    def __init__(self):
        # Initialise main plugin window (GUI)
        super().__init__("CAD Sync plugin")

        # Get config.ini file path
        config_file = os.path.join(directory_path, "Config", "config.ini").replace("\\", "/")
        # Use module to read config data
        self.config = ConfigLoader(config_file)
        logger.info(f"Loaded configuration: {self.config.getConfig()}")
        self.console_logger.info(f"Loaded configuration: {self.config.getConfig()}")

        # self.searching_port = None  # Variable used for stopping port search
        self.brd = None
        self.pcb = None
        self.diff = {}
        # Indicate we don't have a workter thread yet
        self.client = None
        self.connection = None

        # Call function to get board on startup
        self.scanBoard()


    def onButtonScanBoard(self, event):
        self.scanBoard()

    def scanBoard(self):
        # Get board
        try:
            self.brd = pcbnew.GetBoard()
        except Exception as e:
            logger.exception(e)
            self.console_logger.exception(e)

        # Get dictionary from board
        if self.brd:
            logger.debug("Calling PcbScanner... (check pcb_scanner.log for logs)")
            self.pcb = PcbScanner.getPcb(self.brd)
            self.console_logger.log(logging.INFO, f"Board scanned: {self.pcb['general']['pcb_name']}")
            logger.debug(f"Board scanned: {self.pcb['general']['pcb_name']}")
            # Print pcb data to json file
            with open(directory_path + "/Logs/data_indent.json", "w") as f:
                json.dump(self.pcb, f, indent=4)


    def onButtonConnect(self, event):
        # Check if worker already exists
        if self.pcb and not self.client:
            # Connect event to method
            self.Connect(-1, -1, EVT_CONNECTED_ID, self.startConnectionHandler)
            # Instantiate client
            self.client = Client(self,
                                 config=self.config)
            # Start worker thread
            self.client.start()


    def stopSocket(self):
        if self.client:
            self.client.abort()


    def startConnectionHandler(self, event):
        # Connection sucessful if socket is received
        if event.socket and not self.connection:
            # Register socket object to parent as atribute
            self.socket = event.socket
            # Set buttons and text
            self.button_connect.Enable(False)
            self.button_connect.SetLabel("Connected")
            self.button_send_message.Enable(True)
            self.button_disconnect.Enable(True)
            # Display status to console
            self.console_logger.log(logging.INFO, f"[CLIENT] Connected")
            # Connect received messag event to method
            self.Connect(-1, -1, EVT_RECEIVED_HASH, self.onReceivedHash)
            # Connect disconnect event message
            self.Connect(-1, -1, EVT_DISCONNECT_ID, self.onReceivedDisconnectMessage)
            # Connect event when diff is received
            self.Connect(-1, -1, EVT_START_UPDATER_ID, self.startPcbUpdater)
            # Instantiate ConnectionHandler class, pass socket object as argument
            self.connection = ConnectionHandler(self,
                                                connection_socket=event.socket,
                                                config=self.config)
            # Start connection thread
            self.connection.start()

        # Case if None means connection has failed
        else:
            # Log status and display to console
            self.console_logger.log(logging.ERROR,
                                    "[ConnectionRefusedError] Connection to server failed. \n "
                                    "Check if server is running")
            logger.error("[ConnectionRefusedError] Connection to server failed")

        # If event is triggered, client worker thread is done in any case: conn sucessful or not
        self.client = None


    def startPcbUpdater(self, event):

        self.console_logger.log(logging.INFO, f"Diff received: {event.diff}")
        logger.info(f"Diff received: {event.diff}")

        if event.diff and self.brd and self.pcb:
            self.console_logger.log(logging.INFO, f"[UPDATER] Starting...")
            # Attach diff to as class attribute
            self.diff = event.diff

            # Call update scripts to apply diff to pcbnew.BOARD
            if self.diff.get("footprints"):
                try:
                    PcbUpdater.updateFootprints(self.brd, self.pcb, self.diff)
                except Exception as e:
                    logger.exception(e)

            if self.diff.get("drawings"):
                try:
                    PcbUpdater.updateDrawings(self.brd, self.pcb, self.diff)
                except Exception as e:
                    logger.exception(e)

            # Send hash of updated data model to freecad, so that freecad checks if all diffs were applied correctly
            # (data model is updated when editing pcbnew in pcb_updater)
            self.sendHashOfDataModel()

            self.console_logger.log(logging.INFO, f"[UPDATER] Done, refreshing document")
            # Refresh document
            pcbnew.Refresh()

            self.console_logger.log(logging.INFO, f"Clearing local Diff")
            logger.info(f"Clearing local Diff: {self.diff}")
            # TODO do another hash check if data model is in sync? To check if changes were applied correctly
            self.diff = {}

    def onReceivedHash(self, event):
        """
        Compare received hash to own hash, if same clear local diff
        :param event: wx.Event that carries data -> hash (str)
        :return:
        """
        received_pcb_hash = event.message

        logger.debug(f"Received hash: {received_pcb_hash}")
        own_pcb_hash = hashlib.md5(str(self.pcb).encode("utf-8")).hexdigest()
        logger.debug(f"Own hash: {own_pcb_hash}")

        try:
            # Dump data model to file for debugging
            Plugin.dumpToJsonFile(self.pcb, "/Logs/data_indent.json")
        except Exception as e:
            logger.exception(e)

        if received_pcb_hash == own_pcb_hash:
            logger.info(f"Hash match, diff synced")
            self.console_logger.log(logging.INFO, f"Hash match, diff synced")
            logger.debug(f"Clearing local diff: {self.diff}")
            self.diff = {}
        else:
            logger.error(f"Hash mismatch, sync lost!")
            # TODO handle mishmatch case

    def onReceivedDisconnectMessage(self, event):
        if event.message == "!DISCONNECT":
            self.button_send_message.Enable(False)
            self.button_disconnect.Enable(False)
            self.button_connect.Enable(True)
            self.console_logger.log(logging.INFO, "Received disconnect message")
            logger.info(f"Received disconnect message: {event.message}")
        else:
            self.console_logger.log(logging.INFO, "Received Diff")
            logger.info(f"Received Diff: {event.message}")


    def onButtonDisconnect(self, event):
        self.console_logger.log(logging.INFO, "Disconnecting...")
        logger.debug("Disconnecting...")

        try:
            # Send message to host to request disconnect
            self.sendMessage(json.dumps("!DISCONNECT"))
            # Close socket
            self.socket.close()
            disconnected = True
        except ConnectionAbortedError as e:
            self.console_logger.exception(e)
            logger.exception(e)
            disconnected = False

        if disconnected:
            # Log status
            self.console_logger.log(logging.INFO, "Socket closed")
            logger.info("Socket closed")
            # Set buttons
            self.button_send_message.Enable(False)
            self.button_disconnect.Enable(False)
            self.button_connect.Enable(True)
            self.button_connect.SetLabel("Connect")


    def onButtonSendMessage(self, event):
        if self.diff:
            self.console_logger.log(logging.INFO, "Sending Diff")
            logger.debug("Sending Diff")
            self.sendMessage(json.dumps(self.diff), msg_type="DIF")
        elif self.pcb:
            self.console_logger.log(logging.INFO, "Sending PCB")
            logger.debug("Sending PCB")
            self.sendMessage(json.dumps(self.pcb), msg_type="PCB")


    def onButtonGetDiff(self, event):
        if self.pcb:
            # Call the function to get diff (this takes existing diff dictionary and updates it)
            self.diff = PcbScanner.getDiff(self.brd, self.pcb, self.diff)
            self.console_logger.log(logging.INFO, self.diff)
            # Print diff and pcb dictionaries to .json
            # with open(directory_path + "/Logs/diff.json", "w") as f:
            #     json.dump(self.diff, f, indent=4)
            # with open(directory_path + "/Logs/data_indent.json", "w") as f:
            #     json.dump(self.pcb, f, indent=4)
            Plugin.dumpToJsonFile(self.diff, "/Logs/diff.json")
            Plugin.dumpToJsonFile(self.pcb, "/Logs/data_indent.json")

    def sendMessage(self, msg, msg_type="!DIS"):
        # Calculate length of first message
        msg_length = len(msg)
        send_length = str(msg_length)
        # First message is type and length of second message
        first_message = f"{msg_type}_{send_length}".encode(self.config.format)
        # Pad first message
        first_message += b' ' * (self.config.header- len(first_message))
        # Send length and object
        self.socket.send(first_message)
        self.socket.send(msg.encode(self.config.format))

    def sendHashOfDataModel(self):
        """ Call this function after updating part so FreeCAD can confirm change """
        # Convert pcb dictionary to encoded string, hash string, convert hash object to string
        pcb_hash = hashlib.md5(str(self.pcb).encode("utf-8")).hexdigest()

        self.console_logger.log(logging.INFO, f"Sending hash")
        logger.info(f"Sending hash {pcb_hash}")
        # Send this hash as message to KC
        self.sendMessage(json.dumps(pcb_hash), msg_type="HASH")

    @staticmethod
    def dumpToJsonFile(data, filename):
        with open(directory_path + filename, "w") as f:
            json.dump(data, f, indent=4)