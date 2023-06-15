import FreeCAD as App
import FreeCADGui as Gui
import Sketcher

"""
    Functions for adding constrints to FC Sketch
"""


def constrainPadDelta(sketch, list_of_constraints):
    """
    Constrain pad geometries in sketch relative (Delta Pos) to first pad of footprint
    :param sketch: Sketcher::SketchObject
    :param list_of_constraints: list [tuple of int and tuple -> (index, (const_x, const_y))   ,  ...]
    """
    # Indexes are first elements of list entry
    indexes = [e[0] for e in list_of_constraints]
    # Constraint tuples are second element of list entry
    constraints = [e[1] for e in list_of_constraints]

    # First pad is not constrained, other are X and Y constrained relative to first pad (Delta Pos parameters)
    for i in range(len(indexes)):
        if i == 0:
            # First pad is not constrainded
            continue
        else:
            # All other pads are constraint to first pad by delta position coordinates
            # Add X constraint
            sketch.addConstraint(Sketcher.Constraint("DistanceX",         # Type
                                                     indexes[0],          # Index of first pad
                                                     3,                   # Index of vertex (3 is center)
                                                     indexes[i],          # Index of current pad
                                                     3,                   # Index if vertex (3 is center)
                                                     constraints[i][0]))  # X value of delta position
            # Add Y constraint
            sketch.addConstraint(Sketcher.Constraint("DistanceY",         # Type
                                                     indexes[0],          # Index of first pad
                                                     3,                   # Index of vertex (3 is center)
                                                     indexes[i],          # Index of current pad
                                                     3,                   # Index if vertex (3 is center)
                                                     constraints[i][1]))  # Y value of delta position


def coincidentLineVerteces(sketch, lines):
    """
    Constrains multiple lines (forming polygon or rectangle) to eachother (end->start)
    :param sketch: Sketcher::SketchObject
    :param lines: list of indexes representing geometries in sketch
    """
    for i, geom in enumerate(lines):
        if i < (len(lines) - 1):
            sketch.addConstraint(
                Sketcher.Constraint(
                    "Coincident",
                    geom,      # Current line index
                    1,         # Curent line start (vertex number)
                    geom + 1,  # Next line index
                    2          # Next line end (vertex number)
                )
            )
        else:
            # If last line - constrain it to first line
            sketch.addConstraint(
                Sketcher.Constraint(
                    "Coincident",
                    geom,      # Current line index
                    1,         # Curent line start (vertex number)
                    lines[0],  # First line index
                    2          # First line end (vertex number)
                )
            )


def constrainRectangle(sketch, lines):
    """
    Constraint first line of rect to horizontal or vertical and constrains lines perpendicular to eachother
    :param sketch: Sketcher::SketchObject
    :param lines: list of indexes representing geometries in sketch
    """

    # Perpendicular constraints:
    for i, geom in enumerate(lines):
        # Constrain only first 3 lines, 4->1 (last to first) is overconstrained
        if i < (len(lines) - 1):
            sketch.addConstraint(Sketcher.Constraint("Perpendicular", geom, geom + 1))

    # Get ONLY FIRST line of reactangle in sketch, constrain it to vertical or horizontal.
    # Because other lines are perpendicular, rectangle is constrained with free vertexes
    line = sketch.Geometry[lines[0]]
    if line.StartPoint.x == line.EndPoint.x:
        sketch.addConstraint(Sketcher.Constraint("Vertical", lines[0]))
    elif line.StartPoint.y == line.EndPoint.y:
        sketch.addConstraint(Sketcher.Constraint("Horizontal", lines[0]))


def coincidentGeometry(sketch):
    """
    Coincident constraint all geometry in sketch with same start/end points to each other
    to create continuous edge of lines and arcs
    :param sketch: Sketcher::SketchObject
    """
    # Class for storing geometry and index of said geometry in sketch (setting constraint works by indexing)
    class SketchGeometry:
        def __init__(self, shape, i):
            self.shape = shape
            self.index = i

    # Get indexes of all arcs and lines in sketch (circes cant be coincident constrained)
    geoms = []
    for index, geom in enumerate(sketch.Geometry):
        if ("Line" in geom.TypeId) or ("Arc" in geom.TypeId):
            # Create object for each geometry containing Part::Geom and index in sketch
            geoms.append(
                SketchGeometry(geom, index)
            )

    # Compare every geometry in sketch to eachother
    for geom_1 in geoms:
        for geom_2 in geoms:
            # Ignore if same geometry
            if geom_1.shape != geom_2.shape:

                if geom_1.shape.StartPoint == geom_2.shape.EndPoint:
                    sketch.addConstraint(
                        Sketcher.Constraint(
                            "Coincident",
                            geom_1.index,   # First geometry
                            1,              # Start vertex of first geometry
                            geom_2.index,   # Second geometry
                            2               # End vertex of second geometry
                        )
                    )
                    break

                elif geom_1.shape.StartPoint == geom_2.shape.StartPoint:
                    if geom_1.shape.TypeId != geom_2.shape.TypeId:
                        # Edge case: constrain arc to line:
                        # Vertex indexes of arc do not correspond to 1-start, 2-end
                        if "Arc" in geom_1.shape.TypeId:
                            sketch.addConstraint(
                                Sketcher.Constraint(
                                    "Coincident",
                                    geom_1.index,
                                    2,
                                    geom_2.index,
                                    1
                                )
                            )

                elif geom_1.shape.EndPoint == geom_2.shape.EndPoint:
                    if geom_1.shape.TypeId != geom_2.shape.TypeId:
                        # Edge case: constrainarc to line:
                        # Vertex indexes of arc do not correspond to 1-start, 2-end
                        if "Arc" in geom_1.shape.TypeId:
                            sketch.addConstraint(
                                Sketcher.Constraint(
                                    "Coincident",
                                    geom_1.index,
                                    1,
                                    geom_2.index,
                                    2
                                )
                            )
