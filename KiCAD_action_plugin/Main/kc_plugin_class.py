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
from Main.kc_plugin_gui import KcPluginGui


# Get the path to log file because configparser doesn't search for the file in same directory where module is saved
# in file system. (it searches in directory where script is executed)
directory_path = os.path.dirname(os.path.realpath(__file__))
parent_directory_path = os.path.dirname(directory_path)
# Backslash is replaced with forward slash, otherwise the file paths don't work
logging_config_file = os.path.join(parent_directory_path, "Config", "logging.ini").replace("\\", "/")
# Create Logs directory if it doesn't exist
if not os.path.exists(os.path.join(parent_directory_path, "Logs")):
    os.makedirs(os.path.join(parent_directory_path, "Logs"))
# Define directory path for /Logs
log_files_directory = os.path.join(parent_directory_path, "Logs").replace("\\", "/")
# Configure logging module with .ini file, pass /Logs directory as argument (part of formatted string in .ini)
logging.config.fileConfig(logging_config_file, defaults={"log_directory": log_files_directory})

# Initialize logger and log basic system info:
logger = logging.getLogger()
logger.info("Plugin executed on: " + repr(sys.platform))
logger.info("Plugin executed with python version: " + repr(sys.version))
logger.info("KiCad build version: " + str(pcbnew.GetBuildVersion()))


# Define event IDS for cross thread communication
EVT_CONNECTED_ID = wx.NewId()
EVT_PCB_REQUEST_ID = wx.NewId()
EVT_DIFF_REQUEST_ID = wx.NewId()
EVT_RECEIVED_DIFF = wx.NewId()
EVT_DISCONNECT_ID = wx.NewId()
# Events, EVT_IDs, Client and ConnectionHandler must all be defined in same module.


# Define wx event for cross-thread communication (Client --(socket)--> main)
# If data is None (by convention), connection failed
class ClientConnectedEvent(wx.PyEvent):
    """ Event to carry socket object when connection to server occurs."""

    # noinspection PyShadowingNames
    def __init__(self, socket):
        super().__init__()
        self.SetEventType(EVT_CONNECTED_ID)
        self.socket = socket


# Event for connecting function when receiving request message from FreeCAD
class ReceivedPcbRequestEvent(wx.PyEvent):
    """ Event to trigger function. """
    def __init__(self):
        super().__init__()
        self.SetEventType(EVT_PCB_REQUEST_ID)


# Event for connecting function when receiving request message from FreeCAD
class ReceivedDiffRequestEvent(wx.PyEvent):
    """ Event to trigger function. """
    def __init__(self):
        super().__init__()
        self.SetEventType(EVT_DIFF_REQUEST_ID)


# Define wx event for cross-thread communication (ConnectionHandler --(diff dictionary)--> main)
class ReceivedDiffEvent(wx.PyEvent):
    """Event to carry status message"""
    def __init__(self, data):
        super().__init__()
        self.SetEventType(EVT_RECEIVED_DIFF)
        self.diff = data


class ReceivedDisconnectMessage(wx.PyEvent):
    """ Event to signal disconnect message. """
    def __init__(self):
        super().__init__()
        self.SetEventType(EVT_DISCONNECT_ID)


class Client(threading.Thread):
    """ Worker Thread that handles socket connection. """

    def __init__(self, notify_window, config):
        super().__init__()
        self.config = config
        # This port get changed
        self.port = self.config.port
        self._notify_window = notify_window
        self._want_abort = False

    def abort(self):
        """ Method used by main thread to signal abort. """
        self._want_abort = True

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


class ConnectionHandler(threading.Thread):
    """ Worker Thread class that handles messaging via socket."""

    def __init__(self, notify_window, connection_socket, config):
        super().__init__()
        self.config = config
        self.socket = connection_socket
        self._notify_window = notify_window
        self._want_abort = False

    def send_message(self, msg, msg_type="!DIS"):
        """
        Message can be type (by convention) of !DIS, REQ_PCB, REQ_DIF, DIF, DIFREP
        :param msg: json encoded string
        :param msg_type: str
        :return:
        """
        logger.debug(f"Sending message {msg_type}_{msg}")
        # Calculate length of first message
        msg_length = len(msg)
        send_length = str(msg_length)
        # First message is type and length of second message
        first_message = f"{msg_type}_{send_length}".encode(self.config.format)
        # Pad first message
        first_message += b' ' * (self.config.header - len(first_message))
        # Send length and object
        self.socket.send(first_message)
        self.socket.send(msg.encode(self.config.format))

    def abort(self):
        """ Method used by main thread to signal abort (condition is checked in While loop) """
        self._want_abort = True

    def run(self):
        """ Worker thread for receiving messages from client. """
        logger.info(f"[CONNECTION] ConnectionHandler running")
        data = None
        msg_type = None
        while not self._want_abort:
            # noinspection PyBroadException
            try:
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
            except Exception:
                # OSError: [WinError 10038] an operation was attempted on something that is not a socket
                # If exception OSError, receiving the second message (diff request doesn't work)
                # If not socket.recv not in try/except block, receiving the second message (diff request doesn't work)
                pass

            # Check for disconnect message
            if msg_type == "!DIS":
                self._want_abort = True
                # Post event that signals request received
                wx.PostEvent(self._notify_window, ReceivedDisconnectMessage())

            elif msg_type == "REQPCB":
                logger.debug(f"[CONNECTION] Received Pcb request.")
                # Post event that signals request received
                wx.PostEvent(self._notify_window, ReceivedPcbRequestEvent())

            elif msg_type == "REQDIF":
                logger.debug(f"[CONNECTION] Received Diff request.")
                # Post event that signals request received
                wx.PostEvent(self._notify_window, ReceivedDiffRequestEvent())

            elif msg_type == "DIF":
                if not isinstance(data, dict):
                    continue
                logger.info(f"[CONNECTION] Diff Dictionary received: {data}")
                # Post event that starts updater
                wx.PostEvent(self._notify_window, ReceivedDiffEvent(data))

        self._want_abort = False
        self.socket.close()
        logger.debug("[CONNECTION] Socket closed")


# noinspection PyAttributeOutsideInit
class KcPlugin(KcPluginGui):

    def __init__(self):
        # Initialise main plugin window (GUI)
        super().__init__("FreeSync Host Instance")

        # Get config.ini file path
        config_file = os.path.join(parent_directory_path, "Config", "config.ini").replace("\\", "/")
        # Use module to read config data
        self.config = ConfigLoader(config_file)
        logger.info(f"Loaded configuration: {self.config.get_config()}")
        self.console_logger.info(f"Loaded configuration: {self.config.get_config()}")
        # self.searching_port = None  # Variable used for stopping port search
        self.brd = None
        self.pcb = None
        self.diff = {}
        self.client = None
        self.connection = None
        # # Call function to get board on startup
        # self.scanBoard()

    # --------------------------------- Button Methods --------------------------------- #

    # noinspection PyUnusedLocal
    def on_button_connect(self, event):
        """ Function must accept event argument to be triggered. """
        # Check if worker already exists
        if self.client:
            return 1

        # Connect event to method
        self.Connect(-1, -1, EVT_CONNECTED_ID, self.start_connection_handler)
        # Instantiate client
        self.client = Client(self, config=self.config)
        # Start worker thread
        self.client.start()

    def start_connection_handler(self, event):
        """ Start a separate thread for listening to incoming messages. """
        # Connection successful if socket is received
        if event.socket and not self.connection:
            # Register socket object to parent as attribute to be able to send messages
            self.socket = event.socket
            # Set buttons and text
            self.button_connect.Enable(False)
            self.button_connect.SetLabel("Connected")
            # self.button_send_message.Enable(True)
            self.button_disconnect.Enable(True)
            # Display status to console
            self.console_logger.log(logging.INFO, f"[CLIENT] Connected")
            # Connected received DISCONNECT message to method
            self.Connect(-1, -1, EVT_DISCONNECT_ID, self.on_disconnect_message)
            # Connect received PCB REQUEST to method
            self.Connect(-1, -1, EVT_PCB_REQUEST_ID, self.on_received_pcb_request)
            # Connect received DIFF REQUEST to method
            self.Connect(-1, -1, EVT_DIFF_REQUEST_ID, self.on_received_diff_request)
            # Connect received DIFF to method
            self.Connect(-1, -1, EVT_RECEIVED_DIFF, self.on_received_diff)
            # Instantiate ConnectionHandler class, pass socket object as argument
            self.connection = ConnectionHandler(self, connection_socket=event.socket, config=self.config)
            # Start connection thread
            self.connection.start()

        # Case if None means connection has failed
        else:
            # Log status and display to console
            self.console_logger.log(logging.ERROR,
                                    "[ConnectionRefusedError] Connection to server failed. \n "
                                    "Check if server is running")
            logger.error("[ConnectionRefusedError] Connection to server failed")

        # If event is triggered, client worker thread is done in any case: conn successful or not
        self.client = None

    # ---------------------------------| Sequential Process Methods |--------------------------------- #

    # noinspection PyUnusedLocal
    def on_received_pcb_request(self, event):
        """
        Send pcb data model to FC. Method is invoked when receiving request message via event.
        Event does not carry and data.
        """
        logger.info(f"PCB request received.")
        self.console_logger.log(logging.INFO, f"PCB request received.")

        # Get data model
        self.scan_board()

        if self.pcb:
            self.connection.send_message(json.dumps(self.pcb), msg_type="PCB")
        else:
            self.console_logger.log(logging.ERROR, f"Failed to scan board, disconnecting")
            logger.error(f"Failed to scan board, disconnecting")
            self.connection.send_message(json.dumps("!DIS"))

    # noinspection PyUnusedLocal
    def on_received_diff_request(self, event):
        """
        Send Diff to FC. Method is invoked when receiving request message via event.
        Event does not carry and data.
        """
        try:
            # Call the function to get diff (this takes existing diff dictionary and updates it)
            self.diff = PcbScanner.get_diff(self.brd, self.pcb, self.diff)
            self.console_logger.log(logging.INFO, self.diff)
            self.dump_to_json_file(self.diff, "/Logs/diff.json")
            self.dump_to_json_file(self.pcb, "/Logs/data_indent.json")

            self.console_logger.log(logging.INFO, "Sending Diff")
            logger.debug("Sending Diff")
            self.connection.send_message(json.dumps(self.diff), msg_type="DIF")

            # Clear diff, FreeCAD takes care of merging sent diff with FC diff, and then sends merged diff back
            logger.debug(f"Clearing local Diff: {self.diff}")
            self.diff = {}
        except Exception as e:
            logger.exception(e)

    def on_received_diff(self, event):
        """
        Apply received Diff data to pcbnew object. Special case for drawings that were added in FC: these drawings don't
        have valid KIID. They are first added to board, at which point KiCAD assigns them an m_Uuid (cannot be set
        manually). These drawings are added to
        """
        self.console_logger.log(logging.INFO, f"Diff received: {event.diff}")
        logger.info(f"Diff received: {event.diff}")
        self.console_logger.log(logging.INFO, f"[UPDATER] Starting...")

        # Attach diff to object. This gets modified if new drawings are updated with KIIDs and then sent back to FC
        self.diff = event.diff
        footprints = self.diff.get("footprints")
        drawings = self.diff.get("drawings")

        # Call update scripts to apply diff to pcbnew.BOARD
        if footprints:
            logger.debug(f"calling update footprints")
            PcbUpdater.update_footprints(self.brd, self.pcb, footprints)
        if drawings:
            changed = drawings.get("changed")
            added = drawings.get("added")
            removed = drawings.get("removed")
            if changed:
                # Update drawings with pcbnew (also update data model)
                PcbUpdater.update_drawings(self.brd, self.pcb, changed)
            if removed:
                # Remove drawings with pcbnew from board and from data model
                PcbUpdater.remove_drawings(self.brd, self.pcb, removed)
                # # Delete the whole key from diff to avoid -> "removed": []
                # del drawings["removed"]

            if added:
                # (KIID cannot be set, it's attached to object after instantiation with pcbnew).
                # Drawings with invalid KIID (new drawings from FC) are marked as deleted, drawings are added to pcb
                # with new kiid, Differ is called to recognise them as added, Diff is sent to FC where invalid
                # drawings are redrawn and replaced in data model with valid KIIDs

                # List of dictionary data
                drawings_added = []
                # List if KIIDs
                drawings_to_remove = []
                # Copy diff.added since drawing is being removed from diff (to avoid in place .remove())
                for drawing in added.copy():
                    # Draw the new drawings with pcbnew
                    valid_kiid = PcbUpdater.add_drawing(brd=self.brd, drawing=drawing)
                    # Make a new instance of dictionary, so that drawing stays the same
                    drawing_updated = drawing.copy()
                    # Override "new-drawing-added-in-freecad" with actual m_Uuid
                    drawing_updated.update({"kiid": valid_kiid})
                    # Append to list. This will be added to Diff as "added" drawings
                    drawings_added.append(drawing_updated)
                    # Append KIID of deleted drawing to list. This will be added to Diff as "removed" drawings
                    drawings_to_remove.append(drawing["kiid"])
                    # Remove entry with invalid ID from diff
                    self.diff.get("drawings").get("added").remove(drawing)

                    # If null, define value # todo change to dict if data model changes
                    if not self.pcb.get("drawings"):
                        self.pcb.update({"drawings": []})

                    # Add entry with updated kiid to data model
                    self.pcb.get("drawings").append(drawing_updated)

                # Build Diff dictionary as follows:
                # {
                #   "removed": [invalid IDs of new drawings, as sent by FreeCAD] <-  to be deleted from sketch and pcb
                #   "added": [newly added drawings with correct KIIDs] <- to be redrawn in sketch and added to pcb
                # }
                PcbScanner.update_diff_dict(key="drawings",
                                            value={
                                              "removed": drawings_to_remove,
                                              "added": drawings_added
                                            },
                                            diff=self.diff)

        # # Delete whole drawings from diff if it's an empty dictionary
        # if self.diff.get("drawings") == {}:
        #     del self.diff["drawings"]

        # Save data model and diff to file for debugging
        KcPlugin.dump_to_json_file(self.pcb, "/Logs/data_indent.json")
        KcPlugin.dump_to_json_file(self.diff, "/Logs/diff.json")

        # Hash data model after applying all changes. Send hash to FC so data model sync can be checked on FC side.

        pcb_hash = hashlib.md5(str(self.pcb).encode()).hexdigest()

        self.console_logger.log(logging.INFO, "[UPDATER] Sending Diff Reply")
        logger.debug(f"Sending Diff Reply {self.diff}")
        # Send diff back to FC
        # (either same as merged diff, or with updated "removed" and "added" in case of new drawings)
        # Also contains hash of updated data model (separated by double underscore (because single underscore appears
        # in dictionary string)
        diff_reply = f"{json.dumps(self.diff)}__{pcb_hash}"
        self.connection.send_message(diff_reply, msg_type="REP")

        logger.debug(f"Clearing diff.")
        self.diff = {}

        self.console_logger.log(logging.INFO, f"[UPDATER] Done, refreshing document")
        logger.info(f"[UPDATER] Done, refreshing document")
        # Refresh document
        pcbnew.Refresh()

    # noinspection PyUnusedLocal
    def on_button_disconnect(self, event):
        """ Send disconnect message via socket and close socket connection. """
        self.console_logger.log(logging.INFO, "Disconnecting...")
        logger.debug("Disconnecting...")
        # Send message to host to request disconnect
        self.connection.send_message(json.dumps("!DIS"))
        # Call abort method of ConnectionHandler to stop listening loop and shutdown socket
        self.connection.abort()
        self.console_logger.log(logging.INFO, "Socket closed")
        logger.info("Socket closed")
        # Clear connection socket object (to pass the check when connecting again after disconnect)
        self.connection = None
        # Set buttons
        self.button_disconnect.Enable(False)
        self.button_connect.Enable(True)
        self.button_connect.SetLabel("Connect")

    # noinspection PyUnusedLocal
    def on_disconnect_message(self, event):
        """ Handle disconnection from host side: close socket and reset button without sending disconnect message. """
        # Log to GUI here, cannot be done in ConnectionHandler class
        self.console_logger.log(logging.INFO, "Socket closed")
        # Clear connection socket object (to pass the check when connecting again after disconnect)
        self.connection = None
        # Set buttons
        self.button_disconnect.Enable(False)
        self.button_connect.Enable(True)
        self.button_connect.SetLabel("Connect")

    # ------------------------------------| Utils |--------------------------------------------- #

    def scan_board(self):
        """ Get pcb data model. """
        # Get board
        try:
            self.brd = pcbnew.GetBoard()
        except Exception as e:
            logger.exception(e)
            self.console_logger.exception(e)

        # Get dictionary from board
        if self.brd:
            logger.debug("Calling PcbScanner... (check pcb_scanner.log for logs)")
            self.pcb = PcbScanner.get_pcb(self.brd)
            self.console_logger.log(logging.INFO, f"Board scanned: {self.pcb['general']['pcb_name']}")
            logger.debug(f"Board scanned: {self.pcb['general']['pcb_name']}")
            # Print pcb data to json file
            with open(parent_directory_path + "/Logs/data_indent.json", "w") as f:
                json.dump(self.pcb, f, indent=4)

    def get_diff(self):
        """ Scan get data with pcbnew API, update existing dictionary. """
        # Call the function to get diff (this takes existing diff dictionary and updates it)
        self.diff = PcbScanner.get_diff(self.brd, self.pcb, self.diff)
        self.console_logger.log(logging.INFO, self.diff)
        self.dump_to_json_file(self.diff, "/Logs/diff.json")
        self.dump_to_json_file(self.pcb, "/Logs/data_indent.json")

    @staticmethod
    def dump_to_json_file(data, filename):
        """ Save data to file. """
        with open(parent_directory_path + filename, "w") as f:
            json.dump(data, f, indent=4)
