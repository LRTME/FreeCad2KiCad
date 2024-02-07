""" Helper functions for getting objects by IDs, and converting to/from KC vectors. """

import pcbnew


def relativeModelPath(file_path: str) -> str:
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


def getDictEntryByKIID(list: list, kiid: str) -> dict:
    """ Returns entry in dictionary with same KIID value. """
    result = None

    for entry in list:
        if entry.get("kiid"):
            if entry["kiid"] == kiid:
                result = entry
                break

    return result


def getDrawingByKIID(brd: pcbnew.BOARD, kiid: str) -> pcbnew.PCB_SHAPE:
    """ Returns pcbnew.PCB_SHAPE object with same KIID attribute. """
    result = None

    drws = brd.GetDrawings()
    for drw in drws:
        if drw.m_Uuid.AsString() == kiid:
            result = drw
            break

    return result


def getFootprintByKIID(brd: pcbnew.BOARD, kiid: str) -> pcbnew.FOOTPRINT:
    """ Returns pcbnew.FOOTPRINT object with same KIID attribute. """
    result = None

    fps = brd.GetFootprints()
    for fp in fps:
        if fp.m_Uuid.AsString() == kiid:
            result = fp
            break

    return result


def KiCADVector(list: list) -> pcbnew.VECTOR2I:
    """ Convert two element list to pcbnew.VECTOR2I type. """
    return pcbnew.VECTOR2I(list[0], list[1])