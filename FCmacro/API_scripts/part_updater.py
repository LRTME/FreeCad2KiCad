import logging

import FreeCAD as App
import Part

from PySide import QtCore

from API_scripts.constants import VEC
from API_scripts.utils import *

# TODO logger
logger_updater = logging.getLogger("updater")


class FcPartUpdater(QtCore.QObject):
    """
    Updates Part objects in FC from diff dictionary
    :param doc: FreeCAD document object
    :param pcb: dict
    :param diff: dict
    :return:
    """

    progress = QtCore.Signal(str)
    finished = QtCore.Signal(dict)

    def __init__(self, doc, pcb, diff):
        super().__init__()
        self.doc = doc
        self.pcb = pcb
        self.diff = diff

    def run(self):

        self.progress.emit("Started updating part")
        logger_updater.debug("Started updater")

        self.pcb_id = self.pcb["general"]["pcb_id"]
        self.sketch = self.doc.getObject(f"Board_Sketch_{self.pcb_id}")

        if self.diff.get("footprints"):
            self.progress.emit("Updating footprints")
            self.updateFootprints()

        if self.diff.get("drawings"):
            self.progress.emit("Updating drawings")
            self.updateDrawings()

        if self.diff.get("vias"):
            self.progress.emit("Updating vias")
            self.updateVias()

        # # Add new PCB dictionary as Property of pcb_Part
        # pcb_name = pcb["general"]["pcb_name"]
        # pcb_part = doc.getObject(f"{pcb_name}_{pcb_id}")
        # pcb_part.JSON = str(pcb)

        self.progress.emit("Recomputing document")
        self.doc.recompute()
        self.finished.emit(self.pcb)

    def updateFootprints(self):

        key = "footprints"
        changed = self.diff[key].get("changed")
        added = self.diff[key].get("added")
        removed = self.diff[key].get("removed")

        if added:
            for footprint in added:
                # Add to document
                self.addFootprintPart(footprint)
                # Add to dictionary
                self.pcb["footprints"].append(footprint)

        if removed:
            for kiid in removed:

                footprint = getDictEntryByKIID(self.pcb["footprints"], kiid)
                fp_part = getPartByKIID(self.doc, kiid)

                # Remove through holes from sketch
                geom_indexes = []
                for child in fp_part.Group:
                    # Find Pads container of footprints container
                    if "Pads" in child.Label:
                        for pad_part in child.Group:
                            # Get index of geometry and add it to list
                            geom_indexes.append(getGeomsByTags(self.sketch, pad_part.Tags)[0])

                # Delete pad holes from sketch
                self.sketch.delGeometries(geom_indexes)
                # Delete FP Part container
                self.doc.getObject(fp_part.Name).removeObjectsFromDocument()
                self.doc.removeObject(fp_part.Name)
                self.doc.recompute()
                # Remove from dictionary
                self.pcb[key].remove(footprint)

        if changed:
            for entry in changed:
                # Get dictionary items as 1 tuple
                items = [(x, y) for x, y in entry.items()]
                # First index to get tuple inside list  items = [(x,y)]
                # Second index to get values in tuple
                kiid = items[0][0]
                changes = items[0][1]

                footprint = getDictEntryByKIID(self.pcb["footprints"], kiid)
                fp_part = getPartByKIID(self.doc, kiid)

                for c in changes:
                    prop, value = c[0], c[1]
                    # Apply changes based on property
                    if prop == "ref":
                        fp_part.Reference = value
                        footprint.update({"ref": value})
                        fp_part.Label = f"{footprint['ID']}_{footprint['ref']}_{self.pcb_id}"

                    elif prop == "pos":
                        # Move footprint to new position
                        base = FreeCADVector(value)
                        fp_part.Placement.Base = base
                        footprint.update({"pos": value})

                        # PAD HOLE FUNCTIONALITY COMMENTED OUT
                        # # Move holes in sketch to new position
                        # if footprint["pads_pth"] and self.sketch:
                        #     # Group[0] is pad_part container of footprint part
                        #     for pad_part in fp_part.Group[0].Group:
                        #         # Get delta from feature obj
                        #         delta = App.Vector(pad_part.PosDelta[0],
                        #                            pad_part.PosDelta[1],
                        #                            pad_part.PosDelta[2])
                        #         # Get index of sketch geometry by Tag to move point
                        #         geom_index = getGeomsByTags(self.sketch, pad_part.Tags)[0]
                        #         # Move point to new footprint pos
                        #         # (account for previous pad delta)
                        #         self.sketch.movePoint(geom_index, 3, base + delta)

                    elif prop == "rot":
                        fp_part.Placement.rotate(VEC["0"],
                                                 VEC["z"],
                                                 value - footprint["rot"])
                        footprint.update({"rot": value})

                    elif prop == "layer":
                        # Remove from parent
                        parent = fp_part.Parents[0][1].split(".")[1]
                        self.doc.getObject(parent).removeObject(fp_part)
                        # Add to new layer
                        new_layer = f"{value}_{self.pcb_id}"
                        self.doc.getObject(new_layer).addObject(fp_part)
                        # Update dictionary
                        footprint.update({"layer": value})

                        # Top -> Bottom
                        # rotate model 180 around x and move in -z by pcb thickness
                        if value == "Bot":
                            for feature in fp_part.Group:
                                if "Pads" in feature.Label:
                                    continue
                                feature.Placement.Rotation = App.Rotation(VEC["x"], 180.00)
                                feature.Placement.Base.z = -(self.pcb["general"]["thickness"] / SCALE)
                        # Bottom -> Top
                        if value == "Top":
                            for feature in fp_part.Group:
                                if "Pads" in feature.Label:
                                    continue
                                feature.Placement.Rotation = App.Rotation(VEC["x"], 0.0)
                                feature.Placement.Base.z = 0

                    # # PAD HOLE FUNCTIONALITY COMMENTED OUT
                    # elif prop == "pads_pth" and self.sketch:
                    #     # Go through list if dictionaries ( "kiid": [*list of changes*])
                    #     for val in value:
                    #         for kiid, changes in val.items():
                    #
                    #             pad_part = getPartByKIID(self.doc, kiid)
                    #
                    #             # Go through changes ["property", *new_value*]
                    #             for change in changes:
                    #                 prop, value = change[0], change[1]
                    #
                    #                 if prop == "pos_delta":
                    #                     dx = value[0]
                    #                     dy = value[1]
                    #                     # Change constraint:
                    #                     distance_constraints = getConstraintByTag(self.sketch, pad_part.Tags[0])
                    #                     x_constraint = distance_constraints.get("dist_x")
                    #                     y_constraint = distance_constraints.get("dist_y")
                    #                     if not x_constraint and y_constraint:
                    #                         continue
                    #                     # Change distance constraint to new value
                    #                     self.sketch.setDatum(x_constraint, App.Units.Quantity(f"{dx / SCALE} mm"))
                    #                     self.sketch.setDatum(y_constraint, App.Units.Quantity(f"{-dy / SCALE} mm"))
                    #
                    #                     # Find geometry in sketch with same Tag
                    #                     geom_index = getGeomsByTags(self.sketch, pad_part.Tags)[0]
                    #                     # Get footprint position
                    #                     base = fp_part.Placement.Base
                    #                     delta = FreeCADVector(value)
                    #                     # Move pad for fp bas and new delta
                    #                     self.sketch.movePoint(geom_index, 3, base + delta)
                    #                     # Save new delta to pad object
                    #                     pad_part.PosDelta = delta
                    #
                    #                     # Update dictionary
                    #                     for pad in footprint["pads_pth"]:
                    #                         if pad["kiid"] != kiid:
                    #                             continue
                    #                         # Update dictionary entry with same KIID
                    #                         pad.update({"pos_delta": value})
                    #
                    #                 elif prop == "hole_size":
                    #                     maj_axis = value[0]
                    #                     min_axis = value[1]
                    #                     # Get index of radius contraint in sketch (of pad)
                    #                     constraints = getConstraintByTag(self.sketch, pad_part.Tags[0])
                    #                     radius_constraint_index = constraints.get("radius")
                    #                     if not radius_constraint_index:
                    #                         continue
                    #                     radius = (maj_axis / 2) / SCALE
                    #                     # Change radius constraint to new value
                    #                     self.sketch.setDatum(radius_constraint_index,
                    #                                          App.Units.Quantity(f"{radius} mm"))
                    #                     # Save new value to pad object
                    #                     pad_part.Radius = radius
                    #
                    #                     # Update dictionary
                    #                     for pad in footprint["pads_pth"]:
                    #                         if pad["kiid"] != kiid:
                    #                             continue
                    #                         pad.update({"hole_size": value})

                    elif prop == "3d_models":
                        # Remove all existing step models from FP container
                        for feature in fp_part.Group:
                            if "Pads" in feature.Label:
                                continue
                            self.doc.removeObject(feature.Name)

                        # Re-import footprint step models to FP container
                        for model in value:
                            self.importModel(model, footprint, fp_part)
                        # Update dictionary
                        footprint.update({"3d_models": value})

    def updateDrawings(self):

        key = "drawings"
        changed = self.diff[key].get("changed")
        added = self.diff[key].get("added")
        removed = self.diff[key].get("removed")

        drawings_part = self.doc.getObject(f"Drawings_{self.pcb_id}")

        if added:
            for drawing in added:
                # Add to document
                self.addDrawing(drawing=drawing,
                                container=drawings_part,
                                shape=drawing["shape"])
                # Add to dictionary
                self.pcb[key].append(drawing)

        if removed:
            for kiid in removed:
                drawing = getDictEntryByKIID(self.pcb["drawings"], kiid)
                drw_part = getPartByKIID(self.doc, kiid)
                geoms_indexes = getGeomsByTags(self.sketch, drw_part.Tags)

                # Delete geometry by index
                sketch.delGeometries(geoms_indexes)
                # Delete drawing part
                self.doc.removeObject(drw_part.Name)
                self.doc.recompute()
                # Remove from dictionary
                self.pcb[key].remove(drawing)

        if changed:
            for entry in changed:
                # Get dictionary items as 1 tuple
                items = [(x, y) for x, y in entry.items()]
                # First index to get tuple inside list  items = [(x,y)]
                # Second index to get values in tuple
                kiid = items[0][0]
                changes = items[0][1]

                drawing = getDictEntryByKIID(self.pcb["drawings"], kiid)
                drw_part = getPartByKIID(self.doc, kiid)
                geoms_indexes = getGeomsByTags(self.sketch, drw_part.Tags)

                for c in changes:
                    prop, value = c[0], c[1]
                    # Apply changes based on type of geometry

                    if "Line" in drw_part.Label:
                        new_point = FreeCADVector(value)
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
                        for i, p in enumerate(value):
                            point = FreeCADVector(p)
                            if i != 0:
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


                    elif "Arc" in drw_part.Label:
                        # Delete existing arc geometry from sketch
                        self.sketch.delGeometries(geoms_indexes)
                        # Get new points, convert them to FC vector
                        p1 = FreeCADVector(value[0])  # Start
                        md = FreeCADVector(value[1])  # Arc middle
                        p2 = FreeCADVector(value[2])  # End
                        # Create a new arc (3 points)
                        arc = Part.ArcOfCircle(p1, md, p2)
                        # Add arc to sketch
                        self.sketch.addGeometry(arc, False)
                        # Add Tag after its added to sketch
                        drw_part.Tags = self.sketch.Geometry[-1].Tag


                    elif "Circle" in drw_part.Label:
                        if prop == "center":
                            center_new = FreeCADVector(value)
                            # Move geometry in sketch to new pos
                            # PointPos parameter for circle center is 3 (second argument)
                            self.sketch.movePoint(geoms_indexes[0], 3, center_new)
                            # Update pcb dictionary with new values
                            drawing.update({"center": value})

                        elif prop == "radius":
                            radius = value
                            # Get index of radius constrint
                            constraints = getConstraintByTag(self.sketch, drw_part.Tags[0])
                            radius_constraint_index = constraints.get("radius")
                            if not radius_constraint_index:
                                continue
                            # Change radius constraint to new value
                            self.sketch.setDatum(radius_constraint_index,
                                                 App.Units.Quantity(f"{radius / SCALE} mm"))
                            # Save new value to drw Part object
                            drw_part.Radius = radius / SCALE
                            # Update pcb dictionary with new value
                            drawing.update({"radius": radius})


    def updateVias(self):

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
                via = getDictEntryByKIID(pcb["vias"], kiid)
                via_part = getPartByKIID(self.doc, kiid)
                geom_indexes = getGeomsByTags(self.sketch, via_part.Tags)

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
                changes = items[0][1]

                via = getDictEntryByKIID(pcb["vias"], kiid)
                via_part = getPartByKIID(self.doc, kiid)
                geom_indexes = getGeomsByTags(self.sketch, via_part.Tags)

                # Go through list of all changes
                # list of changes consists of:  [ [name of property, new value of property] ,..]
                for c in changes:
                    prop, value = c[0], c[1]

                    if prop == "center":
                        center_new = FreeCADVector(value)
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

    def addDrawing(self, drawing, container, shape="Circle"):
        # Default shape is "Circle" because saame function is called when drawing Vias
        # (Via has no property shape, defaults to circle)
        """
        Add a geometry to board sketch
        Add an object with geometry properies to Part container (Drawings of Vias)
        :param drawing: pcb dictionary entry
        :param container: FreeCAD Part object
        :param shape: string (Circle, Rect, Polygon, Line, Arc)
        :return:
        """

        # Create an object to store Tag
        obj = self.doc.addObject("Part::Feature", f"{shape}_{self.pcb_id}")
        obj.Label = f"{drawing['ID']}_{shape}_{self.pcb_id}"
        # Tag property to store geometry sketch ID (Tag) used for editing sketch geometry
        obj.addProperty("App::PropertyStringList", "Tags", "Sketch")
        # Add KiCAD ID string (UUID)
        obj.addProperty("App::PropertyString", "KIID", "KiCAD")
        obj.KIID = drawing["kiid"]
        # Hide object and add it to container
        obj.Visibility = False
        container.addObject(obj)

        if ("Rect" in shape) or ("Polygon" in shape):
            points, tags, geom_indexes = [], [], []
            for i, p in enumerate(drawing["points"]):
                point = FreeCADVector(p)
                # If not first point
                if i != 0:
                    # Create a line from current to previous point
                    self.sketch.addGeometry(Part.LineSegment(point, points[-1]), False)
                    tags.append(self.sketch.Geometry[-1].Tag)
                    geom_indexes.append(self.sketch.GeometryCount - 1)

                points.append(point)

            # Add another line from last to first point
            self.sketch.addGeometry(Part.LineSegment(points[0], points[-1]), False)
            tags.append(self.sketch.Geometry[-1].Tag)
            geom_indexes.append(self.sketch.GeometryCount - 1)
            # Add Tags after geometries are added to sketch
            obj.Tags = tags
            # Add horizontal/ vertical and perpendicular constraints if shape is rectangle
            if "Rect" in shape:
                constrainRectangle(self.sketch, geom_indexes, tags)

        elif "Line" in shape:
            start = FreeCADVector(drawing["start"])
            end = FreeCADVector(drawing["end"])
            line = Part.LineSegment(start, end)
            # Add line to sketch
            self.sketch.addGeometry(line, False)
            # Add Tag after its added to sketch
            obj.Tags = self.sketch.Geometry[-1].Tag

        elif "Arc" in shape:
            p1 = FreeCADVector(drawing["points"][0])
            p2 = FreeCADVector(drawing["points"][1])
            p3 = FreeCADVector(drawing["points"][2])
            arc = Part.ArcOfCircle(p1, p2, p3)
            # Add arc to sketch
            self.sketch.addGeometry(arc, False)
            # Add Tag after its added to sketch
            obj.Tags = self.sketch.Geometry[-1].Tag

        elif "Circle" in shape:
            radius = drawing["radius"] / SCALE
            center = FreeCADVector(drawing["center"])
            circle = Part.Circle(Center=center,
                                 Normal=VEC["z"],
                                 Radius=radius)
            # Add circle to sketch
            self.sketch.addGeometry(circle, False)
            # Save tag of geometry
            tag = self.sketch.Geometry[-1].Tag
            # Add constraint to sketch
            self.sketch.addConstraint(Sketcher.Constraint('Radius',
                                                          (self.sketch.GeometryCount - 1),
                                                          radius))
            self.sketch.renameConstraint(self.sketch.ConstraintCount - 1,
                                         f"circleradius_{tag}")

            # Add Tag after its added to sketch
            obj.Tags = tag
            obj.addProperty("App::PropertyFloat", "Radius")
            obj.Radius = radius
            # Save constraint index (used for modifying hole size when applying diff)
            obj.addProperty("App::PropertyInteger", "ConstraintRadius", "Sketch")
            obj.ConstraintRadius = self.sketch.ConstraintCount - 1

    def addFootprintPart(self, footprint):
        """
        Adds footprint container to "Top" or "Bot" Group of "Footprints"
        Imports Step models as childer
        Add "Pads" container with through hole pads - add holes to sketch as circles
        :param footprint: footprint dictionary
        """

        # Crate a part object for each footprint
        # naming: " kiid_ref_id "  so there is no auto-self-naming duplicates
        fp_part = self.doc.addObject("App::Part", f"{footprint['ID']}_{footprint['ref']}_{self.pcb_id}")
        fp_part.Label = f"{footprint['ID']}_{footprint['ref']}_{self.pcb_id}"
        # Add property reference, which is same as label
        fp_part.addProperty("App::PropertyString", "Reference", "KiCAD")
        fp_part.Reference = footprint["ref"]
        # Add flag (consecutive number)
        fp_part.addProperty("App::PropertyInteger", "Flag", "KiCAD")
        fp_part.Flag = footprint["ID"]
        # Add KiCAD ID string (Path)
        fp_part.addProperty("App::PropertyString", "KIID", "KiCAD")
        fp_part.KIID = footprint["kiid"]

        # Add to layer part
        if footprint["layer"] == "Top":
            self.doc.getObject(f"Top_{self.pcb_id}").addObject(fp_part)
        else:
            self.doc.getObject(f"Bot_{self.pcb_id}").addObject(fp_part)

        # Footprint placement
        base = FreeCADVector(footprint["pos"])
        fp_part.Placement.Base = base
        # Footprint rotation around z axis
        fp_part.Placement.rotate(VEC["0"], VEC["z"], footprint["rot"])

        self.progress.emit("Adding pads")

        # Check if footprint has through hole pads
        if footprint.get("pads_pth"):
            pads_part = self.doc.addObject("App::Part", f"Pads_{fp_part.Label}")
            pads_part.Visibility = False
            fp_part.addObject(pads_part)

            constraints = []
            for i, pad in enumerate(footprint["pads_pth"]):
                # Call function to add pad -> returns FC object and index of geom in sketch
                pad_part, index = self.addPad(pad=pad,
                                              footprint=footprint,
                                              fp_part=fp_part,
                                              container=pads_part)
                # save pad and index to list for constraining pads
                constraints.append((pad_part, index))

            # Add constraints to pads:
            constrainPadDelta(self.sketch, constraints)

        self.progress.emit("Importing models")

        # Check footprint for 3D models
        if footprint.get("3d_models"):
            for model in footprint["3d_models"]:
                # Import model - call function
                self.importModel(model, footprint, fp_part)

    def addPad(self, pad, footprint, fp_part, container):
        """
        Add circle geometry to sketch, create a Pad Part object and add it to footprints pad container.
        :param pad: pcb dictionary entry (pad data)
        :param footprint: pcb dictionary entry  (footprint data)
        :param fp_part: footprint Part object
        :param container: FreeCAD Part object
        :return: Pad Part object, sketch geometry index of pad
        """

        base = fp_part.Placement.Base

        maj_axis = pad["hole_size"][0] / SCALE
        radius = maj_axis / 2
        min_axis = pad["hole_size"][1] / SCALE
        pos_delta = FreeCADVector(pad["pos_delta"])
        circle = Part.Circle(Center=base + pos_delta,
                             Normal=VEC["z"],
                             Radius=radius)

        # Add ellipse to sketch
        self.sketch.addGeometry(circle, False)
        tag = self.sketch.Geometry[-1].Tag

        # TODO this is probably not needed
        # Add radius constraint
        self.sketch.addConstraint(Sketcher.Constraint("Radius",  # Type
                                                      (self.sketch.GeometryCount - 1),  # Index of geometry
                                                      radius))  # Value (radius)
        self.sketch.renameConstraint(self.sketch.ConstraintCount - 1,
                                     f"padradius_{tag}")

        # Create an object to store Tag and Delta
        obj = self.doc.addObject("Part::Feature", f"{footprint['ref']}_{pad['ID']}_{self.pcb_id}")
        obj.Shape = circle.toShape()
        # Store abosolute position of pad (used for comparing to sketch geometry position)
        obj.Placement.Base = base + pos_delta
        # Add properties to object:
        # Tag property to store geometry sketch ID (Tag) used for editing sketch geometry
        obj.addProperty("App::PropertyStringList", "Tags", "Sketch")
        # Add Tag after its added to sketch!
        obj.Tags = tag
        # Store position delta, which is used when moving geometry in sketch (apply diff)
        obj.addProperty("App::PropertyVector", "PosDelta")
        obj.PosDelta = pos_delta
        # Save radius of circle
        obj.addProperty("App::PropertyFloat", "Radius")
        obj.Radius = radius
        # Save constraint index (used for modifying hole size when applying diff)
        obj.addProperty("App::PropertyInteger", "ConstraintRadius", "Sketch")
        obj.ConstraintRadius = self.sketch.ConstraintCount - 1
        # Add KIID as property
        obj.addProperty("App::PropertyString", "KIID", "KiCAD")
        obj.KIID = pad["kiid"]
        # Hide pad object and add it to pad Part container
        obj.Visibility = False
        container.addObject(obj)

        return obj, self.sketch.GeometryCount - 1

    def importModel(self, model, fp, fp_part):
        """
        Import .step models to document as children of footprint Part container
        :param model: dictionary with model properties
        :param fp: footprint dictionary
        :param fp_part: FreeCAD App::Part object
        """

        # Import model
        path = self.MODELS_PATH + model["filename"] + ".step"
        ImportGui.insert(path, self.doc.Name)

        # Last obj in doc is imported model
        feature = self.doc.Objects[-1]
        # Set label
        feature.Label = f"{fp['ID']}_{fp['ref']}_{model['model_id']}_{self.pcb_id}"
        feature.addProperty("App::PropertyString", "Filename", "KiCAD")
        feature.Filename = model["filename"].split("/")[-1]
        feature.addProperty("App::PropertyBool", "Model", "Base")
        feature.Model = True

        # Model is child of fp - inherits base coordinates, only offset necessary
        # Offset unit is mm, y is not flipped:
        offset = App.Vector(model["offset"][0],
                            model["offset"][1],
                            model["offset"][2])
        feature.Placement.Base = offset

        # Check if model needs to be rotated
        if model["rot"] != [0.0, 0.0, 0.0]:
            feature.Placement.rotate(VEC["0"], VEC["x"], -model["rot"][0])
            feature.Placement.rotate(VEC["0"], VEC["y"], -model["rot"][1])
            feature.Placement.rotate(VEC["0"], VEC["z"], -model["rot"][2])

        # If footprint is on bottom layer:
        # rotate model 180 around x and move in -z by pcb thickness
        if fp["layer"] == "Bot":
            feature.Placement.Rotation = App.Rotation(VEC["x"], 180.00)
            feature.Placement.Base.z = -(self.pcb_thickness / SCALE)

        # Scale model if it's not 1x
        if model["scale"] != [1.0, 1.0, 1.0]:
            # Make clone with Draft module in order to scale shape
            clone = Draft.make_clone(feature, delta=offset)
            clone.Scale = App.Vector(model["scale"][0],
                                     model["scale"][1],
                                     model["scale"][2])
            # Rename original: add "_o_"
            feature.Label = f"{fp['ID']}_{fp['ref']}_{model['model_id']}_o_{self.pcb_id}"
            # Add clone name without "_o_"
            clone.Label = f"{fp['ID']}_{fp['ref']}_{model['model_id']}_{self.pcb_id}"
            clone.addProperty("App::PropertyString", "Filename", "Base")
            clone.Filename = model["filename"].split("/")[-1]
            clone.addProperty("App::PropertyBool", "Model", "Base")
            clone.Model = True
            # Hide original
            feature.Visibility = False
            fp_part.addObject(clone)
            # Both feature and clone must be in footprint part containter for clone to work

        fp_part.addObject(feature)