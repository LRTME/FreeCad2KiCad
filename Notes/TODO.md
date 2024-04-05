# Priority
- FC Demo IDs don't match - reimport demo boards in FC with new board origin positions

# Bugs
- xy flip imported models (LED) <- not fixable

# Ideas
- data model change:
	- instead of lists, group drawings and footprints in dictionary where KIID is key.
	- this would reduce all search utility functions from O(n^2) to O(n) since .get() is O(1)
# Notes
