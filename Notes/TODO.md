# Priority


# Bugs
![[Pasted image 20240313175340.png]]

# Ideas
- data model change:
	- instead of lists, group drawings and footprints in dictionary where KIID is key.
	- this would reduce all search utility functions from O(n^2) to O(n) since .get() is O(1)
# Notes
