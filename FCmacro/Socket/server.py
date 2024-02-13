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
    """ Instantiate host socket and start listening for clients """
    # There is no way to stop socket.accept() method -> create a new socket to establish connection. This is the only
    # way to satisfy condition for exiting this thread "cleanly"
    # Solution: Wrap return values to dictionary where a key holds information if connection is quasi-abort or real,
    # check this status before launching connection handler
    # https://stackoverflow.com/questions/16734534/close-listening-socket-in-python-thread

    finished = QtCore.Signal(dict)

    def __init__(self, config):
        super().__init__()
        self.config = config
        # Private attribute to stop infinite loop
        self._want_abort = False
        self.socket = None
        self.conn = None
        self.addr = None

    def stop(self):
        """ Method used by main thread stop accepting clients. Established fake connection"""
        self._want_abort = True
        socket.socket(socket.AF_INET,
                      socket.SOCK_STREAM).connect((self.config.host, self.config.port))
        self.socket.close()

    def run(self):
        """Worker thread for starting Socket and listening for client"""
        logger_server.info("Server starting")

        # Instantiate socket object
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Set Re-use address option to 1 to avoid [Errno 98]
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.socket.bind((self.config.host, self.config.port))
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

        if bind_successful:
            # Wait for connection
            self.socket.listen()
            logger_server.info(f"Server is listening on {self.config.host}, port {self.config.port}")

            while not self._want_abort:
                # Accept new connection
                self.conn, self.addr = self.socket.accept()
                # Connection is a genuine client
                if not self._want_abort:
                    logger_server.info(f"Client connected: {str(self.addr)}")
                    self.socket.close()
                    break
                # Connection is fake socket
                else:
                    logger_server.debug(f"Listening stopped by abort signal")
                    self.socket.close()

                    break

        logger_server.info("Server Socket closed")

        # See docstring
        result = {
            "connection_socket": self.conn,
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
        self.socket = connection_socket
        self.config = config
        self.connected = False

    def run(self):
        """ Worker thread for receiving messages from client. """

        logger_server.debug(f"ConnectionHandler running")
        self.connected = True
        while self.connected:

            # Receive first message
            first_msg = self.socket.recv(self.config.header).decode(self.config.format)
            # Check if anything was actually sent, skip if not
            if not first_msg:
                continue
            # Split first message -> first half is type (pcb, diff, disconnect), second is length
            msg_type = first_msg.split("_")[0]
            msg_length = first_msg.split("_")[1]
            # Receive second message
            msg_length = int(msg_length)
            data_raw = self.socket.recv(msg_length).decode(self.config.format)

            logger_server.debug(f"[CONNECTION] Message received: {msg_type}")

            # Check for disconnect message
            if msg_type == "!DIS":
                self.connected = False
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

        self.socket.close()
        logger_server.info("Client disconnected, connection closed")
        self.finished.emit()
