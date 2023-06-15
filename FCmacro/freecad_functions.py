import Draft
import FreeCAD as App
import FreeCADGui as Gui
import Import
import ImportGui
import Part
import PartDesignGui
import Sketcher

from utils import *
from constants import SCALE, VEC
from constraints import coincidentGeometry, coincidentLineVerteces, constrainRectangle, constrainPadDelta
from update_fncs import updateFootprints, updateDrawings, updateVias


# noinspection PyShadowingNames
def importModel(model, fp, fp_part, doc, pcb_id, thickness, MODELS_PATH):
    """
    Import .step models to document as children of footprint Part container
    :param model: dictioneray with model properties
    :param fp: footprint dictionary
    :param fp_part: FreeCAD App::Part object
    :param doc: FreeCAD document object
    :param pcb_id: string
    :param thickness: pcb thickenss in mm (for moving model by z)
    :param MODELS_PATH: string (models directory path)
    """

    # Import model
    path = MODELS_PATH + model["filename"] + ".step"
    ImportGui.insert(path, doc.Name)

    # Last obj in doc is imported model
    feature = doc.Objects[-1]
    # Set label
    feature.Label = f"{fp['ID']}_{fp['ref']}_{model['model_id']}_{pcb_id}"
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
        feature.Placement.Base.z = -(thickness / SCALE)

    # Scale model if it's not 1x
    if model["scale"] != [1.0, 1.0, 1.0]:
        # Make clone with Draft module in order to scale shape
        clone = Draft.make_clone(feature, delta=offset)
        clone.Scale = App.Vector(model["scale"][0],
                                 model["scale"][1],
                                 model["scale"][2])
        # Rename original: add "_o_"
        feature.Label = f"{fp['ID']}_{fp['ref']}_{model['model_id']}_o_{pcb_id}"
        # Add clone name without "_o_"
        clone.Label = f"{fp['ID']}_{fp['ref']}_{model['model_id']}_{pcb_id}"
        clone.addProperty("App::PropertyString", "Filename", "Base")
        clone.Filename = model["filename"].split("/")[-1]
        clone.addProperty("App::PropertyBool", "Model", "Base")
        clone.Model = True
        # Hide original
        feature.Visibility = False
        fp_part.addObject(clone)
        # Both feature and clone must be in footprint part containter for clone to work

    fp_part.addObject(feature)


def addPad(pad, footprint, fp_part, doc, pcb_id, container):
    """
    Add circle geometry to sketch, create a Pad Part object and add it to footprints pad container.
    :param pad: pcb dictionary entry (pad data)
    :param footprint: pcb dictionary entry  (footprint data)
    :param fp_part: footprint Part object
    :param doc: FreeCAD document object
    :param pcb_id: string
    :param container: FreeCAD Part object
    :return: tuple of int and tuple -> (index, (const_x, const_y))
    """

    sketch = doc.getObject(f"Board_Sketch_{pcb_id}")
    base = fp_part.Placement.Base

    maj_axis = pad["hole_size"][0] / SCALE
    min_axis = pad["hole_size"][1] / SCALE
    pos_delta = App.Vector(pad["pos_delta"][0] / SCALE,
                           pad["pos_delta"][1] / SCALE,
                           0)

    # center = App.Vector((footprint["pos"][0] + pad["pos_delta"][0]) / SCALE,
    #                     -(footprint["pos"][1] + pad["pos_delta"][1]) / SCALE,
    #                     0)
    circle = Part.Circle(Center=base + pos_delta,
                         Normal=VEC["z"],
                         Radius=float(maj_axis) / 2)
    # Add ellipse to sketch
    sketch.addGeometry(circle, False)
    # Add radius constraint
    sketch.addConstraint(Sketcher.Constraint("Radius",                    # Type
                                             (sketch.GeometryCount - 1),  # Index of geometry
                                             (maj_axis / 2)))             # Value (radius)

    # Create an object to store Tag and Delta
    obj = doc.addObject("Part::Feature", f"{footprint['ref']}_{pad['ID']}_{pcb_id}")
    obj.Shape = circle.toShape()
    # Store abosolute position of pad (used for comparing to sketch geometry position)
    obj.Placement.Base = base + pos_delta
    # Add properties to object:
    # Tag property to store geometry sketch ID (Tag) used for editing sketch geometry
    obj.addProperty("App::PropertyStringList", "Tags", "Sketch")
    # Add Tag after its added to sketch!
    obj.Tags = sketch.Geometry[-1].Tag
    # Store position delta, which is used when moving geometry in sketch (apply diff)
    obj.addProperty("App::PropertyVector", "PosDelta")
    obj.PosDelta = pos_delta
    # Save radius of circle
    obj.addProperty("App::PropertyFloat", "Radius")
    obj.Radius = maj_axis / 2
    # Save constraint index (used for modifying hole size when applying diff)
    obj.addProperty("App::PropertyInteger", "Constraint", "Sketch")
    obj.Constraint = sketch.ConstraintCount - 1
    # Add KIID as property
    obj.addProperty("App::PropertyString", "KIID", "KiCAD")
    obj.KIID = pad["kiid"]

    # Hide pad object and add it to pad Part container
    obj.Visibility = False
    container.addObject(obj)

    return (sketch.GeometryCount - 1), (pad["pos_delta"][0] / SCALE, pad["pos_delta"][1] / SCALE)


def addFootprintPart(footprint, doc, pcb, MODELS_PATH):
    """
    Adds footprint container to "Top" or "Bot" Group of "Footprints"
    Imports Step models as childer
    Add "Pads" container with through hole pads - add holes to sketch as circles
    :param footprint: footprint dictionary
    :param doc: FreeCAD document object
    :param pcb: pcb dictionary
    :param MODELS_PATH: string (models directory path)
    """
    pcb_id = pcb["general"]["pcb_id"]
    sketch = doc.getObject(f"Board_Sketch_{pcb_id}")

    # Crate a part object for each footprint
    # naming: " kiid_ref_id "  so there is no auto-self-naming duplicates
    fp_part = doc.addObject("App::Part", f"{footprint['ID']}_{footprint['ref']}_{pcb_id}")
    fp_part.Label = f"{footprint['ID']}_{footprint['ref']}_{pcb_id}"
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
        doc.getObject(f"Top_{pcb_id}").addObject(fp_part)
    else:
        doc.getObject(f"Bot_{pcb_id}").addObject(fp_part)

    # Footprint placement
    base = App.Vector(footprint["pos"][0] / SCALE,
                      -footprint["pos"][1] / SCALE,
                      0)
    fp_part.Placement.Base = base
    # Footprint rotation around z axis
    fp_part.Placement.rotate(VEC["0"], VEC["z"], footprint["rot"])

    # Check if footprint has through hole pads
    if footprint.get("pads_pth"):
        pad_part = doc.addObject("App::Part", f"Pads_{fp_part.Label}")
        pad_part.Visibility = False
        fp_part.addObject(pad_part)

        constraints = []
        for i, pad in enumerate(footprint["pads_pth"]):
            # Call function to add pad -> returns tuple of geometry index in Delta Pos values
            i, c = addPad(pad=pad,
                          footprint=footprint,
                          fp_part=fp_part,
                          doc=doc,
                          pcb_id=pcb_id,
                          container=pad_part)
            # save index and values (tuple) to list for constraining pads
            constraints.append((i, c))

        # Add constarints to pads:
        constrainPadDelta(sketch, constraints)

    # Check footprint for 3D models
    if footprint.get("3d_models"):
        for model in footprint["3d_models"]:
            # Import model - call function
            importModel(model, footprint, fp_part, doc, pcb_id, pcb["general"]["thickness"], MODELS_PATH)


def addDrawing(drawing, doc, pcb_id, container, shape="Circle"):
    """
    Add a geometry to board sketch
    Add an object with geometry properies to Part container (Drawings of Vias)
    :param drawing: pcb dictionary entry
    :param doc: FreeCAD document object
    :param pcb_id: string
    :param container: FreeCAD Part object
    :param shape: string (Circle, Rect, Polygon, Line, Arc)
    :return:
    """
    sketch = doc.getObject(f"Board_Sketch_{pcb_id}")

    # Create an object to store Tag
    obj = doc.addObject("Part::Feature", f"{shape}_{pcb_id}")
    obj.Label = f"{drawing['ID']}_{shape}_{pcb_id}"
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
            point = App.Vector(p[0] / SCALE,
                               -p[1] / SCALE,
                               0)
            # If not first point
            if i != 0:
                # Create a line from current to previous point
                sketch.addGeometry(Part.LineSegment(point, points[-1]), False)
                tags.append(sketch.Geometry[-1].Tag)
                geom_indexes.append(sketch.GeometryCount - 1)

            points.append(point)

        # Add another line from last to first point
        sketch.addGeometry(Part.LineSegment(points[0], points[-1]), False)
        tags.append(sketch.Geometry[-1].Tag)
        geom_indexes.append(sketch.GeometryCount - 1)
        # Add Tags after geometries are added to sketch
        obj.Tags = tags
        # Add horizontal/ vertical and perpendicular constraints if shape is rectangle
        if "Rect" in shape:
            constrainRectangle(sketch, geom_indexes)

    elif "Line" in shape:
        start = App.Vector(drawing["start"][0] / SCALE,
                           -drawing["start"][1] / SCALE,
                           0)
        end = App.Vector(drawing["end"][0] / SCALE,
                         -drawing["end"][1] / SCALE,
                         0)
        line = Part.LineSegment(start, end)
        # Add line to sketch
        sketch.addGeometry(line, False)
        # Add Tag after its added to sketch
        obj.Tags = sketch.Geometry[-1].Tag

    elif "Arc" in shape:
        p1 = App.Vector(drawing["points"][0][0] / SCALE,
                        -drawing["points"][0][1] / SCALE,
                        0)
        p2 = App.Vector(drawing["points"][1][0] / SCALE,
                        -drawing["points"][1][1] / SCALE,
                        0)

        p3 = App.Vector(drawing["points"][2][0] / SCALE,
                        -drawing["points"][2][1] / SCALE,
                        0)

        arc = Part.ArcOfCircle(p1, p2, p3)
        # Add arc to sketch
        sketch.addGeometry(arc, False)
        # Add Tag after its added to sketch
        obj.Tags = sketch.Geometry[-1].Tag

    elif "Circle" in shape:
        radius = drawing["radius"] / SCALE
        center = App.Vector(drawing["center"][0] / SCALE,
                            -drawing["center"][1] / SCALE,
                            0)
        circle = Part.Circle(Center=center,
                             Normal=VEC["z"],
                             Radius=radius)
        # Add circle to sketch
        sketch.addGeometry(circle, False)
        sketch.addConstraint(Sketcher.Constraint('Radius',
                                                 (sketch.GeometryCount - 1),
                                                 radius))
        # Add Tag after its added to sketch
        obj.Tags = sketch.Geometry[-1].Tag
        obj.addProperty("App::PropertyFloat", "Radius")
        obj.Radius = radius
        # Save constraint index (used for modifying hole size when applying diff)
        obj.addProperty("App::PropertyInteger", "Constraint", "Sketch")
        obj.Constraint = sketch.ConstraintCount - 1


def drawPcb(doc, doc_gui, pcb, MODELS_PATH):
    """
    Creates PCB from dictionary as Part object in FC
    :param doc: FreeCAD document object
    :param doc_gui: FreeCAD Document GUI object
    :param pcb: pcb dictionary, from which to generate PCB part
    :param MODELS_PATH: string (models directory path)
    :return: FreeCAD Part object
    """
    # Draft need to be activated
    Gui.activateWorkbench("DraftWorkbench")

    try:  # Delete pcb object with same name if it exists
        obj = doc.getObject(pcb["general"]["pcb_name"] + "_" + pcb["general"]["pcb_id"])
        obj.removeObjectsFromDocument()
        doc.removeObject(obj.Label)
        doc.recompute()
    except AttributeError:
        pass

    if not doc:
        doc = App.newDocument("Unnamed")

    # Create parent part
    pcb_part = doc.addObject("App::Part", pcb["general"]["pcb_name"] + "_" + pcb["general"]["pcb_id"])
    pcb_id = pcb["general"]["pcb_id"]
    # Add entire JSON file string as property of parent part
    pcb_part.addProperty("App::PropertyString", "JSON", "Data")
    pcb_part.JSON = str(pcb)

    board_geoms_part = doc.addObject("App::Part", f"Board_Geoms_{pcb_id}")
    pcb_part.addObject(board_geoms_part)

    sketch = doc.addObject("Sketcher::SketchObject", f"Board_Sketch_{pcb_id}")
    board_geoms_part.addObject(sketch)

    # DRAWINGS
    drawings = pcb.get("drawings")
    if drawings:
        # Create Drawings container
        drawings_part = doc.addObject("App::Part", f"Drawings_{pcb_id}")
        drawings_part.Visibility = False
        board_geoms_part.addObject(drawings_part)
        # Add drawings to sketch and container
        for drawing in drawings:
            addDrawing(drawing=drawing,
                       doc=doc,
                       pcb_id=pcb_id,
                       container=drawings_part,
                       shape=drawing["shape"])
    # VIAs
    vias = pcb.get("vias")
    if vias:
        vias_part = doc.addObject("App::Part", f"Vias_{pcb_id}")
        vias_part.Visibility = False
        board_geoms_part.addObject(vias_part)
        # Add vias to sketch and container
        for via in vias:
            addDrawing(drawing=via,
                       doc=doc,
                       pcb_id=pcb_id,
                       container=vias_part)

    # Constraints
    coincidentGeometry(sketch)

    # EXTRUDE
    pcb_extr = doc.addObject('Part::Extrusion', f"Board_{pcb_id}")
    board_geoms_part.addObject(pcb_extr)
    pcb_extr.Base = sketch
    pcb_extr.DirMode = "Normal"
    pcb_extr.DirLink = None
    pcb_extr.LengthFwd = -(pcb["general"]["thickness"] / SCALE)
    pcb_extr.LengthRev = 0
    pcb_extr.Solid = True
    pcb_extr.Reversed = False
    pcb_extr.Symmetric = False
    pcb_extr.TaperAngle = 0
    pcb_extr.TaperAngleRev = 0
    pcb_extr.ViewObject.ShapeColor = getattr(doc.getObject(f"Board_{pcb_id}").getLinkedObject(True).ViewObject,
                                             'ShapeColor', pcb_extr.ViewObject.ShapeColor)
    pcb_extr.ViewObject.LineColor = getattr(doc.getObject(f"Board_{pcb_id}").getLinkedObject(True).ViewObject,
                                            'LineColor', pcb_extr.ViewObject.LineColor)
    pcb_extr.ViewObject.PointColor = getattr(doc.getObject(f"Board_{pcb_id}").getLinkedObject(True).ViewObject,
                                             'PointColor', pcb_extr.ViewObject.PointColor)
    # Set extrude pcb color to HTML #339966
    doc_gui.getObject(pcb_extr.Label).ShapeColor = (0.20000000298023224, 0.6000000238418579, 0.4000000059604645, 0.0)

    sketch.Visibility = False

    # FOOTPRINTS
    footprints = pcb.get("footprints")
    if footprints:
        # Create Footprint container and add it to PCB Part
        footprints_part = doc.addObject("App::Part", f"Footprints_{pcb_id}")
        pcb_part.addObject(footprints_part)
        # Create Top and Bot containers and add them to Footprints container
        fps_top_part = doc.addObject("App::Part", f"Top_{pcb_id}")
        fps_bot_part = doc.addObject("App::Part", f"Bot_{pcb_id}")
        footprints_part.addObject(fps_top_part)
        footprints_part.addObject(fps_bot_part)

        for footprint in footprints:
            addFootprintPart(footprint, doc, pcb, MODELS_PATH)

    doc.recompute()
    # Hide grid from Draft module
    Gui.runCommand("Draft_ToggleGrid")
    Gui.SendMsgToActiveView("ViewFit")

    return pcb_part


def updatePartFromDiff(doc, pcb, diff):
    """
    Updates Part objects in FC and updates internal pcb dictionary
    :param doc: FreeCAD document object
    :param pcb: dict
    :param diff: dict
    :return:
    """

    pcb_id = pcb["general"]["pcb_id"]
    sketch = doc.getObject(f"Board_Sketch_{pcb_id}")

    if diff.get("footprints"):
        updateFootprints(doc, pcb, diff, sketch)

    if diff.get("drawings"):
        updateDrawings(doc, pcb, diff, sketch)

    if diff.get("vias"):
        updateVias(doc, pcb, diff, sketch)

    # Add new PCB dictionary as Property of pcb_Part
    pcb_name = pcb["general"]["pcb_name"]
    pcb_part = doc.getObject(f"{pcb_name}_{pcb_id}")
    pcb_part.JSON = str(pcb)



def scanFootprints(doc, pcb):
    """
    Scans data of all objects in FreeCAD and updates pcb dictionary
    :param doc: FreeCAD document object
    :param pcb: dict
    :return:
    """
    # TODO function need to get all properties of fp (getFPData) and calculate hash, then compare new hash to old
    #  to see if fp was changed. (like it is on KC side)
    # Footprint would need to contain all properties as it does in KC

    # Currently works with updating position of fp, and position of pads

    # TODO build a diff dictionary to send back to KiCAD

    pcb_id = pcb["general"]["pcb_id"]
    sketch = doc.getObject(f"Board_Sketch_{pcb_id}")
    footprint_list = pcb["footprints"]

    # Get FC object corresponding to pcb_id
    pcb_part = doc.getObject(pcb["general"]["pcb_name"] + f"_{pcb_id}")
    # Get footprints part container
    fps_parts = pcb_part.getObject(f"Footprints_{pcb_id}")

    # Go through top and bot footprint containers
    for fp_part in fps_parts.getObject(f"Top_{pcb_id}").Group + fps_parts.getObject(f"Bot_{pcb_id}").Group:

        # Get corresponding footprint in dictionary to be edited
        footprint = getDictEntryByKIID(footprint_list, fp_part.KIID)
        # Skip if failed to get footprint in dictionary
        if not footprint:
            continue

        # Update dictionary entry with new position coordinates
        footprint.update({"pos": toList(fp_part.Placement.Base)})

        # TODO update other properties
        # TODO handle rotation (move holes in sketch)

        # Model changes in FC are ignored (no KIID)

        # Handle change of Pad Position Delta in object (feature) and change of footprint position in sketch:

        # Get FC container Part where pad objects are stored
        pads_part = getPadContainer(fp_part)
        # Check if gotten pads part
        if not pads_part:
            continue

        # Go through pads
        for pad_part in pads_part.Group:

            # Get corresponding pad in dictionary to be edited
            pad = getDictEntryByKIID(footprint["pads_pth"], pad_part.KIID)
            # Get sketch geometry by Tag:
            # first get index (single entry in list) of pad geometry in sketch
            geom_index = getGeomsByTags(sketch, pad_part.Tags)[0]
            # get geometry by index
            pad_geom = sketch.Geometry[geom_index]

            # Check if gotten dict entry and sketch geometry
            if not pad and not pad_geom:
                continue

            # If pad position delta was edited as vector attribute by user:
            # Compare dictionary deltas to property deltas
            if pad["pos_delta"] != toList(pad_part.PosDelta):

                # Update dictionary with new deltas
                pad.update({"pos_delta": toList(pad_part.PosDelta)})
                # Move geometry in sketch to new position
                sketch.movePoint(geom_index,                                  # Index of geometry
                                 3,                                           # Index of vertex (3 is center)
                                 fp_part.Placement.Base + pad_part.PosDelta)  # New position

            # If pad was moved in sketch by user:
            # Check if pad is first pad of footprint (with relative pos 0) -> this is footprint base
            if pad_part.PosDelta == App.Vector(0, 0, 0):
                # Get new footprint base
                new_base = pad_geom.Center

                # Compare geometry position with pad object position, if not same: sketch has been edited
                if new_base!= pad_part.Placement.Base:

                    # Move footprint to new base position
                    fp_part.Placement.Base = new_base
                    # Update footprint dictionary entry with new position
                    footprint.update({"pos": toList(new_base)})

            # Update pad absolute placement property for all pads
            pad_part.Placement.Base = pad_geom.Center
