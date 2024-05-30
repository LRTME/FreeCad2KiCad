"""
    Module used for standalone plugin execution
"""

import wx

from KiCAD_action_plugin.Main.kc_plugin_class import KcPlugin

app = wx.App()
window = KcPlugin()
app.MainLoop()