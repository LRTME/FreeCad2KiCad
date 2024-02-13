"""
This module does not log to its own logger. Logging was cause FreeCAD memory violation crash.
Currently, logging is achieved by emitting signal to main thread and logging from there.
"""

import FreeCAD as App
import FreeCADGui as Gui
import Import
import ImportGui
import Part
import Sketcher

import logging
from PySide import QtCore

from API_scripts.constants import SCALE, VEC
from API_scripts.constraints import coincidentGeometry, constrainRectangle, constrainPadDelta
from API_scripts.utils import FreeCADVector


class FcPartDrawer(QtCore.QObject):
    """
    Creates PCB from dictionary as Part object in FreeCAD
    :param doc: FreeCAD document object
    :param doc_gui: FreeCAD Document GUI object
    :param pcb: pcb dictionary, from which to generate PCB part
    :param MODELS_PATH: string (models directory path)
    :return:
    """

    progress = QtCore.Signal(str)
    finished = QtCore.Signal(App.Part)

    def __init__(self, doc, doc_gui, pcb, models_path):
        super().__init__()
        self.doc = doc
        self.doc_gui = doc_gui
        self.pcb = pcb
        self.MODELS_PATH = models_path
        self.pcb_thickness = self.pcb["general"]["thickness"]

    def run(self):
        """ Main method which is called when thread is started. """
        self.progress.emit("Started drawer")

        # Create parent part
        self.pcb_id = self.pcb["general"]["pcb_id"]
        pcb_name = self.pcb["general"]["pcb_name"]
        pcb_part = self.doc.addObject("App::Part", f"{pcb_name}_{self.pcb_id}")
        # Attach hashed filepath as attribute (used when linking existing parts to KiCAD)
        pcb_part.addProperty("App::PropertyString", "KIID", "Data")
        pcb_part.KIID = self.pcb["general"]["kiid"]

        board_geoms_part = self.doc.addObject("App::Part", f"Board_Geoms_{self.pcb_id}")
        pcb_part.addObject(board_geoms_part)

        self.sketch = self.doc.addObject("Sketcher::SketchObject", f"Board_Sketch_{self.pcb_id}")
        board_geoms_part.addObject(self.sketch)

        # ------------------------------------| Drawings |--------------------------------------------- #
        self.progress.emit("Adding drawings to sketch")
        drawings = self.pcb.get("drawings")

        if drawings:
            # Create Drawings container
            drawings_part = self.doc.addObject("App::Part", f"Drawings_{self.pcb_id}")
            drawings_part.Visibility = False
            board_geoms_part.addObject(drawings_part)
            # Add drawings to sketch and container
            for drawing in drawings:
                self.addDrawing(drawing=drawing,
                                container=drawings_part,
                                shape=drawing["shape"])

        self.progress.emit("Adding constraint to sketch")
        # # Call function from utils: coincident constrain all touching vertices in sketch
        # coincidentGeometry(self.sketch)

        # # --------------------------------------| Vias |----------------------------------------------- #
        # self.progress.emit("Adding vias to sketch")
        # vias = self.pcb.get("vias")
        #
        # if vias:
        #     vias_part = self.doc.addObject("App::Part", f"Vias_{self.pcb_id}")
        #     vias_part.Visibility = False
        #     board_geoms_part.addObject(vias_part)
        #     # Add vias to sketch and container
        #     for via in vias:
        #         self.addDrawing(drawing=via,
        #                         container=vias_part)

        # ------------------------------------| Footprints |--------------------------------------------- #
        self.progress.emit("Adding footprints")
        footprints = self.pcb.get("footprints")

        if footprints:
            # Create Footprint container and add it to PCB Part
            footprints_part = self.doc.addObject("App::Part", f"Footprints_{self.pcb_id}")
            pcb_part.addObject(footprints_part)
            # Create Top and Bot containers and add them to Footprints container
            fps_top_part = self.doc.addObject("App::Part", f"Top_{self.pcb_id}")
            fps_bot_part = self.doc.addObject("App::Part", f"Bot_{self.pcb_id}")
            footprints_part.addObject(fps_top_part)
            footprints_part.addObject(fps_bot_part)

            for footprint in footprints:
                self.addFootprintPart(footprint)

        # ------------------------------------| Extrude |--------------------------------------------- #
        self.progress.emit("Extruding sketch")
        # Copied from KiCadStepUpMod
        pcb_extr = self.doc.addObject("Part::Extrusion", f"Board_{self.pcb_id}")
        board_geoms_part.addObject(pcb_extr)
        pcb_extr.Base = self.sketch
        pcb_extr.DirMode = "Normal"
        pcb_extr.DirLink = None
        pcb_extr.LengthFwd = -(self.pcb_thickness / SCALE)
        pcb_extr.LengthRev = 0
        pcb_extr.Solid = True
        pcb_extr.Reversed = False
        pcb_extr.Symmetric = False
        pcb_extr.TaperAngle = 0
        pcb_extr.TaperAngleRev = 0
        pcb_extr.ViewObject.ShapeColor = getattr(
            self.doc.getObject(f"Board_{self.pcb_id}").getLinkedObject(True).ViewObject,
            "ShapeColor", pcb_extr.ViewObject.ShapeColor)
        pcb_extr.ViewObject.LineColor = getattr(
            self.doc.getObject(f"Board_{self.pcb_id}").getLinkedObject(True).ViewObject,
            "LineColor", pcb_extr.ViewObject.LineColor)
        pcb_extr.ViewObject.PointColor = getattr(
            self.doc.getObject(f"Board_{self.pcb_id}").getLinkedObject(True).ViewObject,
            "PointColor", pcb_extr.ViewObject.PointColor)
        # Set extrude pcb color to HTML #339966 (KiCAD StepUp color)
        self.doc_gui.getObject(pcb_extr.Label).ShapeColor = (0.20000000298023224,
                                                             0.6000000238418579,
                                                             0.4000000059604645,
                                                             0.0)
        # Hide white outline on board
        self.sketch.Visibility = False


        # Commented out: recompute in main thread
        # # logger_drawer.info("Recomputing document")
        # self.progress.emit("Recomputing document")
        # self.doc.recompute()
        # Gui.SendMsgToActiveView("ViewFit")
        # self.progress.emit("Finished")
        # # logger_drawer.info("Finished")
        self.finished.emit(pcb_part)

    def addDrawing(self, drawing: dict, container:type(App.Part), shape="Circle"):
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

        self.progress.emit(f"Drawing: {drawing}")

        if "Line" in shape:
            start = FreeCADVector(drawing["start"])
            end = FreeCADVector(drawing["end"])
            line = Part.LineSegment(start, end)
            # Add line to sketch
            self.sketch.addGeometry(line, False)
            # Add Tag after its added to sketch
            obj.Tags = self.sketch.Geometry[-1].Tag

        elif ("Rect" in shape) or ("Polygon" in shape):
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

        elif "Arc" in shape:
            # Get points of arc, convert list to FC vector
            p1 = FreeCADVector(drawing["points"][0])  # Start
            md = FreeCADVector(drawing["points"][1])  # Arc middle
            p2 = FreeCADVector(drawing["points"][2])  # End
            # Create the arc (3 points)
            arc = Part.ArcOfCircle(p1, md, p2)
            # Add arc to sketch
            self.sketch.addGeometry(arc, False)
            # Add Tag after its added to sketch
            obj.Tags = self.sketch.Geometry[-1].Tag

            # Forum post: (arc angles in degrees)
            # center = FreeCAD.Vector(0, 0, 0)
            # axis = FreeCAD.Vector(0, 0, 1)
            # radius = 1.0
            # circle = Part.Circle(center, axis, radius)
            # start = FreeCAD.Units.parseQuantity("0 deg").getValueAs(FreeCAD.Units.Radian)
            # last = FreeCAD.Units.parseQuantity("180 deg").getValueAs(FreeCAD.Units.Radian)
            # arc = Part.ArcOfCircle(circle, start, last)
            # sketch.addGeometry(arc)

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

    def addFootprintPart(self, footprint: dict):
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

        # # Check if footprint has through hole pads
        # if footprint.get("pads_pth"):
        #     pads_part = self.doc.addObject("App::Part", f"Pads_{fp_part.Label}")
        #     pads_part.Visibility = False
        #     fp_part.addObject(pads_part)
        #
        #     constraints = []
        #     for i, pad in enumerate(footprint["pads_pth"]):
        #         # Call function to add pad -> returns FC object and index of geom in sketch
        #         pad_part, index = self.addPad(pad=pad,
        #                                       footprint=footprint,
        #                                       fp_part=fp_part,
        #                                       container=pads_part)
        #         # # Edit: add pad to drawings container, not as child of footprint -> easyer when scanning for new drawings
        #         # drawings_part = self.doc.getObject(f"Drawings_{self.pcb_id}")
        #         # pad_part, index = self.addPad(pad=pad,
        #         #                               footprint=footprint,
        #         #                               fp_part=fp_part,
        #         #                               container=drawings_part)
        #         # save pad and index to list for constraining pads
        #         constraints.append((pad_part, index))
        #
        #     # Add constraints to pads:
        #     constrainPadDelta(self.sketch, constraints)

        # Check footprint for 3D models
        if footprint.get("3d_models"):
            for model in footprint["3d_models"]:
                try:
                    # Import model - call function
                    self.importModel(model, footprint, fp_part)
                except Exception as e:
                    self.progress.emit(e)


    def importModel(self, model: dict, fp: dict, fp_part: type(App.Part)):
        """
        Import .step models to document as children of footprint Part container
        :param model: dictionary with model properties
        :param fp: footprint dictionary
        :param fp_part: FreeCAD App::Part object
        """

        self.progress.emit(f"Importing model {model.get('filename')}")
        # Import model
        path = self.MODELS_PATH + model["filename"] + ".step"
        # Use ImportGui to preserve colors
        # set LinkGroup so that function returns the imported object
        # https://github.com/FreeCAD/FreeCAD/issues/9898
        feature = ImportGui.insert(path, self.doc.Name, useLinkGroup=True)

        # Set label
        feature.Label = f"{fp['ID']}_{fp['ref']}_{model['model_id']}_{self.pcb_id}"
        feature.addProperty("App::PropertyString", "Filename", "KiCAD")
        # feature.Filename = model["filename"].split("/")[-1]
        # Include the whole filename as property:
        feature.Filename = model["filename"]
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


    def addPad(self, pad: dict, footprint:dict, fp_part:type(App.Part), container:type(App.Part)):
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
        # min_axis = pad["hole_size"][1] / SCALE  # not used since pad is a circle
        pos_delta = FreeCADVector(pad["pos_delta"])
        circle = Part.Circle(Center=base + pos_delta,
                             Normal=VEC["z"],
                             Radius=radius)

        # Add ellipse to sketch
        self.sketch.addGeometry(circle, False)
        tag = self.sketch.Geometry[-1].Tag

        # # Add radius constraint
        # self.sketch.addConstraint(Sketcher.Constraint("Radius",  # Type
        #                                               (self.sketch.GeometryCount - 1),  # Index of geometry
        #                                               radius))  # Value (radius)
        # self.sketch.renameConstraint(self.sketch.ConstraintCount - 1,
        #                              f"padradius_{tag}")

        # Create an object to store Tag and Delta
        # obj = self.doc.addObject("Part::Feature", f"{footprint['ref']}_{pad['ID']}_{self.pcb_id}")
        # Mounting hole pad has no ID
        obj = self.doc.addObject("Part::Feature", f"{footprint['ref']}_{self.pcb_id}")
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
