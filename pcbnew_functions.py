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
           "geometry": getPcbGeometry(brd),
           "footprints": getFootprints(brd, pcb)["added"],
           "vias": getVias(brd)
           }

    return pcb


def getPcbGeometry(brd):
    """
    Returns list of edge cuts
    :param brd: pcbnew.Board object
    :return: list
    """
    edge_cuts = []
    # Counter = [rect, line, arc, circle, poly]
    counter = [0 for _ in range(5)]
    for drw in brd.GetDrawings():
        # Get drawings in edge layer
        if drw.GetLayerName() == "Edge.Cuts":

            if drw.ShowShape() == "Rect":
                edge_cuts.append({
                    "shape": drw.ShowShape() + f"_{counter[0]:03d}",
                    "points": [[c[0], c[1]] for c in drw.GetCorners()]
                })
                counter[0] += 1

            elif drw.ShowShape() == "Line":
                edge_cuts.append({
                    "shape": drw.ShowShape() + f"_{counter[1]:03d}",
                    "start": [
                        drw.GetStart()[0],
                        drw.GetStart()[1]
                    ],
                    "end": [
                        drw.GetEnd()[0],
                        drw.GetEnd()[1]
                    ]
                })
                counter[1] += 1

            elif drw.ShowShape() == "Arc":
                edge_cuts.append({
                    "shape": drw.ShowShape() + f"_{counter[2]:03d}",
                    "radius": drw.GetRadius(),
                    "pos": [
                        drw.GetX(),
                        drw.GetY()
                    ],
                    "start_angle": drw.GetArcAngleStart().AsDegrees(),
                    "arc_angle": drw.GetArcAngle().AsDegrees(),
                    "p1": [
                        drw.GetStart()[0],
                        drw.GetStart()[1],
                    ],
                    "p2": [
                        drw.GetArcMid()[0],
                        drw.GetArcMid()[1],
                    ],
                    "p3": [
                        drw.GetEnd()[0],
                        drw.GetEnd()[1],
                    ],
                })
                counter[2] += 1

            elif drw.ShowShape() == "Circle":
                edge_cuts.append({
                    "shape": drw.ShowShape() + f"_{counter[3]:03d}",
                    "center": [
                        drw.GetCenter()[0],
                        drw.GetCenter()[1]
                    ],
                    "radius": drw.GetRadius()
                })
                counter[3] += 1

            elif drw.ShowShape() == "Polygon":
                edge_cuts.append({
                    "shape": drw.ShowShape() + f"_{counter[4]:03d}",
                    "points": [[c[0], c[1]] for c in drw.GetCorners()]
                })
                counter[4] += 1

    return edge_cuts


def getFootprints(brd, pcb):
    """
    Returns three keyword dictionary: added - changed - removed
    If fp is changed, pcb dictionary gets automatically updated
    :param pcb: dict
    :param brd: pcbnew.Board object
    :return: dict
    """

    # noinspection PyShadowingNames
    def GetFPData(fp):
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
                pad_hole.update({"pad_name": pad.GetName()})
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
        # Get flag of last footprint in dictionary
        # - used when setting flags for newly added fps (so it doesn't start with 1 again)
        latest_flag = pcb["footprints"][-1]["flag"]
    except TypeError:  # Scanning fps for the first time
        latest_flag = 0

    # Go through footprints
    footprints = brd.GetFootprints()
    for i, fp in enumerate(footprints):
        # if fp has flag 0, it has not been added to dict yet
        if fp.GetFlag() == 0:

            # Get FP data
            footprint = GetFPData(fp)

            # Hash footprint without flag
            # - used for detecting change when scanning board
            footprint.update({"hash": hash(str(footprint))})
            footprint.update({"flag": (latest_flag + i + 1)})
            fp.SetFlag(latest_flag + i + 1)
            # Add dict to list
            added.append(footprint)

        # flag not 0, fp has already been added, check for diff
        else:

            # Go through existing list of footprints (dictionary)
            for fp_index, footprint_old in enumerate(pcb["footprints"]):
                # Find corresponding footprint in old dict based on flags
                if fp.GetFlag() == footprint_old["flag"]:
                    # Get data
                    footprint_new = GetFPData(fp)

                    # Calculate new hash and compare to hash in old dict
                    if hash(str(footprint_new)) != footprint_old['hash']:
                        fp_diffs = []
                        FP_PROPS = ["id", "ref", "pos", "rot", "layer", "pads_pth", "3d_models"]
                        for key in FP_PROPS:

                            # Value of property is different
                            if footprint_new[key] != footprint_old[key]:

                                # ------------ Special case for pads: go one layer deeper ------------------------------
                                if key == "pads_pth":
                                    pad_diffs_dict = None
                                    pad_diffs_parent = []
                                    # Go through all pads in both lists
                                    for pad_new in footprint_new["pads_pth"]:
                                        for pad_old in footprint_old["pads_pth"]:
                                            # Find corresponding pad based on name
                                            if pad_new["pad_name"] == pad_old["pad_name"]:
                                                # Remove hash and name from dict to calculate new hash
                                                pad_new_temp = {k: pad_new[k] for k in set(list(pad_new.keys())) - {
                                                    "hash", "pad_name"}}
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
                                                    pad_diffs_dict = {pad_old["pad_name"]: pad_diffs}

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
                                    fp_diffs.append([key, footprint_new[key]])
                                    # Update old dict
                                    footprint_old.update({key: footprint_new[key]})
                                    # print(f"Updated pcb {pcb['footprints'][fp_index][key]}")

                        # Hash itself when all changes applied
                        footprint_old.update({"hash": hash(str(footprint_old))})
                        if fp_diffs:
                            # Append dictionary with ID and list of changes to list of changed footprints
                            changed.append({footprint_old["flag"]: fp_diffs})

    # Find deleted footprints
    if type(pcb) is dict:
        # Go through existing list of footprints (dictionary)
        for footprint_old in pcb["footprints"]:
            found_match = False
            # Go through FPs in PCB:
            for fp in footprints:
                # Find corresponding footprint in old dict based on flags
                if fp.GetFlag() == footprint_old["flag"]:
                    #  Found match
                    found_match = True
            if not found_match:
                removed.append(footprint_old["flag"])

    result = {}
    if added:
        result.update({"added": added})
    if changed:
        result.update({"changed": changed})
    if removed:
        result.update({"removed": removed})

    return result


def getVias(brd):
    """
    Get freestanding vias - through holes
    :param brd: pcbnew.Board object
    :return: list
    """
    tracks = brd.GetTracks()
    vias = []
    via_count = 0
    for track in tracks:
        # Find freestanding vias in tracks list
        if "VIA" in str(type(track)):
            vias.append({
                "via_id": f"Via_{via_count:03d}",
                "pos": [track.GetX(),
                        track.GetY()
                        ],
                "hole_size": track.GetDrill()
            })
            via_count = via_count + 1

    return vias