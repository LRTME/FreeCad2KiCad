""" Helper functions for getting objects by IDs, and converting to/from KC vectors. """

import pcbnew


def relative_model_path(file_path: str) -> str:
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


def get_dict_entry_by_kiid(list_of_entries: list, kiid: str) -> dict:
    """ Returns entry in dictionary with same KIID value. """
    result = None

    for entry in list_of_entries:
        if entry.get("kiid"):
            if entry["kiid"] == kiid:
                result = entry
                break

    return result


def get_drawing_by_kiid(brd: pcbnew.BOARD, kiid: str) -> pcbnew.PCB_SHAPE:
    """ Returns pcbnew.PCB_SHAPE object with same KIID attribute. """
    result = None

    drws = brd.GetDrawings()
    for drw in drws:
        if drw.m_Uuid.AsString() == kiid:
            result = drw
            break

    return result


def get_footprint_by_kiid(brd: pcbnew.BOARD, kiid: str) -> pcbnew.FOOTPRINT:
    """ Returns pcbnew.FOOTPRINT object with same KIID attribute. """
    result = None

    fps = brd.GetFootprints()
    for fp in fps:
        if fp.m_Uuid.AsString() == kiid:
            result = fp
            break

    return result


def kicad_vector(coordinates: list) -> pcbnew.VECTOR2I:
    """ Convert two element list to pcbnew.VECTOR2I type. """
    return pcbnew.VECTOR2I(coordinates[0], coordinates[1])
