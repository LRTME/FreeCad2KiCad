""" Scale is convertion between nanometers and milimeters, VEC are often used FreeCAD vectors. """
import FreeCAD as App

SCALE = 1000000

# Dictionary of rotations vectors
VEC = {"x": App.Vector(1, 0, 0),
       "y": App.Vector(0, 1, 0),
       "z": App.Vector(0, 0, 1),
       "0": App.Vector(0, 0, 0)}