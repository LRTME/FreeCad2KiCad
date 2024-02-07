# Priority
-  [[Diff Sync.canvas|Diff Sync]]
- Single button operation: 
	- path as board ID
	- hashlib.md5(str(brd.GetFileName()).encode()).hexdigest()
	- scan existing FC document to get existing Part pbc (if any),
	- get pcb id on connection established, see if this pcb in document - delete existing, replace with kc pcb but! keep global position and orientation
	- make Sync button generic - always check if pcb needs to be drawn, redrawn or updated

# Bugs
- QObject timers

# Ideas
- add Part Object to plugin instance (if existing FC project is opened, no need for importing PCB again)
- script for installing plugins (creating symlinks...)
- Loading bar for adding elements to part...
# Notes
- 