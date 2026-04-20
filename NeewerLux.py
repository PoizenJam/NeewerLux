#!/usr/bin/python3
#############################################################
## NeewerLux ver. 1.0.5
NEEWERLUX_VERSION = "1.0.6"
NEEWERLUX_REPO_URL = "https://github.com/poizenjam/NeewerLux/"
NEEWERLUX_RELEASES_API = "https://api.github.com/repos/poizenjam/NeewerLux/releases/latest"
## A NeewerLite-Python Extension
############################################################
## Based on NeewerLite-Python ver. 0.12d by Zach Glenwright
## > https://github.com/taburineagle/NeewerLite-Python/ <
##
## Which is based on the NeewerLite project by Xu Lian (@keefo)
## > https://github.com/keefo/NeewerLite <
############################################################
## A cross-platform Python script using the bleak and
## PySide6 (or PySide2) libraries to control Neewer brand lights via
## Bluetooth on multiple platforms -
##          Windows, Linux/Ubuntu, MacOS and RPi
############################################################

import os
import sys

# When launched via pythonw.exe or .pyw, stdout/stderr are None.
# Redirect to devnull so print() calls don't crash.
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

import math # used for calculating the RGB values of color temperatures
import json # used for animation files and HTTP batch/animation APIs
import tempfile
import faulthandler
import warnings
faulthandler.enable() # print traceback on segfault/C++ crashes
warnings.filterwarnings("ignore", category=FutureWarning, message=".*BLEDevice.rssi.*")  # suppress Bleak deprecation noise

import argparse
import platform # used to determine which OS we're using for MAC address/GUID listing

import asyncio
import threading
import time

from datetime import datetime

# IMPORT BLEAK (this is the library that allows the program to communicate with the lights) - THIS IS NECESSARY!
try:
    from bleak import BleakScanner, BleakClient
except ModuleNotFoundError as e:
    print(" ===== CAN NOT FIND BLEAK LIBRARY =====")
    print(" You need the bleak Python package installed to use NeewerLux.")
    print(" Bleak is the library that connects the program to Bluetooth devices.")
    print(" Please install the Bleak package first before running NeewerLux.")
    print()
    print(" To install Bleak, run either pip or pip3 from the command line:")
    print("    pip install bleak")
    print("    pip3 install bleak")
    print()
    print(" Or visit this website for more information:")
    print("    https://pypi.org/project/bleak/")
    sys.exit(1) # you can't use the program itself without Bleak, so kill the program if we don't have it

# IMPORT THE WINDOWS LIBRARY (needed for older bleak versions on Windows; newer bleak handles this internally)
if platform.system() == "Windows":
    try:
        from winrt import _winrt
        _winrt.uninit_apartment()
    except Exception:
        try:
            # Newer winrt package structure (winrt-runtime)
            import winrt.system
        except Exception:
            pass # modern bleak (0.20+) handles COM apartment threading internally

importError = 0 # whether or not there's an issue loading PySide6/PySide2 or the GUI file
PYSIDE_VERSION = 0

# IMPORT PYSIDE6 (preferred, actively maintained) OR PYSIDE2 (legacy fallback)
try:
    import PySide6
    from PySide6.QtCore import Qt, QItemSelectionModel, Signal as QtSignal
    from PySide6.QtGui import QLinearGradient, QColor, QKeySequence, QFont, QIcon, QShortcut
    from PySide6.QtWidgets import QApplication, QMainWindow, QTableWidgetItem, QMessageBox, QInputDialog, QListWidgetItem, QSizePolicy, QPushButton
    PYSIDE_VERSION = 6

except Exception as e:
    print(f"  [DEBUG] PySide6 import failed: {type(e).__name__}: {e}")
    try:
        import PySide2
        from PySide2.QtCore import Qt, QItemSelectionModel, Signal as QtSignal
        from PySide2.QtGui import QLinearGradient, QColor, QKeySequence, QFont, QIcon
        from PySide2.QtWidgets import QApplication, QMainWindow, QTableWidgetItem, QShortcut, QMessageBox, QInputDialog, QListWidgetItem, QSizePolicy, QPushButton
        PYSIDE_VERSION = 2
    except Exception as e2:
        print(f"  [DEBUG] PySide2 import failed: {type(e2).__name__}: {e2}")
        importError = 1 # log that we can't find either PySide version

# IMPORT THE GUI ITSELF
try:
    from neewerlux_ui import Ui_MainWindow
    from neewerlux_theme import getThemeQSS
    from neewerlux_webui import getWebDashboardHTML
except Exception as e:
    print(f"  [DEBUG] GUI module import failed: {type(e).__name__}: {e}")
    if importError != 1: # if we don't already have a PySide issue
        importError = 2 # log that we can't find the GUI file - which, if the program is downloaded correctly, shouldn't be an issue

# IMPORT SYSTEM TRAY SUPPORT
try:
    from neewerlux_ui import QSystemTrayIcon, QMenu
except ImportError:
    QSystemTrayIcon = None
    QMenu = None

# SET WINDOWS APP ID SO THE TASKBAR SHOWS OUR ICON INSTEAD OF PYTHON'S
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("poizenjam.NeewerLux.1.0.0")
except Exception:
    pass  # not Windows

# CONSOLE MANAGEMENT
# When launched via pythonw.exe (or NeewerLux.bat), there is no console — these are no-ops.
# When launched via python.exe directly, SW_HIDE works on legacy conhost but NOT on
# Windows Terminal (which intercepts and downgrades to minimize).
_hasConsole = False
try:
    import ctypes
    import ctypes.wintypes as wintypes
    ctypes.windll.kernel32.GetConsoleWindow.restype = wintypes.HWND
    ctypes.windll.user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    ctypes.windll.user32.ShowWindow.restype = wintypes.BOOL
    _consoleHwnd = ctypes.windll.kernel32.GetConsoleWindow()
    _hasConsole = bool(_consoleHwnd)
except Exception:
    _consoleHwnd = 0

def hideConsoleWindow():
    if _consoleHwnd:
        try:
            ctypes.windll.user32.ShowWindow(_consoleHwnd, 0)  # SW_HIDE
        except Exception:
            pass

def showConsoleWindow():
    if _consoleHwnd:
        try:
            ctypes.windll.user32.ShowWindow(_consoleHwnd, 5)  # SW_SHOW
        except Exception:
            pass

# IMPORT THE HTTP SERVER
try:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import urllib.parse # parsing custom light names in the HTTP server
except Exception as e:
    pass # if there are any HTTP errors, don't do anything yet

# IMPORT WEB DASHBOARD
try:
    from neewerlux_webui import getWebDashboardHTML
except ImportError:
    getWebDashboardHTML = None

# HELPER: PySide6 uses .exec(), PySide2 uses .exec_() — this calls the right one
def pyside_exec(obj):
    if hasattr(obj, 'exec'):
        return obj.exec()
    else:
        return obj.exec_()

# HELPER: Resolve resource file paths — works both in normal Python and PyInstaller frozen EXE.
# PyInstaller extracts bundled data files to sys._MEIPASS; in normal Python, use script directory.
def _resource_path(filename):
    """Return the absolute path to a bundled resource file."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), filename)

# Are we running as a frozen PyInstaller EXE?
_isFrozenExe = getattr(sys, 'frozen', False)

CCTSlider = -1 # the current slider moved in the CCT window - 1 - Brightness / 2 - Hue / -1 - Both Brightness and Hue
sendValue = [120, 135, 2, 20, 56, 157] # an array to hold the values to be sent to the light - the default is CCT / 5600K / 20%
lastAnimButtonPressed = 1 # which animation button you clicked last - if none, then it defaults to 1 (the police sirens)
lastSelection = [] # the current light selection (this is for snapshot preset entering/leaving buttons)
lastSortingField = -1 # the last field used for sorting purposes

availableLights = [] # the list of Neewer lights currently available to control
# List Subitems (for ^^^^^^):
# [0] - Bleak Scan Object (can use .name / .address to get specifics; RSSI stored separately at index [9])
# [1] - Bleak Connection (the actual Bluetooth connection to the light itself)
# [2] - Custom Name for Light (string)
# [3] - Last Used Parameters (list)
# [4] - The range of color temperatures to use in CCT mode (list, min, max) <- changed in 0.12
# [5] - Whether or not to send Brightness and Hue independently for old lights (boolean)
# [6] - Whether or not this light has been manually turned ON/OFF (boolean)
# [7] - The Power and Channel data returned for this light (list)
# [8] - Preferred ID for sorting (int)
# [9] - Last known RSSI value in dBm (int or str "?")

# Light Preset ***Default*** Settings (for sections below):
# NOTE: The list is 0-based, so the preset itself is +1 from the subitem
# [0] - [CCT mode] - 5600K / 20%
# [1] - [CCT mode] - 3200K / 20%
# [2] - [CCT mode] - 5600K / 0% (lights are on, but set to 0% brightness)
# [3] - [HSI mode] - 0° hue / 100% saturation / 20% intensity (RED)
# [4] - [HSI mode] - 240° hue / 100% saturation / 20% intensity (BLUE)
# [5] - [HSI mode] - 120° hue / 100% saturation / 20% intensity (GREEN)
# [6] - [HSI mode] - 300° hue / 100% saturation / 20% intensity (PURPLE)
# [7] - [HSI mode] - 160° hue / 100% saturation / 20% intensity (CYAN)

# The 8 factory default presets (always available as a fallback)
factoryDefaultPresets = [
    [[-1, [5, 20, 56]]],
    [[-1, [5, 20, 32]]],
    [[-1, [5, 0, 56]]],
    [[-1, [4, 20, 0, 100]]],
    [[-1, [4, 20, 240, 100]]],
    [[-1, [4, 20, 120, 100]]],
    [[-1, [4, 20, 300, 100]]],
    [[-1, [4, 20, 160, 100]]]    
    ]

numOfPresets = 8 # how many presets are active (can grow beyond 8)
presetNames = {} # dict of {preset_index: "custom name"} for user-assigned names

# ============================================================================
# CUSTOM ANIMATION SYSTEM
# ============================================================================
animationRunning = False       # whether an animation is currently playing
animationStopFlag = False      # set True to request the animation to stop
_animChainStop = False         # set True when stopping to chain into another animation (skip revert)
currentAnimationName = ""      # name of the currently playing animation
savedAnimations = {}           # dict of {name: animation_dict} loaded from disk
animationsDir = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep + "light_prefs" + os.sep + "animations"
lightAliases = {}  # {MAC: {"id": int, "name": str}} — built from per-light prefs sidecar files
workerWakeEvent = threading.Event()  # signaled by animation thread to wake the worker immediately
animParallelWrites = True  # send BLE commands to all lights simultaneously during animations
animRevertOnFinish = True  # revert lights to pre-animation state when a non-looping animation finishes
preAnimationStates = {}    # {light_index: byte_list} saved before animation starts

# HTTP SERVER (GUI-LAUNCHED) MANAGEMENT
httpServerInstance = None   # ThreadingHTTPServer object (when running from GUI)
httpServerThread = None     # daemon thread running serve_forever()
httpServerRunning = False   # flag for UI state

def getDefaultPreset(index):
    """Return the factory default for a given preset index, cycling through the 8 built-in defaults."""
    return factoryDefaultPresets[index % len(factoryDefaultPresets)]

def buildDefaultPresets(count):
    """Build a list of default presets of the given length."""
    return [getDefaultPreset(i) for i in range(count)]

# The list of **default** light presets for restoring and checking against
defaultLightPresets = buildDefaultPresets(numOfPresets)

# A list of preset mode settings - custom file will overwrite
customLightPresets = buildDefaultPresets(numOfPresets)

threadAction = "" # the current action to take from the thread
mainWindow = None  # the GUI main window (None in HTTP-only mode)
asyncioEventLoop = None # the current asyncio loop

setLightUUID = "69400002-B5A3-F393-E0A9-E50E24DCCA99" # the UUID to send information to the light
notifyLightUUID = "69400003-B5A3-F393-E0A9-E50E24DCCA99" # the UUID for notify callbacks from the light

receivedData = "" # the data received from the Notify characteristic

# SET FROM THE PREFERENCES FILE ON LAUNCH
findLightsOnStartup = True # whether or not to look for lights when the program starts
autoConnectToLights = True # whether or not to auto-connect to lights after finding them
printDebug = True # show debug messages in the console for all of the program's events
maxNumOfAttempts = 6 # the maximum attempts the program will attempt an action before erroring out
rememberLightsOnExit = False # whether or not to save the currently set light settings (mode/hue/brightness/etc.) when quitting out
rememberPresetsOnExit = True # whether or not to save the custom preset list when quitting out
livePreview = True # whether sliders send values in real-time or require clicking Apply
hideConsoleOnLaunch = False # whether to auto-hide the console window on GUI startup
minimizeToTrayOnClose = True # whether closing the window minimizes to tray (True) or quits (False)
httpAutoStart = False # whether to automatically start the HTTP server on launch
cctFallbackMode = "convert" # how to handle HSI/ANM commands sent to CCT-only lights: "ignore" or "convert"
enableLogTab = True # whether to show and populate the Log tab
logToFile = False # whether to also write log entries to a file
globalCCTMin = 3200 # global default minimum color temperature (K)
globalCCTMax = 5600 # global default maximum color temperature (K)
autoReconnectOnDisconnect = True # whether or not to automatically try reconnecting to lights that disconnect (e.g. after sleep/wake)
acceptable_HTTP_IPs = [] # the acceptable IPs for the HTTP server, set on launch by prefs file
customKeys = [] # custom keymappings for keyboard shortcuts, set on launch by the prefs file
whiteListedMACs = [] # whitelisted list of MAC addresses to add to NeewerLux
enableTabsOnLaunch = False # whether or not to enable tabs on startup (even with no lights connected)

lockFile = tempfile.gettempdir() + os.sep + "NeewerLux.lock"
anotherInstance = False # whether or not we're using a new instance (for the Singleton check)
globalPrefsFile = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep + "light_prefs" + os.sep + "NeewerLux.prefs" # the global preferences file for saving/loading
customLightPresetsFile = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep + "light_prefs" + os.sep + "customLights.prefs"
geometryPrefsFile = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep + "light_prefs" + os.sep + "NeewerLux.geometry"
logFilePath = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep + "light_prefs" + os.sep + "NeewerLux.log"

# FILE LOCKING FOR SINGLE INSTANCE
def singleInstanceLock():
    global anotherInstance

    try:
        lf = os.open(lockFile, os.O_WRONLY | os.O_CREAT | os.O_EXCL) # try to get a file spec to lock the "running" instance

        with os.fdopen(lf, 'w') as lockfile:
            lockfile.write(str(os.getpid())) # write the PID of the current running process to the temporary lockfile
    except (IOError, OSError): # if we had an error acquiring the file descriptor, the file most likely already exists.
        # CHECK IF THE EXISTING LOCK FILE IS STALE (process no longer running)
        try:
            with open(lockFile, 'r') as f:
                oldPid = int(f.read().strip())

            # Check if the process with that PID is still alive
            pidAlive = False
            if oldPid == os.getpid():
                pidAlive = False  # it's our own stale lock from a crash
            elif sys.platform == "win32":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                # Use PROCESS_QUERY_LIMITED_INFORMATION to check if process is truly alive
                handle = kernel32.OpenProcess(0x1000, False, oldPid)
                if handle:
                    # Check exit code — STILL_ACTIVE (259) means genuinely running
                    exitCode = ctypes.c_ulong()
                    if kernel32.GetExitCodeProcess(handle, ctypes.byref(exitCode)):
                        pidAlive = (exitCode.value == 259)  # 259 = STILL_ACTIVE
                    kernel32.CloseHandle(handle)
            else:
                try:
                    os.kill(oldPid, 0) # signal 0 doesn't kill — just checks if PID exists
                    pidAlive = True
                except OSError:
                    pidAlive = False

            if pidAlive:
                anotherInstance = True # genuinely another instance running
            else:
                # Stale lock file — remove it and create a fresh one
                print("Found stale lock file (PID " + str(oldPid) + " is no longer running). Cleaning up...")
                os.remove(lockFile)
                lf = os.open(lockFile, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
                with os.fdopen(lf, 'w') as lockfile:
                    lockfile.write(str(os.getpid()))
        except (ValueError, IOError, OSError):
            # Lock file exists but can't be read or PID is invalid — remove and recreate
            try:
                os.remove(lockFile)
                lf = os.open(lockFile, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
                with os.fdopen(lf, 'w') as lockfile:
                    lockfile.write(str(os.getpid()))
            except (IOError, OSError):
                anotherInstance = True # truly can't acquire the lock
    
def singleInstanceUnlockandQuit(exitCode):
    # Flush any buffered log entries before exiting
    if _logBuffer:
        try:
            with open(logFilePath, "a", encoding="utf-8") as f:
                f.write("\n".join(_logBuffer) + "\n")
            _logBuffer.clear()
        except Exception:
            pass

    try:
        os.remove(lockFile) # try to delete the lockfile on exit
    except FileNotFoundError: # if another process deleted it, then just error out
        printDebugString("Lockfile not found in temp directory, so we're going to skip deleting it!")

    sys.exit(exitCode) # quit out, with the specified exitCode
    # If sys.exit was somehow caught, force-kill the process
    os._exit(exitCode)

def doAnotherInstanceCheck():
    if anotherInstance == True: # if we're running a 2nd instance, but we shouldn't be
        print("You're already running another instance of NeewerLux.")
        print("Please close that copy first before opening a new one.")
        print()
        print("To force opening a new instance, add --force_instance to the command line.")
        sys.exit(1)

try: # try to load the GUI
    class MainWindow(QMainWindow, Ui_MainWindow):
        # Thread-safe signal for updating the light table from background threads
        _tableUpdateSignal = QtSignal(list, int)
        # Thread-safe signal for update check results
        _updateResultSignal = QtSignal(str, str, str, str)
        # Thread-safe signal for appending log messages from any thread
        _logSignal = QtSignal(str)

        def __init__(self):
            QMainWindow.__init__(self)
            self.setupUi(self) # set up the main UI
            self.connectMe() # connect the function handlers to the widgets

            # Connect the thread-safe table update signal
            self._tableUpdateSignal.connect(self.setTheTable)

            # Connect the log signal and log tab buttons
            self._logSignal.connect(self._appendLog)
            self.logClearButton.clicked.connect(lambda: self.logTextEdit.clear())
            self.logSaveButton.clicked.connect(self._saveLogToFile)

            # Connect update check button and result signal
            self.checkUpdateButton.clicked.connect(self._checkForUpdates)
            self._updateResultSignal.connect(self._onUpdateResult)

            # Initialize theme (dark by default)
            self._isDarkTheme = True
            self._forceQuit = False
            QApplication.instance().setStyleSheet(getThemeQSS(True))
            self.themeToggleBtn.setText("\u263E")  # moon symbol

            # Set window icon (shown in taskbar and title bar)
            for _iconName in ("com.github.poizenjam.NeewerLux.png", "com.github.poizenjam.NeewerLux.ico"):
                _iconPath = _resource_path(_iconName)
                if os.path.exists(_iconPath):
                    self.setWindowIcon(QIcon(_iconPath))
                    break

            # Set up system tray icon (minimize to tray on close)
            self.setupSystemTray()

            if enableTabsOnLaunch == False: # if we're not supposed to enable tabs on launch, then disable them all
                self.ColorModeTabWidget.setTabEnabled(0, False) # disable the CCT tab on launch
                self.ColorModeTabWidget.setTabEnabled(1, False) # disable the HSI tab on launch
                self.ColorModeTabWidget.setTabEnabled(2, False) # disable the SCENE tab on launch
                # Animations tab (index 3) is always enabled — no light selection needed
                self.ColorModeTabWidget.setTabEnabled(4, False) # disable the LIGHT PREFS tab on launch
                self.ColorModeTabWidget.setCurrentIndex(6)  # default to Info tab

            if findLightsOnStartup == True: # if we're set up to find lights on startup, then indicate that
                self.statusBar.showMessage("Please wait - searching for Neewer lights...")
            else:
                self.statusBar.showMessage("Welcome to NeewerLux!  Hit the Scan button above to scan for lights.")

            if platform.system() == "Darwin": # if we're on MacOS, then change the column text for the 2nd column in the light table
                self.lightTable.horizontalHeaderItem(1).setText("Light UUID")

            # CREATE AND MARK ALL PRESET BUTTONS DYNAMICALLY
            self.createPresetButtons()
                
            self.show

        def createPresetButtons(self):
            """Create (or recreate) all preset button widgets in an 8-column grid with a + placeholder."""
            from neewerlux_ui import customPresetButton

            # Clear existing layout
            for btn in self.presetButtons:
                btn.setParent(None)
                btn.deleteLater()
            self.presetButtons = []
            # Remove any leftover items (stretch spacers etc.)
            while self.customPresetButtonsLay.count():
                item = self.customPresetButtonsLay.takeAt(0)
                w = item.widget()
                if w:
                    w.setParent(None)

            for i in range(numOfPresets):
                name = presetNames.get(i, "")
                label = name[:16] if name else "PRESET\nGLOBAL"
                btn = customPresetButton(self.customPresetButtonsCW, text=str(i + 1) + "\n" + label)
                btn.setMinimumHeight(58)
                btn.setMinimumWidth(0)  # prevent text from widening the column
                btn.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

                # Left-click = recall, right-click = context menu, middle-click = quick rename
                btn.clicked.connect(lambda _checked=False, idx=i: recallCustomPreset(idx))
                btn.rightclicked.connect(lambda idx=i: self._presetContextMenu(idx))
                btn.middleclicked.connect(lambda idx=i: self.renamePresetDialog(idx))
                btn.enteredWidget.connect(lambda idx=i: self.highlightLightsForSnapshotPreset(idx))
                btn.leftWidget.connect(lambda idx=i: self.highlightLightsForSnapshotPreset(idx, True))

                row, col = divmod(i, 8)
                self.customPresetButtonsLay.addWidget(btn, row, col)
                self.presetButtons.append(btn)

            # "+" placeholder button at the end
            addBtn = QPushButton("+")
            addBtn.setMinimumHeight(58)
            addBtn.setMinimumWidth(0)
            addBtn.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            addBtn.setToolTip("Save a new preset here")
            addBtn.setProperty("presetButton", True)
            addBtn.setProperty("presetType", "default")
            addBtn.clicked.connect(lambda: self._addAndSavePreset())
            addRow, addCol = divmod(numOfPresets, 8)
            self.customPresetButtonsLay.addWidget(addBtn, addRow, addCol)
            self._addPresetButton = addBtn

            # Mark custom presets and generate tooltips
            for i in range(numOfPresets):
                self._updatePresetTooltip(i)
                if i < len(customLightPresets) and i < len(defaultLightPresets):
                    name = presetNames.get(i, "")
                    if customLightPresets[i] != defaultLightPresets[i]:
                        if customLightPresets[i][0][0] == -1:
                            self.presetButtons[i].markCustom(i, presetName=name)
                        else:
                            self.presetButtons[i].markCustom(i, 1, presetName=name)
                    elif name:
                        self.presetButtons[i].markCustom(i, -1, presetName=name)

        def _presetContextMenu(self, idx):
            """Show context menu for a preset button (right-click)."""
            menu = QMenu(self)
            saveAction = menu.addAction("Save Current Settings Here")
            editAction = menu.addAction("Edit Preset...")
            renameAction = menu.addAction("Rename")
            menu.addSeparator()
            moveLeftAction = menu.addAction("\u25C0 Move Left")
            moveRightAction = menu.addAction("Move Right \u25B6")
            menu.addSeparator()
            dupAction = menu.addAction("Duplicate Preset")
            deleteAction = menu.addAction("Delete Preset")

            moveLeftAction.setEnabled(idx > 0)
            moveRightAction.setEnabled(idx < numOfPresets - 1)

            pos = self.presetButtons[idx].mapToGlobal(
                self.presetButtons[idx].rect().center())
            try:
                action = menu.exec(pos)
            except AttributeError:
                action = menu.exec_(pos)

            if action == saveAction:
                self.saveCustomPresetDialog(idx)
            elif action == editAction:
                self._openPresetEditor(idx)
            elif action == renameAction:
                self.renamePresetDialog(idx)
            elif action == moveLeftAction and idx > 0:
                self._swapPresets(idx, idx - 1)
            elif action == moveRightAction and idx < numOfPresets - 1:
                self._swapPresets(idx, idx + 1)
            elif action == dupAction:
                self._duplicatePreset(idx)
            elif action == deleteAction:
                self._deletePreset(idx)

        def _swapPresets(self, a, b):
            """Swap two presets (data, names) and rebuild buttons."""
            global customLightPresets, defaultLightPresets
            customLightPresets[a], customLightPresets[b] = customLightPresets[b], customLightPresets[a]
            defaultLightPresets[a], defaultLightPresets[b] = defaultLightPresets[b], defaultLightPresets[a]
            nameA = presetNames.get(a, "")
            nameB = presetNames.get(b, "")
            if nameA:
                presetNames[b] = nameA
            else:
                presetNames.pop(b, None)
            if nameB:
                presetNames[a] = nameB
            else:
                presetNames.pop(a, None)
            self.createPresetButtons()
            printDebugString("Swapped presets " + str(a + 1) + " and " + str(b + 1))

        def _deletePreset(self, idx):
            """Delete a specific preset, shift everything down."""
            global numOfPresets, customLightPresets, defaultLightPresets
            if numOfPresets <= 1:
                return
            reply = QMessageBox.question(self, "Delete Preset",
                "Delete preset " + str(idx + 1) + "?\nAll presets after it will be renumbered.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            customLightPresets.pop(idx)
            defaultLightPresets.pop(idx)
            # Shift preset names down
            newNames = {}
            for k, v in presetNames.items():
                if k < idx:
                    newNames[k] = v
                elif k > idx:
                    newNames[k - 1] = v
                # k == idx is deleted
            presetNames.clear()
            presetNames.update(newNames)
            numOfPresets -= 1
            self.createPresetButtons()
            printDebugString("Deleted preset " + str(idx + 1) + ", " + str(numOfPresets) + " remaining")

        def _duplicatePreset(self, idx):
            """Duplicate a preset, inserting the copy immediately after it."""
            global numOfPresets, customLightPresets, defaultLightPresets
            import copy as _copy
            newIdx = idx + 1
            customLightPresets.insert(newIdx, _copy.deepcopy(customLightPresets[idx]))
            defaultLightPresets.insert(newIdx, _copy.deepcopy(defaultLightPresets[idx]))
            # Shift preset names up
            newNames = {}
            for k, v in presetNames.items():
                if k <= idx:
                    newNames[k] = v
                else:
                    newNames[k + 1] = v
            # Copy the original name with " (copy)" suffix
            if idx in presetNames:
                origName = presetNames[idx]
                copyName = (origName[:14] + " (copy)") if len(origName) > 14 else (origName + " (copy)")
                newNames[newIdx] = copyName[:20]
            presetNames.clear()
            presetNames.update(newNames)
            numOfPresets += 1
            self.createPresetButtons()
            self._savePresetsQuick()
            printDebugString("Duplicated preset " + str(idx + 1) + " → " + str(newIdx + 1))

        def _openPresetEditor(self, idx):
            """Open a dialog to edit preset settings — mirrors animation editor layout."""
            global customLightPresets
            from neewerlux_ui import GradientSlider as GSL
            if PYSIDE_VERSION == 6:
                from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
                    QGridLayout as QGL, QLabel, QLineEdit, QComboBox, QSpinBox,
                    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
                    QWidget as QW, QPushButton, QSizePolicy)
                from PySide6.QtCore import Qt as QtC
                from PySide6.QtGui import QColor, QBrush, QFont
            else:
                from PySide2.QtWidgets import (QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
                    QGridLayout as QGL, QLabel, QLineEdit, QComboBox, QSpinBox,
                    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
                    QWidget as QW, QPushButton, QSizePolicy)
                from PySide2.QtCore import Qt as QtC
                from PySide2.QtGui import QColor, QBrush, QFont

            sceneNames = ["1: Police", "2: Ambulance", "3: Fire Truck", "4: Fireworks",
                          "5: Party", "6: Candlelight", "7: Lightning", "8: Paparazzi", "9: TV Screen"]
            _stopsHue = [(0.0, QColor(255,0,0)), (0.16, QColor(255,255,0)), (0.33, QColor(0,255,0)),
                         (0.49, QColor(0,255,255)), (0.66, QColor(0,0,255)), (0.83, QColor(255,0,255)), (1.0, QColor(255,0,0))]
            _stopsSat = [(0.0, QColor(255,255,255)), (1.0, QColor(255,0,0))]
            _stopsBri = [(0.0, QColor(0,0,0)), (1.0, QColor(255,255,255))]
            _stopsCCT = [(0.0, QColor(255,147,41)), (1.0, QColor(201,226,255))]

            def _targetLabel(t):
                if t == -1 or t == "-1": return "All Lights"
                return "Light " + str(t)

            def _buildTargetChoices():
                choices = [("All Lights (Global)", "-1")]
                for i, light in enumerate(availableLights):
                    prefID = light[8] if len(light) > 8 else 0
                    cname = light[2]; model = light[0].name; mac = light[0].address
                    if prefID > 0:
                        choices.append((str(prefID) + " - " + (cname or model), str(prefID)))
                    elif cname:
                        choices.append((cname + " (" + model + ")", cname))
                    else:
                        choices.append((model + " [" + mac + "]", mac))
                return choices

            def _colorForHSI(h, s, b):
                return QColor.fromHsv(h % 360, int(s * 2.55), int(b * 2.55))

            def _colorForCCT(t, b):
                frac = max(0, min(1, (t - 32) / max(1, 85 - 32)))
                r = int(255 - frac * 54); g = int(147 + frac * 79); bl = int(41 + frac * 214)
                bri = b / 100.0
                return QColor(int(r * bri), int(g * bri), int(bl * bri))

            # === Internal data: list of dicts ===
            # {"target": str, "mode": "CCT"/"HSI"/"Scene", "bri": int, ...}
            entries = []
            selectedRow = [-1]
            clipboard = [None]

            def _presetToEntries(presetData, defaultData):
                """Convert preset storage format to editor entries."""
                result = []
                if presetData == defaultData:
                    return [{"target": "-1", "mode": "CCT", "temp": globalCCTMax // 100, "bri": 100}]
                for item in presetData:
                    t = item[0]; p = item[1] if len(item) > 1 else [5, 100, 56]
                    e = {"target": str(t)}
                    m = p[0]
                    if m in (5, 8):
                        e["mode"] = "CCT"; e["bri"] = p[1]; e["temp"] = p[2]
                    elif m in (4, 7):
                        e["mode"] = "HSI"; e["bri"] = p[1]; e["hue"] = p[2]
                        e["sat"] = p[3] if len(p) > 3 else 100
                    elif m in (6, 9):
                        e["mode"] = "Scene"; e["bri"] = p[1]; e["scene"] = p[2]
                    else:
                        e["mode"] = "CCT"; e["bri"] = 100; e["temp"] = 56
                    result.append(e)
                return result or [{"target": "-1", "mode": "CCT", "temp": globalCCTMax // 100, "bri": 100}]

            def _entriesToPreset():
                """Convert editor entries to preset storage format."""
                result = []
                for e in entries:
                    t = -1 if e["target"] == "-1" else e["target"]
                    m = e.get("mode", "CCT")
                    if m == "CCT":
                        params = [5, e.get("bri", 100), e.get("temp", 56)]
                    elif m == "HSI":
                        params = [4, e.get("bri", 100), e.get("hue", 240), e.get("sat", 100)]
                    elif m == "Scene":
                        params = [6, e.get("bri", 100), e.get("scene", 1)]
                    else:
                        params = [5, 100, 56]
                    result.append([t, params])
                return result

            # === DIALOG ===
            dlg = QDialog(self)
            dlg.setWindowTitle("Edit Preset " + str(idx + 1))
            dlg.setMinimumSize(600, 480)
            dlg.resize(680, 560)
            mainLay = QVBoxLayout(dlg)

            # Name
            nameRow = QHBoxLayout()
            nameRow.addWidget(QLabel("Name:"))
            nameField = QLineEdit(presetNames.get(idx, ""))
            nameField.setPlaceholderText("Preset name (optional)")
            nameRow.addWidget(nameField, 1)
            mainLay.addLayout(nameRow)

            # === TABLE ===
            table = QTableWidget()
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(["#", "Target", "Mode", "Param 1", "Param 2", "Param 3"])
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setAlternatingRowColors(True)
            hdr = table.horizontalHeader()
            hdr.setStretchLastSection(True)
            hdr.setSectionResizeMode(0, QHeaderView.Fixed)
            table.setColumnWidth(0, 32)
            for col in range(1, 6):
                hdr.setSectionResizeMode(col, QHeaderView.Stretch)
            mainLay.addWidget(table, 2)

            # === TOOLBAR ===
            toolbar = QHBoxLayout(); toolbar.setSpacing(4)
            addBtn = QPushButton("+ Add Entry")
            dupBtn = QPushButton("Duplicate")
            delBtn = QPushButton("Delete")
            upBtn = QPushButton("\u25B2 Up")
            downBtn = QPushButton("\u25BC Down")
            copyBtn = QPushButton("Copy")
            copyBtn.setToolTip("Copy selected entry's settings")
            pasteBtn = QPushButton("Paste")
            pasteBtn.setToolTip("Paste settings to selected entry")
            pasteBtn.setEnabled(False)
            for btn in [addBtn, dupBtn, delBtn, upBtn, downBtn, copyBtn, pasteBtn]:
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                toolbar.addWidget(btn)
            mainLay.addLayout(toolbar)

            # === EDITOR PANEL ===
            editorBox = QW()
            editorBox.setObjectName("presetEditor")
            editorLay = QVBoxLayout(editorBox)
            editorLay.setContentsMargins(8, 8, 8, 8)
            editorLay.setSpacing(6)
            editorLay.addWidget(QLabel("<b>Entry Properties</b>"))

            formGrid = QGL(); formGrid.setSpacing(6)

            # Target
            formGrid.addWidget(QLabel("Target:"), 0, 0)
            targetCombo = QComboBox()
            formGrid.addWidget(targetCombo, 0, 1)

            # Mode
            formGrid.addWidget(QLabel("Mode:"), 1, 0)
            modeCombo = QComboBox()
            modeCombo.addItems(["CCT", "HSI", "Scene"])
            formGrid.addWidget(modeCombo, 1, 1)

            # Gradient sliders
            cctMinT = globalCCTMin // 100; cctMaxT = globalCCTMax // 100
            p1Label = QLabel("Color Temp:")
            formGrid.addWidget(p1Label, 2, 0)
            p1Slider = GSL(cctMinT, cctMaxT, cctMaxT, "00K",
                gradientStops=_stopsCCT, minLabel=str(globalCCTMin)+"K", maxLabel=str(globalCCTMax)+"K")
            formGrid.addWidget(p1Slider, 2, 1)

            p2Label = QLabel("Brightness:")
            formGrid.addWidget(p2Label, 3, 0)
            p2Slider = GSL(0, 100, 100, "%",
                gradientStops=_stopsBri, minLabel="0", maxLabel="100")
            formGrid.addWidget(p2Slider, 3, 1)

            p3Label = QLabel("")
            formGrid.addWidget(p3Label, 4, 0)
            p3Slider = GSL(0, 100, 100, "%",
                gradientStops=_stopsSat, minLabel="0", maxLabel="100")
            p3Slider.setVisible(False)
            formGrid.addWidget(p3Slider, 4, 1)

            # Scene combo (visible in Scene mode, replaces p1)
            sceneCombo = QComboBox()
            for sn in sceneNames:
                sceneCombo.addItem(sn)
            sceneCombo.setVisible(False)
            formGrid.addWidget(sceneCombo, 2, 1)

            editorLay.addLayout(formGrid)

            # Color preview
            colorPreview = QLabel("")
            colorPreview.setFixedHeight(24)
            colorPreview.setStyleSheet("background-color: #555; border-radius: 4px;")
            editorLay.addWidget(colorPreview)

            # Apply button
            applyBtn = QPushButton("Apply to Selected Entry")
            editorLay.addWidget(applyBtn)

            mainLay.addWidget(editorBox)

            # OK / Cancel
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            mainLay.addWidget(buttons)

            # === LOGIC ===

            def _onModeChanged(modeText):
                mode = modeText.upper() if modeText else "CCT"
                if mode == "CCT":
                    p1Label.setText("Color Temp:")
                    p1Slider.setSuffix("00K")
                    p1Slider.setRange(cctMinT, cctMaxT)
                    p1Slider.setGradientStops(_stopsCCT)
                    p1Slider.setMinMaxLabels(str(globalCCTMin)+"K", str(globalCCTMax)+"K")
                    p1Slider.setVisible(True); sceneCombo.setVisible(False)
                    p2Label.setText("Brightness:")
                    p2Slider.setSuffix("%")
                    p2Slider.setGradientStops(_stopsBri); p2Slider.setMinMaxLabels("0","100")
                    p2Slider.setVisible(True)
                    p3Label.setText(""); p3Slider.setVisible(False)
                elif mode == "HSI":
                    p1Label.setText("Hue:")
                    p1Slider.setSuffix("\u00B0")
                    p1Slider.setRange(0, 360)
                    p1Slider.setGradientStops(_stopsHue)
                    p1Slider.setMinMaxLabels("0\u00B0", "360\u00B0")
                    p1Slider.setVisible(True); sceneCombo.setVisible(False)
                    p2Label.setText("Saturation:")
                    p2Slider.setSuffix("%")
                    p2Slider.setGradientStops(_stopsSat); p2Slider.setMinMaxLabels("0","100")
                    p2Slider.setVisible(True)
                    p3Label.setText("Brightness:")
                    p3Slider.setSuffix("%")
                    p3Slider.setGradientStops(_stopsBri); p3Slider.setMinMaxLabels("0","100")
                    p3Slider.setVisible(True)
                elif mode == "SCENE":
                    p1Label.setText("Scene:")
                    p1Slider.setVisible(False); sceneCombo.setVisible(True)
                    p2Label.setText("Brightness:")
                    p2Slider.setSuffix("%")
                    p2Slider.setGradientStops(_stopsBri); p2Slider.setMinMaxLabels("0","100")
                    p2Slider.setVisible(True)
                    p3Label.setText(""); p3Slider.setVisible(False)
                _updatePreview()

            def _updatePreview():
                mode = modeCombo.currentText().upper()
                if mode == "CCT":
                    c = _colorForCCT(p1Slider.value(), p2Slider.value())
                elif mode == "HSI":
                    c = _colorForHSI(p1Slider.value(), p2Slider.value(), p3Slider.value())
                elif mode == "SCENE":
                    c = QColor(145, 0, 255)
                else:
                    c = QColor(60, 60, 60)
                colorPreview.setStyleSheet("background-color: " + c.name() + "; border-radius: 4px;")

            def _readEditor():
                """Read editor controls into an entry dict."""
                mode = modeCombo.currentText()
                e = {"target": targetCombo.currentData() or "-1", "mode": mode}
                if mode == "CCT":
                    e["temp"] = p1Slider.value(); e["bri"] = p2Slider.value()
                elif mode == "HSI":
                    e["hue"] = p1Slider.value(); e["sat"] = p2Slider.value(); e["bri"] = p3Slider.value()
                elif mode == "Scene":
                    e["scene"] = sceneCombo.currentIndex() + 1; e["bri"] = p2Slider.value()
                return e

            def _loadEditor(entry):
                """Load an entry dict into editor controls."""
                # Target
                val = str(entry.get("target", "-1"))
                for i in range(targetCombo.count()):
                    if targetCombo.itemData(i) == val or str(targetCombo.itemData(i)).upper() == val.upper():
                        targetCombo.setCurrentIndex(i); break

                mode = entry.get("mode", "CCT")
                modeCombo.blockSignals(True)
                mIdx = {"CCT": 0, "HSI": 1, "Scene": 2}.get(mode, 0)
                modeCombo.setCurrentIndex(mIdx)
                modeCombo.blockSignals(False)
                _onModeChanged(mode)

                if mode == "CCT":
                    p1Slider.setValue(entry.get("temp", 56))
                    p2Slider.setValue(entry.get("bri", 100))
                elif mode == "HSI":
                    p1Slider.setValue(entry.get("hue", 240))
                    p2Slider.setValue(entry.get("sat", 100))
                    p3Slider.setValue(entry.get("bri", 100))
                elif mode == "Scene":
                    sceneCombo.setCurrentIndex(max(0, entry.get("scene", 1) - 1))
                    p2Slider.setValue(entry.get("bri", 100))
                _updatePreview()

            def _setTableRow(row, entry):
                mode = entry.get("mode", "CCT")
                table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
                table.item(row, 0).setTextAlignment(QtC.AlignCenter)
                tgtItem = QTableWidgetItem(_targetLabel(entry.get("target", "-1")))
                tgtItem.setTextAlignment(QtC.AlignCenter)
                table.setItem(row, 1, tgtItem)
                mItem = QTableWidgetItem(mode)
                mItem.setTextAlignment(QtC.AlignCenter)
                table.setItem(row, 2, mItem)

                if mode == "CCT":
                    p1 = str(entry.get("temp", 56) * 100) + "K"
                    p2 = str(entry.get("bri", 100)) + "%"; p3 = ""
                    c = _colorForCCT(entry.get("temp", 56), entry.get("bri", 100))
                elif mode == "HSI":
                    p1 = str(entry.get("hue", 0)) + "\u00B0"
                    p2 = str(entry.get("sat", 100)) + "%"
                    p3 = str(entry.get("bri", 100)) + "%"
                    c = _colorForHSI(entry.get("hue", 0), entry.get("sat", 100), entry.get("bri", 100))
                elif mode == "Scene":
                    p1 = "Scene " + str(entry.get("scene", 1))
                    p2 = str(entry.get("bri", 100)) + "%"; p3 = ""
                    c = QColor(145, 0, 255, 120)
                else:
                    p1 = p2 = p3 = ""; c = QColor(60, 60, 60)

                table.setItem(row, 3, QTableWidgetItem(p1))
                table.setItem(row, 4, QTableWidgetItem(p2))
                table.setItem(row, 5, QTableWidgetItem(p3))
                if c:
                    brush = QBrush(c)
                    mItem.setBackground(brush)
                    lum = c.red() * 0.299 + c.green() * 0.587 + c.blue() * 0.114
                    mItem.setForeground(QBrush(QColor(0,0,0) if lum > 128 else QColor(255,255,255)))

            def _populateTable():
                table.setRowCount(len(entries))
                for i, e in enumerate(entries):
                    _setTableRow(i, e)
                _updateTargetGuardrails()

            def _updateTargetGuardrails():
                """Disable 'All Lights' when multiple entries exist,
                and disable targets already used by other entries."""
                multi = len(entries) > 1
                r = selectedRow[0]
                currentTarget = entries[r]["target"] if 0 <= r < len(entries) else None
                usedTargets = set()
                for i, e in enumerate(entries):
                    if i != r:
                        usedTargets.add(str(e.get("target", "-1")))
                model = targetCombo.model()
                for i in range(targetCombo.count()):
                    item = model.item(i)
                    if not item:
                        continue
                    val = targetCombo.itemData(i)
                    if i == 0:  # "All Lights (Global)"
                        item.setEnabled(not multi)
                        if multi and targetCombo.currentIndex() == 0 and targetCombo.count() > 1:
                            targetCombo.setCurrentIndex(1)
                    elif val in usedTargets:
                        item.setEnabled(False)
                    else:
                        item.setEnabled(True)

            def _onRowSelected():
                rows = table.selectionModel().selectedRows()
                if not rows:
                    selectedRow[0] = -1; return
                row = rows[0].row()
                selectedRow[0] = row
                if row < len(entries):
                    _loadEditor(entries[row])
                _updateTargetGuardrails()

            def _apply():
                r = selectedRow[0]
                if 0 <= r < len(entries):
                    entries[r] = _readEditor()
                    _setTableRow(r, entries[r])
                _updateTargetGuardrails()

            def _addEntry():
                entries.append({"target": "-1", "mode": "CCT", "temp": globalCCTMax // 100, "bri": 100})
                _populateTable()
                table.selectRow(len(entries) - 1)

            def _dupEntry():
                r = selectedRow[0]
                if 0 <= r < len(entries):
                    import copy as _c
                    entries.insert(r + 1, _c.deepcopy(entries[r]))
                    _populateTable()
                    table.selectRow(r + 1)

            def _delEntry():
                r = selectedRow[0]
                if r < 0 or r >= len(entries) or len(entries) <= 1: return
                entries.pop(r)
                _populateTable()
                if entries:
                    table.selectRow(min(r, len(entries) - 1))
                selectedRow[0] = -1

            def _moveEntry(d):
                r = selectedRow[0]
                if r < 0 or r >= len(entries): return
                nr = r + d
                if nr < 0 or nr >= len(entries): return
                entries[r], entries[nr] = entries[nr], entries[r]
                _populateTable()
                table.selectRow(nr)

            def _copyEntry():
                r = selectedRow[0]
                if 0 <= r < len(entries):
                    import copy as _c
                    clipboard[0] = _c.deepcopy(entries[r])
                    clipboard[0].pop("target", None)  # copy settings, not target
                    pasteBtn.setEnabled(True)
                    pasteBtn.setToolTip("Paste: " + clipboard[0].get("mode", "?"))

            def _pasteEntry():
                r = selectedRow[0]
                if clipboard[0] and 0 <= r < len(entries):
                    import copy as _c
                    tgt = entries[r]["target"]  # preserve target
                    entries[r] = _c.deepcopy(clipboard[0])
                    entries[r]["target"] = tgt
                    _setTableRow(r, entries[r])
                    _loadEditor(entries[r])

            # Wire signals
            modeCombo.currentTextChanged.connect(_onModeChanged)
            for s in [p1Slider, p2Slider, p3Slider]:
                s.valueChanged.connect(lambda v: _updatePreview())
            table.selectionModel().selectionChanged.connect(lambda: _onRowSelected())
            applyBtn.clicked.connect(_apply)
            addBtn.clicked.connect(_addEntry)
            dupBtn.clicked.connect(_dupEntry)
            delBtn.clicked.connect(_delEntry)
            upBtn.clicked.connect(lambda: _moveEntry(-1))
            downBtn.clicked.connect(lambda: _moveEntry(1))
            copyBtn.clicked.connect(_copyEntry)
            pasteBtn.clicked.connect(_pasteEntry)

            # Populate target combo
            for label, val in _buildTargetChoices():
                targetCombo.addItem(label, val)

            # Load preset data
            if idx < len(customLightPresets) and idx < len(defaultLightPresets):
                entries.extend(_presetToEntries(customLightPresets[idx], defaultLightPresets[idx]))
            else:
                entries.append({"target": "-1", "mode": "CCT", "temp": globalCCTMax // 100, "bri": 100})
            _populateTable()
            if entries:
                table.selectRow(0)

            # Restore size
            try:
                if os.path.exists(geometryPrefsFile):
                    with open(geometryPrefsFile, "r", encoding="utf-8") as f:
                        geo = json.load(f)
                    if "presetEditorW" in geo and "presetEditorH" in geo:
                        dlg.resize(geo["presetEditorW"], geo["presetEditorH"])
            except Exception:
                pass

            result_code = pyside_exec(dlg)

            # Save size
            try:
                geo = {}
                if os.path.exists(geometryPrefsFile):
                    with open(geometryPrefsFile, "r", encoding="utf-8") as f:
                        geo = json.load(f)
                geo["presetEditorW"] = dlg.width()
                geo["presetEditorH"] = dlg.height()
                with open(geometryPrefsFile, "w", encoding="utf-8") as f:
                    json.dump(geo, f)
            except Exception:
                pass

            if result_code == 1:  # Accepted
                # Apply any pending editor changes
                r = selectedRow[0]
                if 0 <= r < len(entries):
                    entries[r] = _readEditor()

                presetData = _entriesToPreset()
                if not presetData:
                    return

                customLightPresets[idx] = presetData
                newName = nameField.text().strip()[:20]
                if newName:
                    presetNames[idx] = newName
                else:
                    presetNames.pop(idx, None)

                self.refreshPresetButtonDisplay(idx)
                self._savePresetsQuick()
                isSnapshot = any(e[0] != -1 for e in presetData)
                printDebugString("Preset " + str(idx + 1) + " edited via Preset Editor (" +
                    ("snapshot, " + str(len(presetData)) + " entries" if isSnapshot else "global") + ")")

        def _addAndSavePreset(self):
            """Add a new preset slot and immediately open the save dialog for it."""
            global numOfPresets, defaultLightPresets, customLightPresets
            numOfPresets += 1
            defaultLightPresets.append(getDefaultPreset(numOfPresets - 1))
            customLightPresets.append(getDefaultPreset(numOfPresets - 1))
            self.createPresetButtons()
            self.saveCustomPresetDialog(numOfPresets - 1)

        def _updatePresetTooltip(self, idx):
            """Generate a human-readable tooltip for a preset."""
            if idx >= len(customLightPresets) or idx >= len(defaultLightPresets):
                return
            if customLightPresets[idx] == defaultLightPresets[idx]:
                self.presetButtons[idx].setToolTip("Empty preset\nLeft-click: recall | Right-click: options | Middle-click: rename")
                return
            lines = []
            name = presetNames.get(idx, "Preset " + str(idx + 1))
            lines.append(name)
            lines.append("---")
            for entry in customLightPresets[idx]:
                mac = entry[0]
                params = entry[1]
                if mac == -1:
                    lightLabel = "All Lights"
                else:
                    # Try to resolve MAC to a name
                    lightLabel = str(mac)
                    for light in availableLights:
                        if light[0].address == mac:
                            lightLabel = light[2] if light[2] else light[0].name
                            break
                if len(params) >= 3:
                    mode = params[0]
                    if mode == 4:  # HSI
                        lines.append(lightLabel + ": HSI " + str(params[2]) + "\u00B0 S:" + str(params[3]) + "% B:" + str(params[1]) + "%")
                    elif mode == 5:  # CCT
                        lines.append(lightLabel + ": CCT " + str(params[2]) + "00K B:" + str(params[1]) + "%")
                    elif mode == 6:  # ANM/Scene
                        lines.append(lightLabel + ": Scene " + str(params[2]) + " B:" + str(params[1]) + "%")
                    else:
                        lines.append(lightLabel + ": mode=" + str(mode))
                else:
                    lines.append(lightLabel + ": " + str(params))
            lines.append("---")
            lines.append("Left-click: recall | Right-click: options | Middle-click: rename")
            self.presetButtons[idx].setToolTip("\n".join(lines))

        def renamePresetDialog(self, numOfPreset):
            """Prompt the user to set or change a custom name for this preset (middle-click)."""
            currentName = presetNames.get(numOfPreset, "")
            newName, ok = QInputDialog.getText(self, "Rename Preset " + str(numOfPreset + 1),
                                               "Enter a name for preset " + str(numOfPreset + 1) + ":\n(Leave blank to clear the name)",
                                               text=currentName)
            if ok:
                newName = newName.strip()[:20]  # limit to 20 chars
                if newName:
                    presetNames[numOfPreset] = newName
                else:
                    presetNames.pop(numOfPreset, None)

                # Refresh the button display
                self.refreshPresetButtonDisplay(numOfPreset)
                printDebugString("Preset " + str(numOfPreset + 1) + " renamed to: " + (newName if newName else "(cleared)"))

        def refreshPresetButtonDisplay(self, numOfPreset):
            """Refresh a single preset button's text and style to reflect current state."""
            if numOfPreset >= len(self.presetButtons):
                return
            name = presetNames.get(numOfPreset, "")
            if numOfPreset < len(customLightPresets) and numOfPreset < len(defaultLightPresets):
                if customLightPresets[numOfPreset] != defaultLightPresets[numOfPreset]:
                    if customLightPresets[numOfPreset][0][0] == -1:
                        self.presetButtons[numOfPreset].markCustom(numOfPreset, presetName=name)
                    else:
                        self.presetButtons[numOfPreset].markCustom(numOfPreset, 1, presetName=name)
                else:
                    self.presetButtons[numOfPreset].markCustom(numOfPreset, -1, presetName=name)
            else:
                self.presetButtons[numOfPreset].markCustom(numOfPreset, -1, presetName=name)
            self._updatePresetTooltip(numOfPreset)

        # ================================================================
        # ANIMATION TAB HANDLER METHODS
        # ================================================================

        def animRefreshList(self):
            """Refresh the animation list widget from savedAnimations, grouped by mode type."""
            self.animList.clear()

            def _classifyAnim(anim):
                """Classify an animation as HSI, CCT, or Mixed based on keyframe modes."""
                modes = set()
                for kf in anim.get("keyframes", []):
                    for lightKey, params in kf.get("lights", {}).items():
                        modes.add(params.get("mode", "HSI").upper())
                if modes == {"CCT"}:
                    return "CCT Only"
                elif modes == {"HSI"}:
                    return "HSI Only"
                elif modes == {"ANM"}:
                    return "Scene Only"
                elif len(modes) > 1:
                    return "Mixed"
                elif not modes:
                    return "Mixed"
                return list(modes)[0] + " Only"

            # Group animations by category
            groups = {}
            for name in sorted(savedAnimations.keys()):
                cat = _classifyAnim(savedAnimations[name])
                if cat not in groups:
                    groups[cat] = []
                groups[cat].append(name)

            # Display order: HSI Only first, then Mixed, then CCT Only
            groupOrder = ["HSI Only", "Mixed", "CCT Only", "Scene Only"]
            for g in sorted(groups.keys()):
                if g not in groupOrder:
                    groupOrder.append(g)

            for group in groupOrder:
                if group not in groups:
                    continue
                # Add group header (non-selectable)
                header = QListWidgetItem("━━━ " + group + " ━━━")
                header.setFlags(Qt.NoItemFlags)  # not selectable
                headerFont = QFont()
                headerFont.setBold(True)
                header.setFont(headerFont)
                self.animList.addItem(header)

                for name in groups[group]:
                    desc = savedAnimations[name].get("description", "")
                    kfCount = len(savedAnimations[name].get("keyframes", []))
                    label = "  " + name
                    if desc:
                        label += "  —  " + desc
                    label += "  [" + str(kfCount) + " frames]"
                    item = QListWidgetItem(label)
                    item.setData(Qt.UserRole, name)
                    self.animList.addItem(item)

        def animGetSelectedName(self):
            """Return the name of the currently selected animation, or None."""
            items = self.animList.selectedItems()
            if items:
                return items[0].data(Qt.UserRole)
            return None

        def animPlay(self):
            """Play the selected animation."""
            name = self.animGetSelectedName()
            if not name:
                self.animStatusLabel.setText("Select an animation first")
                return

            loopOverride = self.animLoopCheck.isChecked()
            speedText = self.animSpeedCombo.currentText().replace("x", "")
            try:
                speedMult = float(speedText)
            except ValueError:
                speedMult = 1.0

            self.animPlayButton.setEnabled(False)
            self.animStopButton.setEnabled(True)
            self.animStatusLabel.setText("Starting: " + name)

            fps = self.animRateSpin.value()
            briScale = self.animBriSpin.value() / 100.0

            global animParallelWrites, animRevertOnFinish
            animParallelWrites = self.animParallelCheck.isChecked()
            animRevertOnFinish = self.animRevertCheck.isChecked()
            maxLoops = self.animLoopCountSpin.value()

            startAnimation(name, asyncioEventLoop, speedMult, loopOverride, fps=fps, briScale=briScale, maxLoops=maxLoops)

        def animStop(self):
            """Stop the currently playing animation."""
            stopAnimation()
            self.animPlayButton.setEnabled(True)
            self.animStopButton.setEnabled(False)
            self.animStatusLabel.setText("Stopped")

        def animNew(self):
            """Create a new animation from a template."""
            # Use global PYSIDE_VERSION
            if PYSIDE_VERSION == 6:
                from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QFormLayout as QFL, QLabel as QL, QLineEdit as QLE, QComboBox as QCB, QSpinBox as QSB, QCheckBox as QCK
            else:
                from PySide2.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QFormLayout as QFL, QLabel as QL, QLineEdit as QLE, QComboBox as QCB, QSpinBox as QSB, QCheckBox as QCK

            dlg = QDialog(self)
            dlg.setWindowTitle("New Animation")
            dlg.setFixedSize(400, 350)
            layout = QVBoxLayout(dlg)
            form = QFL()

            nameField = QLE("My Animation")
            form.addRow("Name:", nameField)

            templateCombo = QCB()
            templateCombo.addItems(list(ANIMATION_TEMPLATES.keys()) + ["Empty (Manual)"])
            form.addRow("Template:", templateCombo)

            lightsField = QLE("*")
            form.addRow("Lights (e.g. 1;2 or *):", lightsField)

            speedSpin = QSB()
            speedSpin.setRange(50, 5000)
            speedSpin.setValue(300)
            speedSpin.setSuffix(" ms")
            speedSpin.setButtonSymbols(QSB.NoButtons)
            form.addRow("Speed / hold per frame:", speedSpin)

            fadeSpin = QSB()
            fadeSpin.setRange(0, 10000)
            fadeSpin.setValue(0)
            fadeSpin.setSuffix(" ms")
            fadeSpin.setButtonSymbols(QSB.NoButtons)
            form.addRow("Fade between frames:", fadeSpin)

            loopCheck = QCK("Loop animation")
            loopCheck.setChecked(True)
            form.addRow(loopCheck)

            briSpin = QSB()
            briSpin.setRange(0, 100)
            briSpin.setValue(100)
            briSpin.setSuffix("%")
            briSpin.setButtonSymbols(QSB.NoButtons)
            form.addRow("Brightness:", briSpin)

            layout.addLayout(form)

            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            layout.addWidget(buttons)

            if pyside_exec(dlg) == QDialog.Accepted:
                name = nameField.text().strip() or "Untitled"
                templateName = templateCombo.currentText()
                lightsStr = lightsField.text().strip() or "*"
                lights = lightsStr.split(";") if lightsStr != "*" else ["*"]
                hold = speedSpin.value()
                fade = fadeSpin.value()
                bri = briSpin.value()

                if templateName == "Empty (Manual)":
                    anim = {
                        "name": name,
                        "description": "Custom animation",
                        "loop": loopCheck.isChecked(),
                        "keyframes": [
                            {"hold_ms": hold, "fade_ms": 0, "lights": {l: {"mode": "HSI", "hue": 0, "sat": 100, "bri": bri} for l in lights}}
                        ]
                    }
                else:
                    templateFn = ANIMATION_TEMPLATES[templateName]
                    # Call the template with available parameters
                    if templateName == "Police Flash":
                        anim = templateFn(lights=lights, speed_ms=hold)
                    elif templateName == "Strobe":
                        anim = templateFn(lights=lights, on_ms=hold, off_ms=hold, brightness=bri)
                    elif templateName == "Breathe":
                        anim = templateFn(lights=lights, fade_ms=max(fade, 500), hold_ms=hold, max_bri=bri)
                    elif templateName == "Color Wash":
                        anim = templateFn(lights=lights, fade_ms=max(fade, 1000), hold_ms=hold)
                    elif templateName == "Rainbow Chase":
                        anim = templateFn(lights=lights, step_ms=hold, fade_ms=fade, brightness=bri)
                    else:  # Color Cycle and others
                        anim = templateFn(lights=lights, fade_ms=fade, hold_ms=hold, brightness=bri)

                    anim["loop"] = loopCheck.isChecked()

                anim["name"] = name
                savedAnimations[name] = anim
                saveAnimationToFile(anim)
                self.animRefreshList()
                printDebugString("Created new animation: " + name)

        def animEdit(self):
            """Open the visual keyframe editor dialog for the selected animation."""
            name = self.animGetSelectedName()
            if not name or name not in savedAnimations:
                return

            try:
                from neewerlux_anim_editor import AnimationEditorDialog
            except ImportError:
                printDebugString("Could not import neewerlux_anim_editor — falling back to JSON editor")
                self._animEditJSON(name)
                return

            anim = savedAnimations[name]
            dlg = AnimationEditorDialog(self, anim, name, cctRange=(globalCCTMin // 100, globalCCTMax // 100))
            # Restore saved editor size if available
            try:
                if os.path.exists(geometryPrefsFile):
                    with open(geometryPrefsFile, "r", encoding="utf-8") as f:
                        geo = json.load(f)
                    if "animEditorW" in geo and "animEditorH" in geo:
                        dlg.resize(geo["animEditorW"], geo["animEditorH"])
            except Exception:
                pass

            result_code = pyside_exec(dlg)

            # Save the editor dialog size for next time (regardless of OK/Cancel)
            try:
                if os.path.exists(geometryPrefsFile):
                    with open(geometryPrefsFile, "r", encoding="utf-8") as f:
                        geo = json.load(f)
                else:
                    geo = {}
                geo["animEditorW"] = dlg.width()
                geo["animEditorH"] = dlg.height()
                with open(geometryPrefsFile, "w", encoding="utf-8") as f:
                    json.dump(geo, f)
            except Exception:
                pass

            # Check result (QDialog.exec() returns 1 for Accepted, 0 for Rejected)
            if result_code == 1:
                result = dlg.getResult()
                newName = result["name"]

                # If name changed, delete old file
                if newName != name:
                    deleteAnimationFile(name)
                    savedAnimations.pop(name, None)

                savedAnimations[newName] = result
                saveAnimationToFile(result)
                self.animRefreshList()
                printDebugString("Saved animation: " + newName)

        def _animEditJSON(self, name):
            """Fallback JSON-only animation editor."""
            # Use global PYSIDE_VERSION
            if PYSIDE_VERSION == 6:
                from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout as QHL, QFormLayout as QFL, \
                    QLabel as QL, QLineEdit as QLE, QSpinBox as QSB, QCheckBox as QCK, QTextEdit as QTE, QPushButton as QPB
            else:
                from PySide2.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout as QHL, QFormLayout as QFL, \
                    QLabel as QL, QLineEdit as QLE, QSpinBox as QSB, QCheckBox as QCK, QTextEdit as QTE, QPushButton as QPB

            anim = savedAnimations[name]

            dlg = QDialog(self)
            dlg.setWindowTitle("Edit Animation: " + name)
            dlg.setFixedSize(550, 480)
            layout = QVBoxLayout(dlg)

            form = QFL()
            nameField = QLE(anim.get("name", name))
            form.addRow("Name:", nameField)
            descField = QLE(anim.get("description", ""))
            form.addRow("Description:", descField)
            loopCheck = QCK("Loop")
            loopCheck.setChecked(anim.get("loop", True))
            form.addRow(loopCheck)
            layout.addLayout(form)

            layout.addWidget(QL("<b>Keyframes (JSON)</b> — edit directly:"))
            jsonEdit = QTE()
            jsonEdit.setFont(QFont("Courier", 9))
            jsonEdit.setPlainText(json.dumps(anim.get("keyframes", []), indent=2))
            layout.addWidget(jsonEdit)

            errorLabel = QL("")
            errorLabel.setStyleSheet("color: red;")
            layout.addWidget(errorLabel)

            buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            layout.addWidget(buttons)

            if pyside_exec(dlg) == QDialog.Accepted:
                try:
                    newKeyframes = json.loads(jsonEdit.toPlainText())
                    if not isinstance(newKeyframes, list):
                        raise ValueError("Keyframes must be a JSON array")
                except (json.JSONDecodeError, ValueError) as e:
                    errDlg = QMessageBox(self)
                    errDlg.setWindowTitle("JSON Error")
                    errDlg.setText("Invalid keyframe JSON:\n" + str(e))
                    pyside_exec(errDlg)
                    return

                newName = nameField.text().strip() or name
                if newName != name:
                    deleteAnimationFile(name)
                    savedAnimations.pop(name, None)

                anim["name"] = newName
                anim["description"] = descField.text().strip()
                anim["loop"] = loopCheck.isChecked()
                anim["keyframes"] = newKeyframes

                savedAnimations[newName] = anim
                saveAnimationToFile(anim)
                self.animRefreshList()
                printDebugString("Saved animation: " + newName)

        def animDelete(self):
            """Delete the selected animation."""
            name = self.animGetSelectedName()
            if not name:
                return

            confirm = QMessageBox.question(self, "Delete Animation",
                                           "Delete animation '" + name + "'?",
                                           QMessageBox.Yes | QMessageBox.No)
            if confirm == QMessageBox.Yes:
                if animationRunning and currentAnimationName == name:
                    stopAnimation()
                deleteAnimationFile(name)
                savedAnimations.pop(name, None)
                self.animRefreshList()

        def animDuplicate(self):
            """Duplicate the selected animation."""
            name = self.animGetSelectedName()
            if not name or name not in savedAnimations:
                return
            import copy
            newAnim = copy.deepcopy(savedAnimations[name])
            newName = name + " (copy)"
            counter = 2
            while newName in savedAnimations:
                newName = name + " (copy " + str(counter) + ")"
                counter += 1
            newAnim["name"] = newName
            savedAnimations[newName] = newAnim
            saveAnimationToFile(newAnim)
            self.animRefreshList()

        def animExport(self):
            """Export the selected animation to a JSON file (copies path to clipboard)."""
            name = self.animGetSelectedName()
            if not name or name not in savedAnimations:
                return
            self.animStatusLabel.setText("Animation files are in:\n" + animationsDir)

        def animImport(self):
            """Reload all animations from disk (picks up manually added JSON files)."""
            loadAllAnimations()
            loadLightAliases()
            self.animRefreshList()
            self.animStatusLabel.setText("Reloaded " + str(len(savedAnimations)) + " animation(s)")

        def connectMe(self):
            self.turnOffButton.clicked.connect(self.turnLightOff)
            self.turnOnButton.clicked.connect(self.turnLightOn)

            self.scanCommandButton.clicked.connect(self.startSelfSearch)
            self.tryConnectButton.clicked.connect(self.startConnect)
            self.selectAllButton.clicked.connect(self.lightTable.selectAll)

            self.ColorModeTabWidget.currentChanged.connect(self.tabChanged)
            self.lightTable.itemSelectionChanged.connect(self.selectionChanged)

            # Allow clicking on the headers for sorting purposes
            horizHeaders = self.lightTable.horizontalHeader()
            horizHeaders.setSectionsClickable(True)
            horizHeaders.sectionClicked.connect(self.sortByHeader)

            # PRESET PAGINATION NAVIGATION
            # ANIMATION TAB CONNECTIONS
            self.animPlayButton.clicked.connect(self.animPlay)
            self.animStopButton.clicked.connect(self.animStop)
            self.animNewButton.clicked.connect(self.animNew)
            self.animEditButton.clicked.connect(self.animEdit)
            self.animDeleteButton.clicked.connect(self.animDelete)
            self.animDuplicateButton.clicked.connect(self.animDuplicate)
            self.animExportButton.clicked.connect(self.animExport)
            self.animImportButton.clicked.connect(self.animImport)

            self.Slider_CCT_Hue.valueChanged.connect(lambda: self.computeValueCCT(1))
            self.Slider_CCT_Bright.valueChanged.connect(lambda: self.computeValueCCT(2))

            self.Slider_HSI_1_H.valueChanged.connect(lambda: self.computeValueHSI(1))
            self.Slider_HSI_2_S.valueChanged.connect(lambda: self.computeValueHSI(2))
            self.Slider_HSI_3_L.valueChanged.connect(lambda: self.computeValueHSI(3))

            self.Slider_ANM_Brightness.valueChanged.connect(lambda: self.computeValueANM(0))
            self.Button_1_police_A.clicked.connect(lambda: self.computeValueANM(1))
            self.Button_1_police_B.clicked.connect(lambda: self.computeValueANM(2))
            self.Button_1_police_C.clicked.connect(lambda: self.computeValueANM(3))
            self.Button_2_party_A.clicked.connect(lambda: self.computeValueANM(4))
            self.Button_2_party_B.clicked.connect(lambda: self.computeValueANM(5))
            self.Button_2_party_C.clicked.connect(lambda: self.computeValueANM(6))
            self.Button_3_lightning_A.clicked.connect(lambda: self.computeValueANM(7))
            self.Button_3_lightning_B.clicked.connect(lambda: self.computeValueANM(8))
            self.Button_3_lightning_C.clicked.connect(lambda: self.computeValueANM(9))

            # CHECKS TO SEE IF SPECIFIC FIELDS (and the save button) SHOULD BE ENABLED OR DISABLED
            self.customName.clicked.connect(self.checkLightPrefsEnables)
            self.colorTempRange.clicked.connect(self.checkLightPrefsEnables)
            self.saveLightPrefsButton.clicked.connect(self.checkLightPrefs)

            self.resetGlobalPrefsButton.clicked.connect(lambda: self.setupGlobalLightPrefsTab(True))
            self.saveGlobalPrefsButton.clicked.connect(self.saveGlobalPrefs)
            self.applyButton.clicked.connect(self.manualApply)
            def _onLivePreviewToggled(checked):
                global livePreview
                livePreview = checked
                self.applyButton.setVisible(not checked)
            self.livePreview_check.toggled.connect(_onLivePreviewToggled)

            # THEME TOGGLE
            self.themeToggleBtn.clicked.connect(self.toggleTheme)

            # HTTP SERVER TOGGLE
            self.httpToggleBtn.clicked.connect(self.toggleHTTPServer)

            # SHORTCUT KEYS - MAKE THEM HERE, SET THEIR ASSIGNMENTS BELOW WITH self.setupShortcutKeys()
            # IN CASE WE NEED TO CHANGE THEM AFTER CHANGING PREFERENCES
            self.SC_turnOffButton = QShortcut(self)
            self.SC_turnOnButton = QShortcut(self)
            self.SC_scanCommandButton = QShortcut(self)
            self.SC_tryConnectButton = QShortcut(self)
            self.SC_Tab_CCT = QShortcut(self)
            self.SC_Tab_HSI = QShortcut(self)
            self.SC_Tab_SCENE = QShortcut(self)
            self.SC_Tab_PREFS = QShortcut(self)

            # DECREASE/INCREASE BRIGHTNESS REGARDLESS OF WHICH TAB WE'RE ON
            self.SC_Dec_Bri_Small = QShortcut(self)
            self.SC_Inc_Bri_Small = QShortcut(self)
            self.SC_Dec_Bri_Large = QShortcut(self)
            self.SC_Inc_Bri_Large = QShortcut(self)

            # THE SMALL INCREMENTS *DO* NEED A CUSTOM FUNCTION, BUT ONLY IF WE CHANGE THE
            # SHORTCUT ASSIGNMENT TO SOMETHING OTHER THAN THE NORMAL NUMBERS
            # THE LARGE INCREMENTS DON'T NEED A CUSTOM FUNCTION
            self.SC_Dec_1_Small = QShortcut(self)
            self.SC_Inc_1_Small = QShortcut(self)
            self.SC_Dec_2_Small = QShortcut(self)
            self.SC_Inc_2_Small = QShortcut(self)
            self.SC_Dec_3_Small = QShortcut(self)
            self.SC_Inc_3_Small = QShortcut(self)
            self.SC_Dec_1_Large = QShortcut(self)
            self.SC_Inc_1_Large = QShortcut(self)
            self.SC_Dec_2_Large = QShortcut(self)
            self.SC_Inc_2_Large = QShortcut(self)
            self.SC_Dec_3_Large = QShortcut(self)
            self.SC_Inc_3_Large = QShortcut(self)

            self.setupShortcutKeys() # set up the shortcut keys for the first time

            # CONNECT THE KEYS TO THEIR FUNCTIONS
            self.SC_turnOffButton.activated.connect(self.turnLightOff)
            self.SC_turnOnButton.activated.connect(self.turnLightOn)
            self.SC_scanCommandButton.activated.connect(self.startSelfSearch)
            self.SC_tryConnectButton.activated.connect(self.startConnect)
            self.SC_Tab_CCT.activated.connect(lambda: self.switchToTab(0))
            self.SC_Tab_HSI.activated.connect(lambda: self.switchToTab(1))
            self.SC_Tab_SCENE.activated.connect(lambda: self.switchToTab(2))
            self.SC_Tab_PREFS.activated.connect(lambda: self.switchToTab(4))

            # DECREASE/INCREASE BRIGHTNESS REGARDLESS OF WHICH TAB WE'RE ON
            self.SC_Dec_Bri_Small.activated.connect(lambda: self.changeSliderValue(0, -1))
            self.SC_Inc_Bri_Small.activated.connect(lambda: self.changeSliderValue(0, 1))
            self.SC_Dec_Bri_Large.activated.connect(lambda: self.changeSliderValue(0, -5))
            self.SC_Inc_Bri_Large.activated.connect(lambda: self.changeSliderValue(0, 5))

            # THE SMALL INCREMENTS DO NEED A SPECIAL FUNCTION-
            # (see above) - BASICALLY, IF THEY'RE JUST ASSIGNED THE DEFAULT NUMPAD/NUMBER VALUES
            # THESE FUNCTIONS DON'T TRIGGER (THE SAME FUNCTIONS ARE HANDLED BY numberShortcuts(n))
            # BUT IF THEY ARE CUSTOM, *THEN* THESE TRIGGER INSTEAD, AND THIS FUNCTION ^^^^ JUST DOES
            # SCENE SELECTIONS IN SCENE MODE
            self.SC_Dec_1_Small.activated.connect(lambda: self.changeSliderValue(1, -1))
            self.SC_Inc_1_Small.activated.connect(lambda: self.changeSliderValue(1, 1))
            self.SC_Dec_2_Small.activated.connect(lambda: self.changeSliderValue(2, -1))
            self.SC_Inc_2_Small.activated.connect(lambda: self.changeSliderValue(2, 1))
            self.SC_Dec_3_Small.activated.connect(lambda: self.changeSliderValue(3, -1))
            self.SC_Inc_3_Small.activated.connect(lambda: self.changeSliderValue(3, 1))

            # THE LARGE INCREMENTS DON'T NEED A CUSTOM FUNCTION
            self.SC_Dec_1_Large.activated.connect(lambda: self.changeSliderValue(1, -5))
            self.SC_Inc_1_Large.activated.connect(lambda: self.changeSliderValue(1, 5))
            self.SC_Dec_2_Large.activated.connect(lambda: self.changeSliderValue(2, -5))
            self.SC_Inc_2_Large.activated.connect(lambda: self.changeSliderValue(2, 5))
            self.SC_Dec_3_Large.activated.connect(lambda: self.changeSliderValue(3, -5))
            self.SC_Inc_3_Large.activated.connect(lambda: self.changeSliderValue(3, 5))

            # THE NUMPAD SHORTCUTS ARE SET UP REGARDLESS OF WHAT THE CUSTOM INC/DEC SHORTCUTS ARE
            self.SC_Num1 = QShortcut(QKeySequence("1"), self)
            self.SC_Num1.activated.connect(lambda: self.numberShortcuts(1))
            self.SC_Num2 = QShortcut(QKeySequence("2"), self)
            self.SC_Num2.activated.connect(lambda: self.numberShortcuts(2))
            self.SC_Num3 = QShortcut(QKeySequence("3"), self)
            self.SC_Num3.activated.connect(lambda: self.numberShortcuts(3))
            self.SC_Num4 = QShortcut(QKeySequence("4"), self)
            self.SC_Num4.activated.connect(lambda: self.numberShortcuts(4))
            self.SC_Num5 = QShortcut(QKeySequence("5"), self)
            self.SC_Num5.activated.connect(lambda: self.numberShortcuts(5))
            self.SC_Num6 = QShortcut(QKeySequence("6"), self)
            self.SC_Num6.activated.connect(lambda: self.numberShortcuts(6))
            self.SC_Num7 = QShortcut(QKeySequence("7"), self)
            self.SC_Num7.activated.connect(lambda: self.numberShortcuts(7))
            self.SC_Num8 = QShortcut(QKeySequence("8"), self)
            self.SC_Num8.activated.connect(lambda: self.numberShortcuts(8))
            self.SC_Num9 = QShortcut(QKeySequence("9"), self)
            self.SC_Num9.activated.connect(lambda: self.numberShortcuts(9))

        def sortByHeader(self, theHeader):
            global availableLights
            global lastSortingField

            if theHeader < 2: # if we didn't click on the "Linked" or "Status" headers, start processing the sort
                sortingList = [] # a copy of the availableLights array
                checkForCustomNames = False # whether or not to ask to sort by custom names (if there aren't any custom names, then don't allow)

                for a in range(len(availableLights)): # copy the entire availableLights array into a temporary array to process it
                    if theHeader == 0 and availableLights[a][2] != "": # if the current light has a custom name (and we clicked on Name)
                        checkForCustomNames = True # then we need to ask what kind of sorting when we sort

                    sortingList.append([availableLights[a][0], availableLights[a][1], availableLights[a][2], availableLights[a][3], \
                                        availableLights[a][4], availableLights[a][5], availableLights[a][6], availableLights[a][7], \
                                        availableLights[a][0].name, availableLights[a][0].address, _get_light_rssi(availableLights[a])])
            else: # we clicked on the "Linked" or "Status" headers, which do not allow sorting
                sortingField = -1

            if theHeader == 0:
                sortDlg = QMessageBox(self)
                sortDlg.setIcon(QMessageBox.Question)
                sortDlg.setWindowTitle("Sort by...")
                sortDlg.setText("Which do you want to sort by?")
                   
                sortDlg.addButton(" RSSI (Signal Level) ", QMessageBox.ButtonRole.AcceptRole)
                sortDlg.addButton(" Type of Light ", QMessageBox.ButtonRole.AcceptRole)

                if checkForCustomNames == True: # if we have custom names available, then add that as an option
                    sortDlg.addButton("Custom Name", QMessageBox.ButtonRole.AcceptRole)    
                    
                sortDlg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                sortDlg.setIcon(QMessageBox.Warning)
                clickedButton = pyside_exec(sortDlg)

                if clickedButton == 0:
                    sortingField = 10 # sort by RSSI
                elif clickedButton == 1:
                    sortingField = 8 # sort by type of light
                elif clickedButton == 2:
                    if checkForCustomNames == True: # if the option was available for custom names, this is "custom name"
                        sortingField = 2 
                    else: # if the option wasn't available, then this is "cancel"
                        sortingField = -1 # cancel out of sorting - write this!
                elif clickedButton == 3: # this option is only available if custom names is accessible - if so, this is "cancel"
                        sortingField = -1 # cancel out of sorting - write this!
            elif theHeader == 1: # sort by MAC Address/GUID
                sortingField = 9

            if sortingField != -1: # we want to sort
                self.lightTable.horizontalHeader().setSortIndicatorShown(True) # show the sorting indicator

                if lastSortingField != sortingField: # if we're doing a different kind of sort than the last one
                    self.lightTable.horizontalHeader().setSortIndicator(theHeader, Qt.SortOrder.AscendingOrder) # force the header to "Ascending" order
                    if sortingField != 10: # if we're not looking at RSSI
                        doReverseSort = False # we need an ascending order search
                    else: # we ARE looking at RSSI
                        doReverseSort = True # if we're looking at RSSI, then the search order is reversed (as the smaller # is actually the higher value)
                else: # if it's the same as before, then take the cue from the last order
                    if self.lightTable.horizontalHeader().sortIndicatorOrder() == Qt.SortOrder.DescendingOrder:
                        if sortingField != 10:
                            doReverseSort = True
                        else:
                            doReverseSort = False
                    elif self.lightTable.horizontalHeader().sortIndicatorOrder() == Qt.SortOrder.AscendingOrder:
                        if sortingField != 10:
                            doReverseSort = False
                        else:
                            doReverseSort = True

                sortedList = sorted(sortingList, key = lambda x: x[sortingField], reverse = doReverseSort) # sort the list
                availableLights.clear() # clear the list of available lights

                for a in range(len(sortedList)): # rebuild the available lights list from the sorted list
                    availableLights.append([sortedList[a][0], sortedList[a][1], sortedList[a][2], sortedList[a][3], \
                                            sortedList[a][4], sortedList[a][5], sortedList[a][6], sortedList[a][7], \
                                            sortedList[a][8] if len(sortedList[a]) > 8 else 0])
                                        
                self.updateLights(False, False) # redraw the table with the new light list (don't reorder by preferred ID)
                lastSortingField = sortingField # keep track of the last field used for sorting, so we know whether or not to switch to ascending
            else:
                self.lightTable.horizontalHeader().setSortIndicatorShown(False) # hide the sorting indicator

        def switchToTab(self, theTab): # SWITCH TO THE REQUESTED TAB **IF IT IS AVAILABLE**
            if self.ColorModeTabWidget.isTabEnabled(theTab) == True:
                self.ColorModeTabWidget.setCurrentIndex(theTab)

        def numberShortcuts(self, theNumber):
            # THE KEYS (IF THERE AREN'T CUSTOM ONES SET UP):
            # 7 AND 9 ADJUST THE FIRST SLIDER ON A TAB
            # 4 AND 6 ADJUST THE SECOND SLIDER ON A TAB
            # 1 AND 3 ADJUST THE THIRD SLIDER ON A TAB
            # UNLESS WE'RE IN SCENE MODE, THEN THEY JUST SWITCH THE SCENE
            if theNumber == 1:
                if self.ColorModeTabWidget.currentIndex() == 2: # if we're on the SCENE tab, then the number keys correspond to an animation
                    self.computeValueANM(1)
                else: # if we're not, adjust the slider
                    if customKeys[16] == "1":
                        self.changeSliderValue(3, -1) # decrement slider 3
            elif theNumber == 2:
                if self.ColorModeTabWidget.currentIndex() == 2:
                    self.computeValueANM(2)
            elif theNumber == 3:
                if self.ColorModeTabWidget.currentIndex() == 2:
                    self.computeValueANM(3)
                else:
                    if customKeys[17] == "3":
                        self.changeSliderValue(3, 1) # increment slider 3
            elif theNumber == 4:
                if self.ColorModeTabWidget.currentIndex() == 2:
                    self.computeValueANM(4)
                else:
                    if customKeys[14] == "4":
                        self.changeSliderValue(2, -1) # decrement slider 2
            elif theNumber == 5:
                if self.ColorModeTabWidget.currentIndex() == 2:
                    self.computeValueANM(5)
            elif theNumber == 6:
                if self.ColorModeTabWidget.currentIndex() == 2:
                    self.computeValueANM(6)
                else:
                    if customKeys[15] == "6":
                        self.changeSliderValue(2, 1) # increment slider 2
            elif theNumber == 7:
                if self.ColorModeTabWidget.currentIndex() == 2:
                    self.computeValueANM(7)
                else:
                    if customKeys[12] == "7":
                        self.changeSliderValue(1, -1) # decrement slider 1
            elif theNumber == 8:
                if self.ColorModeTabWidget.currentIndex() == 2:
                    self.computeValueANM(8)
            elif theNumber == 9:
                if self.ColorModeTabWidget.currentIndex() == 2:
                    self.computeValueANM(9)
                else:
                    if customKeys[13] == "9":
                        self.changeSliderValue(1, 1) # increment slider 1

        def changeSliderValue(self, sliderToChange, changeAmt):
            if self.ColorModeTabWidget.currentIndex() == 0: # we have 2 sliders in CCT mode
                if sliderToChange == 1:
                    self.Slider_CCT_Hue.setValue(self.Slider_CCT_Hue.value() + changeAmt)
                elif sliderToChange == 2 or sliderToChange == 0:
                    self.Slider_CCT_Bright.setValue(self.Slider_CCT_Bright.value() + changeAmt)
            elif self.ColorModeTabWidget.currentIndex() == 1: # we have 3 sliders in HSI mode
                if sliderToChange == 1:
                    self.Slider_HSI_1_H.setValue(self.Slider_HSI_1_H.value() + changeAmt)
                elif sliderToChange == 2:
                    self.Slider_HSI_2_S.setValue(self.Slider_HSI_2_S.value() + changeAmt)
                elif sliderToChange == 3 or sliderToChange == 0:
                    self.Slider_HSI_3_L.setValue(self.Slider_HSI_3_L.value() + changeAmt)
            elif self.ColorModeTabWidget.currentIndex() == 2:
                if sliderToChange == 0: # the only "slider" in SCENE mode is the brightness
                    self.Slider_ANM_Brightness.setValue(self.Slider_ANM_Brightness.value() + changeAmt)

        def checkLightTab(self, selectedLight = -1):
            if self.ColorModeTabWidget.currentIndex() == 0: # if we're on the CCT tab, do the check
                if selectedLight == -1: # if we don't have a light selected
                    self.setupCCTBounds(globalCCTMin, globalCCTMax)
                else: # set up the gradient to show the range of color temperatures available
                    minK, maxK = getEffectiveCCTRange(selectedLight)
                    self.setupCCTBounds(minK, maxK)

            elif self.ColorModeTabWidget.currentIndex() == 4: # if we're on the Light Preferences tab
                if selectedLight != -1: # if there is a specific selected light
                    self.setupLightPrefsTab(selectedLight) # update the Prefs tab with the information for that selected light

        def getCCTTempStops(self, startRange, endRange):
            """Return gradient stops for the CCT temperature range."""
            rangeStep = (endRange - startRange) / 4
            stops = []
            for i in range(5):
                rgbValues = convert_K_to_RGB(startRange + (rangeStep * i))
                stops.append((0.25 * i, QColor(rgbValues[0], rgbValues[1], rgbValues[2])))
            return stops

        def getHSISatStops(self, hue):
            """Return gradient stops for saturation bar based on current hue."""
            newColor = convert_HSI_to_RGB(hue / 360)
            return [(0, QColor(255, 255, 255)), (1, QColor(newColor[0], newColor[1], newColor[2]))]

        def setupCCTBounds(self, startRange, endRange):
            self.TFV_CCT_Hue_Min.setText(str(startRange) + "K")
            self.TFV_CCT_Hue_Max.setText(str(endRange) + "K")

            self.Slider_CCT_Hue.setMinimum(startRange / 100)
            self.Slider_CCT_Hue.setMaximum(endRange / 100)
            
            # Update the gradient bar
            self.CCT_Temp_Gradient_BG.setStops(self.getCCTTempStops(startRange, endRange))

        def setupLightPrefsTab(self, selectedLight):
            # SET UP THE CUSTOM NAME TEXT BOX
            if availableLights[selectedLight][2] == "":
                self.customName.setChecked(False)
                self.customNameTF.setEnabled(False)
                self.customNameTF.setText("") # set the "custom name" to nothing
            else:
                self.customName.setChecked(True)
                self.customNameTF.setEnabled(True)
                self.customNameTF.setText(availableLights[selectedLight][2]) # set the "custom name" field to the custom name of this light

            # SET UP THE PREFERRED ID SPINBOX
            prefID = availableLights[selectedLight][8] if len(availableLights[selectedLight]) > 8 else 0
            self.preferredIDSpin.setValue(prefID)

            # SET UP THE MINIMUM AND MAXIMUM TEXT BOXES
            defaultRange = getLightSpecs(availableLights[selectedLight][0].name, "temp")

            if availableLights[selectedLight][4] == defaultRange:
                self.colorTempRange.setChecked(False)
                self.colorTempRange_Min_TF.setEnabled(False)
                self.colorTempRange_Max_TF.setEnabled(False)

                self.colorTempRange_Min_TF.setText(str(defaultRange[0]))
                self.colorTempRange_Max_TF.setText(str(defaultRange[1]))
            else:
                self.colorTempRange.setChecked(True)
                self.colorTempRange_Min_TF.setEnabled(True)
                self.colorTempRange_Max_TF.setEnabled(True)
                
                self.colorTempRange_Min_TF.setText(str(availableLights[selectedLight][4][0]))
                self.colorTempRange_Max_TF.setText(str(availableLights[selectedLight][4][1]))
            
            # IF THE OPTION TO SEND ONLY CCT MODE IS ENABLED, THEN ENABLE THAT CHECKBOX
            if availableLights[selectedLight][5] == True:
                self.onlyCCTModeCheck.setChecked(True)
            else:
                self.onlyCCTModeCheck.setChecked(False)

            self.checkLightPrefsEnables() # set up which fields on the panel are enabled

        def checkLightPrefsEnables(self): # enable/disable fields when clicking on checkboxes
            # allow/deny typing in the "custom name" field if the option is clicked
            if self.customName.isChecked():
                self.customNameTF.setEnabled(True)
            else:
                self.customNameTF.setEnabled(False)
                self.customNameTF.setText("")

            # allow/deny typing in the "minmum" and "maximum" fields if the option is clicked
            if self.colorTempRange.isChecked():
                self.colorTempRange_Min_TF.setEnabled(True)
                self.colorTempRange_Max_TF.setEnabled(True)
            else:
                selectedRows = self.selectedLights() # get the list of currently selected lights
                defaultSettings = getLightSpecs(availableLights[selectedRows[0]][0].name, "temp")

                self.colorTempRange_Min_TF.setText(str(defaultSettings[0]))
                self.colorTempRange_Max_TF.setText(str(defaultSettings[1]))

                self.colorTempRange_Min_TF.setEnabled(False)
                self.colorTempRange_Max_TF.setEnabled(False)
            
        def checkLightPrefs(self): # check the new settings and save the custom file
            selectedRows = self.selectedLights() # get the list of currently selected lights

            # CHECK DEFAULT SETTINGS AGAINST THE CURRENT SETTINGS
            defaultSettings = getLightSpecs(availableLights[selectedRows[0]][0].name)

            if self.colorTempRange.isChecked():
                newRange = [testValid("range_min", self.colorTempRange_Min_TF.text(), defaultSettings[1][0], 1000, 5600, True),
                            testValid("range_max", self.colorTempRange_Max_TF.text(), defaultSettings[1][1], 1000, 10000, True)]
            else:
                newRange = defaultSettings[1]

            changedPrefs = 0 # number of how many preferences have changed

            if len(selectedRows) == 1: # if we have 1 selected light - which should never be false, as we can't use Prefs with more than 1
                if self.customName.isChecked(): # if we're set to allow a custom name
                    if availableLights[selectedRows[0]][2] != self.customNameTF.text():
                        availableLights[selectedRows[0]][2] = self.customNameTF.text() # set this light's custom name to the text box
                        changedPrefs += 1 # add one to the preferences changed counter
                else: # we're not supposed to set a custom name (so delete it)
                    if availableLights[selectedRows[0]][2] != "":
                        availableLights[selectedRows[0]][2] = "" # clear the old custom name if we've turned this off
                        changedPrefs += 1 # add one to the preferences changed counter

                # IF A CUSTOM NAME IS SET UP FOR THIS LIGHT, THEN CHANGE THE TABLE TO REFLECT THAT
                if availableLights[selectedRows[0]][2] != "":
                    self.setTheTable([availableLights[selectedRows[0]][2] + " (" + availableLights[selectedRows[0]][0].name + ")" "\n  [ʀssɪ: " + _get_light_rssi(availableLights[selectedRows[0]]) + " dBm]",
                                    "", "", ""], selectedRows[0])
                else: # if there is no custom name, then reset the table to show that
                    self.setTheTable([availableLights[selectedRows[0]][0].name + "\n  [ʀssɪ: " + _get_light_rssi(availableLights[selectedRows[0]]) + " dBm]",
                                    "", "", ""], selectedRows[0])

                if self.colorTempRange.isChecked(): # if we've asked to save a custom temperature range for this light
                    if availableLights[selectedRows[0]][4] != newRange: # change the range in the available lights table if they are different
                        if defaultSettings[1] != newRange:
                            availableLights[selectedRows[0]][4][0] = newRange[0]
                            availableLights[selectedRows[0]][4][1] = newRange[1]
                            changedPrefs += 1 # add one to the preferences changed counter
                        else: # the ranges are the same as the default range, so we're not modifying those values
                            printDebugString("You asked for a custom range of color temperatures, but didn't specify a custom range, so not changing!")
                else: # if the custom temp checkbox is not clicked
                    if availableLights[selectedRows[0]][4] != defaultSettings[1]: # and the settings are not the defaults
                        availableLights[selectedRows[0]][4] = defaultSettings[1] # restore them to the defaults
                        changedPrefs += 1 # add one to the preferences changed counter

                if availableLights[selectedRows[0]][5] != self.onlyCCTModeCheck.isChecked():
                    availableLights[selectedRows[0]][5] = self.onlyCCTModeCheck.isChecked() # if the option to send BRI and HUE separately is checked, then turn that on
                    changedPrefs += 1

                # PREFERRED ID FOR LIGHT ALIASING
                newPrefID = self.preferredIDSpin.value()
                oldPrefID = availableLights[selectedRows[0]][8] if len(availableLights[selectedRows[0]]) > 8 else 0
                if newPrefID != oldPrefID:
                    if len(availableLights[selectedRows[0]]) > 8:
                        availableLights[selectedRows[0]][8] = newPrefID
                    else:
                        availableLights[selectedRows[0]].append(newPrefID)
                    changedPrefs += 1

                if changedPrefs > 0:
                    # IF ALL THE SETTINGS ARE THE SAME AS THE DEFAULT, THEN DELETE THE PREFS FILE (IF IT EXISTS)
                    currentPrefID = availableLights[selectedRows[0]][8] if len(availableLights[selectedRows[0]]) > 8 else 0
                    if defaultSettings[0] == self.customNameTF.text() and \
                    defaultSettings[1] == newRange and \
                    defaultSettings[2] == self.onlyCCTModeCheck.isChecked() and \
                    currentPrefID == 0:
                        printDebugString("All the options that are currently set are the defaults for this light, so the preferences file will be deleted.")
                        saveLightPrefs(selectedRows[0], True) # delete the old prefs file
                    else:
                        saveLightPrefs(selectedRows[0]) # save the light settings to a special file

                    loadLightAliases() # refresh alias table so names/IDs take effect immediately
                    self.updateLights(False) # reorder table to reflect any preferred ID changes
                else:                    
                    printDebugString("You don't have any new preferences to save, so we aren't saving any!")

        def setupGlobalLightPrefsTab(self, setDefault=False):
            if setDefault == False:
                self.findLightsOnStartup_check.setChecked(findLightsOnStartup)
                self.autoConnectToLights_check.setChecked(autoConnectToLights)
                self.printDebug_check.setChecked(printDebug)
                self.rememberLightsOnExit_check.setChecked(rememberLightsOnExit)
                self.rememberPresetsOnExit_check.setChecked(rememberPresetsOnExit)
                self.livePreview_check.setChecked(livePreview)
                self.autoReconnect_check.setChecked(autoReconnectOnDisconnect)
                self.hideConsoleOnLaunch_check.setChecked(hideConsoleOnLaunch)
                if _isFrozenExe:
                    self.hideConsoleOnLaunch_check.setChecked(False)
                    self.hideConsoleOnLaunch_check.setVisible(False)
                self.minimizeToTrayOnClose_check.setChecked(minimizeToTrayOnClose)
                self.httpAutoStart_check.setChecked(httpAutoStart)
                self.cctFallbackCombo.setCurrentIndex(0 if cctFallbackMode == "convert" else 1)
                self.enableLogTab_check.setChecked(enableLogTab)
                self.logToFile_check.setChecked(logToFile)
                self.globalCCTMinSpin.setValue(globalCCTMin)
                self.globalCCTMaxSpin.setValue(globalCCTMax)
                self.maxNumOfAttempts_field.setText(str(maxNumOfAttempts))
                self.acceptable_HTTP_IPs_field.setText("\n".join(acceptable_HTTP_IPs))
                self.whiteListedMACs_field.setText("\n".join(whiteListedMACs))
                self.SC_turnOffButton_field.setKeySequence(customKeys[0])
                self.SC_turnOnButton_field.setKeySequence(customKeys[1])
                self.SC_scanCommandButton_field.setKeySequence(customKeys[2])
                self.SC_tryConnectButton_field.setKeySequence(customKeys[3])
                self.SC_Tab_CCT_field.setKeySequence(customKeys[4])
                self.SC_Tab_HSI_field.setKeySequence(customKeys[5])
                self.SC_Tab_SCENE_field.setKeySequence(customKeys[6])
                self.SC_Tab_PREFS_field.setKeySequence(customKeys[7])
                self.SC_Dec_Bri_Small_field.setKeySequence(customKeys[8])
                self.SC_Inc_Bri_Small_field.setKeySequence(customKeys[9])
                self.SC_Dec_Bri_Large_field.setKeySequence(customKeys[10])
                self.SC_Inc_Bri_Large_field.setKeySequence(customKeys[11])
                self.SC_Dec_1_Small_field.setKeySequence(customKeys[12])
                self.SC_Inc_1_Small_field.setKeySequence(customKeys[13])
                self.SC_Dec_2_Small_field.setKeySequence(customKeys[14])
                self.SC_Inc_2_Small_field.setKeySequence(customKeys[15])
                self.SC_Dec_3_Small_field.setKeySequence(customKeys[16])
                self.SC_Inc_3_Small_field.setKeySequence(customKeys[17])
                self.SC_Dec_1_Large_field.setKeySequence(customKeys[18])
                self.SC_Inc_1_Large_field.setKeySequence(customKeys[19])
                self.SC_Dec_2_Large_field.setKeySequence(customKeys[20])
                self.SC_Inc_2_Large_field.setKeySequence(customKeys[21])
                self.SC_Dec_3_Large_field.setKeySequence(customKeys[22])
                self.SC_Inc_3_Large_field.setKeySequence(customKeys[23])
            else: # if you clicked the RESET button, reset all preference values to their defaults
                self.findLightsOnStartup_check.setChecked(True)
                self.autoConnectToLights_check.setChecked(True)
                self.printDebug_check.setChecked(True)
                self.rememberLightsOnExit_check.setChecked(False)
                self.rememberPresetsOnExit_check.setChecked(True)
                self.livePreview_check.setChecked(True)
                self.autoReconnect_check.setChecked(True)
                self.hideConsoleOnLaunch_check.setChecked(False)
                self.minimizeToTrayOnClose_check.setChecked(True)
                self.httpAutoStart_check.setChecked(False)
                self.cctFallbackCombo.setCurrentIndex(0)  # Convert
                self.enableLogTab_check.setChecked(True)
                self.logToFile_check.setChecked(False)
                self.globalCCTMinSpin.setValue(3200)
                self.globalCCTMaxSpin.setValue(5600)
                self.maxNumOfAttempts_field.setText("6")
                self.acceptable_HTTP_IPs_field.setText("\n".join(["127.0.0.1", "192.168.", "10."]))
                self.whiteListedMACs_field.setText("")
                self.SC_turnOffButton_field.setKeySequence("Ctrl+PgDown")
                self.SC_turnOnButton_field.setKeySequence("Ctrl+PgUp")
                self.SC_scanCommandButton_field.setKeySequence("Ctrl+Shift+S")
                self.SC_tryConnectButton_field.setKeySequence("Ctrl+Shift+C")
                self.SC_Tab_CCT_field.setKeySequence("Alt+1")
                self.SC_Tab_HSI_field.setKeySequence("Alt+2")
                self.SC_Tab_SCENE_field.setKeySequence("Alt+3")
                self.SC_Tab_PREFS_field.setKeySequence("Alt+4")
                self.SC_Dec_Bri_Small_field.setKeySequence("/")
                self.SC_Inc_Bri_Small_field.setKeySequence("*")
                self.SC_Dec_Bri_Large_field.setKeySequence("Ctrl+/")
                self.SC_Inc_Bri_Large_field.setKeySequence("Ctrl+*")
                self.SC_Dec_1_Small_field.setKeySequence("7")
                self.SC_Inc_1_Small_field.setKeySequence("9")
                self.SC_Dec_2_Small_field.setKeySequence("4")
                self.SC_Inc_2_Small_field.setKeySequence("6")
                self.SC_Dec_3_Small_field.setKeySequence("1")
                self.SC_Inc_3_Small_field.setKeySequence("3")
                self.SC_Dec_1_Large_field.setKeySequence("Ctrl+7")
                self.SC_Inc_1_Large_field.setKeySequence("Ctrl+9")
                self.SC_Dec_2_Large_field.setKeySequence("Ctrl+4")
                self.SC_Inc_2_Large_field.setKeySequence("Ctrl+6")
                self.SC_Dec_3_Large_field.setKeySequence("Ctrl+1")
                self.SC_Inc_3_Large_field.setKeySequence("Ctrl+3")

        def saveGlobalPrefs(self):
            # change these global values to the new values in Prefs
            global customKeys, autoConnectToLights, printDebug, rememberLightsOnExit, rememberPresetsOnExit, autoReconnectOnDisconnect, maxNumOfAttempts, acceptable_HTTP_IPs, whiteListedMACs, hideConsoleOnLaunch, minimizeToTrayOnClose, httpAutoStart, cctFallbackMode, enableLogTab, logToFile, globalCCTMin, globalCCTMax, globalCCTMin, globalCCTMax, enableLogTab, logToFile, globalCCTMin, globalCCTMax, cctFallbackMode

            finalPrefs = [] # list of final prefs to merge together at the end

            if not self.findLightsOnStartup_check.isChecked(): # this option is usually on, so only add on false
                finalPrefs.append("findLightsOnStartup=0")
            
            if not self.autoConnectToLights_check.isChecked(): # this option is usually on, so only add on false
                autoConnectToLights = False
                finalPrefs.append("autoConnectToLights=0")
            else:
                autoConnectToLights = True
            
            if not self.printDebug_check.isChecked(): # this option is usually on, so only add on false
                printDebug = False
                finalPrefs.append("printDebug=0")
            else:
                printDebug = True
            
            if self.rememberLightsOnExit_check.isChecked(): # this option is usually off, so only add on true
                rememberLightsOnExit = True
                finalPrefs.append("rememberLightsOnExit=1")
            else:
                rememberLightsOnExit = False

            if not self.rememberPresetsOnExit_check.isChecked(): # this option is usually on, so only add if false
                rememberPresetsOnExit = False
                finalPrefs.append("rememberPresetsOnExit=0")
            else:
                rememberPresetsOnExit = True

            global livePreview
            if not self.livePreview_check.isChecked():
                livePreview = False
                finalPrefs.append("livePreview=0")
                self.applyButton.setVisible(True)
            else:
                livePreview = True
                self.applyButton.setVisible(False)

            if not self.autoReconnect_check.isChecked(): # this option is usually on, so only add if false
                autoReconnectOnDisconnect = False
                finalPrefs.append("autoReconnectOnDisconnect=0")
            else:
                autoReconnectOnDisconnect = True

            if self.hideConsoleOnLaunch_check.isChecked(): # this option is usually off, so only add on true
                hideConsoleOnLaunch = True
                finalPrefs.append("hideConsoleOnLaunch=1")
                hideConsoleWindow()
                if hasattr(self, '_consoleVisible'):
                    self._consoleVisible = False
                    if self._consoleAction:
                        self._consoleAction.setText("Show Console")
            else:
                hideConsoleOnLaunch = False
                showConsoleWindow()
                if hasattr(self, '_consoleVisible'):
                    self._consoleVisible = True
                    if self._consoleAction:
                        self._consoleAction.setText("Hide Console")

            if not self.minimizeToTrayOnClose_check.isChecked(): # this option is usually on, so only add if false
                minimizeToTrayOnClose = False
                finalPrefs.append("minimizeToTrayOnClose=0")
            else:
                minimizeToTrayOnClose = True

            if self.httpAutoStart_check.isChecked(): # this option is usually off, so only add on true
                httpAutoStart = True
                finalPrefs.append("httpAutoStart=1")
            else:
                httpAutoStart = False

            cctFallbackMode = "convert" if self.cctFallbackCombo.currentIndex() == 0 else "ignore"
            if cctFallbackMode != "convert":  # only save non-default
                finalPrefs.append("cctFallbackMode=" + cctFallbackMode)

            if not self.enableLogTab_check.isChecked():
                enableLogTab = False
                finalPrefs.append("enableLogTab=0")
            else:
                enableLogTab = True

            if self.logToFile_check.isChecked():
                logToFile = True
                finalPrefs.append("logToFile=1")
            else:
                logToFile = False

            globalCCTMin = self.globalCCTMinSpin.value()
            globalCCTMax = self.globalCCTMaxSpin.value()
            if globalCCTMin > globalCCTMax:
                globalCCTMin, globalCCTMax = globalCCTMax, globalCCTMin
                self.globalCCTMinSpin.setValue(globalCCTMin)
                self.globalCCTMaxSpin.setValue(globalCCTMax)
            if globalCCTMin != 3200:
                finalPrefs.append("globalCCTMin=" + str(globalCCTMin))
            if globalCCTMax != 5600:
                finalPrefs.append("globalCCTMax=" + str(globalCCTMax))
            
            maxAttemptText = self.maxNumOfAttempts_field.text().strip()
            if maxAttemptText == "" or not maxAttemptText.isdigit():
                maxAttemptText = "6"  # default
                self.maxNumOfAttempts_field.setText(maxAttemptText)
            if maxAttemptText != "6": # the default for this option is 6 attempts
                maxNumOfAttempts = int(maxAttemptText)
                finalPrefs.append("maxNumOfAttempts=" + maxAttemptText)
            else:
                maxNumOfAttempts = 6

            # FIGURE OUT IF THE HTTP IP ADDRESSES HAVE CHANGED
            returnedList_HTTP_IPs = self.acceptable_HTTP_IPs_field.toPlainText().split("\n")
            
            if returnedList_HTTP_IPs != ["127.0.0.1", "192.168.", "10."]: # if the list of HTTP IPs have changed
                acceptable_HTTP_IPs = returnedList_HTTP_IPs # change the global HTTP IPs available
                finalPrefs.append("acceptable_HTTP_IPs=" + ";".join(acceptable_HTTP_IPs)) # add the new ones to the preferences
            else:
                acceptable_HTTP_IPs = ["127.0.0.1", "192.168.", "10."] # if we reset the IPs, then re-reset the parameter

            # ADD WHITELISTED LIGHTS TO PREFERENCES IF THEY EXIST
            returnedList_whiteListedMACs = self.whiteListedMACs_field.toPlainText().replace(" ", "").split("\n") # remove spaces and split on newlines

            if returnedList_whiteListedMACs[0] != "": # if we have any MAC addresses specified
                whiteListedMACs = returnedList_whiteListedMACs # then set the list to the addresses specified
                finalPrefs.append("whiteListedMACs=" + ";".join(whiteListedMACs)) # add the new addresses to the preferences
            else:
                whiteListedMACs = [] # or clear the list
            
            # SET THE NEW KEYBOARD SHORTCUTS TO THE VALUES IN PREFERENCES
            customKeys[0] = self.SC_turnOffButton_field.getKeySequence()
            customKeys[1] = self.SC_turnOnButton_field.getKeySequence()
            customKeys[2] = self.SC_scanCommandButton_field.getKeySequence()
            customKeys[3] = self.SC_tryConnectButton_field.getKeySequence()
            customKeys[4] = self.SC_Tab_CCT_field.getKeySequence()
            customKeys[5] = self.SC_Tab_HSI_field.getKeySequence()
            customKeys[6] = self.SC_Tab_SCENE_field.getKeySequence()
            customKeys[7] = self.SC_Tab_PREFS_field.getKeySequence()
            customKeys[8] = self.SC_Dec_Bri_Small_field.getKeySequence()
            customKeys[9] = self.SC_Inc_Bri_Small_field.getKeySequence()
            customKeys[10] = self.SC_Dec_Bri_Large_field.getKeySequence()
            customKeys[11] = self.SC_Inc_Bri_Large_field.getKeySequence()
            customKeys[12] = self.SC_Dec_1_Small_field.getKeySequence()
            customKeys[13] = self.SC_Inc_1_Small_field.getKeySequence()
            customKeys[14] = self.SC_Dec_2_Small_field.getKeySequence()
            customKeys[15] = self.SC_Inc_2_Small_field.getKeySequence()
            customKeys[16] = self.SC_Dec_3_Small_field.getKeySequence()
            customKeys[17] = self.SC_Inc_3_Small_field.getKeySequence()
            customKeys[18] = self.SC_Dec_1_Large_field.getKeySequence()
            customKeys[19] = self.SC_Inc_1_Large_field.getKeySequence()
            customKeys[20] = self.SC_Dec_2_Large_field.getKeySequence()
            customKeys[21] = self.SC_Inc_2_Large_field.getKeySequence()
            customKeys[22] = self.SC_Dec_3_Large_field.getKeySequence()
            customKeys[23] = self.SC_Inc_3_Large_field.getKeySequence()

            self.setupShortcutKeys() # change shortcut key assignments to the new values in prefs

            if customKeys[0] != "Ctrl+PgDown": 
                finalPrefs.append("SC_turnOffButton=" + customKeys[0])
            
            if customKeys[1] != "Ctrl+PgUp":
                finalPrefs.append("SC_turnOnButton=" + customKeys[1])
            
            if customKeys[2] != "Ctrl+Shift+S":
                finalPrefs.append("SC_scanCommandButton=" + customKeys[2])
            
            if customKeys[3] != "Ctrl+Shift+C":
                finalPrefs.append("SC_tryConnectButton=" + customKeys[3])
            
            if customKeys[4] != "Alt+1":
                finalPrefs.append("SC_Tab_CCT=" + customKeys[4])
            
            if customKeys[5] != "Alt+2":
                finalPrefs.append("SC_Tab_HSI=" + customKeys[5])
            
            if customKeys[6] != "Alt+3":
                finalPrefs.append("SC_Tab_SCENE=" + customKeys[6])
            
            if customKeys[7] != "Alt+4":
                finalPrefs.append("SC_Tab_PREFS=" + customKeys[7])
            
            if customKeys[8] != "/":
                finalPrefs.append("SC_Dec_Bri_Small=" + customKeys[8])
            
            if customKeys[9] != "*":
                finalPrefs.append("SC_Inc_Bri_Small=" + customKeys[9])
            
            if customKeys[10] != "Ctrl+/":
                finalPrefs.append("SC_Dec_Bri_Large=" + customKeys[10])
            
            if customKeys[11] != "Ctrl+*":
                finalPrefs.append("SC_Inc_Bri_Large=" + customKeys[11])
            
            if customKeys[12] != "7":
                finalPrefs.append("SC_Dec_1_Small=" + customKeys[12])
            
            if customKeys[13] != "9":
                finalPrefs.append("SC_Inc_1_Small=" + customKeys[13])
            
            if customKeys[14] != "4":
                finalPrefs.append("SC_Dec_2_Small=" + customKeys[14])
            
            if customKeys[15] != "6":
                finalPrefs.append("SC_Inc_2_Small=" + customKeys[15])
            
            if customKeys[16] != "1":
                finalPrefs.append("SC_Dec_3_Small=" + customKeys[16])
            
            if customKeys[17] != "3":
                finalPrefs.append("SC_Inc_3_Small=" + customKeys[17])
            
            if customKeys[18] != "Ctrl+7":
                finalPrefs.append("SC_Dec_1_Large=" + customKeys[18])
            
            if customKeys[19] != "Ctrl+9":
                finalPrefs.append("SC_Inc_1_Large=" + customKeys[19])
            
            if customKeys[20] != "Ctrl+4":
                finalPrefs.append("SC_Dec_2_Large=" + customKeys[20])
            
            if customKeys[21] != "Ctrl+6":
                finalPrefs.append("SC_Inc_2_Large=" + customKeys[21])
            
            if customKeys[22] != "Ctrl+1":
                finalPrefs.append("SC_Dec_3_Large=" + customKeys[22])
            
            if customKeys[23] != "Ctrl+3":
                finalPrefs.append("SC_Inc_3_Large=" + customKeys[23])

            # CARRY "HIDDEN" DEBUGGING OPTIONS TO PREFERENCES FILE
            if enableTabsOnLaunch == True:
                finalPrefs.append("enableTabsOnLaunch=1")
               
            if len(finalPrefs) > 0: # if we actually have preferences to save...
                with open(globalPrefsFile, mode="w", encoding="utf-8") as prefsFileToWrite:
                    prefsFileToWrite.write(("\n").join(finalPrefs)) # then write them to the prefs file

                # PRINT THIS INFORMATION WHETHER DEBUG OUTPUT IS TURNED ON OR NOT
                print("New global preferences saved in " + globalPrefsFile + " - here is the list:")

                for a in range(len(finalPrefs)):
                    print(" > " + finalPrefs[a]) # iterate through the list of preferences and show the new value(s) you set
            else: # there are no preferences to save, so clean up the file (if it exists)
                print("There are no preferences to save (all preferences are currently set to their default values).")
                
                if os.path.exists(globalPrefsFile): # if a previous preferences file exists
                    print("Since all preferences are set to their defaults, we are deleting the NeewerLux.prefs file.")
                    os.remove(globalPrefsFile) # ...delete it!

        def setupShortcutKeys(self):
            self.SC_turnOffButton.setKey(QKeySequence(customKeys[0]))
            self.SC_turnOnButton.setKey(QKeySequence(customKeys[1]))
            self.SC_scanCommandButton.setKey(QKeySequence(customKeys[2]))
            self.SC_tryConnectButton.setKey(QKeySequence(customKeys[3]))
            self.SC_Tab_CCT.setKey(QKeySequence(customKeys[4]))
            self.SC_Tab_HSI.setKey(QKeySequence(customKeys[5]))
            self.SC_Tab_SCENE.setKey(QKeySequence(customKeys[6]))
            self.SC_Tab_PREFS.setKey(QKeySequence(customKeys[7]))
            self.SC_Dec_Bri_Small.setKey(QKeySequence(customKeys[8]))
            self.SC_Inc_Bri_Small.setKey(QKeySequence(customKeys[9]))
            self.SC_Dec_Bri_Large.setKey(QKeySequence(customKeys[10]))
            self.SC_Inc_Bri_Large.setKey(QKeySequence(customKeys[11]))

            # IF THERE ARE CUSTOM KEYS SET UP FOR THE SMALL INCREMENTS, SET THEM HERE (AS THE NUMPAD KEYS WILL BE TAKEN AWAY IN THAT INSTANCE):
            if customKeys[12] != "7":
                self.SC_Dec_1_Small.setKey(QKeySequence(customKeys[12]))
            else: # if we changed back to default, clear the key assignment if there was one before
                self.SC_Dec_1_Small.setKey("")

            if customKeys[13] != "9":
                self.SC_Inc_1_Small.setKey(QKeySequence(customKeys[13]))
            else:
                self.SC_Inc_1_Small.setKey("")

            if customKeys[14] != "4":
                self.SC_Dec_2_Small.setKey(QKeySequence(customKeys[14]))
            else:
                self.SC_Dec_2_Small.setKey("")
            
            if customKeys[15] != "6":
                self.SC_Inc_2_Small.setKey(QKeySequence(customKeys[15]))
            else:
                self.SC_Inc_2_Small.setKey("")

            if customKeys[16] != "1":
                self.SC_Dec_3_Small.setKey(QKeySequence(customKeys[16]))
            else:
                self.SC_Dec_3_Small.setKey("")

            if customKeys[17] != "3":
                self.SC_Inc_3_Small.setKey(QKeySequence(customKeys[17]))
            else:
                self.SC_Inc_3_Small.setKey("")
                
            self.SC_Dec_1_Large.setKey(QKeySequence(customKeys[18]))
            self.SC_Inc_1_Large.setKey(QKeySequence(customKeys[19]))
            self.SC_Dec_2_Large.setKey(QKeySequence(customKeys[20]))
            self.SC_Inc_2_Large.setKey(QKeySequence(customKeys[21]))
            self.SC_Dec_3_Large.setKey(QKeySequence(customKeys[22]))
            self.SC_Inc_3_Large.setKey(QKeySequence(customKeys[23]))

        # CHECK TO SEE WHETHER OR NOT TO ENABLE/DISABLE THE "Connect" BUTTON OR CHANGE THE PREFS TAB
        def selectionChanged(self):
            selectedRows = self.selectedLights() # get the list of currently selected lights

            if len(selectedRows) > 0: # if we have a selection
                self.tryConnectButton.setEnabled(True) # if we have light(s) selected in the table, then enable the "Connect" button

                if len(selectedRows) == 1: # we have exactly one light selected
                    self.ColorModeTabWidget.setTabEnabled(4, True) # enable the "Preferences" tab for this light

                    # SWITCH THE TURN ON/OFF BUTTONS ON, AND CHANGE TEXT TO SINGLE BUTTON TEXT
                    self.turnOffButton.setText("Turn Light Off")
                    self.turnOffButton.setEnabled(True)
                    self.turnOnButton.setText("Turn Light On")
                    self.turnOnButton.setEnabled(True)

                    self.ColorModeTabWidget.setTabEnabled(0, True)

                    if availableLights[selectedRows[0]][5] == True: # if this light is CCT only, then disable the HSI and ANM tabs
                        self.ColorModeTabWidget.setTabEnabled(1, False) # disable the HSI mode tab
                        self.ColorModeTabWidget.setTabEnabled(2, False) # disable the ANM/SCENE tab
                    else: # we can use HSI and ANM/SCENE modes, so enable those tabs
                        self.ColorModeTabWidget.setTabEnabled(1, True) # enable the HSI mode tab
                        self.ColorModeTabWidget.setTabEnabled(2, True) # enable the ANM/SCENE tab

                    currentlySelectedRow = selectedRows[0] # get the row index of the 1 selected item
                    self.checkLightTab(currentlySelectedRow) # if we're on CCT, check to see if this light can use extended values + on Prefs, update Prefs

                    # RECALL LAST SENT SETTING FOR THIS PARTICULAR LIGHT, IF A SETTING EXISTS
                    if availableLights[currentlySelectedRow][3] != []: # if the last set parameters aren't empty
                        if availableLights[currentlySelectedRow][6] != False: # if the light is listed as being turned ON
                            sendValue = availableLights[currentlySelectedRow][3] # make the current "sendValue" the last set parameter so it doesn't re-send it on re-load

                            if sendValue[1] == 135: # the last parameter was a CCT mode change
                                self.setUpGUI(colorMode="CCT",
                                        brightness=sendValue[3],
                                        temp=sendValue[4])
                            elif sendValue[1] == 134: # the last parameter was a HSI mode change
                                self.setUpGUI(colorMode="HSI",
                                        hue=sendValue[3] + (256 * sendValue[4]),
                                        sat=sendValue[5],
                                        brightness=sendValue[6])
                            elif sendValue[1] == 136: # the last parameter was a ANM/SCENE mode change
                                self.setUpGUI(colorMode="ANM",
                                        brightness=sendValue[3],
                                        scene=sendValue[4])
                        else:
                            self.ColorModeTabWidget.setCurrentIndex(0) # switch to the CCT tab if the light is off and there ARE prior parameters
                    else:
                        self.ColorModeTabWidget.setCurrentIndex(0) # switch to the CCT tab if there are no prior parameters
                else: # we have multiple lights selected
                    # SWITCH THE TURN ON/OFF BUTTONS ON, AND CHANGE TEXT TO MULTIPLE LIGHTS TEXT
                    self.turnOffButton.setText("Turn Light(s) Off")
                    self.turnOffButton.setEnabled(True)
                    self.turnOnButton.setText("Turn Light(s) On")
                    self.turnOnButton.setEnabled(True)

                    self.ColorModeTabWidget.setTabEnabled(0, True)
                    self.ColorModeTabWidget.setTabEnabled(1, True) # enable the "HSI" mode tab
                    self.ColorModeTabWidget.setTabEnabled(2, True) # enable the "ANM/SCENE" mode tab
                    self.ColorModeTabWidget.setTabEnabled(4, False) # disable the "Preferences" tab, as we have multiple lights selected
            else: # the selection has been cleared or there are no lights to select
                currentTab = self.ColorModeTabWidget.currentIndex() # get the currently selected tab (so when we disable the tabs, we stick on the current one)
                self.tryConnectButton.setEnabled(False) # if we have no lights selected, disable the Connect button

                # SWITCH THE TURN ON/OFF BUTTONS OFF, AND CHANGE TEXT TO GENERIC TEXT
                self.turnOffButton.setText("Turn Light(s) Off")
                self.turnOffButton.setEnabled(False)
                self.turnOnButton.setText("Turn Light(s) On")
                self.turnOnButton.setEnabled(False)

                self.ColorModeTabWidget.setTabEnabled(0, False) # disable the "CCT" mode tab
                self.ColorModeTabWidget.setTabEnabled(1, False) # disable the "HSI" mode tab
                self.ColorModeTabWidget.setTabEnabled(2, False) # disable the "ANM/SCENE" mode tab
                # Animations tab (3) stays enabled
                self.ColorModeTabWidget.setTabEnabled(4, False) # disable the "Preferences" tab, as we have no lights selected

                if currentTab not in (3, 5): # if user is on Animations or Global Prefs, keep them there
                    self.ColorModeTabWidget.setCurrentIndex(currentTab) # disable the tabs, but don't switch the current one shown
                else:
                    self.ColorModeTabWidget.setCurrentIndex(0) # if we're on Prefs, then switch to the CCT tab

                self.checkLightTab() # check to see if we're on the CCT tab - if we are, then restore order

        # ADD A LIGHT TO THE TABLE VIEW
        def setTheTable(self, infoArray, rowToChange = -1):
            """Update the light table. Must be called from the main/GUI thread."""
            if rowToChange == -1:
                currentRow = self.lightTable.rowCount()
                self.lightTable.insertRow(currentRow) # if rowToChange is not specified, then we'll make a new row at the end
                self.lightTable.setItem(currentRow, 0, QTableWidgetItem())
                self.lightTable.setItem(currentRow, 1, QTableWidgetItem())
                self.lightTable.setItem(currentRow, 2, QTableWidgetItem())
                self.lightTable.setItem(currentRow, 3, QTableWidgetItem())
            else:
                currentRow = rowToChange # change data for the specified row

            # THIS SECTION BELOW LIMITS UPDATING THE TABLE **ONLY** IF THE DATA SUPPLIED IS DIFFERENT THAN IT WAS ORIGINALLY
            if infoArray[0] != "": # the name of the light
                if rowToChange == -1 or (rowToChange != -1 and infoArray[0] != self.returnTableInfo(rowToChange, 0)):
                    self.lightTable.item(currentRow, 0).setText(infoArray[0])
            if infoArray[1] != "": # the MAC address of the light
                if rowToChange == -1 or (rowToChange != -1 and infoArray[1] != self.returnTableInfo(rowToChange, 1)):
                    self.lightTable.item(currentRow, 1).setText(infoArray[1])
            if infoArray[2] != "": # the Linked status of the light
                if rowToChange == -1 or (rowToChange != -1 and infoArray[2] != self.returnTableInfo(rowToChange, 2)):
                    self.lightTable.item(currentRow, 2).setText(infoArray[2])
                    self.lightTable.item(currentRow, 2).setTextAlignment(Qt.AlignCenter) # align the light status info to be center-justified
            if infoArray[3] != "": # the current status message of the light
                if rowToChange == -1 or (rowToChange != -1 and infoArray[3] != self.returnTableInfo(rowToChange, 3)):
                    self.lightTable.item(currentRow, 3).setText(infoArray[3])

            self.lightTable.resizeRowsToContents()

        def returnTableInfo(self, row, column):
            return self.lightTable.item(row, column).text()

        def _appendLog(self, msg):
            """Append a timestamped message to the Log tab (main thread only)."""
            if enableLogTab:
                sb = self.logTextEdit.verticalScrollBar()
                atBottom = sb.value() >= sb.maximum() - 10
                self.logTextEdit.append(msg)
                if atBottom:
                    sb.setValue(sb.maximum())

        def _saveLogToFile(self):
            """Save current log contents to the log file."""
            try:
                createLightPrefsFolder()
                with open(logFilePath, "w", encoding="utf-8") as f:
                    f.write(self.logTextEdit.toPlainText())
                self.statusBar.showMessage("Log saved to " + logFilePath)
            except Exception as e:
                self.statusBar.showMessage("Error saving log: " + str(e))

        def _checkForUpdates(self):
            """Check GitHub for a newer version of NeewerLux (runs in a background thread)."""
            self.checkUpdateButton.setEnabled(False)
            self.checkUpdateButton.setText("Checking...")
            self.updateBanner.setVisible(False)

            def _doCheck():
                try:
                    import urllib.request, json as _json
                    req = urllib.request.Request(NEEWERLUX_RELEASES_API,
                        headers={"User-Agent": "NeewerLux/" + NEEWERLUX_VERSION, "Accept": "application/vnd.github.v3+json"})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = _json.loads(resp.read().decode("utf-8"))
                    tag = data.get("tag_name", "").lstrip("vV")
                    url = data.get("html_url", NEEWERLUX_REPO_URL + "releases")
                    body = data.get("body", "")[:200]
                    self._updateResultSignal.emit(tag, url, body, "")
                except Exception as e:
                    self._updateResultSignal.emit("", "", "", str(e))

            import threading
            threading.Thread(target=_doCheck, daemon=True, name="updateCheck").start()

        def _onUpdateResult(self, tag, url, body, err):
            """Handle update check result on the main thread (via signal)."""
            self.checkUpdateButton.setEnabled(True)
            self.checkUpdateButton.setText("Check for Updates")
            if err:
                self.updateBanner.setText("Could not check for updates: " + err)
                self.updateBanner.setStyleSheet("QLabel { background-color: #3a2a1a; color: #ff9800; padding: 8px; border: 1px solid #ff9800; border-radius: 4px; }")
                self.updateBanner.setVisible(True)
            elif tag and tag != NEEWERLUX_VERSION:
                try:
                    remote = tuple(int(x) for x in tag.split("."))
                    local = tuple(int(x) for x in NEEWERLUX_VERSION.split("."))
                    if remote > local:
                        notePreview = (" — " + body.split("\n")[0]) if body else ""
                        self.updateBanner.setText(
                            "<b>Update available: v" + tag + "</b>" + notePreview +
                            "<br><a href='" + url + "' style='color:#81c784'>Download from GitHub</a>")
                        self.updateBanner.setStyleSheet("QLabel { background-color: #1a3a1a; color: #4caf50; padding: 8px; border: 1px solid #4caf50; border-radius: 4px; }")
                        self.updateBanner.setVisible(True)
                        return
                except (ValueError, TypeError):
                    pass
                self.updateBanner.setText("You are running NeewerLux v" + NEEWERLUX_VERSION + " (latest: v" + tag + ")")
                self.updateBanner.setStyleSheet("QLabel { background-color: #1a2a3a; color: #64b5f6; padding: 8px; border: 1px solid #64b5f6; border-radius: 4px; }")
                self.updateBanner.setVisible(True)
            else:
                self.updateBanner.setText("You are running the latest version (v" + NEEWERLUX_VERSION + ")")
                self.updateBanner.setStyleSheet("QLabel { background-color: #1a3a1a; color: #4caf50; padding: 8px; border: 1px solid #4caf50; border-radius: 4px; }")
                self.updateBanner.setVisible(True)

        # CLEAR ALL LIGHTS FROM THE TABLE VIEW
        def clearTheTable(self):
            if self.lightTable.rowCount() != 0:
                self.lightTable.clearContents()
                self.lightTable.setRowCount(0)

        def selectRows(self, rowsToSelect):
            self.lightTable.clearSelection()
            indexes = [self.lightTable.model().index(r, 0) for r in rowsToSelect]
            [self.lightTable.selectionModel().select(i, QItemSelectionModel.Select | QItemSelectionModel.Rows) for i in indexes]
            
        # TELL THE BACKGROUND THREAD TO START LOOKING FOR LIGHTS
        def startSelfSearch(self):
            global threadAction
            threadAction = "discover"

            self.statusBar.showMessage("Please wait - searching for Neewer lights...")

        # TELL THE BACKGROUND THREAD TO START CONNECTING TO LIGHTS
        def startConnect(self):
            global threadAction
            threadAction = "connect"

        # TELL THE BACKGROUND THREAD TO START SENDING TO THE LIGHTS
        def startSend(self):
            global threadAction

            # If live preview is off, don't auto-send — user clicks Apply instead
            if not livePreview:
                return

            # If an animation is playing, stop it — user is taking manual control
            if animationRunning:
                stopAnimation()
                self.animPlayButton.setEnabled(True)
                self.animStopButton.setEnabled(False)
                self.animStatusLabel.setText("Stopped")

            if threadAction == "":
                threadAction = "send"

        def manualApply(self):
            """Send current values when live preview is off."""
            global threadAction

            if animationRunning:
                stopAnimation()
                self.animPlayButton.setEnabled(True)
                self.animStopButton.setEnabled(False)
                self.animStatusLabel.setText("Stopped")

            if threadAction == "":
                threadAction = "send"

        # IF YOU CLICK ON ONE OF THE TABS, THIS WILL SWITCH THE VIEW/SEND A NEW SIGNAL FROM THAT SPECIFIC TAB
        def tabChanged(self, i):
            currentSelection = self.selectedLights() # get the list of currently selected lights

            if i == 0: # we clicked on the CCT tab
                if len(currentSelection) > 0: # if we have something selected
                    if len(currentSelection) == 1: # if we have just one light selected
                        self.checkLightTab(currentSelection[0]) # set up the current light's CCT bounds
                    else:
                        self.checkLightTab() # reset the bounds to the normal values (5600K)
                # Always compute the bytestring so Apply has current values ready
                self.computeValueCCT()
            elif i == 1: # we clicked on the HSI tab
                if len(currentSelection) == 1:
                    self.HSI_Sat_Gradient_BG.setStops(self.getHSISatStops(self.Slider_HSI_1_H.value()))
                # Always compute the bytestring so Apply has current values ready
                self.computeValueHSI()
            elif i == 2: # we clicked on the SCENE tab
                pass # skip this, we don't want the animation automatically triggering when we go to this page
            elif i == 3: # we clicked on the ANIMATIONS tab
                pass # no automatic action needed
            elif i == 4: # we clicked on the LIGHT PREFS tab
                if len(currentSelection) == 1:
                    self.setupLightPrefsTab(currentSelection[0])
            elif i == 5: # we clicked on the Global PREFS tab
                self.setupGlobalLightPrefsTab()
            elif i == 6: # Info tab
                pass
            elif i == 7: # Log tab
                pass

        # COMPUTE A BYTESTRING FOR THE CCT SECTION
        def computeValueCCT(self, hueOrBrightness = -1):
            global CCTSlider
            CCTSlider = hueOrBrightness # set the global CCT "current slider" to the slider you just... slid

            if CCTSlider == 1: # we dragged the color temperature slider
                self.TFV_CCT_Hue.setText(str(self.Slider_CCT_Hue.value()) + "00K")
            else: # we dragged the brightness slider
                self.TFV_CCT_Bright.setText(str(self.Slider_CCT_Bright.value()) + "%")

            calculateByteString(colorMode="CCT",\
                                temp=str(int(self.Slider_CCT_Hue.value())),\
                                brightness=str(int(self.Slider_CCT_Bright.value())))

            self.statusBar.showMessage("Current value (CCT Mode): " + updateStatus())
            self.startSend()

        # COMPUTE A BYTESTRING FOR THE HSI SECTION
        def computeValueHSI(self, slidSlider = -1):
            calculateByteString(colorMode="HSI",\
                                HSI_H=str(int(self.Slider_HSI_1_H.value())),\
                                HSI_S=str(int(self.Slider_HSI_2_S.value())),\
                                HSI_I=str(int(self.Slider_HSI_3_L.value())))

            if slidSlider == 1: # we dragged the hue slider
                self.TFV_HSI_1_H.setText(str(int(self.Slider_HSI_1_H.value())) + "º")
                self.HSI_Sat_Gradient_BG.setStops(self.getHSISatStops(self.Slider_HSI_1_H.value()))
            elif slidSlider == 2: # we dragged the saturation slider
                self.TFV_HSI_2_S.setText(str(int(self.Slider_HSI_2_S.value())) + "%")
            elif slidSlider == 3: # we dragged the intensity slider
                self.TFV_HSI_3_L.setText(str(int(self.Slider_HSI_3_L.value())) + "%")
            
            self.statusBar.showMessage("Current value (HSI Mode): " + updateStatus())
            self.startSend()

        # COMPUTE A BYTESTRING FOR THE ANIM SECTION
        def computeValueANM(self, buttonPressed):
            global lastAnimButtonPressed

            if buttonPressed == 0:
                buttonPressed = lastAnimButtonPressed
                self.TFV_ANM_Brightness.setText(str(int(self.Slider_ANM_Brightness.value())) + "%")
            else:
                # Map button IDs to button widgets
                _sceneButtons = {
                    1: self.Button_1_police_A, 2: self.Button_1_police_B, 3: self.Button_1_police_C,
                    4: self.Button_2_party_A, 5: self.Button_2_party_B, 6: self.Button_2_party_C,
                    7: self.Button_3_lightning_A, 8: self.Button_3_lightning_B, 9: self.Button_3_lightning_C
                }

                # Deactivate old button
                if lastAnimButtonPressed in _sceneButtons:
                    btn = _sceneButtons[lastAnimButtonPressed]
                    btn.setProperty("activeScene", False)
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)

                # Activate new button
                if buttonPressed in _sceneButtons:
                    btn = _sceneButtons[buttonPressed]
                    btn.setProperty("activeScene", True)
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)

                lastAnimButtonPressed = buttonPressed

            calculateByteString(colorMode="ANM",\
                                brightness=str(int(self.Slider_ANM_Brightness.value())),\
                                animation=str(buttonPressed))

            self.statusBar.showMessage("Current value (ANM Mode): " + updateStatus())
            self.startSend()

        def turnLightOn(self):
            global threadAction
            setPowerBytestring("ON")
            self.statusBar.showMessage("Turning light on")
            # Power commands always send immediately, even with live preview off
            if animationRunning:
                stopAnimation()
                self.animPlayButton.setEnabled(True)
                self.animStopButton.setEnabled(False)
                self.animStatusLabel.setText("Stopped")
            if threadAction == "":
                threadAction = "send"

        def turnLightOff(self):
            global threadAction
            setPowerBytestring("OFF")
            self.statusBar.showMessage("Turning light off")
            # Power commands always send immediately, even with live preview off
            if animationRunning:
                stopAnimation()
                self.animPlayButton.setEnabled(True)
                self.animStopButton.setEnabled(False)
                self.animStatusLabel.setText("Stopped")
            if threadAction == "":
                threadAction = "send"

        # ==============================================================
        # FUNCTIONS TO RETURN / MODIFY VALUES RUNNING IN THE GUI
        # ==============================================================

        # RETURN THE ROW INDEXES THAT ARE CURRENTLY HIGHLIGHTED IN THE TABLE VIEW
        def selectedLights(self):
            selectionList = []

            if threadAction != "quit":
                currentSelection = self.lightTable.selectionModel().selectedRows()

                for a in range(len(currentSelection)):
                    selectionList.append(currentSelection[a].row()) # add the row index of the nth selected light to the selectionList array

            return selectionList # return the row IDs that are currently selected, or an empty array ([]) otherwise

        # UPDATE THE TABLE WITH THE CURRENT INFORMATION FROM availableLights
        def updateLights(self, updateTaskbar = True, applyPreferredOrder = True):
            # Reorder availableLights so preferred-ID lights come first in ID order
            # (skip this when the user is manually sorting the table by column header)
            if applyPreferredOrder:
                reorderByPreferredID()

            self.clearTheTable()

            if updateTaskbar == True: # if we're scanning for lights, then update the taskbar - if we're just sorting, then don't
                if len(availableLights) != 0: # if we found lights on the last scan
                    if self.scanCommandButton.text() == "Scan":
                        self.scanCommandButton.setText("Re-scan") # change the "Scan" button to "Re-scan"

                    if len(availableLights) == 1: # we found 1 light
                        self.statusBar.showMessage("We located 1 Neewer light on the last search")
                    elif len(availableLights) > 1: # we found more than 1 light
                        self.statusBar.showMessage("We located " + str(len(availableLights)) + " Neewer lights on the last search")
                else: # if we didn't find any (additional) lights on the last scan
                    self.statusBar.showMessage("We didn't locate any Neewer lights on the last search")

            for a in range(len(availableLights)):
                _rssi_str = _get_light_rssi(availableLights[a])
                if availableLights[a][1] == "": # the light does not currently have a Bleak object connected to it
                    if availableLights[a][2] != "": # the light has a custom name, so add the custom name to the light
                        self.setTheTable([availableLights[a][2] + " (" + availableLights[a][0].name + ")" + "\n  [ʀssɪ: " + _rssi_str + " dBm]", availableLights[a][0].address, "Waiting", "Waiting to connect..."])
                    else: # the light does not have a custom name, so just use the model # of the light
                        self.setTheTable([availableLights[a][0].name + "\n  [ʀssɪ: " + _rssi_str + " dBm]", availableLights[a][0].address, "Waiting", "Waiting to connect..."])
                else: # the light does have a Bleak object connected to it
                    if availableLights[a][2] != "": # the light has a custom name, so add the custom name to the light
                        if availableLights[a][1].is_connected: # we have a connection to the light
                            self.setTheTable([availableLights[a][2] + " (" + availableLights[a][0].name + ")" + "\n  [ʀssɪ: " + _rssi_str + " dBm]", availableLights[a][0].address, "LINKED", "Waiting to send..."])
                        else: # we're still trying to connect, or haven't started trying yet
                            self.setTheTable([availableLights[a][2] + " (" + availableLights[a][0].name + ")" + "\n  [ʀssɪ: " + _rssi_str + " dBm]", availableLights[a][0].address, "Waiting", "Waiting to connect..."])
                    else: # the light does not have a custom name, so just use the model # of the light
                        if availableLights[a][1].is_connected:
                            self.setTheTable([availableLights[a][0].name + "\n  [ʀssɪ: " + _rssi_str + " dBm]", availableLights[a][0].address, "LINKED", "Waiting to send..."])
                        else:
                            self.setTheTable([availableLights[a][0].name + "\n  [ʀssɪ: " + _rssi_str + " dBm]", availableLights[a][0].address, "Waiting", "Waiting to connect..."])

            # Update vertical header labels to show effective IDs (preferred ID if set, else row number)
            headerLabels = []
            for a in range(len(availableLights)):
                prefID = availableLights[a][8] if len(availableLights[a]) > 8 else 0
                if prefID > 0:
                    headerLabels.append(str(prefID))
                else:
                    headerLabels.append(str(a + 1))
            self.lightTable.setVerticalHeaderLabels(headerLabels)

        # === THEME TOGGLE ===
        def toggleTheme(self):
            self._isDarkTheme = not self._isDarkTheme
            qss = getThemeQSS(self._isDarkTheme)
            QApplication.instance().setStyleSheet(qss)
            self.themeToggleBtn.setText("\u263E" if self._isDarkTheme else "\u2600")
            self.themeToggleBtn.setToolTip("Switch to light theme" if self._isDarkTheme else "Switch to dark theme")

        # === HTTP SERVER TOGGLE ===
        def toggleHTTPServer(self):
            global httpServerInstance, httpServerThread, httpServerRunning

            if httpServerRunning:
                # Stop the server
                try:
                    printDebugString("Stopping the HTTP server...")
                    httpServerInstance.shutdown()  # unblocks serve_forever() in the thread
                    httpServerThread.join(timeout=5)
                    httpServerInstance.server_close()
                    printDebugString("HTTP server stopped")
                except Exception as e:
                    printDebugString("Error stopping HTTP server: " + str(e))
                httpServerInstance = None
                httpServerThread = None
                httpServerRunning = False
                self.httpToggleBtn.setText("HTTP: OFF")
                self.httpToggleBtn.setProperty("httpActive", False)
                self.httpToggleBtn.style().unpolish(self.httpToggleBtn)
                self.httpToggleBtn.style().polish(self.httpToggleBtn)
                self.statusBar.showMessage("HTTP server stopped")
            else:
                # Start the server
                try:
                    httpServerInstance = ThreadingHTTPServer(("", 8080), NLPythonServer)
                    httpServerThread = threading.Thread(target=httpServerInstance.serve_forever, name="httpServerThread", daemon=True)
                    httpServerThread.start()
                    httpServerRunning = True
                    self.httpToggleBtn.setText("HTTP: ON")
                    self.httpToggleBtn.setProperty("httpActive", True)
                    self.httpToggleBtn.style().unpolish(self.httpToggleBtn)
                    self.httpToggleBtn.style().polish(self.httpToggleBtn)
                    printDebugString("HTTP server started on port 8080")
                    self.statusBar.showMessage("HTTP server running on port 8080")
                except OSError as e:
                    printDebugString("Could not start HTTP server: " + str(e))
                    self.statusBar.showMessage("HTTP server failed: " + str(e))
                    httpServerInstance = None
                    httpServerThread = None

        # === SYSTEM TRAY ===
        def setupSystemTray(self):
            if QSystemTrayIcon is None or not QSystemTrayIcon.isSystemTrayAvailable():
                self._trayIcon = None
                return

            self._trayIcon = QSystemTrayIcon(self)

            # Try to use the app icon, fall back to a generic one
            iconPath = _resource_path("com.github.poizenjam.NeewerLux.png")
            if not os.path.exists(iconPath):
                iconPath = _resource_path("com.github.poizenjam.NeewerLux.ico")
            if os.path.exists(iconPath):
                self._trayIcon.setIcon(QIcon(iconPath))
            else:
                self._trayIcon.setIcon(self.windowIcon())

            self._trayIcon.setToolTip("NeewerLux 1.0.0")

            trayMenu = QMenu()
            showAction = trayMenu.addAction("Show / Hide")
            showAction.triggered.connect(self._trayToggleVisibility)
            trayMenu.addSeparator()
            httpAction = trayMenu.addAction("Toggle HTTP Server")
            httpAction.triggered.connect(self.toggleHTTPServer)
            self._consoleAction = None
            self._consoleVisible = not _hasConsole  # False if no console (pythonw)
            if _hasConsole:
                consoleAction = trayMenu.addAction("Hide Console")
                consoleAction.triggered.connect(self._trayToggleConsole)
                self._consoleAction = consoleAction
                self._consoleVisible = True
            trayMenu.addSeparator()
            quitAction = trayMenu.addAction("Quit")
            quitAction.triggered.connect(self._trayQuit)

            self._trayIcon.setContextMenu(trayMenu)
            self._trayIcon.activated.connect(self._trayActivated)
            self._trayIcon.show()

        def saveWindowGeometry(self):
            """Save window position, size, splitter state, and animation settings to a JSON file."""
            try:
                geo = {
                    "x": self.x(), "y": self.y(),
                    "width": self.width(), "height": self.height(),
                    "splitter": self.mainSplitter.sizes(),
                    "animSpeed": self.animSpeedCombo.currentText(),
                    "animRate": self.animRateSpin.value(),
                    "animBri": self.animBriSpin.value(),
                    "animLoop": self.animLoopCheck.isChecked(),
                    "animLoopCount": self.animLoopCountSpin.value(),
                    "animParallel": self.animParallelCheck.isChecked(),
                    "animRevert": self.animRevertCheck.isChecked()
                }
                # Save current tab index for recall on next launch
                geo["lastTab"] = self.ColorModeTabWidget.currentIndex()
                createLightPrefsFolder()
                with open(geometryPrefsFile, "w", encoding="utf-8") as f:
                    json.dump(geo, f)
            except Exception:
                pass

        def restoreWindowGeometry(self):
            """Restore window position, size, and splitter state from JSON file."""
            try:
                if os.path.exists(geometryPrefsFile):
                    with open(geometryPrefsFile, "r", encoding="utf-8") as f:
                        geo = json.load(f)
                    x, y = geo["x"], geo["y"]
                    w, h = geo["width"], geo["height"]

                    # Ensure the window is at least partially visible on a connected screen
                    screen = QApplication.instance().primaryScreen()
                    if screen:
                        avail = screen.availableGeometry()
                        # If saved position is completely off-screen, reset to center
                        if x + w < 0 or y + h < 0 or x > avail.width() or y > avail.height():
                            x = max(0, (avail.width() - w) // 2)
                            y = max(0, (avail.height() - h) // 2)

                    self.move(x, y)
                    self.resize(w, h)
                    if "splitter" in geo:
                        savedSizes = geo["splitter"]
                        # Only apply if section count matches (handles upgrades from 2→3 sections)
                        if len(savedSizes) == self.mainSplitter.count():
                            self.mainSplitter.setSizes(savedSizes)
                    # Restore animation tab settings
                    if "animSpeed" in geo:
                        val = geo["animSpeed"]
                        if isinstance(val, int):
                            self.animSpeedCombo.setCurrentIndex(val)
                        else:
                            idx = self.animSpeedCombo.findText(str(val))
                            if idx >= 0:
                                self.animSpeedCombo.setCurrentIndex(idx)
                            else:
                                self.animSpeedCombo.setEditText(str(val))
                    if "animRate" in geo:
                        self.animRateSpin.setValue(geo["animRate"])
                    if "animBri" in geo:
                        self.animBriSpin.setValue(geo["animBri"])
                    if "animLoop" in geo:
                        self.animLoopCheck.setChecked(geo["animLoop"])
                    if "animLoopCount" in geo:
                        self.animLoopCountSpin.setValue(geo["animLoopCount"])
                    if "animParallel" in geo:
                        self.animParallelCheck.setChecked(geo["animParallel"])
                    if "animRevert" in geo:
                        self.animRevertCheck.setChecked(geo["animRevert"])
                    # Restore last active tab (default to Info tab on first launch)
                    if "lastTab" in geo:
                        tabIdx = geo["lastTab"]
                        if 0 <= tabIdx < self.ColorModeTabWidget.count():
                            self.ColorModeTabWidget.setCurrentIndex(tabIdx)
            except Exception:
                pass

        def _trayToggleVisibility(self):
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.activateWindow()
                self.raise_()

        def _trayToggleConsole(self):
            if self._consoleVisible:
                hideConsoleWindow()
                self._consoleVisible = False
                self._consoleAction.setText("Show Console")
            else:
                showConsoleWindow()
                self._consoleVisible = True
                self._consoleAction.setText("Hide Console")

        def _trayActivated(self, reason):
            """Double-click tray icon to toggle visibility."""
            if reason == QSystemTrayIcon.DoubleClick:
                self._trayToggleVisibility()

        def _trayQuit(self):
            """Quit for real — don't minimize to tray."""
            self._forceQuit = True
            if self._trayIcon:
                self._trayIcon.hide()
            self.close()

        def _savePresetsQuick(self):
            """Save custom presets and names to disk without shutting down.
            Called when minimizing to tray so presets persist even if the process is killed later."""
            if not rememberPresetsOnExit:
                return
            try:
                customPresetsToWrite = ["numOfPresets=" + str(numOfPresets)]
                for i in range(numOfPresets):
                    if customLightPresets[i] != defaultLightPresets[i]:
                        customPresetsToWrite.append(customPresetToString(i))
                for idx, name in presetNames.items():
                    if name:
                        customPresetsToWrite.append("presetName" + str(idx) + "=" + name)

                hasNonDefaultContent = len(customPresetsToWrite) > 1 or numOfPresets != 8
                if hasNonDefaultContent:
                    createLightPrefsFolder()
                    with open(customLightPresetsFile, mode="w", encoding="utf-8") as f:
                        f.write("\n".join(customPresetsToWrite))
                    printDebugString("Quick-saved presets to " + customLightPresetsFile)
                elif os.path.exists(customLightPresetsFile):
                    os.remove(customLightPresetsFile)
            except Exception as e:
                printDebugString("Error quick-saving presets: " + str(e))

        # THE FINAL FUNCTION TO UNLINK ALL LIGHTS WHEN QUITTING THE PROGRAM
        def closeEvent(self, event):
            global threadAction, httpServerInstance, httpServerRunning

            # Always save window geometry on close (whether tray-minimizing or quitting)
            self.saveWindowGeometry()

            # If system tray is available, preference is on, and this isn't a force-quit, minimize to tray instead
            if minimizeToTrayOnClose and hasattr(self, '_trayIcon') and self._trayIcon and not getattr(self, '_forceQuit', False):
                # Save presets now so they persist even if the process is later killed
                self._savePresetsQuick()
                event.ignore()
                self.hide()
                self._trayIcon.showMessage("NeewerLux", "Minimized to system tray. Double-click to restore.",
                                           QSystemTrayIcon.Information, 2000)
                return

            # STOP HTTP SERVER IF RUNNING
            if hasattr(self, '_trayIcon') and self._trayIcon:
                self._trayIcon.hide()

            if httpServerRunning and httpServerInstance:
                try:
                    httpServerInstance.shutdown()
                    httpServerInstance.server_close()
                except Exception:
                    pass
                httpServerRunning = False

            # STOP ANY RUNNING ANIMATION BEFORE SHUTTING DOWN
            if animationRunning:
                stopAnimation()

            # WAIT UNTIL THE BACKGROUND THREAD SETS THE threadAction FLAG TO finished SO WE CAN UNLINK THE LIGHTS
            _quit_deadline = time.time() + 10  # give the thread 10 seconds max
            while threadAction != "finished": # wait until the background thread has a chance to terminate
                if time.time() > _quit_deadline:
                    printDebugString("Background thread did not finish in time — forcing exit")
                    break
                printDebugString("Waiting for the background thread to terminate...")
                threadAction = "quit" # make sure to tell the thread to quit again (if it missed it the first time)
                time.sleep(2)

            if rememberPresetsOnExit == True:
                printDebugString("You asked NeewerLux to save the custom parameters on exit, so we will do that now...")
                customPresetsToWrite = [] # the list of custom presets to write to file

                # SAVE THE TOTAL NUMBER OF PRESETS SO WE KNOW HOW MANY TO LOAD NEXT TIME
                customPresetsToWrite.append("numOfPresets=" + str(numOfPresets))

                # CHECK EVERY SINGLE CUSTOM PRESET AGAINST THE "DEFAULT" LIST, AND IF IT'S DIFFERENT, THEN LOG THAT ONE
                for i in range(numOfPresets):
                    if customLightPresets[i] != defaultLightPresets[i]:
                        customPresetsToWrite.append(customPresetToString(i))

                # SAVE ANY CUSTOM PRESET NAMES
                for idx, name in presetNames.items():
                    if name:
                        customPresetsToWrite.append("presetName" + str(idx) + "=" + name)

                # Determine if there's anything non-default to save
                hasNonDefaultContent = len(customPresetsToWrite) > 1 or numOfPresets != 8

                if hasNonDefaultContent: # if there are altered presets, names, or a non-default preset count
                    createLightPrefsFolder() # create the light_prefs folder if it doesn't exist

                    # WRITE THE PREFERENCES FILE
                    with open(customLightPresetsFile, mode="w", encoding="utf-8") as prefsFileToWrite:
                        prefsFileToWrite.write("\n".join(customPresetsToWrite))

                    printDebugString("Exported custom presets to " + customLightPresetsFile)
                else:
                    if os.path.exists(customLightPresetsFile):
                        printDebugString("There were no changed custom presets, so we're deleting the custom presets file!")
                        os.remove(customLightPresetsFile) # if there are no presets to save, then delete the custom presets file
                      
            # Keep in mind, this is broken into 2 separate "for" loops, so we save all the light params FIRST, then try to unlink from them
            if rememberLightsOnExit == True:
                printDebugString("You asked NeewerLux to save the last used light parameters on exit, so we will do that now...")

                for a in range(len(availableLights)):
                    printDebugString("Saving last used parameters for light #" + str(a + 1) + " (" + str(a + 1) + " of " + str(len(availableLights)) + ")")
                    saveLightPrefs(a)

            # THE THREAD HAS TERMINATED, NOW CONTINUE...
            printDebugString("We will now attempt to unlink from the lights...")
            self.statusBar.showMessage("Quitting program - unlinking from lights...")
            QApplication.processEvents() # force the status bar to update

            asyncioEventLoop.run_until_complete(parallelAction("disconnect", [-1])) # disconnect from all lights in parallel

            printDebugString("Closing the program NOW")
            event.accept()

            # Force-kill the process so the CMD window closes too
            # (background threads like HTTP server would keep it alive otherwise)
            import os as _os
            _os._exit(0)

        def saveCustomPresetDialog(self, numOfPreset):
            if (QApplication.keyboardModifiers() & Qt.AltModifier) == Qt.AltModifier: # if you have the ALT key held down
                customLightPresets[numOfPreset] = defaultLightPresets[numOfPreset] # then restore the default for this preset
                presetNames.pop(numOfPreset, None) # also clear the custom name
                # Change the button display back to "PRESET GLOBAL"
                if numOfPreset < len(self.presetButtons):
                    self.presetButtons[numOfPreset].markCustom(numOfPreset, -1)
            else:
                if len(availableLights) == 0: # if we don't have lights, then we can't save a preset!
                    errDlg = QMessageBox(self)
                    errDlg.setWindowTitle("Can't Save Preset!")
                    errDlg.setText("You can't save a custom preset at the moment because you don't have any lights set up yet.  To save a custom preset, connect a light to NeewerLux first.")
                    errDlg.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
                    errDlg.setIcon(QMessageBox.Warning)
                    pyside_exec(errDlg)
                else: # we have lights, we can do it!
                    selectedLights = self.selectedLights() # get the currently selected lights

                    saveDlg = QMessageBox(self)
                    saveDlg.setWindowTitle("Save a Custom Preset")
                    saveDlg.setTextFormat(Qt.TextFormat.RichText)
                    saveDlg.setText("Would you like to save a <em>Global</em> or <em>Snapshot</em> preset for preset " + str(numOfPreset + 1) + "?" + "<hr>"
                                    "A <em>Global Preset</em> saves only the currently set global parameters (mode, hue, color temperature, brightness, etc.) and applies that global preset to all the lights that are currently selected.<br><br>"
                                    "A <em>Snapshot Preset</em> saves the currently set parameters for each light individually, allowing you to recall more complex lighting setups.  You can also either set a <em>snapshot preset</em> for a series of selected lights (you have to select 1 or more lights for this option), or all the currently available lights.  If you save a <em>snapshot preset</em> of a series of selected lights, it will only apply the settings for those specific lights.")
                    saveDlg.addButton(" Global Preset ", QMessageBox.ButtonRole.YesRole)
                    saveDlg.addButton(" Snapshot Preset - All Lights ", QMessageBox.ButtonRole.YesRole)

                    selectedLightsQuestion = 0

                    if selectedLights != []:
                        saveDlg.addButton(" Snapshot Preset - Selected Lights ", QMessageBox.ButtonRole.YesRole)
                        selectedLightsQuestion = 1
                    
                    saveDlg.addButton(" Cancel ", QMessageBox.ButtonRole.RejectRole)           
                    saveDlg.setIcon(QMessageBox.Question)

                    clickedButton = pyside_exec(saveDlg)
                    
                    if clickedButton == 0: # save a "Global" preset
                        saveCustomPreset("global", numOfPreset)
                    elif clickedButton == 1: # save a "Snapshot" preset with all lights
                        saveCustomPreset("snapshot", numOfPreset)
                    elif clickedButton == 2: # save a "Snapshot" preset with only the selected lights
                        saveCustomPreset("snapshot", numOfPreset, selectedLights)
                        
                    if clickedButton != (2 + selectedLightsQuestion): # if we didn't cancel out, then mark that button as being "custom"
                        # Prompt for a name
                        currentName = presetNames.get(numOfPreset, "")
                        newName, accepted = QInputDialog.getText(self, "Preset Name",
                            "Enter a name for preset " + str(numOfPreset + 1) + " (leave blank for default):",
                            text=currentName)
                        if accepted:
                            if newName.strip():
                                presetNames[numOfPreset] = newName.strip()
                            else:
                                presetNames.pop(numOfPreset, None)

                        if numOfPreset < len(self.presetButtons):
                            name = presetNames.get(numOfPreset, "")
                            self.presetButtons[numOfPreset].markCustom(numOfPreset, clickedButton, presetName=name)

                        # Persist presets to disk immediately so HTTP/web UI can use them
                        self._savePresetsQuick()

        def highlightLightsForSnapshotPreset(self, numOfPreset, exited = False):
            global lastSelection

            if exited == False: # if we're entering a snapshot preset, then highlight the affected lights in green
                toolTip = customPresetInfoBuilder(numOfPreset)

                # LOAD A NEWLY GENERATED TOOLTIP FOR EVERY HOVER
                if numOfPreset < len(self.presetButtons):
                    self.presetButtons[numOfPreset].setToolTip(toolTip)

                lightsToHighlight = self.checkForSnapshotPreset(numOfPreset)
                
                if lightsToHighlight != []:
                    lastSelection = self.selectedLights()
                    # Block signals to prevent clearSelection from triggering selectionChanged → tab switch
                    self.lightTable.blockSignals(True)
                    self.lightTable.clearSelection()
                    self.lightTable.blockSignals(False)

                    for a in range(len(lightsToHighlight)):
                        for b in range(4):
                            self.lightTable.item(lightsToHighlight[a], b).setBackground(QColor(76, 175, 80, 80))
            else: # if we're exiting a snapshot preset, then reset the color of the affected lights
                lightsToHighlight = self.checkForSnapshotPreset(numOfPreset)
                
                if lightsToHighlight != []:
                    self.lightTable.blockSignals(True)
                    self.selectRows(lastSelection)
                    self.lightTable.blockSignals(False)

                    for a in range(len(lightsToHighlight)):
                        for b in range(4):
                            self.lightTable.item(lightsToHighlight[a], b).setData(Qt.BackgroundRole, None)

        def checkForSnapshotPreset(self, numOfPreset):
            if customLightPresets[numOfPreset][0][0] != -1: # if the value is not -1, then we most likely have a snapshot preset
                lightsToHighlight = []
                
                for a in range(len(customLightPresets[numOfPreset])): # check each entry in the preset for matching lights
                    currentLight = returnLightIndexesFromMacAddress(customLightPresets[numOfPreset][a][0])

                    if currentLight != []: # if we have a match, add it to the list of lights to highlight
                        lightsToHighlight.append(currentLight[0])

                return lightsToHighlight
            else:
                return [] # if we don't have a snapshot preset, then just return an empty list (no lights directly affected)

        # SET UP THE GUI BASED ON COMMAND LINE ARGUMENTS
        def setUpGUI(self, **modeArgs):
            if modeArgs["colorMode"] == "CCT":
                self.ColorModeTabWidget.setCurrentIndex(0)

                self.Slider_CCT_Hue.setValue(modeArgs["temp"])
                self.Slider_CCT_Bright.setValue(modeArgs["brightness"])

                self.computeValueCCT()
            elif modeArgs["colorMode"] == "HSI":
                self.ColorModeTabWidget.setCurrentIndex(1)

                self.Slider_HSI_1_H.setValue(modeArgs["hue"])
                self.Slider_HSI_2_S.setValue(modeArgs["sat"])
                self.Slider_HSI_3_L.setValue(modeArgs["brightness"])

                self.computeValueHSI()
            elif modeArgs["colorMode"] == "ANM":
                self.ColorModeTabWidget.setCurrentIndex(2)

                self.Slider_ANM_Brightness.setValue(modeArgs["brightness"])
                self.computeValueANM(modeArgs["scene"])
except NameError:
    pass # could not load the GUI, but we have already logged an error message

def setUpAsyncio():
    global asyncioEventLoop

    try:
        asyncioEventLoop = asyncio.get_running_loop()
    except RuntimeError:
        asyncioEventLoop = asyncio.new_event_loop()

    asyncio.set_event_loop(asyncioEventLoop)

# CALCULATE THE RGB VALUE OF COLOR TEMPERATURE
def convert_K_to_RGB(Ktemp):
    # Based on this script: https://gist.github.com/petrklus/b1f427accdf7438606a6
    # from @petrklus on GitHub (his source was from http://www.tannerhelland.com/4435/convert-temperature-rgb-algorithm-code/)

    tmp_internal = Ktemp / 100.0
    
    # red 
    if tmp_internal <= 66:
        red = 255
    else:
        tmp_red = 329.698727446 * math.pow(tmp_internal - 60, -0.1332047592)

        if tmp_red < 0:
            red = 0
        elif tmp_red > 255:
            red = 255
        else:
            red = tmp_red
    
    # green
    if tmp_internal <= 66:
        tmp_green = 99.4708025861 * math.log(tmp_internal) - 161.1195681661

        if tmp_green < 0:
            green = 0
        elif tmp_green > 255:
            green = 255
        else:
            green = tmp_green
    else:
        tmp_green = 288.1221695283 * math.pow(tmp_internal - 60, -0.0755148492)

        if tmp_green < 0:
            green = 0
        elif tmp_green > 255:
            green = 255
        else:
            green = tmp_green
    
    # blue
    if tmp_internal >= 66:
        blue = 255
    elif tmp_internal <= 19:
        blue = 0
    else:
        tmp_blue = 138.5177312231 * math.log(tmp_internal - 10) - 305.0447927307
        if tmp_blue < 0:
            blue = 0
        elif tmp_blue > 255:
            blue = 255
        else:
            blue = tmp_blue
    
    return int(red), int(green), int(blue) # return the integer value for each part of the RGB values for this step

def convert_HSI_to_RGB(h, s = 1, v = 1):
    # Taken from this StackOverflow page, which is an articulation of the colorsys code to
    # convert HSV values (not HSI, but close, as I'm keeping S and V locked to 1) to RGB:
    # https://stackoverflow.com/posts/26856771/revisions

    if s == 0.0: v*=255; return (v, v, v)
    i = int(h*6.) # XXX assume int() truncates!
    f = (h*6.)-i; p,q,t = int(255*(v*(1.-s))), int(255*(v*(1.-s*f))), int(255*(v*(1.-s*(1.-f)))); v*=255; i%=6
    if i == 0: return (v, t, p)
    if i == 1: return (q, v, p)
    if i == 2: return (p, v, t)
    if i == 3: return (p, q, v)
    if i == 4: return (t, p, v)
    if i == 5: return (v, p, q)

def saveLightPrefs(lightID, deleteFile = False): # save a sidecar file with the preferences for a specific light
    createLightPrefsFolder() # create the light_prefs folder if it doesn't exist

    # GET THE CUSTOM FILENAME FOR THIS FILE, NOTED FROM THE MAC ADDRESS OF THE CURRENT LIGHT
    exportFileName = availableLights[lightID][0].address.split(":") # take the colons out of the MAC address
    exportFileName = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep + "light_prefs" + os.sep + "".join(exportFileName)

    if deleteFile == True:
        if os.path.exists(exportFileName):
            os.remove(exportFileName) # delete the old preferences file (if it exists)
    else:
        customName = availableLights[lightID][2] # the custom name for this light
        defaultSettings = getLightSpecs(availableLights[lightID][0].name)

        if defaultSettings[1] != availableLights[lightID][4]:
            customTempRange = str(availableLights[lightID][4][0]) + "," + str(availableLights[lightID][4][1]) # the color temperature range available
        else:
            customTempRange = "" # if the range is the same as the default range, then just leave this entry blank

        if defaultSettings[2] != availableLights[lightID][5]:
            onlyCCTMode = str(availableLights[lightID][5]) # whether or not the light can only use CCT mode
        else:
            onlyCCTMode = "" # if the CCT mode enable is the same as the default value, then just leave this entry blank

        exportString = customName + "|" + customTempRange + "|" + onlyCCTMode # the exported string, minus the light last set parameters

        if rememberLightsOnExit == True: # if we're supposed to remember the last settings, then add that to the Prefs file
            if len(availableLights[lightID][3]) > 0: # if we actually have a value stored for this light
                lastSettingsString = ",".join(map(str, availableLights[lightID][3])) # combine all the elements of the last set params
                exportString += "|" + lastSettingsString # add it to the exported string
            else: # if we don't have a value stored for this light (nothing has changed yet)
                exportString += "|" + "120,135,2,100,56,157" # then just give the default (CCT, 5600K, 100%) params
        else:
            exportString += "|" # empty lastSettings field so preferredID stays in correct position

        # Preferred ID (5th pipe field) — 0 means auto/no preference
        preferredID = availableLights[lightID][8] if len(availableLights[lightID]) > 8 else 0
        exportString += "|" + str(preferredID)

        # WRITE THE PREFERENCES FILE
        with open(exportFileName, mode="w", encoding="utf-8") as prefsFileToWrite:
            prefsFileToWrite.write(exportString)

        if customName != "":
            printDebugString("Exported preferences for " + customName + " [" + availableLights[lightID][0].name + "] to " + exportFileName)
        else:
            printDebugString("Exported preferences for [" + availableLights[lightID][0].name + "] to " + exportFileName)

# WORKING WITH CUSTOM PRESETS
def customPresetInfoBuilder(numOfPreset, formatForHTTP = False):
    toolTipBuilder = [] # constructor for the tooltip
    numOfLights = len(customLightPresets[numOfPreset]) # the number of lights in this specific preset

    # Show the custom name if one is set
    name = presetNames.get(numOfPreset, "")
    if name:
        if formatForHTTP == False:
            toolTipBuilder.append("\"" + name + "\"")
        else:
            toolTipBuilder.append("<STRONG>\"" + name + "\"</STRONG>")

    if numOfLights == 1 and customLightPresets[numOfPreset][0][0] == -1: # we're looking at a global preset
        if formatForHTTP == False:
            toolTipBuilder.append("[GLOBAL PRESET]")
        else:
            toolTipBuilder.append("<STRONG>[GLOBAL PRESET]</STRONG>")
    else: # we're looking at a snapshot preset
        if formatForHTTP == False:
            toolTipBuilder.append("[SNAPSHOT PRESET]")
        else:
            toolTipBuilder.append("<STRONG>[SNAPSHOT PRESET]</STRONG>")

    toolTipBuilder.append("")

    for a in range(numOfLights): # write out a little description of each part of this preset
        if customLightPresets[numOfPreset][a][0] == -1:
            if formatForHTTP == False:
                toolTipBuilder.append(" FOR: ALL SELECTED LIGHTS") # this is a global preset, and it affects all *selected* lights
            else:
                toolTipBuilder.append(" FOR: ALL LIGHTS AVAILABLE") # this is a global preset, and it affects all lights
        else:
            currentLight = returnLightIndexesFromMacAddress(customLightPresets[numOfPreset][a][0]) # find the light in the current list

            if currentLight != []: # if we have a match, add it to the list of lights to highlight
                if availableLights[currentLight[0]][2] != "": # if the custom name is filled in
                    toolTipBuilder.append(" FOR: " + availableLights[currentLight[0]][2] + " [" + availableLights[currentLight[0]][0].name + "]")
                else:
                    toolTipBuilder.append(" FOR: " + availableLights[currentLight[0]][0].name)
            else:
                toolTipBuilder.append("FOR: ---LIGHT NOT AVAILABLE AT THE MOMENT---") # if the light is not found (yet), display that

            toolTipBuilder.append(" " + customLightPresets[numOfPreset][a][0] + "") # this is a snapshot preset, and this specific preset controls this light
                    
        if customLightPresets[numOfPreset][a][1][0] == 5:
            if formatForHTTP == False:
                toolTipBuilder.append(" > MODE: CCT / TEMP: " + str(customLightPresets[numOfPreset][a][1][2]) + "00K / BRIGHTNESS: " + str(customLightPresets[numOfPreset][a][1][1]) + "% < ")
            else:
                toolTipBuilder.append(" &gt; MODE: CCT / TEMP: " + str(customLightPresets[numOfPreset][a][1][2]) + "00K / BRIGHTNESS: " + str(customLightPresets[numOfPreset][a][1][1]) + "% &lt; ")
        elif customLightPresets[numOfPreset][a][1][0] == 4:
            if formatForHTTP == False:
                toolTipBuilder.append(" > MODE: HSI / H: " + str(customLightPresets[numOfPreset][a][1][2]) + "º / S: " + str(customLightPresets[numOfPreset][a][1][3]) + "% / I: " + str(customLightPresets[numOfPreset][a][1][1]) + "% < ")
            else: # if we're sending this string back for the HTTP server, then replace the degree with the HTML version
                toolTipBuilder.append(" &gt; MODE: HSI / H: " + str(customLightPresets[numOfPreset][a][1][2]) + "&#176; / S: " + str(customLightPresets[numOfPreset][a][1][3]) + "% / I: " + str(customLightPresets[numOfPreset][a][1][1]) + "% &lt; ")
        elif customLightPresets[numOfPreset][a][1][0] == 6:
            if formatForHTTP == False:
                toolTipBuilder.append(" > MODE: SCENE / ANIMATION: " + str(customLightPresets[numOfPreset][a][1][2]) + " / BRIGHTNESS: " + str(customLightPresets[numOfPreset][a][1][1]) + "% < ")
            else:
                toolTipBuilder.append(" &gt; MODE: SCENE / ANIMATION: " + str(customLightPresets[numOfPreset][a][1][2]) + " / BRIGHTNESS: " + str(customLightPresets[numOfPreset][a][1][1]) + "% &lt; ")
        else: # if we're set to turn the light off, show that here
            if formatForHTTP == False:
                toolTipBuilder.append(" > TURN THIS LIGHT OFF < ")
            else:
                toolTipBuilder.append(" &gt; TURN THIS LIGHT OFF &lt; ")

        if numOfLights > 1 and a < (numOfLights - 1): # if we have any more lights, then separate each one
            if formatForHTTP == False:
                toolTipBuilder.append("----------------------------")
            else:
                toolTipBuilder.append("")
            
    if formatForHTTP == False:
        return "\n".join(toolTipBuilder)
    else:
        return "<BR>".join(toolTipBuilder)

def recallCustomPreset(numOfPreset, updateGUI=True, loop=None):
    global availableLights
    global lastSelection
    global threadAction

    # If an animation is playing, stop it — user is recalling a preset
    if animationRunning:
        stopAnimation()
        try:
            if mainWindow is not None: mainWindow.animPlayButton.setEnabled(True)
            if mainWindow is not None: mainWindow.animStopButton.setEnabled(False)
            if mainWindow is not None: mainWindow.animStatusLabel.setText("Stopped")
        except Exception:
            pass

    changedLights = [] # if a snapshot preset exists in this setting, log the lights that are to be changed here

    for a in range(len(customLightPresets[numOfPreset])): # check all the entries stored in this preset
        if customLightPresets[numOfPreset][0][0] == -1: # we're looking at a global preset, so set the light(s) up accordingly
            
            if updateGUI == True: # if we are in the GUI
                if mainWindow.selectedLights() == []: # and no lights are selected in the light selector
                    mainWindow.lightTable.selectAll() # select all of the lights available
                    time.sleep(0.2)
            
            if customLightPresets[numOfPreset][0][1][0] == 5: # the preset is in CCT mode
                p_colorMode = "CCT"
                p_brightness = customLightPresets[numOfPreset][0][1][1]
                p_temp = customLightPresets[numOfPreset][0][1][2]

                if updateGUI == True:
                    if mainWindow is not None: mainWindow.setUpGUI(colorMode=p_colorMode, brightness=p_brightness, temp=p_temp)
                else:
                    computedValue = calculateByteString(True, colorMode=p_colorMode, brightness=p_brightness, temp=p_temp)
            elif customLightPresets[numOfPreset][0][1][0] == 4: # the preset is in HSI mode
                p_colorMode = "HSI"
                # Due to the way the custom presets store information (brightness is always first),
                # this section is broken up into H, S and I portions for readability
                p_hue = customLightPresets[numOfPreset][0][1][2]
                p_sat = customLightPresets[numOfPreset][0][1][3]
                p_int = customLightPresets[numOfPreset][0][1][1]

                if updateGUI == True:
                    if mainWindow is not None: mainWindow.setUpGUI(colorMode=p_colorMode, hue=p_hue, sat=p_sat, brightness=p_int)
                else:
                    computedValue = calculateByteString(True, colorMode=p_colorMode, HSI_H=p_hue, HSI_S=p_sat, HSI_I=p_int)
            elif customLightPresets[numOfPreset][0][1][0] == 6: # the preset is in ANM/SCENE mode
                p_colorMode = "ANM"
                p_brightness = customLightPresets[numOfPreset][0][1][1]
                p_scene = customLightPresets[numOfPreset][0][1][2]

                if updateGUI == True:
                    if mainWindow is not None: mainWindow.setUpGUI(colorMode=p_colorMode, brightness=p_brightness, scene=p_scene)
                else:
                    computedValue = calculateByteString(True, colorMode=p_colorMode, brightness=p_brightness, scene=p_scene)

            if updateGUI == False:
                for b in range(len(availableLights)):
                    changedLights.append(b) # add each light to changedLights
                    availableLights[b][3] = computedValue # set each light's "last" parameter to the computed value above
            else:
                # Presets always send immediately — force a send even if livePreview is off
                if not livePreview:
                    threadAction = "send"

        else: # we're looking at a snapshot preset, so see if any of those lights are available to change
            currentLight = returnLightIndexesFromMacAddress(customLightPresets[numOfPreset][a][0])

            if currentLight != []: # if we have a match
                # always refer to the light it found as currentLight[0]
                if customLightPresets[numOfPreset][a][1][0] == 5 or customLightPresets[numOfPreset][a][1][0] == 8: # the preset is in CCT mode
                    availableLights[currentLight[0]][3] = calculateByteString(True, colorMode="CCT",\
                                                            brightness=customLightPresets[numOfPreset][a][1][1],\
                                                            temp=customLightPresets[numOfPreset][a][1][2])

                    if customLightPresets[numOfPreset][a][1][0] == 8: # if we want to turn the light off, let the send system know this
                        availableLights[currentLight[0]][3][0] = 0
                elif customLightPresets[numOfPreset][a][1][0] == 4 or customLightPresets[numOfPreset][a][1][0] == 7: # the preset is in HSI mode
                    availableLights[currentLight[0]][3] = calculateByteString(True, colorMode="HSI",\
                                                            HSI_I=customLightPresets[numOfPreset][a][1][1],\
                                                            HSI_H=customLightPresets[numOfPreset][a][1][2],\
                                                            HSI_S=customLightPresets[numOfPreset][a][1][3])

                    if customLightPresets[numOfPreset][a][1][0] == 7: # if we want to turn the light off, let the send system know this
                        availableLights[currentLight[0]][3][0] = 0
                elif customLightPresets[numOfPreset][a][1][0] == 6 or customLightPresets[numOfPreset][a][1][0] == 9: # the preset is in ANM/SCENE mode
                    availableLights[currentLight[0]][3] = calculateByteString(True, colorMode="ANM",\
                                                            brightness=customLightPresets[numOfPreset][a][1][1],\
                                                            animation=customLightPresets[numOfPreset][a][1][2])
                    
                    if customLightPresets[numOfPreset][a][1][0] == 9: # if we want to turn the light off, let the send system know this
                        availableLights[currentLight[0]][3][0] = 0
                
                changedLights.append(currentLight[0])

    if changedLights != []:
        if updateGUI == True:
            lastSelection = [] # clear the last selection if you've clicked on a snapshot preset (which, if we're here, you did)

            mainWindow.lightTable.setFocus() # set the focus to the light table, in order to show which rows are selected
            mainWindow.selectRows(changedLights) # select those rows affected by the lights above

        # Always use the threadAction approach — this is safe from both GUI and HTTP threads
        threadAction = "send|" + "|".join(map(str, changedLights))

def saveCustomPreset(presetType, numOfPreset, selectedLights = []):
    global customLightPresets

    if presetType == "global":
        customLightPresets[numOfPreset] = [listBuilder(-1)]
    elif presetType == "snapshot":
        listConstructor = []
        
        if selectedLights == []: # add all the lights to the snapshot preset
            for a in range(len(availableLights)): 
                listConstructor.append(listBuilder(a))
        else: # add only the selected lights to the snapshot preset
            for a in range(len(selectedLights)):
                listConstructor.append(listBuilder(selectedLights[a]))

        customLightPresets[numOfPreset] = listConstructor

def listBuilder(selectedLight):
    paramsListBuilder = [] # the cut-down list of parameters to return to the main preset constructor

    if selectedLight == -1: # then we get the value from sendValue
        lightMACAddress = -1 # this is a global preset
        listToWorkWith = sendValue # we're using the last sent parameter on any light for this
    else: # we're recalling the params for a specific light
        # Use preferred ID or custom name if available (makes presets portable)
        prefID = availableLights[selectedLight][8] if len(availableLights[selectedLight]) > 8 else 0
        customName = availableLights[selectedLight][2]
        if prefID > 0:
            lightMACAddress = str(prefID)  # numeric ID as string
        elif customName:
            lightMACAddress = customName  # alias name
        else:
            lightMACAddress = availableLights[selectedLight][0].address  # MAC fallback
        listToWorkWith = availableLights[selectedLight][3] # we're specificially using the last parameter for the specified light for this

    if listToWorkWith != []: # if we have elements in this list, then sort them out
        if selectedLight == -1:
            # Global preset — assume light is ON (user just set this value)
            paramsListBuilder.append(listToWorkWith[1] - 130)
        elif availableLights[selectedLight][6] == False:
            paramsListBuilder.append(listToWorkWith[1] - 127) # the first value is the mode, but -127 to simplify it (and mark it as being OFF)
        else:
            paramsListBuilder.append(listToWorkWith[1] - 130) # the first value is the mode, but -130 to simplify it (and mark it as being ON)

        if listToWorkWith[1] == 135: # we're in CCT mode
            paramsListBuilder.append(listToWorkWith[3]) # the brightness
            paramsListBuilder.append(listToWorkWith[4]) # the color temperature
        elif listToWorkWith[1] == 134: # we're in HSI mode
            paramsListBuilder.append(listToWorkWith[6]) # the brightness
            paramsListBuilder.append(listToWorkWith[3] + (256 * listToWorkWith[4])) # the hue
            paramsListBuilder.append(listToWorkWith[5]) # the saturation
        elif listToWorkWith[1] == 136: # we're in ANM/SCENE
            paramsListBuilder.append(listToWorkWith[3]) # the brightness
            paramsListBuilder.append(listToWorkWith[4]) # the scene

    return [lightMACAddress, paramsListBuilder]

def customPresetToString(numOfPreset):
    returnedString = "customPreset" + str(numOfPreset) + "=" # the string to return back to the saving mechanism
    numOfLights = len(customLightPresets[numOfPreset]) # how many lights this custom preset holds values for

    for a in range(numOfLights): # get all of the lights stored in this preset (or 1 if it's a global)
        returnedString += str(customLightPresets[numOfPreset][a][0]) # get the MAC address/UUID of the nth light
        returnedString += "|" + "|".join(map(str,customLightPresets[numOfPreset][a][1])) # get a string for the rest of this current array
      
        if numOfLights > 1 and a < (numOfLights - 1): # if there are more lights left, then add a semicolon to differentiate that
            returnedString += ";"

    return returnedString

def stringToCustomPreset(presetString, numOfPreset):   
    if presetString != "|": # if the string is a valid string, then process it
        lightsToWorkWith = presetString.split(";") # split the current string into individual lights
        presetToReturn = [] # a list containing all of the preset information

        for a in range(len(lightsToWorkWith)):
            presetList = lightsToWorkWith[a].split("|") # split the current light list into its individual items
            presetPayload = [] # the actual preset list
            
            for b in range(1, len(presetList)):
                presetPayload.append(int(presetList[b]))

            if presetList[0] == "-1":
                presetToReturn.append([-1, presetPayload]) # if the light ID is -1, keep that value as an integer
            else:
                presetToReturn.append([presetList[0], presetPayload]) # if it isn't, then the MAC address is a string, so keep it that way

        return presetToReturn
    else: # if it isn't, then just return the default parameters for this preset
        return getDefaultPreset(numOfPreset)

def loadCustomPresets():
    global customLightPresets, numOfPresets, defaultLightPresets, presetNames

    # READ THE PREFERENCES FILE INTO A LIST
    with open(customLightPresetsFile, mode="r", encoding="utf-8") as fileToOpen:
        customPresets = fileToOpen.read().split("\n")

    # First pass: check for numOfPresets line and preset names
    for line in customPresets:
        if line.startswith("numOfPresets="):
            try:
                savedCount = int(line.split("=", 1)[1])
                if savedCount > numOfPresets:
                    numOfPresets = savedCount
                    defaultLightPresets = buildDefaultPresets(numOfPresets)
                    # Extend customLightPresets to match
                    while len(customLightPresets) < numOfPresets:
                        customLightPresets.append(getDefaultPreset(len(customLightPresets)))
            except ValueError:
                pass
        elif line.startswith("presetName"):
            # Parse lines like "presetName0=My Cool Preset"
            try:
                keyVal = line.split("=", 1)
                idx = int(keyVal[0].replace("presetName", ""))
                name = keyVal[1].strip() if len(keyVal) > 1 else ""
                if name:
                    presetNames[idx] = name
            except (ValueError, IndexError):
                pass

    # Build list of acceptable customPresetN argument names
    acceptable_arguments = ["customPreset" + str(i) for i in range(numOfPresets)]

    # Filter out non-matching lines (and the numOfPresets/presetName lines)
    filteredPresets = []
    for line in customPresets:
        if line.startswith("numOfPresets=") or line.startswith("presetName"):
            continue
        if any(x in line for x in acceptable_arguments):
            filteredPresets.append("--" + line)

    if not filteredPresets:
        return  # nothing to parse

    # Build the argument parser dynamically
    customPresetParser = argparse.ArgumentParser()
    for i in range(numOfPresets):
        customPresetParser.add_argument("--customPreset" + str(i), default=-1)

    parsedPresets = customPresetParser.parse_args(filteredPresets)

    # Apply parsed presets
    for i in range(numOfPresets):
        val = getattr(parsedPresets, "customPreset" + str(i), -1)
        if val != -1:
            customLightPresets[i] = stringToCustomPreset(val, i)
    
# RETURN THE CORRECT NAME FOR THE IDENTIFIER OF THE LIGHT (FOR DEBUG STRINGS)
def returnMACname():
    if platform.system() == "Darwin":
        return "UUID:"
    else:
        return "MAC Address:"

def _get_rssi(device, adv_data=None):
    """Safely extract RSSI from a BLEDevice or AdvertisementData.
    Newer Bleak (0.21+) removed BLEDevice.rssi; it's on AdvertisementData instead."""
    if adv_data is not None:
        try:
            return adv_data.rssi
        except (AttributeError, TypeError):
            pass
    try:
        return device.rssi
    except (AttributeError, TypeError):
        return "?"

def _get_light_rssi(light_entry):
    """Get the RSSI display string for an availableLights entry.
    Uses stored RSSI at index [9] if available, falls back to device object."""
    if len(light_entry) > 9 and light_entry[9] is not None:
        return str(light_entry[9])
    try:
        return str(light_entry[0].rssi)
    except (AttributeError, TypeError):
        return "?"

# TEST TO MAKE SURE THE VALUE GIVEN TO THE FUNCTION IS VALID OR IN BOUNDS
def testValid(theParam, theValue, defaultValue, startBounds, endBounds, returnDefault = False):
    if theParam == "temp":
        if len(theValue) > 1: # if the temp has at least 2 characters in it
            theValue = theValue[:2] # take the first 2 characters of the string to convert into int
        else: # it either doesn't have enough characters, or isn't a number
            printDebugString(" >> error with --temp specified (not enough digits or not a number), so falling back to default value of " + str(defaultValue))
            theValue = defaultValue # default to 56(00)K for color temperature

    try: # try converting the string into an integer and processing the bounds
        theValue = int(theValue) # the value is assumed to be within the bounds, so we check it...

        if theValue < startBounds or theValue > endBounds: # the value is not within bounds, so there's an error
            if returnDefault == False: # if the value is too high or low, but we aren't set to return the defaults, make it the lowest/highest boundary
                if theValue < startBounds: # if the value specified is below the starting boundary, make it the starting boundary
                    printDebugString(" >> --" + theParam + " (" + str(theValue) + ") isn't between the bounds of " + str(startBounds) + " and " + str(endBounds) + ", so falling back to closest boundary of " + str(startBounds))
                    theValue = startBounds
                elif theValue > endBounds: # if the value specified is above the ending boundary, make it the ending boundary
                    printDebugString(" >> --" + theParam + " (" + str(theValue) + ") isn't between the bounds of " + str(startBounds) + " and " + str(endBounds) + ", so falling back to closest boundary of " + str(endBounds))
                    theValue = endBounds
            else: # if the value is too high or low, but we're set to return the default, do that here
                printDebugString(" >> --" + theParam + " (" + str(theValue) + ") isn't between the bounds of " + str(startBounds) + " and " + str(endBounds) + ", so falling back to the default value of " + str(defaultValue))
                theValue = defaultValue

        return theValue # return the within-bounds value
    except ValueError: # if the string can not be converted, then return the defaultValue
        printDebugString(" >> --" + theParam + " specified is not a number - falling back to default value of " + str(defaultValue))
        return defaultValue # return the default value

# PRINT A DEBUG STRING TO THE CONSOLE, ALONG WITH THE CURRENT TIME
_logBuffer = []  # buffered log lines for file writing
_logBufferFlushInterval = 10.0  # seconds between file flushes
_lastLogFlush = 0
_bgThreadLogCounter = 0  # throttle "Background Thread Running" messages

def printDebugString(theString):
    global _lastLogFlush, _bgThreadLogCounter
    now = datetime.now()
    currentTime = now.strftime("%H:%M:%S")
    logLine = "[" + currentTime + "] - " + theString

    if printDebug == True:
        print(logLine)

    # Emit to GUI log tab if available
    if enableLogTab:
        try:
            if mainWindow is not None:
                mainWindow._logSignal.emit(logLine)
        except Exception:
            pass

    # Buffer log file writes for efficiency (flush every 10s instead of per-line)
    if logToFile:
        _logBuffer.append(logLine)
        elapsed = time.time() - _lastLogFlush
        if elapsed >= _logBufferFlushInterval or len(_logBuffer) >= 50:
            try:
                with open(logFilePath, "a", encoding="utf-8") as f:
                    f.write("\n".join(_logBuffer) + "\n")
                _logBuffer.clear()
                _lastLogFlush = time.time()
            except Exception:
                pass

# CALCULATE THE BYTESTRING TO SEND TO THE LIGHT
def calculateByteString(returnValue = False, **modeArgs):
    if modeArgs["colorMode"] == "CCT":
        # We're in CCT (color balance) mode
        computedValue = [120, 135, 2, 0, 0, 0]

        computedValue[3] = int(modeArgs["brightness"]) # the brightness value
        computedValue[4] = int(modeArgs["temp"]) # the color temp value, ranging from 32(00K) to 85(00)K - some lights (like the SL-80) can go as high as 8500K
        computedValue[5] = calculateChecksum(computedValue) # compute the checksum
    elif modeArgs["colorMode"] == "HSI":
        # We're in HSI (any color of the spectrum) mode
        computedValue = [120, 134, 4, 0, 0, 0, 0, 0]

        computedValue[3] = int(modeArgs["HSI_H"]) & 255 # hue value, up to 255
        computedValue[4] = (int(modeArgs["HSI_H"]) & 65280) >> 8 # offset value, computed from above value
        computedValue[5] = int(modeArgs["HSI_S"]) # saturation value
        computedValue[6] = int(modeArgs["HSI_I"]) # intensity value
        computedValue[7] = calculateChecksum(computedValue) # compute the checksum
    elif modeArgs["colorMode"] == "ANM":
        # We're in ANM (animation) mode
        computedValue = [120, 136, 2, 0, 0, 0]

        computedValue[3] = int(modeArgs["brightness"]) # brightness value
        computedValue[4] = int(modeArgs["animation"]) # the number of animation you're going to run (check comments above)
        computedValue[5] = calculateChecksum(computedValue) # compute the checksum
    else:
        computedValue = [0]

    if returnValue == False: # if we aren't supposed to return a value, then just set sendValue to the value returned from computedValue
        global sendValue
        sendValue = computedValue
    else:
        return computedValue # return the computed value

# RECALCULATE THE BYTESTRING FOR CCT-ONLY NEEWER LIGHTS INTO HUE AND BRIGHTNESS SEPARATELY
def calculateSeparateBytestrings(sendValue):
    # CALCULATE BRIGHTNESS ONLY PARAMETER FROM MAIN PARAMETER
    newValueBRI = [120, 130, 1, sendValue[3], 0]
    newValueBRI[4] = calculateChecksum(newValueBRI)

    # CALCULATE HUE ONLY PARAMETER FROM MAIN PARAMETER
    newValueHUE = [120, 131, 1, sendValue[4], 0]
    newValueHUE[4] = calculateChecksum(newValueHUE)

    if CCTSlider == -1: # return both newly computed values
        return [newValueBRI, newValueHUE]
    elif CCTSlider == 1: # return only the color temperature value
        return newValueHUE
    elif CCTSlider == 2: # return only the brightness value
        return newValueBRI
        

def setPowerBytestring(onOrOff):
    global sendValue

    if onOrOff == "ON":
        sendValue = [120, 129, 1, 1, 251] # return the "turn on" bytestring
    else:
        sendValue = [120, 129, 1, 2, 252] # return the "turn off" bytestring

# MAKE CURRENT BYTESTRING INTO A STRING OF HEX CHARACTERS TO SHOW THE CURRENT VALUE BEING GENERATED BY THE PROGRAM
def updateStatus(splitString = False, customValue=False):
        currentHexString = ""

        if customValue == False:
            customValue = sendValue

        if splitString == False: # False is for the status bar (shows the bytestring computed as one long line)
            for a in range(len(customValue)):
                currentHexString = currentHexString + " " + str(hex(customValue[a]))
        else: # True is for the table view, this view no longer shows bytestring, but readable status of current mode (temp/bri/hue, etc.)
            currentHexString = ""

            if customValue[1] == 134:
                currentHexString = "(HSI MODE):\n"
                currentHexString = currentHexString + "  H: " + str(customValue[3] + (256 * customValue[4])) + u'\N{DEGREE SIGN}' + " / S: " + str(customValue[5]) + " / I: " + str(customValue[6])
            elif customValue[1] == 135:
                currentHexString = "(CCT MODE):\n"
                currentHexString = currentHexString + "  TEMP: " + str(customValue[4]) + "00K / BRI: " + str(customValue[3])
            elif customValue[1] == 136:
                currentHexString = "(ANM/SCENE MODE):\n"
                currentHexString = currentHexString + "  SCENE: " + str(customValue[4]) + " / BRI: " + str(customValue[3])

        return currentHexString

# CALCULATE THE CHECKSUM FROM THE BYTESTRING
def calculateChecksum(sendValue):
    checkSum = 0

    for a in range(len(sendValue) - 1):
        if sendValue[a] < 0:
            checkSum = checkSum + int(sendValue[a] + 256)
        else:
            checkSum = checkSum + int(sendValue[a])

    checkSum = checkSum & 255
    return checkSum

# FIND NEW LIGHTS
async def findDevices():
    global availableLights
    printDebugString("Searching for new lights")

    currentScan = [] # add all the current scan's lights detected to a standby array (to check against the main one)

    # Use return_adv=True to get AdvertisementData (which carries RSSI in newer Bleak)
    try:
        scan_results = await BleakScanner.discover(return_adv=True)  # returns dict[str, tuple[BLEDevice, AdvertisementData]]
    except TypeError:
        # Very old Bleak that doesn't support return_adv — fall back
        scan_results_list = await BleakScanner.discover()
        scan_results = {d.address: (d, None) for d in scan_results_list}

    for addr, (d, adv) in scan_results.items(): # go through all of the devices Bleak just found
        if d.address in whiteListedMACs: # if the MAC address is in the list of whitelisted addresses, add this device
            printDebugString("Matching whitelisted address found - " + returnMACname() + " " + d.address + ", adding to the list")
            currentScan.append((d, adv))
        else: # if this device is not whitelisted, check to see if it's valid (contains "NEEWER" in the name)
            if d.name != None and "NEEWER" in d.name: # if Bleak returned a proper string, and the string has "NEEWER" in the name
                currentScan.append((d, adv)) # add this light to this session's available lights            

    for a in range(len(currentScan)): # scan the newly found NEEWER devices
        device, adv_data = currentScan[a]
        rssi = _get_rssi(device, adv_data)
        newLight = True # initially mark this light as a "new light"

        # check the "new light" against the global list
        for b in range(len(availableLights)):
            if device.address == availableLights[b][0].address: # if the new light's MAC address matches one already in the global list
                printDebugString("Light found! [" + device.name + "] " + returnMACname() + " " + device.address + " but it's already in the list.  It may have disconnected, so relinking might be necessary.")
                newLight = False # then don't add another instance of it

                # if we found the light *again*, it's most likely the light disconnected, so we need to link it again
                availableLights[b][0] = device  # replace with fresh device object
                # Update stored RSSI (index 9), extending list if needed
                if len(availableLights[b]) > 9:
                    availableLights[b][9] = rssi
                else:
                    availableLights[b].append(rssi)
                availableLights[b][1] = "" # clear the Bleak connection (as it's changed) to force the light to need re-linking

                break # stop checking if we've found a negative result

        if newLight == True: # if this light was not found in the global list, then we need to add it
            printDebugString("Found new light! [" + device.name + "] " + returnMACname() + " " + device.address + " RSSI: " + str(rssi) + " dBm")
            customPrefs = getCustomLightPrefs(device.address, device.name)
            prefID = customPrefs[4] if len(customPrefs) > 4 else 0

            if customPrefs[3] is not None and isinstance(customPrefs[3], list): # we have previously stored parameters
                availableLights.append([device, "", customPrefs[0], customPrefs[3], customPrefs[1], customPrefs[2], True, ["---", "---"], prefID, rssi])
            else: # no stored parameters — use defaults
                availableLights.append([device, "", customPrefs[0], [120, 135, 2, 20, 56, 157], customPrefs[1], customPrefs[2], True, ["---", "---"], prefID, rssi])

    if threadAction != "quit":
        return "" # once the device scan is over, set the threadAction to nothing
    else: # if we're requesting that we quit, then just quit
        return "quit"

def getCustomLightPrefs(MACAddress, lightName = ""):
    customPrefsPath = MACAddress.split(":")
    customPrefsPath = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep + "light_prefs" + os.sep + "".join(customPrefsPath)

    if os.path.exists(customPrefsPath):
        printDebugString("A custom preferences file was found for " + MACAddress + "!")

        # READ THE PREFERENCES FILE INTO A LIST
        with open(customPrefsPath, mode="r", encoding="utf-8") as fileToOpen:
            customPrefs = fileToOpen.read().split("|")

        if customPrefs[1] == "True": # original "wider" preference set expands color temps to 3200-8500K
            customPrefs[1] = [3200, 8500]
        elif customPrefs[1] == "False": # original "non wider" preference set color temps to 3200-5600K
            customPrefs[1] = [3200, 5600]
        elif customPrefs[1] == "": # no entry means we need to get the default value for color temps
            customPrefs[1] = getLightSpecs(lightName, "temp")
        else: # we have a new version of preferences that directly specify the color temperatures
            testPrefs = getLightSpecs(lightName, "temp")
            colorTemps = customPrefs[1].replace(" ", "").split(",")

            # TEST TO MAKE SURE VALUES RETURNED FROM colorTemps ARE VALID INTEGER VALUES
            if len(colorTemps) == 2: # we NEED to have 2 values in the list, or it's not a correct declaration (min,max)
                customPrefs[1] = [testValid("custom_preset_range_min", colorTemps[0], testPrefs[0], 1000, 5600, True),
                                  testValid("custom_preset_range_max", colorTemps[1], testPrefs[1], 1000, 10000, True)]
            else: # so if we have a different number of elements, we're wrong - revert to defaults
                printDebugString("Custom color range defined in preferences is incorrect - falling back to default values!")
                customPrefs[1] = testPrefs

        if customPrefs[2] == "True":
            customPrefs[2] = True # convert "True" as a string to an actual boolean value of True
        elif customPrefs[2] == "False":
            customPrefs[2] = False # convert "False" as a string to an actual boolean value of False
        else: # if we have no value, then get the default value for CCT enabling
            customPrefs[2] = getLightSpecs(lightName, "CCT")

        if len(customPrefs) >= 4 and customPrefs[3].strip(): # if we have a 4th element (the last used parameters), then load them here
            customPrefs[3] = customPrefs[3].replace(" ", "").split(",") # split the last params into a list

            try:
                for a in range(len(customPrefs[3])): # convert the string values to ints
                    customPrefs[3][a] = int(customPrefs[3][a])
            except ValueError:
                customPrefs[3] = None  # malformed last settings — treat as missing
        elif len(customPrefs) >= 4:
            customPrefs[3] = None  # empty lastSettings field

        # Preferred ID is the 5th field (index 4) — parse it and ensure the list has it
        preferredID = 0
        if len(customPrefs) >= 5:
            try:
                preferredID = int(customPrefs[4])
            except (ValueError, IndexError):
                pass

        # Normalize: always return [name, tempRange, cctOnly, lastSettings_or_None, preferredID]
        while len(customPrefs) < 4:
            customPrefs.append(None)
        if len(customPrefs) < 5:
            customPrefs.append(preferredID)
        else:
            customPrefs[4] = preferredID

        return customPrefs
    else: # if there is no custom preferences file, still check the name against a list of per-light parameters
        specs = getLightSpecs(lightName) # get the factory default settings for this light
        # getLightSpecs returns [name, tempRange, cctOnly] — extend with None lastSettings and 0 preferredID
        while len(specs) < 4:
            specs.append(None)
        if len(specs) < 5:
            specs.append(0)
        return specs

# RETURN THE DEFAULT FACTORY SPECIFICATIONS FOR LIGHTS
def getLightSpecs(lightName, returnParam = "all"):
    # the first section of lights here are LED only (can't use HSI), and the 2nd section are HSI-capable lights
    # listed with their name, the max and min color temps available to use in CCT mode, and HSI only (True) or not (False)
    masterNeewerLuxList = [
        ["Apollo", 5600, 5600, True], ["GL1", 2900, 7000, True], ["NL140", 3200, 5600, True],
        ["SNL1320", 3200, 5600, True], ["SNL1920", 3200, 5600, True], ["SNL480", 3200, 5600, True],
        ["SNL530", 3200, 5600, True], ["SNL660", 3200, 5600, True], ["SNL960", 3200, 5600, True],
        ["SRP16", 3200, 5600, True], ["SRP18", 3200, 5600, True], ["WRP18", 3200, 5600, True],
        ["ZRP16", 3200, 5600, True],
        ["BH30S", 2500, 10000, False], ["CB60", 2500, 6500, False], ["CL124", 2500, 10000, False],
        ["RGB C80", 2500, 10000, False], ["RGB CB60", 2500, 10000, False], ["RGB1000", 2500, 10000, False],
        ["RGB1200", 2500, 10000, False], ["RGB140", 2500, 10000, False], ["RGB168", 2500, 8500, False],
        ["RGB176 A1", 2500, 10000, False], ["RGB512", 2500, 10000, False], ["RGB800", 2500, 10000, False],
        ["SL-90", 2500, 10000, False], ["RGB1", 3200, 5600, False], ["RGB176", 3200, 5600, False],
        ["RGB18", 3200, 5600, False], ["RGB190", 3200, 5600, False], ["RGB450", 3200, 5600, False],
        ["RGB480", 3200, 5600, False], ["RGB530PRO", 3200, 5600, False], ["RGB530", 3200, 5600, False],
        ["RGB650", 3200, 5600, False], ["RGB660PRO", 3200, 5600, False], ["RGB660", 3200, 5600, False],
        ["RGB960", 3200, 5600, False], ["RGB-P200", 3200, 5600, False], ["RGB-P280", 3200, 5600, False],
        ["SL70", 3200, 8500, False], ["SL80", 3200, 8500, False], ["ZK-RY", 5600, 5600, False]
    ]
    
    for a in range(len(masterNeewerLuxList)): # scan the list of preset specs above to find the current light in them
        # the default list of preferences - no custom name, a color temp range from 3200-5600K, and RGB not restricted (False)
        # if we don't find the name of the light in the master list, we just return these default parameters
        customPrefs = ["", [3200, 5600], False]

        # check the master list to see if the current light is found - if it is, then change the prefs to reflect the light's spec
        if masterNeewerLuxList[a][0] in lightName.replace(" ", ""):
            # customPrefs[0] = masterNeewerLuxList[a][0] # the name of the light (for testing purposes)
            customPrefs[1] = [masterNeewerLuxList[a][1], masterNeewerLuxList[a][2]] # the HSI color temp range
            customPrefs[2] = masterNeewerLuxList[a][3] # whether or not to allow RGB commands
            break # stop looking for the light!

    if returnParam == "all": # we want to return all information (the default)
        return customPrefs
    elif returnParam == "temp": # we only want to return color temp ranges for this light
        return customPrefs[1]
    elif returnParam == "CCT": # we only want to return CCT-only status for this light
        return customPrefs[2]

# CONNECT (LINK) TO A LIGHT
async def connectToLight(selectedLight, updateGUI=True):
    global availableLights
    isConnected = False # whether or not the light is connected
    returnValue = "" # the value to return to the thread (in GUI mode, a string) or True/False (in CLI mode, a boolean value)

    lightName = availableLights[selectedLight][0].name # the Name of the light (for status updates)
    lightMAC = availableLights[selectedLight][0].address # the MAC address of the light (to keep track of the light even if the index number changes)

    createNewBleakInstance = False

    # CHECK TO SEE IF A BLEAK OBJECT EXISTS
    if availableLights[returnLightIndexesFromMacAddress(lightMAC)[0]][1] == "":
        createNewBleakInstance = True
    else: # if the object exists, but nothing is connected to it, then make a new instance
        if not availableLights[returnLightIndexesFromMacAddress(lightMAC)[0]][1].is_connected:
            createNewBleakInstance = True

    if createNewBleakInstance == True: # FILL THE [1] ELEMENT OF THE availableLights ARRAY WITH A NEW BLEAK CONNECTION OBJECT
        lightIdx = returnLightIndexesFromMacAddress(lightMAC)[0]
        device = availableLights[lightIdx][0]
        try:
            availableLights[lightIdx][1] = BleakClient(device)
        except (AttributeError, TypeError):
            # BLEDevice.details may be None if re-discovered without advertisement data
            # Fall back to MAC address string
            printDebugString("BLEDevice details unavailable for " + lightMAC + ", using address string")
            availableLights[lightIdx][1] = BleakClient(lightMAC)
        await asyncio.sleep(0.25) # wait just a short time before trying to connect

    # TRY TO CONNECT TO THE LIGHT SEVERAL TIMES BEFORE GIVING UP THE LINK
    currentAttempt = 1

    while isConnected == False and currentAttempt <= maxNumOfAttempts:
        if threadAction != "quit":
            try:
                if not availableLights[returnLightIndexesFromMacAddress(lightMAC)[0]][1].is_connected: # if the current device isn't linked to Bluetooth
                    printDebugString("Attempting to link to light [" + lightName + "] " + returnMACname() + " " + lightMAC + " (Attempt " + str(currentAttempt) + " of " + str(maxNumOfAttempts) + ")")
                    isConnected = await availableLights[returnLightIndexesFromMacAddress(lightMAC)[0]][1].connect() # try connecting it (and return the connection status)
                else:
                    isConnected = True # the light is already connected, so mark it as being connected
            except Exception as e:
                printDebugString("Error linking to light [" + lightName + "] " + returnMACname() + " " + lightMAC)
              
                if updateGUI == True:
                    if currentAttempt < maxNumOfAttempts:
                        lightIdx = returnLightIndexesFromMacAddress(lightMAC)[0]
                        if currentAttempt == 1:
                            # First attempt failures are common (BLE adapter settling) — show gentle status
                            if mainWindow is not None: mainWindow._tableUpdateSignal.emit(["", "", "", "Connecting..."], lightIdx)
                        else:
                            # Subsequent failures are worth reporting
                            if mainWindow is not None: mainWindow._tableUpdateSignal.emit(["", "", "NOT\nLINKED", "There was an error connecting to the light, trying again (Attempt " + str(currentAttempt + 1) + " of " + str(maxNumOfAttempts) + ")..."], lightIdx)
                else:
                    returnValue = False # if we're in CLI mode, and there is an error connecting to the light, return False

                currentAttempt = currentAttempt + 1
                if currentAttempt == 2:
                    await asyncio.sleep(1) # short retry after first failure (usually just BLE settling)
                else:
                    await asyncio.sleep(4) # longer wait for subsequent retries
        else:
            return "quit"

    if threadAction == "quit":
        return "quit"
    else:
        if isConnected == True:
            printDebugString("Successful link on light [" + lightName + "] " + returnMACname() + " " + lightMAC)

            if updateGUI == True:
                if mainWindow is not None: mainWindow._tableUpdateSignal.emit(["", "", "LINKED", "Waiting to send..."], returnLightIndexesFromMacAddress(lightMAC)[0]) # if it's successful, show that in the table
            else:
                returnValue = True  # if we're in CLI mode, and there is no error connecting to the light, return True
        else:
            if updateGUI == True:
                if mainWindow is not None: mainWindow._tableUpdateSignal.emit(["", "", "NOT\nLINKED", "There was an error connecting to the light"], returnLightIndexesFromMacAddress(lightMAC)[0]) # there was an issue connecting this specific light to Bluetooh, so show that

            returnValue = False # the light is not connected

    return returnValue # once the connection is over, then return either True or False (for CLI) or nothing (for GUI)

async def readNotifyCharacteristic(selectedLight, diagCommand, typeOfData):
    # clear the global variable before asking the light for info
    global receivedData
    receivedData = ""

    try:
        await availableLights[selectedLight][1].start_notify(notifyLightUUID, notifyCallback) # start reading notifications from the light
    except Exception as e:
        try: # if we've resorted the list, there is a possibility of a hanging callback, so this will raise an exception
            await availableLights[selectedLight][1].stop_notify(notifyLightUUID) # so we need to try disconnecting first
            await asyncio.sleep(0.5) # wait a little bit of time before re-connecting to the callback
            await availableLights[selectedLight][1].start_notify(notifyLightUUID, notifyCallback) # try again to start reading notifications from the light
        except Exception as e: # if we truly can't connect to the callback, return a blank string
            return "" # if there is an error starting the characteristic scan, just quit out of this routine

    for a in range(maxNumOfAttempts): # attempt maxNumOfAttempts times to read the characteristics
        try:
            await availableLights[selectedLight][1].write_gatt_char(setLightUUID, bytearray(diagCommand))
        except Exception as e:
            return "" # if there is an error checking the characteristic, just quit out of this routine

        if receivedData != "": # if the recieved data is populated
            if len(receivedData) > 1: # if we have enough elements to get a status from
                if receivedData[1] == typeOfData: # if the data returned is the correct *kind* of data
                    break # stop scanning for data
            else: # if we have a list, but it doesn't have a payload in it (the light didn't supply enough data)
                receivedData = "---" # then just re-set recievedData to the default string
                break # stop scanning for data
        else:
            await asyncio.sleep(0.25) # wait a little bit of time before checking again
    try:
        await availableLights[selectedLight][1].stop_notify(notifyLightUUID) # stop reading notifications from the light
    except Exception as e:
        pass # we will return whatever data remains from the scan, so if we can't stop the scan (light disconnected), just return what we have

    return receivedData

async def getLightChannelandPower(selectedLight):
    global availableLights
    returnInfo = ["---", "---"] # the information to return to the light

    powerInfo = await readNotifyCharacteristic(selectedLight, [120, 133, 0, 253], 2)

    try:
        if powerInfo != "":
            if powerInfo[3] == 1:
                returnInfo[0] = "ON"
            elif powerInfo[3] == 2:
                returnInfo[0] = "STBY"
        
            # IF THE LIGHT IS ON, THEN ATTEMPT TO READ THE CURRENT CHANNEL
            chanInfo = await readNotifyCharacteristic(selectedLight, [120, 132, 0, 252], 1)

            if chanInfo != "": # if we got a result from the query
                try:
                    returnInfo[1] = chanInfo[3] # set the current channel to the returned result
                except IndexError:
                    pass # if we have an index error (the above value doesn't exist), then just return -1
    except IndexError:
        # if we have an IndexError (the information returned isn't blank, but also isn't enough to descipher the status)
        # then just error out, but print the information that *was* returned for debugging purposes
        printDebugString("We don't have enough information from light [" + availableLights[selectedLight][0].name + "] to get the status.")
        print(powerInfo)

    availableLights[selectedLight][7][0] = returnInfo[0]

    if availableLights[selectedLight][1] != "---" and returnInfo[1] != "---":
        availableLights[selectedLight][7][1] = returnInfo[1]

def notifyCallback(sender, data):
    global receivedData
    receivedData = data

# DISCONNECT FROM A LIGHT
async def disconnectFromLight(selectedLight, updateGUI=True):
    returnValue = "" # same as above, string for GUI mode and boolean for CLI mode, default to blank string

    if availableLights[selectedLight][1] != "": # if there is a Bleak object attached to the light, try to disconnect
        try:
            if availableLights[selectedLight][1].is_connected: # if the current light is connected
                await availableLights[selectedLight][1].disconnect() # disconnect the selected light
        except Exception as e:
            returnValue = False # if we're in CLI mode, then return False if there is an error disconnecting

            printDebugString("Error unlinking from light " + str(selectedLight + 1) + " [" + availableLights[selectedLight][0].name + "] " + returnMACname() + " " + availableLights[selectedLight][0].address)
            print(e)

        try:
            if not availableLights[selectedLight][1].is_connected: # if the current light is NOT connected, then we're good
                if updateGUI == True: # if we're using the GUI, update the display (if we're waiting)
                    if mainWindow is not None: mainWindow._tableUpdateSignal.emit(["", "", "NOT\nLINKED", "Light disconnected!"], selectedLight) # show the new status in the table
                else: # if we're not, then indicate that we're good
                    returnValue = True # if we're in CLI mode, then return False if there is an error disconnecting

                printDebugString("Successfully unlinked from light " + str(selectedLight + 1) + " [" + availableLights[selectedLight][0].name + "] " + returnMACname() + " " + availableLights[selectedLight][0].address)
        except AttributeError:
            printDebugString("Light " + str(selectedLight + 1) + " has no Bleak object attached to it, so not attempting to disconnect from it")

    return returnValue

# WRITE TO A LIGHT - optional arguments for the CLI version (GUI version doesn't use either of these)
async def writeToLight(selectedLights=0, updateGUI=True, useGlobalValue=True):
    global availableLights
    returnValue = "" # same as above, return value "" for GUI, or boolean for CLI

    startTimer = time.time() # the start of the triggering
    printDebugString("Going into send mode")

    try:
        if updateGUI == True:
            if selectedLights == 0:
                selectedLights = mainWindow.selectedLights() # get the list of currently selected lights from the GUI table
        else:
            if type(selectedLights) is int: # if we specify an integer-based index
                selectedLights = [selectedLights] # convert asked-for light to list

        currentSendValue = [] # initialize the value check

        # if there are lights selected (otherwise just dump out), and the delay timer is less than it's maximum, then try to send to the lights selected
        while (len(selectedLights) > 0 and time.time() - startTimer < 0.4) :
            if currentSendValue != sendValue: # if the current value is different than what was last sent to the light, then send a new one
                currentSendValue = sendValue # get this value before sending to multiple lights, to ensure the same value is sent to each one

                for a in range(len(selectedLights)): # try to write each light in turn, and show the current data being sent to them in the table
                    # THIS SECTION IS FOR LOADING SNAPSHOT PRESET POWER STATES
                    if useGlobalValue == False: # if we're forcing the lights to use their stored parameters, then load that in here
                        if availableLights[selectedLights[a]][3][0] == 0: # we want to turn the light off
                            availableLights[selectedLights[a]][3][0] = 120 # reset the light's value to the normal value
                            currentSendValue = [120, 129, 1, 2, 252] # set the send value to turn the light off downstream
                        else: # we want to turn the light on and run a snapshot preset
                            await availableLights[int(selectedLights[a])][1].write_gatt_char(setLightUUID, bytearray([120, 129, 1, 1, 251]), False) # force this light to turn on
                            availableLights[int(selectedLights[a])][6] = True # set the ON flag of this light to True
                            await asyncio.sleep(0.05)

                            currentSendValue = availableLights[selectedLights[a]][3] # set the send value to set the preset downstream

                    if availableLights[selectedLights[a]][1] != "": # if a Bleak connection is there
                        try:
                            # Clamp CCT temperature to the light's effective range
                            if currentSendValue[1] == 135:  # CCT mode
                                clampedTemp = clampCCTForLight(int(selectedLights[a]), currentSendValue[4])
                                if clampedTemp is None:
                                    if updateGUI:
                                        if mainWindow is not None: mainWindow._tableUpdateSignal.emit(["", "", "", "CCT temp out of range (ignored)"], int(selectedLights[a]))
                                    continue  # skip this light
                                elif clampedTemp != currentSendValue[4]:
                                    currentSendValue = list(currentSendValue)  # copy before modifying
                                    currentSendValue[4] = clampedTemp
                                    currentSendValue[5] = calculateChecksum(currentSendValue)

                            if availableLights[(int(selectedLights[a]))][5] == True: # if we're using the old style of light
                                if currentSendValue[1] == 135: # if we're on CCT mode
                                    if CCTSlider == -1: # and we need to write both HUE and BRI to the light
                                        splitCommands = calculateSeparateBytestrings(currentSendValue) # get both commands from the converter

                                        # WRITE BOTH LUMINANCE AND HUE VALUES TOGETHER, BUT SEPARATELY
                                        await availableLights[int(selectedLights[a])][1].write_gatt_char(setLightUUID, bytearray(splitCommands[0]), False)
                                        await asyncio.sleep(0.05) # wait 1/20th of a second to give the Bluetooth bus a little time to recover
                                        await availableLights[int(selectedLights[a])][1].write_gatt_char(setLightUUID, bytearray(splitCommands[1]), False)
                                    else: # we're only writing either HUE or BRI independently
                                        await availableLights[int(selectedLights[a])][1].write_gatt_char(setLightUUID, bytearray(calculateSeparateBytestrings(currentSendValue)), False)
                                elif currentSendValue[1] == 129: # we're using an old light, but we're either turning the light on or off
                                    await availableLights[int(selectedLights[a])][1].write_gatt_char(setLightUUID, bytearray(currentSendValue), False)
                                elif currentSendValue[1] in (134, 136): # HSI or ANM mode on CCT-only light
                                    convertedVal = applyCCTFallback(int(selectedLights[a]), currentSendValue)
                                    if convertedVal is not None:
                                        # Send converted CCT value using split commands for old-style lights
                                        splitCommands = calculateSeparateBytestrings(convertedVal)
                                        await availableLights[int(selectedLights[a])][1].write_gatt_char(setLightUUID, bytearray(splitCommands[0]), False)
                                        await asyncio.sleep(0.05)
                                        await availableLights[int(selectedLights[a])][1].write_gatt_char(setLightUUID, bytearray(splitCommands[1]), False)
                                        currentSendValue = convertedVal  # for status display
                                    elif updateGUI == True:
                                        modeName = "HSI" if currentSendValue[1] == 134 else "ANM/SCENE"
                                        if mainWindow is not None: mainWindow._tableUpdateSignal.emit(["", "", "", modeName + " mode ignored (CCT-only)"], int(selectedLights[a]))
                            else: # we're using a "newer" Neewer light, so just send the original calculated value
                                await availableLights[int(selectedLights[a])][1].write_gatt_char(setLightUUID, bytearray(currentSendValue), False)

                            if updateGUI == True:
                                # if we're not looking at an old light, or if we are, we're not in either HSI or ANM modes, then update the status of that light
                                if not (availableLights[(int(selectedLights[a]))][5] == True and (currentSendValue[1] == 134 or currentSendValue[1] == 136)):
                                    if currentSendValue[1] != 129: # if we're not turning the light on or off
                                        if mainWindow is not None: mainWindow._tableUpdateSignal.emit(["", "", "", updateStatus(True, currentSendValue)], int(selectedLights[a]))
                                    else: # we ARE turning the light on or off
                                        if currentSendValue[3] == 1: # we turned the light on
                                            availableLights[int(selectedLights[a])][6] = True # toggle the "light on" parameter of this light to ON

                                            changeStatus = mainWindow.returnTableInfo(selectedLights[a], 2).replace("STBY", "ON") if mainWindow is not None else ""
                                            if mainWindow is not None: mainWindow._tableUpdateSignal.emit(["", "", changeStatus, "Light turned on"], int(selectedLights[a]))

                                        else: # we turned the light off
                                            availableLights[int(selectedLights[a])][6] = False # toggle the "light on" parameter of this light to OFF

                                            changeStatus = mainWindow.returnTableInfo(selectedLights[a], 2).replace("ON", "STBY") if mainWindow is not None else ""
                                            if mainWindow is not None: mainWindow._tableUpdateSignal.emit(["", "", changeStatus, "Light turned off\nA long period of inactivity may require a re-link to the light"], int(selectedLights[a]))
                            else:
                                returnValue = True # we successfully wrote to the light

                            if currentSendValue[1] != 129: # if we didn't just send a command to turn the light on/off
                                availableLights[selectedLights[a]][3] = currentSendValue # store the currenly sent value to recall later
                        except Exception as e:
                            if updateGUI == True:
                                if mainWindow is not None: mainWindow._tableUpdateSignal.emit(["", "", "", "Error Sending to light!"], int(selectedLights[a]))
                    else: # if there is no Bleak object associated with this light (otherwise, it's been found, but not linked)
                        if updateGUI == True:
                            if mainWindow is not None: mainWindow._tableUpdateSignal.emit(["", "", "", "Light isn't linked yet, can't send to it"], int(selectedLights[a]))
                        else:
                            returnValue = 0 # the light is not linked, even though it *should* be if it gets to this point, so this is an odd error

                if useGlobalValue == True:
                    startTimer = time.time() # if we sent a value, then reset the timer
                else:
                    break # don't do the loop again (as we just want to send the commands once instead of look for newly selected lights)

            await asyncio.sleep(0.05) # wait 1/20th of a second to give the Bluetooth bus a little time to recover

            if updateGUI == True:
                selectedLights = mainWindow.selectedLights() # re-acquire the current list of selected lights
    except Exception as e:
        printDebugString("There was an error communicating with light " + str(selectedLights[a] + 1) + " [" + availableLights[selectedLights[a]][0].name + "] " + returnMACname() + " " + availableLights[selectedLights[a]][0].address)
        print(e)

        if updateGUI == True:
            returnValue = False # there was an error writing to this light, so return false to the CLI

    if updateGUI == True:
        if threadAction != "quit": # if we've been asked to quit somewhere else in the program
            printDebugString("Leaving send mode and going back to background thread")
        else:
            printDebugString("The program has requested to quit, so we're not going back to the background thread")
            returnValue = "quit"

    return returnValue

# USE THIS FUNCTION TO CONNECT TO ONE LIGHT (for CLI mode) AND RETRIEVE ANY CUSTOM PREFS (necessary for lights like the SNL-660)
async def connectToOneLight(MACAddress):
    global availableLights

    try:
        currentLightToAdd = await BleakScanner.find_device_by_address(MACAddress)
        customLightPrefs = getCustomLightPrefs(currentLightToAdd.address, currentLightToAdd.name)
        availableLights = [[currentLightToAdd, "", customLightPrefs[0], [], customLightPrefs[1], customLightPrefs[2], True, ["---", "---"], customLightPrefs[4] if len(customLightPrefs) > 4 else 0]]
    except Exception as e:
        printDebugString("Error finding the Neewer light with MAC address " + MACAddress)
        print(e)

async def parallelWriteToLights(lightIndices):
    """Write stored byte values to multiple lights simultaneously using asyncio.gather.
    Used by animation engine when parallel write mode is enabled."""
    async def writeSingleLight(idx):
        try:
            if idx < len(availableLights) and availableLights[idx][1] != "":
                currentSendValue = availableLights[idx][3]
                if currentSendValue is not None:
                    # Apply CCT-only fallback if needed
                    sendVal = applyCCTFallback(idx, currentSendValue)
                    if sendVal is None:
                        return  # ignore mode
                    # Clamp CCT temperature to effective range
                    if sendVal[1] == 135:
                        clampedTemp = clampCCTForLight(idx, sendVal[4])
                        if clampedTemp is None:
                            return  # out of range, ignore
                        elif clampedTemp != sendVal[4]:
                            sendVal = list(sendVal)
                            sendVal[4] = clampedTemp
                            sendVal[5] = calculateChecksum(sendVal)
                    if availableLights[idx][5] == True and sendVal[1] == 135:
                        # Old-style CCT light needs split commands
                        splitCmds = calculateSeparateBytestrings(sendVal)
                        await availableLights[int(idx)][1].write_gatt_char(setLightUUID, bytearray(splitCmds[0]), False)
                        await asyncio.sleep(0.05)
                        await availableLights[int(idx)][1].write_gatt_char(setLightUUID, bytearray(splitCmds[1]), False)
                    else:
                        await availableLights[int(idx)][1].write_gatt_char(setLightUUID, bytearray(sendVal), False)
        except Exception as e:
            printDebugString("Parallel write error on light " + str(idx + 1) + ": " + str(e))

    tasks = [writeSingleLight(idx) for idx in lightIndices]
    if tasks:
        await asyncio.gather(*tasks)


# THE BACKGROUND WORKER THREAD
def workerThread(_loop):
    global threadAction, _bgThreadLogCounter

    # A LIST OF LIGHTS THAT DON'T SEND POWER/CHANNEL STATUS
    lightsToNotCheckPower = ["NEEWER-RGB176"]
    hasGUI = mainWindow is not None  # False in HTTP-only mode

    if findLightsOnStartup == True: # if we're set to find lights at startup, then automatically set the thread to discovery mode
        threadAction = "discover"

    delayTicks = 1 # count a few ticks before checking light information
    reconnectCooldown = {} # {light_index: ticks_remaining} to avoid spamming reconnect attempts
    allDisconnectedSince = 0  # ticks since all known lights were seen as disconnected (for rescan-after-wake)

    while True:
        if delayTicks < 12:
            delayTicks += 1
        elif delayTicks == 12:
            delayTicks = 1

            # SKIP HEAVY BLE STATUS POLLING WHILE AN ANIMATION IS RUNNING
            # The status check does BLE reads on every connected light which blocks the worker
            # for 1-2 seconds, causing visible stutters in animation playback.
            if not animationRunning:
                _bgThreadLogCounter += 1
                if _bgThreadLogCounter >= 10:  # log every ~30s instead of every ~3s
                    printDebugString("Background Thread Running")
                    _bgThreadLogCounter = 0

                lightsNeedingReconnect = [] # collect lights that need reconnection this cycle
                anyConnected = False

                # CHECK EACH LIGHT AGAINST THE TABLE TO SEE IF THERE ARE CONNECTION ISSUES
                for a in range(len(availableLights)):
                    if threadAction == "": # if we're not sending, then update the light info... (check this before scanning each light)
                        if availableLights[a][1] != "": # if there is a Bleak object, then check to see if it's connected
                            if not availableLights[a][1].is_connected: # the light is disconnected, but we're reporting it isn't
                                if hasGUI: mainWindow._tableUpdateSignal.emit(["", "", "NOT\nLINKED", "Light disconnected!"], a) # show the new status in the table
                                availableLights[a][1] = "" # clear the Bleak object

                                # Queue this light for auto-reconnect if enabled
                                if autoReconnectOnDisconnect and a not in reconnectCooldown:
                                    lightsNeedingReconnect.append(a)
                                    reconnectCooldown[a] = 20  # cooldown: skip ~20 cycles (~60s) before retrying this light again
                                    printDebugString("Light " + str(a + 1) + " disconnected - will attempt auto-reconnect")
                            else:
                                anyConnected = True
                                reconnectCooldown.pop(a, None)  # light is connected, clear any cooldown
                                if not availableLights[a][0].name in lightsToNotCheckPower: # if the name of the current light is not in the list to skip checking
                                    try:
                                        _loop.run_until_complete(getLightChannelandPower(a)) # then check the power and light status of that light
                                    except Exception as e:
                                        printDebugString("Error reading power/channel for light " + str(a + 1) + ": " + str(e))
                                    if hasGUI: mainWindow._tableUpdateSignal.emit(["", "", "LINKED\n" + availableLights[a][7][0] + " / ᴄʜ. " + str(availableLights[a][7][1]), "Waiting to send..."], a)
                                else: # if the light we're scanning doesn't supply power or channel status, then just show "LINKED"
                                    if hasGUI: mainWindow._tableUpdateSignal.emit(["", "", "LINKED", "Waiting to send..."], a)
                        else:
                            # Bleak object is empty - light was previously cleared; check cooldown for retry
                            if autoReconnectOnDisconnect and a not in reconnectCooldown:
                                lightsNeedingReconnect.append(a)
                                reconnectCooldown[a] = 20

                # Tick down cooldowns
                for lightIdx in list(reconnectCooldown.keys()):
                    reconnectCooldown[lightIdx] -= 1
                    if reconnectCooldown[lightIdx] <= 0:
                        del reconnectCooldown[lightIdx]

                # ATTEMPT AUTO-RECONNECT FOR DISCONNECTED LIGHTS
                if lightsNeedingReconnect and threadAction == "":
                    printDebugString("Auto-reconnect: attempting to reconnect " + str(len(lightsNeedingReconnect)) + " light(s)...")

                    # If ALL lights are disconnected, do a fresh scan first (common after sleep/wake)
                    if not anyConnected and len(availableLights) > 0:
                        allDisconnectedSince += 1
                        if allDisconnectedSince >= 2:  # after 2 consecutive all-disconnected cycles, rescan
                            printDebugString("Auto-reconnect: all lights disconnected (likely wake from sleep) - rescanning...")
                            if hasGUI: mainWindow.statusBar.showMessage("Woke from sleep - rescanning for lights...")
                            _loop.run_until_complete(findDevices())
                            if hasGUI: mainWindow.updateLights()
                            allDisconnectedSince = 0
                    else:
                        allDisconnectedSince = 0

                    # Now try connecting to each disconnected light
                    for lightIdx in lightsNeedingReconnect:
                        if threadAction == "quit":
                            break
                        if lightIdx < len(availableLights):
                            if hasGUI: mainWindow._tableUpdateSignal.emit(["", "", "NOT\nLINKED", "Auto-reconnecting..."], lightIdx)

                    try:
                        if threadAction != "quit":
                            _loop.run_until_complete(parallelAction("connect", lightsNeedingReconnect))
                            printDebugString("Auto-reconnect attempt complete")
                    except Exception as e:
                        printDebugString("Auto-reconnect error: " + str(e))

        if threadAction == "quit":
            printDebugString("Stopping the background thread")
            threadAction = "finished"
            break # stop the background thread before quitting the program
        elif threadAction == "discover":
            threadAction = _loop.run_until_complete(findDevices()) # add new lights to the main array

            if threadAction != "quit":
                if hasGUI: mainWindow.updateLights() # tell the GUI to update its list of available lights

                if autoConnectToLights == True: # if we're set to automatically link to the lights on startup, then do it here
                    #for a in range(len(availableLights)):
                    if threadAction != "quit": # if we're not supposed to quit, then try to connect to the light(s)
                        if _isFrozenExe and len(availableLights) > 0:
                            # In PyInstaller builds, the first BleakClient.connect() call almost
                            # always fails (WinRT backend one-time initialization). Do a silent
                            # warm-up attempt with no GUI updates so the user never sees the error.
                            printDebugString("Frozen EXE detected — performing silent BLE warm-up connect...")
                            _loop.run_until_complete(parallelAction("connect", [-1], False))  # updateGUI=False
                            # Clear stale Bleak objects from failed warm-up so real connect creates fresh ones
                            for _wIdx in range(len(availableLights)):
                                if availableLights[_wIdx][1] != "" and not availableLights[_wIdx][1].is_connected:
                                    availableLights[_wIdx][1] = ""
                            await_time = 1  # brief pause before real attempt
                            time.sleep(await_time)
                        _loop.run_until_complete(parallelAction("connect", [-1])) # real connect with GUI updates

                threadAction = ""
        elif threadAction == "connect":
            selectedLights = mainWindow.selectedLights() if hasGUI else [-1] # get the list of currently selected lights

            if threadAction != "quit": # if we're not supposed to quit, then try to connect to the light(s)
                _loop.run_until_complete(parallelAction("connect", selectedLights)) # connect to each *selected* light in parallel

            threadAction = ""
        elif threadAction.startswith("httplink|"):
            # HTTP-triggered connection to specific lights (by index)
            lightIndices = [int(x) for x in threadAction.split("|")[1:]]
            if threadAction != "quit":
                _loop.run_until_complete(parallelAction("connect", lightIndices, False))
            threadAction = ""
        elif threadAction == "send":
            threadAction = _loop.run_until_complete(writeToLight()) # write a value to the light(s) - the selectedLights() section is in the write loop itself for responsiveness
        elif threadAction.startswith("psend|"):
            # Parallel animation write — send to all specified lights simultaneously
            lightIndices = [int(x) for x in threadAction.split("|")[1:]]
            printDebugString("Going into send mode")
            _loop.run_until_complete(parallelWriteToLights(lightIndices))
            printDebugString("Leaving send mode and going back to background thread")
            # Update the Status column in the light table so the user sees current values
            try:
                if mainWindow is not None:
                    for idx in lightIndices:
                        if idx < len(availableLights) and availableLights[idx][3] is not None:
                            if hasGUI: mainWindow._tableUpdateSignal.emit(["", "", "", updateStatus(True, availableLights[idx][3])], idx)
            except Exception:
                pass
            threadAction = ""
        elif threadAction != "":
            result = processMultipleSends(_loop, threadAction)
            threadAction = result if result is not None else ""
        
        # Sleep until next cycle, but wake immediately if animation signals us
        workerWakeEvent.wait(timeout=0.25)
        workerWakeEvent.clear()

def processMultipleSends(_loop, threadAction, updateGUI = True):
    currentThreadAction = threadAction.split("|")

    if currentThreadAction[0] == "send": # this will come from loading a custom snapshot preset
        lightsToSendTo = [] # the current lights to affect

        for a in range (1, len(currentThreadAction)): # find the lights that need to be refreshed
            lightsToSendTo.append(int(currentThreadAction[a]))

        threadAction = _loop.run_until_complete(writeToLight(lightsToSendTo, updateGUI, False)) # write the value stored in the lights to the light(s)
        return threadAction

async def parallelAction(theAction, theLights, updateGUI = True):
    # SUBMIT A SERIES OF PARALLEL ASYNCIO FUNCTIONS TO RUN ALL IN PARALLEL
    parallelFuncs = []

    if theLights[0] == -1: # if we have no specific lights set, then operate on the entire availableLights range
        theLights = [] # clear the selected light list

        for a in range(len(availableLights)):
            theLights.append(a) # add all of availableLights to the list

    for a in range(len(theLights)):
        if theAction == "connect": # connect to a series of lights
            parallelFuncs.append(connectToLight(theLights[a], updateGUI))
        elif theAction == "disconnect": # disconnect from a series of lights
            parallelFuncs.append(disconnectFromLight(theLights[a], updateGUI))
        
    await asyncio.gather(*parallelFuncs) # run the functions in parallel

def processCommands(listToProcess=[]):
    inStartupMode = False # if we're in startup mode (so report that to the log), start as False initially to be set to True below

    # SET THE CURRENT LIST TO THE sys.argv SYSTEM PARAMETERS LIST IF A LIST ISN'T SPECIFIED
    # SO WE CAN USE THIS SAME FUNCTION TO PARSE HTML ARGUMENTS USING THE HTTP SERVER AND COMMAND-LINE ARGUMENTS
    if len(listToProcess) == 0: # if there aren't any elements in the list, then check against sys.argv
        listToProcess = sys.argv[1:] # the list to parse is the system args minus the first one
        inStartupMode = True

    # ADD DASHES TO ANY PARAMETERS THAT DON'T CURRENTLY HAVE THEM AS WELL AS
    # CONVERT ALL ARGUMENTS INTO lower case (to allow ALL CAPS arguments to parse correctly)
    for a in range(len(listToProcess)):
        if listToProcess[a] != "-h" and listToProcess[a][:2] != "--": # if the dashes aren't in the current item (and it's not the -h flag)
            if listToProcess[a][:1] == "-": # if the current parameter only has one dash (typed wrongly)
                listToProcess[a] = "--" + listToProcess[a][1:].lower() # then remove that, and add the double dash and switch to lowercase
            else: # the parameter has no dashes at all, so add them
                if listToProcess[a][:11] == "custom_name": # if we're setting a custom name for the light, DON'T LOWERCASE THE RESULT
                    listToProcess[a] = "--" + listToProcess[a] # add the dashes (but don't make it lowercase)
                else:
                    listToProcess[a] = "--" + listToProcess[a].lower() # add the dashes + switch to lowercase to properly parse as arguments below                  
        else: # if the dashes are already in the current item
            listToProcess[a] = listToProcess[a].lower() # we don't need to add dashes, so just switch to lowercase

    # ARGUMENTS EACH MODE HAS ACCESS TO
    acceptable_arguments = ["--light", "--mode", "--temp", "--hue", "--sat", "--bri", "--intensity",
                            "--scene", "--animation", "--list", "--on", "--off", "--force_instance"]

    # MODE-SPECIFIC ARGUMENTS
    if inStartupMode == True: # if we're using the GUI or CLI, then add these arguments to the list
        acceptable_arguments.extend(["--http", "--cli", "--silent", "--help"])
    else: # if we're using the HTTP server, then add these arguments to the list
        acceptable_arguments.extend(["--custom_name", "--discover", "--nopage", "--link", "--use_preset", "--save_preset", "--add_preset", "--delete_preset", "--batch", "--animate", "--stop_animate", "--list_animations"])

    # KICK OUT ANY PARAMETERS THAT AREN'T IN THE "ACCEPTABLE ARGUMENTS" LIST
    for a in range(len(listToProcess) - 1, -1, -1):
        if not any(x in listToProcess[a] for x in acceptable_arguments): # if the current argument is invalid
            if inStartupMode == True:
                if listToProcess[a] != "-h": # and the argument isn't "-h" (for help)
                    listToProcess.pop(a) # delete the invalid argument from the list
            else: # if we're not in startup mode, then also delete the "-h" flag
                listToProcess.pop(a) # delete the invalid argument from the list

    # IF THERE ARE NO VALID PARAMETERS LEFT TO PARSE, THEN RETURN THAT TO THE HTTP SERVER
    if inStartupMode == False and len(listToProcess) == 0:
        printDebugString("There are no usable parameters from the HTTP request!")
        return []

    # FORCE VALUES THAT NEED PARAMETERS TO HAVE ONE, AND VALUES THAT REQUIRE NO PARAMETERS TO HAVE NONE
    for a in range(len(listToProcess)):
        if listToProcess[a].find("--silent") != -1:
            listToProcess[a] = "--silent"
        elif listToProcess[a].find("--cli") != -1:
            listToProcess[a] = "--cli"
        elif listToProcess[a].find("--html") != -1:
            listToProcess[a] = "--html"
        elif listToProcess[a].find("--discover") != -1:
            listToProcess[a] = "--discover"
        elif listToProcess[a].find("--off") != -1:
            listToProcess[a] = "--off"
        elif listToProcess[a].find("--on") != -1:
            listToProcess[a] = "--on"
        elif listToProcess[a] == "--link":
            listToProcess[a] = "--link=-1"
        elif listToProcess[a] == "--custom_name":
            listToProcess[a] = "--custom_name=-1"
        elif listToProcess[a] == "--use_preset":
            listToProcess[a] = "--use_preset=-1"
        elif listToProcess[a] == "--save_preset":
            listToProcess[a] = "--save_preset=-1"
        elif listToProcess[a] == "--batch":
            listToProcess[a] = "--batch=-1"
        elif listToProcess[a] == "--animate":
            listToProcess[a] = "--animate=-1"
        elif listToProcess[a].find("--stop_animate") != -1:
            listToProcess[a] = "--stop_animate"
        elif listToProcess[a].find("--list_animations") != -1:
            listToProcess[a] = "--list_animations"

    # PARSE THE ARGUMENT LIST FOR CUSTOM PARAMETERS
    parser = argparse.ArgumentParser()

    parser.add_argument("--list", action="store_true", help="Scan for nearby Neewer lights and list them on the CLI") # list the currently available lights
    parser.add_argument("--http", action="store_true", help="Use an HTTP server to send commands to Neewer lights using a web browser")
    parser.add_argument("--silent", action="store_false", help="Don't show any debug information in the console")
    parser.add_argument("--cli", action="store_false", help="Don't show the GUI at all, just send command to one light and quit")
    parser.add_argument("--force_instance", action="store_false", help="Force a new instance of NeewerLux if another one is already running")

    # HTML SERVER SPECIFIC PARAMETERS
    if inStartupMode == False:
        parser.add_argument("--custom_name", default=-1) # a new custom name for the light
        parser.add_argument("--discover", action="store_true") # tell the HTTP server to search for newly added lights
        parser.add_argument("--link", default=-1) # link a specific light to NeewerLux
        parser.add_argument("--nopage", action="store_false") # don't render an HTML page
        parser.add_argument("--use_preset", default=-1) # number of custom preset to use via the HTTP interface
        parser.add_argument("--save_preset", default=-1) # option to save a custom snapshot preset via the HTTP interface
        parser.add_argument("--add_preset", action="store_true") # add a new preset slot
        parser.add_argument("--delete_preset", default=-1) # delete a specific preset by index
        parser.add_argument("--batch", default=-1) # send different commands to different lights simultaneously
        parser.add_argument("--animate", default=-1) # play a saved animation by name
        parser.add_argument("--stop_animate", action="store_true") # stop the currently running animation
        parser.add_argument("--list_animations", action="store_true") # list available animations

    parser.add_argument("--on", action="store_true", help="Turn the light on")
    parser.add_argument("--off", action="store_true", help="Turn the light off")
    parser.add_argument("--light", default="", help="The MAC Address (XX:XX:XX:XX:XX:XX) of the light you want to send a command to or ALL to find and control all lights (only valid when also using --cli switch)")
    parser.add_argument("--mode", default="CCT", help="[DEFAULT: CCT] The current control mode - options are HSI, CCT and either ANM or SCENE")
    parser.add_argument("--temp", "--temperature", default="56", help="[DEFAULT: 56(00)K] (CCT mode) - the color temperature (3200K+) to set the light to")
    parser.add_argument("--hue", default="240", help="[DEFAULT: 240] (HSI mode) - the hue (0-360 degrees) to set the light to")
    parser.add_argument("--sat", "--saturation", default="100", help="[DEFAULT: 100] (HSI mode) The saturation (how vibrant the color is) to set the light to")
    parser.add_argument("--bri", "--brightness", "--intensity", default="100", help="[DEFAULT: 100] (CCT/HSI/ANM mode) The brightness (intensity) to set the light to")
    parser.add_argument("--scene", "--animation", default="1", help="[DEFAULT: 1] (ANM or SCENE mode) The animation (1-9) to use in Scene mode")

    args = parser.parse_args(listToProcess)

    if args.force_instance == False: # if this value is True, then don't do anything
        global anotherInstance
        anotherInstance = False # change the global to False to allow new instances

    if args.silent == True:
        if inStartupMode == True:
            if args.list != True: # if we're not looking for lights using --list, then print line
                printDebugString("Starting program with command-line arguments")
        else:
            printDebugString("Processing HTTP arguments")
            args.cli = False # we're running the CLI, so don't initialize the GUI
            args.silent = printDebug # we're not changing the silent flag, pass on the current printDebug setting

    if args.http == True:
        return ["HTTP", args.silent] # special mode - don't do any other mode/color/etc. processing, just jump into running the HTML server

    if inStartupMode == False:
        # HTTP specific parameter returns!
        if args.custom_name != -1:
            return [None, args.nopage, args.custom_name, "custom_name"] # rename one of the lights with a new name (| delimited)

        if args.discover == True:
            return[None, args.nopage, None, "discover"] # discover new lights

        if args.link != -1:
            return[None, args.nopage, args.link, "link"] # return the value defined by the parameter

        if args.list == True:
            return [None, args.nopage, None, "list"]

        if args.use_preset != -1:
            return[None, args.nopage, testValid("use_preset", int(args.use_preset), 1, 1, numOfPresets), "use_preset"]

        if args.save_preset != -1:
            return[None, args.nopage, testValid("save_preset", int(args.save_preset), 1, 1, numOfPresets), "save_preset"]

        if args.add_preset == True:
            return[None, args.nopage, None, "add_preset"]

        if args.delete_preset != -1:
            return[None, args.nopage, int(args.delete_preset), "delete_preset"]

        if args.batch != -1:
            return[None, args.nopage, args.batch, "batch"]

        if args.animate != -1:
            return[None, args.nopage, urllib.parse.unquote(str(args.animate)), "animate"]

        if args.stop_animate == True:
            return[None, args.nopage, None, "stop_animate"]

        if args.list_animations == True:
            return[None, args.nopage, None, "list_animations"]
    else:
        # If we request "LIST" from the CLI, then return a CLI list of lights available
        if args.list == True:
            return["LIST", False]

    # CHECK TO SEE IF THE LIGHT SHOULD BE TURNED OFF
    if args.on == True: # we want to turn the light on
        return [args.cli, args.silent, args.light, "ON"]
    elif args.off == True: # we want to turn the light off
        return [args.cli, args.silent, args.light, "OFF"]

    # IF THE LIGHT ISN'T BEING TURNED OFF, CHECK TO SEE IF MODES ARE BEING SET
    if args.mode.lower() == "hsi":
        return [args.cli, args.silent, args.light, "HSI",
                testValid("hue", args.hue, 240, 0, 360),
                testValid("sat", args.sat, 100, 0, 100),
                testValid("bri", args.bri, 100, 0, 100)]
    elif args.mode.lower() in ("anm", "scene"):
        return [args.cli, args.silent, args.light, "ANM",
                testValid("scene", args.scene, 1, 1, 9),
                testValid("bri", args.bri, 100, 0, 100)]
    else: # we've either asked for CCT mode, or gave an invalid mode name
        if args.mode.lower() != "cct": # if we're not actually asking for CCT mode, display error message
            printDebugString(" >> Improper mode selected with --mode command - valid entries are")
            printDebugString(" >> CCT, HSI or either ANM or SCENE, so rolling back to CCT mode.")

        # RETURN CCT MODE PARAMETERS IN CCT/ALL OTHER CASES
        return [args.cli, args.silent, args.light, "CCT",
                testValid("temp", args.temp, 56, 32, 85),
                testValid("bri", args.bri, 100, 0, 100)]

def processHTMLCommands(paramsList, loop):
    """Process HTTP commands by queuing work for the worker thread.
    
    CRITICAL: This function runs on the HTTP server thread.  It must NEVER call
    asyncioEventLoop.run_until_complete() directly — that crashes when the worker
    thread is already using the event loop.  Instead, all BLE operations are
    queued via the global threadAction variable, which the worker thread polls.
    """
    global threadAction, numOfPresets, defaultLightPresets, customLightPresets

    # Wait briefly if worker is busy — BLE writes can take a few seconds
    for _retry in range(20):  # up to 5 seconds
        if threadAction in ("", "HTTP"):
            break
        time.sleep(0.25)
    
    if threadAction not in ("", "HTTP"):
        printDebugString("The HTTP Server requested an action, but the worker thread is busy (" + threadAction + ") after waiting. Skipping.")
        return

    if len(paramsList) == 0:
        return

    # Stop any running animation for non-animation HTTP commands
    if paramsList[3] not in ("animate", "stop_animate", "list_animations") and animationRunning:
        stopAnimation()
        try:
            if mainWindow is not None: mainWindow.animPlayButton.setEnabled(True)
            if mainWindow is not None: mainWindow.animStopButton.setEnabled(False)
            if mainWindow is not None: mainWindow.animStatusLabel.setText("Stopped")
        except Exception:
            pass

    if paramsList[3] == "discover":
        # Queue discovery — worker thread handles "discover" natively (including auto-connect)
        threadAction = "discover"

    elif paramsList[3] == "link":
        selectedLights = returnLightIndexesFromMacAddress(paramsList[2])
        if len(selectedLights) > 0:
            # Queue connection via a special threadAction the worker thread handles
            threadAction = "httplink|" + "|".join(map(str, selectedLights))

    elif paramsList[3] == "use_preset":
        recallCustomPreset(paramsList[2] - 1, False, loop)

    elif paramsList[3] == "save_preset":
        presetIdx = paramsList[2] - 1
        if 0 <= presetIdx < numOfPresets:
            saveCustomPreset("snapshot", presetIdx)
            try:
                if mainWindow is not None: mainWindow._savePresetsQuick()
            except Exception:
                pass
            printDebugString("HTTP: Saved snapshot preset " + str(presetIdx + 1))

    elif paramsList[3] == "add_preset":
        numOfPresets += 1
        defaultLightPresets.append(getDefaultPreset(numOfPresets - 1))
        customLightPresets.append(getDefaultPreset(numOfPresets - 1))
        try:
            if mainWindow is not None: mainWindow.createPresetButtons()
            if mainWindow is not None: mainWindow._savePresetsQuick()
        except Exception:
            pass
        printDebugString("HTTP: Added preset #" + str(numOfPresets))

    elif paramsList[3] == "delete_preset":
        presetIdx = paramsList[2] - 1
        if 0 <= presetIdx < numOfPresets and numOfPresets > 1:
            customLightPresets.pop(presetIdx)
            defaultLightPresets.pop(presetIdx)
            newNames = {}
            for k, v in presetNames.items():
                if k < presetIdx: newNames[k] = v
                elif k > presetIdx: newNames[k - 1] = v
            presetNames.clear()
            presetNames.update(newNames)
            numOfPresets -= 1
            try:
                if mainWindow is not None: mainWindow.createPresetButtons()
                if mainWindow is not None: mainWindow._savePresetsQuick()
            except Exception:
                pass
            printDebugString("HTTP: Deleted preset " + str(presetIdx + 1))

    elif paramsList[3] == "batch":
        processBatchCommands(paramsList[2], loop)

    elif paramsList[3] == "animate":
        animName = paramsList[2]
        if animName and animName != "-1":
            speedMult = 1.0
            fps = 5
            briScale = 1.0
            loopOverride = None
            maxLoops = 0
            revertOverride = None
            if "|" in animName:
                parts = animName.split("|")
                animName = parts[0]
                try: speedMult = float(parts[1])
                except (ValueError, IndexError): pass
                try: fps = int(parts[2])
                except (ValueError, IndexError): pass
                try: briScale = int(parts[3]) / 100.0
                except (ValueError, IndexError): pass
                # Extended parameters: loop, maxLoops, revert
                try:
                    loopVal = parts[4].strip().lower()
                    if loopVal in ("1", "true", "yes", "on"):
                        loopOverride = True
                    elif loopVal in ("0", "false", "no", "off"):
                        loopOverride = False
                except IndexError: pass
                try: maxLoops = int(parts[5])
                except (ValueError, IndexError): pass
                try:
                    revertVal = parts[6].strip().lower()
                    if revertVal in ("1", "true", "yes", "on"):
                        revertOverride = True
                    elif revertVal in ("0", "false", "no", "off"):
                        revertOverride = False
                except IndexError: pass
            # Apply revert override if specified
            if revertOverride is not None:
                global animRevertOnFinish
                animRevertOnFinish = revertOverride
            startAnimation(animName, loop, speedMult, loopOverride=loopOverride, fps=fps, briScale=briScale, maxLoops=maxLoops)
        else:
            printDebugString("HTTP: no animation name specified")

    elif paramsList[3] == "stop_animate":
        stopAnimation()

    elif paramsList[3] == "list_animations":
        pass  # handled in the HTML rendering section

    elif paramsList[3] == "custom_name":
        if paramsList[2] != "-1":
            nameInfo = paramsList[2].split("|")
            if len(nameInfo) > 1:
                nameInfo[0] = int(nameInfo[0])
                nameInfo[1] = urllib.parse.unquote(nameInfo[1])
                availableLights[nameInfo[0]][2] = nameInfo[1]
                saveLightPrefs(nameInfo[0])
                loadLightAliases()

    else:
        # CCT / HSI / ANM / ON / OFF — compute bytestring, store on lights, queue send
        if paramsList[3] == "CCT":
            computedValue = calculateByteString(True, colorMode=paramsList[3], temp=paramsList[4], brightness=paramsList[5])
        elif paramsList[3] == "HSI":
            computedValue = calculateByteString(True, colorMode=paramsList[3], HSI_H=paramsList[4], HSI_S=paramsList[5], HSI_I=paramsList[6])
        elif paramsList[3] == "ANM":
            computedValue = calculateByteString(True, colorMode=paramsList[3], animation=paramsList[4], brightness=paramsList[5])
        elif paramsList[3] == "ON":
            computedValue = [120, 129, 1, 1, 251]
        elif paramsList[3] == "OFF":
            computedValue = [120, 129, 1, 2, 252]
        else:
            printDebugString("HTTP: Unknown mode '" + paramsList[3] + "'")
            return

        selectedLights = returnLightIndexesFromMacAddress(paramsList[2])

        if len(selectedLights) > 0:
            # Store computed value in each target light's parameter slot
            for lightIdx in selectedLights:
                if lightIdx < len(availableLights):
                    availableLights[lightIdx][3] = computedValue

            # Queue the send via worker thread (parallel write)
            threadAction = "psend|" + "|".join(map(str, selectedLights))

def reorderByPreferredID():
    """Reorder availableLights so lights with preferred IDs come first (in ID order),
    followed by lights without preferred IDs (in their original discovery order).

    This ensures the GUI row numbers match the preferred IDs as closely as possible.
    For example, if lights have preferred IDs 1, 2, 3, 4, they will appear as
    rows 1, 2, 3, 4 in the table.
    """
    global availableLights

    if len(availableLights) <= 1:
        return

    withPrefID = []   # (preferredID, light)
    withoutPrefID = [] # (originalIndex, light)

    for i, light in enumerate(availableLights):
        prefID = light[8] if len(light) > 8 else 0
        if prefID > 0:
            withPrefID.append((prefID, light))
        else:
            withoutPrefID.append((i, light))

    # Sort preferred-ID lights by their ID
    withPrefID.sort(key=lambda x: x[0])

    # Rebuild: preferred-ID lights first, then discovery-order lights
    availableLights.clear()
    for _, light in withPrefID:
        availableLights.append(light)
    for _, light in withoutPrefID:
        availableLights.append(light)


def returnLightIndexesFromMacAddress(addresses):
    """Resolve light addresses/IDs/names to availableLights indices.

    Accepts:
      "*"           → all connected lights
      "1" or "2"    → numeric ID (alias-aware: if aliases define id=1 for a MAC,
                       that MAC is used regardless of discovery order)
      "Key"         → alias name (from custom name in Light Preferences)
      "D0:A8:..."   → MAC address
      "1;2;Key"     → semicolon-separated mix of the above
    """
    foundIndexes = []

    if addresses == "*" or addresses == "-1" or addresses.lower() == "all":
        for a in range(len(availableLights)):
            foundIndexes.append(a)
        return foundIndexes

    # Build reverse lookup tables from aliases
    aliasNameToMAC = {}   # {"key": "D0:A8:..."} (lowercase name → MAC)
    aliasIDToMAC = {}     # {1: "D0:A8:..."} (numeric id → MAC)
    for mac, info in lightAliases.items():
        if info.get("name"):
            aliasNameToMAC[info["name"].lower()] = mac.upper()
        if info.get("id", 0) > 0:
            aliasIDToMAC[info["id"]] = mac.upper()

    addressesToCheck = addresses.split(";")

    for addr in addressesToCheck:
        addr = addr.strip()
        if not addr:
            continue

        resolvedMAC = None

        # Try alias name match first (case-insensitive)
        if addr.lower() in aliasNameToMAC:
            resolvedMAC = aliasNameToMAC[addr.lower()]
        else:
            try:
                numericID = int(addr)
                # If aliases define a fixed ID mapping, use it
                if numericID in aliasIDToMAC:
                    resolvedMAC = aliasIDToMAC[numericID]
                else:
                    # No alias for this ID — fall back to discovery order (1-based)
                    idx = numericID - 1
                    if 0 <= idx < len(availableLights):
                        foundIndexes.append(idx)
                    continue
            except ValueError:
                # Not a number — try as MAC address
                resolvedMAC = addr.upper()

        # Resolve MAC to availableLights index
        if resolvedMAC:
            for b in range(len(availableLights)):
                if resolvedMAC == availableLights[b][0].address.upper():
                    foundIndexes.append(b)
                    break

    return foundIndexes

# ============================================================================
# BATCH COMMAND PROCESSING - send different commands to different lights at once
# ============================================================================

def parseBatchString(batchString):
    """Parse a GET-style batch string into a list of command dicts.

    Format: light:mode:p1:p2[:p3][;light:mode:p1:p2[:p3]]...
    Examples:
        1:HSI:0:100:50;2:HSI:240:100:50     (two lights, HSI mode)
        1:CCT:56:80;2:OFF;3:ON              (mixed modes including on/off)
        *:CCT:56:80                          (all lights, same command)

    Returns a list of dicts: [{"light": "1", "mode": "HSI", "hue": 0, ...}, ...]
    """
    commands = []
    segments = urllib.parse.unquote(batchString).split(";")

    for seg in segments:
        parts = seg.strip().split(":")

        # Handle MAC addresses: if we see lots of colons, the first 6 parts are a MAC
        # MAC format: XX:XX:XX:XX:XX:XX:MODE:params...
        # Simple format: lightIndex:MODE:params...
        if len(parts) < 2:
            printDebugString("Batch: skipping malformed segment '" + seg + "'")
            continue

        # Detect if this is a MAC address (6+ colon-separated hex pairs before the mode)
        isMac = False
        if len(parts) >= 8:  # at least 6 MAC octets + mode + 1 param
            try:
                for i in range(6):
                    int(parts[i], 16)
                isMac = True
            except ValueError:
                pass

        if isMac:
            lightId = ":".join(parts[0:6])  # reassemble the MAC address
            modeParts = parts[6:]
        else:
            lightId = parts[0]
            modeParts = parts[1:]

        mode = modeParts[0].upper() if modeParts else ""
        params = modeParts[1:] if len(modeParts) > 1 else []

        cmd = {"light": lightId, "mode": mode}

        if mode == "CCT":
            cmd["temp"] = int(params[0]) if len(params) > 0 else 56
            cmd["bri"] = int(params[1]) if len(params) > 1 else 100
            # Handle full temp values (e.g. 5600 -> 56)
            if cmd["temp"] > 100:
                cmd["temp"] = cmd["temp"] // 100
        elif mode == "HSI":
            cmd["hue"] = int(params[0]) if len(params) > 0 else 240
            cmd["sat"] = int(params[1]) if len(params) > 1 else 100
            cmd["bri"] = int(params[2]) if len(params) > 2 else 100
        elif mode in ("ANM", "SCENE"):
            cmd["mode"] = "ANM"
            cmd["scene"] = int(params[0]) if len(params) > 0 else 1
            cmd["bri"] = int(params[1]) if len(params) > 1 else 100
        elif mode == "ON" or mode == "OFF":
            pass  # no extra params needed
        else:
            printDebugString("Batch: unknown mode '" + mode + "' in segment '" + seg + "'")
            continue

        commands.append(cmd)

    return commands


def processBatchCommands(batchInput, loop):
    """Execute a batch of per-light commands.

    batchInput can be:
        - A string in GET batch format (parsed by parseBatchString)
        - A list of command dicts (from POST JSON)

    Each command dict: {"light": "1", "mode": "HSI", "hue": 240, "sat": 100, "bri": 50}
    """
    global availableLights

    if isinstance(batchInput, str):
        commands = parseBatchString(batchInput)
    else:
        commands = batchInput

    if not commands:
        printDebugString("Batch: no valid commands to process")
        return {"success": False, "error": "No valid commands to process", "results": []}

    printDebugString("Batch: processing " + str(len(commands)) + " command(s)")

    changedLights = []  # track which light indices we've set up
    results = []  # per-command results for JSON response

    for cmd in commands:
        lightId = str(cmd.get("light", ""))
        mode = cmd.get("mode", "").upper()

        # Resolve light identifier to indices
        selectedLights = returnLightIndexesFromMacAddress(lightId)

        if not selectedLights:
            printDebugString("Batch: could not resolve light '" + lightId + "'")
            results.append({"light": lightId, "mode": mode, "status": "error", "error": "Light not found"})
            continue

        # Compute the byte string for this command
        try:
            if mode == "ON":
                byteVal = [120, 129, 1, 1, 251]  # power on
            elif mode == "OFF":
                byteVal = [120, 129, 1, 2, 252]  # power off
            elif mode == "CCT":
                temp = max(32, min(85, int(cmd.get("temp", 56))))
                bri = max(0, min(100, int(cmd.get("bri", 100))))
                byteVal = calculateByteString(True, colorMode="CCT", brightness=bri, temp=temp)
            elif mode == "HSI":
                hue = max(0, min(360, int(cmd.get("hue", 240))))
                sat = max(0, min(100, int(cmd.get("sat", 100))))
                bri = max(0, min(100, int(cmd.get("bri", 100))))
                byteVal = calculateByteString(True, colorMode="HSI", HSI_H=hue, HSI_S=sat, HSI_I=bri)
            elif mode == "ANM":
                scene = max(1, min(9, int(cmd.get("scene", 1))))
                bri = max(0, min(100, int(cmd.get("bri", 100))))
                byteVal = calculateByteString(True, colorMode="ANM", animation=scene, brightness=bri)
            else:
                printDebugString("Batch: skipping unknown mode '" + mode + "'")
                results.append({"light": lightId, "mode": mode, "status": "error", "error": "Unknown mode"})
                continue
        except (ValueError, TypeError) as e:
            printDebugString("Batch: parameter error for light '" + lightId + "': " + str(e))
            results.append({"light": lightId, "mode": mode, "status": "error", "error": str(e)})
            continue

        # Store the computed value into each target light's parameter slot
        for lightIdx in selectedLights:
            if lightIdx < len(availableLights):
                availableLights[lightIdx][3] = byteVal
                if lightIdx not in changedLights:
                    changedLights.append(lightIdx)
                printDebugString("Batch: light " + str(lightIdx + 1) + " -> " + mode + " " + str(byteVal))

        results.append({"light": lightId, "mode": mode, "status": "ok", "targets": len(selectedLights)})

    # Now queue all changed lights for the worker thread to send
    if changedLights:
        printDebugString("Batch: queuing send to " + str(len(changedLights)) + " light(s)")
        global threadAction
        threadAction = "psend|" + "|".join(map(str, changedLights))

    return {"success": True, "commands_processed": len(commands), "lights_updated": len(changedLights), "results": results}


# ============================================================================
# CCT-ONLY FALLBACK CONVERSION
# ============================================================================

def hsiToCCTByteVal(hue, sat, bri):
    """Convert HSI parameters to a CCT byte value for CCT-only lights.
    Maps hue to warm/cool temperature: warm colors → low temp, cool → high temp."""
    cctMin = globalCCTMin // 100
    cctMax = globalCCTMax // 100
    if hue <= 60 or hue >= 300:
        temp = cctMin  # warm
    elif 60 < hue <= 150:
        temp = cctMin + int((hue - 60) / 90 * (cctMax - cctMin) * 0.5)
    elif 150 < hue <= 250:
        temp = (cctMin + cctMax) // 2 + int((hue - 150) / 100 * (cctMax - (cctMin + cctMax) // 2))
    else:
        temp = (cctMin + cctMax) // 2
    temp = max(cctMin, min(cctMax, temp))
    return calculateByteString(True, colorMode="CCT", brightness=max(0, min(100, int(bri))), temp=temp)


def getEffectiveCCTRange(lightIdx=None):
    """Get the effective CCT range for a light. Per-light overrides global.
    Returns (minK, maxK) in Kelvin (e.g. 3200, 5600)."""
    if lightIdx is not None and lightIdx < len(availableLights):
        lightRange = availableLights[lightIdx][4]
        defaultRange = getLightSpecs(availableLights[lightIdx][0].name, "temp")
        if lightRange != defaultRange:
            # Per-light custom range set — use it
            return (lightRange[0], lightRange[1])
    return (globalCCTMin, globalCCTMax)


def clampCCTForLight(lightIdx, tempValue):
    """Clamp a CCT temperature value (32-85 range) to a light's effective range.
    Returns clamped value or None if cctFallbackMode is 'ignore' and out of range."""
    minK, maxK = getEffectiveCCTRange(lightIdx)
    minVal = minK // 100
    maxVal = maxK // 100
    if minVal <= tempValue <= maxVal:
        return tempValue  # in range
    if cctFallbackMode == "convert":
        return max(minVal, min(maxVal, tempValue))  # clamp
    else:  # ignore
        return None  # out of range, skip

def applyCCTFallback(lightIdx, byteVal, mode=None, hue=0, bri=100):
    """Check if a light is CCT-only and apply fallback based on cctFallbackMode.
    Returns the (possibly converted) byte value, or None if the command should be skipped."""
    if lightIdx >= len(availableLights) or availableLights[lightIdx][5] != True:
        return byteVal  # not CCT-only, pass through

    # Check if the byte value is an HSI or ANM command
    isModeIncompat = False
    if byteVal and len(byteVal) > 1:
        if byteVal[1] == 134 or byteVal[1] == 136:  # 134=HSI, 136=ANM
            isModeIncompat = True
    if mode and mode.upper() in ("HSI", "ANM"):
        isModeIncompat = True

    if not isModeIncompat:
        return byteVal  # compatible command, pass through

    if cctFallbackMode == "ignore":
        return None  # skip this light
    elif cctFallbackMode == "convert":
        try:
            if mode and mode.upper() == "HSI":
                return hsiToCCTByteVal(hue, 100, bri)
            elif byteVal and len(byteVal) > 6 and byteVal[1] == 134:
                # Extract HSI values from the byte array
                h = byteVal[3] + (byteVal[4] << 8)
                b = byteVal[6] if len(byteVal) > 6 else 100
                return hsiToCCTByteVal(h, 100, b)
            else:
                # ANM or unknown — use neutral temp at the specified brightness
                b = byteVal[3] if byteVal and len(byteVal) > 3 else 50
                return calculateByteString(True, colorMode="CCT", brightness=max(0, min(100, b)), temp=45)
        except Exception:
            return None  # conversion failed, skip
    return byteVal  # unknown mode, pass through


# ============================================================================
# CUSTOM ANIMATION ENGINE
# ============================================================================

def interpolateHSI(start, end, t):
    """Interpolate between two HSI tuples (hue, sat, bri) at fraction t (0.0-1.0).
    Hue interpolation takes the shortest path around the 360-degree wheel."""
    h1, s1, b1 = start
    h2, s2, b2 = end

    # Shortest path hue interpolation
    diff = (h2 - h1 + 540) % 360 - 180  # wrap to [-180, 180]
    hue = (h1 + diff * t) % 360

    sat = s1 + (s2 - s1) * t
    bri = b1 + (b2 - b1) * t

    return (int(hue), int(sat), int(bri))


def interpolateCCT(start, end, t):
    """Interpolate between two CCT tuples (temp, bri) at fraction t."""
    t1, b1 = start
    t2, b2 = end
    return (int(t1 + (t2 - t1) * t), int(b1 + (b2 - b1) * t))


def animationSendFrame(frameCommands, loop):
    """Set byte values on lights and signal the worker thread to send them.
    Does NOT call any async functions or touch the event loop directly.
    Just sets values and lets the worker thread do the actual BLE writes."""
    global threadAction

    # Compute byte values for each light
    changedLights = []
    for cmd in frameCommands:
        lightId = str(cmd.get("light", ""))
        mode = cmd.get("mode", "").upper()
        selectedLights = returnLightIndexesFromMacAddress(lightId)

        if not selectedLights:
            continue

        try:
            if mode == "ON":
                byteVal = [120, 129, 1, 1, 251]
            elif mode == "OFF":
                byteVal = [120, 129, 1, 2, 252]
            elif mode == "CCT":
                temp = max(32, min(85, int(cmd.get("temp", 56))))
                bri = max(0, min(100, int(cmd.get("bri", 100))))
                byteVal = calculateByteString(True, colorMode="CCT", brightness=bri, temp=temp)
            elif mode == "HSI":
                hue = max(0, min(360, int(cmd.get("hue", 240))))
                sat = max(0, min(100, int(cmd.get("sat", 100))))
                bri = max(0, min(100, int(cmd.get("bri", 100))))
                byteVal = calculateByteString(True, colorMode="HSI", HSI_H=hue, HSI_S=sat, HSI_I=bri)
            elif mode == "ANM":
                scene = max(1, min(9, int(cmd.get("scene", 1))))
                bri = max(0, min(100, int(cmd.get("bri", 100))))
                byteVal = calculateByteString(True, colorMode="ANM", animation=scene, brightness=bri)
            else:
                continue
        except (ValueError, TypeError):
            continue

        for lightIdx in selectedLights:
            if lightIdx < len(availableLights):
                # Apply CCT-only fallback using shared helper
                actualByteVal = applyCCTFallback(lightIdx, byteVal, mode=mode,
                                                 hue=cmd.get("hue", 240), bri=cmd.get("bri", 100))
                if actualByteVal is None:
                    continue  # ignore mode — skip this light
                availableLights[lightIdx][3] = actualByteVal
                if lightIdx not in changedLights:
                    changedLights.append(lightIdx)

    if not changedLights:
        return

    # Wait for the worker thread to be free (up to 2 seconds with 10ms granularity)
    for _ in range(200):
        if threadAction == "" or threadAction == "finished":
            break
        time.sleep(0.01)
    else:
        printDebugString("Animation frame dropped: worker busy")
        return  # worker is still busy — drop this frame (logged, not silent)

    # Signal the worker thread and return immediately — do NOT wait for completion.
    # The next call's "wait for free" check handles sequencing.
    if animParallelWrites:
        threadAction = "psend|" + "|".join(map(str, changedLights))
    else:
        threadAction = "send|" + "|".join(map(str, changedLights))
    workerWakeEvent.set()


def animationEngineThread(animation, loop, speedMultiplier=1.0, loopOverride=None, fps=5, briScale=1.0, maxLoops=0):
    """Main animation playback thread. Runs keyframes with timing and interpolation.
    maxLoops: 0 = infinite (if shouldLoop), N>0 = play exactly N times then stop."""
    global animationRunning, animationStopFlag, currentAnimationName, preAnimationStates, threadAction, _animChainStop

    animationRunning = True
    animationStopFlag = False
    shouldLoop = loopOverride if loopOverride is not None else animation.get("loop", False)
    keyframes = animation.get("keyframes", [])
    animName = animation.get("name", "Untitled")
    currentAnimationName = animName
    stepInterval = max(33, int(1000 / max(1, fps)))
    completedLoops = 0
    userStopped = False  # ms between interpolation steps (min ~30 FPS cap)

    if not keyframes:
        printDebugString("Animation '" + animName + "' has no keyframes")
        animationRunning = False
        currentAnimationName = ""
        return

    printDebugString("Animation '" + animName + "' starting (" + str(len(keyframes)) + " keyframes, loop=" + str(shouldLoop) + ", speed=" + str(speedMultiplier) + "x, rate=" + str(fps) + "/s, bri=" + str(int(briScale * 100)) + "%)")

    frameIndex = 0
    totalFrames = len(keyframes)
    prevFrameIndex = -1  # tracks previous frame for fade interpolation (-1 = none yet)
    lastGUIUpdate = 0  # throttle GUI updates to avoid cross-thread blocking

    try:
        while not animationStopFlag:
            keyframe = keyframes[frameIndex]
            hold_ms = keyframe.get("hold_ms", 200)
            fade_ms = keyframe.get("fade_ms", 0)
            lights = keyframe.get("lights", {})

            # Apply speed multiplier to timing
            hold_ms = max(50, int(hold_ms / speedMultiplier))
            fade_ms = max(0, int(fade_ms / speedMultiplier))

            # For looping animations: if we just wrapped around to frame 0 from the last frame
            # and frame 0 has fade_ms=0, auto-apply a fade using the last keyframe's fade_ms.
            # This makes loops seamless without requiring the user to set fade on the first frame.
            if frameIndex == 0 and prevFrameIndex == totalFrames - 1 and fade_ms == 0 and shouldLoop:
                lastFade = keyframes[-1].get("fade_ms", 0)
                if lastFade > 0:
                    fade_ms = max(0, int(lastFade / speedMultiplier))

            # Update GUI status (throttled to max once per second to avoid
            # cross-thread Qt blocking that causes animation stutters)
            now = time.time()
            if now - lastGUIUpdate >= 1.0:
                lastGUIUpdate = now
                try:
                    if mainWindow is not None:
                        if mainWindow is not None: mainWindow.animStatusLabel.setText("Playing: " + animName + "\nFrame " + str(frameIndex + 1) + "/" + str(totalFrames))
                except Exception:
                    pass

            # === FADE TRANSITION (if fade_ms > 0 and we have a previous frame) ===
            if fade_ms > 0 and prevFrameIndex >= 0:
                prevLights = keyframes[prevFrameIndex].get("lights", {})
                steps = max(1, fade_ms // stepInterval)

                for step in range(steps):
                    if animationStopFlag:
                        break
                    t = (step + 1) / steps
                    frameCommands = []

                    for lightKey, targetParams in lights.items():
                        mode = targetParams.get("mode", "HSI").upper()
                        prevParams = prevLights.get(lightKey, targetParams)
                        prevMode = prevParams.get("mode", mode).upper()

                        # Only interpolate if modes match
                        if mode == prevMode and mode == "HSI":
                            h, s, b = interpolateHSI(
                                (prevParams.get("hue", 0), prevParams.get("sat", 100), prevParams.get("bri", 100)),
                                (targetParams.get("hue", 0), targetParams.get("sat", 100), targetParams.get("bri", 100)),
                                t
                            )
                            frameCommands.append({"light": lightKey, "mode": "HSI", "hue": h, "sat": s, "bri": max(0, min(100, int(b * briScale)))})
                        elif mode == prevMode and mode == "CCT":
                            temp, bri = interpolateCCT(
                                (prevParams.get("temp", 56), prevParams.get("bri", 100)),
                                (targetParams.get("temp", 56), targetParams.get("bri", 100)),
                                t
                            )
                            frameCommands.append({"light": lightKey, "mode": "CCT", "temp": temp, "bri": max(0, min(100, int(bri * briScale)))})
                        else:
                            # Can't interpolate across modes; just snap on last step
                            if step == steps - 1:
                                scaledTarget = dict(targetParams)
                                if "bri" in scaledTarget:
                                    scaledTarget["bri"] = max(0, min(100, int(scaledTarget["bri"] * briScale)))
                                frameCommands.append({"light": lightKey, **scaledTarget})

                    if frameCommands and not animationStopFlag:
                        animationSendFrame(frameCommands, loop)
                    time.sleep(stepInterval / 1000.0)

            else:
                # === INSTANT JUMP to this keyframe ===
                frameCommands = []
                for lightKey, params in lights.items():
                    scaledParams = dict(params)
                    if "bri" in scaledParams:
                        scaledParams["bri"] = max(0, min(100, int(scaledParams["bri"] * briScale)))
                    frameCommands.append({"light": lightKey, **scaledParams})

                if frameCommands and not animationStopFlag:
                    animationSendFrame(frameCommands, loop)

            # === HOLD on this keyframe ===
            holdSteps = max(1, hold_ms // 50)
            for _ in range(holdSteps):
                if animationStopFlag:
                    break
                time.sleep(0.05)

            # Advance to next keyframe
            prevFrameIndex = frameIndex
            frameIndex += 1
            if frameIndex >= totalFrames:
                completedLoops += 1
                if shouldLoop and not animationStopFlag:
                    # Check maxLoops: 0 = infinite, N = stop after N loops
                    if maxLoops > 0 and completedLoops >= maxLoops:
                        break  # reached loop limit
                    frameIndex = 0  # loop back to start (prevFrameIndex stays as last frame)
                else:
                    break  # animation complete

    except Exception as e:
        printDebugString("Animation engine error: " + str(e))

    userStopped = animationStopFlag  # was this a user-initiated stop?
    animationRunning = False
    currentAnimationName = ""
    printDebugString("Animation '" + animName + "' stopped" + (" (completed " + str(completedLoops) + " loop(s))" if completedLoops > 0 else ""))

    # Revert lights to pre-animation state if enabled (both natural finish and user stop)
    # BUT NOT if we're chaining into another animation — the new animation will inherit our preAnimationStates
    if animRevertOnFinish and preAnimationStates and not _animChainStop:
        printDebugString("Reverting lights to pre-animation state")
        changedLights = []
        for lightIdx, savedState in preAnimationStates.items():
            if lightIdx < len(availableLights):
                availableLights[lightIdx][3] = savedState
                changedLights.append(lightIdx)
        if changedLights:
            threadAction = "psend|" + "|".join(map(str, changedLights))
        preAnimationStates = {}

    try:
        if mainWindow is not None:
            if mainWindow is not None: mainWindow.animStatusLabel.setText("Stopped")
            if mainWindow is not None: mainWindow.animPlayButton.setEnabled(True)
            if mainWindow is not None: mainWindow.animStopButton.setEnabled(False)
    except Exception:
        pass


def startAnimation(animName, loop, speedMultiplier=1.0, loopOverride=None, fps=5, briScale=1.0, maxLoops=0):
    """Start an animation by name. Stops any currently running animation first.
    maxLoops: 0 = use animation's loop setting, N>0 = play N times then stop."""
    global animationStopFlag, savedAnimations, preAnimationStates, _animChainStop

    # Case-insensitive name lookup — HTTP args get lowercased by the argument parser
    resolvedName = None
    for key in savedAnimations:
        if key.lower() == animName.lower():
            resolvedName = key
            break
    if resolvedName is None:
        printDebugString("Animation '" + animName + "' not found")
        return False
    animName = resolvedName

    # Stop any running animation — but remember if one was running so we preserve
    # the original pre-animation states (captured before the FIRST animation in a chain)
    wasRunning = animationRunning
    if wasRunning:
        _animChainStop = True  # tell the stopping thread: don't revert, we're chaining
    stopAnimation()
    _animChainStop = False  # reset for future non-chain stops

    # Only capture pre-animation states if we're starting fresh. If we're interrupting
    # an existing animation, light[3] would contain that animation's last keyframe values,
    # not the user's pre-animation state. Keep the original states instead.
    if not wasRunning:
        preAnimationStates = {}
        for i, light in enumerate(availableLights):
            if light[3] is not None and isinstance(light[3], list) and len(light[3]) > 0:
                preAnimationStates[i] = list(light[3])  # deep copy

    animation = savedAnimations[animName].copy()
    t = threading.Thread(target=animationEngineThread,
                         args=(animation, asyncioEventLoop, speedMultiplier, loopOverride, fps, briScale, maxLoops),
                         name="animationThread", daemon=True)
    t.start()
    return True


def stopAnimation():
    """Stop the currently running animation."""
    global animationStopFlag
    if animationRunning:
        animationStopFlag = True
        # Wait up to 2 seconds for it to actually stop
        for _ in range(40):
            if not animationRunning:
                break
            time.sleep(0.05)
        printDebugString("Animation stop requested")


# ============================================================================
# ANIMATION TEMPLATES - generate animation definitions from parameters
# ============================================================================

def templatePoliceFlash(lights=None, speed_ms=300, colors=None):
    """Alternating red/blue flash between two light groups."""
    if lights is None:
        lights = ["1", "2"]
    if colors is None:
        colors = [(0, 100, 100), (240, 100, 100)]  # red, blue as (hue, sat, bri)

    halfA = lights[:len(lights)//2] if len(lights) > 1 else lights
    halfB = lights[len(lights)//2:] if len(lights) > 1 else lights

    keyframes = [
        {
            "hold_ms": speed_ms,
            "fade_ms": 0,
            "lights": {}
        },
        {
            "hold_ms": speed_ms,
            "fade_ms": 0,
            "lights": {}
        }
    ]

    for l in halfA:
        keyframes[0]["lights"][l] = {"mode": "HSI", "hue": colors[0][0], "sat": colors[0][1], "bri": colors[0][2]}
        keyframes[1]["lights"][l] = {"mode": "HSI", "hue": colors[1][0], "sat": colors[1][1], "bri": colors[1][2]}
    for l in halfB:
        keyframes[0]["lights"][l] = {"mode": "HSI", "hue": colors[1][0], "sat": colors[1][1], "bri": colors[1][2]}
        keyframes[1]["lights"][l] = {"mode": "HSI", "hue": colors[0][0], "sat": colors[0][1], "bri": colors[0][2]}

    return {
        "name": "Police Flash",
        "description": "Alternating red/blue flash",
        "loop": True,
        "keyframes": keyframes
    }


def templateColorCycle(lights=None, step_count=12, fade_ms=500, hold_ms=100, saturation=100, brightness=100):
    """Smooth hue rotation through the full spectrum on all lights."""
    if lights is None:
        lights = ["*"]

    keyframes = []
    for i in range(step_count):
        hue = int(360 * i / step_count)
        kf = {
            "hold_ms": hold_ms,
            "fade_ms": fade_ms if i > 0 else 0,
            "lights": {}
        }
        for l in lights:
            kf["lights"][l] = {"mode": "HSI", "hue": hue, "sat": saturation, "bri": brightness}
        keyframes.append(kf)

    return {
        "name": "Color Cycle",
        "description": "Smooth hue rotation through the spectrum",
        "loop": True,
        "keyframes": keyframes
    }


def templateStrobe(lights=None, on_ms=50, off_ms=50, brightness=100):
    """Rapid on/off flash."""
    if lights is None:
        lights = ["*"]

    keyframes = [
        {"hold_ms": on_ms, "fade_ms": 0, "lights": {}},
        {"hold_ms": off_ms, "fade_ms": 0, "lights": {}}
    ]
    for l in lights:
        keyframes[0]["lights"][l] = {"mode": "HSI", "hue": 0, "sat": 0, "bri": brightness}
        keyframes[1]["lights"][l] = {"mode": "HSI", "hue": 0, "sat": 0, "bri": 0}

    return {
        "name": "Strobe",
        "description": "Rapid on/off flash",
        "loop": True,
        "keyframes": keyframes
    }


def templateBreathe(lights=None, fade_ms=1500, hold_ms=200, hue=0, sat=0, max_bri=100, min_bri=5):
    """Smooth brightness fade up and down (breathing effect)."""
    if lights is None:
        lights = ["*"]

    keyframes = [
        {"hold_ms": hold_ms, "fade_ms": fade_ms, "lights": {}},
        {"hold_ms": hold_ms, "fade_ms": fade_ms, "lights": {}}
    ]
    for l in lights:
        keyframes[0]["lights"][l] = {"mode": "HSI", "hue": hue, "sat": sat, "bri": max_bri}
        keyframes[1]["lights"][l] = {"mode": "HSI", "hue": hue, "sat": sat, "bri": min_bri}

    return {
        "name": "Breathe",
        "description": "Smooth brightness fade up and down",
        "loop": True,
        "keyframes": keyframes
    }


def templateColorWash(lights=None, colors=None, fade_ms=2000, hold_ms=1000):
    """Slow transition through a list of specified colors."""
    if lights is None:
        lights = ["*"]
    if colors is None:
        colors = [(0, 100, 100), (60, 100, 100), (120, 100, 100), (180, 100, 100), (240, 100, 100), (300, 100, 100)]

    keyframes = []
    for i, (hue, sat, bri) in enumerate(colors):
        kf = {
            "hold_ms": hold_ms,
            "fade_ms": fade_ms if i > 0 else 0,
            "lights": {}
        }
        for l in lights:
            kf["lights"][l] = {"mode": "HSI", "hue": hue, "sat": sat, "bri": bri}
        keyframes.append(kf)

    return {
        "name": "Color Wash",
        "description": "Slow transition through colors",
        "loop": True,
        "keyframes": keyframes
    }


def templateRainbowChase(lights=None, step_ms=300, fade_ms=200, saturation=100, brightness=100):
    """Staggered color cycle across multiple lights (each offset in hue)."""
    if lights is None:
        lights = ["1", "2"]

    numLights = len(lights)
    step_count = max(6, numLights * 3)
    keyframes = []

    for i in range(step_count):
        kf = {
            "hold_ms": step_ms,
            "fade_ms": fade_ms if i > 0 else 0,
            "lights": {}
        }
        for idx, l in enumerate(lights):
            hueOffset = int(360 * idx / numLights)
            hue = (int(360 * i / step_count) + hueOffset) % 360
            kf["lights"][l] = {"mode": "HSI", "hue": hue, "sat": saturation, "bri": brightness}
        keyframes.append(kf)

    return {
        "name": "Rainbow Chase",
        "description": "Staggered color cycle across lights",
        "loop": True,
        "keyframes": keyframes
    }


ANIMATION_TEMPLATES = {
    "Police Flash": templatePoliceFlash,
    "Color Cycle": templateColorCycle,
    "Strobe": templateStrobe,
    "Breathe": templateBreathe,
    "Color Wash": templateColorWash,
    "Rainbow Chase": templateRainbowChase
}


# ============================================================================
# ANIMATION FILE I/O
# ============================================================================

def ensureAnimationsDir():
    """Create the animations directory if it doesn't exist."""
    try:
        os.makedirs(animationsDir, exist_ok=True)
    except OSError as e:
        printDebugString("Could not create animations directory: " + str(e))


def saveAnimationToFile(animation):
    """Save an animation dict to a JSON file."""
    ensureAnimationsDir()
    name = animation.get("name", "Untitled")
    safeName = "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip()
    filePath = animationsDir + os.sep + safeName + ".json"

    try:
        with open(filePath, "w", encoding="utf-8") as f:
            json.dump(animation, f, indent=2)
        printDebugString("Saved animation '" + name + "' to " + filePath)
        return True
    except Exception as e:
        printDebugString("Error saving animation: " + str(e))
        return False


def loadAllAnimations():
    """Load all animation JSON files from the animations directory."""
    global savedAnimations
    savedAnimations = {}
    ensureAnimationsDir()

    try:
        for filename in sorted(os.listdir(animationsDir)):
            if filename.endswith(".json"):
                filePath = animationsDir + os.sep + filename
                try:
                    with open(filePath, "r", encoding="utf-8") as f:
                        anim = json.load(f)
                    name = anim.get("name", filename.replace(".json", ""))
                    savedAnimations[name] = anim
                    printDebugString("Loaded animation: " + name)
                except (json.JSONDecodeError, IOError) as e:
                    printDebugString("Error loading " + filename + ": " + str(e))
    except FileNotFoundError:
        pass

    printDebugString("Loaded " + str(len(savedAnimations)) + " animation(s)")


def loadLightAliases():
    """Build the light aliases table from per-light preferences sidecar files.

    Scans all sidecar files in light_prefs/ (named by MAC address without colons)
    and extracts custom names and preferred IDs. This is called at startup so
    aliases are available immediately for HTTP commands and animations.

    Prefs file format: customName|colorTempRange|onlyCCTMode[|lastSettings][|preferredID]
    """
    global lightAliases
    lightAliases = {}

    prefsDir = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep + "light_prefs"
    if not os.path.isdir(prefsDir):
        return

    for filename in os.listdir(prefsDir):
        # Sidecar files are named like D0A89E6B2084 (12 hex chars, no extension)
        if len(filename) == 12 and all(c in "0123456789ABCDEFabcdef" for c in filename):
            # Reconstruct MAC address from filename
            mac = ":".join(filename[i:i+2] for i in range(0, 12, 2)).upper()

            try:
                with open(prefsDir + os.sep + filename, mode="r", encoding="utf-8") as f:
                    fields = f.read().strip().split("|")

                customName = fields[0] if len(fields) > 0 else ""
                preferredID = 0

                # Preferred ID is in the 5th field (index 4), but if there are
                # 4 fields then [3] is lastSettings; if 5 then [4] is preferredID
                if len(fields) >= 5:
                    try:
                        preferredID = int(fields[4])
                    except (ValueError, IndexError):
                        pass
                # If there are exactly 4 fields and the 4th looks like just an int
                # (no commas), it might be a preferred ID with no lastSettings
                # But the standard format has lastSettings as comma-separated bytes
                # so this case won't arise with valid files

                if customName or preferredID > 0:
                    lightAliases[mac] = {"id": preferredID, "name": customName}
            except (IOError, OSError):
                pass

    if lightAliases:
        parts = []
        for mac, info in lightAliases.items():
            label = info["name"] if info["name"] else mac
            if info["id"] > 0:
                label += " (#" + str(info["id"]) + ")"
            parts.append(label)
        printDebugString("Loaded " + str(len(lightAliases)) + " light alias(es): " + ", ".join(parts))


def deleteAnimationFile(name):
    """Delete an animation JSON file by name."""
    safeName = "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip()
    filePath = animationsDir + os.sep + safeName + ".json"
    try:
        if os.path.exists(filePath):
            os.remove(filePath)
            printDebugString("Deleted animation file: " + filePath)
            return True
    except OSError as e:
        printDebugString("Error deleting animation: " + str(e))
    return False


class NLPythonServer(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/favicon.ico": # if favicon.ico is specified, then send a 404 error and stop processing
            try:
                self.send_error(404)
            except ConnectionAbortedError:
                printDebugString("Could not serve the error page, the HTTP server is already busy with another request.")

            return
        else:
            # CHECK THE LENGTH OF THE URL REQUEST AND SEE IF IT'S TOO LONG
            if len(self.path) > 1024: # INCREASED LENGTH TO SUPPORT BATCH COMMANDS
                # THE LAST REQUEST WAS WAY TOO LONG, SO QUICKLY RENDER AN ERROR PAGE AND RETURN FROM THE HTTP RENDERER
                writeHTMLSections(self, "httpheaders")
                writeHTMLSections(self, "htmlheaders")
                writeHTMLSections(self, "quicklinks")
                writeHTMLSections(self, "errorHelp", "The last request you provided was too long!  The NeewerLux HTTP server can only accept URL commands less than 1024 characters long.")
                writeHTMLSections(self, "quicklinks")
                writeHTMLSections(self, "htmlendheaders")

                return

            # CHECK TO SEE IF THE IP REQUESTING ACCESS IS IN THE LIST OF "acceptable_HTTP_IPs"
            clientIP = self.client_address[0] # the IP address of the machine making the request
            acceptedIP = False

            for check in range(len(acceptable_HTTP_IPs)): # check all the "accepted" IP addresses against the current requesting IP
                if acceptedIP != True: # if we haven't found the IP in the accepted list, then keep checking
                    if acceptable_HTTP_IPs[check] in clientIP:
                        acceptedIP = True # if we're good to go, then we can just move on

            # IF THE IP MAKING THE REQUEST IS NOT IN THE LIST OF APPROVED ADDRESSES, THEN RETURN A "FORBIDDEN" ERROR
            if acceptedIP == False:
                self.send_error(403, "The IP of the device you're making the request from (" + clientIP + ") has to be in the list of accepted IP addresses in order to use the NeewerLux HTTP Server, any outside addresses will generate this Forbidden error.  To use this device with NeewerLux, add its IP address (or range of IP addresses) to the list of acceptable IPs")
                return

            acceptableURL = "/NeewerLux/doAction?"
            # Accept old URL path for backward compatibility
            if "/NeewerLite-Python/" in self.path:
                self.path = self.path.replace("/NeewerLite-Python/", "/NeewerLux/")

            if not acceptableURL in self.path: # serve the modern web dashboard
                if getWebDashboardHTML is not None:
                    self.send_response(200)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "text/html;charset=UTF-8")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.end_headers()
                    self.wfile.write(getWebDashboardHTML().encode("utf-8"))
                else:
                    self.send_response(302)
                    self.send_header('Location', acceptableURL)
                    self.end_headers()

                return
            else: # if the URL contains "/NeewerLux/doAction?" then it's a valid URL
                # Check for JSON API endpoints first
                queryPart = self.path.replace(acceptableURL, "")

                # Redirect old ?list to new dashboard
                if queryPart == "list" or queryPart.startswith("list&"):
                    self.send_response(302)
                    self.send_header('Location', '/NeewerLux/')
                    self.end_headers()
                    return

                if queryPart.startswith("list_json"):
                    # Return structured JSON for the web dashboard
                    self.send_response(200)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json;charset=UTF-8")
                    self.end_headers()

                    lightsData = []
                    for idx, light in enumerate(availableLights):
                        prefID = light[8] if len(light) > 8 else 0
                        effectiveID = prefID if prefID > 0 else idx + 1
                        name = light[2] if light[2] else light[0].name
                        mac = light[0].address
                        linked = bool(light[1] != "" and hasattr(light[1], 'is_connected') and light[1].is_connected)
                        try:
                            if light[3] is not None and isinstance(light[3], list) and len(light[3]) > 3:
                                status = updateStatus(True, light[3])
                            else:
                                status = ""
                        except Exception:
                            status = ""
                        lightsData.append({"id": effectiveID, "name": name, "mac": mac,
                                           "linked": linked, "status": status,
                                           "model": light[0].name})

                    animData = []
                    for aName, aData in sorted(savedAnimations.items()):
                        # Collect unique modes used in keyframes for categorization
                        modes = set()
                        for kf in aData.get("keyframes", []):
                            for lk, lp in kf.get("lights", {}).items():
                                modes.add(lp.get("mode", "HSI").upper())
                        animData.append({"name": aName,
                                         "description": aData.get("description", ""),
                                         "frames": len(aData.get("keyframes", [])),
                                         "loop": aData.get("loop", False),
                                         "modes": sorted(modes)})

                    import json as _json
                    # Build preset data for web dashboard
                    presetsData = []
                    for i in range(numOfPresets):
                        pName = presetNames.get(i, "")
                        isCustom = (i < len(customLightPresets) and i < len(defaultLightPresets)
                                    and customLightPresets[i] != defaultLightPresets[i])
                        presetsData.append({"index": i + 1, "name": pName, "custom": isCustom})

                    result = {"lights": lightsData, "animations": animData,
                              "animationPlaying": animationRunning,
                              "currentAnimation": currentAnimationName if animationRunning else "",
                              "presets": presetsData, "numPresets": numOfPresets}
                    self.wfile.write(_json.dumps(result).encode("utf-8"))
                    return

                writeHTMLSections(self, "httpheaders")

                # BREAK THE URL INTO USABLE PARAMTERS
                paramsList = self.path.replace(acceptableURL, "").split("&") # split the included params into a list
                paramsList = processCommands(paramsList) # process the commands returned from the HTTP parameters

                if len(paramsList) == 0: # we have no valid parameters, so show the error page
                    writeHTMLSections(self, "htmlheaders")
                    writeHTMLSections(self, "quicklinks")
                    writeHTMLSections(self, "errorHelp", "You didn't provide any valid parameters in the last URL.  To send multiple parameters to NeewerLux, separate each one with a & character.")
                    writeHTMLSections(self, "quicklinks")
                    writeHTMLSections(self, "htmlendheaders")
                    return
                else:
                    if paramsList[1] == True:
                        writeHTMLSections(self, "htmlheaders") # write the HTML header section
                        writeHTMLSections(self, "quicklinks-timer") # put the quicklinks (with timer) at the top of the page

                        self.wfile.write(bytes("<H1>Request Successful!</H1>\n", "utf-8"))
                        self.wfile.write(bytes("Last Request: <EM>" + self.path + "</EM><BR>\n", "utf-8"))
                        self.wfile.write(bytes("From IP: <EM>" + clientIP + "</EM><BR><BR>\n", "utf-8"))

                    if paramsList[3] != "list":
                        if paramsList[1] == True:
                            self.wfile.write(bytes("Provided Parameters:<BR>\n", "utf-8"))

                            if len(paramsList) <= 2:
                                for a in range(len(paramsList)):
                                    self.wfile.write(bytes("&nbsp;&nbsp;" + str(paramsList[a]) + "<BR>\n", "utf-8"))
                            else:
                                if paramsList[3] == "use_preset":
                                    self.wfile.write(bytes("&nbsp;&nbsp;Preset to Use: " + str(paramsList[2]) + "<BR>\n", "utf-8"))
                                elif paramsList[3] == "save_preset":
                                    pass # TODO: implement saving presets!
                                elif paramsList[3] == "batch":
                                    self.wfile.write(bytes("&nbsp;&nbsp;Batch command: " + str(paramsList[2]) + "<BR>\n", "utf-8"))
                                elif paramsList[3] == "animate":
                                    self.wfile.write(bytes("&nbsp;&nbsp;Animation: " + str(paramsList[2]) + "<BR>\n", "utf-8"))
                                    if animationRunning:
                                        self.wfile.write(bytes("&nbsp;&nbsp;Status: <STRONG>Playing</STRONG><BR>\n", "utf-8"))
                                    else:
                                        self.wfile.write(bytes("&nbsp;&nbsp;Status: Animation not found or failed to start<BR>\n", "utf-8"))
                                elif paramsList[3] == "stop_animate":
                                    self.wfile.write(bytes("&nbsp;&nbsp;Animation stopped<BR>\n", "utf-8"))
                                elif paramsList[3] == "list_animations":
                                    self.wfile.write(bytes("<H2>Saved Animations</H2>\n", "utf-8"))
                                    if len(savedAnimations) == 0:
                                        self.wfile.write(bytes("No animations saved yet.<BR>\n", "utf-8"))
                                    else:
                                        self.wfile.write(bytes("<TABLE BORDER=1 CELLPADDING=5>\n", "utf-8"))
                                        self.wfile.write(bytes("<TR><TH>Name</TH><TH>Description</TH><TH>Frames</TH><TH>Loop</TH><TH>Actions</TH></TR>\n", "utf-8"))
                                        for aName, aData in sorted(savedAnimations.items()):
                                            desc = aData.get("description", "")
                                            frames = len(aData.get("keyframes", []))
                                            loopStr = "Yes" if aData.get("loop", False) else "No"
                                            encodedName = urllib.parse.quote(aName)
                                            self.wfile.write(bytes("<TR><TD>" + aName + "</TD><TD>" + desc + "</TD><TD>" + str(frames) + "</TD><TD>" + loopStr + "</TD>", "utf-8"))
                                            self.wfile.write(bytes("<TD><A HREF='doAction?animate=" + encodedName + "'>Play</A></TD></TR>\n", "utf-8"))
                                        self.wfile.write(bytes("</TABLE>\n", "utf-8"))
                                    if animationRunning:
                                        self.wfile.write(bytes("<BR>Currently playing: <STRONG>" + currentAnimationName + "</STRONG> ", "utf-8"))
                                        self.wfile.write(bytes("<A HREF='doAction?stop_animate'>[Stop]</A><BR>\n", "utf-8"))
                                else:
                                    self.wfile.write(bytes("&nbsp;&nbsp;Parameters: " + str(paramsList[2]) + "<BR>\n", "utf-8"))

                                self.wfile.write(bytes("&nbsp;&nbsp;Mode: " + str(paramsList[3]) + "<BR>\n", "utf-8"))

                                if paramsList[3] == "CCT":
                                    self.wfile.write(bytes("&nbsp;&nbsp;Color Temperature: " + str(paramsList[4]) + "00K<BR>\n", "utf-8"))
                                    self.wfile.write(bytes("&nbsp;&nbsp;Brightness: " + str(paramsList[5]) + "<BR>\n", "utf-8"))
                                elif paramsList[3] == "HSI":
                                    self.wfile.write(bytes("&nbsp;&nbsp;Hue: " + str(paramsList[4]) + "<BR>\n", "utf-8"))
                                    self.wfile.write(bytes("&nbsp;&nbsp;Saturation: " + str(paramsList[5]) + "<BR>\n", "utf-8"))
                                    self.wfile.write(bytes("&nbsp;&nbsp;Brightness: " + str(paramsList[6]) + "<BR>\n", "utf-8"))
                                elif paramsList[3] == "ANM" or paramsList[3] == "SCENE":
                                    self.wfile.write(bytes("&nbsp;&nbsp;Animation Scene: " + str(paramsList[4]) + "<BR>\n", "utf-8"))
                                    self.wfile.write(bytes("&nbsp;&nbsp;Brightness: " + str(paramsList[5]) + "<BR>\n", "utf-8"))
                            
                            self.wfile.write(bytes("<BR><HR><BR>\n", "utf-8"))

                        # PROCESS THE HTML COMMANDS IN ANOTHER THREAD
                        htmlProcessThread = threading.Thread(target=processHTMLCommands, args=(paramsList, asyncioEventLoop), name="htmlProcessThread")
                        htmlProcessThread.start()

                    if paramsList[1] == True: # if we've been asked to list the currently available lights, do that now
                        totalLights = len(availableLights)

                        # JAVASCRIPT CODE TO CHANGE LIGHT NAMES
                        self.wfile.write(bytes("\n<!-- JAVASCRIPT CODE TO REFRESH PAGE / CHANGE LIGHT NAMES -->\n", "utf-8"))
                        self.wfile.write(bytes("<script language='JavaScript'>\n", "utf-8"))
                        self.wfile.write(bytes("  class webTimer{\n", "utf-8"))
                        self.wfile.write(bytes("    constructor(timeOut) {\n", "utf-8"))
                        self.wfile.write(bytes("      this.isRunning = true; // set to 'running' status on creation\n", "utf-8"))
                        self.wfile.write(bytes("      this.startTime = Date.now(); // the time the timer was first created\n", "utf-8"))
                        self.wfile.write(bytes("      this.timeOut = timeOut; // how long to time down from\n", "utf-8"))
                        self.wfile.write(bytes("    }\n\n", "utf-8"))
                        self.wfile.write(bytes("    stop() { // stop running the timer\n", "utf-8"))
                        self.wfile.write(bytes("      this.isRunning = false;\n", "utf-8"))
                        self.wfile.write(bytes("    }\n\n", "utf-8"))
                        self.wfile.write(bytes("    restart() { // re-start the countdown timer\n", "utf-8"))
                        self.wfile.write(bytes("      this.isRunning = true;\n", "utf-8"))
                        self.wfile.write(bytes("      this.startTime = Date.now(); // re-initialize the counter from the current time\n", "utf-8"))
                        self.wfile.write(bytes("    }\n\n", "utf-8"))
                        self.wfile.write(bytes("    getTime() {\n", "utf-8"))
                        self.wfile.write(bytes("      if (this.isRunning) { // return the amount of time that's left until the timeout\n", "utf-8"))
                        self.wfile.write(bytes("        return Math.round(this.timeOut - (Date.now() - this.startTime) / 1000);\n", "utf-8"))
                        self.wfile.write(bytes("      }\n\n", "utf-8"))
                        self.wfile.write(bytes("      return 42; // we're paused, so return a... decent answer\n", "utf-8"))
                        self.wfile.write(bytes("    }\n", "utf-8"))
                        self.wfile.write(bytes("  }\n\n", "utf-8"))
                        self.wfile.write(bytes("  function checkPageReload(ctElapsed) {\n", "utf-8"))
                        self.wfile.write(bytes("    if (ctElapsed > 0) {\n", "utf-8"))
                        self.wfile.write(bytes("      if (ctElapsed > 1) {\n", "utf-8"))
                        self.wfile.write(bytes("        document.getElementById('refreshDisplay').innerText = 'This page will auto-refresh in ' + ctElapsed + ' seconds';\n", "utf-8"))
                        self.wfile.write(bytes("      } else {\n", "utf-8"))
                        self.wfile.write(bytes("        document.getElementById('refreshDisplay').innerText = 'This page will auto-refresh in 1 second';\n", "utf-8"))
                        self.wfile.write(bytes("      }\n", "utf-8"))
                        self.wfile.write(bytes("    } else {\n", "utf-8"))
                        self.wfile.write(bytes("      location.assign('/NeewerLux/doAction?list');\n", "utf-8"))
                        self.wfile.write(bytes("    }\n", "utf-8"))
                        self.wfile.write(bytes("  }\n\n", "utf-8"))
                        self.wfile.write(bytes("  function editLight(lightNum, lightType, previousName) {\n", "utf-8"))
                        self.wfile.write(bytes("    WT.stop(); // stop the refresh timer\n\n", "utf-8"))
                        self.wfile.write(bytes("    document.getElementById('refreshDisplay').innerText = 'You clicked on an Edit button, so the refresh timer has been stopped.';\n", "utf-8"))
                        self.wfile.write(bytes("    let newName = prompt('What do you want to call light ' + (lightNum+1) + ' (' + lightType + ')?', previousName);\n\n", "utf-8"))
                        self.wfile.write(bytes("    if (!(newName == null || newName == '' || newName == previousName)) {\n", "utf-8"))
                        self.wfile.write(bytes("      window.location.href = 'doAction?custom_name=' + lightNum + '|' + newName + '';\n", "utf-8"))
                        self.wfile.write(bytes("    } else {\n", "utf-8"))
                        self.wfile.write(bytes("      WT.restart(); // restart the countdown timer for refreshing the page\n", "utf-8"))
                        self.wfile.write(bytes("    }\n", "utf-8"))
                        self.wfile.write(bytes("  }\n\n", "utf-8"))
                        self.wfile.write(bytes("  const timeOut = 8; // the delay in seconds before the page reloads\n", "utf-8"))
                        self.wfile.write(bytes("  const WT = new webTimer(timeOut); // the timer to track the above\n\n", "utf-8"))
                        self.wfile.write(bytes("  // The check to see whether or not to refresh the page\n", "utf-8"))
                        self.wfile.write(bytes("  setInterval(() => {\n", "utf-8"))
                        self.wfile.write(bytes("    const ctElapsed = WT.getTime();\n", "utf-8"))
                        self.wfile.write(bytes("    checkPageReload(ctElapsed);\n", "utf-8"))
                        self.wfile.write(bytes("  }, 250)\n", "utf-8"))
                        self.wfile.write(bytes("</script>\n\n", "utf-8"))

                        if totalLights == 0: # there are no lights available to you at the moment!
                            self.wfile.write(bytes("NeewerLux is not currently set up with any Neewer lights.  To discover new lights, <A HREF='doAction?discover'>click here</a>.<BR>\n", "utf-8"))
                        else:
                            self.wfile.write(bytes("List of available Neewer lights:<BR><BR>\n", "utf-8"))
                            self.wfile.write(bytes("<TABLE WIDTH='98%' BORDER='1'>\n", "utf-8"))
                            self.wfile.write(bytes("  <TR>\n", "utf-8"))
                            self.wfile.write(bytes("     <TH STYLE='width:2%; text-align:left'>ID #\n", "utf-8"))
                            self.wfile.write(bytes("     <TH STYLE='width:18%; text-align:left'>Custom Name</TH>\n", "utf-8"))
                            self.wfile.write(bytes("     <TH STYLE='width:18%; text-align:left'>Light Type</TH>\n", "utf-8"))
                            self.wfile.write(bytes("     <TH STYLE='width:30%; text-align:left'>MAC Address/GUID</TH>\n", "utf-8"))
                            self.wfile.write(bytes("     <TH STYLE='width:5%; text-align:left'>RSSI</TH>\n", "utf-8"))
                            self.wfile.write(bytes("     <TH STYLE='width:5%; text-align:left'>Linked</TH>\n", "utf-8"))
                            self.wfile.write(bytes("     <TH STYLE='width:22%; text-align:left'>Last Sent Value</TH>\n", "utf-8"))
                            self.wfile.write(bytes("  </TR>\n", "utf-8"))

                            for a in range(totalLights):
                                self.wfile.write(bytes("  <TR>\n", "utf-8"))
                                self.wfile.write(bytes("     <TD STYLE='background-color:rgb(173,255,47)'>" + str(a + 1) + "</TD>\n", "utf-8")) # light ID #
                                self.wfile.write(bytes("     <TD STYLE='background-color:rgb(240,248,255)'><button onclick='editLight(" + str(a) + ", \"" + availableLights[a][0].name + "\", \"" + availableLights[a][2] + "\")'>Edit</button>&nbsp;&nbsp;" + availableLights[a][2] + "</TD>\n", "utf-8")) # light custom name
                                self.wfile.write(bytes("     <TD STYLE='background-color:rgb(240,248,255)'>" + availableLights[a][0].name + "</TD>\n", "utf-8")) # light type
                                self.wfile.write(bytes("     <TD STYLE='background-color:rgb(240,248,255)'>" + availableLights[a][0].address + "</TD>\n", "utf-8")) # light MAC address
                                self.wfile.write(bytes("     <TD STYLE='background-color:rgb(240,248,255)'>" + _get_light_rssi(availableLights[a]) + " dBm</TD>\n", "utf-8")) # light RSSI (signal quality)

                                try:
                                    if availableLights[a][1].is_connected:
                                        self.wfile.write(bytes("     <TD STYLE='background-color:rgb(240,248,255)'>" + "Yes" + "</TD>\n", "utf-8")) # is the light linked?
                                    else:
                                        self.wfile.write(bytes("     <TD STYLE='background-color:rgb(240,248,255)'>" + "<A HREF='doAction?link=" + str(a + 1) + "'>No</A></TD>\n", "utf-8")) # is the light linked?
                                except Exception as e:
                                    self.wfile.write(bytes("     <TD STYLE='background-color:rgb(240,248,255)'>" + "<A HREF='doAction?link=" + str(a + 1) + "'>No</A></TD>\n", "utf-8")) # is the light linked?

                                self.wfile.write(bytes("     <TD STYLE='background-color:rgb(240,248,255)'>" + updateStatus(False, availableLights[a][3]) + "</TD>\n", "utf-8")) # the last sent value to the light
                                self.wfile.write(bytes("  </TR>\n", "utf-8"))

                            self.wfile.write(bytes("</TABLE>\n", "utf-8"))

                        self.wfile.write(bytes("<BR><HR><BR>\n", "utf-8"))
                        self.wfile.write(bytes("<A ID='presets'>List of available custom presets to use:</A><BR><BR>\n", "utf-8"))
                        self.wfile.write(bytes("<TABLE WIDTH='98%' BORDER='1'>\n", "utf-8"))
                        self.wfile.write(bytes("  <TR>\n", "utf-8"))
                        self.wfile.write(bytes("     <TH STYLE='width:4%; text-align:left'>Preset\n", "utf-8"))
                        self.wfile.write(bytes("     <TH STYLE='width:46%; text-align:left'>Preset Parameters</TH>\n", "utf-8"))
                        self.wfile.write(bytes("     <TH STYLE='width:4%; text-align:left'>Preset\n", "utf-8"))
                        self.wfile.write(bytes("     <TH STYLE='width:46%; text-align:left'>Preset Parameters</TH>\n", "utf-8"))
                        self.wfile.write(bytes("  </TR>\n", "utf-8"))
                        
                        for a in range((numOfPresets + 1) // 2): # build the list itself, showing 2 presets next to each other
                            currentPreset = (2 * a)
                            self.wfile.write(bytes("  <TR>\n", "utf-8"))
                            self.wfile.write(bytes("     <TD ALIGN='CENTER' STYLE='background-color:rgb(173,255,47)'><FONT SIZE='+2'><A HREF='doAction?use_preset=" + str(currentPreset + 1) + "'>" + str(currentPreset + 1) + "</A></FONT></TD>\n", "utf-8"))
                            self.wfile.write(bytes("     <TD VALIGN='TOP' STYLE='background-color:rgb(240,248,255)'>" + customPresetInfoBuilder(currentPreset, True) + "</TD>\n", "utf-8"))
                            if currentPreset + 1 < numOfPresets:
                                self.wfile.write(bytes("     <TD ALIGN='CENTER' STYLE='background-color:rgb(173,255,47)'><FONT SIZE='+2'><A HREF='doAction?use_preset=" + str(currentPreset + 2) + "'>" + str(currentPreset + 2) + "</A></FONT></TD>\n", "utf-8"))
                                self.wfile.write(bytes("     <TD VALIGN='TOP' STYLE='background-color:rgb(240,248,255)'>" + customPresetInfoBuilder(currentPreset + 1, True) + "</TD>\n", "utf-8"))
                            else:
                                self.wfile.write(bytes("     <TD></TD><TD></TD>\n", "utf-8"))
                            self.wfile.write(bytes("  </TR>\n", "utf-8"))
                        
                        self.wfile.write(bytes("</TABLE>\n", "utf-8"))
            
            if paramsList[1] == True:
                writeHTMLSections(self, "quicklinks") # add the footer to the bottom of the page
                writeHTMLSections(self, "htmlendheaders") # add the ending section to the very bottom

    def do_POST(self):
        """Handle POST requests for batch commands with JSON body.

        POST /NeewerLux/batch
        Content-Type: application/json

        Request body:
        {
            "commands": [
                {"light": "1", "mode": "HSI", "hue": 0, "sat": 100, "bri": 50},
                {"light": "2", "mode": "CCT", "temp": 56, "bri": 80},
                {"light": "3", "mode": "ON"},
                {"light": "*", "mode": "OFF"}
            ]
        }

        Response: JSON with per-command results.
        """
        # IP CHECK (same as do_GET)
        clientIP = self.client_address[0]
        acceptedIP = False
        for check in range(len(acceptable_HTTP_IPs)):
            if acceptedIP != True:
                if acceptable_HTTP_IPs[check] in clientIP:
                    acceptedIP = True

        if acceptedIP == False:
            self.send_error(403, "Forbidden - IP " + clientIP + " is not in the list of accepted addresses")
            return

        # ONLY ACCEPT REQUESTS TO SUPPORTED POST ENDPOINTS
        if self.path not in ("/NeewerLux/batch", "/NeewerLux/animate", "/NeewerLite-Python/batch", "/NeewerLite-Python/animate"):
            self.send_error(404, "POST requests are supported at /NeewerLux/batch and /NeewerLux/animate")
            return

        # READ AND PARSE THE JSON BODY
        try:
            contentLength = int(self.headers.get("Content-Length", 0))
            if contentLength > 65536:  # 64KB sanity limit
                self.send_error(413, "Request body too large (max 64KB)")
                return
            if contentLength == 0:
                self.send_error(400, "Empty request body")
                return

            rawBody = self.rfile.read(contentLength)
            body = json.loads(rawBody.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self.send_error(400, "Invalid JSON: " + str(e))
            return

        resultData = {}

        if self.path in ("/NeewerLux/batch", "/NeewerLite-Python/batch"):
            commands = body.get("commands", [])
            if not isinstance(commands, list) or len(commands) == 0:
                self.send_error(400, "Request must contain a non-empty 'commands' array")
                return

            printDebugString("POST batch request from " + clientIP + " with " + str(len(commands)) + " command(s)")

            global threadAction
            if threadAction != "" and threadAction != "finished":
                resultData = {"success": False, "error": "Server is busy processing another command. Please retry."}
            else:
                threadAction = "HTTP"
                try:
                    resultData = processBatchCommands(commands, asyncioEventLoop)
                except Exception as e:
                    resultData = {"success": False, "error": str(e)}
                finally:
                    threadAction = ""

        elif self.path in ("/NeewerLux/animate", "/NeewerLite-Python/animate"):
            action = body.get("action", "play")  # play, stop, list, create
            printDebugString("POST animate request from " + clientIP + ": " + action)

            if action == "play":
                animName = body.get("name", "")
                speed = body.get("speed", 1.0)
                loop = body.get("loop", None)
                fps = body.get("rate", body.get("fps", 5))
                briScale = body.get("brightness", body.get("bri", 100)) / 100.0
                if "parallel" in body:
                    global animParallelWrites
                    animParallelWrites = bool(body.get("parallel", True))
                if animName:
                    # Case-insensitive name resolution
                    resolvedAnimName = None
                    for key in savedAnimations:
                        if key.lower() == animName.lower():
                            resolvedAnimName = key
                            break
                if resolvedAnimName:
                    animName = resolvedAnimName
                    maxLoops = int(body.get("maxLoops", body.get("max_loops", 0)))
                    # Handle revert flag from web UI
                    if "revert" in body:
                        global animRevertOnFinish
                        animRevertOnFinish = bool(body.get("revert", True))
                    startAnimation(animName, asyncioEventLoop, speed, loop, fps=int(fps), briScale=briScale, maxLoops=maxLoops)
                    resultData = {"success": True, "action": "play", "animation": animName}
                else:
                    resultData = {"success": False, "error": "Animation '" + str(animName) + "' not found",
                                  "available": list(savedAnimations.keys())}
            elif action == "stop":
                stopAnimation()
                resultData = {"success": True, "action": "stop"}
            elif action == "list":
                animList = []
                for aName, aData in sorted(savedAnimations.items()):
                    animList.append({
                        "name": aName,
                        "description": aData.get("description", ""),
                        "keyframes": len(aData.get("keyframes", [])),
                        "loop": aData.get("loop", False)
                    })
                resultData = {"success": True, "animations": animList,
                              "currently_playing": currentAnimationName if animationRunning else None}
            elif action == "create":
                # Create a new animation from JSON definition
                animData = body.get("animation", {})
                if not animData.get("name") or not animData.get("keyframes"):
                    resultData = {"success": False, "error": "Animation must have 'name' and 'keyframes'"}
                else:
                    savedAnimations[animData["name"]] = animData
                    saveAnimationToFile(animData)
                    resultData = {"success": True, "action": "create", "animation": animData["name"]}
                    # Refresh GUI list if available
                    try:
                        if mainWindow is not None:
                            mainWindow.animRefreshList()
                    except Exception:
                        pass
            elif action == "status":
                resultData = {"success": True, "running": animationRunning,
                              "animation": currentAnimationName if animationRunning else None}
            else:
                resultData = {"success": False, "error": "Unknown action: " + action}

        # SEND JSON RESPONSE
        responseBody = json.dumps(resultData).encode("utf-8")
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(responseBody)))
        self.end_headers()
        self.wfile.write(responseBody)

def writeHTMLSections(self, theSection, errorMsg = ""):
    if theSection == "httpheaders":
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", "text/html;charset=UTF-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
    elif theSection == "htmlheaders":
        self.wfile.write(bytes("<!DOCTYPE html>\n", "utf-8"))
        self.wfile.write(bytes("<HTML>\n<HEAD>\n", "utf-8"))
        self.wfile.write(bytes("<TITLE>NeewerLux 1.0.0 — based on NeewerLite-Python by Zach Glenwright / NeewerLite by Xu Lian</TITLE>\n</HEAD>\n", "utf-8"))
        self.wfile.write(bytes("<BODY>\n", "utf-8"))
    elif theSection == "errorHelp":
        self.wfile.write(bytes("<H1>Invalid request!</H1>\n", "utf-8"))
        self.wfile.write(bytes("Last Request: <EM>" + self.path + "</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes(errorMsg + "<BR><BR>\n", "utf-8"))
        self.wfile.write(bytes("Valid parameters to use -<BR>\n", "utf-8"))
        self.wfile.write(bytes("<STRONG>list</STRONG> - list the current lights NeewerLux has available to it and the custom presets it can use<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Example: <EM>http://(server address)/NeewerLux/doAction?list</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("<STRONG>discover</STRONG> - tell NeewerLux to scan for new lights<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Example: <EM>http://(server address)/NeewerLux/doAction?discover</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("<STRONG>nopage</STRONG> - send a command to the HTTP server, but don't render the webpage showing the results (<EM>useful, for example, on a headless Raspberry Pi where you don't necessarily want to see the results page</EM>)<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Example: <EM>http://(server address)/NeewerLux/doAction?nopage</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("<STRONG>link=</STRONG> - (value: <EM>index of light to link to</EM>) manually link to a specific light - you can specify multiple lights with semicolons (so link=1;2 would try to link to both lights 1 and 2)<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Example: <EM>http://(server address)/NeewerLux/doAction?link=1</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("<STRONG>light=</STRONG> - the MAC address (or current index of the light) you want to send a command to - you can specify multiple lights with semicolons (so light=1;2 would send a command to both lights 1 and 2)<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Example: <EM>http://(server address)/NeewerLux/doAction?light=11:22:33:44:55:66</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("<STRONG>mode=</STRONG> - the mode (value: <EM>HSI, CCT, and either ANM or SCENE</EM>) - the color mode to switch the light to<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Example: <EM>http://(server address)/NeewerLux/doAction?mode=CCT</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("<STRONG>use_preset=</STRONG> - (value: <EM>1-" + str(numOfPresets) + "</EM>) - use a custom global or snapshot preset<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Example: <EM>http://(server address)/NeewerLux/doAction?use_preset=2</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("(CCT mode only) <STRONG>temp=</STRONG> or <STRONG>temperature=</STRONG> - (value: <EM>3200 to 8500</EM>) the color temperature in CCT mode to set the light to<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Example: <EM>http://(server address)/NeewerLux/doAction?temp=5200</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("(HSI mode only) <STRONG>hue=</STRONG> - (value: <EM>0 to 360</EM>) the hue value in HSI mode to set the light to<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Example: <EM>http://(server address)/NeewerLux/doAction?hue=240</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("(HSI mode only) <STRONG>sat=</STRONG> or <STRONG>saturation=</STRONG> - (value: <EM>0 to 100</EM>) the color saturation value in HSI mode to set the light to<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Example: <EM>http://(server address)/NeewerLux/doAction?sat=65</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("(ANM/SCENE mode only) <STRONG>scene=</STRONG> - (value: <EM>1 to 9</EM>) which animation (scene) to switch the light to<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Example: <EM>http://(server address)/NeewerLux/doAction?scene=3</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("(CCT/HSI/ANM modes) <STRONG>bri=</STRONG>, <STRONG>brightness=</STRONG> or <STRONG>intensity=</STRONG> - (value: <EM>0 to 100</EM>) how bright you want the light<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Example: <EM>http://(server address)/NeewerLux/doAction?brightness=80</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("<BR><BR>More examples -<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;Set the light with MAC address <EM>11:22:33:44:55:66</EM> to <EM>CCT</EM> mode, with a color temperature of <EM>5200</EM> and brightness of <EM>40</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;<EM>http://(server address)/NeewerLux/doAction?light=11:22:33:44:55:66&mode=CCT&temp=5200&bri=40</EM><BR><BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;Set the light with MAC address <EM>11:22:33:44:55:66</EM> to <EM>HSI</EM> mode, with a hue of <EM>70</EM>, saturation of <EM>50</EM> and brightness of <EM>10</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;<EM>http://(server address)/NeewerLux/doAction?light=11:22:33:44:55:66&mode=HSI&hue=70&sat=50&bri=10</EM><BR><BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;Set the first light available to <EM>SCENE</EM> mode, using the <EM>first</EM> animation and brightness of <EM>55</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;<EM>http://(server address)/NeewerLux/doAction?light=1&mode=SCENE&scene=1&bri=55</EM><BR><BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;Use the 2nd custom preset, but don't render the webpage showing the results<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;<EM>http://(server address)/NeewerLux/doAction?use_preset=2&nopage</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("<BR><HR><BR>\n", "utf-8"))
        self.wfile.write(bytes("<H2>Batch Commands (multiple lights, different settings)</H2>\n", "utf-8"))
        self.wfile.write(bytes("<STRONG>batch=</STRONG> - send different commands to different lights in a single request<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;Format: <EM>light:mode:param1:param2[:param3]</EM> — separate multiple commands with semicolons<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;Modes: <STRONG>CCT</STRONG> (temp:bri), <STRONG>HSI</STRONG> (hue:sat:bri), <STRONG>ANM</STRONG> (scene:bri), <STRONG>ON</STRONG>, <STRONG>OFF</STRONG><BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;Lights can be specified by index (1, 2...), MAC address, or * for all<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;CCT temp values: use either short (56) or full (5600) format — both become 5600K<BR><BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;Examples:<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Set light 1 to red and light 2 to blue:<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;<EM>http://(server address)/NeewerLux/doAction?batch=1:HSI:0:100:100;2:HSI:240:100:100</EM><BR><BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Set light 1 to warm CCT, turn light 2 off:<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;<EM>http://(server address)/NeewerLux/doAction?batch=1:CCT:32:80;2:OFF</EM><BR><BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Set all lights to 5600K at 50% brightness:<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;<EM>http://(server address)/NeewerLux/doAction?batch=*:CCT:56:50</EM><BR><BR>\n", "utf-8"))
        self.wfile.write(bytes("<STRONG>POST /NeewerLux/batch</STRONG> - same as above, but using a JSON body for richer control<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;Send a POST request with Content-Type: application/json<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;Body: <EM>{\"commands\": [{\"light\": \"1\", \"mode\": \"HSI\", \"hue\": 0, \"sat\": 100, \"bri\": 50}, ...]}</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;Returns a JSON response with per-command results<BR>\n", "utf-8"))
        self.wfile.write(bytes("<BR><HR><BR>\n", "utf-8"))
        self.wfile.write(bytes("<H2>Custom Animations</H2>\n", "utf-8"))
        self.wfile.write(bytes("<STRONG>list_animations</STRONG> - list all saved custom animations<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Example: <EM>http://(server address)/NeewerLux/doAction?list_animations</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("<STRONG>animate=</STRONG> - play a saved animation by name (URL-encode spaces as %20)<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;Optionally append |speed|rate|brightness (e.g. animate=Police%20Flash|2.0|10|50)<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Example: <EM>http://(server address)/NeewerLux/doAction?animate=Police%20Flash</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Example: <EM>http://(server address)/NeewerLux/doAction?animate=Color%20Cycle|0.5</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("<STRONG>stop_animate</STRONG> - stop the currently playing animation<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;&nbsp;&nbsp;Example: <EM>http://(server address)/NeewerLux/doAction?stop_animate</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("<STRONG>POST /NeewerLux/animate</STRONG> - JSON API for animation control<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;Actions: play, stop, list, create, status<BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;Play: <EM>{\"action\": \"play\", \"name\": \"Police Flash\", \"speed\": 1.0, \"loop\": true, \"rate\": 5}</EM><BR>\n", "utf-8"))
        self.wfile.write(bytes("&nbsp;&nbsp;Create: <EM>{\"action\": \"create\", \"animation\": {\"name\": \"...\", \"loop\": true, \"keyframes\": [...]}}</EM><BR>\n", "utf-8"))
    elif theSection == "quicklinks" or theSection == "quicklinks-timer":
        footerLinks = "Shortcut links: "
        footerLinks = footerLinks + "<A HREF='doAction?discover'>Scan for New Lights</A> | "
        footerLinks = footerLinks + "<A HREF='doAction?list'>List Currently Available Lights and Custom Presets</A> | "
        footerLinks = footerLinks + "<A HREF='doAction?list_animations'>Animations</A>"
        self.wfile.write(bytes("<CENTER><HR>" + footerLinks + "<HR></CENTER>\n", "utf-8"))

        if theSection == "quicklinks-timer": # write the "This page will refresh..." timer
            self.wfile.write(bytes("<CENTER><strong><em><span id='refreshDisplay'><BR></span></em></strong></CENTER><HR>\n", "utf-8"))
    elif theSection == "htmlendheaders":
        self.wfile.write(bytes("<CENTER><A HREF='https://github.com/poizenjam/NeewerLux/'>NeewerLux 1.0.0</A><BR>based on <A HREF='https://github.com/taburineagle/NeewerLite-Python/'>NeewerLite-Python</A> (v0.12d) by Zach Glenwright / originally from <A HREF='https://github.com/keefo/NeewerLite'>NeewerLite</A> by Xu Lian<BR></CENTER>\n", "utf-8"))
        self.wfile.write(bytes("</BODY>\n</HTML>", "utf-8"))

def formatStringForConsole(theString, maxLength):
    if theString == "-": # return a header divider if the string is "="
        return "-" * maxLength
    else:
        if len(theString) == maxLength: # if the string is the max length, then just return the string
            return theString
        if len(theString) < maxLength: # if the string fits in the max length, then add spaces to pad it out
            return theString + " " * (maxLength - len(theString))
        else: # truncate the string, it's too long
            return theString[0:maxLength - 4] + " ..."

def createLightPrefsFolder():
    #CREATE THE light_prefs FOLDER IF IT DOESN'T EXIST
    try:
        os.mkdir(os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep + "light_prefs")
    except FileExistsError:
        pass # the folder already exists, so we don't need to create it

def loadPrefsFile(globalPrefsFile = ""):
    global findLightsOnStartup, autoConnectToLights, printDebug, maxNumOfAttempts, \
           rememberLightsOnExit, acceptable_HTTP_IPs, customKeys, enableTabsOnLaunch, \
           whiteListedMACs, rememberPresetsOnExit, autoReconnectOnDisconnect, livePreview, hideConsoleOnLaunch, minimizeToTrayOnClose, httpAutoStart, cctFallbackMode, enableLogTab, logToFile, globalCCTMin, globalCCTMax

    if globalPrefsFile != "":
        printDebugString("Loading global preferences from file...")

        with open(globalPrefsFile, mode="r", encoding="utf-8") as fileToOpen:
            mainPrefs = fileToOpen.read().splitlines()

        acceptable_arguments = ["findLightsOnStartup", "autoConnectToLights", "printDebug", "maxNumOfAttempts", "rememberLightsOnExit", "acceptableIPs", \
            "SC_turnOffButton", "SC_turnOnButton", "SC_scanCommandButton", "SC_tryConnectButton", "SC_Tab_CCT", "SC_Tab_HSI", "SC_Tab_SCENE", "SC_Tab_PREFS", \
            "SC_Dec_Bri_Small", "SC_Inc_Bri_Small", "SC_Dec_Bri_Large", "SC_Inc_Bri_Large", \
            "SC_Dec_1_Small", "SC_Inc_1_Small", "SC_Dec_2_Small", "SC_Inc_2_Small", "SC_Dec_3_Small", "SC_Inc_3_Small", \
            "SC_Dec_1_Large", "SC_Inc_1_Large", "SC_Dec_2_Large", "SC_Inc_2_Large", "SC_Dec_3_Large", "SC_Inc_3_Large", \
            "enableTabsOnLaunch", "whiteListedMACs", "rememberPresetsOnExit", "autoReconnectOnDisconnect", "hideConsoleOnLaunch", "minimizeToTrayOnClose", "livePreview", "httpAutoStart", "cctFallbackMode", "enableLogTab", "logToFile", "globalCCTMin", "globalCCTMax"]

        # KICK OUT ANY PARAMETERS THAT AREN'T IN THE "ACCEPTABLE ARGUMENTS" LIST ABOVE
        # THIS SECTION OF CODE IS *SLIGHTLY* DIFFERENT THAN THE CLI KICK OUT CODE
        # THIS WAY, WE CAN HAVE COMMENTS IN THE PREFS FILE IF DESIRED
        for a in range(len(mainPrefs) - 1, -1, -1):
            if not any(x in mainPrefs[a] for x in acceptable_arguments): # if the current argument is invalid
                mainPrefs.pop(a) # delete the invalid argument from the list

        # NOW THAT ANY STRAGGLERS ARE OUT, ADD DASHES TO WHAT REMAINS TO PROPERLY PARSE IN THE PARSER
        for a in range(len(mainPrefs)):
            mainPrefs[a] = "--" + mainPrefs[a]
    else:
        mainPrefs = [] # submit an empty list to return the default values for everything

    prefsParser = argparse.ArgumentParser() # parser for preference arguments

    # SET PROGRAM DEFAULTS
    prefsParser.add_argument("--findLightsOnStartup", default=1)
    prefsParser.add_argument("--autoConnectToLights", default=1)
    prefsParser.add_argument("--printDebug", default=1)
    prefsParser.add_argument("--maxNumOfAttempts", default=6)
    prefsParser.add_argument("--rememberLightsOnExit", default=0)
    prefsParser.add_argument("--acceptableIPs", default=["127.0.0.1", "192.168.", "10."])
    prefsParser.add_argument("--whiteListedMACs" , default=[])
    prefsParser.add_argument("--rememberPresetsOnExit", default=1)
    prefsParser.add_argument("--livePreview", default=1)
    prefsParser.add_argument("--autoReconnectOnDisconnect", default=1)
    prefsParser.add_argument("--hideConsoleOnLaunch", default=0)
    prefsParser.add_argument("--minimizeToTrayOnClose", default=1)
    prefsParser.add_argument("--httpAutoStart", default=0)
    prefsParser.add_argument("--cctFallbackMode", default="convert")
    prefsParser.add_argument("--enableLogTab", default=1)
    prefsParser.add_argument("--logToFile", default=0)
    prefsParser.add_argument("--globalCCTMin", default=3200)
    prefsParser.add_argument("--globalCCTMax", default=5600)

    # SHORTCUT KEY CUSTOMIZATIONS
    prefsParser.add_argument("--SC_turnOffButton", default="Ctrl+PgDown") # 0
    prefsParser.add_argument("--SC_turnOnButton", default="Ctrl+PgUp") # 1
    prefsParser.add_argument("--SC_scanCommandButton", default="Ctrl+Shift+S") # 2
    prefsParser.add_argument("--SC_tryConnectButton", default="Ctrl+Shift+C") # 3
    prefsParser.add_argument("--SC_Tab_CCT", default="Alt+1") # 4
    prefsParser.add_argument("--SC_Tab_HSI", default="Alt+2") # 5
    prefsParser.add_argument("--SC_Tab_SCENE", default="Alt+3") # 6
    prefsParser.add_argument("--SC_Tab_PREFS", default="Alt+4") # 7
    prefsParser.add_argument("--SC_Dec_Bri_Small", default="/") # 8
    prefsParser.add_argument("--SC_Inc_Bri_Small", default="*") # 9
    prefsParser.add_argument("--SC_Dec_Bri_Large", default="Ctrl+/") # 10
    prefsParser.add_argument("--SC_Inc_Bri_Large", default="Ctrl+*") # 11
    prefsParser.add_argument("--SC_Dec_1_Small", default="7") # 12
    prefsParser.add_argument("--SC_Inc_1_Small", default="9") # 13
    prefsParser.add_argument("--SC_Dec_2_Small", default="4") # 14
    prefsParser.add_argument("--SC_Inc_2_Small", default="6") # 15
    prefsParser.add_argument("--SC_Dec_3_Small", default="1") # 16
    prefsParser.add_argument("--SC_Inc_3_Small", default="3") # 17
    prefsParser.add_argument("--SC_Dec_1_Large", default="Ctrl+7") # 18
    prefsParser.add_argument("--SC_Inc_1_Large", default="Ctrl+9") # 19
    prefsParser.add_argument("--SC_Dec_2_Large", default="Ctrl+4") # 20
    prefsParser.add_argument("--SC_Inc_2_Large", default="Ctrl+6") # 21
    prefsParser.add_argument("--SC_Dec_3_Large", default="Ctrl+1") # 22
    prefsParser.add_argument("--SC_Inc_3_Large", default="Ctrl+3") # 23

    # "HIDDEN" DEBUG OPTIONS - oooooh!
    # THESE ARE OPTIONS THAT HELP DEBUG THINGS, BUT AREN'T REALLY USEFUL FOR NORMAL OPERATION
    # enableTabsOnLaunch SHOWS ALL TABS ACTIVE (INSTEAD OF DISABLING THEM) ON LAUNCH SO EVEN WITHOUT A LIGHT, A BYTESTRING CAN BE CALCULATED
    prefsParser.add_argument("--enableTabsOnLaunch", default=0)

    mainPrefs = prefsParser.parse_args(mainPrefs)

    # SET GLOBAL VALUES BASED ON PREFERENCES
    findLightsOnStartup = bool(int(mainPrefs.findLightsOnStartup)) # whether or not to scan for lights on launch
    autoConnectToLights = bool(int(mainPrefs.autoConnectToLights)) # whether or not to connect to lights when found
    printDebug = bool(int(mainPrefs.printDebug)) # whether or not to display debug messages in the console
    maxNumOfAttempts = int(mainPrefs.maxNumOfAttempts) # maximum number of attempts before failing out
    rememberLightsOnExit = bool(int(mainPrefs.rememberLightsOnExit)) # whether or not to remember light mode/settings when quitting out
    rememberPresetsOnExit = bool(int(mainPrefs.rememberPresetsOnExit)) # whether or not to remember the custom presets when quitting out
    livePreview = bool(int(mainPrefs.livePreview)) # whether sliders send in real-time
    autoReconnectOnDisconnect = bool(int(mainPrefs.autoReconnectOnDisconnect)) # whether or not to auto-reconnect after disconnection
    hideConsoleOnLaunch = bool(int(mainPrefs.hideConsoleOnLaunch)) # whether to auto-hide the console window on GUI startup
    minimizeToTrayOnClose = bool(int(mainPrefs.minimizeToTrayOnClose))
    httpAutoStart = bool(int(mainPrefs.httpAutoStart))
    cctFallbackMode = mainPrefs.cctFallbackMode if mainPrefs.cctFallbackMode in ("convert", "ignore") else "convert"
    enableLogTab = bool(int(mainPrefs.enableLogTab))
    logToFile = bool(int(mainPrefs.logToFile))
    globalCCTMin = int(mainPrefs.globalCCTMin)
    globalCCTMax = int(mainPrefs.globalCCTMax) # whether closing the window minimizes to tray or quits

    if type(mainPrefs.acceptableIPs) is not list: # we have a string in the return, so we need to post-process it
        acceptable_HTTP_IPs = mainPrefs.acceptableIPs.replace(" ", "").split(";") # split the IP addresses into a list for acceptable IPs
    else: # the return is already a list (the default list), so return it
        acceptable_HTTP_IPs = mainPrefs.acceptableIPs

    if type(mainPrefs.whiteListedMACs) is not list: # if we've specified MAC addresses to whitelist, add them to the global list
        whiteListedMACs = mainPrefs.whiteListedMACs.replace(" ", "").split(";")

    # RETURN THE CUSTOM KEYBOARD MAPPINGS
    customKeys = [mainPrefs.SC_turnOffButton, mainPrefs.SC_turnOnButton, mainPrefs.SC_scanCommandButton, mainPrefs.SC_tryConnectButton, \
                  mainPrefs.SC_Tab_CCT, mainPrefs.SC_Tab_HSI, mainPrefs.SC_Tab_SCENE, mainPrefs.SC_Tab_PREFS, \
                  mainPrefs.SC_Dec_Bri_Small, mainPrefs.SC_Inc_Bri_Small, mainPrefs.SC_Dec_Bri_Large, mainPrefs.SC_Inc_Bri_Large, \
                  mainPrefs.SC_Dec_1_Small, \
                  mainPrefs.SC_Inc_1_Small, \
                  mainPrefs.SC_Dec_2_Small, \
                  mainPrefs.SC_Inc_2_Small, \
                  mainPrefs.SC_Dec_3_Small, \
                  mainPrefs.SC_Inc_3_Small, \
                  mainPrefs.SC_Dec_1_Large, \
                  mainPrefs.SC_Inc_1_Large, \
                  mainPrefs.SC_Dec_2_Large, \
                  mainPrefs.SC_Inc_2_Large, \
                  mainPrefs.SC_Dec_3_Large, \
                  mainPrefs.SC_Inc_3_Large]
                
    enableTabsOnLaunch = bool(int(mainPrefs.enableTabsOnLaunch))

if __name__ == '__main__':
    # Display the version of NeewerLux we're using
    print("---------------------------------------------------------")
    print("               NeewerLux ver. 1.0.0")
    print("  Cross-platform Neewer LED light control")
    print("  https://github.com/poizenjam/NeewerLux/")
    print("")
    print("  Based on NeewerLite-Python (v0.12d)")
    print("    by Zach Glenwright (@taburineagle)")
    print("  Originally from NeewerLite by Xu Lian (@keefo)")
    print("---------------------------------------------------------")

    singleInstanceLock() # make a lockfile if one doesn't exist yet, and quit out if one does

    if os.path.exists(globalPrefsFile):
        loadPrefsFile(globalPrefsFile) # if a preferences file exists, process it and load the preferences
    else:
        loadPrefsFile() # if it doesn't, then just load the defaults

    if os.path.exists(customLightPresetsFile):
        loadCustomPresets() # if there's a custom mapping for presets, then load that into memory

    setUpAsyncio() # set up the asyncio loop
    cmdReturn = [True] # initially set to show the GUI interface over the CLI interface

    if len(sys.argv) > 1: # if we have more than 1 argument on the command line (the script itself is argument 1), then process switches
        cmdReturn = processCommands()
        printDebug = cmdReturn[1] # if we use the --quiet option, then don't show debug strings in the console

        if cmdReturn[0] == False: # if we're trying to load the CLI, make sure we aren't already running another version of it
            doAnotherInstanceCheck() # check to see if another instance is running, and if it is, then error out and quit

        # START HTTP SERVER HERE AND SIT IN THIS LOOP UNTIL THE END
        if cmdReturn[0] == "HTTP":
            doAnotherInstanceCheck() # check to see if another instance is running, and if it is, then error out and quit

            # Load animations and light aliases for HTTP access
            loadAllAnimations()
            loadLightAliases()

            # Start a worker thread to process BLE operations (discover, connect, send, etc.)
            # Without this, threadAction commands from processHTMLCommands would never be picked up.
            httpWorker = threading.Thread(target=workerThread, args=(asyncioEventLoop,), name="workerThread", daemon=True)
            httpWorker.start()

            webServer = ThreadingHTTPServer(("", 8080), NLPythonServer)

            try:
                printDebugString("Starting the HTTP Server on Port 8080...")
                printDebugString("-------------------------------------------------------------------------------------")

                # start the HTTP server and wait for requests
                webServer.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                printDebugString("Stopping the HTTP Server...")
                webServer.server_close()

                # Stop the worker thread and disconnect from lights
                printDebugString("Attempting to unlink from lights...")
                threadAction = "quit"
                time.sleep(1)  # give worker thread time to process quit
                try:
                    asyncioEventLoop.run_until_complete(parallelAction("disconnect", [-1], False))
                except RuntimeError:
                    pass  # event loop may still be in use briefly
           
            printDebugString("Closing the program NOW")
            singleInstanceUnlockandQuit(0) # delete the lock file and quit out

        if cmdReturn[0] == "LIST":
            doAnotherInstanceCheck() # check to see if another instance is running, and if it is, then error out and quit

            print("NeewerLux 1.0.0 — based on NeewerLite-Python 0.12d by Zach Glenwright / NeewerLite by Xu Lian")
            print("Searching for nearby Neewer lights...")
            asyncioEventLoop.run_until_complete(findDevices())

            if len(availableLights) > 0:
                print()

                if len(availableLights) == 1: # we only found one
                    print("We found 1 Neewer light on the last search.")
                else: # we found more than one
                    print("We found " + str(len(availableLights)) + " Neewer lights on the last search.")

                print()

                if platform.system() == "Darwin": # if we're on MacOS, then we display the GUID instead of the MAC address
                    addressCharsAllowed = 36 # GUID addresses are 36 characters long
                    addressString = "GUID (MacOS)"
                else:
                    addressCharsAllowed = 17 # MAC addresses are 17 characters long
                    addressString = "MAC Address"

                nameCharsAllowed = 79 - addressCharsAllowed # the remaining space is to display the light name

                # PRINT THE HEADERS
                print(formatStringForConsole("Custom Name (Light Type)", nameCharsAllowed) + \
                      " " + \
                      formatStringForConsole(addressString, addressCharsAllowed))

                # PRINT THE SEPARATORS
                print(formatStringForConsole("-", nameCharsAllowed) + " " + formatStringForConsole("-", addressCharsAllowed))

                # PRINT THE LIGHTS
                for a in range(len(availableLights)):
                    lightName = availableLights[a][2] + "(" + availableLights[a][0].name + ")"

                    print(formatStringForConsole(lightName, nameCharsAllowed) + " " + \
                          formatStringForConsole(availableLights[a][0].address, addressCharsAllowed))

                    print(formatStringForConsole(" > RSSI: " + _get_light_rssi(availableLights[a]) + "dBm", nameCharsAllowed))
            else:
                print("We did not find any Neewer lights on the last search.")

            singleInstanceUnlockandQuit(0) # delete the lock file and quit out

        printDebugString(" > Launch GUI: " + str(cmdReturn[0]))
        printDebugString(" > Show Debug Strings on Console: " + str(cmdReturn[1]))

        printDebugString(" > Mode: " + cmdReturn[3])

        if cmdReturn[3] == "CCT":
            printDebugString(" > Color Temperature: " + str(cmdReturn[4]) + "00K")
            printDebugString(" > Brightness: " + str(cmdReturn[5]))
        elif cmdReturn[3] == "HSI":
            printDebugString(" > Hue: " + str(cmdReturn[4]))
            printDebugString(" > Saturation: " + str(cmdReturn[5]))
            printDebugString(" > Brightness: " + str(cmdReturn[6]))
        elif cmdReturn[3] == "ANM":
            printDebugString(" > Scene: " + str(cmdReturn[4]))
            printDebugString(" > Brightness: " + str(cmdReturn[5]))

        if cmdReturn[0] == False: # if we're not showing the GUI, we need to specify a MAC address
            if cmdReturn[2] != "":
                printDebugString("-------------------------------------------------------------------------------------")
                printDebugString(" > CLI >> MAC Address of light to send command to: " + cmdReturn[2].upper())

                asyncioEventLoop.run_until_complete(connectToOneLight(cmdReturn[2])) # get Bleak object linking to this specific light and getting custom prefs
            else:
                printDebugString("-------------------------------------------------------------------------------------")
                printDebugString(" > CLI >> You did not specify a light to send the command to - use the --light switch")
                printDebugString(" > CLI >> and write either a MAC Address (XX:XX:XX:XX:XX:XX) to a Neewer light or")
                printDebugString(" > CLI >> ALL to send to all available Neewer lights found by Bluetooth")
                printDebugString("-------------------------------------------------------------------------------------")

    if cmdReturn[0] == True: # launch the GUI with the command-line arguments
        if importError == 0:
            try: # try to load the GUI
                # Enable high-DPI scaling (PySide2/Qt5 needs explicit opt-in; Qt6 does it automatically)
                if PYSIDE_VERSION == 2:
                    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
                    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
                    
                app = QApplication(sys.argv)
                
                if anotherInstance == True: # different than the CLI handling, the GUI needs to show a dialog box asking to quit or launch
                    errDlg = QMessageBox()
                    errDlg.setWindowTitle("Another Instance Running!")
                    errDlg.setTextFormat(Qt.TextFormat.RichText)
                    errDlg.setText("There is another instance of NeewerLux already running.&nbsp;Please close out of that instance first before trying to launch a new instance of the program.<br><br>If you are positive that you don't have any other instances running and you want to launch a new one anyway,&nbsp;click <em>Launch New Instance</em> below.&nbsp;Otherwise click <em>Quit</em> to quit out.")
                    launchBtn = errDlg.addButton("Launch New Instance", QMessageBox.ButtonRole.YesRole)
                    quitBtn = errDlg.addButton("Quit", QMessageBox.ButtonRole.RejectRole)
                    errDlg.setDefaultButton(quitBtn)
                    errDlg.setIcon(QMessageBox.Warning)

                    pyside_exec(errDlg)

                    if errDlg.clickedButton() == quitBtn:
                        sys.exit(1)

                mainWindow = MainWindow()

                # SET UP GUI BASED ON COMMAND LINE ARGUMENTS
                if len(cmdReturn) > 1:
                    if cmdReturn[3] == "CCT": # set up the GUI in CCT mode with specified parameters (or default, if none)
                        if mainWindow is not None: mainWindow.setUpGUI(colorMode=cmdReturn[3], temp=cmdReturn[4], brightness=cmdReturn[5])
                    elif cmdReturn[3] == "HSI": # set up the GUI in HSI mode with specified parameters (or default, if none)
                        if mainWindow is not None: mainWindow.setUpGUI(colorMode=cmdReturn[3], hue=cmdReturn[4], sat=cmdReturn[5], brightness=cmdReturn[6])
                    elif cmdReturn[3] == "ANM": # set up the GUI in ANM mode with specified parameters (or default, if none)
                        if mainWindow is not None: mainWindow.setUpGUI(colorMode=cmdReturn[3], scene=cmdReturn[4], brightness=cmdReturn[5])

                mainWindow.show()
                print("[TRACE] mainWindow.show() complete")
                
                # Restore saved window geometry and splitter sizes
                mainWindow.restoreWindowGeometry()

                # Sync Global Preferences tab with loaded prefs (checkboxes default
                # to UI-defined values until this is called, causing glitches)
                mainWindow.setupGlobalLightPrefsTab()

                # Hide console window on launch if preference is set
                if hideConsoleOnLaunch:
                    hideConsoleWindow()
                    if hasattr(mainWindow, '_consoleVisible'):
                        mainWindow._consoleVisible = False
                        if mainWindow._consoleAction:
                            mainWindow._consoleAction.setText("Show Console")

                # Auto-start HTTP server if preference is set
                if httpAutoStart:
                    mainWindow.toggleHTTPServer()

                # LOAD SAVED ANIMATIONS AND POPULATE THE ANIMATION LIST
                loadAllAnimations()
                loadLightAliases()
                print("[TRACE] loadAllAnimations() + loadLightAliases() complete")
                mainWindow.animRefreshList()
                print("[TRACE] animRefreshList() complete")

                # START THE BACKGROUND THREAD
                workerThread = threading.Thread(target=workerThread, args=(asyncioEventLoop,), name="workerThread", daemon=True)
                workerThread.start()
                print("[TRACE] workerThread started, entering event loop...")

                ret = pyside_exec(app)
                print("[TRACE] event loop exited with code " + str(ret))
                singleInstanceUnlockandQuit(ret) # delete the lock file and quit out
            except NameError as e:
                import traceback
                print("[CRASH] NameError during GUI startup:")
                traceback.print_exc()
            except Exception as e:
                import traceback
                print("[CRASH] Exception during GUI startup:")
                traceback.print_exc()
        else:
            if importError == 1: # we can't load PySide6 or PySide2
                print(" ===== CAN NOT FIND PYSIDE LIBRARY =====")
                print(" You don't have PySide6 (or PySide2) installed.  If you're only running NeewerLux from")
                print(" a command-line (from a Raspberry Pi CLI for instance), or using the HTTP server, you don't need this package.")
                print(" If you want to launch NeewerLux with the GUI, you need to install PySide6.")
                print()
                print(" To install PySide6, run either pip or pip3 from the command line:")
                print("    pip install PySide6")
                print("    pip3 install PySide6")
                print()
                print(" Or visit this website for more information:")
                print("    https://pypi.org/project/PySide6/")
            elif importError == 2: # we have PySide, but can't load the GUI file itself for some reason
                print(" ===== COULD NOT LOAD/FIND GUI FILE =====")
                print(" If you don't need to use the GUI, you are fine going without PySide6.")
                print(" but using NeewerLux with the GUI requires PySide6 (or PySide2).")
                print()
                print(" If you have already installed PySide6 but are still getting this error message,")
                print(" Make sure you have the neewerlux_ui.py script in the same directory as NeewerLux.py")
                print(" If you don't know where that file is, redownload the NeewerLux package from Github here:")
                print("    https://github.com/poizenjam/NeewerLux/")

                sys.exit(1) # quit out, we can't run the program without PySide or the GUI (for the GUI version, at least)
    else: # don't launch the GUI, send command to a light/lights and quit out
        if len(cmdReturn) > 1:
            if cmdReturn[3] == "CCT": # calculate CCT bytestring
                calculateByteString(colorMode=cmdReturn[3], temp=cmdReturn[4], brightness=cmdReturn[5])
            elif cmdReturn[3] == "HSI": # calculate HSI bytestring
                calculateByteString(colorMode=cmdReturn[3], HSI_H=cmdReturn[4], HSI_S=cmdReturn[5], HSI_I=cmdReturn[6])
            elif cmdReturn[3] == "ANM": # calculate ANM/SCENE bytestring
                calculateByteString(colorMode=cmdReturn[3], animation=cmdReturn[4], brightness=cmdReturn[5])
            elif cmdReturn[3] == "ON": # turn the light on
                setPowerBytestring("ON")
            elif cmdReturn[3] == "OFF": # turn the light off
                setPowerBytestring("OFF")

        if availableLights != []:
            printDebugString(" > CLI >> Bytestring to send to light:" + updateStatus())

            # CONNECT TO THE LIGHT AND SEND INFORMATION TO IT
            isFinished = False
            numOfAttempts = 1

            while isFinished == False:
                printDebugString("-------------------------------------------------------------------------------------")
                printDebugString(" > CLI >> Attempting to connect to light (attempt " + str(numOfAttempts) + " of " + str(maxNumOfAttempts) + ")")
                printDebugString("-------------------------------------------------------------------------------------")
                isFinished = asyncioEventLoop.run_until_complete(connectToLight(0, False))

                if numOfAttempts < maxNumOfAttempts:
                    numOfAttempts = numOfAttempts + 1
                else:
                    printDebugString("Error connecting to light " + str(maxNumOfAttempts) + " times - quitting out")
                    singleInstanceUnlockandQuit(1) # delete the lock file and quit out

            isFinished = False
            numOfAttempts = 1

            while isFinished == False:
                printDebugString("-------------------------------------------------------------------------------------")
                printDebugString(" > CLI >> Attempting to write to light (attempt " + str(numOfAttempts) + " of " + str(maxNumOfAttempts) + ")")
                printDebugString("-------------------------------------------------------------------------------------")
                isFinished = asyncioEventLoop.run_until_complete(writeToLight(0, False))

                if numOfAttempts < maxNumOfAttempts:
                    numOfAttempts = numOfAttempts + 1
                else:
                    printDebugString("Error writing to light " + str(maxNumOfAttempts) + " times - quitting out")
                    singleInstanceUnlockandQuit(1) # delete the lock file and quit out

            isFinished = False
            numOfAttempts = 1

            while isFinished == False:
                printDebugString("-------------------------------------------------------------------------------------")
                printDebugString(" > CLI >> Attempting to disconnect from light (attempt " + str(numOfAttempts) + " of " + str(maxNumOfAttempts) + ")")
                printDebugString("-------------------------------------------------------------------------------------")
                isFinished = asyncioEventLoop.run_until_complete(disconnectFromLight(0, updateGUI = False))

                if numOfAttempts < maxNumOfAttempts:
                    numOfAttempts = numOfAttempts + 1
                else:
                    printDebugString("Error disconnecting from light " + str(maxNumOfAttempts) + " times - quitting out")
                    singleInstanceUnlockandQuit(1) # delete the lock file and quit out
        else:
            printDebugString("-------------------------------------------------------------------------------------")
            printDebugString(" > CLI >> Calculated bytestring:" + updateStatus())

        singleInstanceUnlockandQuit(0) # delete the lock file and quit out
