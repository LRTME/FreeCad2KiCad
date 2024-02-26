""" Helper functions for getting objects by IDs, and converting to/from KC vectors. """

import logging
import os
import pcbnew
import re

logging = logging.getLogger("scanner")


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


def get_model_path(model_path: str) -> str:
    """
    Parse environment variable in model filename, return absolute model path.
    Author: Mitja Nemec, https://github.com/MitjaNemec
    Taken from: https://github.com/MitjaNemec/Archive3DModels/tree/main
    """
    abs_model_path = None
    if "${" in model_path:
        start_index = model_path.find("${") + 2
        end_index = model_path.find("}")
        env_var = model_path[start_index:end_index]

        path = get_variable(env_var)
        # if variable is defined, find proper model path
        if path is not None:
            abs_model_path = os.path.normpath(path + model_path[end_index + 1:])
        # if variable is not defined, we can not find the model. Thus don't put it on the list
        else:
            logger.debug("Can not find model defined with environment variable:\n" + model_path)
            abs_model_path = None
    elif "$(" in model_path:
        start_index = model_path.find("$(") + 2
        end_index = model_path.find(")")
        env_var = model_path[start_index:end_index]

        path = get_variable(env_var)
        # if variable is defined, find proper model path
        if path is not None:
            abs_model_path = os.path.normpath(path + model_path[end_index + 1:])
        # if variable is not defined, we can not find the model. Thus don't put it on the list
        else:
            logger.debug("Can not find model defined with environment variable:\n" + model_path)
            abs_model_path = None
    # check if there is no path (model is local to project)
    elif prj_path == os.path.dirname(os.path.abspath(model_path)):
        abs_model_path = os.path.abspath(model_path)
    # check if model is given with absolute path
    elif os.path.exists(model_path):
        abs_model_path = os.path.abspath(model_path)
    # otherwise we don't know how to parse the path
    else:
        logger.debug("Ambiguous path for the model: " + model_path)
        # test default 3D_library location if defined
        if os.getenv("KICAD6_3DMODEL_DIR"):
            if os.path.exists(os.path.normpath(os.path.join(os.getenv("KICAD6_3DMODEL_DIR"), model_path))):
                abs_model_path = os.path.normpath(os.path.join(os.getenv("KICAD6_3DMODEL_DIR"), model_path))
                logger.debug("Going with: " + abs_model_path)
        # test default 3D_library location if defined
        elif os.getenv("KICAD7_3DMODEL_DIR"):
            if os.path.exists(os.path.normpath(os.path.join(os.getenv("KICAD7_3DMODEL_DIR"), model_path))):
                abs_model_path = os.path.normpath(os.path.join(os.getenv("KICAD7_3DMODEL_DIR"), model_path))
                logger.debug("Going with: " + abs_model_path)
        # test default 3D_library location if defined
        elif os.getenv("KICAD8_3DMODEL_DIR"):
            if os.path.exists(os.path.normpath(os.path.join(os.getenv("KICAD8_3DMODEL_DIR"), model_path))):
                abs_model_path = os.path.normpath(os.path.join(os.getenv("KICAD8_3DMODEL_DIR"), model_path))
                logger.debug("Going with: " + abs_model_path)
        # testing project folder location
        elif os.path.exists(os.path.normpath(os.path.join(prj_path, model_path))):
            abs_model_path = os.path.normpath(os.path.join(prj_path, model_path))
            logger.debug("Going with: " + abs_model_path)
        else:
            abs_model_path = None
            logger.debug("Can not find model defined with: " + model_path)

    return abs_model_path


def get_variable(env_var):
    """
    Author: Mitja Nemec, https://github.com/MitjaNemec
    Taken from: https://github.com/MitjaNemec/Archive3DModels/tree/main
    """
    path = os.getenv(env_var)

    if path is None and (env_var == "KISYS3DMOD" or re.match("KICAD.*_3DMODEL_DIR", env_var)):
        path = os.getenv("KICAD7_3DMODEL_DIR")

        if path is None:
            path = os.getenv("KICAD6_3DMODEL_DIR")

    return path
