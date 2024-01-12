
### Priority
- new drawings in FC have no kiid.
		get unique identifier on FC side, attach it to data model.
		have fc draw it to get kiid.
		send kiid back to fc with FC identifier to be able to override kiid
		problem with this: sync will be dropped
		attach temp id on FC side : "new_object_in_FC"
		add this one to deleted, add new in KC, send new drawing to "Added" so that new one is redrawn and diff doesn't fall
- socket.listend() -> timeout? chekc for flag when requesting server shutdown
- DONE       connect/disconnect FC: handle when KC disconects properly
- collision detection (KiCAD overrides FreeCAD with footprints, FC overrides drawings)?  Timestamp?
- handle sending PCB from KC to FC after connect/disconnect/connect (crash)
- when adding an Arc to Sketch, Scanner recognises it as a circle.
- DONE      Handle Diff Sync (see [[Diff Sync.canvas|Diff Sync]])
- readme
- fc ->kc diff 3D models?
- add Part Object to plugin instance (if existing FC project is opened, no need for importing PCB again)


## Ideas
- script for installing plugins (creating symlinks...)
- Loading bar for adding elements to part...
