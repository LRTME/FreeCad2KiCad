
First create a circle with center and radius, then circle to Part.ArcOfCircle and specify parameters (angle start and end in radians)
- Radius <- float
- Position <- FC Vector
- Direction <- FC Vector (*z-axis*)
- First parameter <- float / *rad*
- Last parameter <- float / *rad*

- arc.SetParameterRange() <- float, float

*ArcOfCircle (Radius : 1, Position : (0, 0, 0), Direction : (0, 0, 1), Parameter : (0, 3.14159))*
#### Create arc from circle
center = FreeCAD.Vector(0, 0, 0)
axis = FreeCAD.Vector(0, 0, 1) 
radius = 1.0 
start = start angle in red
last = end angle in rad
arc = Part.ArcOfCircle(circle, start, last)
sketch.addGeometry(arc)


