*Worker thread for receiving messages from client*

#### run()
	while connected:
		socket.recv().decode()

There are always two messages:
First message:
- *type_length*
- length of 8 bytes
Second message:
- *data*
- length of previous message *length*

#todo currently only DISCONNECT message is supported.
Add support for DIFF message
