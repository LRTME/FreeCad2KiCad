import FreeCAD as App
import FreeCADGui as Gui

import hashlib
import json
import logging
import logging.config
import os
import sys

from PySide import QtGui, QtCore

from API_scripts.part_scanner import FcPartScanner
from API_scripts.part_drawer import FcPartDrawer
from API_scripts.part_updater import FcPartUpdater
from Config.config_loader import ConfigLoader
from Socket.server import Server, ConnectionHandler

# Add plugin directory to path for imports to work
DIRECTORY_PATH = os.path.dirname(os.path.realpath(__file__))
sys.path.append(DIRECTORY_PATH)

# Initialize logger and log basic system info:
logger = logging.getLogger("root")

# Button placement magic numbers
BUTTON_WIDTH = 200
BUTTON_HEIGHT = 25
INITIAL_Y = 50
INITIAL_X = 25
OFFSET_Y = 40


# noinspection PyAttributeOutsideInit
class FreeCADPlugin(QtGui.QDockWidget):
    """ Main plugin class. """

    def __init__(self, doc, doc_gui):
        super().__init__()

        # Get FreeCAD document and GUI objects
        self.doc = doc
        self.doc_gui = doc_gui

        self.pcb = {}
        self.diff = {}
        self.existing_placement = None

        # Get config.ini file path
        config_file = os.path.join(DIRECTORY_PATH, "Config", "config.ini").replace("\\", "/")
        # Load config data
        self.config = ConfigLoader(config_file)
        logger.info(f"Loaded configuration: {self.config.get_config()}")
        logger.info(f"Active document: {self.doc.Name}")
        # Set up the User Interface
        self.setup_ui()

    def setup_ui(self):
        """ Set up buttons and text. """
        self.setObjectName("FreeSync Server Instance")
        self.resize(QtCore.QSize(300, 100).expandedTo(self.minimumSizeHint()))  # sets size of the widget

        # Text
        self.text_title = QtGui.QLabel("FreeSync Server Instance", self)
        self.text_title.move(30, 10)
        self.text_title.resize(250, BUTTON_HEIGHT)

        self.text_connection = QtGui.QLabel("", self)
        # Move text more to the left to accommodate longer pcb name
        self.text_connection.move(INITIAL_X - 10, INITIAL_Y)
        self.text_connection.resize(210, BUTTON_HEIGHT)
        self.text_connection.hide()

        # Buttons
        # Start and stop button have same position
        self.button_start_server = QtGui.QPushButton("Accept new connection", self)
        self.button_start_server.clicked.connect(self.on_button_start_server)
        self.button_start_server.move(INITIAL_X, INITIAL_Y)
        self.button_start_server.resize(BUTTON_WIDTH, BUTTON_HEIGHT)

        self.button_stop_server = QtGui.QPushButton("Stop listening", self)
        self.button_stop_server.clicked.connect(self.on_button_stop_server)
        self.button_stop_server.hide()
        self.button_stop_server.move(INITIAL_X, INITIAL_Y)
        self.button_stop_server.resize(BUTTON_WIDTH, BUTTON_HEIGHT)
        self.button_stop_server.setEnabled(False)

        # Sync button and progres bar have same position
        self.button_sync = QtGui.QPushButton("Sync", self)
        self.button_sync.clicked.connect(self.on_button_sync)
        self.button_sync.move(INITIAL_X, INITIAL_Y + OFFSET_Y)
        self.button_sync.resize(BUTTON_WIDTH, BUTTON_HEIGHT)
        self.button_sync.setEnabled(False)

        # Progress bar
        self.progress_bar = QtGui.QProgressBar(self)
        self.progress_bar.move(INITIAL_X, INITIAL_Y + OFFSET_Y)
        self.progress_bar.resize(BUTTON_WIDTH, BUTTON_HEIGHT)
        self.progress_bar.hide()

    # --------------------------------- Button Methods --------------------------------- #
    def on_button_start_server(self):
        """ Call method on button press. """
        self.start_server()

    def on_button_stop_server(self):
        """ Call stop method (in another thread) to queue abort. """
        self.server.abort()
        # Set appropriate button visibility
        self.server_closed_buttons()

    def on_button_sync(self):
        """ Call method on button press. """
        self.start_sync_sequence()

    # --------------------------------- Hide/Show Buttons --------------------------------- #

    def connected_buttons(self):
        """ Change button visibility. """
        self.text_connection.show()
        self.button_stop_server.hide()
        self.button_start_server.hide()

    def disconnected_buttons(self):
        """ Change large button text and visibility. """
        self.text_connection.hide()
        self.button_stop_server.setEnabled(False)
        self.button_stop_server.hide()
        self.button_start_server.setEnabled(True)
        self.button_start_server.show()
        # Disable buttons for requesting pcb or attaching pcb
        self.button_sync.setEnabled(False)

    def server_closed_buttons(self):
        """ Disable stop and enable start when server is stopped. """
        self.button_start_server.setEnabled(True)
        self.button_start_server.show()
        self.button_stop_server.setEnabled(False)
        self.button_stop_server.hide()

    def server_start_buttons(self):
        """ Enable stop button and disable start when starting server. """
        self.button_start_server.setEnabled(False)
        self.button_start_server.hide()
        self.button_stop_server.setEnabled(True)
        self.button_stop_server.show()

    # ---------------------------------| Sequential Process Methods |--------------------------------- #

    def start_server(self):
        """ 1. step: Start server in a new thread. Thread is stopped and deleted when connection to client occurs. """
        self.server_thread = QtCore.QThread()
        self.server = Server(self.config)
        self.server.moveToThread(self.server_thread)

        # Connect signals and slots
        self.server_thread.started.connect(self.server.run)
        self.server.finished.connect(self.server_thread.quit)
        self.server.finished.connect(self.server.deleteLater)
        self.server_thread.finished.connect(self.server_thread.deleteLater)
        # Connect finished signal to startConnection method - this passes socket.socket object to ConnectionHandler
        self.server.finished.connect(self.on_server_finished)

        # Start the thread
        self.server_thread.start()
        # Enable stop button and disable start when starting server
        self.server_start_buttons()

    def on_server_finished(self, server_response):
        """ 2. step: Attach socket objects to self. """
        # Get data from dictionary type
        status = server_response.get("status")

        # Perform check if connection is real or fake (quasi-abort) see Server class docstring
        if status == "abort":
            logger.debug("Server aborted, ignoring connection socket")
            # Show correct button configuration - server was aborted, enable button for starting server again
            self.server_closed_buttons()

        elif status == "exception":
            logger.error(f"Exception when starting server")

        elif status == "client_connected":
            # Get data from dictionary type
            connection_socket = server_response.get("connection_socket")
            # Attach connection handle (socket) to class, so that a message can be sent manually by button (sendMessage)
            self.socket = connection_socket
            # Change button visibility
            self.connected_buttons()
            # Change button text
            self.text_connection.setText(f"Connected: {self.socket}")
            logger.debug("Client connected.")

            # Run ConnectionHandler in a new thread to listen for replies
            self.connection_thread = QtCore.QThread()
            # Instantiate Connection class with client connection Socket
            self.connection = ConnectionHandler(self.socket, self.config)
            self.connection.moveToThread(self.connection_thread)
            # Finished signal
            self.connection_thread.started.connect(self.connection.run)
            self.connection.finished.connect(self.connection_thread.quit)
            self.connection.finished.connect(self.connection.deleteLater)
            self.connection_thread.finished.connect(self.connection_thread.deleteLater)
            self.connection.finished.connect(self.on_connection_handler_finished)
            # Custom signals
            self.connection.received_pcb.connect(self.on_received_pcb)
            self.connection.received_diff.connect(self.on_received_diff)
            self.connection.received_diff_reply.connect(self.on_received_diff_reply)
            # Start thread
            self.connection_thread.start()

            # Enable Sync button.
            self.button_sync.setEnabled(True)

    def start_sync_sequence(self):
        """ 3. step: check if plugin instance has a pcb data-model attached (skip to step 7). """
        if not self.pcb:
            logger.info(f"Data-model not attached, requesting Pcb")
            # No data-model, request pcb from KC
            self.request_pcb()
        else:
            logger.info(f"Data-model attached, requesting Diff")
            # Plugin instance has data-model attached, proceed with requesting diff
            self.request_diff()

    def request_pcb(self):
        """ 4. step: send a request message over socket, listen for reply in a new thread. """
        # Send message to request pcb from KiCAD
        self.send_message("blankmessage", msg_type="REQPCB")

    def on_received_pcb(self, pcb_data: dict):
        """ 5. step: Draw part object when data model is received. """
        # Search FC document if Part object with same KIID as received pcb already exists (in case of opening
        # a project with board already in it)
        existing_part = self.find_board_part_by_kiid(doc=self.doc,
                                                     kiid=pcb_data.get("general").get("kiid"))
        if existing_part:
            logger.info(f"Found a board {existing_part.Name} with same ID as in KiCAD")
            # Store placement of existing part
            self.existing_placement = existing_part.Placement
            logger.warning("Removing existing board part")
            # Delete existing part
            self.doc.getObject(existing_part.Name).removeObjectsFromDocument()
            self.doc.removeObject(existing_part.Name)

        # Attach dictionary to object
        self.pcb = pcb_data
        # Write data model to file for debugging purposes
        self.dump_to_json_file(self.pcb, "/Logs/data_indent.json")
        # Change button text to indicate registered pcb data-model
        self.text_connection.setText(f"Connected: {self.pcb.get('general').get('pcb_name')}")

        # Add file directory to models path so that .kicad_pcb file directory is also searched when importing 3d models
        self.config.models_path.update({"file_directory": self.pcb.get("general").get("file_directory")})

        # Instantiate and run Drawer
        pcb_drawer = FcPartDrawer(doc=self.doc,
                                  doc_gui=self.doc_gui,
                                  pcb=self.pcb,
                                  models_path=self.config.models_path,
                                  progress_bar=self.progress_bar)
        # Drawer returns board part, so it can be moved to previous location if board with same is existed in document
        board_part = pcb_drawer.run()

        # Move newly drawn part to same placement where old part was (if part was already in document)
        if self.existing_placement:
            logger.warning(f"Moving redrawn board to same position.")
            board_part.Placement = self.existing_placement

        self.refresh_document()
        Gui.SendMsgToActiveView("ViewFit")

    def request_diff(self):
        """ 6. step: Send request message when user presses SYNC button. """
        # Change button text to indicate registered pcb data-model
        self.text_connection.setText(f"Connected: {self.pcb.get('general').get('pcb_name')}")
        logger.info("Sending request message.")
        # Send request message
        self.send_message("blankmessage", msg_type="REQDIF")

    def on_received_diff(self, diff_data: dict):
        """ 7. step: start PartScanner to get local Diff, merge local diff and KiCAD diff """
        # Attach received data to object
        self.kc_diff = diff_data

        # Instantiate and call PartScanner to get local Diff
        part_scanner = FcPartScanner(doc=self.doc,
                                     pcb=self.pcb,
                                     diff=self.diff,
                                     config=self.config,
                                     progress_bar=self.progress_bar)
        local_diff = part_scanner.run()

        # ------------------| Diff merge |------------------
        logger.info(f"PartScanner finished {local_diff}")
        merged_diff = {}

        # Select which drawings diff to use:
        fc_drawings = local_diff.get("drawings")
        kc_drawings = self.kc_diff.get("drawings")
        # If only one instance of drawings (logical XOR): use that instance
        if (fc_drawings and not kc_drawings) or (kc_drawings and not fc_drawings):
            merged_diff.update({"drawings": fc_drawings if fc_drawings else kc_drawings})
        # Conflict case (both diffs have drawings)
        elif fc_drawings and kc_drawings:
            # FC drawing is a base for merge
            merged_drawings = fc_drawings
            # Drawings that were added by user in KC should be deleted when syncing: add their KIIDs to "removed"
            # key of diff, to be deleted when sending merged diff back
            added_in_kc = kc_drawings.get("added")
            if added_in_kc:
                merged_drawings.update({"removed": [drawing.get("kiid") for drawing in added_in_kc]})
            merged_diff.update({"drawings": merged_drawings})

        # Select which footprints diff to use:
        fc_footprints = local_diff.get("footprints")
        kc_footprints = self.kc_diff.get("footprints")
        fc_footprints_changed = None
        kc_footprints_changed = None
        # First check if diff exist (if non-type it crashed)
        if fc_footprints is not None:
            fc_footprints_changed = fc_footprints.get("changed")
        if kc_footprints is not None:
            kc_footprints_changed = kc_footprints.get("changed")

        # Initialise empty list to build merged diff
        footprints_merged_changed = []

        if fc_footprints_changed:
            # Walk list of fc diff: if conflict append kc diff to merged list, otherwise append fc diff to merged list
            for fc_fp in fc_footprints_changed:
                # Entry in changed is a dictionary with single key value pair where key is kiid
                fc_kiid = list(fc_fp.keys())[0]
                if kc_footprints_changed:
                    for kc_fp in kc_footprints_changed:
                        kc_kiid = list(kc_fp.keys())[0]
                        # If entry with same kiid exists in kicad diffs, apply this entry and break
                        if fc_kiid == kc_kiid:
                            footprints_merged_changed.append(kc_fp)
                            break

                # No conflicts with kc, append fc diff to list
                footprints_merged_changed.append(fc_fp)

        if kc_footprints_changed:
            # Add all kicad entries to merged diff after appending kc entries
            for kc_fp in kc_footprints_changed:
                footprints_merged_changed.append(kc_fp)

        # Add merged fp diff if not empty list
        if footprints_merged_changed:
            logger.debug(f"Merged diff {footprints_merged_changed}")
            # Add key if missing from dictionary
            if merged_diff.get("footprints") is None:
                merged_diff.update({"footprints": {}})
            # Add key if missing from dictionary, add merged diff
            if merged_diff["footprints"].get("changed") is None:
                merged_diff["footprints"].update({"changed": footprints_merged_changed})

        logger.info(f"Diff merged: {merged_diff}")
        self.dump_to_json_file(merged_diff, "/Logs/diff.json")
        # Attach diff to object
        self.diff = merged_diff
        # Send new diff to KiCAD
        self.send_message(json.dumps(merged_diff), msg_type="DIF")

    def on_received_diff_reply(self, diff_reply, hash_data):
        """
        8. step: apply diff. diff_reply contains merged diff which was sent to FC before and also updated KIID
        if new drawings were added in FC.
        Hash data is hashed KC data model used to check sync on FC side after updating.
        """
        # Attach received values to object
        self.diff = diff_reply
        self.kc_hash = hash_data
        logger.info(f"Received reply: {self.diff},\nHash: {hash_data}")
        self.dump_to_json_file(self.diff, "/Logs/diff.json")

        if self.diff:
            # # Update FC Part objects
            # self.start_part_updater(self.diff)

            # Instantiate and run part updater
            part_updater = FcPartUpdater(doc=self.doc,
                                         pcb=self.pcb,
                                         diff=self.diff,
                                         models_path=self.config.models_path,
                                         progress_bar=self.progress_bar)
            part_updater.run()

        logger.info(f"Finished part updater")
        self.refresh_document()

        # Write data model to file for debugging purposes
        self.dump_to_json_file(self.pcb, "/Logs/data_indent.json")

        pcb_hash = hashlib.md5(str(self.pcb).encode()).hexdigest()
        if pcb_hash == self.kc_hash:
            logger.info(f"Hash match!")
            logger.debug(f"Clearing Diff")
            self.diff = {}
        else:
            logger.error(f"Hash mismatch!\n{pcb_hash} should be {self.kc_hash}")
            logger.debug(f"Clearing data-model")
            # Send disconnect message
            self.send_message(json.dumps("!DIS"))
            # Abort connection handler by calling the stop method to break listening loop
            self.connection.abort()

    # noinspection PyUnusedLocal
    def on_connection_handler_finished(self):
        """
        9: step: Remove data model from plugin instance when disconnecting:
        this way reconnection after disconnection is treated the same as connection for the first time
        (board part is redrawn)
        """
        # Clear data-model. This causes pcb to be redrawn
        self.pcb = {}
        # Change button visibility
        self.disconnected_buttons()

    # ------------------------------------| Utils |--------------------------------------------- #

    @staticmethod
    def find_board_part_by_kiid(doc: App.Document, kiid: str) -> App.Part:
        """ Go through root level objects in document to find if board object with same KIID exists. """
        board_part = None
        for object_in_document in doc.RootObjects:
            try:
                if object_in_document.KIID == kiid:
                    board_part = object_in_document
            except AttributeError:
                # Only objects created by this plugin have a .KIID attribute, default Part objects do not.
                pass

        return board_part

    def send_message(self, msg: str, msg_type: str = "!DIS"):
        """
        Message can be type (by convention) of !DIS, REQ_PCB, REQ_DIF, PCB, DIF
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

    def refresh_document(self):
        """ Recompute FreeCAD Document object. """
        logger.info(f"Recomputing document")
        try:
            self.doc.recompute()
        except Exception as e:
            logger.exception(e)

    @staticmethod
    def dump_to_json_file(data, filename: str):
        """ Save data to file. """
        with open(DIRECTORY_PATH + filename, "w") as f:
            json.dump(data, f, indent=4)
