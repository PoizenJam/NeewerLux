"""NeewerLux main window UI.

Builds the widget tree and layouts. Widget attribute names are the
contract with NeewerLux.py, which connects the signal handlers.
"""

try:
    import PySide6
    from PySide6.QtCore import Qt, Signal, QSize, QRectF, QPointF
    from PySide6.QtGui import QFont, QColor, QLinearGradient, QBrush, QKeySequence, QIcon, QPainter, QPixmap, QPolygonF
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
        QSplitter, QSizePolicy, QAbstractItemView, QAbstractScrollArea,
        QPushButton, QLabel, QSlider, QTableWidget, QTableWidgetItem,
        QTabWidget, QCheckBox, QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QAbstractButton,
        QGraphicsView, QGraphicsScene, QScrollArea, QKeySequenceEdit,
        QListWidget, QListWidgetItem, QStatusBar, QHeaderView, QFrame,
        QSystemTrayIcon, QMenu, QTextBrowser, QProgressBar
    )
    customSignal = Signal
except ImportError:
    try:
        import PySide2
        from PySide2.QtCore import Qt, Signal, QSize, QRectF, QPointF
        from PySide2.QtGui import QFont, QColor, QLinearGradient, QBrush, QKeySequence, QIcon, QPainter, QPixmap, QPolygonF
        from PySide2.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
            QSplitter, QSizePolicy, QAbstractItemView, QAbstractScrollArea,
            QPushButton, QLabel, QSlider, QTableWidget, QTableWidgetItem,
            QTabWidget, QCheckBox, QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QAbstractButton,
            QGraphicsView, QGraphicsScene, QScrollArea, QKeySequenceEdit,
            QListWidget, QListWidgetItem, QStatusBar, QHeaderView, QFrame,
            QSystemTrayIcon, QMenu, QTextBrowser, QProgressBar
        )
        customSignal = Signal
    except ImportError:
        raise  # let it propagate, NeewerLux.py will handle the error


# === HELPER WIDGETS ===

def personIcon(size):
    """A top-down head and shoulders facing up (the front), as an icon."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    c = size / 2.0
    p.setBrush(QColor(120, 120, 120))
    p.drawEllipse(QRectF(c - size * 0.45, c - size * 0.02, size * 0.9, size * 0.38))
    p.setBrush(QColor(160, 160, 160))
    p.drawEllipse(QRectF(c - size * 0.17, c - size * 0.16, size * 0.34, size * 0.34))
    p.drawPolygon(QPolygonF([QPointF(c - size * 0.07, c - size * 0.13), QPointF(c + size * 0.07, c - size * 0.13),
                             QPointF(c, c - size * 0.3)]))
    p.end()
    return QIcon(pix)


class PositionPicker(QWidget):
    """Where a light stands, from the streamer's seat facing the camera: a 3 x 3 grid for side
    (columns: your left, centre, your right) and depth (rows: front at the top, beside you,
    back at the bottom), plus a height control. Other lights can be shown in their cells for
    reference. value() is (side, depth, height) using the names below."""
    changed = customSignal()
    SIDES = ["left", "centre", "right"]
    DEPTHS = ["front", "beside", "back"]
    HEIGHTS = ["high", "middle", "low"]  # top to bottom, as they're shown
    AIM_PAD = {(0, 0): "front-left", (0, 1): "front", (0, 2): "front-right", (1, 0): "left", (1, 1): "you",
               (1, 2): "right", (2, 0): "back-left", (2, 1): "back", (2, 2): "back-right"}
    AIM_GLYPHS = {"front-left": "\u2196", "front": "\u2191", "front-right": "\u2197", "left": "\u2190", "you": "\u25cf",
                  "right": "\u2192", "back-left": "\u2199", "back": "\u2193", "back-right": "\u2198"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._side, self._depth, self._height, self._aim = "centre", "beside", "middle", "you"
        self._others = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        grid = QGridLayout(); grid.setSpacing(3)
        for c, name in enumerate(["Your left", "Centre", "Your right"]):
            lab = QLabel(name); lab.setAlignment(Qt.AlignCenter); lab.setStyleSheet("color: #999;")
            grid.addWidget(lab, 0, c + 1)
        for r, name in enumerate(["Front", "Beside", "Back"]):
            lab = QLabel(name); lab.setStyleSheet("color: #999;")
            grid.addWidget(lab, r + 1, 0)
        self.cells = {}
        for r, depth in enumerate(self.DEPTHS):
            for c, side in enumerate(self.SIDES):
                b = QPushButton(); b.setCheckable(True)
                b.setMinimumSize(84, 44); b.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)  # long names clip, not widen
                b.clicked.connect(lambda _=False, s=side, d=depth: self._pick(s, d))
                grid.addWidget(b, r + 1, c + 1)
                self.cells[(side, depth)] = b
        for c in (1, 2, 3):
            grid.setColumnStretch(c, 1)
        lay.addLayout(grid, 3)
        col = QVBoxLayout(); col.setSpacing(3)
        hl = QLabel("Height"); hl.setStyleSheet("color: #999;")
        col.addWidget(hl)
        self.heightButtons = {}
        for h in self.HEIGHTS:
            b = QPushButton(h.capitalize()); b.setCheckable(True); b.setMinimumWidth(72)
            b.clicked.connect(lambda _=False, h=h: self._pickHeight(h))
            col.addWidget(b)
            self.heightButtons[h] = b
        al = QLabel("Points"); al.setStyleSheet("color: #999;")
        al.setToolTip("Which way the light points, on the same top-down grid (up = towards the camera).\nThe middle button means at you.")
        col.addSpacing(6)
        col.addWidget(al)
        aimGrid = QGridLayout(); aimGrid.setSpacing(2)
        self.aimButtons = {}
        for (r, c), aim in self.AIM_PAD.items():
            b = QPushButton(self.AIM_GLYPHS[aim]); b.setCheckable(True); b.setFixedSize(26, 24)
            b.setToolTip("Points at you" if aim == "you" else "Points " + aim.replace("-", " "))
            b.clicked.connect(lambda _=False, a=aim: self._pickAim(a))
            aimGrid.addWidget(b, r, c)
            self.aimButtons[aim] = b
        col.addLayout(aimGrid)
        col.addStretch(1)
        lay.addLayout(col, 1)
        self.setToolTip("Where this light is, from your seat facing the camera (front is between you and the camera),\nits height, and which way it points.\n"
                        "Targets: @left @centre @right, @front @beside @back, @low @middle @high,\n"
                        "combined with dots and roles: @back.left, @rim.high. Auto sweep order follows position.")
        self._refresh()

    def _pick(self, side, depth):
        self._side, self._depth = side, depth
        self._refresh(); self.changed.emit()

    def _pickHeight(self, height):
        self._height = height
        self._refresh(); self.changed.emit()

    def _pickAim(self, aim):
        self._aim = aim
        self._refresh(); self.changed.emit()

    def aim(self):
        return self._aim

    def setAim(self, aim):
        self._aim = aim if aim in self.AIM_GLYPHS else "you"
        self._refresh()

    def value(self):
        return self._side, self._depth, self._height

    def setValue(self, side, depth, height, aim=None):
        if aim is not None:
            self._aim = aim if aim in self.AIM_GLYPHS else "you"
        self._side = side if side in self.SIDES else "centre"
        self._depth = depth if depth in self.DEPTHS else "beside"
        self._height = height if height in self.HEIGHTS else "middle"
        self._refresh()

    def setOthers(self, others):
        """others: {(side, depth): [names]} for the other lights, shown greyed in their cells."""
        self._others = others or {}
        self._refresh()

    CHECKED = "QPushButton:checked { background-color: #3d6fd8; color: white; font-weight: bold; border: 1px solid #8fb0ff; }"

    def _refresh(self):
        for (side, depth), b in self.cells.items():
            sel = (side, depth) == (self._side, self._depth)
            b.setChecked(sel)
            names = self._others.get((side, depth), [])
            listed = "\n".join(names[:2]) + ("\n+%d more" % (len(names) - 2) if len(names) > 2 else "")
            if sel:
                text = "This light" + ("\n+ %d other%s" % (len(names), "" if len(names) == 1 else "s") if names else "")
            elif names:
                text = listed
            else:
                text = ""
            b.setText(text)
            b.setToolTip("\n".join(names) if names else "")
            b.setStyleSheet("QPushButton { color: %s; padding: 2px; } " % ("#aaa" if names else "#777") + self.CHECKED)
        for h, b in self.heightButtons.items():
            b.setChecked(h == self._height)
            b.setStyleSheet(self.CHECKED)
        for a, b in self.aimButtons.items():
            b.setChecked(a == self._aim)
            b.setStyleSheet("QPushButton { padding: 0px; } " + self.CHECKED)
        you = self.cells[("centre", "beside")]
        if not you.text():  # nobody placed on you: show you, from above, facing the front
            you.setIcon(personIcon(28)); you.setIconSize(QSize(28, 28))
        else:
            you.setIcon(QIcon())


def hideSpinArrows(spin):
    """Hide a spin box's own arrows through the theme (see neewerlux_theme). Not NoButtons: with a
    style sheet Qt 6.12 shrinks a NoButtons box's text area to nothing."""
    spin.setProperty("arrows", "none")
    return spin


class SpinBoxWithButtons(QWidget):
    """A spin box whose -/+ are ordinary buttons beside it. Native spin arrows end up under the
    text area once the theme styles the box (Windows, high DPI), so no spin box in the app uses
    them; tests/smoke_gui.py fails if one does. Anything not defined here is passed to the inner
    QSpinBox (or QDoubleSpinBox with double=True), so it is used like one: setRange, setSuffix,
    setSpecialValueText, setDecimals, valueChanged, editingFinished and so on."""

    def __init__(self, parent=None, minVal=0, maxVal=100, value=0, suffix="", double=False):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self._spin = QDoubleSpinBox() if double else QSpinBox()
        self._spin.setRange(minVal, maxVal)
        self._spin.setValue(value)
        if suffix:
            self._spin.setSuffix(suffix)
        hideSpinArrows(self._spin)
        self._minus = QPushButton("-")
        self._plus = QPushButton("+")
        for b, step in ((self._minus, self._spin.stepDown), (self._plus, self._spin.stepUp)):
            b.setStyleSheet("QPushButton { font-size: 14px; font-weight: bold; padding: 0px; }")
            b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
            b.setFixedWidth(26)
            b.setFocusPolicy(Qt.NoFocus)
            b.setAutoRepeat(True)   # hold to keep stepping, like the native arrows
            b.clicked.connect(step)
        lay.addWidget(self._spin, 1)
        lay.addWidget(self._minus)
        lay.addWidget(self._plus)
        self.setFocusProxy(self._spin)

    def __getattr__(self, name):
        if name == "_spin":   # not set yet (during construction)
            raise AttributeError(name)
        return getattr(self._spin, name)

    def blockSignals(self, block):
        self._spin.blockSignals(block)
        return super().blockSignals(block)

    def setToolTip(self, t):
        for w in (self, self._spin, self._minus, self._plus):
            QWidget.setToolTip(w, t)

    def setMinimumWidth(self, w):
        self._spin.setMinimumWidth(w)


def DoubleSpinBoxWithButtons(parent=None, minVal=0.0, maxVal=100.0, value=0.0, suffix=""):
    return SpinBoxWithButtons(parent, minVal, maxVal, value, suffix, double=True)


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


def _monoFont(pointSize=9):
    """Monospace font with fallbacks, matching the theme's mono stack."""
    f = QFont("Consolas", pointSize)
    f.setStyleHint(QFont.Monospace)
    f.setFamilies(["Consolas", "Menlo", "DejaVu Sans Mono", "Courier New"])
    return f


class singleKeySequenceEditCancel(QWidget):
    def __init__(self, defaultValue=""):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.defaultValue = defaultValue
        self.keySequence = QKeySequence(defaultValue)
        self.keyPressField = QKeySequenceEdit(self.keySequence)
        self.keyPressField.setMinimumWidth(150)
        # Qt draws an internal clear button that renders as an empty square on this theme.
        # The external X button below covers the same job.
        for _btn in self.keyPressField.findChildren(QAbstractButton):
            _btn.setFixedSize(0, 0)
            _btn.setVisible(False)
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
        MainWindow.setWindowTitle("NeewerLux")

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
        self.stageButton = QPushButton("Stage")
        self.stageButton.setToolTip("Open the Stage window: every light's current colour at a glance,\n"
            "including simulated lights, and which layer is driving it")
        toolbar.addWidget(self.stageButton)

        toolbar.addStretch(1)

        self.httpToggleBtn = QPushButton("HTTP: OFF")
        self.httpToggleBtn.setObjectName("httpToggleBtn")
        self.httpToggleBtn.setProperty("httpActive", False)
        self.httpToggleBtn.setMinimumWidth(100)
        self.httpToggleBtn.setToolTip("Start/stop the HTTP control server")
        toolbar.addWidget(self.httpToggleBtn)
        self.httpOpenWebUIBtn = QPushButton("WebUI")
        self.httpOpenWebUIBtn.setToolTip("Open the web dashboard in your browser")
        self.httpOpenWebUIBtn.setEnabled(False)
        toolbar.addWidget(self.httpOpenWebUIBtn)

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
        animLeft = QVBoxLayout(); animLeft.setSpacing(4)
        animLeft.addWidget(self.animList, 1)

        animLay.addLayout(animLeft, 1)

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

        # --- SEQUENCES ---
        self.seqTab = QWidget()
        seqLay = QHBoxLayout(self.seqTab)
        seqLay.setContentsMargins(8, 8, 8, 8)
        seqLay.setSpacing(8)
        seqLeft = QVBoxLayout(); seqLeft.setSpacing(4)
        self.seqList = QListWidget()
        self.seqList.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        seqLeft.addWidget(self.seqList, 1)
        seqRow = QHBoxLayout()
        self.seqPlayButton = QPushButton("\u25B6 Play")
        self.seqPauseButton = QPushButton("Pause")
        self.seqStopButton = QPushButton("\u25A0 Stop")
        self.seqReloadButton = QPushButton("Reload")
        self.seqReloadButton.setToolTip("Reload sequence files from light_prefs/sequences")
        self.seqRenderButton = QPushButton("Render")
        self.seqRenderButton.setToolTip("Show the whole sequence as a strip, one row per light, without playing it")
        for b in [self.seqPlayButton, self.seqPauseButton, self.seqStopButton, self.seqRenderButton, self.seqReloadButton]:
            seqRow.addWidget(b)
        seqLeft.addLayout(seqRow)
        seqEditRow = QHBoxLayout()
        self.seqNewButton = QPushButton("+New")
        self.seqNewButton.setToolTip("Open the timeline editor on a new sequence, blank or from a starter")
        self.seqEditButton = QPushButton("Edit")
        self.seqEditButton.setToolTip("Open the selected sequence in the timeline editor")
        self.seqDuplicateButton = QPushButton("Duplicate")
        self.seqDeleteButton = QPushButton("Delete")
        for b in [self.seqNewButton, self.seqEditButton, self.seqDuplicateButton, self.seqDeleteButton]:
            seqEditRow.addWidget(b)
        seqLeft.addLayout(seqEditRow)
        self.seqStatusLabel = QLabel("No sequence playing")
        self.seqStatusLabel.setAlignment(Qt.AlignCenter)
        seqLeft.addWidget(self.seqStatusLabel)
        seqLay.addLayout(seqLeft, 3)
        # details of the selected sequence
        self.seqInfoLabel = QLabel("Select a sequence to see its details.")
        self.seqInfoLabel.setWordWrap(True)
        self.seqInfoLabel.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.seqInfoLabel.setTextFormat(Qt.RichText)
        self.seqInfoLabel.setMinimumWidth(220)
        seqInfoScroll = QScrollArea()
        seqInfoScroll.setWidgetResizable(True)
        seqInfoScroll.setFrameShape(QFrame.NoFrame)
        seqInfoScroll.setWidget(self.seqInfoLabel)
        seqLay.addWidget(seqInfoScroll, 2)
        self.ColorModeTabWidget.addTab(self.seqTab, "Sequences")

        # --- SOUND ---  (behaviour in NeewerLux.py, MainWindow sound* methods)
        self.soundTab = QWidget()
        soundOuter = QVBoxLayout(self.soundTab)
        soundOuter.setContentsMargins(8, 8, 8, 8)
        soundOuter.setSpacing(6)
        self.soundUnavailableLabel = QLabel("")
        self.soundUnavailableLabel.setWordWrap(True)
        soundOuter.addWidget(self.soundUnavailableLabel)
        self.soundControls = QWidget()
        soundOuter.addWidget(self.soundControls, 1)
        soundLay = QHBoxLayout(self.soundControls)
        soundLay.setContentsMargins(0, 0, 0, 0)
        soundLay.setSpacing(10)
        # the controls scroll: the tab is short when the light table is tall
        soundLeftScroll = QScrollArea()
        soundLeftScroll.setWidgetResizable(True)
        soundLeftScroll.setFrameShape(QFrame.NoFrame)
        soundLeftPage = QWidget()
        soundLeftScroll.setWidget(soundLeftPage)
        soundLeft = QVBoxLayout(soundLeftPage); soundLeft.setSpacing(6); soundLeft.setContentsMargins(0, 0, 6, 0)
        devRow = QHBoxLayout()
        devRow.addWidget(QLabel("Listen to:"))
        self.soundDeviceCombo = QComboBox()
        self.soundDeviceCombo.setToolTip("What to listen to: what an output plays (loopback), or an input such as a microphone or audio interface")
        self.soundDeviceCombo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        devRow.addWidget(self.soundDeviceCombo, 1)
        self.soundDeviceRefresh = QPushButton("Refresh")
        self.soundDeviceRefresh.setToolTip("List the audio devices again (after plugging one in)")
        devRow.addWidget(self.soundDeviceRefresh)
        soundLeft.addLayout(devRow)
        modeRow = QHBoxLayout()
        modeRow.addWidget(QLabel("Mode:"))
        self.soundModeCombo = QComboBox()
        self.soundModeCombo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        modeRow.addWidget(self.soundModeCombo, 1)
        self.soundStartButton = QPushButton("\u25B6 Start")
        self.soundStartButton.setToolTip("Play this mode on the lights it names, replacing whatever sound is playing")
        self.soundStartSelectedButton = QPushButton("On selected")
        self.soundStartSelectedButton.setToolTip("Only the lights selected in the light list follow this mode;\n"
                                                 "other lights keep following whatever sound they follow")
        self.soundStopButton = QPushButton("\u25A0 Stop")
        self.soundStopButton.setToolTip("Stop sound on every light")
        modeRow.addWidget(self.soundStartButton)
        modeRow.addWidget(self.soundStartSelectedButton)
        modeRow.addWidget(self.soundStopButton)
        soundLeft.addLayout(modeRow)
        self.soundDescLabel = QLabel("")
        self.soundDescLabel.setWordWrap(True)
        soundLeft.addWidget(self.soundDescLabel)

        soundGrid = QGridLayout(); soundGrid.setSpacing(4); soundGrid.setColumnStretch(1, 1)
        self.soundSliders = {}
        for row, (key, label, lo, hi, tip) in enumerate((
                ("sensitivity", "Sensitivity", 10, 500, "How strongly the lights react: above 100% more, below less"),
                ("range_db", "Range", 6, 30, "How far under the loudest recent moment counts as dark: smaller swings further"),
                ("floor", "Floor", 0, 100, "Brightness when it's quiet"),
                ("ceiling", "Ceiling", 0, 100, "Brightness at full"),
                ("smoothing", "Smoothing", 0, 100, "How slowly lights fall back and colours drift"))):
            slider = QSlider(Qt.Horizontal)
            slider.setRange(lo, hi)
            slider.setToolTip(tip)
            value = QLabel("")
            value.setMinimumWidth(52)
            soundGrid.addWidget(QLabel(label + ":"), row, 0)
            soundGrid.addWidget(slider, row, 1)
            soundGrid.addWidget(value, row, 2)
            self.soundSliders[key] = (slider, value)
        soundLeft.addLayout(soundGrid)

        palLabel = QLabel("Palette: the colours this mode uses. Each group of lights below picks one of them, "
                          "or moves through them (cycling, on the beat, or with the sound).")
        palLabel.setWordWrap(True)
        soundLeft.addWidget(palLabel)
        palRow = QHBoxLayout()
        self.soundPaletteKind = QComboBox()
        self.soundPaletteKind.addItems(["Colours", "White (Kelvin)"])
        self.soundPaletteKind.setToolTip("Colours (hue and saturation) or whites (colour temperature) for CCT-only lights")
        palRow.addWidget(self.soundPaletteKind)
        self.soundPaletteAdd = QPushButton("+ Colour")
        palRow.addWidget(self.soundPaletteAdd)
        palRow.addWidget(QLabel("Cycle:"))
        self.soundCycleSpin = SpinBoxWithButtons(None, 4, 600, 20, " s")
        self.soundCycleSpin.setToolTip("How long lights set to \"Cycles\" take to go round the whole palette\n"
                                       "(one colour goes once round the colour wheel)")
        palRow.addWidget(self.soundCycleSpin)
        palRow.addStretch(1)
        soundLeft.addLayout(palRow)
        palPresetRow = QHBoxLayout()
        palPresetRow.addWidget(QLabel("Saved palettes:"))
        self.soundPalettePresetCombo = QComboBox()
        self.soundPalettePresetCombo.setToolTip("Load a saved palette into this mode (replacing its colours)")
        self.soundPalettePresetCombo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        palPresetRow.addWidget(self.soundPalettePresetCombo, 1)
        self.soundPaletteSaveButton = QPushButton("Save palette...")
        self.soundPaletteSaveButton.setToolTip("Save these colours as a palette to use in other modes")
        self.soundPaletteDeleteButton = QPushButton("Delete palette")
        palPresetRow.addWidget(self.soundPaletteSaveButton)
        palPresetRow.addWidget(self.soundPaletteDeleteButton)
        soundLeft.addLayout(palPresetRow)
        self.soundPaletteBox = QVBoxLayout(); self.soundPaletteBox.setSpacing(2)
        soundLeft.addLayout(self.soundPaletteBox)

        soundLeft.addWidget(QLabel("Lights and what drives them:"))
        self.soundPartsTable = QTableWidget(0, 5)
        self.soundPartsTable.setHorizontalHeaderLabels(["Lights", "Brightness", "Colour", "Chase", ""])
        partsHeader = self.soundPartsTable.horizontalHeader()
        partsHeader.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in (1, 2, 3):
            partsHeader.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        partsHeader.setSectionResizeMode(4, QHeaderView.Fixed)
        self.soundPartsTable.setColumnWidth(4, 34)
        self.soundPartsTable.horizontalHeaderItem(1).setToolTip("What drives these lights' brightness")
        self.soundPartsTable.verticalHeader().setVisible(False)
        self.soundPartsTable.setMinimumHeight(150)
        soundLeft.addWidget(self.soundPartsTable)
        partsRow = QHBoxLayout()
        self.soundPartAdd = QPushButton("+ Lights")
        self.soundPartAdd.setToolTip("Add a group of lights (by role, position or number)")
        partsRow.addWidget(self.soundPartAdd)
        partsRow.addStretch(1)
        self.soundSaveButton = QPushButton("Save")
        self.soundSaveAsButton = QPushButton("Save as...")
        self.soundRevertButton = QPushButton("Revert")
        self.soundRevertButton.setToolTip("Go back to the saved mode")
        self.soundDeleteButton = QPushButton("Delete")
        for b in (self.soundSaveButton, self.soundSaveAsButton, self.soundRevertButton, self.soundDeleteButton):
            partsRow.addWidget(b)
        soundLeft.addLayout(partsRow)
        soundLeft.addStretch(1)
        soundLay.addWidget(soundLeftScroll, 3)

        soundRightBox = QWidget()
        soundRightBox.setMaximumWidth(230)  # the meters need little room; the parts table needs it
        soundRight = QVBoxLayout(soundRightBox); soundRight.setSpacing(4); soundRight.setContentsMargins(0, 0, 0, 0)
        self.soundStatusLabel = QLabel("Not playing")
        self.soundStatusLabel.setWordWrap(True)
        soundRight.addWidget(self.soundStatusLabel)
        self.soundMeters = {}
        for key, label in (("level", "Level"), ("low", "Bass"), ("mid", "Mids"), ("high", "Treble"), ("centroid", "Brightness of sound")):
            soundRight.addWidget(QLabel(label))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setFixedHeight(12)
            soundRight.addWidget(bar)
            self.soundMeters[key] = bar
        self.soundTempoLabel = QLabel("Tempo: -")
        soundRight.addWidget(self.soundTempoLabel)
        soundRight.addStretch(1)
        soundLay.addWidget(soundRightBox, 1)
        # after Scene: sound is a bed under animations and sequences
        self.ColorModeTabWidget.insertTab(self.ColorModeTabWidget.indexOf(self.animTab), self.soundTab, "Sound")

        # --- LIGHT PREFS ---
        # Two columns: the light itself on the left, its part in shows on the right
        self.lightPrefs = QScrollArea()  # scrolls only on small windows
        self.lightPrefs.setWidgetResizable(True)
        self.lightPrefsCW = QWidget()
        lpOuter = QVBoxLayout(self.lightPrefsCW)
        lpOuter.setContentsMargins(8, 8, 8, 8)
        lpCols = QHBoxLayout()
        lpCols.setSpacing(18)
        lpOuter.addLayout(lpCols, 1)
        lpLay = QVBoxLayout()
        lpLay.setSpacing(6)
        lpCols.addLayout(lpLay, 4)

        lpLay.addWidget(QLabel("<strong>This light</strong>"))
        nameRow = QHBoxLayout()
        self.customName = QCheckBox("Custom name:")
        nameRow.addWidget(self.customName, 1)
        nameRow.addWidget(QLabel("Preferred ID:"))
        self.preferredIDSpin = SpinBoxWithButtons(); self.preferredIDSpin.setRange(0, 99); self.preferredIDSpin.setMinimumWidth(65)
        self.preferredIDSpin.setSpecialValueText("Auto")
        self.preferredIDSpin.setToolTip("Fixed numeric ID for HTTP commands and animations (Auto = table order)")
        nameRow.addWidget(self.preferredIDSpin)
        lpLay.addLayout(nameRow)
        self.customNameTF = QLineEdit(); self.customNameTF.setMaxLength(80)
        self.customNameTF.setPlaceholderText("Enter a custom name...")
        lpLay.addWidget(self.customNameTF)
        self.colorTempRange = QCheckBox("Custom colour temperature range for CCT mode:")
        lpLay.addWidget(self.colorTempRange)
        tempRow = QHBoxLayout()
        self.colorTempRange_Min_TF = QLineEdit(); self.colorTempRange_Min_TF.setMaxLength(10); self.colorTempRange_Min_TF.setPlaceholderText("Min")
        self.colorTempRange_Max_TF = QLineEdit(); self.colorTempRange_Max_TF.setMaxLength(10); self.colorTempRange_Max_TF.setPlaceholderText("Max")
        tempRow.addWidget(self.colorTempRange_Min_TF); tempRow.addWidget(QLabel("to")); tempRow.addWidget(self.colorTempRange_Max_TF); tempRow.addWidget(QLabel("K"))
        lpLay.addLayout(tempRow)
        self.onlyCCTModeCheck = QCheckBox("This light can only use CCT mode (Neewer lights without HSI)")
        lpLay.addWidget(self.onlyCCTModeCheck)
        lpLay.addSpacing(6)

        lpLay.addWidget(QLabel("<strong>Limits in sequences, effects, presets and HTTP</strong>"))
        limitGrid = QGridLayout(); limitGrid.setSpacing(4)
        self.lightMaxBriSpin = SpinBoxWithButtons(); self.lightMaxBriSpin.setRange(-1, 100); self.lightMaxBriSpin.setSuffix("%")
        self.lightMaxBriSpin.setSpecialValueText("Global"); self.lightMaxBriSpin.setValue(-1)
        self.lightMaxBriSpin.setToolTip("Brightness ceiling for presets, HTTP commands, animations and sequences.\nThe manual sliders are exempt. Global = the default in Global Preferences.")
        self.lightMinBriSpin = SpinBoxWithButtons(); self.lightMinBriSpin.setRange(-1, 100); self.lightMinBriSpin.setSuffix("%")
        self.lightMinBriSpin.setSpecialValueText("Global"); self.lightMinBriSpin.setValue(-1)
        self.lightMinBriSpin.setToolTip("Brightness floor while the light is on (0% and OFF still pass).\nThe manual sliders are exempt.")
        limitGrid.addWidget(QLabel("Max brightness:"), 0, 0); limitGrid.addWidget(self.lightMaxBriSpin, 0, 1)
        limitGrid.addWidget(QLabel("Min brightness:"), 0, 2); limitGrid.addWidget(self.lightMinBriSpin, 0, 3)
        limitGrid.setColumnStretch(4, 1)
        lpLay.addLayout(limitGrid)
        self.lightLockedCheck = QCheckBox("Locked: stays on its manual or preset state during sequences and effects")
        lpLay.addWidget(self.lightLockedCheck)
        self.lightEyelineCheck = QCheckBox("In my eye line (a light I look into on camera)")
        self.lightEyelineCheck.setToolTip("Targets: @eyeline. Global Preferences can also make flashes gentler on these lights.")
        lpLay.addWidget(self.lightEyelineCheck)
        lpLay.addStretch(1)

        showLay = QVBoxLayout()
        showLay.setSpacing(6)
        lpCols.addLayout(showLay, 5)
        showLay.addWidget(QLabel("<strong>In sequences and effects</strong>"))
        roleRow = QHBoxLayout()
        self.lightRoleCombo = QComboBox(); self.lightRoleCombo.addItems(["Key", "Fill", "Rim / back", "Background", "Practical"])
        self.lightRoleCombo.setToolTip("Role used by @key, @fill, @rim, @background and @practical targets.\n"
            "Key: main light on you. Fill: softens the key's shadows. Rim / back: behind you, outlines you.\n"
            "Background: lights the wall or set behind you. Practical: a light that is visible in shot.\n"
            "Lights without a role count as Background.")
        self.lightOrderSpin = SpinBoxWithButtons(); self.lightOrderSpin.setRange(0, 99); self.lightOrderSpin.setSpecialValueText("Auto")
        self.lightOrderSpin.setToolTip("Position in sweeps: @ targets list lights in this order,\nand a clip's light 1, 2, 3... map onto them in this order.\nAuto = by position (left to right, front to back, low to high), then ID.")
        roleRow.addWidget(QLabel("Role:")); roleRow.addWidget(self.lightRoleCombo, 1)
        roleRow.addSpacing(12)
        roleRow.addWidget(QLabel("Sweep order:")); roleRow.addWidget(self.lightOrderSpin)
        showLay.addLayout(roleRow)
        showLay.addWidget(QLabel("Position, height and aim (from your seat, facing the camera):"))
        self.lightPositionPicker = PositionPicker()
        showLay.addWidget(self.lightPositionPicker)
        showLay.addStretch(1)

        self.saveLightPrefsButton = QPushButton("Save Preferences")
        lpOuter.addWidget(self.saveLightPrefsButton, alignment=Qt.AlignRight)
        self.lightPrefs.setWidget(self.lightPrefsCW)
        self.ColorModeTabWidget.addTab(self.lightPrefs, "Light Preferences")

        # --- GLOBAL PREFS ---
        # Four sub-tabs, with Reset and Save below them so they're always in view
        self.globalPrefs = QWidget()
        gpOuter = QVBoxLayout(self.globalPrefs)
        gpOuter.setContentsMargins(0, 0, 0, 0)
        self.globalPrefsCW = self.globalPrefs  # every control lives under here (for the unsaved-changes watch)
        self.globalPrefsTabs = QTabWidget()
        gpOuter.addWidget(self.globalPrefsTabs, 1)

        def _gpPage(title):
            scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
            page = QWidget(); form = QFormLayout(page); form.setLabelAlignment(Qt.AlignLeft)
            scroll.setWidget(page)
            self.globalPrefsTabs.addTab(scroll, title)
            return form

        self.findLightsOnStartup_check = QCheckBox("Scan for Neewer lights on program launch")
        self.autoConnectToLights_check = QCheckBox("Automatically try to link to newly found lights")
        self.printDebug_check = QCheckBox("Print debug information to the console")
        self.rememberLightsOnExit_check = QCheckBox("Remember the last mode parameters set for lights on exit")
        self.rememberPresetsOnExit_check = QCheckBox("Save configuration of custom presets on exit")
        self.livePreview_check = QCheckBox("Live Preview (send settings in real-time as sliders move)")
        self.livePreview_check.setChecked(True)
        self.livePreview_check.setToolTip("While a sequence or effect is playing, slider and preset changes to the lights it drives\n"
            "don't show until it ends: they become the state those lights return to.\n"
            "Lights it isn't using, and Locked lights, change straight away.")
        self.autoReconnect_check = QCheckBox("Automatically reconnect after disconnection")
        self.hideConsoleOnLaunch_check = QCheckBox("Hide console on startup (only when launched via python.exe)")
        self.minimizeToTrayOnClose_check = QCheckBox("Minimize to system tray on close (uncheck to quit on close)")
        self.minimizeToTrayOnClose_check.setChecked(True)
        self.httpAutoStart_check = QCheckBox("Start HTTP server automatically on launch")
        self.httpPortField = QLineEdit("8080")
        self.httpPortField.setFixedWidth(70)
        self.httpPortField.setToolTip("Port for the HTTP server (1024-65535, default 8080). Restart the server to apply.")
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
        hideSpinArrows(self.globalCCTMinSpin)
        self.globalCCTMaxSpin = QSpinBox()
        self.globalCCTMaxSpin.setRange(2700, 8500); self.globalCCTMaxSpin.setValue(5600)
        self.globalCCTMaxSpin.setSuffix("K"); self.globalCCTMaxSpin.setSingleStep(100)
        hideSpinArrows(self.globalCCTMaxSpin)
        cctRangeRow.addWidget(cctRangeLabel)
        cctRangeRow.addWidget(self.globalCCTMinSpin)
        cctRangeRow.addWidget(QLabel("to"))
        cctRangeRow.addWidget(self.globalCCTMaxSpin)
        self.envMaxBriSpin = SpinBoxWithButtons(); self.envMaxBriSpin.setRange(1, 100); self.envMaxBriSpin.setValue(100); self.envMaxBriSpin.setSuffix("%")
        self.envMaxBriSpin.setToolTip("Default brightness ceiling for lights without their own limit.\nApplies to presets, HTTP, animations and sequences; the manual sliders are exempt.")
        self.envMinBriSpin = SpinBoxWithButtons(); self.envMinBriSpin.setRange(0, 100); self.envMinBriSpin.setValue(0); self.envMinBriSpin.setSuffix("%")
        self.envMinBriSpin.setToolTip("Default brightness floor while a light is on (0% and OFF still pass)")
        self.flashGuardCheck = QCheckBox("Flash guard: at most 3 flashes a second per light (recommended)")
        self.flashGuardCheck.setChecked(True)
        self.flashGuardCheck.setToolTip("Holds back changes that would make a light flash more than 3 times a second\n"
                                        "(the WCAG limit for photosensitive seizures), from animations, sequences, effects,\n"
                                        "presets and HTTP commands. The manual sliders are exempt. Scenes run inside the\n"
                                        "light and can't be limited.")
        self.seqFrameRateSpin = SpinBoxWithButtons(); self.seqFrameRateSpin.setRange(1, 30); self.seqFrameRateSpin.setValue(20); self.seqFrameRateSpin.setSuffix(" /s")
        self.seqFrameRateSpin.setToolTip("Updates per second for sequences that don't set their own 'fps'.\nSequences always use the synchronized (parallel) send.")
        self.effectMaxSecondsSpin = SpinBoxWithButtons(); self.effectMaxSecondsSpin.setRange(1, 600); self.effectMaxSecondsSpin.setValue(30); self.effectMaxSecondsSpin.setSuffix(" s")
        self.effectMaxSecondsSpin.setToolTip("Effect-layer animations that loop forever stop after this long,\nso one effect can't hold up the queue")
        self.simulatedLightsCombo = QComboBox()
        self.simulatedLightsCombo.addItems(["Off", "1 light (key)", "2 lights (key, fill)", "3 lights (key, fill, rim)", "4 lights (key, fill, rim, background)"])
        self.simulatedLightsCombo.setToolTip("Adds virtual lights that behave like real ones, for trying sequences, effects and\n"
            "HTTP commands without hardware. They show in the light table and the Stage window\n"
            "and can be used alongside real lights. Takes effect the next time NeewerLux starts.\n"
            "Launching with --simulate=N does the same for one run only.")
        self.simulatedCCTOnlyCheck = QCheckBox("Also add a CCT-only light (tests the CCT-only fallback)")
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

        # Settings added in 1.3.3
        self.cameraPositionCombo = QComboBox()
        self.CAMERA_POSITIONS = ["front-left", "front", "front-right", "left", "right", "back-left", "back", "back-right"]
        self.cameraPositionCombo.addItems(["Front left", "Front (straight ahead)", "Front right", "Your left", "Your right",
                                           "Back left", "Behind you", "Back right"])
        self.cameraPositionCombo.setCurrentIndex(1)
        self.cameraPositionCombo.setToolTip("Where your main camera is, from your seat. Shown on the Stage plan;\n"
                                            "positions (front, left...) stay relative to you, facing the camera.")
        self.eyelineFlashCombo = QComboBox()
        self.EYELINE_FLASH = ["same", "gentler", "calm"]
        self.eyelineFlashCombo.addItems(["Same as other lights", "Gentler: at most 1 flash a second", "Calm: at most one change every 2 seconds"])
        self.eyelineFlashCombo.setToolTip("For lights marked 'In my eye line' in Light Preferences. Applies even with the flash guard off.")
        self.handbackFadeSpin = SpinBoxWithButtons(); self.handbackFadeSpin.setRange(0, 5000); self.handbackFadeSpin.setSingleStep(100)
        self.handbackFadeSpin.setSuffix(" ms"); self.handbackFadeSpin.setSpecialValueText("Off (cut)"); self.handbackFadeSpin.setValue(500)
        self.handbackFadeSpin.setToolTip("When an effect ends and the sequence takes back over, a sequence ends and reverts,\n"
                                         "or an animation stops: fade to what comes next instead of cutting.\n"
                                         "Each animation and sequence can set its own; the slider tabs stay instant.")
        self.fadeInSpin = SpinBoxWithButtons(); self.fadeInSpin.setRange(0, 5000); self.fadeInSpin.setSingleStep(100)
        self.fadeInSpin.setSuffix(" ms"); self.fadeInSpin.setSpecialValueText("Off (cut)"); self.fadeInSpin.setValue(0)
        self.fadeInSpin.setToolTip("When a preset is recalled, or an animation or sequence takes lights over (including\n"
                                   "one animation replacing another): fade into it instead of cutting.\n"
                                   "Each preset, animation and sequence can set its own; the slider tabs stay instant.")

        general = _gpPage("General")
        general.addRow(QLabel("<strong>Startup and connection</strong>"))
        general.addRow(self.findLightsOnStartup_check)
        general.addRow(self.autoConnectToLights_check)
        general.addRow(self.autoReconnect_check)
        general.addRow("Max connection retries:", self.maxNumOfAttempts_field)
        general.addRow(QLabel("Whitelisted MAC addresses:"))
        general.addRow(self.whiteListedMACs_field)
        general.addRow(QLabel("<br><strong>Control and presets</strong>"))
        general.addRow(self.livePreview_check)
        general.addRow(self.rememberLightsOnExit_check)
        general.addRow(self.rememberPresetsOnExit_check)
        general.addRow(QLabel("<br><strong>Window</strong>"))
        general.addRow(self.hideConsoleOnLaunch_check)
        general.addRow(self.minimizeToTrayOnClose_check)
        general.addRow(QLabel("<br><strong>Logging</strong>"))
        self.enableLogTab_check = QCheckBox("Enable Log tab (show debug output in GUI)")
        self.enableLogTab_check.setChecked(True)
        self.logToFile_check = QCheckBox("Also write log to file (light_prefs/NeewerLux.log)")
        self.logHeartbeat_check = QCheckBox("Log a background heartbeat every 30 seconds")
        general.addRow(self.enableLogTab_check)
        general.addRow(self.logToFile_check)
        general.addRow(self.logHeartbeat_check)
        general.addRow(self.printDebug_check)

        shows = _gpPage("Lights and shows")
        shows.addRow(QLabel("<strong>Safety</strong>"))
        shows.addRow("", self.flashGuardCheck)
        shows.addRow("Eye-line lights during flashes:", self.eyelineFlashCombo)
        shows.addRow("Default max brightness:", self.envMaxBriSpin)
        shows.addRow("Default min brightness:", self.envMinBriSpin)
        shows.addRow(QLabel("<br><strong>Playback</strong>"))
        shows.addRow("Fade in (presets, animations, sequences):", self.fadeInSpin)
        shows.addRow("Fade back (when they let go):", self.handbackFadeSpin)
        shows.addRow("Sequence frame rate:", self.seqFrameRateSpin)
        shows.addRow("Looping effect time limit:", self.effectMaxSecondsSpin)
        shows.addRow(QLabel("<br><strong>Sound modes</strong>"))
        self.prefsSoundDeviceCombo = QComboBox()
        self.prefsSoundDeviceCombo.setToolTip("What sound modes listen to (the same choice as on the Sound tab; saved at once)")
        shows.addRow("Listen to:", self.prefsSoundDeviceCombo)
        shows.addRow(QLabel("<br><strong>Your rig</strong>"))
        shows.addRow("Main camera:", self.cameraPositionCombo)
        shows.addRow(cctFallbackRow)
        shows.addRow(cctRangeRow)

        net = _gpPage("Simulation and HTTP")
        net.addRow(QLabel("<strong>Simulated lights</strong>"))
        net.addRow("Simulated rig:", self.simulatedLightsCombo)
        net.addRow("", self.simulatedCCTOnlyCheck)
        net.addRow(QLabel("<br><strong>HTTP server</strong>"))
        net.addRow(self.httpAutoStart_check)
        net.addRow("HTTP server port:", self.httpPortField)
        net.addRow(QLabel("Acceptable IPs for the HTTP server:"))
        net.addRow(self.acceptable_HTTP_IPs_field)

        keys = _gpPage("Shortcuts")
        keys.addRow(self.windowButtonsCW)
        keys.addRow(self.tabSwitchCW)
        keys.addRow(self.brightnessCW)
        keys.addRow(self.sliderAdjustmentCW)

        gpOuter.addWidget(self.bottomButtonsCW)
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

        self.infoText = QTextBrowser()
        self.infoText.setReadOnly(True)
        self.infoText.setOpenExternalLinks(True)
        self.infoText.setHtml("""
<h2>NeewerLux {VERSION}</h2>

<h3>Lights</h3>
<p>Scan for Neewer lights over Bluetooth and control them in CCT, HSI, or Scene mode.
Give a light a name and a fixed number in Light Preferences and it keeps its place in
the table, and can be addressed by that name in animations and HTTP commands.</p>

<h3>Colour temperature limits</h3>
<p>Set the CCT range your lights should stay within, globally or per light. A command
outside a light's range is either converted to the nearest value it can reach or skipped
entirely, depending on which you pick in Global Preferences. Useful when mixing models
with different ranges.</p>

<h3>Presets</h3>
<p>Right-click a preset button to save the current setup, left-click to recall it,
middle-click to rename. A preset can target one light or all of them. The Preset Editor
offers the same thing as a table if you would rather work that way.</p>

<h3>Animations</h3>
<p>101 animations ship with the app, covering emergency, stage, holiday, studio, and
ambient looks. The editor works on keyframes with a table and live preview, or you can
edit the underlying JSON directly. CCT-only lights follow colour animations by mapping
hue to the nearest temperature, so mixed setups stay in step.</p>
<p>Animations target lights by name, by number, by MAC address, or with <code>*</code>
for all of them.</p>

<h3>Remote control</h3>
<p>Turn on the HTTP server to drive everything from a browser or from hardware such as a
Stream Deck. The dashboard lives at <code>http://localhost:8080/</code>, and every action
is also available as a plain URL. The port is configurable in Global Preferences.</p>

<h3>Files</h3>
<p>Presets, animations, and per-light settings are plain files in the
<code>light_prefs</code> folder next to the application. They can be edited by hand and
copied between installations.</p>

<hr>

<h3>HTTP reference</h3>
<p><b>Base URL:</b> <code>http://localhost:8080/NeewerLux/doAction?</code></p>
<table cellpadding="4">
<tr><td><b>discover</b></td><td>Scan for new lights</td></tr>
<tr><td><b>link=N</b></td><td>Connect to light N, or <code>all</code></td></tr>
<tr><td><b>light=N&amp;mode=CCT&amp;temp=5600&amp;bri=100</b></td><td>Set a light to CCT mode</td></tr>
<tr><td><b>light=N&amp;mode=HSI&amp;hue=240&amp;sat=100&amp;bri=80</b></td><td>Set a light to HSI mode</td></tr>
<tr><td><b>light=N&amp;mode=ANM&amp;scene=1&amp;bri=50</b></td><td>Set a light to a built-in scene</td></tr>
<tr><td><b>turnoff / turnon</b></td><td>Power lights off or on</td></tr>
<tr><td><b>use_preset=N</b></td><td>Recall preset N</td></tr>
<tr><td><b>animate=Name|speed|rate|bri|loop|maxLoops|revert</b></td>
    <td>Play an animation. Only the name is required. The rest are positional and optional:
    speed (1.0), rate (5), brightness percent (80), loop (true/false), maxLoops (0 for
    endless), revert (true/false).</td></tr>
<tr><td><b>stop_animate</b></td><td>Stop the running animation</td></tr>
<tr><td><b>list / list_json</b></td><td>List lights, presets, and animations</td></tr>
<tr><td><b>animate=Name|...|revert|layer|queue|target</b></td><td>Optional layer (override, effect, show), queue mode (queue, replace) and target such as <code>@rim</code></td></tr>
<tr><td><b>stop_layer=effect</b></td><td>Stop a layer (<code>effect_all</code> also clears the effect queue; also <code>show</code>, <code>sound</code>, <code>all</code>)</td></tr>
<tr><td><b>sound=start|Pulse</b></td><td>Start a sound mode (lights following live audio); also <code>mode|Name</code>, <code>stop</code>; add <code>|1;3</code> for some lights only (<code>stop|3</code>)</td></tr>
<tr><td><b>sequence=play|Name</b></td><td>Play a sequence; also <code>pause</code>, <code>resume</code>, <code>stop</code></td></tr>
<tr><td><b>status_json</b></td><td>Layers, sequence position, and each light's layer and approximate colour</td></tr>
</table>
<p>POST to <code>/NeewerLux/batch</code> for multi-light JSON commands, to
<code>/NeewerLux/animate</code> for JSON animation control, to <code>/NeewerLux/sequence</code>
for sequences (list, reload, play, pause, resume, stop, seek, set_position, status, validate,
save, get, delete, render), to <code>/NeewerLux/sound</code> for sound modes (start, stop,
mode, set, device, status and the mode files), to <code>/NeewerLux/presets</code> to edit presets, or to
<code>/NeewerLux/settings</code> for light and show preferences (get, set_light, set_global). The web dashboard has the same Sequences, Stage and Settings panels
as this window. The full contract, including the structured light state in <code>list_json</code>,
is in <code>docs/HTTP_API.md</code>.</p>

<hr>

<p style="color:#888; font-size:0.9em;">
<b>Repository:</b> <a href="https://github.com/poizenjam/NeewerLux/">github.com/poizenjam/NeewerLux</a><br>
<b>Releases:</b> <a href="https://github.com/poizenjam/NeewerLux/releases">github.com/poizenjam/NeewerLux/releases</a><br><br>
Based on <a href="https://github.com/taburineagle/NeewerLite-Python/">NeewerLite-Python</a> (v0.12d) by Zach Glenwright.
Originally from <a href="https://github.com/keefo/NeewerLite">NeewerLite</a> by Xu Lian.
</p>
""")
        infoLay.addWidget(self.infoText)
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
        self.logTextEdit = QPlainTextEdit()
        self.logTextEdit.setReadOnly(True)
        self.logTextEdit.setFont(_monoFont(9))
        self.logTextEdit.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.logTextEdit.setMaximumBlockCount(2000)  # cap log at 2000 lines to prevent unbounded growth (CPU creep)
        logLay.addWidget(self.logTextEdit)
        self.ColorModeTabWidget.addTab(self.logTab, "Log")
        # Tab positions by name, so code doesn't depend on the tab order
        tabs = self.ColorModeTabWidget
        self.TAB_ANIM, self.TAB_SEQ = tabs.indexOf(self.animTab), tabs.indexOf(self.seqTab)
        self.TAB_SOUND = tabs.indexOf(self.soundTab)
        self.TAB_LIGHTPREFS, self.TAB_GLOBALPREFS = tabs.indexOf(self.lightPrefs), tabs.indexOf(self.globalPrefs)
        self.TAB_INFO, self.TAB_LOG = tabs.indexOf(self.infoTab), tabs.indexOf(self.logTab)

        # === ASSEMBLE ===
        bottomLay.addWidget(self.ColorModeTabWidget, 1)
        
        # Apply button, shown when live preview is disabled
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
