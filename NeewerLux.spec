# -*- mode: python ; coding: utf-8 -*-
# NeewerLux PyInstaller spec file
# Build: pyinstaller NeewerLux.spec
# Output: dist/NeewerLux/ (onedir)

import sys
from PyInstaller.utils.hooks import collect_all

# Collect all bleak submodules and WinRT DLLs
bleak_datas, bleak_binaries, bleak_hiddenimports = collect_all('bleak')

# On Windows, bleak needs winrt backend
winrt_datas = []
winrt_binaries = []
winrt_hiddenimports = []
if sys.platform == 'win32':
    try:
        wd, wb, wh = collect_all('bleak_winrt')
        winrt_datas += wd; winrt_binaries += wb; winrt_hiddenimports += wh
    except Exception:
        pass
    # Some bleak versions use winrt directly
    for pkg in ['winrt', 'winrt.windows.devices.bluetooth',
                'winrt.windows.devices.bluetooth.genericattributeprofile',
                'winrt.windows.devices.bluetooth.advertisement',
                'winrt.windows.devices.enumeration',
                'winrt.windows.foundation',
                'winrt.windows.storage.streams']:
        try:
            wd2, wb2, wh2 = collect_all(pkg)
            winrt_datas += wd2; winrt_binaries += wb2; winrt_hiddenimports += wh2
        except Exception:
            pass

a = Analysis(
    ['NeewerLux.py'],
    pathex=[],
    binaries=bleak_binaries + winrt_binaries,
    datas=bleak_datas + winrt_datas,
    hiddenimports=[
        'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
        'neewerlux_ui', 'neewerlux_theme', 'neewerlux_webui', 'neewerlux_anim_editor',
    ] + bleak_hiddenimports + winrt_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'unittest', 'xmlrpc', 'pydoc', 'doctest',
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtDesigner',
        'PySide6.Qt3D', 'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtMultimedia', 'PySide6.QtWebEngine', 'PySide6.QtPdf',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NeewerLux',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # --console: allows optional console visibility via hideConsoleOnLaunch preference
    # The app hides the console on startup if the preference is enabled.
    # Users who want debug output can disable hideConsoleOnLaunch in Global Preferences.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='com.github.poizenjam.NeewerLux.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NeewerLux',
)
