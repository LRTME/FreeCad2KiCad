import json
import os
import socket
import sys

from PySide import QtGui, QtCore


class Server(QtCore.QObject):

    progress = QtCore.Signal(str)
    finished = QtCore.Signal()
    connected = QtCore.Signal(type(socket.socket))

    def __init__(self, host, starting_port):
        super().__init__()
        self.host = host
        self.port = starting_port

    @QtCore.Slot()
    def workerSlot(self):
        self.progress.emit("Closing connection manually")
        self.socket.close()
        self.progress.emit("Server Socket closed")
        self.finished.emit()

    def run(self):
        """Worker thread for starting Socket and listening for client"""

        self.progress.emit("Server starting")
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Loop through available sockets
        socket_searching = True
        while socket_searching:
            if self.port > (self.port + 20):
                socket_searching = False
                self.port = 5050
                self.progress.emit(f"Failed to start server, port reset to: {self.port}")
                self.finished.emit()

            try:
                self.socket.bind((self.host, self.port))
                socket_searching = False
                # Wait for connection
                self.socket.listen()
                self.progress.emit(f"Server is listening on {self.host}, port {self.port}")

                while True:
                    # Accept new connection
                    self.conn, self.addr = self.socket.accept()
                    self.progress.emit(f"Client connected: {str(self.addr)}")
                    self.socket.close()
                    self.progress.emit("Server Socket closed")
                    # Emit Qt Signal
                    self.connected.emit(self.conn)
                    self.finished.emit()
                    break

            except OSError as e:
                # BUG: error message when manually closing Socket.
                # FIX: Catch error number 10038 (on windows: Operation was attempted on
                #                                            something that is not a Socket)
                if e.errno == 10038:
                    pass
                # Only one usage of each Socket address is permitted
                elif e.errno == 10048:
                    self.port = self.port + 1
                else:
                    print(e)
                    self.finished.emit()


class ConnectionHandler(QtCore.QObject):

    progress = QtCore.Signal(str)
    finished = QtCore.Signal()
    received_pcb = QtCore.Signal(dict)
    received_diff = QtCore.Signal(dict)

    def __init__(self, connection_socket, header, format):
        super().__init__()
        self.socket = connection_socket
        self.HEADER = header
        self.FORMAT = format

    def run(self):
        """Worker thread for receiving messages from client"""

        self.connected = True
        while self.connected:
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
                self.connected = False
                self.progress.emit(f"Disconnect message received: {data}")

            elif msg_type == "PCB":
                if not isinstance(data, dict):
                    continue
                self.progress.emit(f"PCB Dictionary received: {data}")
                self.received_pcb.emit(data)

            elif msg_type == "DIF":
                if not isinstance(data, dict):
                    continue
                self.progress.emit(f"Diff Dictionary received: {data}")
                self.received_diff.emit(data)


        self.socket.close()
        self.progress.emit("Client disconnected, connection closed")
        self.finished.emit()