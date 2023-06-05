import random


def relativeModelPath(file_path):
    """
    Get relative model path and name without file extension
    :param file_path: string - full file path
    :return: string - model directory and name without file extension
    """
    if type(file_path) is str:
        string_list = file_path.split("/")
        # Remove "${KICAD6_3DMODEL_DIR}"
        string_list.pop(0)
        new_string = '/'.join(string for string in string_list)
        # Remove .wrl from model
        return "/" + new_string.replace(".wrl", "")


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
           "drawings": getPcbDrawings(brd, pcb)["added"],
           "footprints": getFootprints(brd, pcb)["added"],
           "vias": getVias(brd, pcb)["added"]
           }

    return pcb


def getPcbDrawings(brd, pcb):
    """
    Returns three keyword dictionary: added - changed - removed
    If drawings is changed, pcb dictionary gets automatically updated
    :param pcb: dict
    :param brd: pcbnew.Board object
    :return: dict
    """

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
    # ------- End of getGeometryData function --------------------------------------

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

    # Counter = [rect, line, arc, circle, poly]
    counter = [0 for _ in range(5)]
    # Go through drawings
    drawings = brd.GetDrawings()
    for i, drw in enumerate(drawings):
        # Get drawings in edge layer
        if drw.GetLayerName() == "Edge.Cuts":

            # if drawing kiid is not in pcb dictionary, it's a new drawing
            if drw.m_Uuid.AsString() not in list_of_ids:

                # Get data
                drawing = getDrawingsData(drw)
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

                # Go through existing list of drawings (dictionary)
                for drw_index, drawing_old in enumerate(pcb["drawings"]):
                    # Find corresponding drawings in old dict based on kiid
                    if drw.m_Uuid.AsString() == drawing_old["kiid"]:

                        # Get data
                        drawing_new = getDrawingsData(drw)

                        # Calculate new hash and compare to hash in old dict
                        if hash(str(drawing_new)) != drawing_old['hash']:
                            drawing_diffs = []
                            for key, value in drawing_new.items():
                                # Check all properties of drawing (keys)
                                if value != drawing_old[key]:
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
                if drw.m_Uuid.AsString() == drawing_old["kiid"]:
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


def getFootprints(brd, pcb):
    """
    Returns three keyword dictionary: added - changed - removed
    If fp is changed, pcb dictionary gets automatically updated
    :param pcb: dict
    :param brd: pcbnew.Board object
    :return: dict
    """

    # noinspection PyShadowingNames
    def getFPData(fp):
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
    # ------- End of FPData function --------------------------------------

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
            footprint = getFPData(fp)

            # Hash footprint - used for detecting change when scanning board
            footprint.update({"hash": hash(str(footprint))})
            footprint.update({"ID": (latest_nr + i + 1)})
            footprint.update({"kiid": fp.GetPath().AsString()})
            # Add dict to list
            added.append(footprint)
            # Add to footprint to pcb dictionary
            if pcb:
                pcb["footprints"].append(footprint)

        # known kiid, fp has already been added, check for diff
        else:

            # Go through existing list of footprints (dictionary)
            for fp_index, footprint_old in enumerate(pcb["footprints"]):
                # Find corresponding footprint in old dict based on kiid
                if fp.GetPath().AsString() == footprint_old["kiid"]:

                    # Get data
                    footprint_new = getFPData(fp)

                    # Calculate new hash and compare to hash in old dict
                    if hash(str(footprint_new)) != footprint_old['hash']:
                        fp_diffs = []
                        for key, value in footprint_new.items():
                            # Value of property is different
                            if value != footprint_old[key]:

                                # ------------ Special case for pads: go one layer deeper ------------------------------
                                if key == "pads_pth":
                                    pad_diffs_dict = None
                                    pad_diffs_parent = []
                                    # Go through all pads in both lists
                                    for pad_new in footprint_new["pads_pth"]:
                                        for pad_old in footprint_old["pads_pth"]:
                                            # Find corresponding pad based on name
                                            if pad_new["kiid"] == pad_old["kiid"]:
                                                # Remove hash and name from dict to calculate new hash
                                                pad_new_temp = {k: pad_new[k] for k in set(list(pad_new.keys())) - {
                                                    "hash", "kiid"}}
                                                # Compare hashes
                                                if hash(str(pad_new_temp)) != pad_old["hash"]:
                                                    pad_diffs = []
                                                    PAD_PROPS = ["pos_delta", "hole_size"]
                                                    for pad_key in PAD_PROPS:
                                                        if pad_new[pad_key] != pad_old[pad_key]:
                                                            # Add diff to list
                                                            pad_diffs.append([pad_key, pad_new[pad_key]])
                                                            # Update old dict
                                                            pad_old.update({pad_key: pad_new[pad_key]})

                                                    # Hash itself when all changes applied
                                                    pad_old.update({"hash": hash(str(pad_old))})
                                                    # Add list of diffs to dictionary with pad name
                                                    pad_diffs_dict = {pad_old["kiid"]: pad_diffs}

                                                # Check if dictionary not is empty:
                                                if pad_diffs_dict:
                                                    if list(pad_diffs_dict.values())[-1]:
                                                        # Add dict with pad name to list of pads changed
                                                        pad_diffs_parent.append(pad_diffs_dict)

                                    if pad_diffs_parent:
                                        # Add list of pads changed to fp diff
                                        fp_diffs.append([key, pad_diffs_parent])
                                # --------------------------------------------------------------------------------------

                                #  Base layer diff e.g. position, rotation, ref...
                                else:
                                    # Add diff to list
                                    fp_diffs.append([key, value])
                                    # Update pcb dictionary
                                    footprint_old.update({key: value})

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


def getVias(brd, pcb):
    """
    Returns three keyword dictionary: added - changed - removed
    If via is changed, pcb dictionary gets automatically updated
    :param pcb: dict
    :param brd: pcbnew.Board object
    :return: dict
    """

    # noinspection PyShadowingNames
    def getViaData(track):
        return {
            "center": [track.GetX(),
                       track.GetY()
                       ],
            "radius": track.GetDrill(),
        }

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
            via = getViaData(v)
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

            # Go through existing list of drawings (dictionary)
            for via_index, via_old in enumerate(pcb["vias"]):
                # Find corresponding via in old dict based on kiid
                if v.m_Uuid.AsString() == via_old["kiid"]:

                    # Get data
                    via_new = getViaData(v)
                    # Calculate new hash and compare to hash in old dict
                    if hash(str(via_new)) != via_old["hash"]:
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