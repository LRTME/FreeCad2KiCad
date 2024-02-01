# Priority
- DONE when changing fp model placement -> actually change fp parent placement
- collision detection (KiCAD overrides FreeCAD with footprints, FC overrides drawings)?  Timestamp?
	- complete reimplementation (see [[Diff Sync.canvas|Diff Sync]])

# Bugs
- QObject timers
- handle sending PCB from KC to FC after connect/disconnect/connect (crash)

# Ideas
- add Part Object to plugin instance (if existing FC project is opened, no need for importing PCB again)
- script for installing plugins (creating symlinks...)
- Loading bar for adding elements to part...
