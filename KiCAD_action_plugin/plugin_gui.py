"""
    Classes for generating GUI - Main window and Settings window
"""

import logging
import wx


class WxTextCtrlHandler(logging.Handler):
    """ Class for displaying console_logger messages to wx.TextCtrl window. """
    def __init__(self, ctrl):
        logging.Handler.__init__(self)
        self.ctrl = ctrl

    def emit(self, record):
        """ Update text control on GUI after log event. """
        s = self.format(record) + '\n'
        wx.CallAfter(self.ctrl.WriteText, s)


# GUI class
# noinspection PyAttributeOutsideInit
class PluginGui(wx.Frame):
    """ GUI class, subclassed by main plugin. """

    def __init__(self, title):
        super().__init__(parent=None, title=title, style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER)

        # Temp var used for moving fp left and right to test diff
        self.odd_even_var = 0

        self.init_ui()
        self.Centre()
        self.Show()

    # --------------------------- User interface --------------------------- #
    def init_ui(self):
        """ Set up buttons and text. """

        panel = wx.Panel(self)

        # Menu bar
        self.menubar = wx.MenuBar()
        self.file = wx.Menu()
        self.menubar.Append(self.file, "File")
        self.SetMenuBar(self.menubar)

        # Console output
        text_log = wx.StaticText(panel, label="Log:", style=wx.ALIGN_LEFT)
        console = wx.TextCtrl(panel, wx.ID_ANY, size=(400, 200),
                              style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
        # Console logger
        self.console_logger = logging.getLogger("console-gui")
        console_handler = WxTextCtrlHandler(console)
        self.console_logger.addHandler(console_handler)
        format_short = "%(levelname)s %(message)s"
        console_handler.setFormatter(logging.Formatter(format_short))
        self.console_logger.setLevel(logging.INFO)

        # Buttons
        self.button_quit = wx.Button(panel, label="Quit")
        self.button_quit.Bind(wx.EVT_BUTTON, self.on_button_quit)

        self.button_connect = wx.Button(panel, label="Connect")
        self.button_connect.Bind(wx.EVT_BUTTON, self.on_button_connect)

        self.button_disconnect = wx.Button(panel, label="Disconnect")
        self.button_disconnect.Bind(wx.EVT_BUTTON, self.on_button_disconnect)
        self.button_disconnect.Enable(False)

        # Socket control buttons
        socket_button_sizer = wx.BoxSizer()
        socket_button_sizer.Add(self.button_connect, 0)
        socket_button_sizer.Add(self.button_disconnect, 0)
        # Add Socket control buttons to static box
        socket_box = wx.StaticBoxSizer(wx.VERTICAL, panel, label="Socket")
        socket_box.Add(wx.StaticText(panel, label=""), 1, wx.ALL | wx.EXPAND)  # Blank space
        socket_box.Add(socket_button_sizer, 1, wx.CENTRE)  # Add button sizer as child of static box
        socket_box.Add(wx.StaticText(panel, label=""), 1, wx.ALL | wx.EXPAND)  # Blank space

        # Bottom buttons
        button_sizer = wx.BoxSizer()
        # button_sizer.Add(self.button_scan_board, 0)
        button_sizer.AddStretchSpacer()
        button_sizer.Add(self.button_quit, 0, wx.ALIGN_LEFT, 20)

        # Main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(socket_box, 0, wx.ALL | wx.EXPAND, 5)  # Static box with start/stop buttons
        sizer.Add(text_log, 0, wx.ALL | wx.EXPAND, 0)  # Top text of vertical sizer
        sizer.Add(console, 1, wx.ALL | wx.EXPAND, 5)  # Add ctrl text
        sizer.Add(button_sizer, 0, wx.ALL | wx.EXPAND)  # Bottom buttons

        # Fit window to panel size
        panel.SetSizer(sizer)
        frame_sizer = wx.BoxSizer()
        frame_sizer.Add(panel, 0, wx.EXPAND)
        self.SetSizer(frame_sizer)
        self.Fit()

    # noinspection PyUnusedLocal
    def on_button_quit(self, event):
        """ Function must accept event argument to be triggered. """
        self.Close()

    def on_button_connect(self, event):
        """ Method for override. """
        pass

    def on_button_disconnect(self, event):
        """ Method for override. """
        pass
