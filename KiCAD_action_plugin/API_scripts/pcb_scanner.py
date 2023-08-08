"""
    This module consists only of static methods and represents the collection of KiCAD API API_scripts
    that return either pcb of diff dictionary data model.
"""

import random

from scripts.utils import getDictEntryByKIID, relativeModelPath


class PcbScanner:

    @staticmethod
    def getDiff(brd, pcb, diff):
        PcbScanner.updateDiffDict(key="footprints",
                                  value=PcbScanner.getFootprints(brd, pcb),
                                  diff=diff)
        PcbScanner.updateDiffDict(key="drawings",
                                  value=PcbScanner.getPcbDrawings(brd, pcb),
                                  diff=diff)
        PcbScanner.updateDiffDict(key="vias",
                                  value=PcbScanner.getVias(brd, pcb),
                                  diff=diff)
        return diff


    @staticmethod
    def updateDiffDict(key, value, diff):
        """Helper function for adding and removing entries from diff dictionary"""

        if value.get("added") or value.get("changed") or value.get("removed"):
            diff.update({key: value})
        else:
            # Removed from diff if no new changes
            try:
                diff.pop(key)
            except KeyError:
                pass


    @staticmethod
    def getPcb(brd, pcb=None):
        """
        Create a dictionary with PCB elements and properties
        :param pcb: dict
        :param brd: pcbnew.Board object
        :return: dict
        """

        # List for creating random tailpiece (id)
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

        # Pcb dictionary
        pcb = {"general": general_data,
               "drawings": PcbScanner.getPcbDrawings(brd, pcb)["added"],
               "footprints": PcbScanner.getFootprints(brd, pcb)["added"],
               "vias": PcbScanner.getVias(brd, pcb)["added"]
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

        edge_cuts = []
        added = []
        removed = []
        changed = []

        try:
            # Add all drw IDs to list, to find out if drw is new, or it already exists in pcb dictionary
            list_of_ids = [d["kiid"] for d in pcb["drawings"]]
            latest_nr = pcb["drawings"][-1]["ID"]
        except TypeError:  # Scanning fps for the first time
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
                    drawing.update({"hash": hash(str(drawing))})
                    drawing.update({"ID": (latest_nr + i + 1)})
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
                    # Calculate new hash and compare to hash in old dict
                    if hash(str(drawing_new)) == drawing_old['hash']:
                        # Skip if no diffs (same hash)
                        continue

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
                        drawing_old.update({"hash": hash(str(drawing_old))})
                        # Append dictionary with ID and list of changes to list of changed drawings
                        changed.append({drawing_old["kiid"]: drawing_diffs})

        # Find deleted drawings
        if type(pcb) is dict:
            # Go through existing list of drawings (dictionary)
            for drawing_old in pcb["drawings"]:
                found_match = False
                # Go through DRWs in PCB:
                for drw in drawings:
                    # Find corresponding drawing in old dict based on UUID
                    if drw.m_Uuid.AsString() != drawing_old["kiid"]:
                        #  Found match
                        found_match = True
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

        added = []
        removed = []
        changed = []

        try:
            # Add all fp IDs to list, to find out if fp is new, or it already exists in pcb dictionary
            latest_nr = pcb["footprints"][-1]["ID"]
            list_of_ids = [f["kiid"] for f in pcb["footprints"]]

        except TypeError:  # Scanning fps for the first time
            latest_nr = 0
            list_of_ids = []

        # Go through footprints
        footprints = brd.GetFootprints()
        for i, fp in enumerate(footprints):
            # if footprints kiid is not in pcb dictionary, it's a new footprint
            if fp.GetPath().AsString() not in list_of_ids:

                # Get FP data
                footprint = PcbScanner.getFpData(fp)

                # Hash footprint - used for detecting change when scanning board
                footprint.update({"hash": hash(str(footprint))})
                footprint.update({"ID": (latest_nr + i + 1)})
                footprint.update({"kiid": fp.GetPath().AsString()})
                # Add dict to list
                added.append(footprint)
                # Add footprint to pcb dictionary
                if pcb:
                    pcb["footprints"].append(footprint)

            # known kiid, fp has already been added, check for diff
            else:
                # Get old dictionary entry to be edited:
                footprint_old = getDictEntryByKIID(list=pcb["footprints"],
                                                   kiid=fp.GetPath().AsString())
                # Get new data of footprint
                footprint_new = PcbScanner.getFpData(fp)
                # Calculate new hash and compare to hash in old dict
                if hash(str(footprint_new)) == footprint_old['hash']:
                    # Skip if no diffs (same hash)
                    continue

                fp_diffs = []
                # Start of main diff loop (compare values of all footprint properties):
                for key, value in footprint_new.items():
                    # Compare value of property
                    if value == footprint_old[key]:
                        # Skip if same (no diffs)
                        continue

                    #  Base layer diff e.g. position, rotation, ref... ect
                    if key != "pads_pth":
                        # Add diff to list
                        fp_diffs.append([key, value])
                        # Update pcb dictionary
                        footprint_old.update({key: value})

                    # ------------ Special case for pads: go one layer deeper ------------------------------
                    else:
                        pad_diffs_dict = None
                        pad_diffs_parent = []
                        # Go through all pads
                        for pad_new in footprint_new["pads_pth"]:

                            # Get old pad to be edited (by new pads KIID)
                            pad_old = getDictEntryByKIID(list=footprint_old["pads_pth"],
                                                         kiid=pad_new["kiid"])

                            # Remove hash and name from dict to calculate new hash
                            pad_new_temp = {k: pad_new[k] for k in set(list(pad_new.keys())) - {
                                "hash", "kiid"}}

                            # Compare hashes
                            if hash(str(pad_new_temp)) == pad_old["hash"]:
                                continue
                            pad_diffs = []
                            for pad_key in ["pos_delta", "hole_size"]:
                                # Skip if value match
                                if pad_new[pad_key] == pad_old[pad_key]:
                                    continue
                                # Add diff to list
                                pad_diffs.append([pad_key, pad_new[pad_key]])
                                # Update old dict
                                pad_old.update({pad_key: pad_new[pad_key]})

                            # Hash itself when all changes applied
                            pad_old.update({"hash": hash(str(pad_old))})
                            # Add list of diffs to dictionary with pad name
                            pad_diffs_dict = {pad_old["kiid"]: pad_diffs}

                            # Check if dictionary not is empty:
                            if pad_diffs_dict and list(pad_diffs_dict.values())[-1]:
                                # Add dict with pad name to list of pads changed
                                pad_diffs_parent.append(pad_diffs_dict)

                        if pad_diffs_parent:
                            # Add list of pads changed to fp diff
                            fp_diffs.append([key, pad_diffs_parent])

                # Hash itself when all changes applied
                footprint_old.update({"hash": hash(str(footprint_old))})
                if fp_diffs:
                    # Append dictionary with ID and list of changes to list of changed footprints
                    changed.append({footprint_old["kiid"]: fp_diffs})


        # Find deleted footprints
        if type(pcb) is dict:
            # Go through existing list of footprints (dictionary)
            for footprint_old in pcb["footprints"]:
                found_match = False
                # Go through FPs in PCB:
                for fp in footprints:
                    # Find corresponding footprint in old dict based on kiid
                    if fp.GetPath().AsString() == footprint_old["kiid"]:
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
                via.update({"hash": hash(str(via))})
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

                # Calculate new hash and compare to hash in old dict
                # Skip if no diff (same value)
                if hash(str(via_new)) == via_old["hash"]:
                    continue

                via_diffs = []
                for key, value in via_new.items():
                    # Check all properties of vias (keys)
                    if value != via_old[key]:
                        # Add diff to list
                        via_diffs.append([key, value])
                        # Update old dictionary
                        via_old.update({key: value})

                # If any difference is found and added to list:
                if via_diffs:
                    # Hash itself when all changes applied
                    via_old.update({"hash": hash(str(via_old))})
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
        edge = None

        if drw.ShowShape() == "Rect":
            edge = {
                "shape": drw.ShowShape(),
                "points": [[c[0], c[1]] for c in drw.GetCorners()]
            }

        elif drw.ShowShape() == "Line":
            edge = {
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

        elif drw.ShowShape() == "Arc":
            edge = {
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

        elif drw.ShowShape() == "Circle":
            edge = {
                "shape": drw.ShowShape(),
                "center": [
                    drw.GetCenter()[0],
                    drw.GetCenter()[1]
                ],
                "radius": drw.GetRadius()
            }

        elif drw.ShowShape() == "Polygon":
            edge = {
                "shape": drw.ShowShape(),
                "points": [[c[0], c[1]] for c in drw.GetCorners()]
            }

        if edge:
            return edge


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

        # Get holes
        if fp.HasThroughHolePads():
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
                pad_hole.update({"ID": int(pad.GetName())})
                pad_hole.update({"kiid": pad.m_Uuid.AsString()})
                pads_list.append(pad_hole)

            # Add pad holes to footprint dict
            footprint.update({"pads_pth": pads_list})
        else:
            # Add pad holes to footprint dict
            footprint.update({"pads_pth": None})

        # Get models
        model_list = None
        if fp.Models():
            model_list = []
            for ii, model in enumerate(fp.Models()):
                model_list.append({
                    "model_id": f"{ii:03d}",
                    "filename": relativeModelPath(model.m_Filename),
                    "offset": [
                        model.m_Offset[0],
                        model.m_Offset[1],
                        model.m_Offset[2]
                    ],
                    "scale": [model.m_Scale[0],
                              model.m_Scale[1],
                              model.m_Scale[2]
                              ],
                    "rot": [model.m_Rotation[0],
                            model.m_Rotation[1],
                            model.m_Rotation[2]
                            ]
                })

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