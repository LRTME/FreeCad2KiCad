import Draft
import FreeCAD as App
import FreeCADGui as Gui
import Import
import ImportGui
import Part
import PartDesignGui
import Sketcher

from utils import *
from constants import SCALE, VEC


def scanFootprints(doc, pcb):
    """
    Scans data of all objects in FreeCAD and updates pcb dictionary
    :param doc: FreeCAD document object
    :param pcb: dict
    :return:
    """
    # TODO function need to get all properties of fp (getFPData) and calculate hash, then compare new hash to old
    #  to see if fp was changed. (like it is on KC side)
    # Footprint would need to contain all properties as it does in KC

    # TODO build a diff dictionary to send back to KiCAD

    pcb_id = pcb["general"]["pcb_id"]
    sketch = doc.getObject(f"Board_Sketch_{pcb_id}")
    footprint_list = pcb["footprints"]

    # Get FC object corresponding to pcb_id
    pcb_part = doc.getObject(pcb["general"]["pcb_name"] + f"_{pcb_id}")
    # Get footprints part container
    fps_parts = pcb_part.getObject(f"Footprints_{pcb_id}")

    # Go through top and bot footprint containers
    for fp_part in fps_parts.getObject(f"Top_{pcb_id}").Group + fps_parts.getObject(f"Bot_{pcb_id}").Group:

        # Get corresponding footprint in dictionary to be edited
        footprint = getDictEntryByKIID(footprint_list, fp_part.KIID)
        # Skip if failed to get footprint in dictionary
        if not footprint:
            continue

        # TODO check if diff before updating pos?
        # Update dictionary entry with new position coordinates
        footprint.update({"pos": toList(fp_part.Placement.Base)})

        # TODO update other properties
        # TODO handle rotation (move holes in sketch)
        # Model changes in FC are ignored (no KIID)


        # Get FC container Part where pad objects are stored
        pads_part = getPadContainer(fp_part)
        # Check if gotten pads part
        if not pads_part:
            continue

        # Go through pads
        for pad_part in pads_part.Group:
            # Get corresponding pad in dictionary to be edited
            pad = getDictEntryByKIID(footprint["pads_pth"], pad_part.KIID)
            # Get sketch geometry by Tag:
            # first get index (single entry in list) of pad geometry in sketch
            geom_index = getGeomsByTags(sketch, pad_part.Tags)[0]
            # get geometry by index
            pad_geom = sketch.Geometry[geom_index]
            # Check if gotten dict entry and sketch geometry
            if not pad and not pad_geom:
                continue

            # ----- If pad position delta was edited as vector attribute by user:  -----------
            # Compare dictionary deltas to property deltas
            if pad["pos_delta"] != toList(pad_part.PosDelta):
                # Update dictionary with new deltas
                pad.update({"pos_delta": toList(pad_part.PosDelta)})
                # Move geometry in sketch to new position
                sketch.movePoint(geom_index,  # Index of geometry
                                 3,           # Index of vertex (3 is center)
                                 fp_part.Placement.Base + pad_part.PosDelta)  # New position

            # ------- If pad was moved in sketch by user:  -----------------------------------
            # Check if pad is first pad of footprint (with relative pos 0)
            # -> this is footprint base, move only this hole because others are constrained to it
            if pad_part.PosDelta == App.Vector(0, 0, 0):
                # Get new footprint base
                new_base = pad_geom.Center
                # Compare geometry position with pad object position, if not same: sketch has been edited
                if new_base != pad_part.Placement.Base:
                    # Move footprint to new base position
                    fp_part.Placement.Base = new_base
                    # Update footprint dictionary entry with new position
                    footprint.update({"pos": toList(new_base)})

            # Update pad absolute placement property for all pads
            pad_part.Placement.Base = pad_geom.Center