"""Stage window for NeewerLux: one tile per light showing roughly what it's showing now.

Simulated lights show the state built from the packets they accepted; real lights show
what was last sent to them. Colours are approximations (see neewerlux_show.commandToRGB).
The window polls a provider on the GUI thread, so no background thread touches widgets.
The StageView widget is meant to be reused as the timeline editor's preview.
"""

try:
    from PySide6.QtCore import Qt, QTimer, QRectF, QSize
    from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPixmap
    from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel, QDialog,
                                   QScrollArea, QPushButton, QFileDialog)
except ImportError:
    from PySide2.QtCore import Qt, QTimer, QRectF, QSize
    from PySide2.QtGui import QColor, QPainter, QPen, QFont, QPixmap
    from PySide2.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel, QDialog,
                                   QScrollArea, QPushButton, QFileDialog)

# Outline colour per layer, so it's visible at a glance what is driving each light
LAYER_COLOURS = {"base": QColor(90, 90, 90), "show": QColor(70, 140, 255),
                 "effect": QColor(255, 160, 40), "override": QColor(235, 70, 70)}
TILE_W, TILE_H, GAP, TEXT_H = 120, 90, 14, 58


class StageView(QWidget):
    """Draws a row (wrapping when needed) of light tiles. Call setTiles() with a list of
    dicts: name, role, rgb (tuple or None), mode, bri, linked, simulated, layer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tiles = []
        self.setMinimumSize(TILE_W + 2 * GAP, TILE_H + TEXT_H + 2 * GAP)

    def setTiles(self, tiles):
        if tiles != self.tiles:
            self.tiles = tiles
            self.update()

    def _columns(self):
        return max(1, (self.width() - GAP) // (TILE_W + GAP))

    def sizeHint(self):
        n = max(1, len(self.tiles))
        return QSize(min(n, 6) * (TILE_W + GAP) + GAP, ((n + 5) // 6) * (TILE_H + TEXT_H + GAP) + GAP)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(24, 24, 24))
        if not self.tiles:
            p.setPen(QColor(160, 160, 160))
            p.drawText(self.rect(), Qt.AlignCenter, "No lights yet")
            return
        cols = self._columns()
        small = QFont(self.font())
        small.setPointSizeF(max(7.0, small.pointSizeF() - 1))
        for n, t in enumerate(self.tiles):
            x = GAP + (n % cols) * (TILE_W + GAP)
            y = GAP + (n // cols) * (TILE_H + TEXT_H + GAP)
            box = QRectF(x, y, TILE_W, TILE_H)
            rgb = t.get("rgb")
            fill = QColor(*rgb) if rgb is not None else QColor(55, 55, 55)
            if not t.get("linked"):
                fill = fill.darker(250)
            p.setBrush(fill)
            p.setPen(QPen(LAYER_COLOURS.get(t.get("layer"), LAYER_COLOURS["base"]), 4))
            p.drawRoundedRect(box, 10, 10)
            if rgb is None:
                p.setPen(QColor(200, 200, 200))
                p.drawText(box, Qt.AlignCenter, "?")
            if t.get("simulated"):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 150))
                badge = QRectF(x + 6, y + 6, 34, 16)
                p.drawRoundedRect(badge, 4, 4)
                p.setPen(QColor(230, 230, 230))
                p.setFont(small)
                p.drawText(badge, Qt.AlignCenter, "SIM")
            p.setFont(self.font())
            p.setPen(QColor(235, 235, 235))
            p.drawText(QRectF(x, y + TILE_H + 2, TILE_W, 18), Qt.AlignHCenter | Qt.AlignTop, t.get("name", ""))
            p.setFont(small)
            p.setPen(QColor(170, 170, 170))
            detail = t.get("role", "").capitalize()
            if t.get("mode"):
                detail += "  " + t["mode"] + ("" if t["mode"] == "OFF" else " " + str(t.get("bri", "")) + "%")
            p.drawText(QRectF(x, y + TILE_H + 20, TILE_W, 16), Qt.AlignHCenter | Qt.AlignTop, detail)
            status = t.get("layer", "base") if t.get("linked") else "not linked"
            p.drawText(QRectF(x, y + TILE_H + 36, TILE_W, 16), Qt.AlignHCenter | Qt.AlignTop, status)


class StageWindow(QWidget):
    """Floating window around a StageView. provider() returns the tile list; it is polled
    20 times a second while the window is visible and not at all while it's hidden."""

    def __init__(self, provider, parent=None):
        super().__init__(parent, Qt.Window)
        self.provider = provider
        self.setWindowTitle("NeewerLux Stage")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.view = StageView(self)
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        legend = QLabel("Outline: grey = manual/preset, blue = sequence, orange = effect, red = override animation")
        legend.setStyleSheet("color: #999;")
        row.addWidget(legend, 1)
        self.onTopCheck = QCheckBox("Always on top")
        self.onTopCheck.toggled.connect(self._setOnTop)
        row.addWidget(self.onTopCheck)
        lay.addLayout(row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.resize(4 * (TILE_W + GAP) + GAP + 12, TILE_H + TEXT_H + 2 * GAP + 40)

    def _setOnTop(self, on):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.show()  # changing window flags hides the window until it's shown again

    def refresh(self):
        self.view.setTiles(self.provider())

    def showEvent(self, event):
        self.refresh()
        self.timer.start(50)
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)


class RenderDialog(QDialog):
    """Shows a sequence's render strip, with a button to save it as a PNG."""

    def __init__(self, pngBytes, sequenceName, parent=None):
        super().__init__(parent)
        self.pngBytes = pngBytes
        self.sequenceName = sequenceName
        self.setWindowTitle("Render: " + sequenceName)
        lay = QVBoxLayout(self)
        pix = QPixmap()
        pix.loadFromData(pngBytes, "PNG")
        img = QLabel()
        img.setPixmap(pix)
        scroll = QScrollArea()
        scroll.setWidget(img)
        lay.addWidget(scroll, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("Rows are lights in their table order; thin lines mark cue starts. Colours are approximate."), 1)
        save = QPushButton("Save PNG...")
        save.clicked.connect(self._save)
        row.addWidget(save)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        self.resize(min(pix.width() + 40, 1700), min(pix.height() + 90, 800))

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save render", self.sequenceName + ".png", "PNG image (*.png)")
        if path:
            with open(path, "wb") as f:
                f.write(self.pngBytes)
