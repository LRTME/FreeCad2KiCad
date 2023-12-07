import FreeCAD as App

import configparser
import hashlib
import itertools
import logging
import math
import os
import sys

from PySide import QtCore

from API_scripts.constants import SCALE, VEC
from API_scripts.utils import *

# Get parent direcory, so that ConfigLoader can be imported from config_loader module
parent_directory = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(parent_directory)

from Config.config_loader import ConfigLoader


# Initialize logger
logger_scanner = logging.getLogger("SCANNER")


class FcPcbScanner(QtCore.QObject):

    progress = QtCore.Signal(str)
    finished = QtCore.Signal(dict)


    def __init__(self, doc, pcb, diff):
        super().__init__()

        # Get config.ini file path
        config_file = os.path.join(parent_directory, "Config", "config.ini").replace("\\", "/")
        self.config = ConfigLoader(config_file)

        self.doc = doc
        self.pcb = pcb
        # Take diff dictionary (existing or empty) to be updated
        self.diff = diff
        self.pcb_id = self.pcb["general"]["pcb_id"]
        self.sketch = doc.getObject(f"Board_Sketch_{self.pcb_id}")


    def run(self):
        logger_scanner.info("Scanner started")

        # Update existing diff dictionary with new value
        FcPcbScanner.updateDiffDict(key="drawings",
                                    value=self.getPcbDrawings(),
                                    diff=self.diff)
        # TODO footprints
        logger_scanner.info("Scanner finished")
        self.finished.emit(self.diff)


    @staticmethod
    def updateDiffDict(key, value, diff):
        """Helper function for adding and removing entries from diff dictionary"""

        if value.get("added") or value.get("changed") or value.get("removed"):
            diff.update({key: value})
        else:
            # Remove from diff if no new changes
            try:
                diff.pop(key)
            except KeyError:
                pass


    def getPcbDrawings(self):

        added, removed, changed = [], [], []

        # Get FreeCAD drawings_xyzz container part where drawings are stored
        self.drawings_part = self.doc.getObject(f"Drawings_{self.pcb_id}")

        # Break if invalid doc or pcb
        if not (self.sketch and self.drawings_part):
            logger_scanner.error("Breaking (invalid sketch or part)")
            self.finished.emit()
            return 0

        # Store all geometry tags that have been scanned to this list. Used later for finding new drawings
        scanned_geometries_tags = []

        # Go through drawings in part containter and find corresponding geometry in sketch
        for drawing_part in self.drawings_part.Group:

            # Get indexes of all elements in sketch which are part of drawing (lines of rectangle, etc.)
            geoms_indices = getGeomsByTags(sketch=self.sketch,
                                           tags=drawing_part.Tags)
            # Store geometry tags to a list. This tracks which sketch geometries have been scanned (used for finding new
            # drawings later)
            scanned_geometries_tags.append(drawing_part.Tags)

            # Get old dictionary entry to be edited (by KIID)
            drawing_old = getDictEntryByKIID(list=self.pcb["drawings"],
                                             kiid=drawing_part.KIID)
            # Get new drawing data
            drawing_new = self.getDrawingData(geoms_indices,
                                              drawing_part=drawing_part)
            if not drawing_new:
                continue

            # Calculate new hash and compare it to hash in old dictionary
            # to see if anything is changed
            drawing_new_hash = hashlib.md5(str(drawing_new).encode("utf-8"))
            if drawing_new_hash.hexdigest() == drawing_old["hash"]:
                # Skip if no diffs, which is indicated by the same hash (hash in calculated from dictionary)
                logger_scanner.debug(f"Same hash for {drawing_old['shape']}, kiid: {drawing_old['kiid']}")
                continue
            logger_scanner.debug(f"Different hash for {drawing_old['shape']}, kiid: {drawing_old['kiid']}")

            # Add old missing key:value pairs in new dictionary. This is so that new dictionary has all the same keys
            # as old dictionary -> important when comparing all values between old and new in the next step.
            drawing_new.update({"hash": drawing_old["hash"]})
            drawing_new.update({"ID": drawing_old["ID"]})
            drawing_new.update({"kiid": drawing_old["kiid"]})
            logger_scanner.debug(f"Updated drawing: {drawing_new}")

            # Find diffs in dictionaries by comparing all key value pairs
            # (this is why drawing had to be updated beforehand)
            drawing_diffs = []
            for key, value in drawing_new.items():
                # Check all properties of drawing (keys), if same as in old dictionary -> skip
                if value == drawing_old[key]:
                    continue
                # Add diff to list
                drawing_diffs.append([key, value])
                logger_scanner.debug(f"Found diff: {key}:{value}")
                # Update old dictionary
                drawing_old.update({key: value})

            if drawing_diffs:
                # Hash itself when all changes applied
                drawing_old_hash = hashlib.md5(str(drawing_old).encode("utf-8"))
                drawing_old.update({"hash": drawing_old_hash.hexdigest()})
                # Append dictionary with ID and list of changes to list of changed drawings
                changed.append({drawing_old["kiid"]: drawing_diffs})


        # Find new drawings (rectangles and polynoms are treated as lines)
        # Flatten 2D list to 1D list. 2D list can exist because a single drawing part (rectangle, polynom) can append
        # a list of line geometries
        scanned_geometries_tags = list(itertools.chain.from_iterable(scanned_geometries_tags))
        # Walk all the geometries in sketch:
        for geometry_index, sketch_geom in enumerate(self.sketch.Geometry):
            # If current geometry exists in list of scanned geometries, skip this geometry
            if sketch_geom.Tag in scanned_geometries_tags:
                continue
            # Call Function to get new drawing data
            # Argument must be list type
            drawing = self.getDrawingData(geoms=[geometry_index])

            if drawing:
                added.append(drawing)



        # TODO Find deleted drawings


        result = {}
        if added:
            result.update({"added": added})
            logger_scanner.info(f"Found new drawings: {str(added)}")
        if changed:
            result.update({"changed": changed})
            logger_scanner.info(f"Found changed drawings: {str(changed)}")
        if removed:
            result.update({"removed": removed})
            logger_scanner.info(f"Found removed drawings: {str(removed)}")

        logger_scanner.debug("Drawings finished.")
        return result


    def getDrawingData(self, geoms, drawing_part=None):
        """
        Get dictionary with drawing data
        :param geoms: list of indexes of geometry (which form a drawing) in sketch
        :param drawing_part: FreeCAD Part object (used for Rectangle and Polynom)
        :return:
        """
        # Since this function can be call to either get data about existing drawing with multiple geometries,
        # OR get data about a single geometry that does not belong to a existing drawing Part (new drawings)
        # this check must be performed to get geometry type:
        if (drawing_part is None) and len(geoms) == 1:
            geometry_type = self.sketch.Geometry[geoms[0]].TypeId
        else:
            geometry_type = drawing_part.Name

        drawing = None

        if ("Line" in geometry_type) and (len(geoms) == 1):
            # Get line geometry by index (single value in "geoms" list)
            line = self.sketch.Geometry[geoms[0]]
            drawing = {
                "shape": "Line",
                "start": toList(line.StartPoint),
                "end": toList(line.EndPoint)
            }

        elif ("Rect" in geometry_type) or ("Poly" in drawing_part.Name):
            # First operation to keep dictionary key orded consistent (so that hash stays the same)
            # Initialize drawing dictionary with correct string
            if "Rect" in drawing_part.Name:
                drawing = {"shape": "Rect"}
            else:
                drawing = {"shape": "Polygon"}

            # Initialise list where points of rectangle or polygon are stored
            points = []
            # Go through all indices in geoms list
            for geom in geoms:
                line = self.sketch.Geometry[geom]
                # Get start and end points of each line in rectangle (or poly)
                start = toList(line.StartPoint)
                end = toList(line.EndPoint)
                # Add points to array if new, so vertices array has unique elements
                if start not in points:
                    points.append(start)
                if end not in points:
                    points.append(end)

            # Swap first and second point because KC starts a shape in top left corner and FC in bottom left corner.
            # KC: 1,2,3,4, FC: 2,1,3,4
            # If not swapped, the hash doesn't match since point order matters
            points[0], points[1] = points[1], points[0]
            # Add points to dictionary
            drawing.update({"points": points})

        elif ("Circle" in geometry_type) and (len(geoms) == 1):
            # Get circle geometry in sketch by index
            circle = self.sketch.Geometry[geoms[0]]
            drawing = {
                "shape": "Circle",
                "center": toList(circle.Center),
                "radius": int(circle.Radius * SCALE)
            }

        elif ("Arc" in geometry_type) and (len(geoms) == 1):
            # Get arc geometry in sketch by index
            arc = self.sketch.Geometry[geoms[0]]
            # Get start and end point
            start = arc.StartPoint
            end = arc.EndPoint
            # Calculate arc middle point
            md = arc.value(arc.parameterAtDistance(arc.length() / 2, arc.FirstParameter))

            # Convert FreeCAD Vector types to list
            start = toList(start)
            end = toList(end)
            md = toList(md)

            # Add points to dictionary
            drawing = {
                "shape": "Arc",
                "points": [
                    start,
                    md,
                    end
                ]
            }


        if drawing:
            #logger_scanner.debug(f"Drawings scanned: {str(drawing)}")
            return drawing


    def getFootprints(self):
        # TODO
        pass

    def getFootprintData(self):
        # TODO
        pass
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
