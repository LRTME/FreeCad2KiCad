import FreeCAD as App
import FreeCADGui as Gui

SCALE = 1000000


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
    """Get list of indexes of geometries in sketch with same Tag"""
    indexes = []
    # Go through geomtries of sketch end find geoms with same tag
    for i, geom in enumerate(sketch.Geometry):
        for tag in tags:
            if geom.Tag == tag:
                indexes.append(i)

    return indexes


def getPadContainer(parent):
    """Returns child FC Part container of parent with Pads in the label"""
    pads = None
    # Go through childer of fp_part to find Pads part
    for child in parent.Group:
        if "Pads" in child.Label:
            pads = child

    return pads


def toList(vec):
    return [vec[0] * SCALE,
            -vec[1] * SCALE]


def toVector(list):
    return App.Vector(list[0] / SCALE,
                      -list[1] / SCALE,
                      0)