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


PLAN_SIDES = ["left", "centre", "right"]      # columns: the streamer's left to right
PLAN_DEPTHS = ["front", "beside", "back"]     # rows: front (towards the camera) at the top
HEIGHT_BADGES = {"low": "L", "middle": "M", "high": "H"}


class StageView(QWidget):
    """Draws light tiles, either as a row in sweep order (wrapping when needed) or as a plan:
    a top-down 3 x 3 grid from the streamer's seat (your left to right, front at the top),
    with each light in its cell and its height as a badge. Call setTiles() with a list of
    dicts: name, role, rgb (tuple or None), mode, bri, linked, simulated, layer, and for the
    plan side, depth, height. All sizes come from the font, so the tiles grow with Windows
    display scaling and font size instead of clipping their text. Names too long for a tile
    are elided; hovering a tile shows the full name."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tiles = []
        self.planMode = False
        self.setMouseTracking(True)
        self._applyGeometry()

    def setPlanMode(self, on):
        if bool(on) != self.planMode:
            self.planMode = bool(on)
            self._applyGeometry()
            self.update()

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
        if self.planMode:
            w, h = self._planSize()
            self.setMinimumSize(w, h)
        else:
            self.setMinimumSize(cw + gap, ch + gap)
        self.updateGeometry()

    def _planCells(self):
        """{(side, depth): [tile indices]} in the order given (sweep order)."""
        cells = {}
        for n, t in enumerate(self.tiles):
            side = t.get("side") if t.get("side") in PLAN_SIDES else "centre"
            depth = t.get("depth") if t.get("depth") in PLAN_DEPTHS else "beside"
            cells.setdefault((side, depth), []).append(n)
        return cells

    def _planMetrics(self):
        """(label column width, header height, column widths per side, row height)."""
        tileW, swatchH, gap, line, sline = self._geometry()
        cw, ch = self._cell()
        fm = QFontMetrics(self._smallFont())
        labelW = max(_textWidth(fm, w) for w in ("Front", "Beside", "Back")) + gap
        cells = self._planCells()
        colW = [max([len(cells.get((side, d), [])) for d in PLAN_DEPTHS] + [1]) * cw for side in PLAN_SIDES]
        return labelW, sline + 4, colW, ch

    def _planSize(self):
        labelW, headH, colW, rowH = self._planMetrics()
        gap = self._geometry()[2]
        return labelW + sum(colW) + gap, headH + 3 * rowH + gap

    def _layout(self):
        """[(tile index, x, y)] for every tile in the current mode."""
        tileW, swatchH, gap, line, sline = self._geometry()
        cw, ch = self._cell()
        if not self.planMode:
            cols = self._columns()
            return [(n, gap + (n % cols) * cw, gap + (n // cols) * ch) for n in range(len(self.tiles))]
        labelW, headH, colW, rowH = self._planMetrics()
        out = []
        for (side, depth), members in self._planCells().items():
            c, r = PLAN_SIDES.index(side), PLAN_DEPTHS.index(depth)
            x0 = labelW + sum(colW[:c]) + (colW[c] - len(members) * cw) / 2.0
            for k, n in enumerate(members):
                out.append((n, x0 + k * cw, headH + r * rowH))
        return out

    def changeEvent(self, event):
        if event.type() == QEvent.FontChange:
            self._applyGeometry()
        super().changeEvent(event)

    def setTiles(self, tiles):
        if tiles != self.tiles:
            shape = lambda ts: [(t.get("name"), t.get("side"), t.get("depth")) for t in ts]
            resize = shape(tiles) != shape(self.tiles)
            self.tiles = tiles
            if resize:
                self._applyGeometry()
            self.update()

    def _columns(self):
        cw, ch = self._cell()
        return max(1, (self.width() - self._geometry()[2]) // cw)

    def sizeHint(self):
        if self.planMode:
            return QSize(*self._planSize())
        n = max(1, len(self.tiles))
        cw, ch = self._cell()
        gap = self._geometry()[2]
        return QSize(min(n, 6) * cw + gap, ((n + 5) // 6) * ch + gap)

    def _tileAt(self, pos):
        tileW, swatchH, gap, line, sline = self._geometry()
        cw, ch = self._cell()
        for n, x, y in self._layout():
            if x <= pos.x() < x + tileW and y <= pos.y() < y + ch - gap:
                return self.tiles[n]
        return None

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        t = self._tileAt(pos)
        tip = ""
        if t:
            tip = t.get("name", "")
            if t.get("depth") or t.get("height"):
                tip += "\n%s, %s, %s" % (t.get("side", "centre"), t.get("depth", "beside"), t.get("height", "middle"))
        self.setToolTip(tip)
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
        font, small = self.font(), self._smallFont()
        fm, sfm = QFontMetrics(font), QFontMetrics(small)
        if self.planMode:
            self._paintPlanGrid(p, small)
        for n, x, y in self._layout():
            t = self.tiles[n]
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
            if self.planMode and t.get("height") in HEIGHT_BADGES:
                label = HEIGHT_BADGES[t["height"]]
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 150))
                bw = _textWidth(sfm, "M") + 10
                hb = QRectF(x + tileW - bw - 6, y + 6, bw, sline)
                p.drawRoundedRect(hb, 4, 4)
                p.setPen(QColor(230, 230, 230))
                p.setFont(small)
                p.drawText(hb, Qt.AlignCenter, label)
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


    def _paintPlanGrid(self, p, small):
        """Cell outlines, row and column names, and where the streamer sits."""
        labelW, headH, colW, rowH = self._planMetrics()
        gap = self._geometry()[2]
        p.setFont(small)
        for c, name in enumerate(["Your left", "Centre", "Your right"]):
            x = labelW + sum(colW[:c])
            p.setPen(QColor(130, 130, 130))
            p.drawText(QRectF(x, 0, colW[c], headH), Qt.AlignCenter, name)
        for r, name in enumerate(["Front", "Beside", "Back"]):
            p.setPen(QColor(130, 130, 130))
            p.drawText(QRectF(0, headH + r * rowH, labelW - 4, rowH - gap), Qt.AlignRight | Qt.AlignVCenter, name)
        p.setPen(QPen(QColor(50, 50, 50), 1, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        for r in range(3):
            for c in range(3):
                x = labelW + sum(colW[:c])
                p.drawRoundedRect(QRectF(x - gap / 4.0, headH + r * rowH - gap / 4.0, colW[c] - gap / 2.0, rowH - gap / 2.0), 6, 6)
        if ("centre", "beside") not in self._planCells():
            x = labelW + colW[0]
            p.setPen(QColor(110, 110, 110))
            p.drawText(QRectF(x, headH + rowH, colW[1], rowH - gap), Qt.AlignCenter, "(you)")


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
        self.planCheck = QCheckBox("Plan view")
        self.planCheck.setToolTip("Show the lights where they stand, from your seat facing the camera\n"
                                  "(set each light's position in Light Preferences). Badges: L, M, H = height.")
        self.planCheck.toggled.connect(self._setPlan)
        row.addWidget(self.planCheck)
        self.onTopCheck = QCheckBox("Always on top")
        self.onTopCheck.toggled.connect(self._setOnTop)
        row.addWidget(self.onTopCheck)
        lay.addLayout(row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        cw, ch = self.view._cell()
        gap = self.view._geometry()[2]
        self.resize(4 * cw + gap + 12, ch + gap + legend.sizeHint().height() + 24)

    def _setPlan(self, on):
        self.view.setPlanMode(on)
        if on:
            hint = self.view.sizeHint()
            self.resize(max(self.width(), hint.width() + 12), max(self.height(), hint.height() + 60))

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
