""" Helper functions for getting objects by IDs, and converting to/from FC vectors. """

import FreeCAD as App
import Sketcher
import math
from API_scripts.constants import SCALE


def get_part_by_kiid(doc: App.Document, kiid: str) -> App.Part:
    """ Returns FreeCAD Part object with same KIID attribute. """
    result = None

    for obj in doc.Objects:
        try:
            if obj.KIID == kiid:
                result = obj
                break
        except AttributeError:
            pass

    return result


def get_dict_entry_by_kiid(list_of_entries: list, kiid: str) -> dict:
    """ Returns entry in dictionary with same KIID value. """
    result = None

    for entry in list_of_entries:
        if entry.get("kiid"):
            if entry["kiid"] == kiid:
                result = entry

    return result


def get_geoms_by_tags(sketch: Sketcher.Sketch, tags: list) -> list:
    """ Get list of indexes of geometries and actual geometry object in sketch with same Tags. """
    indexes = []
    # Go through geometries of sketch end find geoms with same tag
    for i, geom in enumerate(sketch.Geometry):
        for tag in tags:
            if geom.Tag == tag:
                indexes.append(i)

    return indexes


def get_model_by_id(list_of_models: list, model_id: str) -> dict:
    """ Return dict model data. """
    result = None

    for model in list_of_models:
        if model["model_id"] == model_id:
            result = model

    return result


def get_pad_container(parent: App.Part) -> App.Part:
    """ Returns child FC Part container of parent with Pads in the label. """
    pads = None
    # Go through children of fp_part to find Pads part
    for child in parent.Group:
        if "Pads" in child.Label:
            pads = child

    return pads


def to_list(vec: App.Vector) -> list:
    """ Convert FreeCAD vector in millimeters to a two element list [x, y] in nanometers. """
    return [int(vec[0] * SCALE),
            int(-vec[1] * SCALE)]


def freecad_vector(coordinates: list) -> App.Vector:
    """ Convert two element list in nanometers to a FreeCAD.Vector type in millimeters. """
    return App.Vector(coordinates[0] / SCALE,
                      -coordinates[1] / SCALE,
                      0)


def rotate_vector(vector: App.Vector, angle: float) -> App.Vector:
    """ Return FreeCAD.Vector rotated by an angle. """
    x = vector[0] * math.cos(angle) - vector[1] * math.sin(angle)
    y = vector[0] * math.sin(angle) + vector[1] * math.cos(angle)
    # Convert new coordinates to FreeCAD vector object
    return freecad_vector([x, y])


def get_constraint_by_tag(sketch, tag):
    """
    Get dictionary of constraint indexes of geometry properties based on geometry Tag
    :param sketch: Sketcher::Sketch object
    :param tag: string (geometry.Tag)
    :return: dictionary of indexes as values
    """
    result = {}
    for i, c in enumerate(sketch.Constraints):
        if tag not in c.Name:
            continue

        if "radius" in c.Name:
            result.update({"radius": i})
        elif "distance_x" in c.Name:
            result.update({"dist_x": i})
        elif "distance_y" in c.Name:
            result.update({"dist_y": i})

    return result
