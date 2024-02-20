""" Standard action plugin structure. """

import logging
import os
import pcbnew
import sys
import wx


# noinspection PyAttributeOutsideInit,PyPep8Naming
class PluginAction(pcbnew.ActionPlugin):

    def defaults(self):
        self.name = "KiCAD To FreeCAD"
        self.category = ""
        self.description = "ECAD to MCAD synchronization"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), 'icon.png')

    # noinspection PyMethodMayBeStatic
    def Run(self):
        from .plugin import Plugin

        # Instantiate and run plugin
        app = wx.App()
        window = Plugin()
        app.MainLoop()
