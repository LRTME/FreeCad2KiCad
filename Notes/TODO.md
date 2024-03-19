# Priority
- board origin![[MicrosoftTeams-image.png]]
-  FC Demo IDs don't match
- merge footprint diff (reset back to original position?) <- težko implementirati
  drop sync, redraw?

# Bugs
- xy flip imported models (LED)

# Ideas
- data model change:
	- instead of lists, group drawings and footprints in dictionary where KIID is key.
	- this would reduce all search utility functions from O(n^2) to O(n) since .get() is O(1)
# Notes
