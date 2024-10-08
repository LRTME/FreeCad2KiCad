"""
    Module contains Server and ConnectionHandler host for managing socket connection.
"""

import json
import logging
import socket

from PySide import QtGui, QtCore

# Initialize logger
logger_server = logging.getLogger("SERVER")


class Server(QtCore.QObject):
    """
    Instantiate host socket and start listening for clients.
    There is no way to stop socket.accept() method -> create a new socket to establish connection. This is the only
    way to satisfy condition for exiting this thread "cleanly"
    Solution: Wrap return values to dictionary where a key holds information if connection is quasi-abort or real,
    check this status before launching connection handler
    https://stackoverflow.com/questions/16734534/close-listening-socket-in-python-thread
    """

    finished = QtCore.Signal(dict)

    def __init__(self, config):
        super().__init__()
        self.config = config
        # Private attribute to stop infinite loop
        self._want_abort = False
        self._socket = None

    def abort(self):
        """ Method used by main thread stop accepting clients. Establishes fake connection. """
        self._want_abort = True
        socket.socket(socket.AF_INET,
                      socket.SOCK_STREAM).connect((self.config.host, self.config.port))
        self._socket.close()

    def run(self):
        """ Worker thread for starting Socket and listening for client. """
        logger_server.info("Server starting")

        # Instantiate socket object
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Set Re-use address option to 1 to avoid [Errno 98]
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self._socket.bind((self.config.host, self.config.port))
            bind_successful = True
        except OSError as e:
            # BUG: error message when manually closing Socket.
            # FIX: Catch error number 10038 (on windows: Operation was attempted on
            #                                            something that is not a Socket)
            bind_successful = False
            if e.errno == 10038:
                pass
            # Only one usage of each Socket address is permitted
            elif e.errno == 10048:
                # self.config.port = self.config.port + 1
                logger_server.exception(e)
            else:
                logger_server.exception(e)
                self.finished.emit({"status": "exception"})
                return

        conn = None
        if bind_successful:
            # Wait for connection
            self._socket.listen()
            logger_server.info(f"Server is listening on {self.config.host}, port {self.config.port}")
            # Accept new connection
            conn, addr = self._socket.accept()
            # Connection is a genuine client
            if not self._want_abort:
                logger_server.info(f"Client connected: {str(addr)}")
                self._socket.close()
            # Connection is fake socket
            else:
                logger_server.debug(f"Listening stopped by abort signal")
                self._socket.close()

        logger_server.info("Server Socket closed")

        # See docstring
        result = {
            "connection_socket": conn,
            "status": "abort" if self._want_abort else "client_connected"
            }

        # Emit Qt Signal
        self.finished.emit(result)


class ConnectionHandler(QtCore.QObject):
    """
    Listen for an incoming message on connection socket in a separate thread to avoid crashing FreeCAD
    (socket.recv is a blocking operation).
    """
    finished = QtCore.Signal()
    received_pcb = QtCore.Signal(dict)
    received_diff = QtCore.Signal(dict)
    received_diff_reply = QtCore.Signal(dict, dict)

    def __init__(self, connection_socket, config):
        super().__init__()
        self._socket = connection_socket
        self.config = config
        self._abort = False

    def abort(self):
        """ Method used by main when disconnection from FC side. """
        self._abort = True

    def run(self):
        """ Worker thread for receiving messages from client. """

        logger_server.debug(f"ConnectionHandler running")
        self._abort = False
        while not self._abort:

            # Receive first message
            first_msg = self._socket.recv(self.config.header).decode(self.config.format)
            # Check if anything was actually sent, skip if not
            if not first_msg:
                continue
            # Split first message -> first half is type (pcb, diff, disconnect), second is length
            msg_type = first_msg.split("_")[0]
            msg_length = first_msg.split("_")[1]
            # Receive second message
            msg_length = int(msg_length)
            data_raw = self._socket.recv(msg_length).decode(self.config.format)

            logger_server.debug(f"[CONNECTION] Message received: {msg_type}")

            # Check for disconnect message
            if msg_type == "!DIS":
                self._abort = True
                logger_server.info(f"Disconnect message received.")

            elif msg_type == "REP":
                # Second message has two parts: diff and hash separated by double underscore (because single underscore
                # appears in dictionary string)
                dict_data_string = data_raw.split("__")[0]
                hash_data_string = data_raw.split("__")[1]
                # String to dictionary with json.loads
                dict_data = json.loads(dict_data_string)
                logger_server.info(f"Diff Reply received: {dict_data}, Hash: {hash_data_string}")
                self.received_diff_reply.emit(dict_data, hash_data_string)

            elif msg_type == "PCB":
                # String to dictionary with json.loads
                dict_data = json.loads(data_raw)
                if not isinstance(dict_data, dict):
                    continue
                logger_server.info(f"PCB Dictionary received.")
                self.received_pcb.emit(dict_data)

            elif msg_type == "DIF":
                # String to dictionary with json.loads
                dict_data = json.loads(data_raw)
                if not isinstance(dict_data, dict):
                    continue
                logger_server.info(f"Diff Dictionary received: {dict_data}")
                self.received_diff.emit(dict_data)

            else:
                logger_server.error(f"Invalid message type: {msg_type}_{json.loads(data_raw)}")

        self._socket.close()
        logger_server.info("Client disconnected, connection closed")
        self.finished.emit()

    def send_message(self, msg: str, msg_type: str = "!DIS"):
        """
        Message can be type (by convention) of !DIS, REQ_PCB, REQ_DIF, PCB, DIF
        :param msg: json encoded string
        :param msg_type: str
        :return:
        """
        logger_server.debug(f"Sending message {msg_type}_{msg}")
        # Calculate length of first message
        msg_length = len(msg)
        send_length = str(msg_length)
        # First message is type and length of second message
        first_message = f"{msg_type}_{send_length}".encode(self.config.format)
        # Pad first message
        first_message += b' ' * (self.config.header - len(first_message))
        # Send length and object
        self._socket.send(first_message)
        self._socket.send(msg.encode(self.config.format))
