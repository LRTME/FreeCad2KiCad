"""
    Module used for standalone plugin execution
"""

import wx

from kc_2_fc import Kc2Fc

app = wx.App()
window = Kc2Fc()
app.MainLoop()