# Priority
- board origin: store relative coordinates in data model.
- ![[MicrosoftTeams-image.png]]
	- brd.GetDesignSettings().GetAuxOrigin()
	- tolerance when scanning: use old values if withing 1 nm
	-  check mounting hole position
	- #TODO coincident tolerance
- FC Demo IDs don't match

# Bugs
- xy flip imported models (LED)

# Ideas
- data model change:
	- instead of lists, group drawings and footprints in dictionary where KIID is key.
	- this would reduce all search utility functions from O(n^2) to O(n) since .get() is O(1)
# Notes
