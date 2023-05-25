
import json
import logging
import pcbnew
import pickle
import random
import time
import wx

from pcbnew_functions import *

SCALE = 1000000
"""
    Classes for generating GUI - Main window and Settings window
"""


class WxTextCtrlHandler(logging.Handler):
    def __init__(self, ctrl):
        logging.Handler.__init__(self)
        self.ctrl = ctrl

    def emit(self, record):
        s = self.format(record) + '\n'
        wx.CallAfter(self.ctrl.WriteText, s)


# ================================== Main window ================================== #
# noinspection PyUnusedLocal,PyMethodMayBeStatic
class Kc2FcGui(wx.Frame):

    def __init__(self, title):
        super().__init__(parent=None, title=title, style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER)

        self.logger = logging.getLogger(__name__)
        self.button_log_pressed = False

        # Socket config values are defined in GUI class, so they can be changed by GUI
        self.STARTING_PORT = 5050
        self.MAX_PORT_RANGE = 20
        self.host = 'localhost'  # This can be changed by user
        self.port = self.STARTING_PORT  # This can be changed by user
        self.port_is_manual = False
        self.HEADER = 8
        self.FORMAT = 'utf-8'

        self.initUI()
        self.Centre()
        self.Show()

    # --------------------------- User interface --------------------------- #
    def initUI(self):
        panel = wx.Panel(self)

        # Menu bar
        self.menubar = wx.MenuBar()
        self.file = wx.Menu()
        settings = self.file.Append(wx.ID_SETUP, "&Settings\tCtrl+S", "Open setting window")
        load = self.file.Append(wx.ID_FILE, "&Load\tCtrl+L", "Load test board")
        test = self.file.Append(wx.ID_ANY, "&Test\tCtrl+T")
        self.Bind(wx.EVT_MENU, self.openSettings, settings)
        self.Bind(wx.EVT_MENU, self.loadBoard, load)
        self.Bind(wx.EVT_MENU, self.testFunction, test)
        self.menubar.Append(self.file, "File")
        self.SetMenuBar(self.menubar)

        # Text
        text_log = wx.StaticText(panel, label="Log:", style=wx.ALIGN_LEFT)
        log = wx.TextCtrl(panel, wx.ID_ANY, size=(400, 200),
                          style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)

        # Buttons
        self.button_quit = wx.Button(panel, label="Quit")
        self.button_quit.Bind(wx.EVT_BUTTON, self.onButtonQuit)

        self.button_connect = wx.Button(panel, label="Connect")
        self.button_connect.Bind(wx.EVT_BUTTON, self.onButtonConnect)

        self.button_disconnect = wx.Button(panel, label="Disconnect")
        self.button_disconnect.Bind(wx.EVT_BUTTON, self.onButtonDisconnect)
        self.button_disconnect.Enable(False)

        self.button_send_message = wx.Button(panel, label="Send JSON")
        self.button_send_message.Bind(wx.EVT_BUTTON, self.onButtonSendMessage)
        self.button_send_message.Enable(False)

        self.button_scan_board = wx.Button(panel, label="Board to JSON")
        self.button_scan_board.Bind(wx.EVT_BUTTON, self.onButtonScanBoard)
        self.button_scan_board.Enable(True)

        self.button_get_diff = wx.Button(panel, label="Get diff")
        self.button_get_diff.Bind(wx.EVT_BUTTON, self.onButtonGetDiff)
        self.button_get_diff.Enable(True)

        # Socket control buttons
        socket_button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        socket_button_sizer.Add(self.button_connect, 0)
        socket_button_sizer.Add(self.button_disconnect, 0)
        # socket_button_sizer.Add(self.button_send_message, 0)
        # Add socket control buttons to static box
        socket_box = wx.StaticBoxSizer(wx.VERTICAL, panel, label="Socket")
        socket_box.Add(wx.StaticText(panel, label=""), 1, wx.ALL | wx.EXPAND)  # Blank space
        socket_box.Add(socket_button_sizer, 1, wx.CENTRE)  # Add button sizer as child of static box
        socket_box.Add(wx.StaticText(panel, label=""), 1, wx.ALL | wx.EXPAND)  # Blank space

        # Board control buttons
        board_button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        board_button_sizer.Add(self.button_scan_board, 0)
        board_button_sizer.Add(self.button_get_diff, 0)
        board_button_sizer.Add(self.button_send_message, 0)
        # Add board control buttons to static box
        board_box = wx.StaticBoxSizer(wx.VERTICAL, panel, label="PCB")
        board_box.Add(wx.StaticText(panel, label=""), 1, wx.ALL | wx.EXPAND)  # Blank space
        board_box.Add(board_button_sizer, 1, wx.CENTRE)  # Add pcb control button sizer to static box
        board_box.Add(wx.StaticText(panel, label=""), 1, wx.ALL | wx.EXPAND)  # Blank space

        # Bottom buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        # button_sizer.Add(self.button_scan_board, 0)
        button_sizer.AddStretchSpacer(1)
        button_sizer.Add(self.button_quit, 0, wx.ALIGN_LEFT, 20)

        # Main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(socket_box, 0, wx.ALL | wx.EXPAND, 5)  # Static box with start/stop buttons
        sizer.Add(board_box, 0, wx.ALL | wx.EXPAND, 5)  # Static box with pcb control buttons
        sizer.Add(text_log, 0, wx.ALL | wx.EXPAND, 0)  # Top text of vertical sizer
        sizer.Add(log, 1, wx.ALL | wx.EXPAND, 5)  # Add ctrl text
        sizer.Add(button_sizer, 0, wx.ALL | wx.EXPAND)  # Bottom buttons

        # Fit window to panel size
        panel.SetSizer(sizer)
        frameSizer = wx.BoxSizer()
        frameSizer.Add(panel, 0, wx.EXPAND)
        self.SetSizer(frameSizer)
        self.Fit()

        # Log text handler
        handler = WxTextCtrlHandler(log)
        self.logger.addHandler(handler)
        FORMAT_LONG = "%(asctime)s %(levelname)s %(message)s"
        FORMAT_SHORT = "%(levelname)s %(message)s"
        handler.setFormatter(logging.Formatter(FORMAT_SHORT))
        self.logger.setLevel(logging.INFO)

    # --------------------------- UI Methods --------------------------- #
    def testFunction(self, event):
        pass

    def onButtonConnect(self, event):
        pass

    def onButtonDisconnect(self, event):
        pass

    def onButtonSendMessage(self, event):
        pass

    def onButtonScanBoard(self, event):
        pass

    def onButtonGetDiff(self, event):
        pass

    def openSettings(self, event):
        self.settingsWindow = SettingsWindow(title="Settings", parent=self)

    def loadBoard(self, event):
        self.loadBoardFn()

    def loadBoardFn(self):
        try:
            # Load test board
            self.brd = pcbnew.LoadBoard("test_pcbs/test_pcb.kicad_pcb")
            file_name = self.brd.GetFileName()
            pcb_id = file_name.split('.')[0].split('/')[-1]
            self.logger.log(logging.INFO, f"Loaded pcb: {pcb_id}")
        except Exception as e:
            self.logger.exception(e)

    def updateHost(self, new_host):
        # Check if argument is the same as current host ip
        if not new_host == self.host:
            self.host = new_host
            self.logger.log(logging.INFO, f"Host IP changed to {self.host}")
            return 1
        else:
            return 0

    def updatePort(self, new_port, manual):
        # Check if port must be changed
        if manual and not new_port == self.port:
            try:
                # Check data type
                new_port = int(new_port)
                # Check value
                if 1024 < new_port < 64738:
                    self.port = new_port
                    self.logger.log(logging.INFO, f"Port changed to {self.port}")
                    self.port_is_manual = True
                    return 1  # Return used for evaluating if changes took place
                else:
                    self.logger.log(logging.ERROR, "Invalid requested port number!\n\
                    Please select integer between 1024 and 64738")
                    return 0

            except ValueError:
                self.logger.log(logging.ERROR, "Invalid port value")
                return 0

        elif manual and new_port == self.port:
            self.logger.log(logging.INFO, f"Port changed to {self.port}, manual")
            self.port_is_manual = True

        elif manual == self.port_is_manual:
            pass

        elif not manual:
            self.port = 5050
            self.logger.log(logging.INFO, f"Port selection automatic (Starting at: {self.port})")
            self.port_is_manual = False

    def onButtonQuit(self, event):
        # First close setting window
        try:
            self.settingsWindow.Close()
        except RuntimeError:
            # wrapped object has been deleted
            pass
        except AttributeError:
            # object has no attribute 'settingsWindow'
            pass

        self.Close()


# ================================== Settings window ================================== #
class SettingsWindow(wx.Frame):

    def __init__(self, title, parent):
        super().__init__(parent=None, title=title, style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER)

        # Parent attribute used for modifying .HOST and .PORT
        self.parent = parent
        self.changes_applied = False

        self.initUI()
        self.Centre()
        self.Show()

    # --------------------------- User interface --------------------------- #
    def initUI(self):
        self.panel = wx.Panel(self)

        # Buttons
        self.button_ok = wx.Button(self.panel, label="OK")
        self.button_ok.Bind(wx.EVT_BUTTON, self.onButtonOK)
        self.button_quit = wx.Button(self.panel, label="Quit")
        self.button_quit.Bind(wx.EVT_BUTTON, self.onButtonQuit)
        self.button_apply = wx.Button(self.panel, label="Apply")
        self.button_apply.Bind(wx.EVT_BUTTON, self.onButtonApply)
        # Add buttons to sizer
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.Add(self.button_ok, 0)
        button_sizer.AddStretchSpacer(1)
        button_sizer.Add(self.button_quit, 0, wx.ALIGN_LEFT, 20)
        button_sizer.Add(self.button_apply, 0)

        # Host control
        # When opening setting window, "localhost" is not displayed in textctrl
        if self.parent.host == "localhost":
            self.display_host_value = ""
            is_selected_host = False  # Var determines which button is selected
        # When opening setting window, custom value is displayed in textctrl
        else:
            self.display_host_value = self.parent.host
            is_selected_host = True

        self.text_host = wx.StaticText(self.panel, label="Host IP:",
                                       style=wx.ALIGN_LEFT)
        # Crate radiobuttons for localhost and custom value
        self.rb_host_local = wx.RadioButton(self.panel, label="Localhost", style=wx.RB_GROUP)
        self.rb_host_custom = wx.RadioButton(self.panel)
        # Create text for custom value input
        self.host_custom_value = wx.TextCtrl(self.panel, value=f"{self.display_host_value}")
        self.rb_host_custom.SetValue(is_selected_host)  # enable/disable button and text
        self.host_custom_value.Enable(is_selected_host)  # enable/disable button and text
        # Bind radiobuttons to functions to enable/disable textCtrl
        self.rb_host_custom.Bind(wx.EVT_RADIOBUTTON, self.onCustomHost)
        self.rb_host_local.Bind(wx.EVT_RADIOBUTTON, self.onDefaultHost)
        # Add button and text field to sizer
        rb_host_custom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        rb_host_custom_sizer.Add(self.rb_host_custom, 0)
        rb_host_custom_sizer.Add(self.host_custom_value, 0)
        # Add both radio buttons to vertical sizer
        rb_host_sizer = wx.BoxSizer(wx.VERTICAL)
        rb_host_sizer.Add(self.rb_host_local, 0)
        rb_host_sizer.Add(rb_host_custom_sizer, 0)
        # Add text and buttons for HOST control to single sizer
        host_sizer = wx.BoxSizer(wx.HORIZONTAL)
        host_sizer.Add(self.text_host, 0)
        host_sizer.AddStretchSpacer(1)
        host_sizer.Add(rb_host_sizer, 0)

        # Port control
        if not self.parent.port_is_manual:
            self.display_port_value = "5050"
            is_selected_port = False  # Var determines which button is selected
        else:
            self.display_port_value = self.parent.port
            is_selected_port = True

        self.text_port = wx.StaticText(self.panel, label="Port number:",
                                       style=wx.ALIGN_LEFT)
        # Create radiobuttons for auto and manual port selection
        self.rb_port_auto = wx.RadioButton(self.panel, label="Auto", style=wx.RB_GROUP)
        self.rb_port_manual = wx.RadioButton(self.panel)
        # Create text for custom value input
        self.port_custom_value = wx.TextCtrl(self.panel, value=f"{self.display_port_value}")
        self.rb_port_manual.SetValue(is_selected_port)  # enable/disable button and text
        self.port_custom_value.Enable(is_selected_port)  # enable/disable button and text
        # Bind radiobuttons to functions to enable/disable textCtrl
        self.rb_port_manual.Bind(wx.EVT_RADIOBUTTON, self.onCustomPort)
        self.rb_port_auto.Bind(wx.EVT_RADIOBUTTON, self.onDefaultPort)
        # Add button and text field to sizer
        rb_port_manual_sizer = wx.BoxSizer(wx.HORIZONTAL)
        rb_port_manual_sizer.Add(self.rb_port_manual, 0)
        rb_port_manual_sizer.Add(self.port_custom_value, 0)
        # Add both radio buttons to vertical sizer
        rb_port_sizer = wx.BoxSizer(wx.VERTICAL)
        rb_port_sizer.Add(self.rb_port_auto, 0)
        rb_port_sizer.Add(rb_port_manual_sizer, 0)
        # Add text and buttons for PORT control to single sizer
        port_sizer = wx.BoxSizer(wx.HORIZONTAL)
        port_sizer.Add(self.text_port, 0)
        port_sizer.AddStretchSpacer(1)
        port_sizer.Add(rb_port_sizer, 0, wx.ALIGN_LEFT, 20)

        # ------- Add host and port control to STATIC BOX -------
        socket_box = wx.StaticBoxSizer(wx.VERTICAL, self.panel, "Socket Configuration")
        socket_box.Add(wx.StaticText(self.panel, label=""), 1, wx.ALL | wx.EXPAND)  # Blank space
        socket_box.Add(host_sizer, 1, wx.ALL | wx.EXPAND)  # Add IP selection
        socket_box.Add(wx.StaticText(self.panel, label=""), 1, wx.ALL | wx.EXPAND)  # Blank space
        socket_box.Add(port_sizer, 1, wx.ALL | wx.EXPAND)  # Add port selection as child of static box
        socket_box.Add(wx.StaticText(self.panel, label=""), 1, wx.ALL | wx.EXPAND)  # Blank space

        # Main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(socket_box, 0, wx.ALL | wx.EXPAND, 5)
        sizer.Add(button_sizer, 0, wx.ALL | wx.EXPAND)

        # Fit window to panel size
        self.panel.SetSizer(sizer)
        frameSizer = wx.BoxSizer()
        frameSizer.Add(self.panel, 0, wx.EXPAND)
        self.SetSizer(frameSizer)
        self.Fit()

    # --------------------------- UI methods --------------------------- #
    def onButtonOK(self, event):
        if not self.changes_applied:
            self.applyChanges()
        # OK button doesn't close window if changes failed to apply
        if self.changes_applied:
            self.Close()

    def onButtonQuit(self, event):
        self.Close()

    def onButtonApply(self, event):
        self.applyChanges()

    def applyChanges(self):
        # If radiobutton for custom value is selected, get new host value
        if self.rb_host_custom.GetValue():
            new_host = self.host_custom_value.GetValue()
        else:
            new_host = "localhost"

        if self.rb_port_manual.GetValue():
            port_manual = True
            new_port = self.port_custom_value.GetValue()
            self.parent.logger.log(logging.INFO, f"I got new value: {new_port}, manual: {port_manual}")
        else:
            port_manual = False
            new_port = 5050

        self.parent.updateHost(new_host)
        self.parent.updatePort(new_port, port_manual)
        self.changes_applied = True

    # Functions for toggling radiobutton custom value visibility
    def onCustomHost(self, event):
        self.host_custom_value.Enable(True)

    def onDefaultHost(self, event):
        self.host_custom_value.Enable(False)

    def onCustomPort(self, event):
        self.port_custom_value.Enable(True)

    def onDefaultPort(self, event):
        self.port_custom_value.Enable(False)