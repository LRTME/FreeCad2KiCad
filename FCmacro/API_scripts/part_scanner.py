"""
Module contains PartScanner class which is run in a separate thread. When finished, emits Diff dictionary via signal.
"""
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

# Get parent directory, so that ConfigLoader can be imported from config_loader module
parent_directory = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(parent_directory)

from Config.config_loader import ConfigLoader

# Initialize logger
logger_scanner = logging.getLogger("scanner")


# noinspection PyAttributeOutsideInit
class FcPartScanner:
    """
    Get data from FreeCAD Part object
    :param doc: FreeCAD document object
    :param pcb: pcb dictionary to compare new data to
    :param diff: diff dictionary to store new data to
    :return:
    """

    def __init__(self, doc, pcb, diff, config, progress_bar):
        super().__init__()
        self.doc = doc
        self.pcb = pcb
        self.config = config
        self.progress_bar = progress_bar
        # Take diff dictionary (existing or empty) to be updated
        self.diff = diff
        self.pcb_id = self.pcb["general"]["pcb_id"]
        self.sketch = doc.getObject(f"Board_Sketch_{self.pcb_id}")

    def run(self):
        """ Main method which is called when thread is started. """
        logger_scanner.info("Scanner started")

        try:
            # Update existing diff dictionary with new value
            FcPartScanner.update_diff_dict(key="drawings",
                                           value=self.get_pcb_drawings(),
                                           diff=self.diff)
            FcPartScanner.update_diff_dict(key="footprints",
                                           value=self.get_footprints(),
                                           diff=self.diff)
        except Exception as e:
            logger_scanner.exception(e)
            return 1

        logger_scanner.info(f"Scanner finished {self.diff}")
        return self.diff

    @staticmethod
    def update_diff_dict(key: str, value: dict, diff: dict):
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
                # Entry is a dictionary of changes if a particular object: kiid: [changes]
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
                    # overridden
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

    def get_pcb_drawings(self) -> dict:
        """ Scan drawings in sketch. """
        added, removed, changed = [], [], []

        # Get FreeCAD drawings_xyzz container part where drawings are stored
        self.drawings_part = self.doc.getObject(f"Drawings_{self.pcb_id}")
        # Break if invalid doc or pcb
        if not (self.sketch and self.drawings_part):
            logger_scanner.error("Breaking (invalid sketch or part)")
            return {}

        # Set up progress bar
        self.progress_bar.setRange(0, len(self.drawings_part.Group))
        self.progress_bar.show()
        # Store all geometry tags that have been scanned to this list. Used later for finding new drawings
        scanned_geometries_tags = []
        # Used when adding a new geometry (ID is sequential number, used for adding a unique label to Part object)
        highest_geometry_id = 0
        # Go through drawings in part container and find corresponding geometry in sketch
        for i, drawing_part in enumerate(self.drawings_part.Group):
            # Update progress bar
            self.progress_bar.setValue(i)
            self.progress_bar.setFormat("Scanning drawings: %p%")

            # Get indexes of all elements in sketch which are part of drawing (lines of rectangle, etc.)
            geoms_indices = get_geoms_by_tags(sketch=self.sketch,
                                              tags=drawing_part.Tags)
            # Store geometry tags to a list. This tracks which sketch geometries have been scanned (used for finding new
            # drawings later)
            scanned_geometries_tags.append(drawing_part.Tags)

            # Get old dictionary entry to be edited (by KIID)
            drawing = get_dict_entry_by_kiid(list_of_entries=self.pcb["drawings"],
                                             kiid=drawing_part.KIID)
            # Store sequential number of drawings
            if drawing["ID"] > highest_geometry_id:
                highest_geometry_id = drawing["ID"]

            # Get new drawing data
            drawing_new = self.get_drawing_data(geoms_indices, drawing_part=drawing_part)
            if not drawing_new:
                continue

            # Calculate new hash and compare it to hash in old dictionary to see if anything is changed
            drawing_new_hash = hashlib.md5(str(drawing_new).encode()).hexdigest()
            if drawing_new_hash == drawing["hash"]:
                logger_scanner.debug(f"Same hash for \n{drawing}\n{drawing_new}")
                # Skip if no diffs, which is indicated by the same hash (hash in calculated from dictionary)
                continue

            # Add old missing key:value pairs in new dictionary. This is so that new dictionary has all the same keys
            # as old dictionary -> important when comparing all values between old and new in the next step.
            drawing_new.update({"hash": drawing["hash"]})
            drawing_new.update({"ID": drawing["ID"]})
            drawing_new.update({"kiid": drawing["kiid"]})
            logger_scanner.debug(f"Different hash for \n{drawing}\n{drawing_new}")
            # Find diffs in dictionaries by comparing all key value pairs
            # (this is why drawing had to be updated beforehand)
            drawing_diffs = {}
            for key, value in drawing_new.items():
                # Check all properties of drawing (keys), if same as in old dictionary -> skip
                if value == drawing[key]:
                    continue
                # Add diff to list
                drawing_diffs.update({key: value})
                logger_scanner.debug(f"Found diff: {key}:{value}")
                # Update old dictionary
                drawing.update({key: value})

            if drawing_diffs:
                # Hash itself when all changes applied
                drawing_old_hash = hashlib.md5(str(drawing).encode()).hexdigest()
                drawing.update({"hash": drawing_old_hash})
                # Append dictionary with ID and list of changes to list of changed drawings
                changed.append({drawing["kiid"]: drawing_diffs})
        self.progress_bar.reset()
        self.progress_bar.hide()

        # Find new drawings (rectangles and polynomials are treated as lines)
        # Flatten 2D list to 1D list. 2D list can exist because a single drawing part (rectangle, polynom) can append
        # a list of line geometries
        scanned_geometries_tags = list(itertools.chain.from_iterable(scanned_geometries_tags))
        # Walk all the geometries in sketch:
        for geometry_index, sketch_geom in enumerate(self.sketch.Geometry):
            # If current geometry exists in list of scanned geometries, skip this geometry
            if sketch_geom.Tag in scanned_geometries_tags:
                continue

            # Check if geometry tag belongs to a mounting hole footprint - ignore it also in that case
            mounting_holes_tags = []
            # Go top and bottom layers in part container
            # Get FreeCAD footprints_xyzz container part where footprints are stored
            footprints_part = self.doc.getObject(f"Footprints_{self.pcb_id}")
            for layer_part in footprints_part.Group:
                # Walk all footprint parts in this layer container
                for footprint_part in layer_part.Group:
                    # Walk list of children to find Pads container (there is usually only 1 child)
                    for footprint_child in footprint_part.Group:
                        # Check if container is "Pads_", walk list of pad Objects in Pads container (only 1 pad)
                        if "Pads" in footprint_child.Name:
                            for pad in footprint_child.Group:
                                # Hole geometry only has one tag, hence index 0
                                mounting_holes_tags.append(pad.Tags[0])

            # If current geometry exist in list of mounting holes, skip this geometry (mounting holes are footprint not
            # drawings)
            if sketch_geom.Tag in mounting_holes_tags:
                continue

            logger_scanner.debug(f"Geometry index: {geometry_index}")
            # Call Function to get new drawing data, argument must be list type
            drawing = self.get_drawing_data(geoms=[geometry_index])

            # Hash drawing - used for detecting change when scanning board (id, kiid, hash are excluded from
            # hash calculation)
            drawing_hash = hashlib.md5(str(drawing).encode()).hexdigest()
            drawing.update({"hash": drawing_hash})
            # ID for enumerating drawing name in FreeCAD (sequential number for creating a unique part label)
            drawing.update({"ID": highest_geometry_id + 1})
            # Increment this integer, so next geometry added has unique part label
            highest_geometry_id += 1
            # Attach a dummy ID to new drawing (hash to make it unique) This is because objects are identified by
            # m_Uuid, which can only be obtained in KC when creating a new item. After creating a new item in KC,
            # first instance with dummy ID if FC will be deleted, and a new drawing will be added to sketcher
            # with proper ID
            drawing.update({"kiid": f"added-in-fc_{drawing_hash}"})

            # If null, define value # todo change to dict if data model changes
            if not self.pcb.get("drawings"):
                self.pcb.update({"drawings": []})

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
            # Add scanned drawing to container
            drawings_container = self.doc.getObject(f"Drawings_{self.pcb_id}")
            drawings_container.addObject(obj)

            if drawing:
                added.append(drawing)
        
        # Go through existing list of drawings in data model
        for drawing in self.pcb["drawings"]:
            # Get Part object from document by KIID
            drawing_part = get_part_by_kiid(self.doc, drawing.get("kiid"))
            # Get geometry from sketch by Tag, which is attribute of Part object
            geom_tag = drawing_part.Tags
            # Returns list if geometry with Tag exists in sketch, skip this iteration
            if get_geoms_by_tags(self.sketch, geom_tag):
                continue
            # No matches in board: drawings has been removed from board
            # Add UUID of deleted drawing to removed list
            removed.append(drawing.get("kiid"))
            # Delete drawing from pcb dictionary
            self.pcb.get("drawings").remove(drawing)
            #  Delete drawing part from FreeCAD document
            self.doc.removeObject(drawing_part.Name)

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

    def get_footprints(self) -> dict:
        """ Scan footprint Parts. """

        removed, changed = [], []
        logger_scanner.debug("Scanning footprints")

        # Get FreeCAD footprints_xyzz container part where footprints are stored
        self.footprints_part = self.doc.getObject(f"Footprints_{self.pcb_id}")
        # Break if invalid doc or pcb
        if not (self.sketch and self.footprints_part):
            logger_scanner.error("Braking (invalid sketch or part)")
            self.finished.emit({})
            return {}

        # Go through top and bottom layers in part container
        for layer_part in self.footprints_part.Group:
            # Set up progress bar
            self.progress_bar.setRange(0, len(layer_part.Group))
            self.progress_bar.show()
            # Walk all footprint parts in this layer container
            for i, footprint_part in enumerate(layer_part.Group):
                # Update progress bar
                self.progress_bar.setValue(i)
                self.progress_bar.setFormat("Scanning footprints: %p%")

                # Get old dictionary entry to be edited (by KIID)
                footprint_old = get_dict_entry_by_kiid(list_of_entries=self.pcb["footprints"],
                                                       kiid=footprint_part.KIID)

                # Get new footprint data
                footprint_new = self.get_footprint_data(footprint_old=footprint_old,
                                                        footprint_part=footprint_part,
                                                        pcb_thickness=self.pcb.get("general").get("thickness"))
                if not footprint_new:
                    continue

                # Calculate new hash and compare it to hash in old dictionary to see of anything is changed
                footprint_new_hash = hashlib.md5(str(footprint_new).encode()).hexdigest()
                if footprint_new_hash == footprint_old["hash"]:
                    # Skip if no diff, which is indicated by the same hash (hash is calculated from dictionary)
                    continue

                # Add old missing key:value pairs in new dictionary. This is so that new dictionary has all the same
                # keys as old dictionary -> important when comparing all values between old and new in the next step
                footprint_new.update({"id": footprint_old["id"]})
                footprint_new.update({"hash": footprint_old["hash"]})
                footprint_new.update({"ID": footprint_old["ID"]})
                footprint_new.update({"kiid": footprint_old["kiid"]})

                # Find diffs in dictionaries by comparing all key value paris
                # (this is why footprint had to be updated beforehand)
                footprint_diffs = {}
                for key, value in footprint_new.items():
                    # Check all properties of footprint (keys), if same as in old dictionary -> skip
                    if value == footprint_old[key]:
                        continue

                    # Special case for rotation (numerical error when converting rad to deg)
                    if key == "rot" and (abs(value - footprint_old.get("rot")) <= self.config.deg_to_rad_tolerance):
                        continue

                    # Numerical error when getting position: check if both components inside tolerance
                    if (key == "pos"
                            and (abs(value[0] - footprint_old.get("pos")[0]) <= self.config.placement_tolerance)
                            and (abs(value[1] - footprint_old.get("pos")[1]) <= self.config.placement_tolerance)):
                        continue

                    # Add diff to list
                    footprint_diffs.update({key: value})
                    # Update old dictionary
                    footprint_old.update({key: value})

                if footprint_diffs:
                    # Hash itself when all changes applied
                    footprint_old_hash = hashlib.md5(str(footprint_old).encode()).hexdigest()
                    footprint_old.update({"hash": footprint_old_hash})
                    # Append dictionary with ID and list of changes to list of changed footprints
                    changed.append({footprint_old["kiid"]: footprint_diffs})

            self.progress_bar.reset()
            self.progress_bar.hide()

        result = {}
        if changed:
            result.update({"changed": changed})
            logger_scanner.info(f"Found changed footprint: {str(changed)}")
        if removed:
            result.update({"removed": removed})
            logger_scanner.info(f"Found removed footprint: {str(removed)}")

        logger_scanner.debug("Footprints finished.")
        return result

    def get_drawing_data(self, geoms: list, drawing_part: dict = None) -> dict:
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
                "start": to_list(line.StartPoint),
                "end": to_list(line.EndPoint)
            }

        elif ("Rect" in geometry_type) or ("Poly" in geometry_type):
            # First operation to keep dictionary key order consistent (so that hash stays the same)
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
                start = to_list(line.StartPoint)
                end = to_list(line.EndPoint)
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
            start = to_list(start)
            end = to_list(end)
            md = to_list(md)

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
                "center": to_list(circle.Center),
                "radius": int(circle.Radius * SCALE)
            }

        if drawing:
            logger_scanner.debug(f"Drawing scanned: {str(drawing)}")
            return drawing

    # noinspection GrazieInspection
    def get_footprint_data(self, footprint_old: dict, footprint_part, pcb_thickness: int = 1600000) -> dict:
        """
        Return dictionary with footprint information. Returns also data about models, where -z offset and
        180deg rotation (as a result of importing model on bottom layer) are ignored. If model offset is set,
        footprint base is moved by offset, and model offset is reset to previous value.
        If footprint has a thru-hole (MountingHole footprint) and that hole geometry is moved in sketch,
        corresponding footprint is marked as moved
        """

        pcb_thickness /= SCALE
        # Get footprint properties
        reference = footprint_part.Reference
        # Convert from vector to list
        position = to_list(footprint_part.Placement.Base)
        # Numerical error happens during conversion - handled when comparing new and old values
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
        # Variable for storing old model data - used if there is only one model to apply model offset as footprint
        # position change
        model_old = None
        # Children of footprints group are models AND pads
        for child in footprint_part.Group:
            # Check type, skip if child is Pads container, otherwise child if a 3D model objects
            if "Pads" in child.Name:
                continue
            model = child
            # Parse id from model label (000, 001,...)
            model_id = model.Label.split("_")[2]
            filename = model.Filename
            # to_list helper function not called because offset is in mm and y is not flipped (in KiCAD, which is
            # reference for dictionary data model)
            offset = [
                model.Placement.Base[0],
                model.Placement.Base[1],
                model.Placement.Base[2]
            ]
            # Get old model data from dictionary by model ID
            model_old = get_model_by_id(list_of_models=footprint_old["3d_models"],
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

            # Create a data-model with model information
            model_new = {
                "model_id": model_id,
                "filename": filename,
                "absolute_path": model_old.get("absolute_path"),  # Copy over absolute path to keep data model same
                "offset": offset,
                "scale": scale,
                "rot": model_rotation
            }
            models.append(model_new)

        # --------------- Check if model was moved instead of footprint ---------------
        # presume user meant to move footprint, not offset model
        # If footprint has single model: if model has offset or rotation: reset these values to previous
        #  and apply offset on rotation of model to actual footprint part. If user moves a model, probably intention
        #  was to move the footprint, not model offset
        if len(models) == 1 and model_old:
            model = models[0]
            # Check if model was moved by user - maybe offset existed before, so subtract it from new value
            model_offset = [(v1 - v2) for v1, v2 in zip(model["offset"], model_old["offset"])]
            if model_offset != [0, 0, 0]:
                logger_scanner.debug(f"fp position: {position}")
                logger_scanner.debug(f"model offset: {model_offset}")
                # Model offset is list type, units are millimeters, transform to integer list in nanometers
                transformed_offset = [int(value * SCALE) for value in model_offset]
                # Element-wise addition of footprint part object base placement and model relative placement
                new_footprint_position = [(base + offset) for base, offset in zip(position, transformed_offset)]
                logger_scanner.debug(f"new fp position: {new_footprint_position}")

                # Reset model offset to old value
                model["offset"] = model_old["offset"]
                # Move model to old value:
                # First get object as child of footprint object
                for child in footprint_part.Group:
                    # Check type, skip if child is Pads container, otherwise child if a 3D model objects
                    if "Pads" in child.Name:
                        continue
                    # We know first  child that is not a Pad is as 3D model (fp has single model)
                    model_part = child
                    # Set placement as FC vector
                    model_part.Placement.Base = App.Vector(
                        model_old["offset"][0],
                        model_old["offset"][1],
                        model_old["offset"][2]
                    )
                    logger_scanner.debug(f"Moved model part back to {model_part.Placement.Base}")
                # Move footprint to new position
                footprint_part.Placement.Base = freecad_vector(new_footprint_position)
                logger_scanner.debug(f"Moved footprint part back to {footprint_part.Placement.Base}")
                # Set new position -> override scanned value so that diff is recognised
                position = new_footprint_position
        else:
            logger_scanner.debug(f"Multiple models or not model_old data for {footprint_old}")

        # --------------- Check if single pad footprint was moved in sketch (mounting hole) ---------------
        # Children of footprints group are models AND pads
        for child in footprint_part.Group:
            try:
                # Check type of child
                if "Pads" not in child.Name:
                    continue
                # Only works for footprints with single hole!
                # Get first (and only) child of Pads container: this is pad Part
                pad_part = child.Group[0]
                # Get corresponding pad in dictionary to be edited
                pad = get_dict_entry_by_kiid(footprint_old["pads_pth"], pad_part.KIID)
                # Get sketch geometry by Tag
                geom_index = get_geoms_by_tags(sketch=self.sketch,
                                               tags=pad_part.Tags)[0]
                # Get geometry object by index
                pad_geom = self.sketch.Geometry[geom_index]
                # Check if valid values:
                if not pad and not pad_geom:
                    continue
                logger_scanner.debug(f"Footprint {footprint_part} has through hole")
                logger_scanner.debug(f"pad: {pad}")
                logger_scanner.debug(f"pad_geom {pad_geom}")
                # Check if pad was moved in sketch by user:
                # Get sketch geometry position
                new_footprint_position = pad_geom.Center
                # Compare geometry position with pad object position, if not same: sketch has been edited
                if new_footprint_position != pad_part.Placement.Base:
                    # Move footprint to new position
                    footprint_part.Placement.Base = new_footprint_position
                    # Change position variable that will be added to footprint dictionary
                    position = to_list(new_footprint_position)
            except Exception as e:
                logger_scanner.exception(e)

        # --------------- Write data to dictionary model ---------------
        footprint = {
            "ref": reference,
            "pos": position,
            "rot": fp_rotation,
            "layer": layer,
            "3d_models": models
        }

        # Check if models list is empty: happens if 3d models failed to import
        # In this case copy over old data to keep sync
        if not models:
            footprint.update({"3d_models": footprint_old.get("3d_models")})

        # Return dictionary
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
    #         footprint = get_dict_entry_by_kiid(footprint_list, fp_part.KIID)
    #         # Skip if failed to get footprint in dictionary
    #         if not footprint:
    #             continue
    #
    #
    #         # Update dictionary entry with new position coordinates
    #         footprint.update({"pos": to_list(fp_part.Placement.Base)})
    #
    #         # Model changes in FC are ignored (no KIID)
    #
    #         # Get FC container Part where pad objects are stored
    #         pads_part = get_pad_container(fp_part)
    #         # Check if gotten pads part
    #         if not pads_part:
    #             continue
    #
    #         # Go through pads
    #         for pad_part in pads_part.Group:
    #             # Get corresponding pad in dictionary to be edited
    #             pad = get_dict_entry_by_kiid(footprint["pads_pth"], pad_part.KIID)
    #             # Get sketch geometry by Tag:
    #             # first get index (single entry in list) of pad geometry in sketch
    #             geom_index = get_geoms_by_tags(sketch, pad_part.Tags)[0]
    #             # get geometry by index
    #             pad_geom = sketch.Geometry[geom_index]
    #             # Check if gotten dict entry and sketch geometry
    #             if not pad and not pad_geom:
    #                 continue
    #
    #
    #             # ----- If pad position delta was edited as vector attribute by user:  -----------
    #             # Compare dictionary deltas to property deltas
    #             if pad["pos_delta"] != to_list(pad_part.PosDelta):
    #                 # Update dictionary with new deltas
    #                 pad.update({"pos_delta": to_list(pad_part.PosDelta)})
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
    #                     footprint.update({"pos": to_list(new_base)})
    #
    #             # Update pad absolute placement property for all pads
    #             pad_part.Placement.Base = pad_geom.Center
