import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher

from utils import *
from constants import SCALE, VEC
from constraints import *


def updateFootprints(doc, pcb, diff, sketch):

    key = "footprints"
    changed = diff[key].get("changed")
    added = diff[key].get("added")
    removed = diff[key].get("removed")


    if added:
        for footprint in added:
            # Add to document
            addFootprintPart(footprint, doc, pcb)
            # Add to dictionary
            pcb["footprints"].append(footprint)

    if removed:
        for kiid in removed:

            footprint = getDictEntryByKIID(pcb["footprints"], kiid)
            fp_part = getPartByKIID(doc, kiid)

            # Remove through holes from sketch
            geom_indexes = []
            for child in fp_part.Group:
                # Find Pads container of footprints container
                if "Pads" in child.Label:
                    for pad_part in child.Group:
                        # Get index of geometry and add it to list
                        geom_indexes.append(getGeomsByTags(sketch, pad_part.Tags)[0])

            # Delete pad holes from sketch
            sketch.delGeometries(geom_indexes)
            # Delete FP Part container
            doc.getObject(fp_part.Name).removeObjectsFromDocument()
            doc.removeObject(fp_part.Name)
            doc.recompute()
            # Remove from dictionary
            pcb[key].remove(footprint)

    if changed:
        for entry in changed:
            # Get dictionary items as 1 tuple
            items = [(x, y) for x, y in entry.items()]
            # First index to get tuple inside list  items = [(x,y)]
            # Second index to get values in tuple
            kiid = items[0][0]
            changes = items[0][1]

            footprint = getDictEntryByKIID(pcb["footprints"], kiid)
            fp_part = getPartByKIID(doc, kiid)

            for c in changes:
                prop, value = c[0], c[1]
                # Apply changes based on property
                if prop == "ref":
                    fp_part.Reference = value
                    footprint.update({"ref": value})
                    fp_part.Label = f"{footprint['ID']}_{footprint['ref']}_{pcb_id}"

                elif prop == "pos":
                    # Move footprint to new position
                    base = App.Vector(value[0] / SCALE,
                                      -value[1] / SCALE,
                                      0)
                    fp_part.Placement.Base = base
                    footprint.update({"pos": value})

                    # Move holes in sketch to new position
                    if footprint["pads_pth"] and sketch:
                        # Group[0] is pad_part container of footprint part
                        for pad_part in fp_part.Group[0].Group:
                            # Get delta from feature obj
                            delta = App.Vector(pad_part.PosDelta[0],
                                               pad_part.PosDelta[1],
                                               pad_part.PosDelta[2])
                            # Get index of sketch geometry by Tag to move point
                            geom_index = getGeomsByTags(sketch, pad_part.Tags)[0]
                            # Move point to new footprint pos
                            # (account for previous pad delta)
                            sketch.movePoint(geom_index, 3, base + delta)

                elif prop == "rot":
                    fp_part.Placement.rotate(VEC["0"],
                                             VEC["z"],
                                             value - footprint["rot"])
                    footprint.update({"rot": value})

                elif prop == "layer":
                    # Remove from parent
                    parent = fp_part.Parents[0][1].split(".")[1]
                    doc.getObject(parent).removeObject(fp_part)
                    # Add to new layer
                    new_layer = f"{value}_{pcb_id}"
                    doc.getObject(new_layer).addObject(fp_part)
                    # Update dictionary
                    footprint.update({"layer": value})

                    # Top -> Bottom
                    # rotate model 180 around x and move in -z by pcb thickness
                    if value == "Bot":
                        for feature in fp_part.Group:
                            if "Pads" in feature.Label:
                                continue
                            feature.Placement.Rotation = App.Rotation(VEC["x"], 180.00)
                            feature.Placement.Base.z = -(pcb["general"]["thickness"] / SCALE)
                    # Bottom -> Top
                    if value == "Top":
                        for feature in fp_part.Group:
                            if "Pads" in feature.Label:
                                continue
                            feature.Placement.Rotation = App.Rotation(VEC["x"], 0.0)
                            feature.Placement.Base.z = 0

                elif prop == "pads_pth" and sketch:
                    # Go through list if dictionaries ( "kiid": [*list of changes*])
                    for val in value:
                        for kiid, changes in val.items():

                            pad_part = getPartByKIID(doc, kiid)

                            # Go through changes ["property", *new_value*]
                            for change in changes:
                                prop, value = change[0], change[1]

                                if prop == "pos_delta":

                                    # TODO do not move point to new pos -> change constrain value of pad

                                    delta = App.Vector(value[0] / SCALE,
                                                       -value[1] / SCALE,
                                                       0)
                                    # Get footprint position
                                    base = fp_part.Placement.Base
                                    # Find geometry in sketch with same Tag
                                    geom_index = getGeomsByTags(sketch, pad_part.Tags)[0]
                                    # Move pad for fp bas and new delta
                                    sketch.movePoint(geom_index, 3, base + delta)
                                    # Save new delta to pad object
                                    pad_part.PosDelta = delta

                                    # Update dictionary
                                    for pad in footprint["pads_pth"]:
                                        if pad["kiid"] != kiid:
                                            continue
                                        # Update dictionary entry with same KIID
                                        pad.update(
                                            {"pos_delta": [value[0],
                                                           value[1]]
                                             }
                                        )

                                elif prop == "hole_size":
                                    # todo UNITS?
                                    # Change radius constraint to new value
                                    sketch.setDatum(pad_part.Constraint,
                                                    App.Units.Quantity(f"{value[0] / SCALE} mm"))
                                    # Save new value to pad object
                                    pad_part.Radius = value[0] / SCALE

                                    # Update dictionary
                                    for pad in footprint["pads_pth"]:
                                        if pad["kiid"] != kiid:
                                            continue
                                        pad.update(
                                            {"hole_size": [value[0],
                                                           value[1]]
                                             }
                                        )

                elif prop == "3d_models":
                    # Remove all existing step models from FP container
                    for feature in fp_part.Group:
                        if "Pads" in feature.Label:
                            continue
                        doc.removeObject(feature.Name)

                    # Re-import footprint step models to FP container
                    for model in value:
                        importModel(model, footprint, fp_part, doc, pcb, MODELS_PATH)
                    # Update dictionary
                    footprint.update({"3d_models": value})


def updateDrawings(doc, pcb, diff, sketch):

    key = "drawings"
    changed = diff[key].get("changed")
    added = diff[key].get("added")
    removed = diff[key].get("removed")

    drawings_part = doc.getObject(f"Drawings_{pcb['general']['pcb_id']}")

    if added:
        for drawing in added:
            # Add to document
            addDrawing(drawing=drawing,
                       doc=doc,
                       pcb_id=pcb_id,
                       container=drawings_part,
                       shape=drawing["shape"])
            # Add to dictionary
            pcb[key].append(drawing)

    if removed:
        for kiid in removed:
            drawing = getDictEntryByKIID(pcb["drawings"], kiid)
            drw_part = getPartByKIID(doc, kiid)
            geoms_indexes = getGeomsByTags(sketch, drw_part.Tags)

            # Delete geometry by index
            sketch.delGeometries(geoms_indexes)
            # Delete drawing part
            doc.removeObject(drw_part.Name)
            doc.recompute()
            # Remove from dictionary
            pcb[key].remove(drawing)

    if changed:
        for entry in changed:
            # Get dictionary items as 1 tuple
            items = [(x, y) for x, y in entry.items()]
            # First index to get tuple inside list  items = [(x,y)]
            # Second index to get values in tuple
            kiid = items[0][0]
            changes = items[0][1]

            drawing = getDictEntryByKIID(pcb["drawings"], kiid)
            drw_part = getPartByKIID(doc, kiid)
            geoms_indexes = getGeomsByTags(sketch, drw_part.Tags)

            for c in changes:
                prop, value = c[0], c[1]
                # Apply changes based on type of geometry
                if "Circle" in drw_part.Label:
                    if prop == "center":
                        center_new = App.Vector(value[0] / SCALE,
                                                -value[1] / SCALE,
                                                0)
                        # Move geometry in sketch to new pos
                        # PointPos parameter for circle center is 3 (second argument)
                        sketch.movePoint(geoms_indexes[0], 3, center_new)
                        # Update pcb dictionary with new values
                        drawing.update({"center": [value[0], value[1]]})

                    elif prop == "radius":
                        # Change radius constraint to new value
                        # first parameter is index of constraint (stored as Part property)
                        sketch.setDatum(drw_part.Constraint, App.Units.Quantity(f"{value / SCALE} mm"))
                        # Save new value to drw Part object
                        drw_part.Radius = value / SCALE
                        # Update pcb dictionary with new value
                        drawing.update({"radius": value})

                elif "Line" in drw_part.Label:
                    # New point position
                    new_point = App.Vector(value[0] / SCALE,
                                           value[1] / SCALE,
                                           0)
                    if prop == "start":
                        # Start point has PointPos parameter 1, end has 2
                        sketch.movePoint(geoms_indexes[0], 1, new_point)
                    elif prop == "end":
                        sketch.movePoint(geoms_indexes[0], 2, new_point)

                elif "Rect" in drw_part.Label or "Polygon" in drw_part.Label:
                    # Delete existing geometries
                    sketch.delGeometries(geoms_indexes)

                    # Add new points to sketch
                    points, tags = [], []
                    for i, p in enumerate(value):
                        point = App.Vector(p[0] / SCALE,
                                           -p[1] / SCALE,
                                           0)
                        if i != 0:
                            # Create a line from current to previous point
                            sketch.addGeometry(Part.LineSegment(point, points[-1]),
                                               False)
                            tags.append(sketch.Geometry[-1].Tag)

                        points.append(point)

                    # Add another line from last to first point
                    sketch.addGeometry(Part.LineSegment(points[-1], points[0]), False)
                    tags.append(sketch.Geometry[-1].Tag)
                    # Add Tags to Part object after it's added to sketch
                    drw_part.Tags = tags

                elif "Arc" in drw_part.Label:
                    # Delete existing arc geometry from sketch
                    sketch.delGeometries(geoms_indexes)

                    points = []
                    for p in value:
                        points.append(
                            App.Vector(p[0] / SCALE,
                                       -p[1] / SCALE,
                                       0)
                        )

                    # Create a new arc (3 points)
                    arc = Part.ArcOfCircle(points[0], points[1], points[2])
                    # Add arc to sketch
                    sketch.addGeometry(arc, False)
                    # Add Tag after its added to sketch
                    drw_part.Tags = sketch.Geometry[-1].Tag


def updateVias(doc, pcb, diff, sketch):

    key = "vias"
    changed = diff[key].get("changed")
    added = diff[key].get("added")
    removed = diff[key].get("removed")

    vias_part = doc.getObject(f"Vias_{pcb['general']['pcb_id']}")

    if added:
        for via in added:
            # Add vias to sketch and container
            addDrawing(drawing=via,
                       doc=doc,
                       pcb_id=pcb_id,
                       container=vias_part)
            # Add to dictionary
            pcb[key].append(via)

    if removed:
        for kiid in removed:
            via = getDictEntryByKIID(pcb["vias"], kiid)
            via_part = getPartByKIID(doc, kiid)
            geom_indexes = getGeomsByTags(sketch, via_part.Tags)

            # Delete geometry by index
            sketch.delGeometries(geom_indexes)
            # Delete via part
            doc.removeObject(via_part.Name)
            doc.recompute()
            # Remove from dictionary
            pcb[key].remove(via)

    if changed:
        for entry in changed:
            # Get dictionary items as 1 tuple
            items = [(x, y) for x, y in entry.items()]
            # First index to get tuple inside list  items = [(x,y)]
            # Second index to get values in tuple
            kiid = items[0][0]
            changes = items[0][1]

            via = getDictEntryByKIID(pcb["vias"], kiid)
            via_part = getPartByKIID(doc, kiid)
            geom_indexes = getGeomsByTags(sketch, via_part.Tags)

            # Go through list of all changes
            # list of changes consists of:  [ [name of property, new value of property] ,..]
            for c in changes:
                prop, value = c[0], c[1]

                if prop == "center":
                    center_new = App.Vector(value[0] / SCALE,
                                            -value[1] / SCALE,
                                            0)
                    # Move geometry in sketch new pos
                    # PointPos parameter for circle center is 3 (second argument)
                    sketch.movePoint(geom_indexes[0], 3, center_new)
                    # Update pcb dictionary with new values
                    via.update({"center": [value[0], value[1]]})

                elif prop == "radius":
                    # Change radius constraint to new value
                    # first parameter is index of constraint (stored as Part property)
                    # TODO if number of constraints changes, .Constraint property becomes wrong?
                    sketch.setDatum(via_part.Constraint, App.Units.Quantity(f"{value / SCALE} mm"))
                    # Save new value to via Part object
                    via_part.Radius = value / SCALE
                    # Update pcb dictionary with new value
                    via.update({"radius": value})