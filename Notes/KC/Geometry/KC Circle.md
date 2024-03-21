### Geometry:
*Center, radius*

PCB_SHAPE:
- GetCenter() -> VECTOR2I
- GetRadius() -> INT
- GetEnd() -> VECTOR2I

### Editing:
*Change radius of existing circle by modifying EndPoint (which is a point on the circle. More precisely: modify y coordinate to y + radius_diff*

- drw.SetEnd(pcbnew.VECTOR2I(old_end_x, old_end_y - old_radius + new_radius))