""" Standard action plugin structure. """

import os
import pcbnew
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
        from KiCAD_action_plugin.Main.kc_plugin_class import KcPlugin

        KcPlugin()
        wx.App().MainLoop()
