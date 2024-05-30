"""
    Module used for registering action plugin
"""

import os
import sys

from KiCAD_action_plugin.Main.plugin_action import PluginAction  # Note the relative import!

# For relative imports to work in Python 3.6
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

PluginAction().register()  # Instantiate and register to Pcbnew