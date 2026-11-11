"""Stage window for NeewerLux: one tile per light showing roughly what it's showing now.

Simulated lights show the state built from the packets they accepted; real lights show
what was last sent to them. Colours are approximations (see neewerlux_show.commandToRGB).
The window polls a provider on the GUI thread, so no background thread touches widgets.
The StageView widget is meant to be reused as the timeline editor's preview.
"""

try:
    from PySide6.QtCore import Qt, QTimer, QRectF, QSize, QEvent, QPointF
    from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics, QPixmap, QPolygonF
    from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel, QDialog,
                                   QScrollArea, QPushButton, QFileDialog, QComboBox)
except ImportError:
    from PySide2.QtCore import Qt, QTimer, QRectF, QSize, QEvent, QPointF
    from PySide2.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics, QPixmap, QPolygonF
    from PySide2.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel, QDialog,
                                   QScrollArea, QPushButton, QFileDialog, QComboBox)

# Outline colour per layer, so it's visible at a glance what is driving each light
LAYER_COLOURS = {"base": QColor(90, 90, 90), "show": QColor(70, 140, 255),
                 "effect": QColor(255, 160, 40), "override": QColor(235, 70, 70)}


def _textWidth(fm, text):
    return fm.horizontalAdvance(text) if hasattr(fm, "horizontalAdvance") else fm.width(text)


PLAN_SIDES = ["left", "centre", "right"]      # columns: the streamer's left to right
PLAN_DEPTHS = ["front", "beside", "back"]     # plan rows: front (towards the camera) at the top
HEIGHT_ROWS = ["high", "middle", "low"]       # height view rows, top to bottom
HEIGHT_LEVEL = {"low": 1, "middle": 2, "high": 3}
VIEW_MODES = ["plan", "height", "strip"]
# where a light points, as (dx, dy) on the plan (front is up); "you" is worked out per light
AIM_VECTORS = {"front": (0, -1), "front-right": (1, -1), "right": (1, 0), "back-right": (1, 1),
               "back": (0, 1), "back-left": (-1, 1), "left": (-1, 0), "front-left": (-1, -1)}
CAMERA_POSITIONS = ["front-left", "front", "front-right", "left", "right", "back-left", "back", "back-right"]


def drawPerson(p, cx, cy, size, colour=QColor(125, 125, 125)):
    """A top-down head and shoulders facing the front (up), centred on (cx, cy), with a faint
    view cone so which way they face reads at a glance."""
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 18))
    p.drawPolygon(QPolygonF([QPointF(cx, cy - size * 0.1), QPointF(cx - size * 0.55, cy - size * 0.95),
                             QPointF(cx + size * 0.55, cy - size * 0.95)]))                     # looking forward
    p.setBrush(colour.darker(115))
    p.drawRoundedRect(QRectF(cx - size * 0.5, cy - size * 0.05, size, size * 0.34), size * 0.17, size * 0.17)  # shoulders
    p.setBrush(colour.lighter(125))
    p.drawEllipse(QRectF(cx - size * 0.2, cy - size * 0.24, size * 0.4, size * 0.44))       # head
    p.drawPolygon(QPolygonF([QPointF(cx - size * 0.08, cy - size * 0.2), QPointF(cx + size * 0.08, cy - size * 0.2),
                             QPointF(cx, cy - size * 0.33)]))                                  # nose
    p.restore()


def drawCamera(p, cx, cy, size, facing, colour=QColor(150, 150, 150)):
    """A small camera body with a lens pointing along facing (dx, dy), centred on (cx, cy)."""
    import math
    p.save()
    p.translate(cx, cy)
    dx, dy = facing
    p.rotate(math.degrees(math.atan2(dy, dx)) - 90)  # body drawn with the lens towards +y
    p.setPen(Qt.NoPen)
    p.setBrush(colour)
    p.drawRoundedRect(QRectF(-size * 0.45, -size * 0.35, size * 0.9, size * 0.6), 3, 3)
    p.drawPolygon(QPolygonF([QPointF(-size * 0.18, size * 0.25), QPointF(size * 0.18, size * 0.25),
                             QPointF(size * 0.3, size * 0.55), QPointF(-size * 0.3, size * 0.55)]))
    p.restore()


def drawLevelGauge(p, rect, level):
    """Three bars, low to high, filled up to the light's height (1 to 3)."""
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 150))
    p.drawRoundedRect(rect, 4, 4)
    inner = rect.adjusted(4, 3, -4, -3)
    barH = inner.height() / 3.0
    for i in range(3):  # i = 0 is the top bar (high)
        filled = (3 - i) <= level
        p.setBrush(QColor(235, 235, 235) if filled else QColor(90, 90, 90))
        p.drawRect(QRectF(inner.x(), inner.y() + i * barH + 1, inner.width(), barH - 2))
    p.restore()


class StageView(QWidget):
    """Draws light tiles in one of three views:
      plan    top-down 3 x 3 grid from the streamer's seat (your left to right, front at the
              top), you in the middle, the camera at its set position, each light's height as
              a gauge and its aim as a beam;
      height  the same columns with high, middle and low rows (as you face the camera);
      strip   a row in sweep order, wrapping when needed.
    Call setTiles() with a list of dicts: name, role, rgb (tuple or None), mode, bri, linked,
    simulated, layer, side, depth, height, aim. All sizes come from the font, so the tiles
    grow with Windows display scaling and font size instead of clipping their text. Names
    too long for a tile are elided; hovering a tile shows the full name."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tiles = []
        self.viewMode = "plan"
        self.camera = "front"
        self.setMouseTracking(True)
        self._applyGeometry()

    @property
    def planMode(self):
        return self.viewMode == "plan"

    def setViewMode(self, mode):
        mode = mode if mode in VIEW_MODES else "plan"
        if mode != self.viewMode:
            self.viewMode = mode
            self._applyGeometry()
            self.update()

    def setPlanMode(self, on):  # older callers
        self.setViewMode("plan" if on else "strip")

    def setCamera(self, position):
        position = position if position in CAMERA_POSITIONS else "front"
        if position != self.camera:
            self.camera = position
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
        if self.viewMode == "strip":
            self.setMinimumSize(cw + gap, ch + gap)
        else:
            self.setMinimumSize(*self._gridSize())
        self.updateGeometry()

    def _rows(self):
        return PLAN_DEPTHS if self.viewMode == "plan" else HEIGHT_ROWS

    def _gridCells(self):
        """{(side, row): [tile indices]} in the order given (sweep order)."""
        cells = {}
        rows = self._rows()
        rowKey = "depth" if self.viewMode == "plan" else "height"
        for n, t in enumerate(self.tiles):
            side = t.get("side") if t.get("side") in PLAN_SIDES else "centre"
            row = t.get(rowKey) if t.get(rowKey) in rows else rows[1]
            cells.setdefault((side, row), []).append(n)
        return cells

    def _gridMetrics(self):
        """(left edge of the grid, top edge, column widths per side, row height, margin)."""
        tileW, swatchH, gap, line, sline = self._geometry()
        cw, ch = self._cell()
        fm = QFontMetrics(self._smallFont())
        margin = sline * 2 + 4  # room for the camera around the grid
        labelW = max(_textWidth(fm, w) for w in ("Front", "Beside", "Back", "Middle")) + gap
        cells = self._gridCells()
        colW = [max([len(cells.get((side, r), [])) for r in self._rows()] + [1]) * cw for side in PLAN_SIDES]
        natural = labelW + margin + sum(colW) + margin
        shift = max(0, (self.width() - natural) / 2.0)  # centred when the window is wider than the grid
        return labelW + margin + shift, sline + 4 + margin, colW, ch, margin

    def _gridSize(self):
        tileW, swatchH, gap, line, sline = self._geometry()
        fm = QFontMetrics(self._smallFont())
        labelW = max(_textWidth(fm, w) for w in ("Front", "Beside", "Back", "Middle")) + gap
        x0, y0, colW, rowH, margin = self._gridMetrics()
        return int(labelW + 2 * margin + sum(colW)), int(y0 + 3 * rowH + margin)

    def _layout(self):
        """[(tile index, x, y)] for every tile in the current view."""
        tileW, swatchH, gap, line, sline = self._geometry()
        cw, ch = self._cell()
        if self.viewMode == "strip":
            cols = self._columns()
            return [(n, gap + (n % cols) * cw, gap + (n // cols) * ch) for n in range(len(self.tiles))]
        x0, y0, colW, rowH, margin = self._gridMetrics()
        rows = self._rows()
        out = []
        for (side, row), members in self._gridCells().items():
            c, r = PLAN_SIDES.index(side), rows.index(row)
            xs = x0 + sum(colW[:c]) + (colW[c] - len(members) * cw) / 2.0
            for k, n in enumerate(members):
                out.append((n, xs + k * cw, y0 + r * rowH))
        return out

    def changeEvent(self, event):
        if event.type() == QEvent.FontChange:
            self._applyGeometry()
        super().changeEvent(event)

    def setTiles(self, tiles):
        if tiles != self.tiles:
            shape = lambda ts: [(t.get("name"), t.get("side"), t.get("depth"), t.get("height")) for t in ts]
            resize = shape(tiles) != shape(self.tiles)
            self.tiles = tiles
            if resize:
                self._applyGeometry()
            self.update()

    def _columns(self):
        cw, ch = self._cell()
        return max(1, (self.width() - self._geometry()[2]) // cw)

    def sizeHint(self):
        if self.viewMode != "strip":
            return QSize(*self._gridSize())
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
                tip += "\n%s, %s, %s height" % (t.get("side", "centre"), t.get("depth", "beside"), t.get("height", "middle"))
                tip += "\npoints " + ("at you" if t.get("aim", "you") == "you" else t.get("aim"))
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
        layout = self._layout()
        if self.viewMode != "strip":
            self._paintGrid(p, small)
        if self.viewMode == "plan":
            self._paintBeams(p, layout)
        for n, x, y in layout:
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
            if self.viewMode == "plan" and t.get("height") in HEIGHT_LEVEL:
                gw = max(14, sline * 0.8)
                drawLevelGauge(p, QRectF(x + tileW - gw - 6, y + 6, gw, sline * 1.4), HEIGHT_LEVEL[t["height"]])
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

    def _cellRect(self, c, r):
        x0, y0, colW, rowH, margin = self._gridMetrics()
        gap = self._geometry()[2]
        return QRectF(x0 + sum(colW[:c]) - gap / 4.0, y0 + r * rowH - gap / 4.0, colW[c] - gap / 2.0, rowH - gap / 2.0)

    def _paintGrid(self, p, small):
        """Cell outlines, row and column names, you, and the camera."""
        x0, y0, colW, rowH, margin = self._gridMetrics()
        p.setFont(small)
        p.setPen(QColor(130, 130, 130))
        for c, name in enumerate(["Your left", "Centre", "Your right"]):
            p.drawText(QRectF(x0 + sum(colW[:c]), y0 - QFontMetrics(small).height() - 4, colW[c], QFontMetrics(small).height()),
                       Qt.AlignCenter, name)
        names = ["Front", "Beside", "Back"] if self.viewMode == "plan" else ["High", "Middle", "Low"]
        for r, name in enumerate(names):
            p.drawText(QRectF(0, y0 + r * rowH, x0 - 6, rowH), Qt.AlignRight | Qt.AlignVCenter, name)
        p.setPen(QPen(QColor(50, 50, 50), 1, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        for r in range(3):
            for c in range(3):
                p.drawRoundedRect(self._cellRect(c, r), 6, 6)
        if self.viewMode != "plan":
            return
        you = self._cellRect(1, 1)
        if ("centre", "beside") not in self._gridCells():
            drawPerson(p, you.center().x(), you.center().y(), min(you.width(), you.height()) * 0.45)
        else:  # a light is placed on you: draw the figure small in the corner
            drawPerson(p, you.right() - 22, you.bottom() - 18, 30)
        # the camera sits just outside the grid, facing you
        gridRect = QRectF(self._cellRect(0, 0).topLeft(), self._cellRect(2, 2).bottomRight())
        cols = {"left": 0, "centre": 1, "right": 2}
        cam = self.camera
        side = "left" if cam.endswith("left") else "right" if cam.endswith("right") else "centre"
        depth = "front" if cam.startswith("front") else "back" if cam.startswith("back") else "beside"
        c, r = cols[side], PLAN_DEPTHS.index(depth)
        cell = self._cellRect(c, r)
        labelW = x0 - margin - max(0, (self.width() - (x0 - margin + sum(colW) + margin)) / 2.0)
        leftEdge = gridRect.left() - labelW - margin / 2.0   # outside the row names
        cx = leftEdge if side == "left" and depth == "beside" else \
            gridRect.right() + margin / 2.0 if side == "right" and depth == "beside" else cell.center().x()
        cy = margin / 2.0 + 2 if depth == "front" else gridRect.bottom() + margin / 2.0 if depth == "back" else cell.center().y()
        if depth != "beside" and side != "centre":  # corners: push out sideways too
            cx = gridRect.left() - margin / 2.0 if side == "left" else gridRect.right() + margin / 2.0
        facing = (you.center().x() - cx, you.center().y() - cy)
        drawCamera(p, cx, cy, margin * 0.8, facing)
        p.setPen(QColor(110, 110, 110))
        p.setFont(small)
        if depth == "front" and side == "centre":
            p.drawText(QRectF(cx + margin * 0.6, cy - margin / 2.0, 120, margin), Qt.AlignLeft | Qt.AlignVCenter, "camera")

    def _paintBeams(self, p, layout):
        """A soft wedge from each light in the direction it points."""
        import math
        tileW, swatchH, gap, line, sline = self._geometry()
        you = self._cellRect(1, 1).center()
        for n, x, y in layout:
            t = self.tiles[n]
            cx, cy = x + tileW / 2.0, y + swatchH / 2.0
            aim = t.get("aim", "you")
            if aim in AIM_VECTORS:
                dx, dy = AIM_VECTORS[aim]
            else:
                dx, dy = you.x() - cx, you.y() - cy
                if abs(dx) < 1 and abs(dy) < 1:
                    continue
            ang = math.atan2(dy, dx)
            length = swatchH * 1.6
            spread = math.radians(18)
            rgb = t.get("rgb") or (120, 120, 120)
            colour = QColor(rgb[0], rgb[1], rgb[2], 70)
            poly = QPolygonF([QPointF(cx, cy),
                              QPointF(cx + length * math.cos(ang - spread), cy + length * math.sin(ang - spread)),
                              QPointF(cx + length * math.cos(ang + spread), cy + length * math.sin(ang + spread))])
            p.setPen(Qt.NoPen)
            p.setBrush(colour)
            p.drawPolygon(poly)


class StageWindow(QWidget):
    """Floating window around a StageView. provider() returns the tile list; it is polled
    20 times a second while the window is visible and not at all while it's hidden."""

    def __init__(self, provider, parent=None, view="plan", geometry="", remember=None):
        super().__init__(parent, Qt.Window)
        self.provider = provider
        self.remember = remember   # remember(view, "x,y,w,h") keeps them for next time
        self._userSized = False
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
        self.viewCombo = QComboBox()
        self.viewCombo.addItems(["Plan (from above)", "Height (facing the camera)", "Strip (sweep order)"])
        self.viewCombo.setToolTip("Plan: where each light stands, from your seat facing the camera, with its height\n"
                                  "as bars and its aim as a beam. Height: the same columns, high to low.\n"
                                  "Strip: one row in sweep order. Positions are set in Light Preferences.")
        self.viewCombo.currentIndexChanged.connect(lambda i: self._setView(VIEW_MODES[i]))
        row.addWidget(self.viewCombo)
        self.onTopCheck = QCheckBox("Always on top")
        self.onTopCheck.toggled.connect(self._setOnTop)
        row.addWidget(self.onTopCheck)
        lay.addLayout(row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self._legendH = legend.sizeHint().height()
        self._restoring = True
        self.viewCombo.setCurrentIndex(VIEW_MODES.index(view) if view in VIEW_MODES else 0)
        self.view.setViewMode(view if view in VIEW_MODES else "plan")
        try:
            x, y, w, h = [int(v) for v in str(geometry).split(",")]
            self.setGeometry(x, y, w, h)
            self._userSized = True
        except ValueError:
            self.refreshTiles()  # size to the lights, not to an empty view
            self._fit()
        self._restoring = False

    def refreshTiles(self):
        tiles = self.provider()
        if tiles and "camera" in tiles[0]:
            self.view.setCamera(tiles[0]["camera"])
        self.view.setTiles(tiles)

    def _fit(self):
        """Size the window to the view (the grid views have a natural size)."""
        hint = self.view.sizeHint()
        self._restoring, was = True, self._restoring
        self.resize(max(hint.width() + 12, 520), hint.height() + self._legendH + 30)
        self._restoring = was

    def _setView(self, mode):
        self.view.setViewMode(mode)
        if not self._restoring:
            self._userSized = False
            self._fit()
            self._save()

    def _save(self):
        if self.remember is not None and not self._restoring:
            g = self.geometry()
            self.remember(self.view.viewMode, "%d,%d,%d,%d" % (g.x(), g.y(), g.width(), g.height()) if self._userSized else "")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._restoring and self.isVisible():
            self._userSized = True

    def moveEvent(self, event):
        super().moveEvent(event)

    def closeEvent(self, event):
        self._save()
        super().closeEvent(event)

    def _setOnTop(self, on):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.show()  # changing window flags hides the window until it's shown again

    def refresh(self):
        before = self.view.sizeHint()
        self.refreshTiles()
        if self.view.viewMode != "strip" and self.view.sizeHint() != before and not self.isMaximized() and not self._userSized:
            self._fit()

    def showEvent(self, event):
        self.refresh()
        self.timer.start(50)
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        self._save()
        super().hideEvent(event)


class _RenderStrip(QLabel):
    """The render image with the play marker drawn over it; a click asks to seek there."""

    def __init__(self, pix, axis, onClick):
        super().__init__()
        self.setPixmap(pix)
        self.axis = axis
        self.onClick = onClick
        self.positionMs = None
        if axis:
            self.setCursor(Qt.PointingHandCursor)

    def _x(self, ms):
        a = self.axis
        span = max(1, a["end_ms"] - a["start_ms"])
        return a["x0"] + (ms - a["start_ms"]) * a["width"] / float(span)

    def msAt(self, x):
        a = self.axis
        span = max(1, a["end_ms"] - a["start_ms"])
        return max(a["start_ms"], min(a["end_ms"], a["start_ms"] + (x - a["x0"]) * span / float(a["width"])))

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.axis and self.positionMs is not None:
            p = QPainter(self)
            x = self._x(self.positionMs)
            p.setPen(QPen(QColor(255, 255, 255), 2))
            p.drawLine(int(x), 0, int(x), self.height())
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255))
            p.drawPolygon(QPolygonF([QPointF(x - 6, 0), QPointF(x + 6, 0), QPointF(x, 8)]))

    def mousePressEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if self.axis and pos.x() >= self.axis["x0"] and self.onClick:
            self.onClick(self.msAt(pos.x()))
        super().mousePressEvent(event)


class RenderDialog(QDialog):
    """Shows a sequence's render strip, with a button to save it as a PNG. With axis (where
    time runs on the image) and position (ms if this sequence is playing, else None), a play
    marker follows playback, and clicking the strip seeks there."""

    def __init__(self, pngBytes, sequenceName, parent=None, axis=None, position=None, seek=None):
        super().__init__(parent)
        self.pngBytes = pngBytes
        self.sequenceName = sequenceName
        self.position = position
        self.seek = seek
        self.setWindowTitle("Render: " + sequenceName)
        lay = QVBoxLayout(self)
        pix = QPixmap()
        pix.loadFromData(pngBytes, "PNG")
        self.strip = _RenderStrip(pix, axis, self._clicked)
        scroll = QScrollArea()
        scroll.setWidget(self.strip)
        lay.addWidget(scroll, 1)
        row = QHBoxLayout()
        self.hint = QLabel("Rows are lights in their table order; thin lines mark cue starts. Colours are approximate."
                           + (" While this sequence plays, a marker shows where it is; click to jump there." if axis and position else ""))
        self.hint.setWordWrap(True)
        row.addWidget(self.hint, 1)
        save = QPushButton("Save PNG...")
        save.clicked.connect(self._save)
        row.addWidget(save)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        self.resize(min(pix.width() + 40, 1700), min(pix.height() + 90, 800))
        if axis and position:
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._tick)
            self.timer.start(50)
            self._tick()

    def _tick(self):
        pos = self.position()
        if pos != self.strip.positionMs:
            self.strip.positionMs = pos
            self.strip.update()

    def _clicked(self, ms):
        if self.seek is not None and self.position is not None and self.position() is not None:
            self.seek(int(ms))
            self._tick()

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save render", self.sequenceName + ".png", "PNG image (*.png)")
        if path:
            with open(path, "wb") as f:
                f.write(self.pngBytes)
