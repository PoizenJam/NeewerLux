"""Visual Animation Keyframe Editor for NeewerLux.

Provides a GUI dialog for creating/editing animation keyframes
with visual controls instead of raw JSON editing.
"""

import json
import copy

try:
    import PySide6
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QFont, QColor, QBrush
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
        QLabel, QLineEdit, QSpinBox, QCheckBox, QComboBox, QPushButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QDialogButtonBox,
        QTabWidget, QWidget, QTextEdit, QMessageBox, QAbstractItemView,
        QSizePolicy, QSlider, QSplitter
    )
    PYSIDE_VERSION = 6
except ImportError:
    import PySide2
    from PySide2.QtCore import Qt, Signal
    from PySide2.QtGui import QFont, QColor, QBrush
    from PySide2.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
        QLabel, QLineEdit, QSpinBox, QCheckBox, QComboBox, QPushButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QDialogButtonBox,
        QTabWidget, QWidget, QTextEdit, QMessageBox, QAbstractItemView,
        QSizePolicy, QSlider, QSplitter
    )
    PYSIDE_VERSION = 2


def _colorForHSI(hue, sat, bri):
    """Get a QColor for an HSI keyframe."""
    return QColor.fromHsv(hue % 360, int(sat * 2.55), int(bri * 2.55))


def _colorForCCT(temp, bri):
    """Approximate QColor for a CCT value (32-85 scale)."""
    # Map temp 32..85 to warm orange -> cool blue-white
    t = max(0, min(1, (temp - 32) / 53.0))
    r = int(255 - t * 54)
    g = int(147 + t * 79)
    b = int(41 + t * 214)
    factor = bri / 100.0
    return QColor(int(r * factor), int(g * factor), int(b * factor))


try:
    from neewerlux_ui import GradientSlider
except ImportError:
    GradientSlider = None  # fallback handled below


class AnimationEditorDialog(QDialog):
    """Visual animation keyframe editor dialog."""

    def __init__(self, parent=None, animData=None, animName="", cctRange=None):
        super().__init__(parent)
        self.setWindowTitle("Animation Editor" + (": " + animName if animName else ""))
        self.setMinimumSize(700, 550)
        self.resize(780, 620)
        self._cctRange = cctRange or (32, 56)  # min/max in slider units (e.g. 32=3200K)

        self._animData = copy.deepcopy(animData) if animData else {
            "name": animName or "Untitled",
            "description": "",
            "loop": True,
            "keyframes": []
        }
        self._keyframes = self._animData.get("keyframes", [])
        self._selectedRow = -1

        self._buildUI()
        self._populateTable()

    def _buildUI(self):
        mainLay = QVBoxLayout(self)
        mainLay.setContentsMargins(10, 10, 10, 10)
        mainLay.setSpacing(8)

        # -- Header form --
        headerForm = QFormLayout()
        headerForm.setSpacing(4)

        self._nameField = QLineEdit(self._animData.get("name", ""))
        headerForm.addRow("Name:", self._nameField)

        self._descField = QLineEdit(self._animData.get("description", ""))
        headerForm.addRow("Description:", self._descField)

        self._loopCheck = QCheckBox("Loop animation")
        self._loopCheck.setChecked(self._animData.get("loop", True))
        headerForm.addRow(self._loopCheck)

        mainLay.addLayout(headerForm)

        # -- Tabs: Visual / JSON --
        self._tabs = QTabWidget()
        mainLay.addWidget(self._tabs, 1)

        # === VISUAL TAB ===
        visualTab = QWidget()
        vLay = QVBoxLayout(visualTab)
        vLay.setContentsMargins(6, 6, 6, 6)
        vLay.setSpacing(6)

        # Light view filter (which light's data to show in table)
        lightFilterRow = QHBoxLayout()
        lightFilterRow.addWidget(QLabel("Show light:"))
        self._lightFilterCombo = QComboBox()
        self._lightFilterCombo.setToolTip("Select which light's parameters to display in the keyframe table")
        self._lightFilterCombo.currentIndexChanged.connect(self._onLightFilterChanged)
        lightFilterRow.addWidget(self._lightFilterCombo, 1)
        lightFilterRow.addStretch(1)
        vLay.addLayout(lightFilterRow)

        # Keyframe table
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(["#", "Mode", "Param 1", "Param 2", "Param 3", "Hold (ms)", "Fade (ms)"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        hdr = self._table.horizontalHeader()
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 32)
        for col in range(1, 7):
            hdr.setSectionResizeMode(col, QHeaderView.Stretch)
        self._table.selectionModel().selectionChanged.connect(self._onRowSelected)
        vLay.addWidget(self._table, 2)

        # Frame toolbar
        frameBtns = QHBoxLayout()
        frameBtns.setSpacing(4)
        self._addFrameBtn = QPushButton("+ Add Frame")
        self._addFrameBtn.clicked.connect(self._addFrame)
        self._dupFrameBtn = QPushButton("Duplicate")
        self._dupFrameBtn.clicked.connect(self._duplicateFrame)
        self._delFrameBtn = QPushButton("Delete")
        self._delFrameBtn.clicked.connect(self._deleteFrame)
        self._moveUpBtn = QPushButton("\u25B2 Up")
        self._moveUpBtn.clicked.connect(lambda: self._moveFrame(-1))
        self._moveDownBtn = QPushButton("\u25BC Down")
        self._moveDownBtn.clicked.connect(lambda: self._moveFrame(1))
        self._copyFrameBtn = QPushButton("Copy")
        self._copyFrameBtn.setToolTip("Copy current light's settings from selected frame")
        self._copyFrameBtn.clicked.connect(self._copyFrameSettings)
        self._pasteFrameBtn = QPushButton("Paste")
        self._pasteFrameBtn.setToolTip("Paste copied settings to selected frame's current light")
        self._pasteFrameBtn.clicked.connect(self._pasteFrameSettings)
        self._pasteFrameBtn.setEnabled(False)
        for btn in [self._addFrameBtn, self._dupFrameBtn, self._delFrameBtn, self._moveUpBtn, self._moveDownBtn, self._copyFrameBtn, self._pasteFrameBtn]:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            frameBtns.addWidget(btn)
        vLay.addLayout(frameBtns)

        # -- Frame editor panel --
        editorBox = QWidget()
        editorBox.setObjectName("frameEditor")
        editorLay = QVBoxLayout(editorBox)
        editorLay.setContentsMargins(8, 8, 8, 8)
        editorLay.setSpacing(6)

        editorLay.addWidget(QLabel("<b>Frame Properties</b>"))

        formGrid = QGridLayout()
        formGrid.setSpacing(6)

        # Light target selector (replaces old text field)
        formGrid.addWidget(QLabel("Light:"), 0, 0)
        self._lightCombo = QComboBox()
        self._lightCombo.setToolTip("Select which light target to edit within this keyframe")
        self._lightCombo.currentIndexChanged.connect(self._onLightTargetChanged)
        formGrid.addWidget(self._lightCombo, 0, 1)
        lightBtnRow = QHBoxLayout(); lightBtnRow.setSpacing(4)
        self._addLightBtn = QPushButton("+ Light")
        self._addLightBtn.setToolTip("Add a new light target to this keyframe")
        self._addLightBtn.clicked.connect(self._addLightTarget)
        self._removeLightBtn = QPushButton("- Light")
        self._removeLightBtn.setToolTip("Remove the current light target from this keyframe")
        self._removeLightBtn.clicked.connect(self._removeLightTarget)
        lightBtnRow.addWidget(self._addLightBtn)
        lightBtnRow.addWidget(self._removeLightBtn)
        formGrid.addLayout(lightBtnRow, 0, 2, 1, 2)

        # Per-light params storage: {lightKey: {mode, hue, sat, bri, temp, scene}}
        self._perLightParams = {}
        self._currentLightKey = "*"
        self._clipboardParams = None  # for copy/paste

        # Build light filter from animation data
        self._rebuildLightFilter()

        # Mode selector
        formGrid.addWidget(QLabel("Mode:"), 1, 0)
        self._modeCombo = QComboBox()
        self._modeCombo.addItems(["HSI", "CCT", "Scene", "ON", "OFF"])
        self._modeCombo.currentTextChanged.connect(self._onModeChanged)
        formGrid.addWidget(self._modeCombo, 1, 1)

        # Hold / Fade
        formGrid.addWidget(QLabel("Hold:"), 1, 2)
        self._holdSpin = QSpinBox()
        self._holdSpin.setRange(0, 60000)
        self._holdSpin.setValue(200)
        self._holdSpin.setSuffix(" ms")
        self._holdSpin.setButtonSymbols(QSpinBox.NoButtons)
        formGrid.addWidget(self._holdSpin, 1, 3)

        formGrid.addWidget(QLabel("Fade:"), 2, 2)
        self._fadeSpin = QSpinBox()
        self._fadeSpin.setRange(0, 60000)
        self._fadeSpin.setValue(0)
        self._fadeSpin.setSuffix(" ms")
        self._fadeSpin.setButtonSymbols(QSpinBox.NoButtons)
        formGrid.addWidget(self._fadeSpin, 2, 3)

        # Standard gradient stops for animation editor
        _stopsHue = [(0.0, QColor(255,0,0)), (0.16, QColor(255,255,0)), (0.33, QColor(0,255,0)),
                     (0.49, QColor(0,255,255)), (0.66, QColor(0,0,255)), (0.83, QColor(255,0,255)), (1.0, QColor(255,0,0))]
        _stopsBri = [(0.0, QColor(0,0,0)), (1.0, QColor(255,255,255))]
        _stopsSat = [(0.0, QColor(255,255,255)), (1.0, QColor(255,0,0))]
        _stopsCCT = [(0.0, QColor(255,147,41)), (1.0, QColor(201,226,255))]

        # Param gradient sliders (change based on mode)
        self._p1Label = QLabel("Hue:")
        formGrid.addWidget(self._p1Label, 2, 0)
        if GradientSlider:
            self._p1Spin = GradientSlider(0, 360, 240, "\u00B0",
                gradientStops=_stopsHue, minLabel="0\u00B0", maxLabel="360\u00B0")
        else:
            self._p1Spin = QSpinBox(); self._p1Spin.setRange(0, 360); self._p1Spin.setValue(240)
            self._p1Spin.setButtonSymbols(QSpinBox.NoButtons)
        formGrid.addWidget(self._p1Spin, 2, 1)

        self._p2Label = QLabel("Sat:")
        formGrid.addWidget(self._p2Label, 3, 0)
        if GradientSlider:
            self._p2Spin = GradientSlider(0, 100, 100, "%",
                gradientStops=_stopsSat, minLabel="0", maxLabel="100")
        else:
            self._p2Spin = QSpinBox(); self._p2Spin.setRange(0, 100); self._p2Spin.setValue(100)
            self._p2Spin.setButtonSymbols(QSpinBox.NoButtons)
        formGrid.addWidget(self._p2Spin, 3, 1)

        self._p3Label = QLabel("Bri:")
        formGrid.addWidget(self._p3Label, 3, 2)
        if GradientSlider:
            self._p3Spin = GradientSlider(0, 100, 100, "%",
                gradientStops=_stopsBri, minLabel="0", maxLabel="100")
        else:
            self._p3Spin = QSpinBox(); self._p3Spin.setRange(0, 100); self._p3Spin.setValue(100)
            self._p3Spin.setButtonSymbols(QSpinBox.NoButtons)
        formGrid.addWidget(self._p3Spin, 3, 3)

        # Store gradient sets for mode switching
        self._gradHue = _stopsHue
        self._gradSat = _stopsSat
        self._gradBri = _stopsBri
        self._gradCCT = _stopsCCT

        # Scene dropdown (shown in ANM/Scene mode instead of p1 slider)
        self._sceneCombo = QComboBox()
        self._sceneCombo.addItems(["1: Police", "2: Ambulance", "3: Fire Truck", "4: Fireworks",
            "5: Party", "6: Candlelight", "7: Lightning", "8: Paparazzi", "9: TV Screen"])
        self._sceneCombo.setVisible(False)
        formGrid.addWidget(self._sceneCombo, 2, 1)

        editorLay.addLayout(formGrid)

        # Color preview
        self._colorPreview = QLabel("")
        self._colorPreview.setFixedHeight(24)
        self._colorPreview.setStyleSheet("background-color: #3c3cf0; border-radius: 4px;")
        editorLay.addWidget(self._colorPreview)

        # Apply button
        applyBtn = QPushButton("Apply to Selected Frame")
        applyBtn.clicked.connect(self._applyToFrame)
        editorLay.addWidget(applyBtn)

        vLay.addWidget(editorBox)

        self._tabs.addTab(visualTab, "Visual Editor")

        # Connect preview updates
        for spin in [self._p1Spin, self._p2Spin, self._p3Spin]:
            spin.valueChanged.connect(self._updatePreview)
        self._modeCombo.currentTextChanged.connect(self._updatePreview)

        # === JSON TAB ===
        jsonTab = QWidget()
        jLay = QVBoxLayout(jsonTab)
        jLay.setContentsMargins(6, 6, 6, 6)
        self._jsonEdit = QTextEdit()
        self._jsonEdit.setFont(QFont("Consolas", 9))
        jLay.addWidget(self._jsonEdit)

        jsonBtnRow = QHBoxLayout()
        syncFromJson = QPushButton("Apply JSON \u2192 Visual")
        syncFromJson.clicked.connect(self._syncFromJSON)
        syncToJson = QPushButton("Visual \u2192 JSON")
        syncToJson.clicked.connect(self._syncToJSON)
        jsonBtnRow.addWidget(syncToJson)
        jsonBtnRow.addWidget(syncFromJson)
        jLay.addLayout(jsonBtnRow)

        self._tabs.addTab(jsonTab, "JSON Editor")

        # Sync JSON initially
        self._syncToJSON()

        # -- Dialog buttons --
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._onSave)
        buttons.rejected.connect(self.reject)
        mainLay.addWidget(buttons)

    def _rebuildLightFilter(self):
        """Rebuild the light filter combo from all unique light keys across all keyframes."""
        allKeys = set()
        for kf in self._keyframes:
            for key in kf.get("lights", {}).keys():
                allKeys.add(key)
        if not allKeys:
            allKeys.add("*")

        self._lightFilterCombo.blockSignals(True)
        prev = self._lightFilterCombo.currentData()
        self._lightFilterCombo.clear()
        for key in sorted(allKeys, key=lambda k: (k != "*", k)):
            label = "All Lights" if key == "*" else ("Light " + str(key))
            self._lightFilterCombo.addItem(label, key)
        # Restore previous selection if still valid
        for i in range(self._lightFilterCombo.count()):
            if self._lightFilterCombo.itemData(i) == prev:
                self._lightFilterCombo.setCurrentIndex(i)
                break
        self._lightFilterCombo.blockSignals(False)
        self._currentLightKey = self._lightFilterCombo.currentData() or "*"

    def _onLightFilterChanged(self, idx):
        """When the table's light filter combo changes, refresh the table."""
        self._currentLightKey = self._lightFilterCombo.currentData() or "*"
        self._populateTable()

    def _copyFrameSettings(self):
        """Copy the current light's params from the selected keyframe."""
        if self._selectedRow < 0 or self._selectedRow >= len(self._keyframes):
            return
        kf = self._keyframes[self._selectedRow]
        lights = kf.get("lights", {})
        key = self._currentLightKey
        if key in lights:
            self._clipboardParams = copy.deepcopy(lights[key])
        elif lights:
            self._clipboardParams = copy.deepcopy(lights[list(lights.keys())[0]])
        else:
            return
        self._pasteFrameBtn.setEnabled(True)
        self._pasteFrameBtn.setToolTip("Paste: " + self._clipboardParams.get("mode", "?") + " settings")

    def _pasteFrameSettings(self):
        """Paste copied params to the selected keyframe's current light."""
        if not self._clipboardParams or self._selectedRow < 0:
            return
        if self._selectedRow >= len(self._keyframes):
            return
        kf = self._keyframes[self._selectedRow]
        key = self._currentLightKey
        if "lights" not in kf:
            kf["lights"] = {}
        kf["lights"][key] = copy.deepcopy(self._clipboardParams)
        self._setTableRow(self._selectedRow, kf)
        # Reload editor if this row is selected
        self._perLightParams = copy.deepcopy(kf["lights"])
        self._loadLightParams(key)

    def _populateTable(self):
        """Fill the table from self._keyframes."""
        self._rebuildLightFilter()
        self._table.setRowCount(len(self._keyframes))
        for i, kf in enumerate(self._keyframes):
            self._setTableRow(i, kf)

    def _setTableRow(self, row, kf):
        """Set one table row from a keyframe dict, showing the currently selected light."""
        lights = kf.get("lights", {})
        hold = kf.get("hold_ms", 200)
        fade = kf.get("fade_ms", 0)

        # Show params for the currently selected light, or first light as fallback
        lightKey = self._currentLightKey
        if lightKey in lights:
            params = lights[lightKey]
        elif lights:
            params = lights[list(lights.keys())[0]]
        else:
            params = {}

        # Show light count indicator
        lightCount = len(lights)
        lightIndicator = "" if lightCount <= 1 else " [" + str(lightCount) + " lights]"

        mode = params.get("mode", "?").upper()

        # Frame number
        numItem = QTableWidgetItem(str(row + 1))
        numItem.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, 0, numItem)

        # Mode
        modeItem = QTableWidgetItem(mode + lightIndicator)
        modeItem.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, 1, modeItem)

        # Params based on mode
        if mode == "HSI":
            p1 = str(params.get("hue", 0)) + "\u00B0"
            p2 = str(params.get("sat", 100)) + "%"
            p3 = str(params.get("bri", 100)) + "%"
            color = _colorForHSI(params.get("hue", 0), params.get("sat", 100), params.get("bri", 100))
        elif mode == "CCT":
            p1 = str(params.get("temp", 56) * 100) + "K"
            p2 = str(params.get("bri", 100)) + "%"
            p3 = ""
            color = _colorForCCT(params.get("temp", 56), params.get("bri", 100))
        elif mode in ("ANM", "SCENE"):
            p1 = "Scene " + str(params.get("scene", 1))
            p2 = str(params.get("bri", 100)) + "%"
            p3 = ""
            color = QColor(145, 0, 255, 120)
        elif mode in ("ON", "OFF"):
            p1 = ""
            p2 = ""
            p3 = ""
            color = QColor(0, 255, 145) if mode == "ON" else QColor(80, 80, 80)
        else:
            p1 = p2 = p3 = ""
            color = QColor(60, 60, 60)

        self._table.setItem(row, 2, QTableWidgetItem(p1))
        self._table.setItem(row, 3, QTableWidgetItem(p2))
        self._table.setItem(row, 4, QTableWidgetItem(p3))
        self._table.setItem(row, 5, QTableWidgetItem(str(hold)))
        self._table.setItem(row, 6, QTableWidgetItem(str(fade)))

        # Color the mode cell background
        if color:
            brush = QBrush(color)
            self._table.item(row, 1).setBackground(brush)
            # Make text readable
            lum = color.red() * 0.299 + color.green() * 0.587 + color.blue() * 0.114
            self._table.item(row, 1).setForeground(QBrush(QColor(0, 0, 0) if lum > 128 else QColor(255, 255, 255)))

    def _onRowSelected(self):
        """Load selected keyframe into the editor panel with per-light support."""
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            self._selectedRow = -1
            return
        row = rows[0].row()
        self._selectedRow = row

        if row >= len(self._keyframes):
            return

        kf = self._keyframes[row]
        lights = kf.get("lights", {})
        self._holdSpin.setValue(kf.get("hold_ms", 200))
        self._fadeSpin.setValue(kf.get("fade_ms", 0))

        # Store per-light params for this keyframe
        self._perLightParams = copy.deepcopy(lights)

        # Populate light combo
        self._lightCombo.blockSignals(True)
        self._lightCombo.clear()
        if lights:
            for key in lights.keys():
                label = "All Lights" if key == "*" else ("Light " + str(key))
                self._lightCombo.addItem(label, key)
        else:
            self._lightCombo.addItem("All Lights", "*")
            self._perLightParams["*"] = {"mode": "HSI", "hue": 240, "sat": 100, "bri": 100}
        self._lightCombo.blockSignals(False)

        # Load first light target into editor
        self._currentLightKey = self._lightCombo.currentData() or "*"
        self._loadLightParams(self._currentLightKey)
        self._updateRemoveLightBtn()

    def _onModeChanged(self, mode):
        """Update editor labels/ranges/gradients based on selected mode."""
        mode = mode.upper()
        _hasGrad = hasattr(self._p1Spin, 'setGradientStops')
        _hasSuffix = hasattr(self._p1Spin, 'setSuffix')
        if mode == "HSI":
            self._p1Label.setText("Hue:")
            self._p1Spin.setRange(0, 360)
            self._p1Spin.setVisible(True)
            self._sceneCombo.setVisible(False)
            if _hasSuffix: self._p1Spin.setSuffix("\u00B0")
            if _hasGrad:
                self._p1Spin.setGradientStops(self._gradHue)
                self._p1Spin.setMinMaxLabels("0\u00B0", "360\u00B0")
            self._p2Label.setText("Sat:")
            self._p2Spin.setRange(0, 100)
            self._p2Spin.setVisible(True)
            if _hasSuffix: self._p2Spin.setSuffix("%")
            if _hasGrad:
                self._p2Spin.setGradientStops(self._gradSat)
                self._p2Spin.setMinMaxLabels("0", "100")
            self._p3Label.setText("Bri:")
            self._p3Spin.setRange(0, 100)
            self._p3Spin.setVisible(True)
            if _hasSuffix: self._p3Spin.setSuffix("%")
            if _hasGrad:
                self._p3Spin.setGradientStops(self._gradBri)
                self._p3Spin.setMinMaxLabels("0", "100")
        elif mode == "CCT":
            self._p1Label.setText("Temp:")
            self._p1Spin.setRange(self._cctRange[0], self._cctRange[1])
            self._p1Spin.setVisible(True)
            self._sceneCombo.setVisible(False)
            if _hasSuffix: self._p1Spin.setSuffix("00K")
            if _hasGrad:
                self._p1Spin.setGradientStops(self._gradCCT)
                self._p1Spin.setMinMaxLabels(str(self._cctRange[0]*100)+"K", str(self._cctRange[1]*100)+"K")
            self._p2Label.setText("Bri:")
            self._p2Spin.setRange(0, 100)
            self._p2Spin.setVisible(True)
            if _hasSuffix: self._p2Spin.setSuffix("%")
            if _hasGrad:
                self._p2Spin.setGradientStops(self._gradBri)
                self._p2Spin.setMinMaxLabels("0", "100")
            self._p3Label.setText("")
            self._p3Spin.setVisible(False)
        elif mode in ("ANM", "SCENE"):
            self._p1Label.setText("Scene:")
            self._p1Spin.setVisible(False)
            self._sceneCombo.setVisible(True)
            self._p2Label.setText("Bri:")
            self._p2Spin.setRange(0, 100)
            self._p2Spin.setVisible(True)
            if _hasSuffix: self._p2Spin.setSuffix("%")
            if _hasGrad:
                self._p2Spin.setGradientStops(self._gradBri)
                self._p2Spin.setMinMaxLabels("0", "100")
            self._p3Label.setText("")
            self._p3Spin.setVisible(False)
        else:  # ON / OFF
            self._p1Label.setText("")
            self._p1Spin.setVisible(False)
            self._sceneCombo.setVisible(False)
            self._p2Label.setText("")
            self._p2Spin.setVisible(False)
            self._p3Label.setText("")
            self._p3Spin.setVisible(False)

        self._updatePreview()

    def _updatePreview(self):
        """Update the color preview bar."""
        mode = self._modeCombo.currentText().upper()
        if mode == "HSI":
            color = _colorForHSI(self._p1Spin.value(), self._p2Spin.value(), self._p3Spin.value())
        elif mode == "CCT":
            color = _colorForCCT(self._p1Spin.value(), self._p2Spin.value())
        elif mode in ("ANM", "SCENE"):
            color = QColor(145, 0, 255)
        elif mode == "ON":
            color = QColor(0, 255, 145)
        else:
            color = QColor(60, 60, 60)
        self._colorPreview.setStyleSheet(f"background-color: {color.name()}; border-radius: 4px;")

    def _readCurrentParams(self):
        """Read current editor controls into a params dict."""
        mode = self._modeCombo.currentText().upper()
        if mode == "HSI":
            return {"mode": "HSI", "hue": self._p1Spin.value(),
                    "sat": self._p2Spin.value(), "bri": self._p3Spin.value()}
        elif mode == "CCT":
            return {"mode": "CCT", "temp": self._p1Spin.value(),
                    "bri": self._p2Spin.value()}
        elif mode in ("ANM", "SCENE"):
            return {"mode": "ANM", "scene": self._sceneCombo.currentIndex() + 1,
                    "bri": self._p2Spin.value()}
        elif mode == "ON":
            return {"mode": "ON"}
        else:
            return {"mode": "OFF"}

    def _saveLightParams(self):
        """Save current editor state back to _perLightParams for the current light."""
        if self._currentLightKey:
            self._perLightParams[self._currentLightKey] = self._readCurrentParams()

    def _loadLightParams(self, lightKey):
        """Load a specific light's params from _perLightParams into the editor controls."""
        params = self._perLightParams.get(lightKey, {"mode": "HSI", "hue": 240, "sat": 100, "bri": 100})
        self._currentLightKey = lightKey

        mode = params.get("mode", "HSI").upper()
        if mode == "ANM":
            mode = "SCENE"
        self._modeCombo.blockSignals(True)
        idx = self._modeCombo.findText(mode, Qt.MatchFixedString)
        if idx >= 0:
            self._modeCombo.setCurrentIndex(idx)
        self._modeCombo.blockSignals(False)

        self._onModeChanged(mode)

        if mode == "HSI":
            self._p1Spin.setValue(params.get("hue", 0))
            self._p2Spin.setValue(params.get("sat", 100))
            self._p3Spin.setValue(params.get("bri", 100))
        elif mode == "CCT":
            self._p1Spin.setValue(params.get("temp", 56))
            self._p2Spin.setValue(params.get("bri", 100))
        elif mode in ("ANM", "SCENE"):
            self._sceneCombo.setCurrentIndex(max(0, params.get("scene", 1) - 1))
            self._p2Spin.setValue(params.get("bri", 100))

        self._updatePreview()

    def _onLightTargetChanged(self, comboIdx):
        """Save current light params, switch to newly selected light, load its params."""
        if comboIdx < 0:
            return
        # Save the previous light's params
        self._saveLightParams()
        # Load the newly selected light
        newKey = self._lightCombo.currentData()
        if newKey:
            self._loadLightParams(newKey)
        self._updateRemoveLightBtn()

    def _addLightTarget(self):
        """Add a new light target to the current keyframe."""
        # Save current light first
        self._saveLightParams()
        existing = set(self._perLightParams.keys())
        hasWildcard = "*" in existing
        hasSpecific = any(k != "*" for k in existing)

        # Find a sensible default for the new key
        if not existing:
            newKey = "*"
        elif hasWildcard:
            # Currently have "*" — adding a specific light means replacing wildcard
            # with per-light entries. Suggest "1".
            newKey = "1"
        else:
            # Have specific lights — suggest next unused number
            newKey = None
            for i in range(1, 20):
                if str(i) not in existing:
                    newKey = str(i)
                    break
            if not newKey:
                return

        # Prompt for light ID
        try:
            from PySide6.QtWidgets import QInputDialog
        except ImportError:
            from PySide2.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "Add Light Target",
            "Light ID (number or name).\nUse * for all lights (only if no other lights defined).",
            text=newKey)
        if not ok or not text.strip():
            return
        newKey = text.strip()

        # Validation
        if newKey in self._perLightParams:
            QMessageBox.warning(self, "Duplicate", "Light '" + newKey + "' already exists in this keyframe.")
            return
        if newKey == "*" and hasSpecific:
            QMessageBox.warning(self, "Conflict",
                "'All Lights (*)' cannot be combined with specific light targets.\n"
                "Remove the specific lights first, or use a specific light ID.")
            return
        if newKey != "*" and hasWildcard:
            # Auto-convert: remove wildcard, copy its params as default for the new specific light
            wildcardParams = self._perLightParams.pop("*", {})
            # Remove "*" from combo
            for ci in range(self._lightCombo.count()):
                if self._lightCombo.itemData(ci) == "*":
                    self._lightCombo.blockSignals(True)
                    self._lightCombo.removeItem(ci)
                    self._lightCombo.blockSignals(False)
                    break
            # Re-add old wildcard params as light "1" if that's not our new key
            if "1" != newKey and "1" not in self._perLightParams:
                self._perLightParams["1"] = copy.deepcopy(wildcardParams)
                self._lightCombo.blockSignals(True)
                self._lightCombo.addItem("Light 1", "1")
                self._lightCombo.blockSignals(False)

            # Use wildcard params as default for the new key
            self._perLightParams[newKey] = copy.deepcopy(wildcardParams)
        else:
            # Normal add
            self._perLightParams[newKey] = {"mode": "HSI", "hue": 240, "sat": 100, "bri": 100}

        label = "All Lights" if newKey == "*" else ("Light " + str(newKey))
        self._lightCombo.blockSignals(True)
        self._lightCombo.addItem(label, newKey)
        self._lightCombo.setCurrentIndex(self._lightCombo.count() - 1)
        self._lightCombo.blockSignals(False)
        self._loadLightParams(newKey)
        self._updateRemoveLightBtn()

    def _removeLightTarget(self):
        """Remove the currently selected light target."""
        if self._lightCombo.count() <= 1:
            return
        key = self._lightCombo.currentData()
        self._perLightParams.pop(key, None)
        self._lightCombo.blockSignals(True)
        self._lightCombo.removeItem(self._lightCombo.currentIndex())
        self._lightCombo.blockSignals(False)
        # Load whatever is now selected
        self._currentLightKey = self._lightCombo.currentData() or "*"
        self._loadLightParams(self._currentLightKey)
        self._updateRemoveLightBtn()

    def _updateRemoveLightBtn(self):
        """Disable remove button when only one light target remains."""
        self._removeLightBtn.setEnabled(self._lightCombo.count() > 1)

    def _buildKeyframeDict(self):
        """Build a keyframe dict from per-light params and hold/fade values."""
        # Save the currently displayed light's params first
        self._saveLightParams()
        return {
            "hold_ms": self._holdSpin.value(),
            "fade_ms": self._fadeSpin.value(),
            "lights": copy.deepcopy(self._perLightParams)
        }

    def _addFrame(self):
        """Add a new frame at the end."""
        # If no per-light params exist yet (no row selected), create a default
        if not self._perLightParams:
            self._perLightParams = {"*": self._readCurrentParams()}
            self._currentLightKey = "*"
        kf = self._buildKeyframeDict()
        self._keyframes.append(kf)
        self._populateTable()
        self._table.selectRow(len(self._keyframes) - 1)
        self._syncToJSON()

    def _duplicateFrame(self):
        """Duplicate the selected frame."""
        if self._selectedRow < 0 or self._selectedRow >= len(self._keyframes):
            return
        kf = copy.deepcopy(self._keyframes[self._selectedRow])
        self._keyframes.insert(self._selectedRow + 1, kf)
        self._populateTable()
        self._table.selectRow(self._selectedRow + 1)
        self._syncToJSON()

    def _deleteFrame(self):
        """Delete the selected frame."""
        if self._selectedRow < 0 or self._selectedRow >= len(self._keyframes):
            return
        self._keyframes.pop(self._selectedRow)
        self._populateTable()
        if self._keyframes:
            self._table.selectRow(min(self._selectedRow, len(self._keyframes) - 1))
        self._selectedRow = -1
        self._syncToJSON()

    def _moveFrame(self, direction):
        """Move selected frame up (-1) or down (+1)."""
        row = self._selectedRow
        if row < 0 or row >= len(self._keyframes):
            return
        newRow = row + direction
        if newRow < 0 or newRow >= len(self._keyframes):
            return
        self._keyframes[row], self._keyframes[newRow] = self._keyframes[newRow], self._keyframes[row]
        self._populateTable()
        self._table.selectRow(newRow)
        self._syncToJSON()

    def _applyToFrame(self):
        """Apply current editor settings to the selected frame."""
        if self._selectedRow < 0 or self._selectedRow >= len(self._keyframes):
            return
        self._saveLightParams()  # save current light's params first
        kf = self._buildKeyframeDict()
        self._keyframes[self._selectedRow] = kf
        self._setTableRow(self._selectedRow, kf)
        self._syncToJSON()

    def _syncToJSON(self):
        """Update JSON tab from the visual keyframes."""
        self._jsonEdit.setPlainText(json.dumps(self._keyframes, indent=2))

    def _syncFromJSON(self):
        """Parse JSON tab and update the visual table."""
        try:
            parsed = json.loads(self._jsonEdit.toPlainText())
            if not isinstance(parsed, list):
                raise ValueError("Must be a JSON array")
            self._keyframes = parsed
            self._perLightParams = {}
            self._currentLightKey = "*"
            self._populateTable()
        except (json.JSONDecodeError, ValueError) as e:
            QMessageBox.warning(self, "JSON Error", "Invalid keyframes JSON:\n" + str(e))

    def _onSave(self):
        """Validate and accept."""
        # Apply current editor state to the selected frame if one is selected
        if self._selectedRow >= 0 and self._selectedRow < len(self._keyframes):
            self._saveLightParams()
            kf = self._buildKeyframeDict()
            self._keyframes[self._selectedRow] = kf

        # Sync from whichever tab is active
        if self._tabs.currentIndex() == 1:  # JSON tab is active
            try:
                parsed = json.loads(self._jsonEdit.toPlainText())
                if not isinstance(parsed, list):
                    raise ValueError("Must be a JSON array")
                self._keyframes = parsed
            except (json.JSONDecodeError, ValueError) as e:
                QMessageBox.warning(self, "JSON Error", "Fix the JSON before saving:\n" + str(e))
                return

        # Sanitize all keyframes: remove contradictory light targets
        for kf in self._keyframes:
            lights = kf.get("lights", {})
            if len(lights) > 1 and "*" in lights:
                # Wildcard mixed with specific lights — remove wildcard
                lights.pop("*")
            # Remove duplicate keys (shouldn't happen, but defensive)
            if not lights:
                lights["*"] = {"mode": "HSI", "hue": 240, "sat": 100, "bri": 100}
            kf["lights"] = lights

        self._syncToJSON()
        self.accept()

    def getResult(self):
        """Return the edited animation data."""
        return {
            "name": self._nameField.text().strip() or "Untitled",
            "description": self._descField.text().strip(),
            "loop": self._loopCheck.isChecked(),
            "keyframes": self._keyframes
        }
