"""Stage window for NeewerLux: one tile per light showing roughly what it's showing now.

Simulated lights show the state built from the packets they accepted; real lights show
what was last sent to them. Colours are approximations (see neewerlux_show.commandToRGB).
The window polls a provider on the GUI thread, so no background thread touches widgets.
The StageView widget is meant to be reused as the timeline editor's preview.
"""

try:
    from PySide6.QtCore import Qt, QTimer, QRectF, QSize, QEvent
    from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics, QPixmap
    from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel, QDialog,
                                   QScrollArea, QPushButton, QFileDialog)
except ImportError:
    from PySide2.QtCore import Qt, QTimer, QRectF, QSize, QEvent
    from PySide2.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics, QPixmap
    from PySide2.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel, QDialog,
                                   QScrollArea, QPushButton, QFileDialog)

# Outline colour per layer, so it's visible at a glance what is driving each light
LAYER_COLOURS = {"base": QColor(90, 90, 90), "show": QColor(70, 140, 255),
                 "effect": QColor(255, 160, 40), "override": QColor(235, 70, 70)}


def _textWidth(fm, text):
    return fm.horizontalAdvance(text) if hasattr(fm, "horizontalAdvance") else fm.width(text)


class StageView(QWidget):
    """Draws a row (wrapping when needed) of light tiles. Call setTiles() with a list of
    dicts: name, role, rgb (tuple or None), mode, bri, linked, simulated, layer.
    All sizes come from the font, so the tiles grow with Windows display scaling and font
    size instead of clipping their text. Names too long for a tile are elided; hovering a
    tile shows the full name."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tiles = []
        self.setMouseTracking(True)
        self._applyGeometry()

    def _geometry(self):
        """(tile width, swatch height, gap, line height, small line height) from the font."""
        fm = QFontMetrics(self.font())
        sfm = QFontMetrics(self._smallFont())
        line, sline = fm.height(), sfm.height()
        longest = max([_textWidth(fm, t.get("name", "")) for t in self.tiles] + [0])
        em = _textWidth(fm, "M")
        tileW = max(120, em * 9, _textWidth(sfm, "Ambient  HSI 100%") + 12, min(longest + 12, em * 15))
        return tileW, max(60, min(int(tileW * 0.6), em * 5)), max(10, line), line + 2, sline + 2

    def _smallFont(self):
        small = QFont(self.font())
        if small.pointSizeF() > 0:
            small.setPointSizeF(max(7.0, small.pointSizeF() - 1))
        return small

    def _cell(self):
        tileW, swatchH, gap, line, sline = self._geometry()
        return tileW + gap, swatchH + line + 2 * sline + 6 + gap

    def _applyGeometry(self):
        tileW, swatchH, gap, line, sline = self._geometry()
        cw, ch = self._cell()
        self.setMinimumSize(cw + gap, ch + gap)
        self.updateGeometry()

    def changeEvent(self, event):
        if event.type() == QEvent.FontChange:
            self._applyGeometry()
        super().changeEvent(event)

    def setTiles(self, tiles):
        if tiles != self.tiles:
            resize = [t.get("name") for t in tiles] != [t.get("name") for t in self.tiles]
            self.tiles = tiles
            if resize:
                self._applyGeometry()
            self.update()

    def _columns(self):
        cw, ch = self._cell()
        return max(1, (self.width() - self._geometry()[2]) // cw)

    def sizeHint(self):
        n = max(1, len(self.tiles))
        cw, ch = self._cell()
        gap = self._geometry()[2]
        return QSize(min(n, 6) * cw + gap, ((n + 5) // 6) * ch + gap)

    def _tileAt(self, pos):
        cw, ch = self._cell()
        gap = self._geometry()[2]
        col, row = int((pos.x() - gap) // cw), int((pos.y() - gap) // ch)
        if pos.x() < gap or pos.y() < gap or col >= self._columns():
            return None
        n = row * self._columns() + col
        return self.tiles[n] if 0 <= n < len(self.tiles) else None

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        t = self._tileAt(pos)
        self.setToolTip(t.get("name", "") if t else "")
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(24, 24, 24))
        if not self.tiles:
            p.setPen(QColor(160, 160, 160))
            p.drawText(self.rect(), Qt.AlignCenter, "No lights yet")
            return
        tileW, swatchH, gap, line, sline = self._geometry()
        cw, ch = self._cell()
        cols = self._columns()
        font, small = self.font(), self._smallFont()
        fm, sfm = QFontMetrics(font), QFontMetrics(small)
        for n, t in enumerate(self.tiles):
            x = gap + (n % cols) * cw
            y = gap + (n // cols) * ch
            box = QRectF(x, y, tileW, swatchH)
            rgb = t.get("rgb")
            fill = QColor(*rgb) if rgb is not None else QColor(55, 55, 55)
            if not t.get("linked"):
                fill = fill.darker(250)
            p.setBrush(fill)
            p.setPen(QPen(LAYER_COLOURS.get(t.get("layer"), LAYER_COLOURS["base"]), 4))
            p.drawRoundedRect(box, 10, 10)
            if rgb is None:
                p.setPen(QColor(200, 200, 200))
                p.setFont(font)
                p.drawText(box, Qt.AlignCenter, "?")
            if t.get("simulated"):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 150))
                badge = QRectF(x + 6, y + 6, _textWidth(sfm, "SIM") + 10, sline)
                p.drawRoundedRect(badge, 4, 4)
                p.setPen(QColor(230, 230, 230))
                p.setFont(small)
                p.drawText(badge, Qt.AlignCenter, "SIM")
            ty = y + swatchH + 4
            p.setFont(font)
            p.setPen(QColor(235, 235, 235))
            name = fm.elidedText(t.get("name", ""), Qt.ElideMiddle, int(tileW))
            p.drawText(QRectF(x, ty, tileW, line), Qt.AlignHCenter | Qt.AlignTop, name)
            p.setFont(small)
            p.setPen(QColor(170, 170, 170))
            detail = t.get("role", "").capitalize()
            if t.get("mode"):
                detail += "  " + t["mode"] + ("" if t["mode"] == "OFF" else " " + str(t.get("bri", "")) + "%")
            detail = sfm.elidedText(detail, Qt.ElideRight, int(tileW))
            p.drawText(QRectF(x, ty + line, tileW, sline), Qt.AlignHCenter | Qt.AlignTop, detail)
            status = t.get("layer", "base") if t.get("linked") else "not linked"
            p.drawText(QRectF(x, ty + line + sline, tileW, sline), Qt.AlignHCenter | Qt.AlignTop, status)


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
        legend.setWordWrap(True)
        row.addWidget(legend, 1)
        self.onTopCheck = QCheckBox("Always on top")
        self.onTopCheck.toggled.connect(self._setOnTop)
        row.addWidget(self.onTopCheck)
        lay.addLayout(row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        cw, ch = self.view._cell()
        gap = self.view._geometry()[2]
        self.resize(4 * cw + gap + 12, ch + gap + legend.sizeHint().height() + 24)

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
