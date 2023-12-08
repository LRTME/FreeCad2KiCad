
"""
    Helper functions for getting objects by IDs, and converting to/from FC vectors
"""


import FreeCAD as App

import math

from API_scripts.constants import SCALE



def getPartByKIID(doc, kiid):
    """Returns FreeCAD Part object with same KIID attribute"""
    result = None

    for obj in doc.Objects:
        try:
            if obj.KIID == kiid:
                result = obj
                break
        except AttributeError:
            pass

    return result


def getDictEntryByKIID(list, kiid):
    """Returns entry in dictionary with same KIID value"""
    result = None

    for entry in list:
        if entry.get("kiid"):
            if entry["kiid"] == kiid:
                result = entry

    return result


def getGeomsByTags(sketch, tags):
    """Get list of indexes of geometries and actual geometry object in sketch with same Tags"""
    indexes = []
    # Go through geometries of sketch end find geoms with same tag
    for i, geom in enumerate(sketch.Geometry):
        for tag in tags:
            if geom.Tag == tag:
                indexes.append(i)

    return indexes


def getModelById(list, model_id):
    """Return dict model data"""
    result = None

    for model in list:
        if model["model_id"] == model_id:
            result = model

    return result


def getPadContainer(parent):
    """Returns child FC Part container of parent with Pads in the label"""
    pads = None
    # Go through childer of fp_part to find Pads part
    for child in parent.Group:
        if "Pads" in child.Label:
            pads = child

    return pads


def toList(vec):
    return [int(vec[0] * SCALE),
            int(-vec[1] * SCALE)]


def FreeCADVector(list):
    return App.Vector(list[0] / SCALE,
                      -list[1] / SCALE,
                      0)


def rotateVector(vector, angle):
    x = vector[0] * math.cos(angle) - vector[1] * math.sin(angle)
    y = vector[0] * math.sin(angle) + vector[1] * math.cos(angle)
    # Convert new coordinates to FreeCAD vector object
    return FreeCADVector([x, y])