import FreeCAD as App
import FreeCADGui as Gui
import Sketcher

"""
    Functions for adding constrints to FC Sketch
    Constraints in Sketch are named by type_tag, where tag in .Tag attribute of geometry being constrained.
"""


def getConstraintByTag(sketch, tag):
    """
    Get dictionary of constraint indexes of geometry properties based on geometry Tag
    :param sketch: Skether::Sketch object
    :param tag: string (geometry.Tag)
    :return: dictionary of indexes as values
    """
    result = {}
    for i, c in enumerate(sketch.Constraints):
        if not tag in c.Name:
            continue

        if "radius" in c.Name:
            result.update({"radius": i})
        elif "distance_x" in c.Name:
            result.update({"dist_x": i})
        elif "distance_y" in c.Name:
            result.update({"dist_y": i})

    return result


def constrainPadDelta(sketch, list_of_constraints):
    """
    Constrain pad geometries in sketch relative (Delta Pos) to first pad of footprint
    :param sketch: Sketcher::SketchObject
    :param list_of_constraints: list of tuples of part and index -> [(Part object, index ) , ...]
    """
    # Part objects are first elements of list
    pad_parts = [e[0] for e in list_of_constraints]
    # Indexes are second elements of list
    indexes = [e[1] for e in list_of_constraints]

    # First pad is not constrained, other are X and Y constrained relative to first pad (Delta Pos parameters)
    for i in range(len(indexes)):
        if i == 0:
            # First pad is not constrained
            continue
        else:
            # All other pads are constrained to first pad by delta position coordinates
            pad_part = pad_parts[i]
            dx = pad_part.PosDelta.x
            dy = pad_part.PosDelta.y
            tag = pad_part.Tags[0]

            # Add X constraint
            sketch.addConstraint(Sketcher.Constraint("DistanceX",         # Type
                                                     indexes[0],          # Index of first pad
                                                     3,                   # Index of vertex (3 is center)
                                                     indexes[i],          # Index of current pad
                                                     3,                   # Index if vertex (3 is center)
                                                     dx))                 # X value of delta position
            # Name X constraint
            sketch.renameConstraint(sketch.ConstraintCount - 1, f"distance_x_{tag}")
            # Add Y constraint
            sketch.addConstraint(Sketcher.Constraint("DistanceY",         # Type
                                                     indexes[0],          # Index of first pad
                                                     3,                   # Index of vertex (3 is center)
                                                     indexes[i],          # Index of current pad
                                                     3,                   # Index if vertex (3 is center)
                                                     dy))                 # Y value of delta position
            # Name Y constraint
            sketch.renameConstraint(sketch.ConstraintCount - 1, f"distance_y_{tag}")


def constrainRectangle(sketch, lines, tags):
    """
    Add two vertical and two horizontal constraints to sketch
    :param sketch: Sketcher::SketchObject
    :param lines: list of indexes representing geometries in sketch
    :param tags: list of tags of geometries in sketch
    """

    # # Perpendicular constraints: OUTDATED
    # for i, geom in enumerate(lines):
    #     # Constrain only first 3 lines, 4->1 (last to first) is overconstrained
    #     if i < (len(lines) - 1):
    #         sketch.addConstraint(Sketcher.Constraint("Perpendicular", geom, geom + 1))
    #         sketch.renameConstraint(sketch.ConstraintCount - 1,
    #                                 f"perpendicular_rectangle_{tags[i]}")
    #
    # # Get ONLY FIRST line of reactangle in sketch, constrain it to vertical or horizontal.
    # # Because other lines are perpendicular, rectangle is constrained with free vertexes
    # line = sketch.Geometry[lines[0]]
    # if line.StartPoint.x == line.EndPoint.x:
    #     sketch.addConstraint(Sketcher.Constraint("Vertical", lines[0]))
    #     sketch.renameConstraint(sketch.ConstraintCount - 1,
    #                             f"vertical_rectangle_{tags[0]}")
    # elif line.StartPoint.y == line.EndPoint.y:
    #     sketch.addConstraint(Sketcher.Constraint("Horizontal", lines[0]))
    #     sketch.renameConstraint(sketch.ConstraintCount - 1,
    #                             f"horizontal_rectangle_{tags[0]}")

    for i, geom in enumerate(lines):
        # Get geometry object from sketch (has attributes like .StartPoint, .x, .y etc)
        line = sketch.Geometry[geom]

        # Check if x coordianate is same, add vertical constraint
        if line.StartPoint.x == line.EndPoint.x:
            sketch.addConstraint(Sketcher.Constraint("Vertical", geom))
            sketch.renameConstraint(sketch.ConstraintCount - 1,
                                    f"vertical_rectangle_{tags[i]}")

        # Check if y coordianate is same, add horizontal constraint
        elif line.StartPoint.y == line.EndPoint.y:
            sketch.addConstraint(Sketcher.Constraint("Horizontal", geom))
            sketch.renameConstraint(sketch.ConstraintCount - 1,
                                    f"horizontal_rectangle_{tags[i]}")


def coincidentGeometry(sketch):
    """
    Coincident constraint all geometry in sketch with same start/end points to each other
    to create continuous edge of lines and arcs
    :param sketch: Sketcher::SketchObject
    """
    # Class for storing geometry, index and tag of said geometry in sketch (setting constraint works by indexing,
    #                                                                       naming constraint by tag)
    # If geometry is a class which contains FC sketch.Geometry object as .shape attribute, StartPoint and EndPoint
    # attributes are accessible by geom.shape.StarPoint
    class SketchGeometry:
        def __init__(self, shape, i, tag):
            self.shape = shape
            self.index = i
            self.tag = tag

    # Get indexes of all arcs and lines in sketch (circes cant be coincident constrained)
    geoms = []
    for index, geom in enumerate(sketch.Geometry):
        if ("Line" in geom.TypeId) or ("Arc" in geom.TypeId):
            # Create object for each geometry containing Part::Geom, index and Tag in sketch
            geoms.append(
                SketchGeometry(geom, index, geom.Tag)
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
                    sketch.renameConstraint(sketch.ConstraintCount - 1,
                                            f"coincident_edge_{geom_1.tag}")
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
                            sketch.renameConstraint(sketch.ConstraintCount - 1,
                                                    f"coincident_edge_{geom_2.tag}")

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
                            sketch.renameConstraint(sketch.ConstraintCount - 1,
                                                    f"coincident_edge_{geom_1.tag}")