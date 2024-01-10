import json
import logging
import os
import socket

from PySide import QtGui, QtCore

# Initialize logger
logger_server = logging.getLogger("SERVER")


class Server(QtCore.QObject):
    """
    There is no way to stop socket.accept() method -> create a new socket to establish connection. This is the only
    way to satisfy condition for exiting this thread "cleanly"
    # TODO handle this quasi-connection -> this is not supposed to trigger ConnectionHandler since it is fake:
    wrap return values to dictionary where a key holds information if connection is quasy-abort or real
    """

    #progress = QtCore.Signal(str)
    #finished = QtCore.Signal()
    #connected = QtCore.Signal(type(socket.socket))
    finished = QtCore.Signal(dict)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._want_abort = False

    # @QtCore.Slot()
    # def workerSlot(self):
    #     logger_server.info("Closing connection manually")
    #     self.socket.close()
    #     logger_server.info("Server Socket closed")
    #     self.finished.emit()

    def abort(self):
        """ Method used by main thread to signal abort (condition is checked in While loop) """
        logger_server.debug("abort called")
        self._want_abort = True
        logger_server.debug(f"server._want_abort = {self._want_abort}")

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

    # def _run(self):
    #     """Worker thread for starting Socket and listening for client"""
    #     logger_server.info("Server starting")
    #
    #     # Instantiate socket object
    #     self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #
    #     # Loop through available sockets
    #     socket_searching = True
    #     while socket_searching:
    #         if self.config.port > (self.config.port + 20):
    #             socket_searching = False
    #             self.config.port = 5050
    #             logger_server.info(f"Failed to start server, port reset to: {self.config.port}")
    #             self.finished.emit()
    #
    #         try:
    #             self.socket.bind((self.config.host, self.config.port))
    #             socket_searching = False
    #             # Wait for connection
    #             self.socket.listen()
    #             logger_server.info(f"Server is listening on {self.config.host}, port {self.config.port}")
    #
    #             while not self._want_abort:
    #                 # Accept new connection
    #                 self.conn, self.addr = self.socket.accept()
    #                 logger_server.info(f"Client connected: {str(self.addr)}")
    #                 self.socket.close()
    #                 logger_server.info("Server Socket closed")
    #                 # Emit Qt Signal
    #                 self.connected.emit(self.conn)
    #                 self.finished.emit()
    #                 self._want_abort = False
    #                 break
    #
    #         except OSError as e:
    #             # BUG: error message when manually closing Socket.
    #             # FIX: Catch error number 10038 (on windows: Operation was attempted on
    #             #                                            something that is not a Socket)
    #             if e.errno == 10038:
    #                 pass
    #             # Only one usage of each Socket address is permitted
    #             elif e.errno == 10048:
    #                 self.config.port = self.config.port + 1
    #             else:
    #                 print(e)
    #                 self.finished.emit()


class ConnectionHandler(QtCore.QObject):

    progress = QtCore.Signal(str)
    finished = QtCore.Signal()
    received_pcb = QtCore.Signal(dict)
    received_diff = QtCore.Signal(dict)
    received_hash = QtCore.Signal(str)

    def __init__(self, connection_socket, config):
        super().__init__()
        self.socket = connection_socket
        self.config = config


    def run(self):
        """Worker thread for receiving messages from client"""

        self.connected = True
        while self.connected:
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

            # Check for disconnect message
            if msg_type == "!DIS":
                self.connected = False
                logger_server.info(f"Disconnect message received: {data}")

            elif msg_type == "PCB":
                if not isinstance(data, dict):
                    continue
                logger_server.info(f"PCB Dictionary received.")
                self.received_pcb.emit(data)

            elif msg_type == "DIF":
                if not isinstance(data, dict):
                    continue
                logger_server.info(f"Diff Dictionary received: {data}")
                self.received_diff.emit(data)

            elif msg_type == "HASH":
                logger_server.info(f"Hash received {data}")
                self.received_hash.emit(data)

        self.socket.close()
        logger_server.info("Client disconnected, connection closed")
        self.finished.emit()