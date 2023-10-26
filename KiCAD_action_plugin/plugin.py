"""
    Main plugin class
    This class is being instantiated in plugin_action.py for KiCAD,
    or in __main__ for standalone plugin execution.
"""
import pcbnew

import json
import logging
import os
import random
import socket
import sys
import threading
import wx

from plugin_gui import PluginGui
from API_scripts.pcb_scanner import PcbScanner

# Set up logger
logger = logging.getLogger("__main__")
logger.setLevel(logging.DEBUG)

# Get plugin directory and add /Logs folder
dir_path = os.path.dirname(os.path.realpath(__file__))
if not os.path.exists(dir_path + "/Logs"):
    os.makedirs(dir_path + "/Logs")
handler = logging.FileHandler(filename=dir_path + "/Logs/kicad_client.log",
                              mode="w")
formatter = logging.Formatter(fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                              datefmt="%d/%m/%Y %H:%M:%S")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.debug("Plugin executed on: " + repr(sys.platform))
logger.debug("Plugin executed with python version: " + repr(sys.version))
logger.debug("KiCad build version: " + str(pcbnew.GetBuildVersion()))


# Load configuration file
config_data = json.load(open(file=dir_path + "/config.json", encoding="utf-8"))
if config_data:
    logger.debug(f"Loaded configuration file: {config_data}")


# Define event IDS for Client and ConnectionHandler thread events
EVT_CONNECTED_ID = wx.NewId()
EVT_CONN_HANDLER_ID = wx.NewId()


# Define wx event for cross-thread communication (Client --(socket)--> main)
# If data is None (by convention), connection failed
class ClientConnectedEvent(wx.PyEvent):
    """Event to carry socket object when connection to server accurs."""
    def __init__(self, data):
        super().__init__()
        self.SetEventType(EVT_CONNECTED_ID)
        self.socket = data


# Define wx event for cross-thread communication (ConnectionHander --(message)--> main)
class ReceivedMessageEvent(wx.PyEvent):
    """Event to carry status message"""
    def __init__(self, data):
        super().__init__()
        self.SetEventType(EVT_CONN_HANDLER_ID)
        self.message = data


class Client(threading.Thread):
    """Worker Thread that handels socket connection."""
    def __init__(self, notify_window):
        super().__init__()
        self.host = config_data["host"]
        self.port = config_data["port"]
        self._notify_window = notify_window
        self._want_abort = False

    def run(self):
        """Worker thread for starting Socket and listening for client"""
        connected = False
        # Instantiate CLIENT Socket
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        logger.debug("[CLIENT] Socket created")

        while not self._want_abort:
            try:
                logger.debug(f"[CLIENT] Trying to connect on port {self.port}")
                # Try to connect
                client_socket.connect((self.host, self.port))
                connected = True
                break
            except ConnectionRefusedError:
                logger.debug(f"[CLIENT] Connection failed")
                # Increment port number and try again
                self.port += 1

            if self.port > (config_data["port"] + config_data["max_port_search_range"]):
                connected = False
                break

        # If successfully connected:
        if connected:
            logger.info(f"[CLIENT] Connected to {self.host}, {self.port}")
            # Send socket object to main thread
            wx.PostEvent(self._notify_window, ClientConnectedEvent(client_socket))
        else:
            # Post sam event with None argument signaling connection has failed
            wx.PostEvent(self._notify_window, ClientConnectedEvent(None))

    def abort(self):
        # Method used by main thread to signal abort
        self._want_abort = True


class ConnectionHandler(threading.Thread):
    """ Worker Thread class that handles messing via socket."""
    def __init__(self, notify_window, socket):
        super().__init__()
        self.HEADER = config_data["header"]
        self.FORMAT = config_data["format"]
        self.socket = socket
        self._notify_window = notify_window
        self._want_abort = False

    def run(self):
        """Worker thread for receiving messages from client"""
        data = None
        connected = True
        while connected and not self._want_abort:
            # Receive first message
            first_msg = self.socket.recv(self.HEADER).decode(self.FORMAT)
            # Check if anything was actually sent, skip if not
            if not first_msg:
                continue
            # Split first message -> first half is type (pcb, diff, disconnect), second is length
            msg_type = first_msg.split('_')[0]
            msg_length = first_msg.split('_')[1]
            # Receive second message
            msg_length = int(msg_length)
            data_raw = self.socket.recv(msg_length).decode(self.FORMAT)
            data = json.loads(data_raw)

            # Check for disconnect message
            if msg_type == "!DIS":
                connected = False

        self._want_abort = False
        self.socket.close()
        logger.debug("[CONNECTION] Socket closed")
        wx.PostEvent(self._notify_window, ReceivedMessageEvent(data))

    def abort(self):
        # Method used by main thread to signal abort
        self._want_abort = True


class Plugin(PluginGui):

    def __init__(self):
        # Initialise main plugin window (GUI)
        super().__init__("CAD Sync plugin")

        self.HEADER = config_data["header"]
        self.FORMAT = config_data["format"]
        # self.searching_port = None  # Var used for stopping port search
        self.brd = None
        self.pcb = None
        self.diff = {}
        # Indicate we don't have a workter thread yet
        self.client = None
        self.connection = None
        # Call funtion to get board on startup
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
            self.pcb = PcbScanner.getPcb(self.brd)
            self.console_logger.log(logging.INFO, f"Board scanned: {self.pcb['general']['pcb_name']}")
            logger.debug(f"Board scanned: {self.pcb['general']['pcb_name']}")
            # Print pcb data to json file
            with open(dir_path + "/Logs/data_indent.json", "w") as f:
                json.dump(self.pcb, f, indent=4)

            # TODO removed log entry
            logger.debug(f"{str(self.pcb['drawings'][0])}")


    def onButtonConnect(self, event):
        # Check if worker already exists
        if self.pcb and not self.client:
            # Connect event to method
            self.Connect(-1, -1, EVT_CONNECTED_ID, self.onConnected)
            # Instantiate client
            self.client = Client(self)
            # Start worker thread
            self.client.start()

    def stopSocket(self):
        if self.client:
            self.client.abort()

    def onConnected(self, event):
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
            # Connect event to method
            self.Connect(-1, -1, EVT_CONN_HANDLER_ID, self.onReceivedMessage)
            # Instantiate ConnectionHandler class, pass socket object as argument
            self.connection = ConnectionHandler(self, socket=event.socket)
            # Start connection thread
            self.connection.start()
        
        # Case if None means connection has failed
        else:
            # Log status and display to console
            self.console_logger.log(logging.ERROR,
                                    "[ConnectionRefusedError] Connection to server failed. \n "
                                    "Check if server is running")
            logger.error("[ConnectionRefusedError] Connection to server failed")

        # If event is triggered, worker is done in any case: conn sucessful or not
        self.client = None


    def onReceivedMessage(self, event):
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
            # Call the funtion to get diff
            self.diff = PcbScanner.getDiff(self.brd, self.pcb, self.diff)
            self.console_logger.log(logging.INFO, self.diff)
            # Print diff and pcb dictionaries to .json
            with open(dir_path + "/Logs/diff.json", "w") as f:
                json.dump(self.diff, f, indent=4)
            with open(dir_path + "/Logs/data_indent.json", "w") as f:
                json.dump(self.pcb, f, indent=4)


    def sendMessage(self, msg, msg_type="!DIS"):
        # Calculate length of first message
        msg_length = len(msg)
        send_length = str(msg_length)
        # First message is type and length of second message
        first_message = f"{msg_type}_{send_length}".encode(self.FORMAT)
        # Pad first message
        first_message += b' ' * (self.HEADER - len(first_message))
        # Send length and object
        self.socket.send(first_message)
        self.socket.send(msg.encode(self.FORMAT))