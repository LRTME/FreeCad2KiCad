"""
Contains PartUpdater class that runs in its own thread.
"""
import FreeCAD as App
import Part
import Sketcher

import hashlib
import logging

from PySide import QtCore

from API_scripts import utils
from API_scripts import part_drawer
from API_scripts.constants import VEC, SCALE
from API_scripts.constraints import constrain_rectangle, coincident_geometry

logger_updater = logging.getLogger("updater")


# noinspection PyAttributeOutsideInit
class FcPartUpdater:
    """
    Updates Part objects in FC from diff dictionary
    :param doc: FreeCAD document object
    :param pcb: dict
    :param diff: dict
    :return:
    """

    def __init__(self, doc, pcb, diff, models_path, progress_bar):
        super().__init__()
        self.doc = doc
        self.pcb = pcb
        self.diff = diff
        self.MODELS_PATH = models_path
        self.progress_bar = progress_bar

    def run(self):
        """ Main method which is called when updater is started. """

        try:
            self.pcb_id = self.pcb["general"]["pcb_id"]
            self.sketch = self.doc.getObject(f"Board_Sketch_{self.pcb_id}")

            if self.diff.get("footprints"):
                self.update_footprints()

            if self.diff.get("drawings"):
                self.update_drawings()

            if self.diff.get("vias"):
                self.update_vias()

            return self.pcb
        except Exception as e:
            logger_updater.exception(e)

    def update_drawings(self):
        """ Separate method to clean up run() method. """
        key = "drawings"
        changed = self.diff[key].get("changed")
        added = self.diff[key].get("added")
        removed = self.diff[key].get("removed")

        # Drawings container
        drawings_part = self.doc.getObject(f"Drawings_{self.pcb_id}")

        # First case is "removed": important when new drawings are added in FC and Diff with valid KIID is received:
        # first delete drawings from sketch with invalid IDs, then add new drawings with valid ID to sketch
        if removed:
            # Set up progress bar
            self.progress_bar.setRange(0, len(removed))
            self.progress_bar.show()
            for i, kiid in enumerate(removed):
                # Increment progress bar
                self.progress_bar.setValue(i)
                self.progress_bar.setFormat("Removing drawings: %p%")
                # Get Part object
                drw_part = utils.get_part_by_kiid(self.doc, kiid)
                # If drw part is None, it means drawing was already deleted in FC by user
                if not drw_part:
                    continue

                geoms_indexes = utils.get_geoms_by_tags(self.sketch, drw_part.Tags)
                # Delete geometry by index
                self.sketch.delGeometries(geoms_indexes)
                # Delete drawing part
                self.doc.removeObject(drw_part.Name)
                # Get old entry in data model
                drawing = utils.get_dict_entry_by_kiid(self.pcb["drawings"], kiid)
                # Remove from dictionary
                self.pcb[key].remove(drawing)

            self.progress_bar.reset()
            self.progress_bar.hide()

        if added:
            # Set up progress bar
            self.progress_bar.setRange(0, len(added))
            self.progress_bar.show()
            for i, drawing in enumerate(added):
                # Increment progress bar
                self.progress_bar.setValue(i)
                self.progress_bar.setFormat("Adding drawings: %p%")
                # Add to document
                part_drawer.add_drawing(doc=self.doc,
                                        pcb=self.pcb,
                                        sketch=self.sketch,
                                        drawing=drawing,
                                        container=drawings_part,
                                        shape=drawing["shape"])
                # Add to dictionary
                self.pcb[key].append(drawing)

            self.progress_bar.reset()
            self.progress_bar.hide()

            # Add coincident constraints to all new geometries (function checks if geometries should be constrained)
            try:
                sketch_geometries = self.sketch.Geometry
                # Index geometries of sketch: newly added geometries are appended to the of the array. Index slice
                # from minus length of added drawings to end: Geometry[-n:]
                geometry_list_slice = sketch_geometries[-len(added):]
                # This is used to account for function not constraining all geometries but only last n
                # (list is enumerated in function, so number of ignored geometries must be added to index)
                index_offset = len(sketch_geometries) - len(added)
                # Add coincident constraint
                coincident_geometry(self.sketch, geometry=geometry_list_slice, index_offset=index_offset)

                # If there are 4 geometries, and all are lines, try to rectangle constrain
                only_lines = True
                for drawing in added:
                    if drawing.get("shape") != "Line":
                        only_lines = False
                # Build a list of tags for naming constraints
                tags = [geom.Tag for geom in geometry_list_slice]
                # Add horizontal and vertical constraints
                if len(added) == 4 and only_lines:
                    # Second argument is list of indexes
                    constrain_rectangle(self.sketch, [i + index_offset for i in range(4)], tags)

            except ValueError:
                # ERROR - Duplicate constraints not allowed
                pass

        if changed:
            # Set up progress bar
            self.progress_bar.setRange(0, len(changed))
            self.progress_bar.show()
            for i, entry in enumerate(changed):
                # Increment progress bar
                self.progress_bar.setValue(i)
                self.progress_bar.setFormat("Updating drawings: %p%")
                # Parse entry in dictionary to get kiid and changed values:
                # Get dictionary items as 1 tuple
                items = [(x, y) for x, y in entry.items()]
                # First index to get tuple inside list  items = [(x,y)]
                # Second index to get values in tuple
                kiid = items[0][0]
                # changes is a dictionary where keys are properties
                changes = items[0][1]
                # Part object in FreeCAD document (to be edited)
                drw_part = utils.get_part_by_kiid(self.doc, kiid)
                # Sketch geometries that belong to drawing part object (so that actual sketch can be changed)
                geoms_indexes = utils.get_geoms_by_tags(self.sketch, drw_part.Tags)
                # Old entry in pcb dictionary (to be updated)
                drawing = utils.get_dict_entry_by_kiid(self.pcb["drawings"], kiid)

                # Dictionary of changes consists of:   "name of property": new value of property
                for prop, value in changes.items():
                    # Apply changes based on type of geometry
                    if "Line" in drw_part.Label:
                        new_point = utils.freecad_vector(value)
                        if prop == "start":
                            # Start point has PointPos parameter 1, end has 2
                            self.sketch.movePoint(geoms_indexes[0], 1, new_point)
                        elif prop == "end":
                            self.sketch.movePoint(geoms_indexes[0], 2, new_point)

                    elif "Rect" in drw_part.Label or "Polygon" in drw_part.Label:
                        # Delete existing geometries
                        self.sketch.delGeometries(geoms_indexes)

                        # Add new points to sketch
                        points, tags = [], []
                        for ii, p in enumerate(value):
                            point = utils.freecad_vector(p)
                            if ii != 0:
                                # Create a line from current to previous point
                                self.sketch.addGeometry(Part.LineSegment(point, points[-1]),
                                                        False)
                                tags.append(self.sketch.Geometry[-1].Tag)

                            points.append(point)

                        # Add another line from last to first point
                        self.sketch.addGeometry(Part.LineSegment(points[-1], points[0]), False)
                        tags.append(self.sketch.Geometry[-1].Tag)
                        # Add Tags to Part object after it's added to sketch
                        drw_part.Tags = tags

                    elif "Circle" in drw_part.Label:
                        if prop == "center":
                            center_new = utils.freecad_vector(value)
                            # Move geometry in sketch to new pos
                            # PointPos parameter for circle center is 3 (second argument)
                            self.sketch.movePoint(geoms_indexes[0], 3, center_new)

                        elif prop == "radius":
                            radius = value
                            # Get index of radius constraint
                            constraints = utils.get_constraint_by_tag(self.sketch, drw_part.Tags[0])
                            radius_constraint_index = constraints.get("radius")
                            if not radius_constraint_index:
                                continue
                            # Change radius constraint to new value
                            self.sketch.setDatum(radius_constraint_index,
                                                 App.Units.Quantity(f"{radius / SCALE} mm"))
                            # Save new value to drw Part object
                            drw_part.Radius = radius / SCALE

                    elif "Arc" in drw_part.Label:
                        # Delete existing arc geometry from sketch
                        self.sketch.delGeometries(geoms_indexes)
                        # Get new points, convert them to FC vector
                        p1 = utils.freecad_vector(value[0])  # Start
                        md = utils.freecad_vector(value[1])  # Arc middle
                        p2 = utils.freecad_vector(value[2])  # End
                        # Create a new arc (3 points)
                        arc = Part.ArcOfCircle(p1, md, p2)
                        # Add arc to sketch
                        self.sketch.addGeometry(arc, False)
                        # Add Tag after its added to sketch
                        drw_part.Tags = self.sketch.Geometry[-1].Tag

                    # Update data model
                    drawing.update({prop: value})

                # Remove existing hash from data, so it doesn't affect new hash calculation
                drawing.update({"hash": ""})
                # Hash itself when all changes applied
                drawing_hash = hashlib.md5(str(drawing).encode()).hexdigest()
                drawing.update({"hash": drawing_hash})

            self.progress_bar.reset()
            self.progress_bar.hide()

    def update_footprints(self):
        """ Separate method to clean up run() method. """
        key = "footprints"
        changed = self.diff[key].get("changed")
        added = self.diff[key].get("added")
        removed = self.diff[key].get("removed")

        if added:
            # Set up progress bar
            self.progress_bar.setRange(0, len(added))
            self.progress_bar.show()
            for i, footprint in enumerate(added):
                # Update progress bar
                self.progress_bar.setValue(i)
                self.progress_bar.setFormat("Adding footprints: %p%")
                # Add to document
                part_drawer.add_footprint(doc=self.doc,
                                          pcb=self.pcb,
                                          footprint=footprint,
                                          sketch=self.sketch,
                                          models_path=self.MODELS_PATH)
                # Add to dictionary
                self.pcb[key].append(footprint)

            self.progress_bar.reset()
            self.progress_bar.hide()

        if removed:
            # Set up progress bar
            self.progress_bar.setRange(0, len(removed))
            self.progress_bar.show()
            for i, kiid in enumerate(removed):
                # Increment progress bar
                self.progress_bar.setValue(i)
                self.progress_bar.setFormat("Adding footprints: %p%")
                footprint = utils.get_dict_entry_by_kiid(self.pcb["footprints"], kiid)
                fp_part = utils.get_part_by_kiid(self.doc, kiid)

                # Remove through holes from sketch
                geom_indexes = []
                for child in fp_part.Group:
                    # Find Pads container of footprints container
                    if "Pads" in child.Label:
                        for pad_part in child.Group:
                            # Get index of geometry and add it to list
                            geom_indexes.append(utils.get_geoms_by_tags(self.sketch, pad_part.Tags)[0])

                # Delete pad holes from sketch
                self.sketch.delGeometries(geom_indexes)
                # Delete FP Part container
                self.doc.getObject(fp_part.Name).removeObjectsFromDocument()
                self.doc.removeObject(fp_part.Name)
                self.doc.recompute()
                # Remove from dictionary
                self.pcb[key].remove(footprint)

            self.progress_bar.reset()
            self.progress_bar.hide()

        if changed:
            # Set up progress bar
            self.progress_bar.setRange(0, len(changed))
            self.progress_bar.show()
            for i, entry in enumerate(changed):
                # Increment progress bar
                self.progress_bar.setValue(i)
                self.progress_bar.setFormat("Updating footprints: %p%")

                # Get dictionary items as 1 tuple
                items = [(x, y) for x, y in entry.items()]
                # First index to get tuple inside list  items = [(x,y)]
                # Second index to get values in tuple
                kiid = items[0][0]
                # changes is a dictionary where keys are properties
                changes = items[0][1]
                footprint = utils.get_dict_entry_by_kiid(self.pcb["footprints"], kiid)
                fp_part = utils.get_part_by_kiid(self.doc, kiid)

                # Dictionary of changes consists of:   "name of property": new value of property
                for prop, value in changes.items():
                    # Apply changes based on property
                    if prop == "ref":
                        fp_part.Reference = value
                        # Change label since reference is part of the part label
                        fp_part.Label = f"{footprint['ID']}_{footprint['ref']}_{self.pcb_id}"

                    elif prop == "pos":
                        # logger_updater.info(f"Changing position of {footprint}")
                        # Move footprint to new position
                        base = utils.freecad_vector(value)
                        fp_part.Placement.Base = base

                        # Move holes in sketch to new position
                        if footprint.get("pads_pth") and self.sketch:
                            # logger_updater.debug(f"Moving pads is sketch of footprint {footprint}")
                            # Group[0] is pad_part container of footprint part
                            for pad_part in fp_part.Group[0].Group:
                                # Get delta from feature obj
                                delta = App.Vector(pad_part.PosDelta[0],
                                                   pad_part.PosDelta[1],
                                                   pad_part.PosDelta[2])
                                # Get index of sketch geometry by Tag to move point
                                geom_index = utils.get_geoms_by_tags(self.sketch, pad_part.Tags)[0]
                                # Move point to new footprint pos
                                # (account for previous pad delta)
                                self.sketch.movePoint(geom_index, 3, base + delta)

                    elif prop == "rot":
                        # Rotate footprint (take in account existing rotation)
                        fp_part.Placement.rotate(VEC["0"],
                                                 VEC["z"],
                                                 value - footprint["rot"])

                    elif prop == "layer":
                        # Remove from parent
                        parent = fp_part.Parents[0][1].split(".")[1]
                        self.doc.getObject(parent).removeObject(fp_part)
                        # Add to new layer
                        new_layer = f"{value}_{self.pcb_id}"
                        self.doc.getObject(new_layer).addObject(fp_part)

                        # Top -> Bottom
                        # rotate model 180 around x and move in -z by pcb thickness
                        if value == "Bot":
                            for feature in fp_part.Group:
                                if "Pads" in feature.Label:
                                    continue
                                # If footprint is on bottom layer move in -z by pcb thickness
                                feature.Placement.Base.z = - feature.Placement.Base.z - (
                                            self.pcb.get("general").get("thickness") / SCALE)
                                # Rotate bottom layer footprint model by 180 degrees - taken from KiCAD StepUp Mod
                                shape = feature.Shape.copy()
                                shape.rotate((0, 0, 0), (1, 0, 0), 180)
                                feature.Placement.Rotation = shape.Placement.Rotation

                        # Bottom -> Top
                        if value == "Top":
                            for feature in fp_part.Group:
                                if "Pads" in feature.Label:
                                    continue
                                # Rotate model by 180 degrees - taken from KiCAD StepUp Mod
                                shape = feature.Shape.copy()
                                shape.rotate((0, 0, 0), (1, 0, 0), -180)
                                feature.Placement.Rotation = shape.Placement.Rotation
                                # If footprint is on top layer move in +z by pcb thickness
                                feature.Placement.Base.z = + feature.Placement.Base.z + (
                                        self.pcb.get("general").get("thickness") / SCALE)

                    elif prop == "pads_pth" and self.sketch:
                        # Go through list if dictionaries ( "kiid": [*list of changes*])
                        for val in value:
                            for kiid, changes in val.items():

                                pad_part = utils.get_part_by_kiid(self.doc, kiid)

                                # Go through changes ["property", *new_value*]
                                for change in changes:
                                    prop, value = change[0], change[1]

                                    if prop == "pos_delta":
                                        dx = value[0]
                                        dy = value[1]
                                        # Change constraint:
                                        distance_constraints = utils.get_constraint_by_tag(self.sketch,
                                                                                           pad_part.Tags[0])
                                        x_constraint = distance_constraints.get("dist_x")
                                        y_constraint = distance_constraints.get("dist_y")
                                        if not x_constraint and y_constraint:
                                            continue
                                        # Change distance constraint to new value
                                        self.sketch.setDatum(x_constraint, App.Units.Quantity(f"{dx / SCALE} mm"))
                                        self.sketch.setDatum(y_constraint, App.Units.Quantity(f"{-dy / SCALE} mm"))

                                        # Find geometry in sketch with same Tag
                                        geom_index = utils.get_geoms_by_tags(self.sketch, pad_part.Tags)[0]
                                        # Get footprint position
                                        base = fp_part.Placement.Base
                                        delta = utils.freecad_vector(value)
                                        # Move pad for fp bas and new delta
                                        self.sketch.movePoint(geom_index, 3, base + delta)
                                        # Save new delta to pad object
                                        pad_part.PosDelta = delta

                                        # Update dictionary
                                        for pad in footprint["pads_pth"]:
                                            if pad["kiid"] != kiid:
                                                continue
                                            # Update dictionary entry with same KIID
                                            pad.update({"pos_delta": value})

                                    elif prop == "hole_size":
                                        maj_axis = value[0]
                                        # min_axis = value[1]
                                        # Get index of radius constraint in sketch (of pad)
                                        constraints = utils.get_constraint_by_tag(self.sketch, pad_part.Tags[0])
                                        radius_constraint_index = constraints.get("radius")
                                        if not radius_constraint_index:
                                            continue
                                        radius = (maj_axis / 2) / SCALE
                                        # Change radius constraint to new value
                                        self.sketch.setDatum(radius_constraint_index,
                                                             App.Units.Quantity(f"{radius} mm"))
                                        # Save new value to pad object
                                        pad_part.Radius = radius

                                        # Update dictionary
                                        for pad in footprint["pads_pth"]:
                                            if pad["kiid"] != kiid:
                                                continue
                                            pad.update({"hole_size": value})

                    elif prop == "3d_models":
                        # Remove all existing step models from FP container
                        for feature in fp_part.Group:
                            if "Pads" in feature.Label:
                                continue
                            logger_updater.debug(f"Removing feature {feature.Name}")
                            self.doc.removeObject(feature.Name)
                        # Re-import footprint step models to FP container
                        for model in value:
                            logger_updater.debug(f"model")
                            # Import model - call function
                            part_drawer.import_model(doc=self.doc,
                                                     pcb=self.pcb,
                                                     model=model,
                                                     fp=footprint,
                                                     fp_part=fp_part,
                                                     models_path=self.MODELS_PATH)

                    # Update data model
                    footprint.update({prop: value})

                # Remove existing hash from data, so it doesn't affect new hash calculation
                footprint.update({"hash": ""})
                # Hash itself when all changes applied
                footprint_hash = hashlib.md5(str(footprint).encode()).hexdigest()
                footprint.update({"hash": footprint_hash})

            self.progress_bar.reset()
            self.progress_bar.hide()

    def update_vias(self):
        """ Separate function to clean up run() method. """
        key = "vias"
        changed = self.diff[key].get("changed")
        added = self.diff[key].get("added")
        removed = self.diff[key].get("removed")

        vias_part = self.doc.getObject(f"Vias_{self.pcb_id}")

        if added:
            for via in added:
                # Add vias to sketch and container
                addDrawing(drawing=via,
                           container=vias_part)
                # Add to dictionary
                pcb[key].append(via)

        if removed:
            for kiid in removed:
                via = utils.get_dict_entry_by_kiid(pcb["vias"], kiid)
                via_part = utils.get_part_by_kiid(self.doc, kiid)
                geom_indexes = utils.get_geoms_by_tags(self.sketch, via_part.Tags)

                # Delete geometry by index
                self.sketch.delGeometries(geom_indexes)
                # Delete via part
                self.doc.removeObject(via_part.Name)
                self.doc.recompute()
                # Remove from dictionary
                self.pcb[key].remove(via)

        if changed:
            for entry in changed:
                # Get dictionary items as 1 tuple
                items = [(x, y) for x, y in entry.items()]
                # First index to get tuple inside list  items = [(x,y)]
                # Second index to get values in tuple
                kiid = items[0][0]
                # changes is a dictionary where keys are properties
                changes = items[0][1]
                via = utils.get_dict_entry_by_kiid(pcb["vias"], kiid)
                via_part = utils.get_part_by_kiid(self.doc, kiid)
                geom_indexes = utils.get_geoms_by_tags(self.sketch, via_part.Tags)

                # Go through list of all changes
                # Dictionary of changes consists of:   "name of property": new value of property
                for prop, value in changes.items():

                    if prop == "center":
                        center_new = utils.freecad_vector(value)
                        # Move geometry in sketch new pos
                        # PointPos parameter for circle center is 3 (second argument)
                        self.sketch.movePoint(geom_indexes[0], 3, center_new)
                        # Update pcb dictionary with new values
                        via.update({"center": value})

                    elif prop == "radius":
                        radius = value
                        # Change radius constraint to new value
                        # first parameter is index of constraint (stored as Part property)
                        self.sketch.setDatum(via_part.ConstraintRadius, App.Units.Quantity(f"{radius / SCALE} mm"))
                        # Save new value to via Part object
                        via_part.Radius = radius / SCALE
                        # Update pcb dictionary with new value
                        via.update({"radius": radius})
