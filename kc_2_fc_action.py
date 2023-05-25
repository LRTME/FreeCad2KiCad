import logging
import os
import pcbnew
import sys
import wx


class Kc2FcAction(pcbnew.ActionPlugin):

    def defaults(self):
        self.name = "KiCAD To FreeCAD"
        self.category = ""
        self.description = "ECAD to MCAD synchronization"
        self.show_toolbar_button = True  # Optional, defaults to False
        self.icon_file_name = os.path.join(os.path.dirname(__file__), 'icon.png')  # Optional

    # noinspection PyMethodMayBeStatic
    def Run(self):
        from .kc_2_fc import Kc2Fc

        # Instantiate and run plugin
        app = wx.App()
        window = Kc2Fc()
        app.MainLoop()