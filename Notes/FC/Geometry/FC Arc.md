
First create a circle with center and radius, then circle to Part.ArcOfCircle and specify parameters (angle start and end in radians)
- arc.StartPoint
- arc.EndPoint
- md = arc.value(arc.parameterAtDistance(arc.length() / 2, arc.FirstParameter))

*ArcOfCircle (Radius : 1, Position : (0, 0, 0), Direction : (0, 0, 1), Parameter : (0, 3.14159))*

#### Create a three point arc
arc = Part.ArcOfCircle(p1, md, p2)

#### Editing
Delete, draw new

#### Create arc from circle
center = FreeCAD.Vector(0, 0, 0)
axis = FreeCAD.Vector(0, 0, 1) 
radius = 1.0 
start = start angle in red
last = end angle in rad
arc = Part.ArcOfCircle(circle, start, last)
sketch.addGeometry(arc)


