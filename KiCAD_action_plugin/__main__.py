"""
    Module used for standalone plugin execution
"""

import wx

from plugin import Plugin

app = wx.App()
window = Plugin()
app.MainLoop()