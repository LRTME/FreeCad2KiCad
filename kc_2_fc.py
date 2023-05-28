import json
import logging
import pickle
import random
import socket
import threading
import pcbnew

from pcbnew_functions import *
from kc_2_fc_gui import Kc2FcGui

logger = logging.getLogger(__name__)

"""
    Main plugin class
    This class is being instantiated in plugin_action.py for KiCAD,
    or in __main__ for standalone plugin execution.
"""


# noinspection PyUnusedLocal
class Kc2Fc(Kc2FcGui):

    def __init__(self):
        # Initialise main plugin window (GUI)
        super().__init__("CAD Sync plugin")

        self.searching_port = None  # Var used for stopping port search
        self.brd = None
        self.pcb = None
        self.diff = {}

    @staticmethod
    def updateDiffDict(key, value, diff_dict):
        """Helper function for adding and removing entries from diff dictionary"""

        if value.get("added") or value.get("changed") or value.get("removed"):
            diff_dict.update({key: value})
        else:
            # Removed from diff if no new changes
            try:
                diff_dict.pop(key)
            except KeyError:
                pass

    # --------------------------- UI Methods --------------------------- #
    # Overwrite this UI methods from parent class
    def onButtonConnect(self, event):

        # Get board
        if not self.brd:
            try:
                self.brd = pcbnew.GetBoard()
            except Exception as e:
                self.logger.exception(e)

        # Get pcb (JSON)
        if not self.pcb:
            try:
                self.pcb = getPcb(self.brd)
            except Exception as e:
                self.logger.exception(e)

        if self.pcb:
            # SERVER SEARCHING
            # If connect button is pressed while searching for server, search stops
            if self.searching_port:
                self.searching_port = False
                self.button_connect.SetLabel("Connect")
                self.logger.log(logging.INFO, "[SOCKET] Stopping search...")
                self.port = self.initial_port
            # Start function in another thread so UI doesn't freeze when searching for port
            else:
                socket_thread = threading.Thread(target=self.startSocket)
                socket_thread.start()

    def onButtonDisconnect(self, event):
        try:
            self.sendMessage(json.dumps("!DISCONNECT"))
            self.logger.log(logging.INFO, "Disconnecting..")
            self.closeSocket()
            self.button_connect.SetLabel("Connect")

        except ConnectionAbortedError as e:
            self.logger.exception("ConnectionAbortedError")

    def onButtonSendMessage(self, event):
        if self.diff:
            self.logger.log(logging.INFO, "Sending diff")
            self.sendMessage(json.dumps(self.diff), msg_type="DIF")
        elif self.pcb:
            self.logger.log(logging.INFO, "Sending JSON")
            self.sendMessage(json.dumps(self.pcb), msg_type="PCB")

    def onButtonGetDiff(self, event):

        if self.pcb:

            # Footprints
            Kc2Fc.updateDiffDict(key="footprints",
                                 value=getFootprints(self.brd, self.pcb),
                                 diff_dict=self.diff)
            # Drawings
            Kc2Fc.updateDiffDict(key="drawings",
                                 value=getPcbDrawings(self.brd, self.pcb),
                                 diff_dict=self.diff)

            # TODO vias, general

            self.logger.log(logging.INFO, self.diff)

            with open("differences.json", "w") as f:
                json.dump(self.diff, f, indent=4)

            with open("data_indent.json", "w") as f:
                json.dump(self.pcb, f, indent=4)

    def onButtonScanBoard(self, event):

        # Get dictionary from board
        if self.brd:
            self.pcb = getPcb(self.brd)
            self.logger.log(logging.INFO, f"Board scanned: {self.pcb.get('general').get('pcb_name')}")
            # self.logger.log(logging.INFO, self.pcb)

        else:
            self.brd = pcbnew.GetBoard()
            self.pcb = getPcb(self.brd)
            self.logger.log(logging.INFO, f"Board scanned: {self.pcb.get('general').get('pcb_name')}")
            # self.logger.log(logging.INFO, self.pcb)

        with open("data_indent.json", "w") as f:
            json.dump(self.pcb, f, indent=4)

    # --------------------------- Socket --------------------------- #
    def startSocket(self):
        # Instantiate CLIENT socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.logger.log(logging.INFO, "[SOCKET] Socket created")
        self.searching_port = True  # Var used for stopping port search
        self.button_connect.SetLabel("Stop search")  # Repurpose connect button for canceling search
        # Save initial port, so when search is stopped and started, it starts from initial value
        self.initial_port = self.port
        # If port selection is automatic (default), search for open ports:
        if not self.port_is_manual:
            self.connected = False
            while not self.connected and self.searching_port:  # TODO connected and searching port could be 1 variable?
                try:
                    self.logger.log(logging.INFO, f"[SOCKET] Searching host: on port {self.port}")
                    # Try to connect
                    self.socket.connect((self.host, self.port))
                    self.connected = True
                except ConnectionRefusedError:
                    self.port = self.port + 1

                if self.port > (self.STARTING_PORT + self.MAX_PORT_RANGE):
                    self.logger.log(logging.ERROR, "Failed to find host server")
                    break

        # If port selection is set to manual, try connecting:
        else:
            try:
                self.socket.connect((self.host, self.port))
                self.connected = True
            except ConnectionRefusedError:
                self.logger.log(logging.ERROR, "[ConnectionRefusedError] Connection to server failed. \n\
                 Check if server is running")

        # If successfully connected:
        if self.connected:
            self.button_connect.Enable(False)
            self.button_connect.SetLabel("Connected")
            self.button_send_message.Enable(True)
            self.button_disconnect.Enable(True)
            self.logger.log(logging.INFO, f"[SOCKET] Connected to {self.host}:{self.port}")
            # Send initial message
            if self.pcb:
                self.logger.log(logging.INFO, "Sending JSON")
                self.sendMessage(json.dumps(self.pcb), msg_type="PCB")

            # Start new thread for receiving messages
            threading.Thread(target=self.handleHost).start()

    def handleHost(self):  # TODO update with new messaging protocol
        """
        Worker thread for receiving messages from host
        """
        while self.connected:
            try:
                # Receive first message
                data_length = self.socket.recv(self.HEADER).decode(self.FORMAT)
                # Check if anything was actually sent
                if data_length:
                    # Calculate length of second message
                    data_length = int(data_length)
                    # Receive and decode second message
                    data_raw = self.socket.recv(data_length)
                    data = json.loads(data_raw)
                    # Check for disconnect message
                    if data == "!DISCONNECT":
                        self.connected = False

                    # Receive dictionary - new pcb
                    elif type(data) is dict:
                        self.new_pcb = data
                        self.button_test.Enable(True)

                    self.logger.log(logging.INFO, f"[DATA] Message received from host: {data}")

            except OSError as e:
                if e.errno == 10038:
                    # [WinError 10038] An operation was attempted on something that is not a socket
                    # appears when closing connection
                    pass

    def closeSocket(self):
        self.socket.close()
        self.button_send_message.Enable(False)
        self.button_disconnect.Enable(False)
        self.button_connect.Enable(True)
        self.logger.log(logging.INFO, "Socket closed")

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