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
        try:
            FcPcbScanner.updateDiffDict(key="footprints",
                                        value=self.getFootprints(),
                                        diff=self.diff)
        except Exception as e:
            logger_scanner.exception(e)

        logger_scanner.info("Scanner finished")
        self.finished.emit(self.diff)


    @staticmethod
    def updateDiffDict(key: str, value: dict, diff: dict):
        """ Helper function for adding and removing entries from diff dictionary
        Same function as on KC side """
        logger_scanner.debug(f"New diff: {value}")
        changed = value.get("changed")
        added = value.get("added")
        removed = value.get("removed")

        if added:
            logger_scanner.debug(f"Added: {added}")
            # There is no "footprints/drawings" yet in diff, add this key with empty dict as value.
            # This dict will have "changed" key later on
            if diff.get(key) is None:
                diff.update({key: {}})
            # There is no "added" yet in diff, add this key with empty list as value
            if diff[key].get("added") is None:
                diff[key].update({"added": []})

            # Add individual items in list to Diff, so the list doesn't become two-dimensional (added is a list)
            for item in added:
                diff[key]["added"].append(item)
            logger_scanner.debug(f"Updated diff: {diff[key]}")

        if removed:
            logger_scanner.debug(f"Removed: {removed}")
            # There is no "footprints/drawings" yet in diff, add this key with empty dict as value.
            # This dict will have "changed" key later on
            if diff.get(key) is None:
                diff.update({key: {}})
            # There is no "added" yet in diff, add this key with empty list as value
            if diff[key].get("removed") is None:
                diff[key].update({"removed": []})

            # Add individual items in list to Diff, so the list doesn't become two-dimensional (removed is a list)
            for item in removed:
                diff[key]["removed"].append(item)
            logger_scanner.debug(f"Updated diff: {diff[key]}")

        # This function combines new diff with previous items by kiid (example: footprint with old position in diff dict
        # and now has a new position -> override old entry, so it is not updated twice)
        if changed:
            logger_scanner.debug(f"Changed:{changed}")
            # There is no "footprints/drawings" yet in diff, add this key with empty dict as value.
            # This dict will have "changed" key later on
            if diff.get(key) is None:
                diff.update({key: {}})
            # There is no "changes" yet in diff, add this key with empty list as value
            if diff[key].get("changed") is None:
                diff[key].update({"changed": []})

            # Changed is a list of dictionaries
            for entry in changed:
                # Entry is a dictionary of changes if a perticular object: kiid: [changes]
                # First item is kiid, second is list of changes
                # Convert keys to list, so it can be indexed: there is only one key, and that is kiid
                kiid = list(entry.keys())[0]
                changes = list(entry.values())[0]

                # Try to find the same key (kiid) in old diff
                # (see if the same item had a new change - this flattens list of changes to single kiid,
                # so the updater function updates all properties in single run)
                # Index is need for indexing a list of changed objects (cannot be read by kiid since it is a list)
                index_of_kiid = None
                for i, existing_diff_entry in enumerate(diff[key].get("changed")):
                    # Key of dictionary is kiid
                    existing_kiid = list(existing_diff_entry.keys())[0]
                    if kiid == existing_kiid:
                        # Same kiid found in old diff dictionary
                        index_of_kiid = i
                        break

                if index_of_kiid is None:
                    # When walking the list of existing changes, the kiid was not found. This means that kiid is
                    # unique: create a new entry with all current changes
                    diff[key]["changed"].append({kiid: changes})
                else:
                    # Item with same kiid found in old dictionary, new properties must be added OR values must be
                    # overriden
                    # Changes is a dictionary
                    for prop, property_value in changes.items():
                        # Single line:
                        # list(diff[key]["changed"][index_of_kiid].values())[0].update({prop:value})
                        # Written out and explained:
                        # key - drawings, footprint
                        # type - changed, added, removed
                        diffs_list = diff[key]["changed"]
                        # index is needed to get object with same kiid in list of changed objects
                        kiid_diffs = diffs_list[index_of_kiid]
                        # indexing the list returns a single key:value pair dictionary
                        # e.g. {'/4c041385-b7cf-465f-91a3-bb2ce5efff01': {'pos': [116500000, 74000000]}}
                        # where key is kiid string and value is changes dictionary. Get dictionary with .values() method
                        # where index is [0]: this is the first (and only) value
                        kiid_diffs_dictionary = list(kiid_diffs.values())[0]
                        # Update this dictionary by key with new value: this overrides same property with new value,
                        # or adds this property value pair if it doesn't already exist
                        kiid_diffs_dictionary.update({prop: property_value})
                        logger_scanner.debug(f"Updated diff {diff[key]}")


    def getPcbDrawings(self) -> dict:
        added, removed, changed = [], [], []

        # Get FreeCAD drawings_xyzz container part where drawings are stored
        self.drawings_part = self.doc.getObject(f"Drawings_{self.pcb_id}")
        # Break if invalid doc or pcb
        if not (self.sketch and self.drawings_part):
            logger_scanner.error("Breaking (invalid sketch or part)")
            self.finished.emit({})
            return 0

        # Store all geometry tags that have been scanned to this list. Used later for finding new drawings
        scanned_geometries_tags = []
        # Used when adding a new geometry (ID is sequential number, used for adding a unique label to Part object)
        highest_geometry_id = 0
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
            # Store sequential number of drawings
            if drawing_old["ID"] > highest_geometry_id:
                highest_geometry_id = drawing_old["ID"]

            # Get new drawing data
            drawing_new = self.getDrawingData(geoms_indices,
                                              drawing_part=drawing_part)
            if not drawing_new:
                continue

            # Calculate new hash and compare it to hash in old dictionary to see if anything is changed
            drawing_new_hash = hashlib.md5(str(drawing_new).encode("utf-8")).hexdigest()
            if drawing_new_hash == drawing_old["hash"]:
                logger_scanner.debug(f"Same hash for \n{drawing_old}\n{drawing_new}")
                # Skip if no diffs, which is indicated by the same hash (hash in calculated from dictionary)
                continue

            # Add old missing key:value pairs in new dictionary. This is so that new dictionary has all the same keys
            # as old dictionary -> important when comparing all values between old and new in the next step.
            drawing_new.update({"hash": drawing_old["hash"]})
            drawing_new.update({"ID": drawing_old["ID"]})
            drawing_new.update({"kiid": drawing_old["kiid"]})
            logger_scanner.debug(f"Different hash for \n{drawing_old}\n{drawing_new}")
            # Find diffs in dictionaries by comparing all key value pairs
            # (this is why drawing had to be updated beforehand)
            drawing_diffs = {}
            for key, value in drawing_new.items():
                # Check all properties of drawing (keys), if same as in old dictionary -> skip
                if value == drawing_old[key]:
                    continue
                # Add diff to list
                drawing_diffs.update({key: value})
                logger_scanner.debug(f"Found diff: {key}:{value}")
                # Update old dictionary
                drawing_old.update({key: value})

            if drawing_diffs:
                # Hash itself when all changes applied
                drawing_old_hash = hashlib.md5(str(drawing_old).encode("utf-8")).hexdigest()
                drawing_old.update({"hash": drawing_old_hash})
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

            # Check if geomtry tag belongs to a mounting hole footprint - ignore it also in that case
            mounting_holes_tags = []
            # Go top and bottom layers in part containter
            # Get FreeCAD footprints_xyzz containter part where footprints are stored
            footprints_part = self.doc.getObject(f"Footprints_{self.pcb_id}")
            for layer_part in footprints_part.Group:
                # Walk all footprint parts in this layer containter
                for footprint_part in layer_part.Group:
                    # Walk list of childer to find Pads container (there is usually only 1 child)
                    for footprint_child in footprint_part.Group:
                        # Check if container is "Pads_", walk list of pad Objects in Pads containe (only 1 pad)
                        if "Pads" in footprint_child.Name:
                            for pad in footprint_child.Group:
                                # Hole geometry only has one tag, hence index 0
                                mounting_holes_tags.append(pad.Tags[0])

            # If current geometry exist in list of mounting holes, skip this geometry
            # TODO enable mounting hole editing via sketcher?
            if sketch_geom.Tag in mounting_holes_tags:
                continue

            logger_scanner.debug(f"Geometry index: {geometry_index}")
            # Call Function to get new drawing data, argument must be list type
            drawing = self.getDrawingData(geoms=[geometry_index])

            # Hash drawing - used for detecting change when scanning board (id, kiid, hash are excluded from
            # hash calculation)
            drawing_hash = hashlib.md5(str(drawing).encode("utf-8")).hexdigest()
            drawing.update({"hash": drawing_hash})
            # ID for enumarating drawing name in FreeCAD (sequential number for creating a unique part label)
            drawing.update({"ID": highest_geometry_id + 1})
            # Increment this integer, so next geometry added has unique part label
            highest_geometry_id += 1
            # Attach a dummy ID to new drawing (hash to make it unique) This is because objects are identified by
            # m_Uuid, which can only be obtained in KC when creating a new item. After creating a new item in KC,
            # first instance with dummy ID if FC will be deleted, and a new drawing will be added to sketcher
            # with proper ID
            drawing.update({"kiid": f"added-in-fc_{drawing_hash}"})

            self.pcb.get("drawings").append(drawing)

            # ADD NEW SKETCH GEOMETRY AS PART OBJECT IN DRAWINGS CONTAINER - copied from part_updater
            # Create an object to store Tag
            obj = self.doc.addObject("Part::Feature", f"{drawing['shape']}_{self.pcb_id}")
            obj.Label = f"{drawing['ID']}_{drawing['shape']}_{self.pcb_id}"
            # Tag property to store geometry sketch ID (Tag) used for editing sketch geometry
            obj.addProperty("App::PropertyStringList", "Tags", "Sketch")
            obj.Tags = sketch_geom.Tag
            # Add KiCAD ID string (UUID)
            obj.addProperty("App::PropertyString", "KIID", "KiCAD")
            obj.KIID = drawing["kiid"]
            # Hide object and add it to container
            obj.Visibility = False
            # Add scanned drawing to
            drawings_container = self.doc.getObject(f"Drawings_{self.pcb_id}")
            drawings_container.addObject(obj)

            if drawing:
                added.append(drawing)

        # TODO Find deleted drawings?

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


    def getFootprints(self) -> dict:
        removed, changed = [], []
        logger_scanner.debug("Scannning footprints")

        # Get FreeCAD footprints_xyzz containter part where footprints are stored
        self.footprints_part = self.doc.getObject(f"Footprints_{self.pcb_id}")
        # Break if invalid doc or pcb
        if not (self.sketch and self.footprints_part):
            logger_scanner.error("Braking (invalid sketch or part)")
            self.finished.emit({})
            return 0

        # Go top and bottom layers in part containter
        for layer_part in self.footprints_part.Group:
            # Walk all footprint parts in this layer containter
            for footprint_part in layer_part.Group:
                # Get old dictionary entry to be edited (by KIID)
                footprint_old = getDictEntryByKIID(list=self.pcb["footprints"],
                                                   kiid=footprint_part.KIID)

                # Get new footprint data
                footprint_new = self.getFootprintData(footprint_old=footprint_old,
                                                      footprint_part=footprint_part,
                                                      pcb_thickness=self.pcb.get("general").get("thickness"))
                if not footprint_new:
                    continue

                # Calculate new hash and compare it to hash in old dictionary to see of anything is changed
                footprint_new_hash = hashlib.md5(str(footprint_new).encode("utf-8")).hexdigest()
                if footprint_new_hash == footprint_old["hash"]:
                    # Skip if no diff, which is indicated by the same hash (hash is calculated from dictionary)
                    continue

                # Add old misisng key:value pairs in new dictionary. This is so that new dictionary has all the same
                # keys as old dictionary -> important when comaparing allvalues between old and new in the next step
                footprint_new.update({"id": footprint_old["id"]})
                footprint_new.update({"hash": footprint_old["hash"]})
                footprint_new.update({"ID": footprint_old["ID"]})
                footprint_new.update({"kiid": footprint_old["kiid"]})

                # Find diffs in dictionaries by comparing all key value paris
                # (this is why footprint had to be updated befohand)
                footprint_diffs = {}
                for key, value in footprint_new.items():
                    # Check all properties of footprint (keys), if same as in old dictionary -> skip
                    if value == footprint_old[key]:
                        continue
                    # Add diff to list
                    footprint_diffs.update({key: value})
                    # Update old dictionary
                    footprint_old.update({key: value})

                if footprint_diffs:
                    # Hash itself when all changes applied
                    footprint_old_hash = hashlib.md5(str(footprint_old).encode("utf-8")).hexdigest()
                    footprint_old.update({"hash": footprint_old_hash})
                    # Append dictionary with ID and list of changes to list of changed footprints
                    changed.append({footprint_old["kiid"]: footprint_diffs})

        # TODO Removed?

        result = {}
        if changed:
            result.update({"changed": changed})
            logger_scanner.info(f"Found changed footprint: {str(changed)}")
        if removed:
            result.update({"removed": removed})
            logger_scanner.info(f"Found removed footprint: {str(removed)}")

        logger_scanner.debug("Footprints finished.")
        return result


    def getDrawingData(self, geoms: list, drawing_part:dict = None) -> dict:
        """
        Get dictionary with drawing data
        :param geoms: list of indexes of geometry (which form a drawing) in sketch
        :param drawing_part: dict FreeCAD Part object (used for Rectangle and Polynom)
        :return:
        """
        # Since this function can be call to either get data about existing drawing with multiple geometries,
        # OR get data about a single geometry that does not belong to an existing drawing Part (new drawings)
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

        elif ("Rect" in geometry_type) or ("Poly" in geometry_type):
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

        elif ("Arc" in geometry_type) and (len(geoms) == 1):
            # Get arc geometry in sketch by index
            arc = self.sketch.Geometry[geoms[0]]
            # Get start and end point
            start = arc.StartPoint
            end = arc.EndPoint
            # Calculate arc middle point - use .parameterAtDistance method
            # https://forum.freecad.org/viewtopic.php?t=31933
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

        elif ("Circle" in geometry_type) and (len(geoms) == 1):
            # Get circle geometry in sketch by index
            circle = self.sketch.Geometry[geoms[0]]
            drawing = {
                "shape": "Circle",
                "center": toList(circle.Center),
                "radius": int(circle.Radius * SCALE)
            }

        if drawing:
            logger_scanner.debug(f"Drawing scanned: {str(drawing)}")
            return drawing


    @staticmethod
    def getFootprintData(footprint_old: dict, footprint_part, pcb_thickness:int = 1600000) -> dict:
        """Return dictionary with footprint information. Returns also data about models, where -z offset and
        180deg rotation (as a result of importing model on bottom layer) are ignored"""

        footprint = None
        pcb_thickness /= SCALE
        # Get footprint properties
        reference = footprint_part.Reference
        # Convert from vector to list
        position = toList(footprint_part.Placement.Base)
        # Convert radians to degrees
        fp_rotation = math.degrees(footprint_part.Placement.Rotation.Angle)
        # Convert FC unit circle degrees to KC model (0->360 to 0->180 OR 0->-180)
        if fp_rotation > 180.0:
            fp_rotation -= 360.0

        # Get layer info based on which container the footprint part is located
        # Parents is list of tuples: (type, name)
        # First index is first tuple in list, second index is second element in tuple (name)
        if "Bot" in footprint_part.Parents[0][1]:
            layer = "Bot"
        else:
            layer = "Top"

        models = []
        # Childer of footprints group are models AND pads
        for child in footprint_part.Group:

            # Check type, skip if child is Pads container, otherwise child if a 3D model objects
            if "Pads" in child.Name:
                continue

            model = child
            # Parse id from model label (000, 001,...)
            model_id = model.Label.split("_")[2]
            filename = model.Filename
            # toList helper function not called because offset is in mm and y is not flipped (in KiCAD, which is
            # reference for dictionary data model)
            offset = [
                model.Placement.Base[0],
                model.Placement.Base[1],
                model.Placement.Base[2]
            ]
            # Get old model data from dictionary by model ID
            model_old = getModelById(list=footprint_old["3d_models"],
                                     model_id=model_id)
            if not model_old:
                continue

            # Take old values (we assume user will not change the scale of model)
            scale = model_old["scale"]
            # Update rotation only in z axis
            model_rotation = [
                model_old["rot"][0],
                model_old["rot"][1],
                math.degrees(model.Placement.Rotation.Angle)
            ]

            # Ignore -board_thickness z offset and rotation if layer is bot
            # Model was rotated and displaced based on layer when importing it
            if layer == "Bot":
                offset[2] += pcb_thickness
                model_rotation[2] -= 180.0

            # Create a datamodel with model information
            model_new = {
                "model_id": model_id,
                "filename": filename,
                "offset": offset,
                "scale": scale,
                "rot": model_rotation
            }
            models.append(model_new)

        # # If modes is and empty list, replace it if None (null) so that empty list doesn't appear as updated value
        # if models == []:
        #     modes = None

        # Write data to dictionary model
        footprint = {
            "ref": reference,
            "pos": position,
            "rot": fp_rotation,
            "layer": layer,
            "3d_models": models
        }

        if footprint:
            logger_scanner.debug(f"Footprint scanned: {str(footprint)}")
            return footprint

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
