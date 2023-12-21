"""
    Collection of functions that update existing objects (and add new drawing) in pcbnew.BOARD object
"""
import pcbnew

import hashlib
import logging

from API_scripts.utils import *


# Initialize logger
logger = logging.getLogger("UPDATER")


class PcbUpdater:

    @staticmethod
    def updateDrawings(brd, pcb, diff):
        key = "drawings"
        changed = diff[key].get("changed")
        added = diff[key].get("added")
        removed = diff[key].get("removed")

        if added:
            for drawing in added:
                try:
                    # Call function to add a drawing to board (also updated kiid property of data model)
                    PcbUpdater.addDrawing(brd, drawing)
                    logger.debug(f"Added new drawing: {drawing}")
                    # Add drawing to dictionary
                    pcb[key].append(drawing)
                except Exception as e:
                    logger.exception(e)

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
                # Changes is a dictionary
                changes = items[0][1]

                # Old entry in pcb dictionary
                drawing = getDictEntryByKIID(pcb["drawings"], kiid)
                # Drawing object in KiCAD
                drw = getDrawingByKIID(brd, kiid)

                for drawing_property, value in changes.items():
                    # Apply changes based on type of geometry
                    shape = drw.ShowShape()

                    if "Line" in shape:
                        # Convert new xy coordinates to VECTOR2I object
                        # In this case, value is a single point
                        point_new = KiCADVector(value)
                        # Change start or end point of existing line
                        if drawing_property == "start":
                            drw.SetStart(point_new)
                        elif drawing_property == "end":
                            drw.SetEnd(point_new)

                    elif "Rect" in shape:
                        x_coordinates = []
                        y_coordinates = []
                        # In this case, value is list of point
                        for p in value:
                            # Gather all x coordinates to list to find the biggest and smallest: used for setting right
                            # and left positions of rectangle
                            x_coordinates.append(p[0])
                            # Gather all y coordinates for setting top and bottom position of rectangle
                            y_coordinates.append(p[1])

                        # Rectangle is edited not by point, but by rectangle sides. These are determined by biggest and
                        # smallest x and y coordinates
                        rect_top = min(y_coordinates)
                        rect_bottom = max(y_coordinates)
                        rect_left = min(x_coordinates)
                        rect_right = max(x_coordinates)

                        # Edit existing rectangle
                        drw.SetTop(rect_top)
                        drw.SetBottom(rect_bottom)
                        drw.SetLeft(rect_left)
                        drw.SetRight(rect_right)

                    elif "Poly" in shape:
                        logger.debug("editing poly")
                        points = []
                        # In this case, value is list of points
                        for p in value:
                            # Convert all points to VECTOR2I
                            point = KiCADVector(p)
                            points.append(point)

                        # Edit exiting polygon
                        drw.SetPolyPoints(points)

                    elif "Arc" in shape:
                        # Convert point to VECTOR2I object
                        p1 = KiCADVector(value[0])  # Start / first point
                        md = KiCADVector(value[1])  # Arc middle / second point
                        p2 = KiCADVector(value[2])  # End / third point
                        # Change existing arc
                        drw.SetArcGeometry(p1, md, p2)

                    elif "Circle" in shape:
                        if drawing_property == "center":
                            # Convert point to VECTOR2I object
                            center_new = KiCADVector(value)
                            # Change circle center point
                            drw.SetCenter(center_new)

                        elif drawing_property == "radius":
                            # Change radius of existing circle by modifying EndPoint (which is a point on the circle
                            # More precisely: modify y coordinate to y + radius_diff
                            new_radius = value
                            # Get old radius
                            old_radius = drw.GetRadius()
                            # Calculate diference in radii (is needed for modifying absolute coordinate)
                            radius_diff = old_radius - new_radius

                            # Get end point of original circle
                            end_point = [
                                drw.GetEnd()[0],
                                drw.GetEnd()[1],
                            ]
                            # Change y coordinate
                            end_point[1] -= radius_diff
                            # Convert list back to vector
                            end_point = KiCADVector(end_point)

                            # Set new end point to drawing
                            drw.SetEnd(end_point)

                    # Update data model
                    drawing.update({drawing_property: value})

                # Hash itself when all changes applied
                drawing_hash = hashlib.md5(str(drawing).encode("utf-8")).hexdigest()
                drawing.update({"hash": drawing_hash})

    @staticmethod
    def updateFootprints(brd, pcb, diff):
        key = "footprints"
        changed = diff[key].get("changed")
        removed = diff[key].get("removed")

        if changed:
            for entry in changed:
                # Get dictionary items as 1 tuple
                items = [(x, y) for x, y in entry.items()]
                # First index to get tuple inside list  items = [(x,y)]
                # Second index to get values in tuple
                kiid = items[0][0]
                # Changes is a dictionary
                changes = items[0][1]

                logger.debug(f"Got change: {kiid} {changes}")

                # Old entry in pcb dictionary
                footprint = getDictEntryByKIID(pcb["footprints"], kiid)
                # Footprint object in KiCAD
                fp = getFootprintByKIID(brd, kiid)
                if fp is None or footprint is None:
                    continue

                for fp_property, value in changes.items():
                    # Apply changes based on property
                    if fp_property == "ref":
                        fp.SetReference(value)

                    elif fp_property == "pos":
                        fp.SetPosition(KiCADVector(value))

                    elif fp_property == "rot":
                        fp.SetOrientationDegrees(value)

                    elif fp_property == "layer":
                        layer = None
                        # Set int value of layer (so it can be set to FOOTPRINT object)
                        if value == "Top":
                            layer = 0
                        elif value == "Bot":
                            layer = 31

                        if layer:
                            # TODO this doesn't move silkscreen to bottom layer
                            fp.SetLayer(layer)
                        else:
                            logger.error(f"Invalid layer for {entry}")

                    elif fp_property == "3d_models":
                        # TODO ?
                        pass

                    # Update data model
                    footprint.update({fp_property: value})

                # Hash itself when all changes applied
                footprint_hash = hashlib.md5(str(footprint).encode("utf-8")).hexdigest()
                footprint.update({"hash": footprint_hash})


    @staticmethod
    def addDrawing(brd, drawing):
        logger.debug(f"Adding new drawing: {drawing}")
        # Create new pcb shape object, add shape to Edge Cuts layer
        new_shape = pcbnew.PCB_SHAPE()
        new_shape.SetLayer(pcbnew.Edge_Cuts)
        new_shape.SetWidth(100000)

        shape = drawing["shape"]
        if "Line" in shape:
            # Convert list to VECTOR2I
            start = KiCADVector(drawing["start"])
            end = KiCADVector(drawing["end"])
            # Set properties of PCB_SHAPE object
            # KC Bug if using shape.SetStartEnd() method
            # Workaround: set start and end individually
            new_shape.SetStart(start)
            new_shape.SetEnd(end)

        elif "Circle" in shape:
            new_shape.SetShape(pcbnew.SHAPE_T_CIRCLE)
            center = drawing["center"]
            radius = drawing["radius"]
            # Calculate circle end point (x is same as center, y is moved down by radius)
            end_point = [
                center[0],
                center[1] + radius
            ]
            # Convert to VECTOR2I
            center = KiCADVector(center)
            end_point = KiCADVector(end_point)
            # Set drawing geometry (end point is the only way to set circle radius)
            new_shape.SetCenter(center)
            new_shape.SetEnd(end_point)

        elif "Arc" in shape:
            new_shape.SetShape(pcbnew.SHAPE_T_ARC)
            # Get three point of arc from list
            start = KiCADVector(drawing["points"][0])
            arc_md = KiCADVector(drawing["points"][1])
            end = KiCADVector(drawing["points"][2])
            # Set three arc points
            new_shape.SetArcGeometry(start, arc_md, end)

        else:
            logger.exception(f"Invalid new drawing shape: {drawing}")
            return

        # Add shape to board object
        brd.Add(new_shape)
        # Get new drawing's id:
        kiid = new_shape.m_Uuid.AsString()
        # Update data model with new drawing's kiid
        drawing.update({"kiid": kiid})