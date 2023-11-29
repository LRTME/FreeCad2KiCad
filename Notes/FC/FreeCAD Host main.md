

### startServer()
	server = Server()
	server.connected.connect(startConnection)

start host [[Server]] in another thread, otherwise FC crashes. Pass connection handle (via emmited signal) to startConnection() method.


### startConnection(conn)
	connection = ConnectionHandler(conn)
	connection.pcb.connect(startPcbDrawer)
	connection.diff.connect(startPartUpdater)

[[Connection Handler]] takes a input parameter (connection handle), where it listens for messages.

has two main signals:
- pcb
	when this signal is emmited, a new thread is opened automatically for drawing as pcb (*Drawer*)
- diff
	when emmited, automatically start new thread for updating existing pcb (*Updater*)

### startPcbDrawer(pcb)
calls [[Drawer(pcb)]] object in another thread*

### startPartUpdater(diff)
*calls [[Updater(diff)]] in another thread*

#### startPartScanner()
start [[Scanner]] in another thread, scanner returns diff