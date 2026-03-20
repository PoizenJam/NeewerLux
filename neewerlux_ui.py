"""NeewerLux UI — PJ Overhaul (Layout-based, Resizable, Themed)

Completely rewritten from fixed QRect geometry to QLayout managers.
All widget attribute names are preserved for backward compatibility
with NeewerLux.py signal connections.
"""

try:
    import PySide6
    from PySide6.QtCore import Qt, Signal, QSize
    from PySide6.QtGui import QFont, QColor, QLinearGradient, QBrush, QKeySequence, QIcon, QPainter
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
        QSplitter, QSizePolicy, QAbstractItemView, QAbstractScrollArea,
        QPushButton, QLabel, QSlider, QTableWidget, QTableWidgetItem,
        QTabWidget, QCheckBox, QLineEdit, QTextEdit, QSpinBox, QComboBox,
        QGraphicsView, QGraphicsScene, QScrollArea, QKeySequenceEdit,
        QListWidget, QListWidgetItem, QStatusBar, QHeaderView, QFrame,
        QSystemTrayIcon, QMenu, QTextBrowser
    )
    customSignal = Signal
except ImportError:
    try:
        import PySide2
        from PySide2.QtCore import Qt, Signal, QSize
        from PySide2.QtGui import QFont, QColor, QLinearGradient, QBrush, QKeySequence, QIcon, QPainter
        from PySide2.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
            QSplitter, QSizePolicy, QAbstractItemView, QAbstractScrollArea,
            QPushButton, QLabel, QSlider, QTableWidget, QTableWidgetItem,
            QTabWidget, QCheckBox, QLineEdit, QTextEdit, QSpinBox, QComboBox,
            QGraphicsView, QGraphicsScene, QScrollArea, QKeySequenceEdit,
            QListWidget, QListWidgetItem, QStatusBar, QHeaderView, QFrame,
            QSystemTrayIcon, QMenu, QTextBrowser
        )
        customSignal = Signal
    except ImportError:
        raise  # let it propagate — NeewerLux.py will handle the error


# === HELPER WIDGETS ===

class SpinBoxWithButtons(QWidget):
    """QSpinBox with external +/- buttons to avoid overlap issues at high DPI."""
    valueChanged = customSignal(int)

    def __init__(self, parent=None, minVal=0, maxVal=100, value=0, suffix=""):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self._spin = QSpinBox()
        self._spin.setRange(minVal, maxVal)
        self._spin.setValue(value)
        if suffix:
            self._spin.setSuffix(suffix)
        self._spin.setButtonSymbols(QSpinBox.NoButtons)
        self._spin.valueChanged.connect(self.valueChanged.emit)

        btnStyle = "QPushButton { font-size: 14px; font-weight: bold; min-width: 28px; }"
        self._minus = QPushButton("-")
        self._minus.setStyleSheet(btnStyle)
        self._minus.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._minus.setFixedWidth(30)
        self._minus.clicked.connect(lambda: self._spin.setValue(self._spin.value() - self._spin.singleStep()))
        self._plus = QPushButton("+")
        self._plus.setStyleSheet(btnStyle)
        self._plus.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._plus.setFixedWidth(30)
        self._plus.clicked.connect(lambda: self._spin.setValue(self._spin.value() + self._spin.singleStep()))

        lay.addWidget(self._spin, 1)
        lay.addWidget(self._minus)
        lay.addWidget(self._plus)

    def value(self):
        return self._spin.value()

    def setValue(self, v):
        self._spin.setValue(v)

    def setRange(self, lo, hi):
        self._spin.setRange(lo, hi)

    def setSuffix(self, s):
        self._spin.setSuffix(s)

    def setSingleStep(self, s):
        self._spin.setSingleStep(s)

    def setToolTip(self, t):
        self._spin.setToolTip(t)
        self._minus.setToolTip(t)
        self._plus.setToolTip(t)

    def setMinimumWidth(self, w):
        self._spin.setMinimumWidth(w)


class customPresetButton(QPushButton):
    rightclicked = customSignal()
    middleclicked = customSignal()
    enteredWidget = customSignal()
    leftWidget = customSignal()

    def __init__(self, parent=None, text=""):
        super().__init__(parent)
        self.setText(text)
        self.setProperty("presetButton", True)
        self.setProperty("presetType", "default")

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.rightclicked.emit()
        elif event.button() == Qt.MiddleButton:
            self.middleclicked.emit()
        else:
            super().mousePressEvent(event)

    def enterEvent(self, event):
        self.enteredWidget.emit()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.leftWidget.emit()
        super().leaveEvent(event)

    def markCustom(self, presetNum, isSnap=0, presetName=""):
        """Update the button display text and type property for QSS styling.
        isSnap: 0 = custom global, >=1 = snapshot, <0 = reset to default."""
        nameLabel = presetName if presetName else ""
        numStr = str(presetNum + 1)

        if isSnap == 0:  # custom global preset
            if nameLabel:
                self.setText(numStr + "\n" + nameLabel[:16])
            else:
                self.setText(numStr + "\nCUSTOM\nGLOBAL")
            self.setProperty("presetType", "global")
        elif isSnap >= 1:  # snapshot preset
            if nameLabel:
                self.setText(numStr + "\n" + nameLabel[:16])
            else:
                self.setText(numStr + "\nCUSTOM\nSNAP")
            self.setProperty("presetType", "snap")
        else:  # reset to default
            if nameLabel:
                self.setText(numStr + "\n" + nameLabel[:16])
            else:
                self.setText(numStr + "\nPRESET\nGLOBAL")
            self.setProperty("presetType", "default")

        # Force QSS refresh for the new property value
        self.style().unpolish(self)
        self.style().polish(self)


class singleKeySequenceEditCancel(QWidget):
    def __init__(self, defaultValue=""):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.defaultValue = defaultValue
        self.keySequence = QKeySequence(defaultValue)
        self.keyPressField = QKeySequenceEdit(self.keySequence)
        self.keyPressField.keySequenceChanged.connect(self._onChanged)
        lay.addWidget(self.keyPressField)
        resetBtn = QPushButton("X")
        resetBtn.setFixedWidth(24)
        resetBtn.clicked.connect(self.resetValue)
        lay.addWidget(resetBtn)

    def _onChanged(self, seq):
        self.keySequence = seq

    def resetValue(self):
        self.keySequence = QKeySequence(self.defaultValue)
        self.keyPressField.setKeySequence(self.keySequence)

    def setKeySequence(self, seq):
        self.keySequence = QKeySequence(seq) if isinstance(seq, str) else seq
        self.keyPressField.setKeySequence(self.keySequence)

    def getKeySequence(self):
        """Return the current key sequence string from the underlying edit field."""
        return self.keyPressField.keySequence().toString()


class GradientBar(QWidget):
    """A widget that paints a linear gradient that always fills its full width."""
    def __init__(self, stops, parent=None):
        """stops: list of (position, QColor) tuples, e.g. [(0.0, QColor(255,0,0)), (1.0, QColor(0,0,255))]"""
        super().__init__(parent)
        self._stops = stops
        self.setMinimumHeight(16)
        self.setMaximumHeight(20)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setStops(self, stops):
        self._stops = stops
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, self.width(), 0)
        for pos, color in self._stops:
            grad.setColorAt(pos, color)
        p.fillRect(self.rect(), grad)
        p.end()


def _makeGradientBar(stops):
    """Create a GradientBar from a list of (position, QColor) tuples."""
    return GradientBar(stops)


class GradientSlider(QWidget):
    """A slider with a gradient bar above it and min/max endpoint labels below.
    Uses a grid layout so gradient, slider groove, and labels all share the same column width."""
    valueChanged = customSignal(int)

    def __init__(self, minVal=0, maxVal=100, value=50, suffix="",
                 gradientStops=None, minLabel="", maxLabel="", parent=None):
        super().__init__(parent)
        self._suffix = suffix
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(1)
        grid.setColumnStretch(0, 1)  # gradient/slider column expands
        grid.setColumnStretch(1, 0)  # value label column stays fixed

        # Row 0: gradient bar | value label
        if gradientStops:
            self._gradient = GradientBar(gradientStops)
        else:
            self._gradient = GradientBar([(0, QColor(128, 128, 128)), (1, QColor(200, 200, 200))])
        grid.addWidget(self._gradient, 0, 0)
        self._valLabel = QLabel(str(value) + suffix)
        self._valLabel.setFixedWidth(60)
        self._valLabel.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f = QFont(); f.setBold(True); self._valLabel.setFont(f)
        grid.addWidget(self._valLabel, 0, 1)

        # Row 1: slider (spans only column 0 so it matches gradient width)
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(minVal, maxVal)
        self._slider.setValue(value)
        self._slider.setMinimumHeight(18)
        self._slider.valueChanged.connect(self._onChanged)
        grid.addWidget(self._slider, 1, 0)

        # Row 2: min/max labels (column 0 only)
        mmW = QWidget()
        mmRow = QHBoxLayout(mmW)
        mmRow.setContentsMargins(0, 0, 0, 0)
        self._minLabel = QLabel(minLabel or str(minVal))
        sf = QFont(); sf.setPointSize(8)
        self._minLabel.setFont(sf)
        self._minLabel.setAlignment(Qt.AlignLeft)
        self._maxLabel = QLabel(maxLabel or str(maxVal))
        self._maxLabel.setFont(sf)
        self._maxLabel.setAlignment(Qt.AlignRight)
        mmRow.addWidget(self._minLabel)
        mmRow.addStretch(1)
        mmRow.addWidget(self._maxLabel)
        grid.addWidget(mmW, 2, 0)

        # Column stretch: slider/gradient column expands, value label fixed
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0)

    def _onChanged(self, v):
        self._valLabel.setText(str(v) + self._suffix)
        self.valueChanged.emit(v)

    def value(self):
        return self._slider.value()

    def setValue(self, v):
        self._slider.setValue(v)

    def setRange(self, lo, hi):
        self._slider.setRange(lo, hi)
        self._minLabel.setText(str(lo))
        self._maxLabel.setText(str(hi))

    def setGradientStops(self, stops):
        self._gradient.setStops(stops)

    def setMinMaxLabels(self, minTxt, maxTxt):
        self._minLabel.setText(minTxt)
        self._maxLabel.setText(maxTxt)

    def setSuffix(self, suffix):
        self._suffix = suffix
        self._valLabel.setText(str(self._slider.value()) + suffix)

    def setVisible(self, v):
        super().setVisible(v)


# Keep old function for backward compat but unused
def _makeGradientView(gradient, minH=22, maxH=28):
    scene = QGraphicsScene()
    scene.setBackgroundBrush(QBrush(gradient))
    view = QGraphicsView(scene)
    view._scene = scene
    view.setFrameShape(QFrame.NoFrame)
    view.setMinimumHeight(minH)
    view.setMaximumHeight(maxH)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return view


def _addSliderRow(grid, row_offset, label_text, slider, value_label, min_label, max_label, gradient_bar, bold_font=None):
    """Add a slider group (gradient + slider + min/max) to a QGridLayout at row_offset.
    Uses 3 grid rows per slider: gradient row, slider row, min/max row.
    Column 0 = label, Column 1 = gradient/slider/minmax, Column 2 = value.
    All sliders on the same grid share column widths, so everything aligns."""

    # Row 0: label | gradient | value
    lbl = QLabel(label_text)
    lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if bold_font:
        lbl.setFont(bold_font)
    grid.addWidget(lbl, row_offset, 0)
    grid.addWidget(gradient_bar, row_offset, 1)
    value_label.setMinimumWidth(55)
    value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if bold_font:
        value_label.setFont(bold_font)
    grid.addWidget(value_label, row_offset, 2)

    # Row 1: (empty) | slider | (empty)
    slider.setMinimumHeight(18)
    slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    grid.addWidget(slider, row_offset + 1, 1)

    # Row 2: (empty) | min ... max | (empty)
    minmaxRow = QHBoxLayout()
    minmaxRow.setContentsMargins(0, 0, 0, 0)
    min_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
    max_label.setAlignment(Qt.AlignRight | Qt.AlignTop)
    minmaxRow.addWidget(min_label)
    minmaxRow.addStretch(1)
    minmaxRow.addWidget(max_label)
    grid.addLayout(minmaxRow, row_offset + 2, 1)

    return row_offset + 3  # next available row


# === MAIN UI CLASS ===

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        mainFont = QFont()
        mainFont.setBold(True)
        smallFont = QFont()
        smallFont.setPointSize(8)

        # Gradients
        # Gradient stops for GradientBar widgets
        stops_Bri = [(0.0, QColor(0, 0, 0)), (1.0, QColor(255, 255, 255))]

        stops_RGB = [(0.0, QColor(255,0,0)), (0.16, QColor(255,255,0)), (0.33, QColor(0,255,0)),
                     (0.49, QColor(0,255,255)), (0.66, QColor(0,0,255)), (0.83, QColor(255,0,255)), (1.0, QColor(255,0,0))]

        stops_Sat = [(0.0, QColor(255, 255, 255)), (1.0, QColor(255, 0, 0))]

        stops_CCT = [(0.0, QColor(255, 147, 41)), (1.0, QColor(201, 226, 255))]

        # === WINDOW ===
        MainWindow.setMinimumSize(780, 620)
        MainWindow.resize(900, 800)
        MainWindow.setWindowTitle("NeewerLux 1.0.0")

        self.centralwidget = QWidget(MainWindow)
        MainWindow.setCentralWidget(self.centralwidget)
        mainLayout = QVBoxLayout(self.centralwidget)
        mainLayout.setContentsMargins(6, 6, 6, 2)
        mainLayout.setSpacing(4)

        # === TOOLBAR ===
        toolbarWidget = QWidget()
        toolbarWidget.setObjectName("toolbarWidget")
        toolbar = QHBoxLayout(toolbarWidget)
        toolbar.setContentsMargins(4, 4, 4, 4)
        toolbar.setSpacing(4)

        self.turnOffButton = QPushButton("Turn Light(s) Off")
        self.turnOffButton.setEnabled(False)
        toolbar.addWidget(self.turnOffButton)
        self.turnOnButton = QPushButton("Turn Light(s) On")
        self.turnOnButton.setEnabled(False)
        toolbar.addWidget(self.turnOnButton)
        toolbar.addSpacing(10)
        self.scanCommandButton = QPushButton("Scan")
        toolbar.addWidget(self.scanCommandButton)
        self.tryConnectButton = QPushButton("Connect")
        self.tryConnectButton.setEnabled(False)
        toolbar.addWidget(self.tryConnectButton)
        toolbar.addSpacing(6)
        self.selectAllButton = QPushButton("Select All")
        self.selectAllButton.setToolTip("Select all lights in the table")
        toolbar.addWidget(self.selectAllButton)

        toolbar.addStretch(1)

        self.httpToggleBtn = QPushButton("HTTP: OFF")
        self.httpToggleBtn.setObjectName("httpToggleBtn")
        self.httpToggleBtn.setProperty("httpActive", False)
        self.httpToggleBtn.setMinimumWidth(100)
        self.httpToggleBtn.setToolTip("Start/stop the HTTP control server on port 8080")
        toolbar.addWidget(self.httpToggleBtn)

        self.themeToggleBtn = QPushButton("\u263E")
        self.themeToggleBtn.setObjectName("themeToggleBtn")
        self.themeToggleBtn.setFixedWidth(34)
        self.themeToggleBtn.setToolTip("Toggle dark/light theme")
        toolbar.addWidget(self.themeToggleBtn)

        mainLayout.addWidget(toolbarWidget)

        # === SPLITTER ===
        self.mainSplitter = QSplitter(Qt.Vertical)
        self.mainSplitter.setChildrenCollapsible(False)

        # --- LIGHT TABLE ---
        self.lightTable = QTableWidget()
        self.lightTable.setColumnCount(4)
        self.lightTable.setHorizontalHeaderLabels(["Light Name", "MAC Address", "Linked", "Status"])
        self.lightTable.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.lightTable.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.lightTable.setAlternatingRowColors(True)
        self.lightTable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.lightTable.verticalHeader().setStretchLastSection(False)
        hdr = self.lightTable.horizontalHeader()
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        self.lightTable.setMinimumHeight(80)
        self.mainSplitter.addWidget(self.lightTable)

        # --- BOTTOM PANEL (tabs only) ---
        bottomPanel = QWidget()
        bottomLay = QVBoxLayout(bottomPanel)
        bottomLay.setContentsMargins(0, 0, 0, 0)
        bottomLay.setSpacing(4)

        # === PRESETS (own splitter section, resizable) ===
        self.presetScrollArea = QScrollArea()
        self.presetScrollArea.setWidgetResizable(True)
        self.presetScrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.presetScrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.presetScrollArea.setFrameShape(QFrame.NoFrame)
        self.presetScrollArea.setMinimumHeight(68)

        self.customPresetButtonsCW = QWidget()
        # Use a VBox with a grid inside + stretch, so buttons stay top-aligned
        self._presetOuterLay = QVBoxLayout(self.customPresetButtonsCW)
        self._presetOuterLay.setContentsMargins(0, 0, 0, 0)
        self._presetOuterLay.setSpacing(0)
        self.customPresetButtonsLay = QGridLayout()
        self.customPresetButtonsLay.setContentsMargins(0, 0, 0, 0)
        self.customPresetButtonsLay.setSpacing(3)
        for c in range(8):
            self.customPresetButtonsLay.setColumnStretch(c, 1)
        self._presetOuterLay.addLayout(self.customPresetButtonsLay)
        self._presetOuterLay.addStretch(1)  # pushes buttons to top
        self.presetScrollArea.setWidget(self.customPresetButtonsCW)

        self.presetButtons = []

        # === TABS ===
        self.ColorModeTabWidget = QTabWidget()
        self.ColorModeTabWidget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # --- CCT ---
        self.CCT = QWidget()
        cctLay = QVBoxLayout(self.CCT)
        cctLay.setContentsMargins(8, 8, 8, 8)
        cctLay.setSpacing(6)
        cctGrid = QGridLayout()
        cctGrid.setSpacing(2)
        cctGrid.setColumnStretch(1, 1)  # gradient/slider column stretches

        self.Slider_CCT_Hue = QSlider(Qt.Horizontal); self.Slider_CCT_Hue.setRange(32, 56); self.Slider_CCT_Hue.setValue(56)
        self.TFV_CCT_Hue = QLabel("5600K"); self.TFV_CCT_Hue.setFont(mainFont)
        self.TFV_CCT_Hue_Min = QLabel("3200K"); self.TFV_CCT_Hue_Min.setFont(smallFont)
        self.TFV_CCT_Hue_Max = QLabel("5600K"); self.TFV_CCT_Hue_Max.setFont(smallFont)
        self.TFL_CCT_Hue = QLabel("Color Temp")
        self.CCT_Temp_Gradient_BG = _makeGradientBar(stops_CCT)
        row = _addSliderRow(cctGrid, 0, "Color Temp:", self.Slider_CCT_Hue, self.TFV_CCT_Hue,
                            self.TFV_CCT_Hue_Min, self.TFV_CCT_Hue_Max, self.CCT_Temp_Gradient_BG, mainFont)

        self.Slider_CCT_Bright = QSlider(Qt.Horizontal); self.Slider_CCT_Bright.setRange(0, 100); self.Slider_CCT_Bright.setValue(100)
        self.TFV_CCT_Bright = QLabel("100%"); self.TFV_CCT_Bright.setFont(mainFont)
        self.TFV_CCT_Bright_Max = QLabel("100"); self.TFV_CCT_Bright_Max.setFont(smallFont)
        self.TFV_CCT_Bright_Min = QLabel("0"); self.TFV_CCT_Bright_Min.setFont(smallFont)
        self.TFL_CCT_Bright = QLabel("Brightness")
        self.CCT_Bright_Gradient_BG = _makeGradientBar(stops_Bri)
        row = _addSliderRow(cctGrid, row, "Brightness:", self.Slider_CCT_Bright, self.TFV_CCT_Bright,
                            self.TFV_CCT_Bright_Min, self.TFV_CCT_Bright_Max, self.CCT_Bright_Gradient_BG, mainFont)
        cctLay.addLayout(cctGrid)
        cctLay.addStretch(1)
        self.ColorModeTabWidget.addTab(self.CCT, "CCT")

        # --- HSI ---
        self.HSI = QWidget()
        hsiLay = QVBoxLayout(self.HSI)
        hsiLay.setContentsMargins(8, 8, 8, 8)
        hsiLay.setSpacing(6)
        hsiGrid = QGridLayout()
        hsiGrid.setSpacing(2)
        hsiGrid.setColumnStretch(1, 1)

        self.Slider_HSI_1_H = QSlider(Qt.Horizontal); self.Slider_HSI_1_H.setRange(0, 360); self.Slider_HSI_1_H.setValue(240)
        self.TFV_HSI_1_H = QLabel("240\u00BA"); self.TFV_HSI_1_H.setFont(mainFont)
        self.TFV_HSI_1_H_Min = QLabel("0"); self.TFV_HSI_1_H_Min.setFont(smallFont)
        self.TFV_HSI_1_H_Max = QLabel("360"); self.TFV_HSI_1_H_Max.setFont(smallFont)
        self.TFL_HSI_1_H = QLabel("Hue")
        self.HSI_Hue_Gradient_BG = _makeGradientBar(stops_RGB)
        row = _addSliderRow(hsiGrid, 0, "Hue:", self.Slider_HSI_1_H, self.TFV_HSI_1_H,
                            self.TFV_HSI_1_H_Min, self.TFV_HSI_1_H_Max, self.HSI_Hue_Gradient_BG, mainFont)

        self.Slider_HSI_2_S = QSlider(Qt.Horizontal); self.Slider_HSI_2_S.setRange(0, 100); self.Slider_HSI_2_S.setValue(100)
        self.TFV_HSI_2_S = QLabel("100%"); self.TFV_HSI_2_S.setFont(mainFont)
        self.TFV_HSI_2_S_Min = QLabel("0"); self.TFV_HSI_2_S_Min.setFont(smallFont)
        self.TFV_HSI_2_S_Max = QLabel("100"); self.TFV_HSI_2_S_Max.setFont(smallFont)
        self.TFL_HSI_2_S = QLabel("Saturation")
        self.HSI_Sat_Gradient_BG = _makeGradientBar(stops_Sat)
        row = _addSliderRow(hsiGrid, row, "Saturation:", self.Slider_HSI_2_S, self.TFV_HSI_2_S,
                            self.TFV_HSI_2_S_Min, self.TFV_HSI_2_S_Max, self.HSI_Sat_Gradient_BG, mainFont)

        self.Slider_HSI_3_L = QSlider(Qt.Horizontal); self.Slider_HSI_3_L.setRange(0, 100); self.Slider_HSI_3_L.setValue(100)
        self.TFV_HSI_3_L = QLabel("100%"); self.TFV_HSI_3_L.setFont(mainFont)
        self.TFV_HSI_3_L_Min = QLabel("0"); self.TFV_HSI_3_L_Min.setFont(smallFont)
        self.TFV_HSI_3_L_Max = QLabel("100"); self.TFV_HSI_3_L_Max.setFont(smallFont)
        self.TFL_HSI_3_L = QLabel("Intensity")
        self.HSI_Int_Gradient_BG = _makeGradientBar(stops_Bri)
        row = _addSliderRow(hsiGrid, row, "Intensity:", self.Slider_HSI_3_L, self.TFV_HSI_3_L,
                            self.TFV_HSI_3_L_Min, self.TFV_HSI_3_L_Max, self.HSI_Int_Gradient_BG, mainFont)
        hsiLay.addLayout(hsiGrid)
        hsiLay.addStretch(1)
        self.ColorModeTabWidget.addTab(self.HSI, "HSI")

        # --- SCENE ---
        self.ANM = QWidget()
        anmLay = QVBoxLayout(self.ANM)
        anmLay.setContentsMargins(8, 8, 8, 8)
        anmLay.setSpacing(6)

        sceneGrid = QGridLayout(); sceneGrid.setSpacing(4)
        self.Button_1_police_A = QPushButton("1 - Police\n(Red/Blue)")
        self.Button_1_police_B = QPushButton("2 - Ambulance\n(Red/White)")
        self.Button_1_police_C = QPushButton("3 - Fire Truck\n(Red/Orange)")
        self.Button_2_party_A = QPushButton("4 - Fireworks\n(Rainbow)")
        self.Button_2_party_B = QPushButton("5 - Party\n(Rainbow)")
        self.Button_2_party_C = QPushButton("6 - Candlelight\n(Warm White)")
        self.Button_3_lightning_A = QPushButton("7 - Lightning\n(White)")
        self.Button_3_lightning_B = QPushButton("8 - Paparazzi\n(White)")
        self.Button_3_lightning_C = QPushButton("9 - TV Screen\n(White)")
        sceneBtns = [self.Button_1_police_A, self.Button_1_police_B, self.Button_1_police_C,
                     self.Button_2_party_A, self.Button_2_party_B, self.Button_2_party_C,
                     self.Button_3_lightning_A, self.Button_3_lightning_B, self.Button_3_lightning_C]
        for btn in sceneBtns:
            btn.setMinimumHeight(36)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        for i, btn in enumerate(sceneBtns):
            sceneGrid.addWidget(btn, i // 3, i % 3)
        anmLay.addLayout(sceneGrid)

        self.Slider_ANM_Brightness = QSlider(Qt.Horizontal); self.Slider_ANM_Brightness.setRange(0, 100); self.Slider_ANM_Brightness.setValue(100)
        self.TFV_ANM_Brightness = QLabel("100%"); self.TFV_ANM_Brightness.setFont(mainFont)
        self.TFV_ANM_Brightness_Min = QLabel("0"); self.TFV_ANM_Brightness_Min.setFont(smallFont)
        self.TFV_ANM_Brightness_Max = QLabel("100"); self.TFV_ANM_Brightness_Max.setFont(smallFont)
        self.TFL_ANM_Brightness = QLabel("Brightness")
        self.ANM_Brightness_Gradient_BG = _makeGradientBar(stops_Bri)
        anmGrid = QGridLayout()
        anmGrid.setSpacing(2)
        anmGrid.setColumnStretch(1, 1)
        _addSliderRow(anmGrid, 0, "Brightness:", self.Slider_ANM_Brightness, self.TFV_ANM_Brightness,
                      self.TFV_ANM_Brightness_Min, self.TFV_ANM_Brightness_Max,
                      self.ANM_Brightness_Gradient_BG, mainFont)
        anmLay.addLayout(anmGrid)
        # Compat labels
        self.TFL_A_policeAnim = QLabel(""); self.TFL_B_partyAnim = QLabel(""); self.TFL_C_lightningAnim = QLabel("")
        anmLay.addStretch(1)
        self.ColorModeTabWidget.addTab(self.ANM, "Scene")

        # --- ANIMATIONS ---
        self.animTab = QWidget()
        animLay = QHBoxLayout(self.animTab)
        animLay.setContentsMargins(8, 8, 8, 8)
        animLay.setSpacing(8)

        self.animList = QListWidget()
        self.animList.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        animLay.addWidget(self.animList, 1)

        animCtrlScroll = QScrollArea()
        animCtrlScroll.setWidgetResizable(True)
        animCtrlScroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        animCtrlScroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        animCtrlScroll.setFrameShape(QFrame.NoFrame)
        animCtrlWidget = QWidget()
        animCtrl = QVBoxLayout(animCtrlWidget); animCtrl.setSpacing(4); animCtrl.setContentsMargins(0, 0, 4, 0)

        r1 = QHBoxLayout()
        self.animPlayButton = QPushButton("\u25B6 Play")
        self.animStopButton = QPushButton("\u25A0 Stop")
        r1.addWidget(self.animPlayButton); r1.addWidget(self.animStopButton)
        animCtrl.addLayout(r1)
        r2 = QHBoxLayout()
        self.animExportButton = QPushButton("Export JSON")
        self.animImportButton = QPushButton("Import JSON")
        r2.addWidget(self.animExportButton); r2.addWidget(self.animImportButton)
        animCtrl.addLayout(r2)

        # Toggles
        chkRow = QHBoxLayout()
        self.animParallelCheck = QCheckBox("Parallel"); self.animParallelCheck.setChecked(True)
        self.animParallelCheck.setToolTip("Send BLE commands to all lights simultaneously")
        self.animRevertCheck = QCheckBox("Revert on finish"); self.animRevertCheck.setChecked(True)
        self.animRevertCheck.setToolTip("Restore lights to pre-animation state when stopped or finished")
        chkRow.addWidget(self.animParallelCheck); chkRow.addWidget(self.animRevertCheck)
        animCtrl.addLayout(chkRow)

        # Labeled controls grid
        cg = QGridLayout(); cg.setSpacing(4)
        loopL = QLabel("Loop:"); loopL.setFont(mainFont); cg.addWidget(loopL, 0, 0)
        self.animLoopCheck = QCheckBox(); cg.addWidget(self.animLoopCheck, 0, 1)
        loopCountL = QLabel("Loops:"); loopCountL.setFont(mainFont); cg.addWidget(loopCountL, 1, 0)
        self.animLoopCountSpin = SpinBoxWithButtons(minVal=0, maxVal=999, value=0)
        self.animLoopCountSpin.setToolTip("0 = infinite (if Loop checked), N = play N times then stop")
        cg.addWidget(self.animLoopCountSpin, 1, 1)
        spdL = QLabel("Speed:"); spdL.setFont(mainFont); cg.addWidget(spdL, 2, 0)
        self.animSpeedCombo = QComboBox()
        self.animSpeedCombo.setEditable(True)
        self.animSpeedCombo.addItems(["0.25x", "0.5x", "1x", "1.5x", "2x", "3x", "4x"])
        self.animSpeedCombo.setCurrentIndex(2)
        self.animSpeedCombo.setToolTip("Multiplier applied to all animation timing\nType a custom value (e.g. 0.75x)")
        self.animSpeedCombo.setMinimumWidth(90)
        cg.addWidget(self.animSpeedCombo, 2, 1)
        rL = QLabel("Rate:"); rL.setFont(mainFont); cg.addWidget(rL, 3, 0)
        self.animRateSpin = SpinBoxWithButtons(minVal=1, maxVal=30, value=5)
        self.animRateSpin.setToolTip("BLE updates per second during fades.\n"
            "With Parallel OFF: ~5/s max (each light takes ~50ms sequentially)\n"
            "With Parallel ON: ~15/s achievable regardless of light count\n"
            "Higher = smoother fades but more BLE traffic")
        cg.addWidget(self.animRateSpin, 3, 1)
        briL = QLabel("Brightness:"); briL.setFont(mainFont); cg.addWidget(briL, 4, 0)
        self.animBriSpin = SpinBoxWithButtons(minVal=5, maxVal=100, value=100, suffix="%")
        cg.addWidget(self.animBriSpin, 4, 1)
        animCtrl.addLayout(cg)

        self.animStatusLabel = QLabel("Stopped")
        self.animStatusLabel.setAlignment(Qt.AlignCenter)
        self.animStatusLabel.setWordWrap(True)
        animCtrl.addWidget(self.animStatusLabel)
        animCtrl.addStretch(1)

        mgmt = QHBoxLayout()
        self.animNewButton = QPushButton("+New")
        self.animEditButton = QPushButton("Edit")
        self.animDeleteButton = QPushButton("Delete")
        self.animDuplicateButton = QPushButton("Duplicate")
        for b in [self.animNewButton, self.animEditButton, self.animDeleteButton, self.animDuplicateButton]:
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); mgmt.addWidget(b)
        animCtrl.addLayout(mgmt)
        animCtrlScroll.setWidget(animCtrlWidget)
        animLay.addWidget(animCtrlScroll)
        self.ColorModeTabWidget.addTab(self.animTab, "Animations")

        # --- LIGHT PREFS ---
        self.lightPrefs = QWidget()
        lpLay = QVBoxLayout(self.lightPrefs)
        lpLay.setContentsMargins(8, 8, 8, 8)
        lpLay.setSpacing(6)

        nameRow = QHBoxLayout()
        self.customName = QCheckBox("Custom Name for this light:")
        self.customName.setFont(mainFont)
        nameRow.addWidget(self.customName, 1)
        nameRow.addWidget(QLabel("Preferred ID:"))
        self.preferredIDSpin = QSpinBox(); self.preferredIDSpin.setRange(0, 99); self.preferredIDSpin.setMinimumWidth(65)
        self.preferredIDSpin.setToolTip("Fixed numeric ID (0 = auto)")
        nameRow.addWidget(self.preferredIDSpin)
        lpLay.addLayout(nameRow)

        self.customNameTF = QLineEdit(); self.customNameTF.setMaxLength(80)
        self.customNameTF.setPlaceholderText("Enter a custom name...")
        lpLay.addWidget(self.customNameTF)
        lpLay.addSpacing(10)

        self.colorTempRange = QCheckBox("Use Custom Color Temperature Range for CCT mode:")
        self.colorTempRange.setFont(mainFont)
        lpLay.addWidget(self.colorTempRange)
        tempRow = QHBoxLayout()
        self.colorTempRange_Min_TF = QLineEdit(); self.colorTempRange_Min_TF.setMaxLength(10); self.colorTempRange_Min_TF.setPlaceholderText("Min")
        self.colorTempRange_Max_TF = QLineEdit(); self.colorTempRange_Max_TF.setMaxLength(10); self.colorTempRange_Max_TF.setPlaceholderText("Max")
        tempRow.addWidget(self.colorTempRange_Min_TF); tempRow.addWidget(QLabel("to")); tempRow.addWidget(self.colorTempRange_Max_TF); tempRow.addStretch(1)
        lpLay.addLayout(tempRow)
        lpLay.addSpacing(10)

        self.onlyCCTModeCheck = QCheckBox("This light can only use CCT mode\n(for Neewer lights without HSI mode)")
        self.onlyCCTModeCheck.setFont(mainFont)
        lpLay.addWidget(self.onlyCCTModeCheck)
        lpLay.addStretch(1)
        self.saveLightPrefsButton = QPushButton("Save Preferences")
        lpLay.addWidget(self.saveLightPrefsButton, alignment=Qt.AlignRight)
        self.ColorModeTabWidget.addTab(self.lightPrefs, "Light Preferences")

        # --- GLOBAL PREFS ---
        self.globalPrefs = QScrollArea()
        self.globalPrefsCW = QWidget()
        self.globalPrefsLay = QFormLayout(self.globalPrefsCW)
        self.globalPrefsLay.setLabelAlignment(Qt.AlignLeft)
        self.globalPrefs.setWidget(self.globalPrefsCW)
        self.globalPrefs.setWidgetResizable(True)

        self.findLightsOnStartup_check = QCheckBox("Scan for Neewer lights on program launch")
        self.autoConnectToLights_check = QCheckBox("Automatically try to link to newly found lights")
        self.printDebug_check = QCheckBox("Print debug information to the console")
        self.rememberLightsOnExit_check = QCheckBox("Remember the last mode parameters set for lights on exit")
        self.rememberPresetsOnExit_check = QCheckBox("Save configuration of custom presets on exit")
        self.livePreview_check = QCheckBox("Live Preview (send settings in real-time as sliders move)")
        self.livePreview_check.setChecked(True)
        self.autoReconnect_check = QCheckBox("Automatically reconnect after disconnection")
        self.hideConsoleOnLaunch_check = QCheckBox("Hide console on startup (only when launched via python.exe)")
        self.minimizeToTrayOnClose_check = QCheckBox("Minimize to system tray on close (uncheck to quit on close)")
        self.minimizeToTrayOnClose_check.setChecked(True)
        self.httpAutoStart_check = QCheckBox("Start HTTP server automatically on launch")
        cctFallbackRow = QHBoxLayout()
        cctFallbackLabel = QLabel("Incompatible command handling:")
        self.cctFallbackCombo = QComboBox()
        self.cctFallbackCombo.addItems(["Convert / Clamp (adapt to light capabilities)", "Ignore / Skip (discard incompatible commands)"])
        self.cctFallbackCombo.setToolTip("How to handle commands a light can't execute:\n"
            "- HSI/Scene sent to a CCT-only light\n"
            "- Color temperature outside a light's supported range\n\n"
            "Convert/Clamp: adapt the command (map HSI to CCT, clamp temp to range)\n"
            "Ignore/Skip: silently drop the command for that light")
        cctFallbackRow.addWidget(cctFallbackLabel)
        cctFallbackRow.addWidget(self.cctFallbackCombo, 1)
        cctRangeRow = QHBoxLayout()
        cctRangeLabel = QLabel("Global CCT range:")
        self.globalCCTMinSpin = QSpinBox()
        self.globalCCTMinSpin.setRange(2700, 8500); self.globalCCTMinSpin.setValue(3200)
        self.globalCCTMinSpin.setSuffix("K"); self.globalCCTMinSpin.setSingleStep(100)
        self.globalCCTMinSpin.setButtonSymbols(QSpinBox.NoButtons)
        self.globalCCTMaxSpin = QSpinBox()
        self.globalCCTMaxSpin.setRange(2700, 8500); self.globalCCTMaxSpin.setValue(5600)
        self.globalCCTMaxSpin.setSuffix("K"); self.globalCCTMaxSpin.setSingleStep(100)
        self.globalCCTMaxSpin.setButtonSymbols(QSpinBox.NoButtons)
        cctRangeRow.addWidget(cctRangeLabel)
        cctRangeRow.addWidget(self.globalCCTMinSpin)
        cctRangeRow.addWidget(QLabel("to"))
        cctRangeRow.addWidget(self.globalCCTMaxSpin)
        self.maxNumOfAttempts_field = QLineEdit(); self.maxNumOfAttempts_field.setFixedWidth(50)
        self.acceptable_HTTP_IPs_field = QTextEdit(); self.acceptable_HTTP_IPs_field.setFixedHeight(70)
        self.whiteListedMACs_field = QTextEdit(); self.whiteListedMACs_field.setFixedHeight(70)

        self.resetGlobalPrefsButton = QPushButton("Reset Preferences to Defaults")
        self.saveGlobalPrefsButton = QPushButton("Save Global Preferences")

        # Keyboard shortcut sections
        self.windowButtonsCW = QWidget(); self.windowButtonsLay = QGridLayout(self.windowButtonsCW)
        self.SC_turnOffButton_field = singleKeySequenceEditCancel("Ctrl+PgDown")
        self.windowButtonsLay.addWidget(QLabel("Turn Off", alignment=Qt.AlignCenter), 1, 1)
        self.windowButtonsLay.addWidget(self.SC_turnOffButton_field, 2, 1)
        self.SC_turnOnButton_field = singleKeySequenceEditCancel("Ctrl+PgUp")
        self.windowButtonsLay.addWidget(QLabel("Turn On", alignment=Qt.AlignCenter), 1, 2)
        self.windowButtonsLay.addWidget(self.SC_turnOnButton_field, 2, 2)
        self.SC_scanCommandButton_field = singleKeySequenceEditCancel("Ctrl+Shift+S")
        self.windowButtonsLay.addWidget(QLabel("Scan", alignment=Qt.AlignCenter), 1, 3)
        self.windowButtonsLay.addWidget(self.SC_scanCommandButton_field, 2, 3)
        self.SC_tryConnectButton_field = singleKeySequenceEditCancel("Ctrl+Shift+C")
        self.windowButtonsLay.addWidget(QLabel("Connect", alignment=Qt.AlignCenter), 1, 4)
        self.windowButtonsLay.addWidget(self.SC_tryConnectButton_field, 2, 4)

        self.tabSwitchCW = QWidget(); self.tabSwitchLay = QGridLayout(self.tabSwitchCW)
        self.SC_Tab_CCT_field = singleKeySequenceEditCancel("Alt+1")
        self.tabSwitchLay.addWidget(QLabel("CCT", alignment=Qt.AlignCenter), 1, 1)
        self.tabSwitchLay.addWidget(self.SC_Tab_CCT_field, 2, 1)
        self.SC_Tab_HSI_field = singleKeySequenceEditCancel("Alt+2")
        self.tabSwitchLay.addWidget(QLabel("HSI", alignment=Qt.AlignCenter), 1, 2)
        self.tabSwitchLay.addWidget(self.SC_Tab_HSI_field, 2, 2)
        self.SC_Tab_SCENE_field = singleKeySequenceEditCancel("Alt+3")
        self.tabSwitchLay.addWidget(QLabel("Scene", alignment=Qt.AlignCenter), 1, 3)
        self.tabSwitchLay.addWidget(self.SC_Tab_SCENE_field, 2, 3)
        self.SC_Tab_PREFS_field = singleKeySequenceEditCancel("Alt+4")
        self.tabSwitchLay.addWidget(QLabel("Prefs", alignment=Qt.AlignCenter), 1, 4)
        self.tabSwitchLay.addWidget(self.SC_Tab_PREFS_field, 2, 4)

        self.brightnessCW = QWidget(); self.brightnessLay = QGridLayout(self.brightnessCW)
        self.SC_Dec_Bri_Small_field = singleKeySequenceEditCancel("/")
        self.brightnessLay.addWidget(QLabel("Bri -", alignment=Qt.AlignCenter), 1, 1)
        self.brightnessLay.addWidget(self.SC_Dec_Bri_Small_field, 2, 1)
        self.SC_Dec_Bri_Large_field = singleKeySequenceEditCancel("Ctrl+/")
        self.brightnessLay.addWidget(QLabel("Bri --", alignment=Qt.AlignCenter), 1, 2)
        self.brightnessLay.addWidget(self.SC_Dec_Bri_Large_field, 2, 2)
        self.SC_Inc_Bri_Small_field = singleKeySequenceEditCancel("*")
        self.brightnessLay.addWidget(QLabel("Bri +", alignment=Qt.AlignCenter), 1, 3)
        self.brightnessLay.addWidget(self.SC_Inc_Bri_Small_field, 2, 3)
        self.SC_Inc_Bri_Large_field = singleKeySequenceEditCancel("Ctrl+*")
        self.brightnessLay.addWidget(QLabel("Bri ++", alignment=Qt.AlignCenter), 1, 4)
        self.brightnessLay.addWidget(self.SC_Inc_Bri_Large_field, 2, 4)

        self.sliderAdjustmentCW = QWidget(); self.sliderAdjustmentLay = QGridLayout(self.sliderAdjustmentCW)
        _defaults = [("7","Ctrl+7","9","Ctrl+9"), ("4","Ctrl+4","6","Ctrl+6"), ("1","Ctrl+1","3","Ctrl+3")]
        for ri, (ds, dl, Is, Il) in enumerate(_defaults):
            rb = ri * 2
            n = str(ri + 1)
            dec_s = singleKeySequenceEditCancel(ds); dec_l = singleKeySequenceEditCancel(dl)
            inc_s = singleKeySequenceEditCancel(Is); inc_l = singleKeySequenceEditCancel(Il)
            setattr(self, f"SC_Dec_{n}_Small_field", dec_s)
            setattr(self, f"SC_Dec_{n}_Large_field", dec_l)
            setattr(self, f"SC_Inc_{n}_Small_field", inc_s)
            setattr(self, f"SC_Inc_{n}_Large_field", inc_l)
            self.sliderAdjustmentLay.addWidget(QLabel(f"S{n} -", alignment=Qt.AlignCenter), rb+1, 1)
            self.sliderAdjustmentLay.addWidget(dec_s, rb+2, 1)
            self.sliderAdjustmentLay.addWidget(QLabel(f"S{n} --", alignment=Qt.AlignCenter), rb+1, 2)
            self.sliderAdjustmentLay.addWidget(dec_l, rb+2, 2)
            self.sliderAdjustmentLay.addWidget(QLabel(f"S{n} +", alignment=Qt.AlignCenter), rb+1, 3)
            self.sliderAdjustmentLay.addWidget(inc_s, rb+2, 3)
            self.sliderAdjustmentLay.addWidget(QLabel(f"S{n} ++", alignment=Qt.AlignCenter), rb+1, 4)
            self.sliderAdjustmentLay.addWidget(inc_l, rb+2, 4)

        self.bottomButtonsCW = QWidget(); self.bottomButtonsLay = QGridLayout(self.bottomButtonsCW)
        self.bottomButtonsLay.addWidget(self.resetGlobalPrefsButton, 1, 1)
        self.bottomButtonsLay.addWidget(self.saveGlobalPrefsButton, 1, 2)

        # Build form
        self.globalPrefsLay.addRow(QLabel("<strong><u>Main Program Options</u></strong>", alignment=Qt.AlignCenter))
        self.globalPrefsLay.addRow(self.findLightsOnStartup_check)
        self.globalPrefsLay.addRow(self.autoConnectToLights_check)
        self.globalPrefsLay.addRow(self.printDebug_check)
        self.globalPrefsLay.addRow(self.rememberLightsOnExit_check)
        self.globalPrefsLay.addRow(self.rememberPresetsOnExit_check)
        self.globalPrefsLay.addRow(self.livePreview_check)
        self.globalPrefsLay.addRow(self.autoReconnect_check)
        self.globalPrefsLay.addRow(self.hideConsoleOnLaunch_check)
        self.globalPrefsLay.addRow(self.minimizeToTrayOnClose_check)
        self.globalPrefsLay.addRow(self.httpAutoStart_check)
        self.globalPrefsLay.addRow(cctFallbackRow)
        self.globalPrefsLay.addRow(cctRangeRow)
        self.enableLogTab_check = QCheckBox("Enable Log tab (show debug output in GUI)")
        self.enableLogTab_check.setChecked(True)
        self.logToFile_check = QCheckBox("Also write log to file (light_prefs/NeewerLux.log)")
        self.globalPrefsLay.addRow(self.enableLogTab_check)
        self.globalPrefsLay.addRow(self.logToFile_check)
        self.globalPrefsLay.addRow("Max connection retries:", self.maxNumOfAttempts_field)
        self.globalPrefsLay.addRow(QLabel("<hr><strong><u>Acceptable IPs for HTTP Server</u></strong>"))
        self.globalPrefsLay.addRow(self.acceptable_HTTP_IPs_field)
        self.globalPrefsLay.addRow(QLabel("<hr><strong><u>Whitelisted MAC Addresses</u></strong>"))
        self.globalPrefsLay.addRow(self.whiteListedMACs_field)
        self.globalPrefsLay.addRow(QLabel("<hr><strong><u>Keyboard Shortcuts</u></strong>"))
        self.globalPrefsLay.addRow(self.windowButtonsCW)
        self.globalPrefsLay.addRow(self.tabSwitchCW)
        self.globalPrefsLay.addRow(self.brightnessCW)
        self.globalPrefsLay.addRow(self.sliderAdjustmentCW)
        self.globalPrefsLay.addRow(self.bottomButtonsCW)
        self.ColorModeTabWidget.addTab(self.globalPrefs, "Global Preferences")

        # --- INFO TAB ---
        self.infoTab = QWidget()
        infoLay = QVBoxLayout(self.infoTab)
        infoLay.setContentsMargins(10, 10, 10, 10)

        # Update notification banner
        self.updateBanner = QLabel("")
        self.updateBanner.setWordWrap(True)
        self.updateBanner.setOpenExternalLinks(True)
        self.updateBanner.setVisible(False)
        self.updateBanner.setStyleSheet("QLabel { background-color: #1a3a1a; color: #4caf50; padding: 8px; border: 1px solid #4caf50; border-radius: 4px; }")
        infoLay.addWidget(self.updateBanner)

        self.checkUpdateButton = QPushButton("Check for Updates")
        self.checkUpdateButton.setToolTip("Check GitHub for a newer version of NeewerLux")
        infoLay.addWidget(self.checkUpdateButton)

        infoText = QTextBrowser()
        infoText.setReadOnly(True)
        infoText.setOpenExternalLinks(True)
        infoText.setHtml("""
<h2 style="color:#9100ff;">NeewerLux 1.0.0</h2>
<p>Cross-platform Neewer LED light control with custom animations, presets, and HTTP API.</p>
<p>Based on <a href="https://github.com/taburineagle/NeewerLite-Python/">NeewerLite-Python</a> by Zach Glenwright &mdash;
Originally from <a href="https://github.com/keefo/NeewerLite">NeewerLite</a> by Xu Lian</p>
<hr>
<h3>Quick Start</h3>
<ul>
<li><b>Scan</b> for Neewer lights via Bluetooth, then <b>Connect</b></li>
<li>Use the <b>CCT</b>, <b>HSI</b>, or <b>Scene</b> tabs to control lights</li>
<li>Create and play <b>Animations</b> with keyframe-based color sequences</li>
<li>Save up to unlimited <b>Presets</b> — right-click to save, left-click to recall, middle-click to rename</li>
<li>Enable the <b>HTTP server</b> for remote control via the web dashboard or API</li>
</ul>
<hr>
<h3>HTTP API Reference</h3>
<p>Start the HTTP server from the toolbar button or Global Preferences ("Start HTTP server automatically on launch").</p>
<p><b>Base URL:</b> <code>http://localhost:8080/NeewerLux/doAction?</code></p>
<table cellpadding="4">
<tr><td><b>discover</b></td><td>Scan for new lights</td></tr>
<tr><td><b>link=N</b></td><td>Connect to light N (or <code>all</code>)</td></tr>
<tr><td><b>light=N&amp;mode=CCT&amp;temp=5600&amp;bri=100</b></td><td>Set light to CCT mode</td></tr>
<tr><td><b>light=N&amp;mode=HSI&amp;hue=240&amp;sat=100&amp;bri=80</b></td><td>Set light to HSI mode</td></tr>
<tr><td><b>light=N&amp;mode=ANM&amp;scene=1&amp;bri=50</b></td><td>Set light to built-in scene</td></tr>
<tr><td><b>turnoff / turnon</b></td><td>Power lights on or off</td></tr>
<tr><td><b>use_preset=N</b></td><td>Recall preset N</td></tr>
<tr><td><b>animate=Name|speed|rate|bri</b></td><td>Play animation (GET)</td></tr>
<tr><td><b>list / list_json</b></td><td>List lights, presets, and animations</td></tr>
</table>
<p>POST to <code>/NeewerLux/batch</code> for multi-light JSON commands.
POST to <code>/NeewerLux/animate</code> for JSON animation control.</p>
<hr>
<p><b>Repository:</b> <a href="https://github.com/poizenjam/NeewerLux/">github.com/poizenjam/NeewerLux</a></p>
<p><b>Releases:</b> <a href="https://github.com/poizenjam/NeewerLux/releases">github.com/poizenjam/NeewerLux/releases</a></p>
""")
        infoLay.addWidget(infoText)
        self.ColorModeTabWidget.addTab(self.infoTab, "Info")

        # --- LOG TAB ---
        self.logTab = QWidget()
        logLay = QVBoxLayout(self.logTab)
        logLay.setContentsMargins(10, 10, 10, 10)
        logLay.setSpacing(4)
        logToolbar = QHBoxLayout()
        self.logClearButton = QPushButton("Clear")
        self.logClearButton.setToolTip("Clear the log display")
        self.logSaveButton = QPushButton("Save Log")
        self.logSaveButton.setToolTip("Save the current log to a file")
        logToolbar.addWidget(self.logClearButton)
        logToolbar.addWidget(self.logSaveButton)
        logToolbar.addStretch(1)
        logLay.addLayout(logToolbar)
        self.logTextEdit = QTextEdit()
        self.logTextEdit.setReadOnly(True)
        self.logTextEdit.setFont(QFont("Consolas", 9))
        self.logTextEdit.setLineWrapMode(QTextEdit.NoWrap)
        logLay.addWidget(self.logTextEdit)
        self.ColorModeTabWidget.addTab(self.logTab, "Log")

        # === ASSEMBLE ===
        bottomLay.addWidget(self.ColorModeTabWidget, 1)
        
        # Apply button — shown when live preview is disabled
        self.applyButton = QPushButton("Apply Settings")
        self.applyButton.setObjectName("applyButton")
        self.applyButton.setMinimumHeight(32)
        self.applyButton.setVisible(False)  # hidden when live preview is on
        bottomLay.addWidget(self.applyButton)
        self.mainSplitter.addWidget(self.presetScrollArea)
        self.mainSplitter.addWidget(bottomPanel)
        self.mainSplitter.setStretchFactor(0, 3)  # light table
        self.mainSplitter.setStretchFactor(1, 1)  # presets
        self.mainSplitter.setStretchFactor(2, 4)  # tabs
        self.mainSplitter.setSizes([260, 72, 380])  # initial sizes
        mainLayout.addWidget(self.mainSplitter, 1)

        # === STATUS BAR ===
        self.statusBar = QStatusBar()
        MainWindow.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Welcome to NeewerLux!")
