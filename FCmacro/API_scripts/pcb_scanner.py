import FreeCAD as App

import math
import os

from PySide import QtCore

from API_scripts.constants import SCALE, VEC
from API_scripts.utils import *


class FcPcbScanner(QtCore.QObject):

    progress = QtCore.Signal(str)
    finished = QtCore.Signal(dict)


    def __init__(self, doc, pcb):
        super().__init__()
        self.doc = doc
        self.pcb = pcb
        self.pcb_id = self.pcb["general"]["pcb_id"]
        self.sketch = doc.getObject(f"Board_Sketch_{self.pcb_id}")


    def run(self):

        self.progress.emit("Starting scanner")
        diff_temp = self.getPcbDrawings()

        self.finished.emit(diff_temp)


    def getPcbDrawings(self):

        added, removed, changed = [], [], []

        self.drawings_part = self.doc.getObject(f"Drawings_{self.pcb_id}")

        self.progress.emit("Started method")

        # Break if invalid doc or pcb
        if not (self.sketch and self.drawings_part):
            self.progress.emit("Breaking")
            self.finished.emit()
            return 0

        # # Get list of existing drawings in dictionary
        # try:
        #     list_of_ids = [d["kiid"] for f in pcb["drawings"]]
        # except TypeError:
        #     # No drawings in pcb dictionary
        #     list_of_ids = []


        # Go through geometries in sketch
        # look at geom.Tag, compare tag with Tag saved as attribute in geometry object inside FC
        # save all vertexes

        # Option 1: go through geometry in sketch and find corresponding drawing Part ?
        # # Go through existing geometry in Sketch:
        # for geom in self.sketch.Geometry:
        #     # Go through drawings in part containter:
        #     for drawing_part in self.drawings_part.Group:
        #
        #         # Compare tags
        #         if geom.Tag in drawing_part.Tags:
        #             pass

        # Option 2: go through drawings in part containter and find corresponding geometry in sketch
        # Go through drawings in part containter:
        for drawing_part in self.drawings_part.Group:

            # Get indexes of all elements in sketch which are part of drawing (lines of rectangle, etc.)
            geoms = getGeomsByTags(sketch=self.sketch,
                                   tags=drawing_part.Tags)

            # Get old dictionary entry to be edited (by KIID)
            drawing_old = getDictEntryByKIID(list=self.pcb["drawings"],
                                             kiid=drawing_part.KIID)
            # Get new drawing data
            drawing_new = self.getDrawingData(drawing_part, geoms)
            if not drawing_new:
                continue

            # TODO
            # either write hash function (hash calculation is incosistent from KC to FC)
            # or
            # skip hash check and compare values even is same  <- CURRENT SOLUTION
            # TODO use hashlib.md5(b"") hashing algorithm

            # Add old data to new drawing, so that data model is consistent
            drawing.update(
                {
                    "hash": drawing_old["hash"],
                    "ID": drawing_old["id"],
                    "kiid": drawing_old["kiid"]
                }
            )

            # Find diffs in dictionaries by comparing all key value pairs
            drawing_diffs = []
            for key, value in drawing_new.items():
                # Check all properties of drawing (keys), if same as in old dictionary -> skip
                if value == drawing_old[key]:
                    continue
                # Add diff to list
                drawing_diffs.append([key, value])
                # Update old dictionary
                drawing_old.update({key: value})

            if drawing_diffs:
                # Hash itself when all changes applied
                # TODO hash?
                # drawing_old.update({"hash": hash(str(drawing_old))})
                # Append dictionary with ID and list of changes to list of changed drawings
                changed.append({drawing_old["kiid"]: drawing_diffs})


        # Find new drawings
        # Find deleted drawings

        result = {}
        if added:
            result.update({"added": added})
        if changed:
            result.update({"changed": changed})
        if removed:
            result.update({"removed": removed})


        return result


    def getDrawingData(self, drawing_part, geoms):
        """
        Get dictionary with drawing data
        :param drawing_part: FreeCAD Part object
        :param geoms: list of indexes of geometry (which form a drawing) in sketch
        :return:
        """

        self.progress.emit(f"Called function drawing data on {drawing_part.Name}")

        drawing = None

        if ("Line" in drawing_part.Name) and (len(geoms) == 1):
            # Get line geometry by index (single value in "geoms" list)
            line = self.sketch.Geometry[geoms[0]]
            drawing = {
                "shape": "Line",
                "start": toList(line.StartPoint),
                "end": toList(line.EndPoint)
            }


        elif ("Rect" in drawing_part.Name) or ("Poly" in drawing_part.Name):
            vertices = []
            # Get lines geometries in sketch by index
            lines = self.sketch.Geometry[geoms]

            # Get rectangle vertices
            for line in lines:
                # Get start and end points of each line in rectangle (or poly)
                start = toList(line.StartPoint)
                end = toList(line.EndPoint)
                # Add points to array if new, so vertices array has unique elements
                if start not in vertices:
                    vertices.append(start)
                if end not in vertices:
                    vertices.append(end)

            # Add points to dictionary
            drawing = {"points": vertices}
            # Add shape to dictionary
            if "Rect" in drawing_part.Name:
                drawing.update({"shape": "Rect"})
            elif "Poly" in drawing_part.Name:
                drawing.update({"shape": "Poly"})


        elif ("Arc" in drawing_part.Name) and (len(geoms) == 1):
            # Get arc geometry in sketch by index
            arc = self.sketch.Geometry[geoms[0]]
            radius = arc.Radius
            start = arc.StartPoint
            end = arc.EndPoint
            center = arc.Center

            # Calculate arc middle point (not directly accessible via FC API)
            # Perform vector calculations on FreeCAD vector objects (floats) and not (int)lists
            a = start - center
            b = end - center
            # m is a vector that goes from center towards middle point
            #m = a + b
            # normalize m to unit vector (direction), scale it by radius
            #m = m.normalize() * radius

            # Get arc angle between a and b
            angle = math.atan2(b.y, b.x) - math.atan2(a.y, a.x)
            if angle < 0:
                angle = 2 * math.pi + angle

            # rotate a by half the arc angle
            m = rotateVector(vector=a,
                             angle=(angle / 2))

            # get arc middle point
            md = center + m

            # Convert FreeCAD vectors to lists, add to dictionary
            drawing = {
                "shape": "Arc",
                "points": [
                    toList(start),
                    toList(md),
                    toList(end)
                ]
            }


        elif ("Circle" in drawing_part.Name) and (len(geoms) == 1):
            # Get circle geometry in sketch by index
            circle = self.sketch.Geometry[geoms[0]]
            drawing = {
                "shape": "Circle",
                "center": toList(circle.Center),
                "radius": toList(circle.Radius)
            }


        if drawing:
            return drawing

    #
    # @staticmethod
    # def scanFootprints(doc, pcb):
    #
    #     pcb_id = pcb["general"]["pcb_id"]
    #     sketch = doc.getObject(f"Board_Sketch_{pcb_id}")
    #     footprint_list = pcb["footprints"]
    #
    #     # Get FC object corresponding to pcb_id
    #     pcb_part = doc.getObject(pcb["general"]["pcb_name"] + f"_{pcb_id}")
    #     # Get footprints part container
    #     fps_parts = pcb_part.getObject(f"Footprints_{pcb_id}")
    #
    #     # Go through top and bot footprint containers
    #     for fp_part in fps_parts.getObject(f"Top_{pcb_id}").Group + fps_parts.getObject(f"Bot_{pcb_id}").Group:
    #
    #         # Get corresponding footprint in dictionary to be edited
    #         footprint = getDictEntryByKIID(footprint_list, fp_part.KIID)
    #         # Skip if failed to get footprint in dictionary
    #         if not footprint:
    #             continue
    #
    #
    #         # Update dictionary entry with new position coordinates
    #         footprint.update({"pos": toList(fp_part.Placement.Base)})
    #
    #         # Model changes in FC are ignored (no KIID)
    #
    #         # Get FC container Part where pad objects are stored
    #         pads_part = getPadContainer(fp_part)
    #         # Check if gotten pads part
    #         if not pads_part:
    #             continue
    #
    #         # Go through pads
    #         for pad_part in pads_part.Group:
    #             # Get corresponding pad in dictionary to be edited
    #             pad = getDictEntryByKIID(footprint["pads_pth"], pad_part.KIID)
    #             # Get sketch geometry by Tag:
    #             # first get index (single entry in list) of pad geometry in sketch
    #             geom_index = getGeomsByTags(sketch, pad_part.Tags)[0]
    #             # get geometry by index
    #             pad_geom = sketch.Geometry[geom_index]
    #             # Check if gotten dict entry and sketch geometry
    #             if not pad and not pad_geom:
    #                 continue
    #
    #
    #             # ----- If pad position delta was edited as vector attribute by user:  -----------
    #             # Compare dictionary deltas to property deltas
    #             if pad["pos_delta"] != toList(pad_part.PosDelta):
    #                 # Update dictionary with new deltas
    #                 pad.update({"pos_delta": toList(pad_part.PosDelta)})
    #                 # Move geometry in sketch to new position
    #                 sketch.movePoint(geom_index,  # Index of geometry
    #                                  3,  # Index of vertex (3 is center)
    #                                  fp_part.Placement.Base + pad_part.PosDelta)  # New position
    #
    #             # ------- If pad was moved in sketch by user:  -----------------------------------
    #             # Check if pad is first pad of footprint (with relative pos 0)
    #             # -> this is footprint base, move only this hole because others are constrained to it
    #             if pad_part.PosDelta == App.Vector(0, 0, 0):
    #                 # Get new footprint base
    #                 new_base = pad_geom.Center
    #                 # Compare geometry position with pad object position, if not same: sketch has been edited
    #                 if new_base != pad_part.Placement.Base:
    #                     # Move footprint to new base position
    #                     fp_part.Placement.Base = new_base
    #                     # Update footprint dictionary entry with new position
    #                     footprint.update({"pos": toList(new_base)})
    #
    #             # Update pad absolute placement property for all pads
    #             pad_part.Placement.Base = pad_geom.Center
