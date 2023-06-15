from utils import relativeModelPath

"""
    Functions for "scanning" elements (and their properties) of pcbnew.Board
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


def getViaData(track):
    return {
        "center": [track.GetX(),
                   track.GetY()
                   ],
        "radius": track.GetDrill(),
    }