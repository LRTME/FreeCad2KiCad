*Worker thread for starting Socket and connecting to server*

#### run()
	client_socket = socket.socket
	
	try:
		client_socket.connect(host, port)
		wx.PostEvent(connection_handle)


connection_handle is socket.socket object