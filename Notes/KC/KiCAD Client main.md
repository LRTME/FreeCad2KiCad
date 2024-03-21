
### onButtonConnect()
*this starts [[Client(threading.Thread)]] in new thread*

	# Instantiate client
	client_thread = Client(config)
	client_thread.start()

When connection accurs, wx event is posted:
- event ID: EVT_CONNECTED_ID
- event data: connection_handle

Event is connected to next method: onConnected().
This is how connection_handle is passed to [[KC Connection Handler(threading.Thread)]]
**Connection_handle is also saved as attribute of this class**. This is so that sendMessage() method can be called a push of a button

### startConnectionHandler()
*this starts [[KC Connection Handler(threading.Thread)]] in new thread*

	# Store connection handle (socket) as attribute of this class
	self.connection_handle = connection_handle
	# Instantiate ConnectionHandler
	connection_thread = ConnectionHandler(connection_handle,
																		config)
	connection_thread.start()

When message is received, wx event is posted:
- event ID: EVT_CONN_HANDLER_ID
- event data: string / json (dictionary)

Event is connected to method: onReceivedMessage()
This is how message is passed to main method

### sendMessage(mesage)
#todo
currently only !DISCONNECT message is being sent from FC to KC