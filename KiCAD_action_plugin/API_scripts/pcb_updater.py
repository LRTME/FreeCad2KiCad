"""
    Collection of functions that update existing objects (and add new drawing) in pcbnew.BOARD object
"""
import pcbnew

import hashlib
import logging

from API_scripts.utils import (relative_model_path, get_dict_entry_by_kiid, get_drawing_by_kiid, get_footprint_by_kiid,
                               kicad_vector)


# Initialize logger
logger = logging.getLogger("UPDATER")


class PcbUpdater:
    """ This class contains only static methods. """

    @staticmethod
    def remove_drawings(brd: pcbnew.BOARD, pcb: dict, removed: list):
        """ Deletes drawings from board by KIID, removes entry from data model. """
        logger.info(f"Deleting drawings {removed}")

        # Walk list of KIIDs to be removed
        for kiid_to_remove in removed:
            logger.debug(f"KIID to remove: {kiid_to_remove}")
            try:
                # Remove from data model:
                # Get drawing from data model by kiid
                drawing_in_data_model = get_dict_entry_by_kiid(pcb.get("drawings"), kiid_to_remove)
                if drawing_in_data_model:
                    logger.debug(f"Removing drawing: {drawing_in_data_model}")
                    # Remove entry from data model
                    pcb.get("drawings").remove(drawing_in_data_model)

                # Remove from board
                # Get PCB SHAPE object from board
                drw = get_drawing_by_kiid(brd, kiid_to_remove)
                if drw:
                    logger.debug(f"Deleting drw: {drw}")
                    # Call pcbnew method to delete PCB SHAPE from BOARD
                    drw.DeleteStructure()
            except Exception as e:
                logger.exception(e)

    @staticmethod
    def update_drawings(brd: pcbnew.BOARD, pcb: dict, changed: list):
        """ Update pcbnew objects with Diff data. Add auxiliary board origin coordinates to relative coordinates in data
        model. """
        logger.info("Updating drawings")
        board_origin = brd.GetDesignSettings().GetAuxOrigin()

        for entry in changed:
            logger.debug(f"Updating {entry}")
            # Parse entry in dictionary to get kiid and changed values:
            # Get dictionary items as 1 tuple
            items = [(x, y) for x, y in entry.items()]
            # First index to get tuple inside list  items = [(x,y)]
            # Second index to get values in tuple
            kiid = items[0][0]
            # Changes is a dictionary
            changes = items[0][1]

            # Old entry in pcb dictionary
            drawing = get_dict_entry_by_kiid(pcb["drawings"], kiid)
            if drawing is None:
                logger.error(f"Cannot find drawing in data model by KIID: {kiid}")

            # Drawing object in KiCAD
            drw = get_drawing_by_kiid(brd, kiid)
            if drw is None:
                logger.error(f"Cannot find drawing is pcb by KIID: {kiid}")

            for drawing_property, value in changes.items():
                # Apply changes based on type of geometry
                shape = drw.ShowShape()

                if "Line" in shape:
                    # Add aux board origin to relative value
                    absolute_coordinates = [value[0] + board_origin[0],
                                            value[1] + board_origin[1]]
                    # Convert new xy coordinates to VECTOR2I object
                    # In this case, value is a single point
                    point_new = kicad_vector(absolute_coordinates)
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
                        # Add board origin x to relative x coordinate
                        x_coordinates.append(p[0] + board_origin[0])
                        # Gather all y coordinates for setting top and bottom position of rectangle
                        # Add board origin y to relative y coordinate
                        y_coordinates.append(p[1] + board_origin[1])

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
                    logger.debug("Updating poly")
                    points = []
                    # In this case, value is list of points
                    for p in value:
                        # Add aux board origin to relative coordinates
                        absolute_coordinates = [p[0] + board_origin[0],
                                                p[1] + board_origin[1]]
                        # Convert all points to VECTOR2I
                        point = kicad_vector(absolute_coordinates)
                        points.append(point)

                    # Edit exiting polygon
                    drw.SetPolyPoints(points)

                elif "Arc" in shape:
                    # First index is arc point (p1, md, p2), second index is x and y
                    # Add aux origin to relative coordinates
                    absolute_p1 = [value[0][0] + board_origin[0],
                                   value[0][1] + board_origin[1]]
                    absolute_md = [value[1][0] + board_origin[0],
                                   value[1][1] + board_origin[1]]
                    absolute_p2 = [value[2][0] + board_origin[0],
                                   value[2][1] + board_origin[1]]
                    # Convert point to VECTOR2I object
                    p1 = kicad_vector(absolute_p1)  # Start / first point
                    md = kicad_vector(absolute_md)  # Arc middle / second point
                    p2 = kicad_vector(absolute_p2)  # End / third point
                    # Change existing arc
                    drw.SetArcGeometry(p1, md, p2)

                elif "Circle" in shape:
                    logger.debug("Editing circle")
                    if drawing_property == "center":
                        # Add aux board origin to relative coordinates
                        absolute_center = [value[0] + board_origin[0],
                                           value[1] + board_origin[1]]
                        # Convert point to VECTOR2I object
                        center_new = kicad_vector(absolute_center)
                        logger.debug(f"Updating position of circle {center_new}")
                        # Change circle center point: SetPosition method instead of SetCenter method. SetCenter also
                        # changes radius (unsure of reason / or bug)
                        drw.SetPosition(center_new)

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
                        end_point = kicad_vector(end_point)

                        logger.debug(f"Updating end point: {end_point}")
                        # Set new end point to drawing
                        drw.SetEnd(end_point)

                # Update data model
                drawing.update({drawing_property: value})

            # Remove existing hash from data, so it doesn't affect new hash calculation
            drawing.update({"hash": ""})
            # Hash itself when all changes applied
            drawing_hash = hashlib.md5(str(drawing).encode()).hexdigest()
            drawing.update({"hash": drawing_hash})

    logger.info("Finished drawings")

    @staticmethod
    def update_footprints(brd: pcbnew.BOARD, pcb: dict, footprints: dict):
        """ Apply data from Diff to pcbnew objects.
        Add board origin coordinates to relative coordinates in data model. """
        board_origin = brd.GetDesignSettings().GetAuxOrigin()

        logger.info("Updating footprints")
        changed = footprints.get("changed")
        # removed = footprints.get("removed")

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
                footprint = get_dict_entry_by_kiid(pcb["footprints"], kiid)
                if footprint is None:
                    logger.error(f"Cannot find footprint {kiid} in data model.")
                    continue

                # Footprint object in KiCAD
                fp = get_footprint_by_kiid(brd, kiid)
                if fp is None:
                    logger.error(f"Cannot find footprint {kiid} in data PCB.")
                    continue

                for footprint_property, value in changes.items():
                    # Apply changes based on property
                    if footprint_property == "ref":
                        fp.SetReference(value)

                    elif footprint_property == "pos":
                        # Add aux board origin to relative coordinates
                        absolute_position = [value[0] + board_origin[0],
                                             value[1] + board_origin[1]]
                        fp.SetPosition(kicad_vector(absolute_position))

                    elif footprint_property == "rot":
                        fp.SetOrientationDegrees(value)
                        logger.debug(f"Changed rotation of {kiid} to {value}")

                    elif footprint_property == "layer":
                        layer = None
                        # Set int value of layer (so it can be set to FOOTPRINT object)
                        if value == "Top":
                            layer = 0
                        elif value == "Bot":
                            layer = 31

                        if layer:
                            fp.SetLayer(layer)
                        else:
                            logger.error(f"Invalid layer for {entry}")

                    elif footprint_property == "3d_models":
                        pass

                    # Update data model
                    footprint.update({footprint_property: value})
                    logger.debug(f"Updated data model: {footprint_property} {value}")

                logger.debug(f"fp data:{footprint}")
                # Remove existing hash from data, so it doesn't affect new hash calculation
                footprint.update({"hash": ""})
                # Hash itself when all changes applied
                footprint_hash = hashlib.md5(str(footprint).encode()).hexdigest()
                footprint.update({"hash": footprint_hash})
                logger.debug(f"Changed {kiid}")

        logger.info("Finished footprints")

    @staticmethod
    def add_drawing(brd: pcbnew.BOARD, drawing: dict) -> str:
        """
        Add a drawing specified in drawing dictionary to board. When board is added, KIID (m_Uuid) is assigned
        automatically by KiCAD. Return this value so data model can be updated with correct KIID value.
        """
        logger.debug(f"Adding new drawing to pcb: {drawing}")
        board_origin = brd.GetDesignSettings().GetAuxOrigin()

        # Create new pcb shape object, add shape to Edge Cuts layer
        new_shape = pcbnew.PCB_SHAPE()
        new_shape.SetLayer(pcbnew.Edge_Cuts)
        new_shape.SetWidth(100000)

        shape = drawing["shape"]
        if "Line" in shape:
            # Add aux board origin to relative coordinates
            start_absolute = [drawing["start"][0] + board_origin[0],
                              drawing["start"][1] + board_origin[1]]
            end_absolute = [drawing["end"][0] + board_origin[0],
                            drawing["end"][1] + board_origin[1]]
            # Convert list to VECTOR2I
            start = kicad_vector(start_absolute)
            end = kicad_vector(end_absolute)
            # Set properties of PCB_SHAPE object
            # KC Bug if using shape.SetStartEnd() method
            # Workaround: set start and end individually
            new_shape.SetStart(start)
            new_shape.SetEnd(end)

        elif "Circle" in shape:
            new_shape.SetShape(pcbnew.SHAPE_T_CIRCLE)
            # Add aux board origin to relative coordinates
            center_absolute = [drawing["center"][0] + board_origin[0],
                               drawing["center"][1] + board_origin[1]]
            radius = drawing["radius"]
            # Calculate circle end point (x is same as center, y is moved down by radius)
            end_point = [
                center_absolute[0],
                center_absolute[1] + radius
            ]
            # Convert to VECTOR2I
            center = kicad_vector(center_absolute)
            end_point = kicad_vector(end_point)
            # Set drawing geometry (end point is the only way to set circle radius)
            new_shape.SetCenter(center)
            new_shape.SetEnd(end_point)

        elif "Arc" in shape:
            logger.debug(f"Drawing a new arc in pcb {drawing}")
            new_shape.SetShape(pcbnew.SHAPE_T_ARC)
            # Add aux origin to relative coordinates.
            #  first index of is point, second index is coordinate (x and y)
            absolute_p1 = [drawing["points"][0][0] + board_origin[0],
                           drawing["points"][0][1] + board_origin[1]]
            absolute_md = [drawing["points"][1][0] + board_origin[0],
                           drawing["points"][1][1] + board_origin[1]]
            absolute_p2 = [drawing["points"][2][0] + board_origin[0],
                           drawing["points"][2][1] + board_origin[1]]
            start = kicad_vector(absolute_p1)
            arc_md = kicad_vector(absolute_md)
            end = kicad_vector(absolute_p2)
            # Set three arc points
            new_shape.SetArcGeometry(start, arc_md, end)

        else:
            logger.exception(f"Invalid new drawing shape: {drawing}")
            return ""

        # Add shape to board object
        brd.Add(new_shape)
        # Get new drawing's id:
        kiid = new_shape.m_Uuid.AsString()

        return kiid
