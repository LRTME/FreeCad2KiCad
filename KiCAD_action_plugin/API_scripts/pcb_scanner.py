"""
    This module consists only of static methods and represents the collection of KiCAD API scripts
    that return either pcb of diff dictionary data model.
"""
import hashlib
import logging
import os
import random

from API_scripts.utils import getDictEntryByKIID, relativeModelPath

# Initialize logger
logger = logging.getLogger("SCANNER")


class PcbScanner:

    @staticmethod
    def getDiff(brd, pcb, diff):
        PcbScanner.updateDiffDict(key="footprints",
                                  value=PcbScanner.getFootprints(brd, pcb),
                                  diff=diff)
        PcbScanner.updateDiffDict(key="drawings",
                                  value=PcbScanner.getPcbDrawings(brd, pcb),
                                  diff=diff)
        # PcbScanner.updateDiffDict(key="vias",
        #                           value=PcbScanner.getVias(brd, pcb),
        #                           diff=diff)
        return diff


    @staticmethod
    def updateDiffDict(key, value, diff):
        """Helper function for adding and removing entries from diff dictionary"""
        logger.debug(f"New diff: {value}")
        changed = value.get("changed")
        added = value.get("added")
        removed = value.get("removed")

        if added:
            logger.debug(f"Added: {added}")
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
            logger.debug(f"Updated diff: {diff[key]}")


        if removed:
            logger.debug(f"Removed: {removed}")
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
            logger.debug(f"Updated diff: {diff[key]}")


        # This function combines new diff with previous items by kiid (example: footprint with old position in diff dict
        # and now has a new position -> override old entry, so it is not updated twice)
        if changed:
            logger.debug(f"Changed:{changed}")
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
                        logger.debug(f"Updated diff {diff[key]}")


    @staticmethod
    def getPcb(brd, pcb=None):
        """
        Create a dictionary with PCB elements and properties
        :param pcb: dict
        :param brd: pcbnew.Board object
        :return: dict
        """

        # List for creating random tailpiece (4 charecters after name) so that multiple instances of same pcb can be
        # opened at once in FreeCAD
        rand_pool = [[i for i in range(10)], "abcdefghiopqruwxyz"]
        random_id_list = [random.choice(rand_pool[1]) for _ in range(2)] + \
                         [random.choice(rand_pool[0]) for _ in range(2)]

        try:
            # Parse file path to get file name / pcb ID
            # TODO check if file extension is different of different KC versions
            # file extension dependant on KC version?
            file_name = brd.GetFileName()
            pcb_id = file_name.split('.')[0].split('/')[-1]
        except Exception as e:
            # fatal error?
            pcb_id = "Unknown"
            print(e)

        # General data for Pcb dictionary
        general_data = {"pcb_name": pcb_id,
                        "pcb_id": "".join(str(char) for char in random_id_list),
                        "thickness": brd.GetDesignSettings().GetBoardThickness()}

        # TODO what if there is no "added" in dictionary?
        # Pcb dictionary
        pcb = {"general": general_data,
               "drawings": PcbScanner.getPcbDrawings(brd, pcb).get("added"),
               "footprints": PcbScanner.getFootprints(brd, pcb).get("added"),
               #"vias": PcbScanner.getVias(brd, pcb)["added"]
               }

        return pcb


    @staticmethod
    def getPcbDrawings(brd, pcb):
        """
        Returns three keyword dictionary: added - changed - removed
        If drawings is changed, pcb dictionary gets automatically updated
        :param pcb: dict
        :param brd: pcbnew.Board object
        :return: dict
        """

        added = []
        removed = []
        changed = []

        try:
            # Add all drw IDs to list, to find out if drw is new, or it already exists in pcb dictionary
            list_of_ids = [d["kiid"] for d in pcb["drawings"]]
            latest_nr = pcb["drawings"][-1]["ID"]
        except TypeError:
            # No drawings in pcb dictionary: scanning drws for the first time
            latest_nr = 0
            list_of_ids = []


        # Go through drawings
        drawings = brd.GetDrawings()
        for i, drw in enumerate(drawings):
            # Get drawings in edge layer
            if drw.GetLayerName() == "Edge.Cuts":

                # if drawing kiid is not in pcb dictionary, it's a new drawing
                if drw.m_Uuid.AsString() not in list_of_ids:

                    # Get data
                    drawing = PcbScanner.getDrawingsData(drw)
                    # Hash drawing - used for detecting change when scanning board
                    drawing_hash = hashlib.md5(str(drawing).encode('utf-8')).hexdigest()
                    drawing.update({"hash": drawing_hash})
                    # ID for enumarating drawing name in FreeCAD
                    drawing.update({"ID": (latest_nr + i + 1)})
                    # KIID for cross-referencing drawings inside KiCAD
                    drawing.update({"kiid": drw.m_Uuid.AsString()})
                    # Add dict to list
                    added.append(drawing)
                    # Add drawing to pcb dictionary
                    if pcb:
                        pcb["drawings"].append(drawing)

                # known kiid, drw has already been added, check for diff
                else:
                    # Get old dictionary entry to be edited (by KIID):
                    drawing_old = getDictEntryByKIID(list=pcb["drawings"],
                                                     kiid=drw.m_Uuid.AsString())
                    # Get new drawing data
                    drawing_new = PcbScanner.getDrawingsData(drw)

                    # Calculate new hash and compare it to hash in old dictionary
                    # to see if anything is changed
                    drawing_new_hash = hashlib.md5(str(drawing_new).encode('utf-8')).hexdigest()
                    if drawing_new_hash == drawing_old["hash"]:
                        # Skip if no diffs, which is indicated by the same hash (hash in calculated from dictionary)
                        continue

                    drawing_diffs = {}
                    for key, value in drawing_new.items():
                        # Check all properties of drawing (keys), if same as in old dictionary -> skip
                        if value == drawing_old[key]:
                            continue
                        # Add diff to dictionary
                        drawing_diffs.update({key: value})
                        logger.debug(drawing_diffs)
                        # Update old dictionary
                        drawing_old.update({key: value})

                    if drawing_diffs:
                        # Hash itself with updated values
                        drawing_old_hash = hashlib.md5(str(drawing_old).encode('utf-8')).hexdigest()
                        drawing_old.update({"hash": drawing_old_hash})
                        # Append dictionary with ID and list of changes to list of changed drawings
                        changed.append({drawing_old["kiid"]: drawing_diffs})


        # Find deleted drawings
        if type(pcb) is dict:
            # Go through existing list of drawings (dictionary)
            for drawing_old in pcb["drawings"]:
                found_match = False

                # Go through DRWSs in board:
                for drw in drawings:
                    # Find corresponding drawing in old dict based on UUID
                    if drw.m_Uuid.AsString() == drawing_old["kiid"]:
                        found_match = True

                # No matches in board: drawings has been removed from board, add to removed, delete from pcb dict
                if not found_match:
                    # Add UUID of deleted drawing to removed list
                    removed.append(drawing_old["kiid"])
                    # Delete drawing from pcb dictonary
                    pcb["drawings"].remove(drawing_old)


        result = {}
        if added:
            result.update({"added": added})
        if changed:
            result.update({"changed": changed})
        if removed:
            result.update({"removed": removed})

        return result


    @staticmethod
    def getFootprints(brd, pcb):
        """
        Returns three keyword dictionary: added - changed - removed
        If fp is changed, pcb dictionary gets automatically updated
        :param pcb: dict
        :param brd: pcbnew.Board object
        :return: dict
        """

        added, removed, changed = [], [], []

        try:
            # Add all fp IDs to list, to find out if fp is new, or it already exists in pcb dictionary
            latest_nr = pcb["footprints"][-1]["ID"]
            list_of_ids = [f["kiid"] for f in pcb["footprints"]]
        except TypeError:
            # No footprints in pcb dictionary: scanning fps for the first time
            latest_nr = 0
            list_of_ids = []

        # Go through footprints
        footprints = brd.GetFootprints()
        for i, fp in enumerate(footprints):
            # # if footprints kiid is not in pcb dictionary, it's a new footprint
            # if fp.GetPath().AsString() not in list_of_ids:
            fp_id = fp.m_Uuid.AsString()
            if fp_id not in list_of_ids:

                # Get FP data
                footprint = PcbScanner.getFpData(fp)
                # Hash footprint - used for detecting change when scanning board
                footprint_hash = hashlib.md5(str(footprint).encode('utf-8')).hexdigest()
                footprint.update({"hash": footprint_hash})
                footprint.update({"ID": (latest_nr + i + 1)})
                # # If fp is a mouting hole, use Uuid intead
                # if "Mount" in fp.GetFPIDAsString():
                #     footprint.update({"kiid": fp.m_Uuid.AsString()})
                # else:
                #     footprint.update({"kiid": fp.GetPath().AsString()})
                # Use Uuid as unique ID, because mouting hole footprints have no .GetPath()? # TODO
                footprint.update({"kiid": fp_id})

                # Add dict to list
                added.append(footprint)
                # Add footprint to pcb dictionary
                if pcb:
                    pcb["footprints"].append(footprint)

                logger.debug(f"New footprint: {footprint}")

            # known kiid, fp has already been added, check for diff
            else:
                # # Get old dictionary entry to be edited:
                # footprint_old = getDictEntryByKIID(list=pcb["footprints"],
                #                                    kiid=fp.GetPath().AsString())
                # Use Uuid as unique ID, because mouting hole footprints have no .GetPath()? # TODO
                footprint_old = getDictEntryByKIID(list=pcb["footprints"],
                                                   kiid=fp_id)
                # Get new data of footprint
                footprint_new = PcbScanner.getFpData(fp)

                # Calculate new hash and compare it to hash in old dictionary
                # to see if anything is changed
                footprint_new_hash = hashlib.md5(str(footprint_new).encode("utf-8")).hexdigest()
                if footprint_new_hash == footprint_old["hash"]:
                    # Skip if no diffs, which is indicated by the same hash (hash in calculated from dictionary)
                    continue

                fp_diffs = {}
                # Start of main diff loop (compare values of all footprint properties):
                for key, value in footprint_new.items():
                    # Compare value of property
                    if value == footprint_old[key]:
                        # Skip if same (no diffs)
                        continue

                    #  Base layer diff e.g. position, rotation, ref... ect
                    #if key != "pads_pth":
                    # Add diff to list
                    fp_diffs.update({key: value})
                    # Update pcb dictionary
                    footprint_old.update({key: value})

                    # PAD diffs code:

                    # # ------------ Special case for pads: go one layer deeper ------------------------------
                    # else:
                    #     pad_diffs_dict = None
                    #     pad_diffs_parent = []
                    #     # Go through all pads
                    #     for pad_new in footprint_new["pads_pth"]:
                    #
                    #         # Get old pad to be edited (by new pads KIID)
                    #         pad_old = getDictEntryByKIID(list=footprint_old["pads_pth"],
                    #                                      kiid=pad_new["kiid"])
                    #
                    #         # Remove hash and name from dict to calculate new hash
                    #         pad_new_temp = {k: pad_new[k] for k in set(list(pad_new.keys())) - {
                    #             "hash", "kiid"}}
                    #
                    #         # Compare hashes
                    #         if hash(str(pad_new_temp)) == pad_old["hash"]:
                    #             continue
                    #         pad_diffs = []
                    #         for pad_key in ["pos_delta", "hole_size"]:
                    #             # Skip if value match
                    #             if pad_new[pad_key] == pad_old[pad_key]:
                    #                 continue
                    #             # Add diff to list
                    #             pad_diffs.append([pad_key, pad_new[pad_key]])
                    #             # Update old dict
                    #             pad_old.update({pad_key: pad_new[pad_key]})
                    #
                    #         # Hash itself when all changes applied
                    #         pad_old.update({"hash": hash(str(pad_old))})
                    #         # Add list of diffs to dictionary with pad name
                    #         pad_diffs_dict = {pad_old["kiid"]: pad_diffs}
                    #
                    #         # Check if dictionary not is empty:
                    #         if pad_diffs_dict and list(pad_diffs_dict.values())[-1]:
                    #             # Add dict with pad name to list of pads changed
                    #             pad_diffs_parent.append(pad_diffs_dict)
                    #
                    #     if pad_diffs_parent:
                    #         # Add list of pads changed to fp diff
                    #         fp_diffs.append([key, pad_diffs_parent])

                if fp_diffs:
                    # Hash itself with updated values
                    footprint_old_hash = hashlib.md5(str(footprint_old).encode("utf-8")).hexdigest()
                    footprint_old.update({"hash": footprint_old_hash})
                    # Append dictionary with ID and list of changes to list of changed footprints
                    changed.append({footprint_old["kiid"]: fp_diffs})


        # Find deleted footprints
        if type(pcb) is dict:
            # Go through existing list of footprints (dictionary)
            for footprint_old in pcb["footprints"]:
                found_match = False
                # Go through FPs in PCB:
                for fp in footprints:
                    # # Find corresponding footprint in old dict based on kiid
                    # if fp.GetPath().AsString() == footprint_old["kiid"]:
                    # TODO Uuid vs Path
                    if fp.m_Uuid.AsString() == footprint_old["kiid"]:
                        #  Found match
                        found_match = True
                if not found_match:
                    # Add kiid of deleted footprint to removed list
                    removed.append(footprint_old["kiid"])
                    # Delete footprint from pcb dictonary
                    pcb["footprints"].remove(footprint_old)

        result = {}
        if added:
            result.update({"added": added})
        if changed:
            result.update({"changed": changed})
        if removed:
            result.update({"removed": removed})

        return result


    @staticmethod
    def getVias(brd, pcb):
        """
        Returns three keyword dictionary: added - changed - removed
        If via is changed, pcb dictionary gets automatically updated
        :param pcb: dict
        :param brd: pcbnew.Board object
        :return: dict
        """

        vias = []
        added = []
        removed = []
        changed = []

        try:
            # Add all track IDs to list to find out if track is new, or it alreasy exist in pcb dictionary
            list_of_ids = [v["kiid"] for v in pcb["vias"]]
            latest_nr = pcb["vias"][-1]["ID"]
        except TypeError:
            list_of_ids = []
            latest_nr = 0

        # Get vias from track list inside KC
        vias = []
        for track in brd.GetTracks():
            if "VIA" in str(type(track)):
                vias.append(track)

        # Go through vias
        for i, v in enumerate(vias):
            # if via kiid is not in pcb dictionary, it's a new via
            if v.m_Uuid.AsString() not in list_of_ids:

                # Get data
                via = PcbScanner.getViaData(v)
                # Hash via - used for detecting change when scanning board
                via_hash = hashlib.md5(str(via).encode('utf-8')).hexdigest()
                via.update({"hash": via_hash})
                via.update({"ID": (latest_nr + i + 1)})
                # Add UUID to dictionary
                via.update({"kiid": v.m_Uuid.AsString()})
                # Add dict to list of added vias
                added.append(via)
                # Add via to pcb dictionary
                if pcb:
                    pcb["vias"].append(via)

            # Known kiid, via has already been added, check for diff
            else:
                # Get old via to be updated
                via_old = getDictEntryByKIID(list=pcb["vias"],
                                             kiid=v.m_Uuid.AsString())
                # Get data
                via_new = PcbScanner.getViaData(v)

                # Calculate new hash and compare to hash in old dict to see if diff
                via_new_hash = hashlib.md5(str(via_new).encode('utf-8')).hexdigest()
                if via_new_hash == via_old["hash"]:
                    # Skip if no diffs, which is indicated by the same hash (hash in calculated from dictionary)
                    continue

                via_diffs = {}
                for key, value in via_new.items():
                    # Check all properties of vias (keys)
                    if value != via_old[key]:
                        # Add diff to list
                        via_diffs.update({key: value})
                        # Update old dictionary
                        via_old.update({key: value})

                # If any difference is found and added to list:
                if via_diffs:
                    # Hash itself when all changes applied
                    via_old_hash = hashlib.md5(str(via_old).encode('utf-8')).hexdigest()
                    via_old.update({"hash": via_old_hash})
                    # Append dictionary with kiid and list of changes to list of changed vias
                    changed.append({via_old["kiid"]: via_diffs})

        # Find deleted vias
        if type(pcb) is dict:
            # Go through existing list of vias (dictionary)
            for via_old in pcb["vias"]:
                found_match = False
                # Go throug vias in KC PCB
                for v in vias:
                    # Find corresponding track in old dict based on UUID
                    if v.m_Uuid.AsString() == via_old["kiid"]:
                        found_match = True
                # Via in dict is not in KC - it has been deleted
                if not found_match:
                    # Add UUID of deleted via to removed list
                    removed.append(via_old["kiid"])
                    # Detele via from pcb dictionary
                    pcb["vias"].remove(via_old)

        result = {}
        if added:
            result.update({"added": added})
        if changed:
            result.update({"changed": changed})
        if removed:
            result.update({"removed": removed})

        return result


    @staticmethod
    def getDrawingsData(drw):
        """
        Returns dictionary of drawing properties
        :param drw: pcbnew.PCB_SHAPE object
        :return: dict
        """
        drawing = None
        geometry_type = drw.ShowShape()

        if geometry_type == "Line":
            drawing = {
                "shape": drw.ShowShape(),
                "start": [
                    drw.GetStart()[0],
                    drw.GetStart()[1]
                ],
                "end": [
                    drw.GetEnd()[0],
                    drw.GetEnd()[1]
                ]
            }

        elif (geometry_type == "Rect") or (geometry_type == "Polygon"):
            drawing = {
                "shape": drw.ShowShape(),
                "points": [[c[0], c[1]] for c in drw.GetCorners()]
            }

        elif geometry_type == "Circle":
            drawing = {
                "shape": drw.ShowShape(),
                "center": [
                    drw.GetCenter()[0],
                    drw.GetCenter()[1]
                ],
                "radius": drw.GetRadius()
            }

        elif geometry_type == "Arc":
            drawing = {
                "shape": drw.ShowShape(),
                "points": [
                    [
                        drw.GetStart()[0],
                        drw.GetStart()[1]
                    ],
                    [
                        drw.GetArcMid()[0],
                        drw.GetArcMid()[1]
                    ],
                    [
                        drw.GetEnd()[0],
                        drw.GetEnd()[1]
                    ]
                ]
            }


        if drawing:
            return drawing


    @staticmethod
    def getFpData(fp):
        """
        Return dictionary of footprint properties
        :param fp: pcbnew.FOOTPRINT object
        :return: dict
        """
        footprint = {
            "id": fp.GetFPIDAsString(),
            "ref": fp.GetReference(),
            "pos": [
                fp.GetX(),
                fp.GetY()
            ],
            "rot": fp.GetOrientationDegrees()
        }

        # Get layer
        if "F." in fp.GetLayerName():
            footprint.update({"layer": "Top"})
        elif "B." in fp.GetLayerName():
            footprint.update({"layer": "Bot"})

        # Add through hole if it's only one (Mouting hole footprint)
        try:
            if fp.HasThroughHolePads() and (len(fp.Pads()) == 1):
                # logger.debug(f"Scanning through holes for {footprint['ref']}")
                pads_list = []
                for pad in fp.Pads():
                    pad_hole = {
                        "pos_delta": [
                            pad.GetX() - fp.GetX(),
                            pad.GetY() - fp.GetY()
                        ],
                        "hole_size": [
                            pad.GetDrillSize()[0],
                            pad.GetDrillSize()[0]
                        ]
                    }
                    # Hash itself and add to list
                    pad_hole.update({"hash": hash(str(pad_hole))})
                    #pad_hole.update({"ID": int(pad.GetName())})
                    pad_hole.update({"kiid": pad.m_Uuid.AsString()})
                    pads_list.append(pad_hole)

                # Add pad holes to footprint dict
                footprint.update({"pads_pth": pads_list})
            # Edit: don't add key to dictionary
            # else:
            #     # Add pad holes to footprint dict
            #     footprint.update({"pads_pth": None})
        except Exception as e:
            logger.exception(e)


        # Get models
        model_list = None
        if fp.Models():
            model_list = []
            for ii, model in enumerate(fp.Models()):
                model_list.append(
                    {
                        "model_id": f"{ii:03d}",
                        "filename": relativeModelPath(model.m_Filename),
                        "offset": [
                            model.m_Offset[0],
                            model.m_Offset[1],
                            model.m_Offset[2]
                        ],
                        "scale": [
                            model.m_Scale[0],
                            model.m_Scale[1],
                            model.m_Scale[2]
                        ],
                        "rot": [
                            model.m_Rotation[0],
                            model.m_Rotation[1],
                            model.m_Rotation[2]
                        ]
                    }
                )

        # Add models to footprint dict
        footprint.update({"3d_models": model_list})

        return footprint


    @staticmethod
    def getViaData(track):
        return {
            "center": [track.GetX(),
                       track.GetY()
                       ],
            "radius": track.GetDrill(),
        }