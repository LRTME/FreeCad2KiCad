"""
    #TODO docstring
"""
import hashlib
import logging
import os
import random

from API_scripts.utils import getDictEntryByKIID, getDrawingByKIID, relativeModelPath, KiCADVector


test_diff = {
    "drawings": {
        "changed": [
            {
                "23941696-887f-4049-8b42-3263bd5982b3": [
                    [
                        "points",
                        [
                            [
                                106680000,
                                74930000
                            ],
                            [
                                112082651,
                                74930000
                            ],
                            [
                                112082651,
                                78168837
                            ],
                            [
                                106680000,
                                78168837
                            ]
                        ]
                    ]
                ]
            }
        ]
    }
}

# Initialize logger
logger = logging.getLogger("UPDATER")

# Testing
# shape = pcbnew.PCB_SHAPE()
# shape.SetLayer(pcbnew.Edge_cuts)
#
# // Line
# line.SetStartEnd(p1, p2)
#
# // Arc
# arc.SetShape(pcbnew.SHAPE_T_ARC)
# arc.SetArcGeometry(p2, md, p2)
#
# // Circle
#					        		 x      y
# circ.SetArcGemetry(p1, VECTOR2I(p1[0], p2[1] + diameter), p1)
#
# // Polygon
# p1 = pcbnew.VECTOR2I(0,0)
# p2 = pcbnew.VECTOR2I(100000000, 0)
# p3 = pcbnew.VECTOR2I(100000000, 100000000)
# p4 = pcbnew.VECTOR2I(0, 100000000)
# points = [p1,p2,p3,p4]
#
# poly.SetShape(pcbnew.SHAPE_T_POLY)
# poly.SetPolyPoints(points)
#
# // Rectangle
# rect = pcbnew.PCB_SHAPE()
# rect.SetShape(pcbnew.SHAPE_T_RECT)
#
# rect2.SetTop(0)
# rect2.SetRight(100000000)
# rect2.SetBottom(100000000)
# rect2.SetLeft(0)


class PcbUpdater:

    @staticmethod
    def updateDrawings(brd, pcb, diff):

        logger.debug(f"updateDrawings called")

        key = "drawings"
        changed = diff[key].get("changed")
        added = diff[key].get("added")
        removed = diff[key].get("removed")

        # TODO added, removed

        # Go through list of changed drawings in diff dictionary
        if changed:
            for entry in changed:
                logger.debug(entry.items())
                # Parse entry in dictionary to get kiid and changed values:
                # Get dictionary items as 1 tuple
                items = [(x, y) for x, y in entry.items()]
                # First index to get tuple inside list  items = [(x,y)]
                # Second index to get values in tuple
                kiid = items[0][0]
                changes = items[0][1]

                logger.debug(f"kiid: {kiid}, changes: {changes}")

                # Old entry in pcb dictionary
                drawing = getDictEntryByKIID(pcb["drawings"], kiid)
                logger.debug(f"Old dictionary entry: {drawing}")
                # Drawing object in KiCAD
                drw = getDrawingByKIID(brd, kiid)
                logger.debug(f"KiCAD drawing: {drw}")

                for change in changes:
                    drawing_property, value = change[0], change[1]
                    # Apply changes based on type of geometry
                    geometry_type = drw.ShowShape()

                    if "Line" in geometry_type:
                        logger.debug(f"Changing line")
                        try:
                            # Convert new xy coordinates to VECTOR2I object
                            point_new = KiCADVector(value)
                        except Exception as e:
                            logger.exception(e)

                        # Change start or end point of existing line
                        if drawing_property == "start":
                            logger.debug(f"Changing start to {point_new}")
                            drw.SetStart(point_new)
                        elif drawing_property == "end":
                            logger.debug(f"Changing end to {point_new}")
                            drw.SetEnd(point_new)

                    elif "Rect" in geometry_type or "Polygon" in geometry_type:
                        # TODO how is rectangle handeld differenty then polygon?
                        pass

                    elif "Arc" in geometry_type:
                        # Convert point to VECTOR2I object
                        p1 = KiCADVector(value[0])  # Start / first point
                        md = KiCADVector(value[1])  # Arc middle / second point
                        p2 = KiCADVector(value[2])  # End / third point

                        # Change existing arc
                        drw.SetArcGeometry(p1, md, p2)

                    elif "Circle" in geometry_type:
                        if drawing_property == "center":
                            # Convert point to VECTOR2I object
                            center_new = KiCADVector(value)
                            # Change circle center point
                            drw.SetCenter(center_new)

                        elif drawing_property == "radius":
                            # TODO figure out how to change properties of circle SHAPE
                            pass

                            # # Circle is treated as 360 degree, three-point arc
                            # p1 = KiCADVector(value[0])  # Start / first point
                            # md = KiCADVector(value[1])  # Arc middle / second point
                            # p2 = KiCADVector(value[2])  # End / third point
                            #
                            # circ.SetArcGemetry(p1, VECTOR2I(p1[0], p2[1] + diameter), p1)