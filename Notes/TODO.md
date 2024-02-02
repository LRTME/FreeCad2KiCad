# Priority
- collision detection (KiCAD overrides FreeCAD with footprints, FC overrides drawings)?  Timestamp?
	- complete reimplementation (see [[Diff Sync.canvas|Diff Sync]])
	- handle Disconnect
# Bugs
- QObject timers
- handle sending PCB from KC to FC after connect/disconnect/connect (crash) posible cause: doc_gui object when changing pcb color

# Ideas
- add Part Object to plugin instance (if existing FC project is opened, no need for importing PCB again)
- script for installing plugins (creating symlinks...)
- Loading bar for adding elements to part...
