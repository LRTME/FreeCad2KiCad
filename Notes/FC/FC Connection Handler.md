*QObject - Thread*

Infinite loop for listening for incoming messages on socket.
When message is received, emit one of three signals:
- pcb
- diff
- !DIS (this is disconnect request)

Pcb and Diff are "returned" to main thread as emmited signals. This automatically calls drawer and updater in a new thread

Break loop and close socket if disconnect request.

##### def run()
	while True:
		socket.recv().decode()
		if msg == hash
			hash_signal.emit(hash)
		elif msg == pcb data
			pcb_signal.emit(pcb_data)
		elif msg = diff data
			diff_signal.emit(diff_data)
		elif msg == !DIS
			socket.close()
			break