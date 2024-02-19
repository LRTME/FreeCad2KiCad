# Priority
- attach document path for importing 3dmodels:
	- some models have relative path to kicad_proj file. search also that directory for models

# Bugs


# Ideas
- data model change:
	- instead of lists, group drawings and footprints in dictionary where KIID is key.
	- this would reduce all search utility functions from O(n^2) to O(n) since .get() is O(1)
# Notes
