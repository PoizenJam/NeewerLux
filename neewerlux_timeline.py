"""Timeline editor for NeewerLux sequences.

One track per light, in sweep order. Cues sit on the tracks of every light they drive, so a
cue aimed at several lights shows on each of them and moves as one. Under each track, a
thin band shows what the light really does (the render, with limits and CCT-only
conversion applied). A preview plays on screen through a Stage view; "Send to lights" plays
the edit through the real lights from the playhead.

The editor knows nothing about Bluetooth or NeewerLux's globals: everything it needs comes
from a host object (see SequenceEditor.__init__), so the same window can be driven by the
desktop app and by tests. Data is the sequence JSON itself (docs/SEQUENCE_FORMAT.md).
"""

import copy
import json
import time

import neewerlux_show as show
from neewerlux_stage import StageView
from neewerlux_ui import SpinBoxWithButtons, DoubleSpinBoxWithButtons, FlowLayout, adjustableColumns, ColourPickRow, ColourPickDialog, _exec

try:
    from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QSize, Signal
    from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics, QKeySequence, QShortcut, QPolygonF, QBrush
    from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
                                   QComboBox, QSpinBox, QDoubleSpinBox, QPushButton, QCheckBox, QScrollBar,
                                   QSplitter, QStackedWidget, QMessageBox, QMenu, QDialog, QDialogButtonBox,
                                   QInputDialog, QSizePolicy, QFrame, QTextEdit, QFileDialog, QScrollArea,
                                   QTableWidget, QTableWidgetItem, QToolButton)
except ImportError:
    from PySide2.QtCore import Qt, QTimer, QRectF, QPointF, QSize, Signal
    from PySide2.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics, QKeySequence, QPolygonF, QBrush
    from PySide2.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
                                   QComboBox, QSpinBox, QDoubleSpinBox, QPushButton, QCheckBox, QScrollBar,
                                   QSplitter, QStackedWidget, QMessageBox, QMenu, QDialog, QDialogButtonBox,
                                   QInputDialog, QSizePolicy, QFrame, QTextEdit, QShortcut, QFileDialog, QScrollArea,
                                   QTableWidget, QTableWidgetItem, QToolButton)

PROPS_START_W = 330          # the sequence editor's properties panel width when it opens
SOUND_CUE_DEFAULT_MS = 8000  # a new sound cue's length
SNAP_CHOICES = [("No snap", 0), ("10 ms", 10), ("50 ms", 50), ("100 ms", 100), ("250 ms", 250),
                ("500 ms", 500), ("1 s", 1000), ("Beat", -1), ("Half beat", -2), ("Bar (4 beats)", -4)]
UNDO_LIMIT = 200
SECTION_COLOURS = {1: QColor(70, 110, 160), 2: QColor(150, 120, 60), 3: QColor(190, 70, 120)}  # by energy level
LEVEL_NAMES = {1: "quiet", 2: "medium", 3: "loud"}


def sectionAt(sections, ms):
    return next((s for s in sections or [] if isinstance(s, dict) and s.get("start_ms", 0) <= ms < s.get("end_ms", 0)), None)


def describeSection(sec):
    """A section's name, times, part and level, for tooltips."""
    a, b = int(sec.get("start_ms", 0)), int(sec.get("end_ms", 0))
    level = int(sec.get("level", 2))
    part = ("Part %s\n" % sec["group"]) if sec.get("group") else ""
    if sec.get("kind"):
        part += "NeewerLux: %s\n" % sec["kind"]
    elif sec.get("ai_label"):
        part += "Section finder: %s\n" % sec["ai_label"]
    return "%s\n%s to %s (%s)\n%sLevel %d (%s)" % (sec.get("label") or "Section", fmtTime(a), fmtTime(b), fmtTime(b - a),
                                                    part, level, LEVEL_NAMES.get(level, ""))


# ============================================================================
# MODEL HELPERS (no Qt): kept separate so they can be tested on their own
# ============================================================================

def newSequence(name="New Sequence"):
    """A blank sequence: 30 s with a soft white base look on every light."""
    return {"format": 1, "name": name, "duration_ms": 30000,
            "cues": [{"at_ms": 0, "target": "*", "state": {"mode": "CCT", "temp": 45, "bri": 50}}]}


def cueKind(cue):
    return "sound" if "sound" in cue else "clip" if "clip" in cue else "state"


def soundName(cue):
    spec = cue.get("sound")
    return spec if isinstance(spec, str) else (spec or {}).get("mode", "")


def rescaleTempo(seq, newBpm):
    """Change a sequence's tempo so its cues stay on the same beats: every time (cue starts,
    lengths, fades, sections, the sequence length) moves and stretches about the first beat,
    and looping clips speed up or slow down to match. Returns the edited copy."""
    seq = copy.deepcopy(seq)
    tempo = seq.get("tempo") or {}
    old = float(tempo.get("bpm") or 0)
    if old <= 0 or newBpm <= 0:
        seq["tempo"] = {"bpm": round(float(newBpm), 2), "offset_ms": int(tempo.get("offset_ms", 0) or 0)}
        return seq
    r = old / float(newBpm)
    off = float(tempo.get("offset_ms", 0) or 0)
    at = lambda t: max(0, int(round(off + (float(t) - off) * r)))
    span = lambda d: max(0, int(round(float(d) * r)))
    for cue in seq.get("cues", []):
        cue["at_ms"] = at(cue.get("at_ms", 0))
        if cue.get("duration_ms"):
            cue["duration_ms"] = max(1, span(cue["duration_ms"]))
        state = cue.get("state")
        if isinstance(state, dict) and state.get("fade_ms"):
            state["fade_ms"] = span(state["fade_ms"])
        clip = cue.get("clip")
        if isinstance(clip, dict) and clip.get("fit") == "loop":
            clip["speed"] = round(max(0.05, min(20.0, float(clip.get("speed", 1)) / r)), 3)
    for sec in seq.get("sections") or []:
        if isinstance(sec, dict):
            for key in ("start_ms", "end_ms"):
                if key in sec:
                    sec[key] = at(sec[key])
    seq["duration_ms"] = max(1, at(seq.get("duration_ms", 1)))
    seq["tempo"] = {"bpm": round(float(newBpm), 2), "offset_ms": int(round(off))}
    return seq


def clipName(cue):
    c = cue.get("clip")
    return c if isinstance(c, str) else (c or {}).get("name", "")


def gridStep(snap, bpm):
    """Snap step in ms for a SNAP_CHOICES value: fixed ms, or a fraction/multiple of a beat."""
    if snap > 0:
        return float(snap)
    if snap < 0 and bpm and bpm > 0:
        beat = 60000.0 / bpm
        return beat / 2 if snap == -2 else beat * (-snap if snap != -2 else 1)
    return 0.0


def snapTime(ms, snap, bpm=0, offset=0):
    step = gridStep(snap, bpm)
    if step <= 0:
        return max(0, int(round(ms)))
    base = offset if snap < 0 else 0
    return max(0, int(round(base + round((ms - base) / step) * step)))


def cueSpans(seq, lightCues):
    """For one light's cues (indices into seq["cues"], any order), the drawn span of each:
    {cueIndex: (start, end, isHoldTail)}. A clip, or a colour cue with a duration, spans its
    duration; a colour cue that holds spans to the next cue on the light (or the end), shown
    as a hold tail."""
    cues = seq["cues"]
    duration = int(seq.get("duration_ms") or 0)
    order = sorted(lightCues, key=lambda i: (int(cues[i].get("at_ms", 0)), i))
    spans = {}
    for pos, i in enumerate(order):
        c = cues[i]
        start = int(c.get("at_ms", 0))
        dur = int(c.get("duration_ms") or 0)
        if cueKind(c) in ("clip", "sound") or dur > 0:
            spans[i] = (start, start + max(1, dur), False)
        else:
            nxt = duration
            for j in order[pos + 1:]:
                if int(cues[j].get("at_ms", 0)) > start:
                    nxt = int(cues[j].get("at_ms", 0))
                    break
            spans[i] = (start, max(start + 1, nxt), True)
    return spans


def cueColour(cue):
    """Colour to draw a cue with: its own colour at a readable brightness, or None for clips."""
    if cueKind(cue) != "state":
        return None
    st = cue.get("state", {})
    cmd = {"mode": st.get("mode", "HSI"), "hue": st.get("hue", 0), "sat": st.get("sat", 100),
           "temp": st.get("temp", 56), "bri": max(60, int(st.get("bri", 100)))}
    return show.commandToRGB(cmd)


def colourAt(changes, t):
    """The render's [t, colour, bri, mode, source] entry in effect at time t, or None."""
    lo, hi, found = 0, len(changes) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if changes[mid][0] <= t:
            found = changes[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    return found


def describeCue(cue):
    if cueKind(cue) == "sound":
        return "Sound: " + soundName(cue)
    if cueKind(cue) == "clip":
        c = cue.get("clip")
        fit = c.get("fit", "stretch") if isinstance(c, dict) else "stretch"
        return clipName(cue) + " (" + fit + ")"
    st = cue.get("state", {})
    if st.get("mode") == "CCT":
        text = "%dK %d%%" % (int(st.get("temp", 56)) * 100, int(st.get("bri", 100)))
    else:
        text = "H%d S%d %d%%" % (int(st.get("hue", 0)), int(st.get("sat", 100)), int(st.get("bri", 100)))
    if st.get("fade_ms"):
        text += ", fade %.1fs" % (int(st["fade_ms"]) / 1000.0)
    return text


def fmtTime(ms, precise=False):
    ms = max(0, int(ms))
    s, rem = divmod(ms, 1000)
    if precise:
        return "%d:%02d.%03d" % (s // 60, s % 60, rem)
    return "%d:%02d" % (s // 60, s % 60)


# ============================================================================
# TIMELINE VIEW
# ============================================================================

class TimelineView(QWidget):
    """Ruler, one track per light and the cue blocks. The editor owns the data; the view
    reads editor.seq and calls back into the editor for every change."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.pxPerSec = 40.0
        self.offsetMs = 0.0
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._hits = []          # [(QRectF, cueIndex, kind)] kind: body, end, fade
        self._drag = None        # dict describing a drag in progress
        self.scrollBar = None    # set by the editor

    # --- geometry --------------------------------------------------------
    def metrics(self):
        fm = QFontMetrics(self.font())
        rowH = max(30, int(fm.height() * 2.3))
        rulerH = max(22, fm.height() + 8) + self.sectionsH(fm)
        labelW = min(220, max(110, max([fm.horizontalAdvance(t["label"]) if hasattr(fm, "horizontalAdvance") else fm.width(t["label"]) for t in self.editor.tracks] + [80]) + 18))
        return fm, rowH, rulerH, labelW

    def sectionsH(self, fm):
        """Height of the song sections row above the time ruler (none without sections)."""
        return fm.height() + 4 if self.editor.seq.get("sections") else 0

    def sizeHint(self):
        fm, rowH, rulerH, labelW = self.metrics()
        return QSize(800, rulerH + rowH * max(1, len(self.editor.tracks)) + 2)

    def minimumSizeHint(self):
        return self.sizeHint()

    def xFor(self, ms):
        labelW = self.metrics()[3]
        return labelW + (ms - self.offsetMs) * self.pxPerSec / 1000.0

    def msFor(self, x):
        labelW = self.metrics()[3]
        return self.offsetMs + (x - labelW) * 1000.0 / self.pxPerSec

    def trackAt(self, y):
        fm, rowH, rulerH, labelW = self.metrics()
        if y < rulerH:
            return -1
        row = int((y - rulerH) // rowH)
        return row if 0 <= row < len(self.editor.tracks) else None

    def visibleMs(self):
        labelW = self.metrics()[3]
        return max(1.0, (self.width() - labelW) * 1000.0 / self.pxPerSec)

    def setZoom(self, pxPerSec, anchorMs=None):
        if anchorMs is None:
            anchorMs = self.offsetMs + self.visibleMs() / 2
        anchorX = self.xFor(anchorMs)
        self.pxPerSec = max(2.0, min(2000.0, pxPerSec))
        labelW = self.metrics()[3]
        self.offsetMs = max(0.0, anchorMs - (anchorX - labelW) * 1000.0 / self.pxPerSec)
        self.syncScrollBar()
        self.update()

    def zoomToFit(self):
        dur = max(1000, int(self.editor.seq.get("duration_ms") or 1000))
        labelW = self.metrics()[3]
        self.pxPerSec = max(2.0, (max(200, self.width()) - labelW - 10) * 1000.0 / dur)
        self.offsetMs = 0.0
        self.syncScrollBar()
        self.update()

    def syncScrollBar(self):
        if self.scrollBar is None:
            return
        dur = int(self.editor.seq.get("duration_ms") or 0)
        vis = int(self.visibleMs())
        self.scrollBar.blockSignals(True)
        self.scrollBar.setRange(0, max(0, dur - vis + 500))
        self.scrollBar.setPageStep(vis)
        self.scrollBar.setSingleStep(max(1, vis // 20))
        self.scrollBar.setValue(int(self.offsetMs))
        self.scrollBar.blockSignals(False)

    def onScroll(self, value):
        self.offsetMs = float(value)
        self.update()

    def resizeEvent(self, event):
        self.syncScrollBar()
        super().resizeEvent(event)

    # --- painting ---------------------------------------------------------
    def paintEvent(self, event):
        ed = self.editor
        seq = ed.seq
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fm, rowH, rulerH, labelW = self.metrics()
        W, H = self.width(), self.height()
        duration = int(seq.get("duration_ms") or 0)
        p.fillRect(self.rect(), QColor(26, 26, 30))
        self._hits = []

        # grid: beats if a tempo is set, else time ticks
        t0, t1 = self.offsetMs, self.offsetMs + self.visibleMs()
        secH = self.sectionsH(fm)
        tickMs = next((s for s in (100, 250, 500, 1000, 2000, 5000, 10000, 15000, 30000, 60000, 120000)
                       if s * self.pxPerSec / 1000.0 >= fm.height() * 4), 300000)
        p.setFont(self.font())
        t = int(t0 // tickMs) * tickMs
        while t <= t1:
            x = self.xFor(t)
            if x >= labelW:
                p.setPen(QColor(48, 48, 56))
                p.drawLine(QPointF(x, rulerH), QPointF(x, H))
                p.setPen(QColor(170, 170, 180))
                p.drawLine(QPointF(x, rulerH - 6), QPointF(x, rulerH))
                p.drawText(QRectF(x + 3, secH, fm.height() * 5, rulerH - secH - 4), Qt.AlignLeft | Qt.AlignVCenter,
                           fmtTime(t, precise=False) if tickMs >= 1000 else ("%.2fs" % (t / 1000.0)))
            t += tickMs
        bpm = ed.bpm()
        if bpm > 0:
            beat = 60000.0 / bpm
            if beat * self.pxPerSec / 1000.0 >= 6:
                k = int((t0 - ed.beatOffset()) // beat)
                bt = ed.beatOffset() + k * beat
                while bt <= t1:
                    x = self.xFor(bt)
                    if x >= labelW:
                        isBar = (k % 4) == 0
                        p.setPen(QPen(QColor(90, 70, 130) if isBar else QColor(55, 45, 75), 1))
                        p.drawLine(QPointF(x, rulerH), QPointF(x, H))
                    k += 1
                    bt += beat

        # song sections (from a song draft): a row above the ruler, coloured by energy level
        for sec in seq.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            a, b = int(sec.get("start_ms", 0)), int(sec.get("end_ms", duration))
            xa, xb = max(labelW, self.xFor(a)), min(W, self.xFor(b))
            if xb <= xa:
                continue
            colour = SECTION_COLOURS.get(int(sec.get("level", 2)), SECTION_COLOURS[2])
            p.fillRect(QRectF(xa, 1, xb - xa - 1, secH - 2), colour)
            if self.xFor(a) >= labelW:
                p.setPen(QPen(colour, 1, Qt.DashLine))
                p.drawLine(QPointF(self.xFor(a), rulerH), QPointF(self.xFor(a), H))
            label = str(sec.get("label", ""))
            if fm.horizontalAdvance(label) + 8 <= xb - xa:  # whole names only; hover shows the rest
                p.setPen(QColor(240, 240, 245))
                p.drawText(QRectF(xa + 4, 0, xb - xa - 8, secH), Qt.AlignLeft | Qt.AlignVCenter, label)

        # past the end of the sequence
        xEnd = self.xFor(duration)
        if xEnd < W:
            p.fillRect(QRectF(max(labelW, xEnd), rulerH, W - max(labelW, xEnd), H - rulerH), QColor(0, 0, 0, 110))

        selected = ed.selection
        for row, track in enumerate(ed.tracks):
            y = rulerH + row * rowH
            p.setPen(QColor(55, 55, 62))
            p.drawLine(QPointF(0, y + rowH - 0.5), QPointF(W, y + rowH - 0.5))
            # result band: what the light really does
            bandH = max(4, rowH // 6)
            changes = ed.renderChanges.get(track.get("id"), [])
            for k, ch in enumerate(changes):
                end = changes[k + 1][0] if k + 1 < len(changes) else ed.renderEnd
                xa, xb = max(labelW, self.xFor(ch[0])), min(W, self.xFor(end))
                if xb > xa and ch[1]:
                    p.fillRect(QRectF(xa, y + rowH - bandH - 1, xb - xa, bandH), QColor(ch[1]))
            # cue blocks
            spans = cueSpans(seq, track["cues"])
            for i, (start, end, holdTail) in spans.items():
                cue = seq["cues"][i]
                xa, xb = self.xFor(start), self.xFor(end)
                if xb < labelW or xa > W:
                    continue
                top, h = y + 3, rowH - bandH - 8
                rgb = cueColour(cue)
                sound = cueKind(cue) == "sound"
                base = QColor(*[int(v) for v in rgb]) if rgb else QColor(35, 120, 120) if sound else QColor(70, 95, 140)
                body = QRectF(max(labelW, xa), top, max(2.0, min(W, xb) - max(labelW, xa)), h)
                if holdTail:
                    # solid head (the fade, or a short marker), faded tail while it holds
                    fade = int(cue.get("state", {}).get("fade_ms") or 0)
                    headEnd = min(xb, max(xa + 8, self.xFor(start + fade)))
                    tail = QColor(base)
                    tail.setAlpha(70)
                    p.fillRect(QRectF(max(labelW, xa), top, max(0.0, min(W, xb) - max(labelW, xa)), h), tail)
                    head = QRectF(max(labelW, xa), top, max(2.0, min(W, headEnd) - max(labelW, xa)), h)
                    p.fillRect(head, base)
                else:
                    p.fillRect(body, base)
                    if sound:  # follows live sound: hatched (teal, like sound-driven lights on the Stage)
                        p.fillRect(body, QBrush(QColor(255, 255, 255, 60), Qt.BDiagPattern))
                    fade = int(cue.get("state", {}).get("fade_ms") or 0) if cueKind(cue) == "state" else 0
                if fade and cueKind(cue) == "state":
                    xf = self.xFor(start + fade)
                    if xf > labelW:
                        tri = QPolygonF([QPointF(max(labelW, xa), top + h), QPointF(min(W, xf), top), QPointF(max(labelW, xa), top)])
                        p.setPen(Qt.NoPen)
                        p.setBrush(QColor(0, 0, 0, 70))
                        p.drawPolygon(tri)
                isSel = i in selected
                shared = len(ed.cueLights.get(i, [])) > 1
                pen = QPen(QColor(255, 255, 255) if isSel else QColor(0, 0, 0, 160), 2 if isSel else 1)
                if shared and not isSel:
                    pen.setStyle(Qt.DashLine)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawRect(body if not holdTail else QRectF(max(labelW, xa), top, max(2.0, min(W, xb) - max(labelW, xa)), h))
                # text
                lum = 0.3 * base.red() + 0.59 * base.green() + 0.11 * base.blue()
                p.setPen(QColor(10, 10, 10) if (lum > 140 and not holdTail) else QColor(235, 235, 235))
                label = cue.get("label") or describeCue(cue)
                textRect = QRectF(max(labelW, xa) + 4, top, max(0.0, min(W, xb) - max(labelW, xa) - 8), h)
                if textRect.width() > fm.averageCharWidth() * 3:
                    p.drawText(textRect, Qt.AlignLeft | Qt.AlignVCenter, fm.elidedText(label, Qt.ElideRight, int(textRect.width())))
                # hit areas (end handle only where the span is a real duration). A holding colour
                # cue's tail is its own area: clicking it selects the cue, double-clicking adds a
                # new cue there, since holds cover most of a track.
                if holdTail:
                    xh = min(xb, max(xa + 8, self.xFor(start + int(cue.get("state", {}).get("fade_ms") or 0))))
                    self._hits.append((QRectF(xa, top, max(4.0, xh - xa), h), i, "body", row))
                    self._hits.append((QRectF(xh, top, max(0.0, xb - xh), h), i, "tail", row))
                else:
                    self._hits.append((QRectF(xa, top, max(4.0, xb - xa), h), i, "body", row))
                if not holdTail:
                    self._hits.append((QRectF(xb - 5, top, 10, h), i, "end", row))
                if cueKind(cue) == "state":
                    xf = self.xFor(start + int(cue.get("state", {}).get("fade_ms") or 0))
                    self._hits.append((QRectF(xf - 4, top, 8, h / 3.0), i, "fade", row))

            # track label (drawn last so blocks scroll under it)
            p.fillRect(QRectF(0, y, labelW, rowH), QColor(34, 34, 40))
            p.setPen(QColor(225, 225, 230) if track.get("index") is not None else QColor(220, 150, 80))
            p.drawText(QRectF(8, y, labelW - 12, rowH * 0.6), Qt.AlignLeft | Qt.AlignBottom,
                       fm.elidedText(track["label"], Qt.ElideRight, labelW - 14))
            p.setPen(QColor(140, 140, 150))
            small = QFont(self.font())
            if small.pointSizeF() > 0:
                small.setPointSizeF(max(7.0, small.pointSizeF() - 1.5))
            p.setFont(small)
            p.drawText(QRectF(8, y + rowH * 0.58, labelW - 12, rowH * 0.42), Qt.AlignLeft | Qt.AlignTop, track.get("sub", ""))
            p.setFont(self.font())

        # ruler background and label corner
        p.fillRect(QRectF(0, 0, labelW, rulerH), QColor(34, 34, 40))
        p.setPen(QColor(150, 150, 160))
        if secH:
            p.drawText(QRectF(8, 0, labelW - 12, secH), Qt.AlignLeft | Qt.AlignVCenter, "Sections")
        p.drawText(QRectF(8, secH, labelW - 12, rulerH - secH), Qt.AlignLeft | Qt.AlignVCenter, fmtTime(duration, True))
        # playhead
        xp = self.xFor(ed.playhead)
        if labelW <= xp <= W:
            p.setPen(QPen(QColor(255, 80, 80), 2))
            p.drawLine(QPointF(xp, 0), QPointF(xp, H))
            p.setBrush(QColor(255, 80, 80))
            p.drawPolygon(QPolygonF([QPointF(xp - 6, 0), QPointF(xp + 6, 0), QPointF(xp, 8)]))
        d = self._drag
        if d is not None and d["kind"] == "marquee":
            p.setPen(QPen(QColor(120, 170, 255), 1, Qt.DashLine))
            p.setBrush(QColor(120, 170, 255, 40))
            p.drawRect(QRectF(d["start"], d["end"]).normalized())

    # --- interaction ------------------------------------------------------
    def hitAt(self, pos):
        """(cueIndex, kind, row) under pos: handles first, then cue heads, then hold tails."""
        best, tail = None, None
        for rect, i, kind, row in reversed(self._hits):
            if rect.contains(pos):
                if kind in ("end", "fade"):
                    return i, kind, row
                if kind == "body" and best is None:
                    best = (i, kind, row)
                elif kind == "tail" and tail is None:
                    tail = (i, kind, row)
        return best or tail

    def _pos(self, event):
        return event.position() if hasattr(event, "position") else QPointF(event.pos())

    def mousePressEvent(self, event):
        self.setFocus()
        pos = self._pos(event)
        ed = self.editor
        labelW = self.metrics()[3]
        if event.button() == Qt.RightButton:
            self._contextMenu(event, pos)
            return
        if event.button() != Qt.LeftButton:
            return
        row = self.trackAt(pos.y())
        if row == -1 and pos.x() >= labelW:  # ruler: move the playhead, drag to scrub
            ed.setPlayhead(self.msFor(pos.x()))
            self._drag = {"kind": "scrub"}
            return
        hit = self.hitAt(pos)
        mods = event.modifiers()
        if hit is None:
            keep = bool(mods & (Qt.ControlModifier | Qt.ShiftModifier))
            if not keep:
                ed.setSelection([])
            if pos.x() >= labelW and row is not None:
                # a click moves the playhead; a drag draws a box that selects the cues it touches
                self._drag = {"kind": "marquee", "start": pos, "end": pos, "base": list(ed.selection) if keep else [],
                              "at": self.msFor(pos.x())}
            return
        i, kind, row = hit
        if mods & (Qt.ControlModifier | Qt.ShiftModifier):
            sel = list(ed.selection)
            if i in sel:
                sel.remove(i)
            else:
                sel.append(i)
            ed.setSelection(sel)
        elif i not in ed.selection:
            ed.setSelection([i])
        cues = ed.seq["cues"]
        self._drag = {"kind": "body" if kind == "tail" else kind, "cue": i, "x0": pos.x(), "moved": False,
                      "orig": {j: (int(cues[j].get("at_ms", 0)), int(cues[j].get("duration_ms") or 0),
                                   int(cues[j].get("state", {}).get("fade_ms") or 0) if cueKind(cues[j]) == "state" else 0)
                               for j in ed.selection}}

    def mouseMoveEvent(self, event):
        pos = self._pos(event)
        ed = self.editor
        d = self._drag
        if d is None:
            fm = QFontMetrics(self.font())
            if pos.y() < self.sectionsH(fm) and pos.x() >= self.metrics()[3]:
                sec = sectionAt(ed.seq.get("sections"), self.msFor(pos.x()))
                self.unsetCursor()
                self.setToolTip(describeSection(sec) if sec else "")
                return
            hit = self.hitAt(pos)
            if hit and hit[1] == "end":
                self.setCursor(Qt.SizeHorCursor)
            elif hit and hit[1] == "fade":
                self.setCursor(Qt.SplitHCursor)
            elif hit:
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.unsetCursor()
            if hit:
                cue = ed.seq["cues"][hit[0]]
                self.setToolTip("%s  %s\n%s" % (fmtTime(cue.get("at_ms", 0), True), cue.get("target", "*"), describeCue(cue)))
            else:
                self.setToolTip("")
            return
        if d["kind"] == "scrub":
            ed.setPlayhead(self.msFor(pos.x()))
            return
        if d["kind"] == "marquee":
            d["end"] = pos
            box = QRectF(d["start"], pos).normalized()
            touched = [i for rect, i, kind, row in self._hits if kind in ("body", "tail") and rect.intersects(box)]
            ed.setSelection(d["base"] + [i for i in dict.fromkeys(touched) if i not in d["base"]])
            self.update()
            return
        dms = (pos.x() - d["x0"]) * 1000.0 / self.pxPerSec
        if not d["moved"]:
            if abs(pos.x() - d["x0"]) < 3:
                return
            ed.pushUndo()
            d["moved"] = True
        cues = ed.seq["cues"]
        anchorAt, anchorDur, anchorFade = d["orig"][d["cue"]]
        if d["kind"] == "body":
            newAt = ed.snap(anchorAt + dms)
            shift = newAt - anchorAt
            shift = max(shift, -min(o[0] for o in d["orig"].values()))
            for j, (at, dur, fade) in d["orig"].items():
                cues[j]["at_ms"] = at + shift
        elif d["kind"] == "end":
            newEnd = ed.snap(anchorAt + anchorDur + dms)
            newDur = max(10, newEnd - anchorAt)
            cues[d["cue"]]["duration_ms"] = int(newDur)
        elif d["kind"] == "fade":
            newFade = max(0, int(ed.snap(anchorAt + anchorFade + dms) - anchorAt))
            cues[d["cue"]].setdefault("state", {})["fade_ms"] = newFade
        ed.changed(live=True)

    def mouseReleaseEvent(self, event):
        d = self._drag
        if d is not None and d.get("moved"):
            self.editor.changed()
        if d is not None and d["kind"] == "marquee":
            if abs(d["end"].x() - d["start"].x()) < 3 and abs(d["end"].y() - d["start"].y()) < 3:
                self.editor.setPlayhead(d["at"])  # just a click
            self.update()
        self._drag = None

    def mouseDoubleClickEvent(self, event):
        pos = self._pos(event)
        hit = self.hitAt(pos)
        if hit is not None and hit[1] != "tail":
            self.editor.focusProperties()
            return
        row = self.trackAt(pos.y())
        if row is not None and row >= 0 and pos.x() >= self.metrics()[3]:
            self.editor.addCue("state", row, self.editor.snap(self.msFor(pos.x())))

    def wheelEvent(self, event):
        delta = event.angleDelta()
        if event.modifiers() & Qt.ControlModifier:
            pos = self._pos(event)
            factor = 1.25 if delta.y() > 0 else 0.8
            self.setZoom(self.pxPerSec * factor, self.msFor(pos.x()))
        else:
            step = delta.x() if abs(delta.x()) > abs(delta.y()) else delta.y()
            self.offsetMs = max(0.0, self.offsetMs - step / 120.0 * self.visibleMs() / 8)
            self.syncScrollBar()
            self.update()
        event.accept()

    def _contextMenu(self, event, pos):
        ed = self.editor
        menu = QMenu(self)
        hit = self.hitAt(pos)
        row = self.trackAt(pos.y())
        at = ed.snap(self.msFor(pos.x()))
        actions = {}
        if hit is not None:
            if hit[0] not in ed.selection:
                ed.setSelection([hit[0]])
            actions[menu.addAction("Duplicate")] = ed.duplicateSelection
            actions[menu.addAction("Copy")] = ed.copySelection
            actions[menu.addAction("Delete")] = ed.deleteSelection
            menu.addSeparator()
        if row is not None and row >= 0:
            actions[menu.addAction("Add colour cue here")] = lambda: ed.addCue("state", row, at)
            actions[menu.addAction("Add clip cue here")] = lambda: ed.addCue("clip", row, at)
            actions[menu.addAction("Add sound cue here")] = lambda: ed.addCue("sound", row, at)
            if ed.clipboard:
                actions[menu.addAction("Paste here")] = lambda: ed.paste(at)
        if not actions:
            return
        gp = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
        try:
            chosen = menu.exec(gp)
        except AttributeError:
            chosen = menu.exec_(gp)
        if chosen in actions:
            actions[chosen]()


# ============================================================================
# SEQUENCE SETTINGS DIALOG
# ============================================================================

class SequenceSettingsDialog(QDialog):
    def __init__(self, seq, presetCount, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sequence settings")
        form = QFormLayout(self)
        self.fps = SpinBoxWithButtons(); self.fps.setRange(0, 30); self.fps.setSpecialValueText("Global default")
        self.fps.setValue(int(seq.get("fps", 0) or 0))
        self.fps.setToolTip("Updates per second during fades and clips")
        form.addRow("Frame rate", self.fps)
        self.end = QComboBox()
        self.end.addItem("Return to the state before the sequence", "revert")
        self.end.addItem("Hold the last frame", "hold")
        for n in range(1, max(1, presetCount) + 1):
            self.end.addItem("Recall preset " + str(n), "preset:" + str(n))
        idx = self.end.findData(seq.get("end", "revert"))
        self.end.setCurrentIndex(max(0, idx))
        form.addRow("At the end", self.end)
        self.pause = QComboBox()
        self.pause.addItem("Return lights to their earlier state", "revert")
        self.pause.addItem("Freeze the current frame", "freeze")
        self.pause.setCurrentIndex(max(0, self.pause.findData(seq.get("pause_mode", "revert"))))
        form.addRow("While paused", self.pause)
        self.interrupt = QComboBox()
        self.interrupt.addItem("Keep running underneath (stay in sync)", "continue")
        self.interrupt.addItem("Pause until the interruption ends", "pause")
        self.interrupt.setCurrentIndex(max(0, self.interrupt.findData(seq.get("on_interrupt", "continue"))))
        form.addRow("During effects", self.interrupt)
        self.fadeIn = SpinBoxWithButtons(); self.fadeIn.setRange(-1, 10000); self.fadeIn.setSingleStep(100); self.fadeIn.setSuffix(" ms")
        self.fadeIn.setSpecialValueText("Global"); self.fadeIn.setValue(int(seq.get("fade_in_ms", -1)))
        self.fadeIn.setToolTip("Fade into the sequence when it starts. Global = Global Preferences, Fade in.")
        form.addRow("Fade in", self.fadeIn)
        self.fadeOut = SpinBoxWithButtons(); self.fadeOut.setRange(-1, 10000); self.fadeOut.setSingleStep(100); self.fadeOut.setSuffix(" ms")
        self.fadeOut.setSpecialValueText("Global"); self.fadeOut.setValue(int(seq.get("handback_fade_ms", -1)))
        self.fadeOut.setToolTip("Fade back when the sequence ends, stops or pauses with revert. Global = Global Preferences, Fade back.")
        form.addRow("Fade back", self.fadeOut)
        self.artist = QLineEdit(str(seq.get("artist", "")))
        form.addRow("Artist", self.artist)
        self.song = QLineEdit(str(seq.get("song", "")))
        form.addRow("Song", self.song)
        self.description = QLineEdit(str(seq.get("description", "")))
        form.addRow("Description", self.description)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def apply(self, seq):
        if self.fps.value():
            seq["fps"] = self.fps.value()
        else:
            seq.pop("fps", None)
        for key, widget in (("end", self.end), ("pause_mode", self.pause), ("on_interrupt", self.interrupt)):
            value = widget.currentData()
            default = {"end": "revert", "pause_mode": "revert", "on_interrupt": "continue"}[key]
            if value == default:
                seq.pop(key, None)
            else:
                seq[key] = value
        for key, spin in (("fade_in_ms", self.fadeIn), ("handback_fade_ms", self.fadeOut)):
            if spin.value() < 0:
                seq.pop(key, None)
            else:
                seq[key] = spin.value()
        for key, widget in (("artist", self.artist), ("song", self.song), ("description", self.description)):
            text = widget.text().strip()
            if text:
                seq[key] = text
            else:
                seq.pop(key, None)


# ============================================================================
# DRAFT FROM A SONG
# ============================================================================

class SongView(QWidget):
    """The song at a glance: waveform, energy curve, section bands (by level) and the beat grid."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.analysis = None
        self.bpm, self.offsetMs = 0.0, 0
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):
        a = self.analysis
        x = event.position().x() if hasattr(event, "position") else event.x()
        sec = sectionAt(a["sections"], x * a["duration_ms"] / max(1, self.width())) if a else None
        self.setToolTip(describeSection(sec) if sec else "")

    def setAnalysis(self, analysis, bpm=None, offsetMs=None):
        self.analysis = analysis
        if analysis is not None:
            self.bpm = float(bpm if bpm else analysis["bpm"])
            self.offsetMs = int(analysis["bars"][0] if offsetMs is None and analysis.get("bars") else (offsetMs or 0))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        p.fillRect(self.rect(), QColor(26, 26, 30))
        a = self.analysis
        if not a:
            p.setPen(QColor(150, 150, 160))
            p.drawText(self.rect(), Qt.AlignCenter, "Choose a song file to analyse")
            return
        dur = max(1, a["duration_ms"])
        xFor = lambda ms: ms * W / dur
        bandH = 16
        fm = QFontMetrics(self.font())
        for sec in a["sections"]:
            colour = SECTION_COLOURS.get(sec.get("level", 2), SECTION_COLOURS[2])
            xa, xb = xFor(sec["start_ms"]), xFor(sec["end_ms"])
            p.fillRect(QRectF(xa, 0, xb - xa - 1, bandH), colour)
            label = sec.get("label", "")
            if fm.horizontalAdvance(label) + 6 <= xb - xa:  # whole names only; hover shows the rest
                p.setPen(QColor(240, 240, 245))
                p.drawText(QRectF(xa + 3, 0, xb - xa - 6, bandH), Qt.AlignLeft | Qt.AlignVCenter, label)
        top, mid = bandH + 4, bandH + 4 + (H - bandH - 4) / 2
        half = (H - bandH - 8) / 2
        wave = a["waveform"]
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(90, 90, 105))
        for i, v in enumerate(wave):
            x = i * W / len(wave)
            p.drawRect(QRectF(x, mid - v * half, max(1.0, W / len(wave)), 2 * v * half))
        energy, step = a["energy"], a.get("energy_step_ms", 250)
        if energy:
            pts = QPolygonF([QPointF(xFor(i * step), H - 4 - v * (H - top - 8)) for i, v in enumerate(energy)])
            p.setPen(QPen(QColor(230, 180, 70), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawPolyline(pts)
        if self.bpm > 0:
            period = 60000.0 / self.bpm
            k = -int(self.offsetMs // period)
            t = self.offsetMs + k * period
            while t <= dur:
                if t >= 0:
                    bar = (k % 4) == 0
                    p.setPen(QPen(QColor(140, 110, 200) if bar else QColor(70, 60, 95), 1))
                    if bar or period * W / dur >= 4:
                        p.drawLine(QPointF(xFor(t), top), QPointF(xFor(t), top + (10 if bar else 5)))
                k += 1
                t += period


class SongDraftDialog(QDialog):
    """Draft a sequence from a song file: analyse it (tempo, beats, sections), adjust the tempo
    if the analysis is off, pick a style and open the draft in the timeline editor.
    host provides analyze(path, bpm, offsetMs) -> analysis dict (success, errors),
    draft(analysis, style, name, bpm, offsetMs) -> {"success", "sequence", "errors", "flashes"}
    and openDraft(sequence)."""

    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self.analysis = None
        self._job = None
        self.setWindowTitle("Draft a sequence from a song")
        self.resize(900, 520)
        lay = QVBoxLayout(self)
        fileRow = QHBoxLayout()
        self.fileLabel = QLabel("No song chosen")
        self.fileLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.chooseButton = QPushButton("Choose song...")
        self.chooseButton.setToolTip("WAV, FLAC, MP3, OGG or AIFF")
        fileRow.addWidget(QLabel("Song:"))
        fileRow.addWidget(self.fileLabel, 1)
        fileRow.addWidget(self.chooseButton)
        lay.addLayout(fileRow)
        self.view = SongView(self)
        lay.addWidget(self.view, 1)
        self.infoLabel = QLabel("")
        self.infoLabel.setWordWrap(True)
        lay.addWidget(self.infoLabel)
        tempoRow = QHBoxLayout()
        tempoRow.addWidget(QLabel("Tempo:"))
        self.bpmSpin = DoubleSpinBoxWithButtons()
        self.bpmSpin.setRange(30, 300)
        self.bpmSpin.setDecimals(2)
        self.bpmSpin.setSuffix(" BPM")
        tempoRow.addWidget(self.bpmSpin)
        self.halfButton = QPushButton("x 1/2")
        self.doubleButton = QPushButton("x 2")
        self.halfButton.setToolTip("The analysis counted twice as many beats as there are")
        self.doubleButton.setToolTip("The analysis counted half the beats")
        tempoRow.addWidget(self.halfButton)
        tempoRow.addWidget(self.doubleButton)
        tempoRow.addWidget(QLabel("First bar at:"))
        self.offsetSpin = SpinBoxWithButtons()
        self.offsetSpin.setRange(0, 600000)
        self.offsetSpin.setSuffix(" ms")
        self.offsetSpin.setToolTip("When a bar's first beat falls; sections move to the nearest bar line")
        tempoRow.addWidget(self.offsetSpin)
        tempoRow.addStretch(1)
        lay.addLayout(tempoRow)
        styleRow = QHBoxLayout()
        styleRow.addWidget(QLabel("Style:"))
        self.styleCombo = QComboBox()
        styleRow.addWidget(self.styleCombo)
        self.stylesButton = QPushButton("Styles...")
        self.stylesButton.setToolTip("Edit, copy or delete draft styles")
        styleRow.addWidget(self.stylesButton)
        styleRow.addWidget(QLabel("or by genre:"))
        self.genreEdit = QLineEdit()
        self.genreEdit.setPlaceholderText("e.g. thrash metal, deep house")
        self.genreEdit.setToolTip("Genres, most important first; picks the style whose genres fit best")
        styleRow.addWidget(self.genreEdit, 1)
        self.genreButton = QPushButton("Pick")
        styleRow.addWidget(self.genreButton)
        lay.addLayout(styleRow)
        self.styleNote = QLabel("")
        self.styleNote.setWordWrap(True)
        lay.addWidget(self.styleNote)
        nameRow = QHBoxLayout()
        nameRow.addWidget(QLabel("Name:"))
        self.nameEdit = QLineEdit()
        nameRow.addWidget(self.nameEdit, 1)
        # filled from the song's tags or an "Artist - Title" file name; playing a show by artist and song matches these
        nameRow.addWidget(QLabel("Artist:"))
        self.artistEdit = QLineEdit()
        nameRow.addWidget(self.artistEdit, 1)
        nameRow.addWidget(QLabel("Song:"))
        self.songEdit = QLineEdit()
        nameRow.addWidget(self.songEdit, 1)
        lay.addLayout(nameRow)
        note = QLabel("The draft drives the fill, rim, background and practical lights, never the key, and stays under the "
                      "flash limit. It opens unsaved in the timeline editor for you to change and save.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #888;")
        lay.addWidget(note)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.draftButton = QPushButton("Create draft")
        self.draftButton.setEnabled(False)
        closeButton = QPushButton("Close")
        buttons.addWidget(self.draftButton)
        buttons.addWidget(closeButton)
        lay.addLayout(buttons)

        self.chooseButton.clicked.connect(self.choose)
        self.halfButton.clicked.connect(lambda: self.bpmSpin.setValue(self.bpmSpin.value() / 2))
        self.doubleButton.clicked.connect(lambda: self.bpmSpin.setValue(self.bpmSpin.value() * 2))
        self.bpmSpin.valueChanged.connect(self._gridEdited)
        self.offsetSpin.valueChanged.connect(self._gridEdited)
        self.styleCombo.currentTextChanged.connect(self._styleNote)
        self.stylesButton.clicked.connect(self.editStyles)
        self.genreButton.clicked.connect(self.pickByGenre)
        self.genreEdit.returnPressed.connect(self.pickByGenre)
        self.styleEditor = None
        self.loadStyles("Concert")
        self.draftButton.clicked.connect(self.createDraft)
        closeButton.clicked.connect(self.reject)
        self.pollTimer = QTimer(self)
        self.pollTimer.timeout.connect(self._poll)

    def loadStyles(self, current=None):
        current = current or self.styleCombo.currentText()
        self._styles = {st["name"]: st for st in self.host.styles()}
        self.styleCombo.blockSignals(True)
        self.styleCombo.clear()
        self.styleCombo.addItems(list(self._styles))
        if current in self._styles:
            self.styleCombo.setCurrentText(current)
        self.styleCombo.blockSignals(False)
        self._styleNote(self.styleCombo.currentText())

    def _styleNote(self, name):
        st = self._styles.get(name) or {}
        note = st.get("description", "")
        if st.get("genres"):
            note += " Genres: " + ", ".join(st["genres"]) + "."
        if st.get("errors"):
            note += " Can't be used: " + "; ".join(st["errors"])
        self.styleNote.setText(note.strip())

    def pickByGenre(self):
        found = self.host.styleFor(self.genreEdit.text())
        if found:
            self.styleCombo.setCurrentText(found)
        else:
            self.styleNote.setText("No style lists those genres; add them to a style's genres in Styles...")

    def editStyles(self):
        if self.styleEditor is None:
            self.styleEditor = DraftStyleDialog(self.host, self.styleCombo.currentText(), self)
            self.styleEditor.saved.connect(lambda name: self.loadStyles(name))
        else:
            self.styleEditor.reload(self.styleCombo.currentText())
        self.styleEditor.show()
        self.styleEditor.raise_()
        return self.styleEditor

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a song", "", "Songs (*.wav *.flac *.mp3 *.ogg *.aiff *.aif)")
        if path:
            self.analyze(path)

    def analyze(self, path):
        """Analyse on a thread of its own (a few seconds for a long song); the window stays live."""
        import threading
        import os
        self.fileLabel.setText(path)
        self.infoLabel.setText("Analysing " + os.path.basename(path) + "...")
        self.draftButton.setEnabled(False)
        self.chooseButton.setEnabled(False)
        box = {}
        def run():
            box["result"] = self.host.analyze(path, None, None)
        self._job = (threading.Thread(target=run, daemon=True), box)
        self._job[0].start()
        self.pollTimer.start(100)

    def _poll(self):
        thread, box = self._job
        if thread.is_alive():
            return
        self.pollTimer.stop()
        self.chooseButton.setEnabled(True)
        self.setAnalysis(box.get("result") or {"success": False, "errors": ["analysis failed"]})

    def setAnalysis(self, result):
        if not result.get("success"):
            self.analysis = None
            self.view.setAnalysis(None)
            self.infoLabel.setText("Couldn't analyse it: " + "; ".join(result.get("errors", [])))
            return
        self.analysis = result
        for spin, value in ((self.bpmSpin, result["bpm"]), (self.offsetSpin, result["bars"][0] if result.get("bars") else result["offset_ms"])):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self.view.setAnalysis(result)
        if not self.nameEdit.text().strip():
            self.nameEdit.setText(result.get("song", ""))
        # a new song replaces what the last one filled in
        self.artistEdit.setText(result.get("artist", ""))
        self.songEdit.setText(result.get("title", ""))
        conf = result.get("confidence")
        self.infoLabel.setText("%s long, %g BPM%s, %d sections. If the beat ticks don't match the song, correct the tempo "
                               "(x 1/2 or x 2 for the commonest mistake) and when the first bar falls." % (
                                   fmtTime(result["duration_ms"]), result["bpm"],
                                   "" if conf is None else " (%d%% of the song agrees)" % round(conf * 100), len(result["sections"]))
                               + (" Sections from the section finder command." if result.get("sections_from") == "command" else "")
                               + "".join(" " + w + "." for w in result.get("warnings", [])))
        self.draftButton.setEnabled(True)

    def _gridEdited(self, *args):
        if self.analysis is not None:
            self.view.setAnalysis(self.analysis, self.bpmSpin.value(), self.offsetSpin.value())

    def _gridChanged(self):
        a = self.analysis
        first = a["bars"][0] if a.get("bars") else a["offset_ms"]
        return abs(self.bpmSpin.value() - a["bpm"]) > 0.005 or self.offsetSpin.value() != first

    def createDraft(self):
        if self.analysis is None:
            return None
        changed = self._gridChanged()
        result = self.host.draft(self.analysis, self.styleCombo.currentText(), self.nameEdit.text().strip() or self.analysis.get("song") or "Draft",
                                 self.bpmSpin.value() if changed else None, self.offsetSpin.value() if changed else None,
                                 self.artistEdit.text().strip(), self.songEdit.text().strip())
        if not result.get("success"):
            self.infoLabel.setText("Couldn't draft it: " + "; ".join(result.get("errors", [])))
            return None
        return self.host.openDraft(result["sequence"])


class DraftStyleDialog(QDialog):
    """Edit draft styles (the files in light_prefs/draft_styles): palette, intensity, whether
    animations and sound modes may be used, and per section kind the behaviours and the pools
    of animations and sound modes, by tag. host provides styles(), styleChoices(),
    saveStyle(data, original, overwrite), deleteStyle(name) and poolCounts(pool, kind).
    saved(name) is emitted after a save, rename or delete."""

    saved = Signal(str)
    OWN = "Own colours"

    def __init__(self, host, current=None, parent=None):
        super().__init__(parent)
        self.host = host
        self.setWindowTitle("Draft styles")
        self.resize(940, 600)
        lay = QVBoxLayout(self)
        top = FlowLayout()
        top.addWidget(QLabel("Style:"))
        self.styleCombo = QComboBox()
        self.styleCombo.setMinimumContentsLength(14)
        top.addWidget(self.styleCombo)
        self.saveButton = QPushButton("Save")
        self.saveAsButton = QPushButton("Save as...")
        self.deleteButton = QPushButton("Delete")
        self.revertButton = QPushButton("Revert")
        for b in (self.saveButton, self.saveAsButton, self.deleteButton, self.revertButton):
            top.addWidget(b)
        lay.addLayout(top)
        form = QFormLayout()
        self.descEdit = QLineEdit()
        form.addRow("Description:", self.descEdit)
        self.genresEdit = QLineEdit()
        self.genresEdit.setToolTip("Genres this style suits, separated by commas; Pick by genre and the HTTP style_for action match them")
        form.addRow("Genres:", self.genresEdit)
        palRow = QHBoxLayout()
        self.paletteCombo = QComboBox()
        palRow.addWidget(self.paletteCombo)
        self.coloursEdit = QLineEdit()
        self.coloursEdit.setToolTip("Hue/saturation pairs (35/90, 215/85) or whites in Kelvin (2700K, 5600K), separated by commas")
        palRow.addWidget(self.coloursEdit, 1)
        self.addColourButton = QPushButton("Add colour...")
        self.addColourButton.setToolTip("Pick a colour on the wheel and add it to the style's own colours")
        self.addColourButton.clicked.connect(self.addColour)
        palRow.addWidget(self.addColourButton)
        form.addRow("Palette:", palRow)
        optRow = QHBoxLayout()
        self.intensityCombo = QComboBox()
        self.intensityCombo.addItems([i.capitalize() for i in show.DRAFT_INTENSITIES])
        self.intensityCombo.setToolTip("How bright the colour lights get: low, medium or high")
        optRow.addWidget(self.intensityCombo)
        self.animCheck = QCheckBox("Use animations")
        self.soundCheck = QCheckBox("Use sound modes")
        optRow.addWidget(self.animCheck)
        optRow.addWidget(self.soundCheck)
        optRow.addStretch(1)
        form.addRow("Intensity:", optRow)
        lay.addLayout(form)
        self.table = QTableWidget(len(show.DRAFT_SECTIONS), 5)
        self.table.setHorizontalHeaderLabels(["Section", "Behaviour", "Animations", "Sound modes", "Matches"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        adjustableColumns(self.table)
        self.behaviourButtons, self.animEdits, self.soundEdits, self._order = {}, {}, {}, {}
        choices = host.styleChoices()
        self._names = {"animations": choices["animations"], "sound_modes": choices["sound_modes"]}
        tagTip = "Tags each item must have, -tags it mustn't, or item names, separated by commas. Tags in use: "
        for row, kind in enumerate(show.DRAFT_SECTIONS):
            item = QTableWidgetItem(kind)
            item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 0, item)
            button = QToolButton()
            button.setPopupMode(QToolButton.InstantPopup)
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            menu = QMenu(button)
            for beh in show.DRAFT_BEHAVIOURS:
                act = menu.addAction(beh)
                act.setCheckable(True)
                act.setToolTip(show.DRAFT_BEHAVIOUR_NOTES[beh])
                act.toggled.connect(lambda on, k=kind: self._behavioursChanged(k))
            menu.setToolTipsVisible(True)
            button.setMenu(menu)
            self.behaviourButtons[kind] = button
            self.table.setCellWidget(row, 1, button)
            anim, snd = QLineEdit(), QLineEdit()
            anim.setToolTip(tagTip + ", ".join(choices["animation_tags"]))
            snd.setToolTip(tagTip + ", ".join(choices["sound_mode_tags"]))
            anim.textChanged.connect(lambda _t, k=kind: self._counts(k))
            snd.textChanged.connect(lambda _t, k=kind: self._counts(k))
            self.animEdits[kind], self.soundEdits[kind] = anim, snd
            self.table.setCellWidget(row, 2, anim)
            self.table.setCellWidget(row, 3, snd)
            matches = QTableWidgetItem("")
            matches.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 4, matches)
        fm = self.table.fontMetrics()
        self.table.setColumnWidth(0, fm.horizontalAdvance("Breakdown") + 24)
        self.table.setColumnWidth(2, 170)
        self.table.setColumnWidth(3, 170)
        lay.addWidget(self.table, 1)
        self.notes = QLabel("Behaviours: " + " ".join("%s: %s" % (b, show.DRAFT_BEHAVIOUR_NOTES[b]) for b in show.DRAFT_BEHAVIOURS))
        self.notes.setWordWrap(True)
        self.notes.setStyleSheet("color: #888;")
        lay.addWidget(self.notes)
        bottom = QHBoxLayout()
        self.status = QLabel("")
        self.status.setWordWrap(True)
        bottom.addWidget(self.status, 1)
        closeButton = QPushButton("Close")
        bottom.addWidget(closeButton)
        lay.addLayout(bottom)

        self.paletteCombo.currentTextChanged.connect(self._ownShown)
        for check in (self.animCheck, self.soundCheck):
            check.toggled.connect(lambda _on: [self._counts(k) for k in show.DRAFT_SECTIONS])
        self.styleCombo.currentTextChanged.connect(self.load)
        self.saveButton.clicked.connect(self.save)
        self.saveAsButton.clicked.connect(self.saveAs)
        self.deleteButton.clicked.connect(self.delete)
        self.revertButton.clicked.connect(lambda: self.load(self.styleCombo.currentText()))
        closeButton.clicked.connect(self.close)
        self.reload(current)

    def reload(self, current=None):
        self._styles = {st["name"]: st for st in self.host.styles()}
        self.paletteCombo.blockSignals(True)
        self.paletteCombo.clear()
        self.paletteCombo.addItems(self.host.styleChoices()["palettes"] + [self.OWN])
        self.paletteCombo.blockSignals(False)
        self.styleCombo.blockSignals(True)
        self.styleCombo.clear()
        self.styleCombo.addItems(list(self._styles))
        if current in self._styles:
            self.styleCombo.setCurrentText(current)
        self.styleCombo.blockSignals(False)
        self.load(self.styleCombo.currentText())

    @staticmethod
    def coloursText(colours):
        return ", ".join("%dK" % c["temp"] if "temp" in c else "%d/%d" % (c["hue"], c["sat"]) for c in colours)

    @staticmethod
    def coloursFromText(text):
        out = []
        for word in str(text).split(","):
            word = word.strip().lower()
            if not word:
                continue
            try:
                if word.endswith("k"):
                    out.append({"temp": int(float(word[:-1]))})
                else:
                    hue, _, sat = word.partition("/")
                    out.append({"hue": int(float(hue)), "sat": int(float(sat or 100))})
            except ValueError:
                return None
        return out

    def load(self, name):
        st = self._styles.get(name)
        if st is None:
            return
        self.descEdit.setText(st.get("description", ""))
        self.genresEdit.setText(", ".join(st.get("genres", [])))
        palette = st.get("palette")
        if isinstance(palette, str):
            self.paletteCombo.setCurrentText(palette)
            self.coloursEdit.setText("")
        else:
            self.paletteCombo.setCurrentText(self.OWN)
            self.coloursEdit.setText(self.coloursText(palette or []))
        self._ownShown(self.paletteCombo.currentText())
        self.intensityCombo.setCurrentText(str(st.get("intensity", "medium")).capitalize())
        self.animCheck.setChecked(bool(st.get("use_animations", True)))
        self.soundCheck.setChecked(bool(st.get("use_sound_modes", True)))
        sections = st.get("sections") or {}
        for kind in show.DRAFT_SECTIONS:
            sec = sections.get(kind) or {}
            beh = sec.get("behaviour", show.DRAFT_DEFAULT_BEHAVIOUR[kind])
            beh = [beh] if isinstance(beh, str) else list(beh)
            self._order[kind] = list(beh)
            for act in self.behaviourButtons[kind].menu().actions():
                act.blockSignals(True)
                act.setChecked(act.text() in beh)
                act.blockSignals(False)
            self._behavioursChanged(kind)
            self.animEdits[kind].setText(show.draftPoolText(dict({"tags": [], "exclude": [], "names": []}, **(sec.get("animations") or {}))))
            self.soundEdits[kind].setText(show.draftPoolText(dict({"tags": [], "exclude": [], "names": []}, **(sec.get("sound_modes") or {}))))
            self._counts(kind)
        self.status.setText("Can't be used: " + "; ".join(st["errors"]) if st.get("errors") else "")
        # the behaviour column fits its longest list (within reason), leaving Matches the rest
        want = max(b.sizeHint().width() for b in self.behaviourButtons.values()) + 12
        self.table.setColumnWidth(1, max(self.table.columnWidth(1), min(280, want)))

    def _ownShown(self, palette):
        self.coloursEdit.setVisible(palette == self.OWN)
        self.addColourButton.setVisible(palette == self.OWN)

    def addColour(self, hue=None, sat=None):
        """Append a wheel-picked colour (or the one given) to the own colours."""
        if hue is None:
            dlg = ColourPickDialog(35, 90, self)
            if not _exec(dlg):
                return
            hue, sat = dlg.value()
        text = self.coloursEdit.text().strip().rstrip(",").strip()
        self.coloursEdit.setText((text + ", " if text else "") + "%d/%d" % (hue, sat))

    def _behavioursChanged(self, kind):
        # kept in the order chosen: sections of the kind take them in turn from the first
        checked = [a.text() for a in self.behaviourButtons[kind].menu().actions() if a.isChecked()]
        chosen = [b for b in self._order.get(kind, []) if b in checked] + [b for b in checked if b not in self._order.get(kind, [])]
        self._order[kind] = chosen
        self.behaviourButtons[kind].setText(", ".join(chosen) or show.DRAFT_DEFAULT_BEHAVIOUR[kind])
        self.behaviourButtons[kind].setToolTip("\n".join("%s: %s" % (b, show.DRAFT_BEHAVIOUR_NOTES[b]) for b in (chosen or [show.DRAFT_DEFAULT_BEHAVIOUR[kind]]))
                                               + "\n\nSeveral: sections of this kind take turns, a repeated part keeping its own.")

    def _counts(self, kind):
        row = show.DRAFT_SECTIONS.index(kind)
        anims = self.host.poolCounts(show.draftPoolFromText(self.animEdits[kind].text(), self._names["animations"]), "animations")
        modes = self.host.poolCounts(show.draftPoolFromText(self.soundEdits[kind].text(), self._names["sound_modes"]), "sound_modes")
        item = self.table.item(row, 4)
        item.setText("%d anim%s, %d sound%s" % (anims, "" if self.animCheck.isChecked() else " (off)",
                                                  modes, "" if self.soundCheck.isChecked() else " (off)"))
        item.setToolTip("%d animations and %d sound modes match%s" % (anims, modes, "" if self.animCheck.isChecked() and self.soundCheck.isChecked()
                                                                        else "; the ones marked off aren't used by this style"))

    def data(self, name=None):
        """The style as edited, or None (with the reason in the status line) if the colours don't read."""
        out = {"format": 1, "name": name or self.styleCombo.currentText(), "description": self.descEdit.text().strip(),
               "genres": [g.strip() for g in self.genresEdit.text().split(",") if g.strip()],
               "intensity": self.intensityCombo.currentText().lower(),
               "use_animations": self.animCheck.isChecked(), "use_sound_modes": self.soundCheck.isChecked(), "sections": {}}
        if self.paletteCombo.currentText() == self.OWN:
            out["palette"] = self.coloursFromText(self.coloursEdit.text())
            if out["palette"] is None:
                self.status.setText("Colours are hue/saturation pairs (35/90) or Kelvin (2700K), separated by commas")
                return None
        else:
            out["palette"] = self.paletteCombo.currentText()
        for kind in show.DRAFT_SECTIONS:
            beh = self._order.get(kind) or [show.DRAFT_DEFAULT_BEHAVIOUR[kind]]
            out["sections"][kind] = {"behaviour": beh[0] if len(beh) == 1 else beh,
                                     "animations": show.draftPoolFromText(self.animEdits[kind].text(), self._names["animations"]),
                                     "sound_modes": show.draftPoolFromText(self.soundEdits[kind].text(), self._names["sound_modes"])}
        return out

    def _saveAs(self, name, original, overwrite):
        data = self.data(name)
        if data is None:
            return None
        result = self.host.saveStyle(data, original, overwrite)
        if not result.get("success"):
            self.status.setText("Couldn't save: " + "; ".join(result.get("errors", [])))
            return result
        self.status.setText("Saved " + result["style"])
        self.reload(result["style"])
        self.saved.emit(result["style"])
        return result

    def save(self):
        name = self.styleCombo.currentText()
        return self._saveAs(name, name, True) if name else None

    def saveAs(self, name=None):
        if name is None:
            name, ok = QInputDialog.getText(self, "Save style as", "Name:", text=self.styleCombo.currentText() + " copy")
            if not ok:
                return None
        name = str(name).strip()
        if not name:
            return None
        result = self._saveAs(name, None, False)
        if result is not None and not result.get("success") and any("exists" in e for e in result.get("errors", [])):
            if QMessageBox.question(self, "Replace style", "A style named %s exists. Replace it?" % name) == QMessageBox.Yes:
                result = self._saveAs(name, None, True)
        return result

    def delete(self, confirm=True):
        name = self.styleCombo.currentText()
        if not name or (confirm and QMessageBox.question(self, "Delete style", "Delete the draft style %s?" % name) != QMessageBox.Yes):
            return False
        ok = self.host.deleteStyle(name)
        self.reload()
        self.saved.emit(self.styleCombo.currentText())
        return ok


# ============================================================================
# THE EDITOR WINDOW
# ============================================================================

class SequenceEditor(QWidget):
    """host provides:
        lights()                 -> [{"index", "id", "name", "role", "side", "simulated"}] in sweep order
        resolveTarget(target)    -> light indices the target matches now
        targetChoices()          -> [(label, target)] for the target box
        animationNames()         -> sorted list of animation names
        render(seq)              -> renderSequence-style dict
        save(seq, original, overwrite) -> {"success", "errors", "warnings", "sequence"}
        sequenceExists(name)     -> bool
        presetCount()            -> int
        playOnLights(seq, ms)    -> {"success", "errors"}
        stopOnLights()
        lightsPosition()         -> ms of the playing sequence, or None
    """

    def __init__(self, host, seq=None, originalName=None, parent=None):
        super().__init__(parent, Qt.Window)
        self.host = host
        self.seq = copy.deepcopy(seq) if seq else newSequence()
        self.seq.setdefault("format", 1)
        self.seq.setdefault("cues", [])
        self.originalName = originalName
        self.dirty = False
        self.selection = []
        self.clipboard = []
        self.undoStack, self.redoStack = [], []
        self.playhead = 0
        self.playing = False
        self._playStart = (0.0, 0)
        self.sendingToLights = False
        self.tracks, self.cueLights = [], {}
        self.renderChanges, self.renderEnd = {}, 0
        self.lastRender = None
        self._loadingProps = False

        self.setWindowTitle("Sequence editor")
        try:  # tall by default, so every light's track and the preview show
            avail = self.screen().availableGeometry().height()
        except Exception:
            avail = 900
        try:
            availW = self.screen().availableGeometry().width()
        except Exception:
            availW = 1280
        self.resize(min(1250, int(availW * 0.95)), int(max(min(680, avail * 0.9), min(1000, avail * 0.85))))
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        # --- top bar: name, length, tempo, snap, zoom, file actions
        # toolbars wrap onto more rows in a narrow window rather than holding it wide
        top = FlowLayout()
        top.addWidget(QLabel("Name"))
        self.nameEdit = QLineEdit(self.seq.get("name", ""))
        self.nameEdit.setMinimumWidth(200)
        self.nameEdit.textEdited.connect(self._nameEdited)
        top.addWidget(self.nameEdit, 1)
        top.addWidget(QLabel("Length"))
        self.durationSpin = DoubleSpinBoxWithButtons()
        self.durationSpin.setRange(1, 86400)
        self.durationSpin.setDecimals(1)
        self.durationSpin.setSuffix(" s")
        self.durationSpin.setValue(int(self.seq.get("duration_ms") or 30000) / 1000.0)
        self.durationSpin.editingFinished.connect(self._durationEdited)
        top.addWidget(self.durationSpin)
        top.addWidget(QLabel("Tempo"))
        self.bpmSpin = DoubleSpinBoxWithButtons()
        self.bpmSpin.setRange(0, 300)
        self.bpmSpin.setDecimals(1)
        self.bpmSpin.setSpecialValueText("Off")
        self.bpmSpin.setSuffix(" BPM")
        self.bpmSpin.setToolTip("Draws beat lines and lets cues snap to beats. Stored in the file as \"tempo\".")
        tempo = self.seq.get("tempo")
        if isinstance(tempo, dict):
            self.bpmSpin.setValue(float(tempo.get("bpm", 0) or 0))
        self.bpmSpin.valueChanged.connect(self._tempoEdited)
        top.addWidget(self.bpmSpin)
        self.offsetSpin = SpinBoxWithButtons()
        self.offsetSpin.setRange(0, 600000)
        self.offsetSpin.setSuffix(" ms")
        self.offsetSpin.setToolTip("Time of the first beat")
        if isinstance(tempo, dict):
            self.offsetSpin.setValue(int(tempo.get("offset_ms", 0) or 0))
        self.offsetSpin.valueChanged.connect(self._tempoEdited)
        top.addWidget(self.offsetSpin)
        self.changeTempoButton = QPushButton("Change tempo...")
        self.changeTempoButton.setToolTip("Set a new tempo and move and stretch the cues so they stay on the same beats")
        self.changeTempoButton.clicked.connect(self.changeTempo)
        top.addWidget(self.changeTempoButton)
        top.addWidget(QLabel("Snap"))
        self.snapCombo = QComboBox()
        for label, value in SNAP_CHOICES:
            self.snapCombo.addItem(label, value)
        # a sequence with a tempo (a song draft) snaps to beats from the start
        self.snapCombo.setCurrentIndex(self.snapCombo.findData(-1) if self.bpmSpin.value() > 0 else 3)
        top.addWidget(self.snapCombo)
        zoomOut, zoomIn, fit = QPushButton("Zoom -"), QPushButton("Zoom +"), QPushButton("Fit")
        zoomOut.setToolTip("Zoom out (Ctrl+wheel)")
        zoomIn.setToolTip("Zoom in (Ctrl+wheel)")
        top.addWidget(zoomOut); top.addWidget(zoomIn); top.addWidget(fit)
        self.settingsButton = QPushButton("Settings...")
        self.validateButton = QPushButton("Check")
        self.validateButton.setToolTip("Validate the sequence against the current lights")
        self.saveButton = QPushButton("Save")
        self.saveAsButton = QPushButton("Save As...")
        for b in (self.settingsButton, self.validateButton, self.saveButton, self.saveAsButton):
            top.addWidget(b)
        root.addLayout(top)

        # --- transport
        trans = FlowLayout()
        self.toStartButton = QPushButton("|<")
        self.playButton = QPushButton("Play")
        self.stopButton = QPushButton("Stop")
        self.toStartButton.setToolTip("Playhead to the start (Home)")
        self.playButton.setToolTip("Play or pause from the playhead (Space)")
        for b in (self.toStartButton, self.playButton, self.stopButton):
            trans.addWidget(b)
        self.timeLabel = QLabel()
        f = QFont(self.font()); f.setBold(True)
        self.timeLabel.setFont(f)
        trans.addWidget(self.timeLabel)
        trans.addSpacing(16)
        self.sendCheck = QCheckBox("Send to lights")
        self.sendCheck.setToolTip("Play the edit through the real lights from the playhead. Off: preview on screen only.")
        trans.addWidget(self.sendCheck)
        trans.addSpacing(16)
        self.addColourButton = QPushButton("+ Colour cue")
        self.addClipButton = QPushButton("+ Clip cue")
        self.addSoundButton = QPushButton("+ Sound cue")
        self.addSoundButton.setToolTip("Hand the selected track's lights to a sound mode for a while (live sound, while the sequence plays)")
        self.undoButton = QPushButton("Undo")
        self.redoButton = QPushButton("Redo")
        for b in (self.addColourButton, self.addClipButton, self.addSoundButton, self.undoButton, self.redoButton):
            trans.addWidget(b)
        root.addLayout(trans)

        # --- timeline + properties
        split = QSplitter(Qt.Horizontal)
        # tracks above, preview below, with a divider to drag between them; the tracks scroll when
        # there are more than fit
        tracksBox = QWidget()
        leftLay = QVBoxLayout(tracksBox)
        leftLay.setContentsMargins(0, 0, 0, 0)
        leftLay.setSpacing(0)
        self.view = TimelineView(self)
        self.trackScroll = QScrollArea()
        self.trackScroll.setWidgetResizable(True)
        self.trackScroll.setFrameShape(QFrame.NoFrame)
        self.trackScroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.trackScroll.setWidget(self.view)
        leftLay.addWidget(self.trackScroll, 1)
        self.hScroll = QScrollBar(Qt.Horizontal)
        self.view.scrollBar = self.hScroll
        self.hScroll.valueChanged.connect(self.view.onScroll)
        leftLay.addWidget(self.hScroll)
        hint = QLabel("Double-click a track to add a cue. Drag a cue to move it, its right edge to change its length, "
                      "the notch at its top to change the fade. Right-click for more. Dashed outlines are cues shared by several lights.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        leftLay.addWidget(hint)
        previewBox = QWidget()
        previewLay = QVBoxLayout(previewBox)
        previewLay.setContentsMargins(0, 6, 0, 0)
        previewLay.setSpacing(0)
        previewRow = QHBoxLayout()
        previewLabel = QLabel("Preview at the playhead")
        previewLabel.setStyleSheet("color: #aaa;")
        previewRow.addWidget(previewLabel)
        previewRow.addStretch(1)
        self.viewCombo = QComboBox()
        self.viewCombo.addItems(["Plan", "Height", "Strip"])
        self.viewCombo.setToolTip("Plan: where each light stands, from your seat facing the camera.\nHeight: high to low. Strip: sweep order.")
        previewRow.addWidget(self.viewCombo)
        previewLay.addLayout(previewRow)
        self.stage = StageView(self)
        self.viewCombo.currentIndexChanged.connect(lambda i: self.stage.setViewMode(["plan", "height", "strip"][i]))
        # the preview's grid scales to fill whatever height it's given
        self.stage.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        previewLay.addWidget(self.stage, 1)
        self.vSplit = QSplitter(Qt.Vertical)
        self.vSplit.addWidget(tracksBox)
        self.vSplit.addWidget(previewBox)
        self.vSplit.setChildrenCollapsible(False)
        self.vSplit.setStretchFactor(1, 1)
        split.addWidget(self.vSplit)
        self.props = self._buildProperties()
        propsScroll = QScrollArea()
        propsScroll.setWidgetResizable(True)
        propsScroll.setFrameShape(QFrame.NoFrame)
        propsScroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        propsScroll.setWidget(self.props)
        split.addWidget(propsScroll)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 1)
        # the panel can be dragged wider or narrower, but never under what its fields need
        propsScroll.setMinimumWidth(self.props.minimumSizeHint().width() + 16)
        split.setChildrenCollapsible(False)
        for sp in (split, self.vSplit):
            sp.setHandleWidth(7)
            sp.setStyleSheet("QSplitter::handle { background: #3a3a46; } QSplitter::handle:hover { background: #5a6a9a; }")
        self.hSplit = split
        root.addWidget(split, 1)

        # --- status
        self.statusLabel = QLabel()
        self.statusLabel.setWordWrap(True)
        root.addWidget(self.statusLabel)

        # --- wiring
        zoomOut.clicked.connect(lambda: self.view.setZoom(self.view.pxPerSec * 0.8))
        zoomIn.clicked.connect(lambda: self.view.setZoom(self.view.pxPerSec * 1.25))
        fit.clicked.connect(self.view.zoomToFit)
        self.settingsButton.clicked.connect(self.editSettings)
        self.validateButton.clicked.connect(self.validate)
        self.saveButton.clicked.connect(self.save)
        self.saveAsButton.clicked.connect(lambda: self.save(saveAs=True))
        self.toStartButton.clicked.connect(lambda: self.setPlayhead(0))
        self.playButton.clicked.connect(self.togglePlay)
        self.stopButton.clicked.connect(self.stop)
        self.sendCheck.toggled.connect(self._sendToggled)
        self.addColourButton.clicked.connect(lambda: self.addCue("state", self._selectedTrackRow(), self.snap(self.playhead)))
        self.addClipButton.clicked.connect(lambda: self.addCue("clip", self._selectedTrackRow(), self.snap(self.playhead)))
        self.addSoundButton.clicked.connect(lambda: self.addCue("sound", self._selectedTrackRow(), self.snap(self.playhead)))
        self.undoButton.clicked.connect(self.undo)
        self.redoButton.clicked.connect(self.redo)
        for keys, fn in ((QKeySequence.Undo, self.undo), (QKeySequence.Redo, self.redo),
                         (QKeySequence.Copy, self.copySelection), (QKeySequence.Paste, lambda: self.paste(self.snap(self.playhead))),
                         (QKeySequence.Delete, self.deleteSelection), (QKeySequence("Ctrl+D"), self.duplicateSelection),
                         (QKeySequence.Save, self.save), (QKeySequence("Space"), self.togglePlay),
                         (QKeySequence("Home"), lambda: self.setPlayhead(0)), (QKeySequence.SelectAll, self.selectAll)):
            sc = QShortcut(keys, self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(fn)

        self.renderTimer = QTimer(self)
        self.renderTimer.setSingleShot(True)
        self.renderTimer.timeout.connect(self.rerender)
        self.restartTimer = QTimer(self)
        self.restartTimer.setSingleShot(True)
        self.restartTimer.timeout.connect(self._restartOnLights)
        self.playTimer = QTimer(self)
        self.playTimer.timeout.connect(self._tick)

        self.rebuildTracks()
        self.rerender()
        self._updateTitle()
        self._updateTime()
        QTimer.singleShot(0, self.view.zoomToFit)

    # --- properties panel ----------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_splitSized", False):
            # the tracks get their full height, up to 60% of the room; the preview the rest
            self._splitSized = True
            props = max(PROPS_START_W, self.hSplit.widget(1).minimumWidth())
            self.hSplit.setSizes([max(1, self.hSplit.width() - props), props])
            room = self.vSplit.height()
            tracks = min(self.view.height() + self.hScroll.sizeHint().height() + 50, int(room * 0.6))
            self.vSplit.setSizes([tracks, max(1, room - tracks)])

    def _buildProperties(self):
        panel = QWidget()
        panel.setMinimumWidth(260)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(6, 0, 0, 0)
        self.propTitle = QLabel("No cue selected")
        f = QFont(self.font()); f.setBold(True)
        self.propTitle.setFont(f)
        lay.addWidget(self.propTitle)
        self.propStack = QStackedWidget()
        lay.addWidget(self.propStack, 1)

        empty = QLabel("Select a cue to edit it, or double-click a track to add one.")
        empty.setWordWrap(True)
        empty.setAlignment(Qt.AlignTop)
        self.propStack.addWidget(empty)

        cueW = QWidget()
        form = QFormLayout(cueW)
        form.setContentsMargins(0, 0, 0, 0)
        self.pStart = DoubleSpinBoxWithButtons(); self.pStart.setRange(0, 86400); self.pStart.setDecimals(3); self.pStart.setSuffix(" s")
        self.pStart.setSingleStep(0.1)
        form.addRow("Start", self.pStart)
        self.pTarget = QComboBox(); self.pTarget.setEditable(True)
        self.pTarget.setToolTip("Lights: an ID, a name, @key/@fill/@rim/@background/@practical, @left/@right, @all or *, several joined with ;")
        form.addRow("Lights", self.pTarget)
        self.pMatches = QLabel()
        self.pMatches.setStyleSheet("color: #999;")
        self.pMatches.setWordWrap(True)
        form.addRow("", self.pMatches)
        self.pKind = QComboBox(); self.pKind.addItem("Colour", "state"); self.pKind.addItem("Clip (animation)", "clip")
        self.pKind.addItem("Sound mode", "sound")
        form.addRow("Type", self.pKind)
        self.pMode = QComboBox(); self.pMode.addItems(["HSI", "CCT"])
        form.addRow("Mode", self.pMode)
        self.pHue = SpinBoxWithButtons(); self.pHue.setRange(0, 360); self.pHue.setSuffix(" °")
        self.pSat = SpinBoxWithButtons(); self.pSat.setRange(0, 100); self.pSat.setSuffix(" %")
        self.pTemp = SpinBoxWithButtons(); self.pTemp.setRange(3200, 8500); self.pTemp.setSingleStep(100); self.pTemp.setSuffix(" K")
        self.pBri = SpinBoxWithButtons(); self.pBri.setRange(0, 100); self.pBri.setSuffix(" %")
        self.pFade = SpinBoxWithButtons(); self.pFade.setRange(0, 600000); self.pFade.setSingleStep(100); self.pFade.setSuffix(" ms")
        self.pSwatch = QLabel(); self.pSwatch.setFixedHeight(16)
        self.pPick = ColourPickRow(lambda: (self.pHue.value(), self.pSat.value()), self._pickColour, columns=6)
        self.pClip = QComboBox()
        self.pSound = QComboBox()
        self.pSound.setToolTip("The sound mode these lights follow for the cue's length (live sound, while the sequence plays)")
        self.pFit = QComboBox(); self.pFit.addItem("Stretch to fit", "stretch"); self.pFit.addItem("Loop", "loop")
        self.pSpeed = DoubleSpinBoxWithButtons(); self.pSpeed.setRange(0.05, 20); self.pSpeed.setSingleStep(0.1); self.pSpeed.setValue(1)
        self.pClipBri = SpinBoxWithButtons(); self.pClipBri.setRange(0, 100); self.pClipBri.setSuffix(" %"); self.pClipBri.setValue(100)
        self.pDuration = SpinBoxWithButtons(); self.pDuration.setRange(0, 86400000); self.pDuration.setSingleStep(100); self.pDuration.setSuffix(" ms")
        self.pLabel = QLineEdit(); self.pLabel.setPlaceholderText("(optional)")
        self._rows = {}
        for key, label, w in (("hue", "Hue", self.pHue), ("sat", "Saturation", self.pSat), ("temp", "Colour temp", self.pTemp),
                              ("pick", "", self.pPick), ("bri", "Brightness", self.pBri), ("fade", "Fade in", self.pFade), ("swatch", "", self.pSwatch),
                              ("clip", "Animation", self.pClip), ("sound", "Sound mode", self.pSound), ("fit", "Fit", self.pFit), ("speed", "Speed", self.pSpeed),
                              ("clipbri", "Brightness", self.pClipBri), ("duration", "Length", self.pDuration), ("label", "Label", self.pLabel)):
            form.addRow(label, w)
            self._rows[key] = (form.labelForField(w), w)
        self._rows["mode"] = (form.labelForField(self.pMode), self.pMode)
        self.pDuration.setToolTip("Colour cue: 0 holds until a later cue changes the light; a length ends it and the light goes back.\nClip: how long the clip plays.")
        self.propStack.addWidget(cueW)

        multiW = QWidget()
        mLay = QVBoxLayout(multiW)
        mLay.setContentsMargins(0, 0, 0, 0)
        self.multiLabel = QLabel()
        mLay.addWidget(self.multiLabel)
        delBtn = QPushButton("Delete selected")
        delBtn.clicked.connect(self.deleteSelection)
        dupBtn = QPushButton("Duplicate selected")
        dupBtn.clicked.connect(self.duplicateSelection)
        mLay.addWidget(dupBtn)
        mLay.addWidget(delBtn)
        mLay.addStretch(1)
        self.propStack.addWidget(multiW)

        for w in (self.pStart, self.pSpeed):
            w.valueChanged.connect(self._propChanged)
        for w in (self.pHue, self.pSat, self.pTemp, self.pBri, self.pFade, self.pClipBri, self.pDuration):
            w.valueChanged.connect(self._propChanged)
        for w in (self.pKind, self.pMode, self.pClip, self.pSound, self.pFit):
            w.currentIndexChanged.connect(self._propChanged)
        self.pTarget.lineEdit().editingFinished.connect(self._propChanged)
        self.pTarget.activated.connect(self._targetPicked)
        self.pLabel.editingFinished.connect(self._propChanged)
        return panel

    def _pickColour(self, hue, sat):
        # one edit (one undo step) for both values
        for w, v in ((self.pHue, hue), (self.pSat, sat)):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        self._propChanged()

    def _targetPicked(self, index):
        # the list shows friendly labels; the cue stores the target itself
        target = self.pTarget.itemData(index)
        if target:
            self.pTarget.setEditText(target)
        self._propChanged()

    def _showRows(self, keys):
        for key, (label, w) in self._rows.items():
            visible = key in keys
            w.setVisible(visible)
            if label is not None:
                label.setVisible(visible)

    def _loadProperties(self):
        self._loadingProps = True
        try:
            sel = [i for i in self.selection if 0 <= i < len(self.seq["cues"])]
            if not sel:
                self.propTitle.setText("No cue selected")
                self.propStack.setCurrentIndex(0)
                return
            if len(sel) > 1:
                self.propTitle.setText(str(len(sel)) + " cues selected")
                self.multiLabel.setText("Drag any of them to move them together.")
                self.propStack.setCurrentIndex(2)
                return
            cue = self.seq["cues"][sel[0]]
            self.propTitle.setText("Cue at " + fmtTime(cue.get("at_ms", 0), True))
            self.propStack.setCurrentIndex(1)
            self.pStart.setValue(int(cue.get("at_ms", 0)) / 1000.0)
            self.pTarget.clear()
            for label, target in self.host.targetChoices():
                self.pTarget.addItem(label, target)
            self.pTarget.setEditText(str(cue.get("target", "*")))
            matched = self.host.resolveTarget(str(cue.get("target", "*")))
            names = {l["index"]: l["name"] for l in self.host.lights()}
            self.pMatches.setText(("Drives: " + ", ".join(names.get(i, "?") for i in matched)) if matched else "Matches no light right now")
            kind = cueKind(cue)
            self.pKind.setCurrentIndex(self.pKind.findData(kind))
            self.pDuration.setValue(int(cue.get("duration_ms") or 0))
            self.pLabel.setText(str(cue.get("label", "")))
            if kind == "state":
                st = cue.get("state", {})
                mode = st.get("mode", "HSI")
                self.pMode.setCurrentText(mode)
                self.pHue.setValue(int(st.get("hue", 0)))
                self.pSat.setValue(int(st.get("sat", 100)))
                self.pTemp.setValue(int(st.get("temp", 56)) * 100)
                self.pBri.setValue(int(st.get("bri", 100)))
                self.pFade.setValue(int(st.get("fade_ms", 0) or 0))
                rgb = cueColour(cue)
                self.pSwatch.setStyleSheet("background: %s; border: 1px solid #555;" % show.rgbHex(rgb))
                self._showRows({"mode", "hue", "sat", "pick", "bri", "fade", "swatch", "duration", "label"} if mode == "HSI"
                               else {"mode", "temp", "bri", "fade", "swatch", "duration", "label"})
                self._rows["duration"][0].setText("Length (0 = hold)")
            elif kind == "sound":
                self.pSound.clear()
                self.pSound.addItems(self.host.soundModeNames())
                self.pSound.setCurrentText(soundName(cue))
                self._showRows({"sound", "duration", "label"})
                self._rows["duration"][0].setText("Length")
            else:
                c = cue.get("clip")
                c = {"name": c} if isinstance(c, str) else (c or {})
                self.pClip.clear()
                self.pClip.addItems(self.host.animationNames())
                self.pClip.setCurrentText(c.get("name", ""))
                self.pFit.setCurrentIndex(0 if c.get("fit", "stretch") == "stretch" else 1)
                self.pSpeed.setValue(float(c.get("speed", 1)))
                self.pClipBri.setValue(int(c.get("brightness", 100)))
                self._showRows({"clip", "fit", "speed", "clipbri", "duration", "label"})
                self._rows["duration"][0].setText("Length")
        finally:
            self._loadingProps = False

    def _propChanged(self, *args):
        if self._loadingProps or len(self.selection) != 1:
            return
        i = self.selection[0]
        if not 0 <= i < len(self.seq["cues"]):
            return
        old = json.dumps(self.seq["cues"][i], sort_keys=True)
        cue = copy.deepcopy(self.seq["cues"][i])
        cue["at_ms"] = int(round(self.pStart.value() * 1000))
        cue["target"] = self.pTarget.currentText().strip() or "*"
        label = self.pLabel.text().strip()
        if label:
            cue["label"] = label
        else:
            cue.pop("label", None)
        kind = self.pKind.currentData()
        dur = self.pDuration.value()
        if kind == "state":
            cue.pop("clip", None)
            cue.pop("sound", None)
            mode = self.pMode.currentText()
            st = {"mode": mode, "bri": self.pBri.value()}
            if mode == "HSI":
                st.update(hue=self.pHue.value(), sat=self.pSat.value())
            else:
                st["temp"] = int(round(self.pTemp.value() / 100.0))
            if self.pFade.value():
                st["fade_ms"] = self.pFade.value()
            cue["state"] = st
            if dur:
                cue["duration_ms"] = dur
            else:
                cue.pop("duration_ms", None)
        elif kind == "sound":
            cue.pop("state", None)
            cue.pop("clip", None)
            spec = cue.get("sound") if isinstance(cue.get("sound"), dict) else {}
            # the mode's own values changed for this cue (palette and so on) stay
            spec = dict(spec, mode=self.pSound.currentText() or (self.host.soundModeNames() or [""])[0])
            cue["sound"] = spec
            cue["duration_ms"] = max(1, dur or SOUND_CUE_DEFAULT_MS)
        else:
            cue.pop("state", None)
            cue.pop("sound", None)
            name = self.pClip.currentText() or (self.host.animationNames() or [""])[0]
            clip = {"name": name, "fit": self.pFit.currentData()}
            if self.pSpeed.value() != 1:
                clip["speed"] = round(self.pSpeed.value(), 3)
            if self.pClipBri.value() != 100:
                clip["brightness"] = self.pClipBri.value()
            cue["clip"] = clip
            cue["duration_ms"] = max(1, dur or 4000)
        if json.dumps(cue, sort_keys=True) == old:
            return
        self.pushUndo()
        self.seq["cues"][i] = cue
        kindChanged = kind != cueKind(json.loads(old))
        self.changed()
        if kindChanged:
            self._loadProperties()
        else:
            rgb = cueColour(cue)
            if rgb:
                self.pSwatch.setStyleSheet("background: %s; border: 1px solid #555;" % show.rgbHex(rgb))
            self.pMatches.setText(self._matchText(cue))
            if cue.get("state", {}).get("mode") and ((cue["state"]["mode"] == "HSI") != self.pHue.isVisible()):
                self._loadProperties()

    def _matchText(self, cue):
        matched = self.host.resolveTarget(str(cue.get("target", "*")))
        names = {l["index"]: l["name"] for l in self.host.lights()}
        return ("Drives: " + ", ".join(names.get(i, "?") for i in matched)) if matched else "Matches no light right now"

    def focusProperties(self):
        if self.propStack.currentIndex() == 1:
            self.pStart.setFocus()

    # --- data plumbing ---------------------------------------------------------
    def bpm(self):
        return self.bpmSpin.value()

    def beatOffset(self):
        return self.offsetSpin.value()

    def snap(self, ms):
        return snapTime(ms, self.snapCombo.currentData(), self.bpm(), self.beatOffset())

    def rebuildTracks(self):
        """One track per light in sweep order, plus one for cues that match no light."""
        lights = self.host.lights()
        self.tracks = [{"index": l["index"], "id": str(l["id"]), "label": str(l["id"]) + "  " + l["name"],
                        "sub": (l.get("role", "") or "").capitalize() + ((", " + l["side"]) if l.get("side") else "") + (" (simulated)" if l.get("simulated") else ""),
                        "cues": [], "target": str(l["id"])} for l in lights]
        byIndex = {t["index"]: t for t in self.tracks}
        self.cueLights = {}
        orphans = []
        for i, cue in enumerate(self.seq["cues"]):
            matched = [x for x in self.host.resolveTarget(str(cue.get("target", "*"))) if x in byIndex]
            self.cueLights[i] = matched
            if matched:
                for x in matched:
                    byIndex[x]["cues"].append(i)
            else:
                orphans.append(i)
        if orphans:
            self.tracks.append({"index": None, "id": None, "label": "No matching light", "sub": "cues for lights that aren't here",
                                "cues": orphans, "target": "*"})
        self.view.updateGeometry()
        self.view.setFixedHeight(self.view.sizeHint().height())
        self.view.update()

    def pushUndo(self):
        self.undoStack.append((json.dumps(self.seq), list(self.selection)))
        del self.undoStack[:-UNDO_LIMIT]
        self.redoStack.clear()

    def undo(self):
        if not self.undoStack:
            return
        self.redoStack.append((json.dumps(self.seq), list(self.selection)))
        data, sel = self.undoStack.pop()
        self.seq = json.loads(data)
        self.selection = [i for i in sel if i < len(self.seq["cues"])]
        self._afterReplace()

    def redo(self):
        if not self.redoStack:
            return
        self.undoStack.append((json.dumps(self.seq), list(self.selection)))
        data, sel = self.redoStack.pop()
        self.seq = json.loads(data)
        self.selection = [i for i in sel if i < len(self.seq["cues"])]
        self._afterReplace()

    def _afterReplace(self):
        self.nameEdit.setText(self.seq.get("name", ""))
        tempo = self.seq.get("tempo") if isinstance(self.seq.get("tempo"), dict) else {}
        for spin, value in ((self.durationSpin, int(self.seq.get("duration_ms") or 1000) / 1000.0),
                            (self.bpmSpin, float(tempo.get("bpm", 0) or 0)), (self.offsetSpin, int(tempo.get("offset_ms", 0) or 0))):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self.changed()
        self._loadProperties()

    def changed(self, live=False):
        """Called after any edit. live=True during a drag: redraw now, rebuild and render shortly."""
        self.dirty = True
        self._updateTitle()
        if not live:
            self.rebuildTracks()
            self.view.syncScrollBar()
            self._loadPropertiesIfSingleMoved()
        self.view.update()
        self.renderTimer.start(60 if live else 20)
        if self.sendingToLights and self.playing:
            self.restartTimer.start(300)

    def _loadPropertiesIfSingleMoved(self):
        if len(self.selection) == 1 and not self._loadingProps:
            cue = self.seq["cues"][self.selection[0]] if self.selection[0] < len(self.seq["cues"]) else None
            if cue is not None and self.propStack.currentIndex() == 1:
                self._loadingProps = True
                self.pStart.setValue(int(cue.get("at_ms", 0)) / 1000.0)
                self.pDuration.setValue(int(cue.get("duration_ms") or 0))
                if cueKind(cue) == "state":
                    self.pFade.setValue(int(cue.get("state", {}).get("fade_ms") or 0))
                self.propTitle.setText("Cue at " + fmtTime(cue.get("at_ms", 0), True))
                self._loadingProps = False

    def rerender(self):
        result = self.host.render(self.seq)
        if result.get("success"):
            self.lastRender = result
            self.renderChanges = result["changes"]
            self.renderEnd = result["end_ms"]
            warn = list(result.get("warnings") or [])
            fl = result.get("flashes") or {}
            rate = max(fl.get("worst", 0), fl.get("worstRed", 0))
            if rate > fl.get("limit", 3):
                warn.insert(0, "flashes up to %.1f times a second; the flash guard (if on) will hold some back" % rate)
            self._setStatus(("Warnings: " + "; ".join(warn)) if warn else "", "warn" if warn else "")
        else:
            self._setStatus("Won't play yet: " + "; ".join(result.get("errors", [])[:3]), "error")
        self.view.update()
        self._updateStage()

    def _setStatus(self, text, level=""):
        colour = {"error": "#e06060", "warn": "#d8a040", "ok": "#60c070"}.get(level, "#999")
        self.statusLabel.setStyleSheet("color: %s;" % colour)
        self.statusLabel.setText(text)

    def setSelection(self, sel):
        self.selection = [i for i in dict.fromkeys(sel) if 0 <= i < len(self.seq["cues"])]
        self._loadProperties()
        self.view.update()

    def selectAll(self):
        self.setSelection(list(range(len(self.seq["cues"]))))

    def _selectedTrackRow(self):
        if self.selection and self.selection[0] in self.cueLights and self.cueLights[self.selection[0]]:
            first = self.cueLights[self.selection[0]][0]
            for row, t in enumerate(self.tracks):
                if t["index"] == first:
                    return row
        return None

    # --- editing actions -----------------------------------------------------
    def addCue(self, kind, row, at):
        target = self.tracks[row]["target"] if row is not None and 0 <= row < len(self.tracks) else "*"
        at = max(0, min(int(at), int(self.seq.get("duration_ms") or 1) - 1))
        if kind == "clip":
            names = self.host.animationNames()
            cue = {"at_ms": at, "duration_ms": 4000, "target": target, "clip": {"name": names[0] if names else "", "fit": "stretch"}}
        elif kind == "sound":
            names = self.host.soundModeNames()
            cue = {"at_ms": at, "duration_ms": SOUND_CUE_DEFAULT_MS, "target": target, "sound": {"mode": names[0] if names else ""}}
        else:
            # start from the colour the light has at that point, so a new cue is an easy tweak
            st = {"mode": "HSI", "hue": 0, "sat": 100, "bri": 80}
            if row is not None and 0 <= row < len(self.tracks):
                spans = cueSpans(self.seq, self.tracks[row]["cues"])
                before = [i for i, (s, e, hold) in spans.items() if s <= at and cueKind(self.seq["cues"][i]) == "state"]
                if before:
                    prev = max(before, key=lambda i: int(self.seq["cues"][i].get("at_ms", 0)))
                    st = copy.deepcopy(self.seq["cues"][prev].get("state", st))
                    st.pop("fade_ms", None)
            cue = {"at_ms": at, "target": target, "state": st}
        self.pushUndo()
        self.seq["cues"].append(cue)
        self.selection = [len(self.seq["cues"]) - 1]
        self.changed()
        self._loadProperties()

    def deleteSelection(self):
        if not self.selection:
            return
        self.pushUndo()
        for i in sorted(self.selection, reverse=True):
            if 0 <= i < len(self.seq["cues"]):
                del self.seq["cues"][i]
        self.selection = []
        self.changed()
        self._loadProperties()

    def copySelection(self):
        cues = [copy.deepcopy(self.seq["cues"][i]) for i in sorted(self.selection) if 0 <= i < len(self.seq["cues"])]
        if cues:
            first = min(int(c.get("at_ms", 0)) for c in cues)
            for c in cues:
                c["at_ms"] = int(c.get("at_ms", 0)) - first
            self.clipboard = cues

    def paste(self, at):
        if not self.clipboard:
            return
        self.pushUndo()
        start = len(self.seq["cues"])
        for c in self.clipboard:
            c = copy.deepcopy(c)
            c["at_ms"] = int(at) + int(c.get("at_ms", 0))
            self.seq["cues"].append(c)
        self.selection = list(range(start, len(self.seq["cues"])))
        self.changed()
        self._loadProperties()

    def duplicateSelection(self):
        if not self.selection:
            return
        cues = [self.seq["cues"][i] for i in sorted(self.selection) if 0 <= i < len(self.seq["cues"])]
        span = max(int(c.get("at_ms", 0)) + int(c.get("duration_ms") or 0) for c in cues) - min(int(c.get("at_ms", 0)) for c in cues)
        self.copySelection()
        self.paste(min(int(c.get("at_ms", 0)) for c in cues) + max(span, 500))

    def editSettings(self):
        dlg = SequenceSettingsDialog(self.seq, self.host.presetCount(), self)
        if dlg.exec() if hasattr(dlg, "exec") else dlg.exec_():
            self.pushUndo()
            dlg.apply(self.seq)
            self.changed()

    def _nameEdited(self, text):
        self.seq["name"] = text.strip()
        self.dirty = True
        self._updateTitle()

    def _durationEdited(self):
        ms = int(round(self.durationSpin.value() * 1000))
        if ms != int(self.seq.get("duration_ms") or 0):
            self.pushUndo()
            self.seq["duration_ms"] = ms
            self.changed()

    def _tempoEdited(self, *args):
        bpm = self.bpmSpin.value()
        if bpm > 0:
            self.seq["tempo"] = {"bpm": round(bpm, 2), "offset_ms": self.offsetSpin.value()}
        else:
            self.seq.pop("tempo", None)
        self.dirty = True
        self._updateTitle()
        self.view.update()

    def changeTempo(self):
        """Change tempo...: a new BPM, optionally moving and stretching every cue so it stays
        on the same beat (one undoable edit)."""
        dlg = self._tempoDialog()
        self._changeTempoDialog = dlg  # tests drive it
        if dlg.exec() != QDialog.Accepted:
            return False
        return self.applyTempo(dlg.tempoSpin.value(), dlg.moveCheck.isChecked())

    def _tempoDialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Change tempo")
        form = QFormLayout(dlg)
        old = self.bpm()
        spin = DoubleSpinBoxWithButtons()
        spin.setRange(30, 300)
        spin.setDecimals(2)
        spin.setSuffix(" BPM")
        spin.setValue(old if old > 0 else 120)
        form.addRow("New tempo", spin)
        move = QCheckBox("Move and stretch the cues so they stay on the same beats")
        move.setChecked(old > 0)
        move.setEnabled(old > 0)
        move.setToolTip("Cue starts, lengths, fades, sections and the length scale by " +
                        ("the old tempo over the new one, about the first beat" if old > 0 else "(needs a tempo set first)"))
        form.addRow(move)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        dlg.tempoSpin, dlg.moveCheck = spin, move
        return dlg

    def applyTempo(self, bpm, moveCues):
        self.pushUndo()
        if moveCues:
            self.seq = rescaleTempo(self.seq, bpm)
        else:
            self.seq["tempo"] = {"bpm": round(float(bpm), 2), "offset_ms": self.beatOffset()}
        for spin, value in ((self.bpmSpin, self.seq["tempo"]["bpm"]), (self.offsetSpin, self.seq["tempo"]["offset_ms"]),
                            (self.durationSpin, int(self.seq.get("duration_ms") or 0) / 1000.0)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self.selection = []
        self.changed()
        self.view.syncScrollBar()
        self._setStatus("Tempo now %g BPM%s." % (self.seq["tempo"]["bpm"], ", cues moved to stay on their beats" if moveCues else ""), "ok")
        return True

    def _updateTitle(self):
        name = self.seq.get("name") or "Untitled"
        self.setWindowTitle(("* " if self.dirty else "") + name + " - Sequence editor")

    # --- validation and saving -----------------------------------------------
    def validate(self):
        result = self.host.render(self.seq)
        if not result.get("success"):
            self._setStatus("Problems: " + "; ".join(result.get("errors", [])), "error")
            return False
        warn = result.get("warnings") or []
        self._setStatus(("OK, with warnings: " + "; ".join(warn)) if warn else "OK: the sequence is valid.", "warn" if warn else "ok")
        return True

    def save(self, saveAs=False):
        if saveAs:
            name, ok = QInputDialog.getText(self, "Save sequence as", "Name:", text=self.seq.get("name", ""))
            if not ok or not name.strip():
                return False
            self.seq["name"] = name.strip()
            self.nameEdit.setText(self.seq["name"])
            original = None
        else:
            original = self.originalName
        name = self.seq.get("name", "").strip()
        if not name:
            self._setStatus("Give the sequence a name first.", "error")
            return False
        renaming = original is None or original.lower() != name.lower()
        overwrite = False
        if renaming and self.host.sequenceExists(name):
            answer = QMessageBox.question(self, "Replace sequence", "A sequence named '" + name + "' already exists. Replace it?",
                                          QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return False
            overwrite = True
        result = self.host.save(self.seq, original, overwrite)
        if not result.get("success"):
            self._setStatus("Not saved: " + "; ".join(result.get("errors", [])), "error")
            return False
        self.originalName = result.get("sequence", name)
        self.dirty = False
        self._updateTitle()
        warn = result.get("warnings") or []
        self._setStatus("Saved" + ((", with warnings: " + "; ".join(warn)) if warn else "."), "warn" if warn else "ok")
        return True

    # --- playback ---------------------------------------------------------------
    def setPlayhead(self, ms):
        dur = int(self.seq.get("duration_ms") or 0)
        self.playhead = max(0, min(dur, int(ms)))
        if self.playing:
            self._playStart = (time.monotonic(), self.playhead)
            if self.sendingToLights:
                self.restartTimer.start(150)
        self._updateTime()
        self._updateStage()
        self.view.update()

    def togglePlay(self):
        if self.playing:
            self.pause()
        else:
            self.play()

    def play(self):
        if self.playhead >= int(self.seq.get("duration_ms") or 0):
            self.playhead = 0
        self.playing = True
        self._playStart = (time.monotonic(), self.playhead)
        self.playButton.setText("Pause")
        if self.sendingToLights:
            self._restartOnLights()
        self.playTimer.start(33)

    def pause(self):
        self.playing = False
        self.playTimer.stop()
        self.playButton.setText("Play")
        if self.sendingToLights:
            self.host.stopOnLights()

    def stop(self):
        self.pause()
        self.setPlayhead(0)

    def _sendToggled(self, on):
        self.sendingToLights = on
        if on and self.playing:
            self._restartOnLights()
        elif not on:
            self.host.stopOnLights()

    def _restartOnLights(self):
        if not (self.sendingToLights and self.playing):
            return
        result = self.host.playOnLights(self.seq, self.playhead)
        if not result.get("success"):
            self._setStatus("Can't send to lights: " + "; ".join(result.get("errors", [])), "error")
            self.sendCheck.setChecked(False)
        else:
            self._playStart = (time.monotonic(), self.playhead)

    def _tick(self):
        pos = None
        if self.sendingToLights:
            pos = self.host.lightsPosition()
        if pos is None:
            t0, p0 = self._playStart
            pos = p0 + (time.monotonic() - t0) * 1000.0
        dur = int(self.seq.get("duration_ms") or 0)
        if pos >= dur:
            self.playhead = dur
            self.pause()
        else:
            self.playhead = int(pos)
        # keep the playhead in view
        if self.view.xFor(self.playhead) > self.view.width() - 40:
            self.view.offsetMs = max(0.0, self.playhead - self.view.visibleMs() * 0.2)
            self.view.syncScrollBar()
        self._updateTime()
        self._updateStage()
        self.view.update()

    def _updateTime(self):
        self.timeLabel.setText(fmtTime(self.playhead, True) + " / " + fmtTime(self.seq.get("duration_ms") or 0, True))

    def _updateStage(self):
        if not self.lastRender:
            return
        tiles = []
        metaById = {m["id"]: m for m in self.lastRender.get("lights", [])}
        for track in self.tracks:
            if track["index"] is None:
                continue
            ch = colourAt(self.renderChanges.get(track["id"], []), self.playhead)
            meta = metaById.get(track["id"], {})
            rgb = None
            mode, bri, layer = None, None, "base"
            if ch is not None and ch[1]:
                c = QColor(ch[1])
                rgb = (c.red(), c.green(), c.blue())
                bri, mode = ch[2], ch[3]
                layer = "show" if ch[4] == "sequence" else "base"
            tiles.append({"name": track["label"].split("  ", 1)[-1], "role": meta.get("role", ""), "rgb": rgb,
                          "mode": mode, "bri": bri, "linked": True, "simulated": meta.get("simulated", False), "layer": layer,
                          "side": meta.get("side"), "depth": meta.get("depth"), "height": meta.get("height"),
                          "aim": meta.get("aim", "you")})
        self.stage.setTiles(tiles)

    # --- closing ------------------------------------------------------------
    def closeEvent(self, event):
        if self.dirty:
            answer = QMessageBox.question(self, "Unsaved changes", "Save changes to '" + (self.seq.get("name") or "Untitled") + "'?",
                                          QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
            if answer == QMessageBox.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.Save and not self.save():
                event.ignore()
                return
        self.pause()
        self.playTimer.stop()
        super().closeEvent(event)
