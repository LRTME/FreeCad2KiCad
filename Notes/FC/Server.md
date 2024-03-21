*QObject - Thread*

Infinite loop where server is listening on HOST:PORT

When connection accurs, break loop end emit signal (conection handle). This signal is type socket.socket


##### run()
	socket.listen()

	while True:
		connection = socket.accept()
		connected_signal.emit(connection)
		break