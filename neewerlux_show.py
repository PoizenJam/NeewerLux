"""Show engine for NeewerLux: animation timelines, sequences and priority layers.

This module holds no BLE or Qt code. NeewerLux.py hands the compositor a hooks
object (target resolution, command encoding, current light bytes, locked
flags, worker wake-up, preset recall, status) so the same engine runs in the
GUI, in --http mode and in the offline test harness.

Layers, lowest to highest: base (0, manual and presets, owned by NeewerLux.py),
show (1, sequences or a background animation), effect (2, queued triggered
effects), override (3, the legacy one-animation-at-a-time slot). Each light is
driven by the highest layer whose current frame includes it; covered layers
keep their clocks running.
"""

import bisect
import math
import threading
import time

LAYER_BASE = 0
LAYER_SHOW = 1
LAYER_EFFECT = 2
LAYER_OVERRIDE = 3
LAYER_BY_NAME = {"base": LAYER_BASE, "show": LAYER_SHOW, "effect": LAYER_EFFECT, "override": LAYER_OVERRIDE}
LAYER_NAMES = {v: k for k, v in LAYER_BY_NAME.items()}

SEQUENCE_FORMAT = 1
DEFAULT_SEQUENCE_FPS = 20
MAX_FPS = 30
SLEW_RATE = 0.05          # set_position corrects at most 5% faster or slower than real time
SLEW_MAX_MS = 250         # larger offsets jump instead of slewing
EFFECT_QUEUE_MAX = 10
TICK_MS = 5               # compositor resolution; sends happen only when a light's value changes

OFF_BYTES = [120, 129, 1, 2, 252]


# ============================================================================
# SMALL HELPERS
# ============================================================================

def _scaleBri(value, scale):
    return max(0, min(100, int(value * scale)))


def _scaled(params, scale):
    out = dict(params)
    if "bri" in out:
        out["bri"] = _scaleBri(out["bri"], scale)
    return out


def _lerpHSI(p, q, t):
    # Same arithmetic as the v1.3.0 engine's interpolateHSI, so animation fades match it
    h1, s1, b1 = p.get("hue", 0), p.get("sat", 100), p.get("bri", 100)
    h2, s2, b2 = q.get("hue", 0), q.get("sat", 100), q.get("bri", 100)
    diff = (h2 - h1 + 540) % 360 - 180
    return int((h1 + diff * t) % 360), int(s1 + (s2 - s1) * t), int(b1 + (b2 - b1) * t)


def _lerpCCT(p, q, t):
    t1, b1 = p.get("temp", 56), p.get("bri", 100)
    t2, b2 = q.get("temp", 56), q.get("bri", 100)
    return int(t1 + (t2 - t1) * t), int(b1 + (b2 - b1) * t)


def bytesToCommand(byteVal):
    """Turn a stored light byte value back into an animation-style command, for fades
    that start from the base state. Returns None for values that can't be faded from."""
    if not isinstance(byteVal, (list, tuple)) or len(byteVal) < 4:
        return None
    if byteVal[0] == 0 or (byteVal[1] == 129 and byteVal[3] == 2):
        return {"mode": "OFF"}  # a leading 0 is how snapshot presets mark a light as off
    if len(byteVal) < 5:
        return None
    if byteVal[1] == 135:
        return {"mode": "CCT", "bri": byteVal[3], "temp": byteVal[4]}
    if byteVal[1] == 134 and len(byteVal) >= 7:
        return {"mode": "HSI", "hue": byteVal[3] + (byteVal[4] << 8), "sat": byteVal[5], "bri": byteVal[6]}
    if byteVal[1] == 136:
        return {"mode": "ANM", "bri": byteVal[3], "scene": byteVal[4]}
    return None


def kelvinToRGB(kelvin):
    """Approximate colour of a white light at a colour temperature (Tanner Helland's fit
    to blackbody data), as 0-255 floats. Good enough for a preview, not for colour work."""
    t = max(1000, min(40000, kelvin)) / 100.0
    if t <= 66:
        r = 255.0
        g = 99.4708025861 * math.log(t) - 161.1195681661
        b = 0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    else:
        r = 329.698727446 * ((t - 60) ** -0.1332047592)
        g = 288.1221695283 * ((t - 60) ** -0.0755148492)
        b = 255.0
    return tuple(max(0.0, min(255.0, c)) for c in (r, g, b))


def commandToRGB(cmd):
    """Approximate on-screen colour of a light command, brightness included, as an (r, g, b)
    tuple of ints, or None when the colour isn't known (a bare ON). Brightness goes through a
    2.2 gamma so a light at 20% still reads as clearly lit, roughly as it looks in a room."""
    if not cmd:
        return None
    mode = str(cmd.get("mode", "")).upper()
    if mode == "OFF":
        return (0, 0, 0)
    level = (max(0, min(100, cmd.get("bri", 100))) / 100.0) ** (1 / 2.2)
    if mode == "HSI":
        h = (cmd.get("hue", 0) % 360) / 60.0
        sat = max(0, min(100, cmd.get("sat", 100))) / 100.0
        c = sat
        x = c * (1 - abs(h % 2 - 1))
        r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][int(h) % 6]
        m = 1 - c
        rgb = ((r + m) * 255, (g + m) * 255, (b + m) * 255)
    elif mode == "CCT":
        rgb = kelvinToRGB(cmd.get("temp", 56) * 100)
    elif mode == "ANM":
        rgb = (200.0, 200.0, 200.0)  # scene colours come from the light's firmware; unknown here
    else:
        return None
    return tuple(int(round(c * level)) for c in rgb)


def rgbHex(rgb):
    return "#%02x%02x%02x" % tuple(rgb) if rgb is not None else None


def buildKeyMap(keys, resolver, targetIdx=None):
    """Map animation light keys to light indices.

    Without a target, each key resolves as it always has ("*", ID, name, MAC, @role).
    With a target (an ordered list of indices), "*" means the whole target, numeric
    keys are positions within the target (clip light "1" is the first target light,
    repeating when the target has more lights than the clip has numbered keys), and
    any other key only counts where it lands inside the target.
    """
    keyMap = {}
    if targetIdx is None:
        for k in keys:
            keyMap[k] = list(resolver(k))
        return keyMap

    targetSet = set(targetIdx)
    numeric = sorted({int(k) for k in keys if str(k).isdigit()})
    for k in keys:
        ks = str(k)
        if ks in ("*", "-1") or ks.lower() == "all":
            keyMap[k] = list(targetIdx)
        elif ks.isdigit():
            n = int(ks)
            keyMap[k] = [targetIdx[j] for j in range(len(targetIdx)) if numeric[j % len(numeric)] == n]
        else:
            keyMap[k] = [i for i in resolver(ks) if i in targetSet]
    return keyMap


# ============================================================================
# ANIMATION TIMELINE
# ============================================================================

class _Segment:
    __slots__ = ("start", "fadeDur", "steps", "holdDur", "kf", "prev", "snapBefore")


class AnimationTimeline:
    """Evaluates an animation at any time offset instead of stepping through sleeps.

    legacy=True reproduces the v1.3.0 engine's timing rules exactly (holds floored to
    50 ms ticks with a 50 ms minimum, fades in whole steps of the rate interval, the
    loop-wrap fade), without its accumulated drift. legacy=False is used for clips in
    sequences: exact durations and continuous fades, sampled at the sequence frame rate.
    """

    def __init__(self, anim, speed=1.0, fps=5, briScale=1.0, loop=None, maxLoops=0, legacy=True):
        self.keyframes = anim.get("keyframes", []) or []
        self.loop = bool(anim.get("loop", False) if loop is None else loop)
        self.maxLoops = max(0, int(maxLoops or 0))
        try:
            speed = float(speed)
        except (TypeError, ValueError):
            speed = 1.0
        self.speed = speed if speed > 0 else 1.0
        self.stepMs = max(33, int(1000 / max(1, int(fps))))
        self.briScale = briScale
        self.legacy = legacy

        self.pass0, self.d0, endSnap = self._buildPass(True, {})
        self.endSnap = endSnap
        if self.loop and self.keyframes:
            self.passL, self.dL, _ = self._buildPass(False, endSnap)
            if self.dL <= 0:
                self.dL = 1.0
        else:
            self.passL, self.dL = None, 0.0
        self.starts0 = [s.start for s in self.pass0]
        self.startsL = [s.start for s in self.passL] if self.passL else []

    def _timing(self, kf, isWrapFrame):
        hold = kf.get("hold_ms", 200)
        fade = kf.get("fade_ms", 0)
        if self.legacy:
            holdMs = max(50, int(hold / self.speed))
            holdDur = max(1, holdMs // 50) * 50
            fadeMs = max(0, int(fade / self.speed))
            if isWrapFrame and fadeMs == 0:
                lastFade = self.keyframes[-1].get("fade_ms", 0)
                if lastFade > 0:
                    fadeMs = max(0, int(lastFade / self.speed))
            steps = max(1, fadeMs // self.stepMs) if fadeMs > 0 else 0
            return steps * self.stepMs, steps, holdDur
        holdDur = max(0.0, hold / self.speed)
        fadeDur = max(0.0, fade / self.speed)
        if isWrapFrame and fadeDur == 0:
            fadeDur = max(0.0, self.keyframes[-1].get("fade_ms", 0) / self.speed)
        return fadeDur, 0, holdDur

    def _buildPass(self, first, startSnap):
        segs = []
        t = 0.0
        snap = dict(startSnap)
        n = len(self.keyframes)
        for i, kf in enumerate(self.keyframes):
            prev = None if (first and i == 0) else (i - 1 if i > 0 else n - 1)
            fadeDur, steps, holdDur = self._timing(kf, (not first) and i == 0)
            if prev is None:
                fadeDur, steps = 0, 0  # nothing to fade from on the very first frame
            seg = _Segment()
            seg.start, seg.fadeDur, seg.steps, seg.holdDur = t, fadeDur, steps, holdDur
            seg.kf, seg.prev, seg.snapBefore = i, prev, dict(snap)
            segs.append(seg)
            for key, params in kf.get("lights", {}).items():
                snap.pop(key, None)  # re-insert so later keys override earlier ones, as frames did
                snap[key] = _scaled(params, self.briScale)
            t += fadeDur + holdDur
        return segs, t, snap

    @property
    def duration(self):
        """Total length in ms, or None when it loops forever."""
        if not self.keyframes:
            return 0
        if not self.loop:
            return self.d0
        if self.maxLoops > 0:
            return self.d0 + (self.maxLoops - 1) * self.dL
        return None

    def frameAt(self, t):
        """Return (state, finished, keyframeIndex), where state maps light key to command."""
        if not self.keyframes:
            return {}, True, -1
        if t < 0:
            t = 0
        if t < self.d0:
            state, kfi = self._evalPass(self.pass0, self.starts0, t)
            return state, False, kfi
        if not self.loop:
            return dict(self.endSnap), True, len(self.keyframes) - 1
        n = int((t - self.d0) // self.dL)
        if self.maxLoops > 0 and 1 + n >= self.maxLoops:
            return dict(self.endSnap), True, len(self.keyframes) - 1
        local = (t - self.d0) - n * self.dL
        state, kfi = self._evalPass(self.passL, self.startsL, local)
        return state, False, kfi

    def _evalPass(self, segs, starts, local):
        seg = segs[max(0, bisect.bisect_right(starts, local) - 1)]
        kf = self.keyframes[seg.kf]
        state = dict(seg.snapBefore)
        within = local - seg.start
        lights = kf.get("lights", {})

        if seg.fadeDur > 0 and within < seg.fadeDur:
            if self.legacy:
                k = int(within // self.stepMs)
                t = (k + 1) / seg.steps
                lastStep = k >= seg.steps - 1
            else:
                t = within / seg.fadeDur
                lastStep = False
            prevLights = self.keyframes[seg.prev].get("lights", {})
            for key, target in lights.items():
                mode = target.get("mode", "HSI").upper()
                prevP = prevLights.get(key, target)
                prevMode = prevP.get("mode", mode).upper()
                if mode == prevMode == "HSI":
                    h, s, b = _lerpHSI(prevP, target, t)
                    cmd = {"mode": "HSI", "hue": h, "sat": s, "bri": _scaleBri(b, self.briScale)}
                elif mode == prevMode == "CCT":
                    temp, b = _lerpCCT(prevP, target, t)
                    cmd = {"mode": "CCT", "temp": temp, "bri": _scaleBri(b, self.briScale)}
                elif lastStep:
                    cmd = _scaled(target, self.briScale)
                else:
                    continue  # different modes can't blend; the light changes at the end of the fade
                state.pop(key, None)
                state[key] = cmd
        else:
            for key, target in lights.items():
                state.pop(key, None)
                state[key] = _scaled(target, self.briScale)
        return state, seg.kf


# ============================================================================
# PLAYERS
# ============================================================================

class AnimationPlayer:
    """An animation on one layer. Times are monotonic milliseconds."""
    kind = "animation"

    def __init__(self, name, timeline, resolver, target=None, revert=None, maxMs=None,
                 parallel=True, legacy=False):
        self.name = name
        self.timeline = timeline
        self.resolver = resolver
        self.target = target          # target string, or None for the animation's own keys
        self.revert = revert          # None = read the global "revert on finish" when it ends
        self.maxMs = maxMs            # cap for effects that would otherwise loop forever
        self.parallel = parallel
        self.legacy = legacy
        self.startMs = 0.0
        self.carry = {}               # lights a chained predecessor left on its last frame
        self.lastOut = {}
        self.kfIndex = -1
        self._keys = []
        for kf in timeline.keyframes:
            for k in kf.get("lights", {}):
                if k not in self._keys:
                    self._keys.append(k)
        self.refreshMap()

    def refreshMap(self):
        targetIdx = self.resolver(self.target) if self.target else None
        self.keyMap = buildKeyMap(self._keys, self.resolver, targetIdx)

    def start(self, nowMs):
        self.startMs = nowMs

    def elapsed(self, nowMs):
        return nowMs - self.startMs

    def frame(self, nowMs):
        t = nowMs - self.startMs
        state, finished, self.kfIndex = self.timeline.frameAt(t)
        if self.maxMs is not None and t >= self.maxMs:
            finished = True
        out = dict(self.carry)
        for key, cmd in state.items():
            for idx in self.keyMap.get(key, ()):
                out[idx] = cmd
        self.lastOut = out
        return out, finished

    def describe(self, nowMs):
        return {"type": "animation", "name": self.name, "elapsed_ms": int(self.elapsed(nowMs)),
                "keyframe": self.kfIndex + 1, "keyframes": len(self.timeline.keyframes)}


class SequenceClock:
    """Sequence position from a monotonic anchor; never accumulates sleep error."""

    def __init__(self):
        self.basePos = 0.0
        self.anchor = 0.0
        self.playing = False
        self.slewTotal = 0.0
        self.slewStart = 0.0

    def position(self, nowMs):
        if not self.playing:
            return self.basePos
        pos = self.basePos + (nowMs - self.anchor)
        if self.slewTotal:
            done = min(abs(self.slewTotal), (nowMs - self.slewStart) * SLEW_RATE)
            pos += done if self.slewTotal > 0 else -done
        return pos

    def _rebase(self, nowMs):
        self.basePos = self.position(nowMs)
        self.anchor = nowMs
        self.slewTotal = 0.0

    def start(self, nowMs, posMs=0.0):
        self.basePos, self.anchor, self.playing, self.slewTotal = float(posMs), nowMs, True, 0.0

    def pause(self, nowMs):
        self._rebase(nowMs)
        self.playing = False

    def resume(self, nowMs):
        self.anchor = nowMs
        self.playing = True

    def seek(self, nowMs, posMs):
        self.basePos, self.anchor, self.slewTotal = float(posMs), nowMs, 0.0

    def setPosition(self, nowMs, posMs):
        """Slew gently for small offsets (RockSniffer jitter), jump for large ones."""
        offset = posMs - self.position(nowMs)
        if not self.playing or abs(offset) > SLEW_MAX_MS:
            self.seek(nowMs, posMs)
            return "jump"
        self._rebase(nowMs)
        self.slewTotal = offset
        self.slewStart = nowMs
        return "slew"


class Cue:
    __slots__ = ("index", "at", "dur", "target", "kind", "clipName", "fit", "brightness",
                 "speed", "state", "fade", "raw")


class Sequence:
    __slots__ = ("name", "duration", "fps", "end", "pausemode", "oninterrupt", "cues", "raw")


class SequencePlayer:
    kind = "sequence"
    parallel = True
    revert = True

    def __init__(self, seq, resolver, clipLookup, baseCmd):
        self.seq = seq
        self.name = seq.name
        self.resolver = resolver
        self.clipLookup = clipLookup
        self.baseCmd = baseCmd
        self.clock = SequenceClock()
        self.userPaused = False
        self.autoPaused = False
        self.frameMs = 1000.0 / seq.fps
        self.lastOut = {}
        self.maxMs = None
        self._tickCache = {}
        self._fromCache = {}
        self.timelines = {}
        for cue in seq.cues:
            if cue.kind == "clip":
                anim = clipLookup(cue.clipName)
                if anim is not None:
                    self.timelines[cue.index] = AnimationTimeline(
                        anim, speed=cue.speed if cue.fit == "loop" else 1.0, fps=seq.fps,
                        briScale=cue.brightness / 100.0, loop=(cue.fit == "loop"), legacy=False)
        self.refreshMap()

    def refreshMap(self):
        self.cueTargets = {}
        self.clipMaps = {}
        self.lightCues = {}
        for cue in self.seq.cues:
            targetIdx = self.resolver(cue.target)
            self.cueTargets[cue.index] = targetIdx
            if cue.kind == "clip":
                tl = self.timelines.get(cue.index)
                if tl is None:
                    continue
                keys = []
                for kf in tl.keyframes:
                    for k in kf.get("lights", {}):
                        if k not in keys:
                            keys.append(k)
                self.clipMaps[cue.index] = buildKeyMap(keys, self.resolver, targetIdx)
            for idx in targetIdx:
                self.lightCues.setdefault(idx, []).append(cue)
        for idx in self.lightCues:
            self.lightCues[idx].sort(key=lambda c: (c.at, c.index))
        self._fromCache = {}
        self._precomputeFades()

    def _precomputeFades(self):
        # Chronological order keeps every lookup one level deep (earlier fades are cached).
        for idx, cues in self.lightCues.items():
            for cue in cues:
                if cue.kind == "state" and cue.fade > 0:
                    self._fromState(cue, idx)

    def _fromState(self, cue, idx):
        key = (cue.index, idx)
        if key not in self._fromCache:
            v = self._evalLight(idx, cue.at - 1) if cue.at > 0 else None
            self._fromCache[key] = v if v is not None else self.baseCmd(idx)
        return self._fromCache[key]

    def _stepped(self, elapsed):
        # Progress inside a cue moves in whole frames counted from the cue's own start, so
        # cue onsets land on time while fades still send at the sequence frame rate
        return int(elapsed // self.frameMs) * self.frameMs

    def _clipFrame(self, cue, pos):
        ck = (cue.index, self._stepped(pos - cue.at))
        if ck in self._tickCache:
            return self._tickCache[ck]
        tl = self.timelines.get(cue.index)
        out = {}
        if tl is not None:
            tau = self._stepped(pos - cue.at)
            if cue.fit == "stretch":
                tau = tau * (tl.d0 / cue.dur) if cue.dur > 0 else 0
            state, _, _ = tl.frameAt(tau)
            keyMap = self.clipMaps.get(cue.index, {})
            for key, cmd in state.items():
                for i in keyMap.get(key, ()):
                    out[i] = cmd
        self._tickCache[ck] = out
        return out

    def _evalLight(self, idx, pos):
        cues = self.lightCues.get(idx)
        if not cues:
            return None
        hi = bisect.bisect_right([c.at for c in cues], pos)
        for cue in reversed(cues[:hi]):
            if cue.dur > 0 and pos >= cue.at + cue.dur:
                continue
            if cue.kind == "clip":
                v = self._clipFrame(cue, pos).get(idx)
                if v is None:
                    continue  # the clip doesn't use this light; look further back
                return v
            target = cue.state
            if cue.fade > 0 and pos < cue.at + cue.fade:
                frm = self._fromState(cue, idx)
                if frm is not None and frm.get("mode") == target["mode"] and target["mode"] in ("HSI", "CCT"):
                    t = self._stepped(pos - cue.at) / cue.fade
                    if target["mode"] == "HSI":
                        h, s, b = _lerpHSI(frm, target, t)
                        return {"mode": "HSI", "hue": h, "sat": s, "bri": b}
                    temp, b = _lerpCCT(frm, target, t)
                    return {"mode": "CCT", "temp": temp, "bri": b}
            return dict(target)
        return None

    @property
    def state(self):
        if self.userPaused or self.autoPaused:
            return "paused"
        return "playing"

    def start(self, nowMs, posMs=0.0):
        self.clock.start(nowMs, posMs)

    def position(self, nowMs):
        return max(0.0, self.clock.position(nowMs))

    def frame(self, nowMs):
        pos = self.position(nowMs)
        if pos >= self.seq.duration:
            return dict(self.lastOut), True
        if self.userPaused and self.seq.pausemode == "revert":
            self.lastOut = {}
            return {}, False
        self._tickCache = {}
        out = {}
        for idx in self.lightCues:
            v = self._evalLight(idx, pos)
            if v is not None:
                out[idx] = v
        self.lastOut = out
        return out, False

    def describe(self, nowMs):
        return {"type": "sequence", "name": self.name, "state": self.state,
                "position_ms": int(self.position(nowMs)), "duration_ms": int(self.seq.duration)}


# ============================================================================
# SEQUENCE PARSING AND VALIDATION
# ============================================================================

def _num(v, name, lo, hi, errors, where, default=None, integer=True):
    if v is None:
        if default is None:
            errors.append(where + ": '" + name + "' is required")
        return default
    try:
        n = int(v) if integer else float(v)
    except (TypeError, ValueError):
        errors.append(where + ": '" + name + "' must be a number, got " + repr(v))
        return default
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        errors.append(where + ": '" + name + "' must be between " + str(lo) + " and " + str(hi) + ", got " + str(n))
        return default
    return n


def parseSequence(data, clipExists, defaultFps=DEFAULT_SEQUENCE_FPS, resolveTarget=None):
    """Validate a sequence dict. Returns (Sequence or None, errors, warnings).

    Error messages name the cue and field so a generator can fix them. Keys this
    version doesn't use (tempo, palette, sections, notes, per-cue palette) are kept
    in .raw and otherwise ignored.
    """
    errors, warnings = [], []
    if not isinstance(data, dict):
        return None, ["sequence must be a JSON object"], []

    seq = Sequence()
    seq.raw = data
    fmt = data.get("format", SEQUENCE_FORMAT)
    if fmt != SEQUENCE_FORMAT:
        errors.append("format " + repr(fmt) + " is not supported (this version reads format " + str(SEQUENCE_FORMAT) + ")")
    seq.name = str(data.get("name", "")).strip()
    if not seq.name:
        errors.append("'name' is required")
    seq.duration = _num(data.get("duration_ms"), "duration_ms", 1, 24 * 3600 * 1000, errors, "sequence")
    seq.fps = _num(data.get("fps"), "fps", 1, MAX_FPS, errors, "sequence", default=defaultFps)

    end = str(data.get("end", "revert")).lower()
    if end in ("revert", "hold") or (end.startswith("preset:") and end[7:].isdigit() and int(end[7:]) >= 1):
        seq.end = end
    else:
        errors.append("'end' must be \"revert\", \"hold\" or \"preset:N\", got " + repr(data.get("end")))
        seq.end = "revert"
    seq.pausemode = str(data.get("pause_mode", "revert")).lower()
    if seq.pausemode not in ("revert", "freeze"):
        errors.append("'pause_mode' must be \"revert\" or \"freeze\"")
        seq.pausemode = "revert"
    seq.oninterrupt = str(data.get("on_interrupt", "continue")).lower()
    if seq.oninterrupt not in ("continue", "pause"):
        errors.append("'on_interrupt' must be \"continue\" or \"pause\"")
        seq.oninterrupt = "continue"

    rawCues = data.get("cues")
    if not isinstance(rawCues, list) or not rawCues:
        errors.append("'cues' must be a non-empty list")
        rawCues = []

    seq.cues = []
    for i, rc in enumerate(rawCues):
        where = "cue " + str(i)
        if not isinstance(rc, dict):
            errors.append(where + ": must be an object")
            continue
        cue = Cue()
        cue.index, cue.raw = i, rc
        cue.at = _num(rc.get("at_ms"), "at_ms", 0, None, errors, where, default=0)
        cue.target = str(rc.get("target", "*")).strip() or "*"
        cue.state, cue.clipName, cue.fade = None, None, 0
        cue.fit, cue.brightness, cue.speed = "stretch", 100, 1.0
        hasClip, hasState = "clip" in rc, "state" in rc
        if hasClip == hasState:
            errors.append(where + ": needs exactly one of 'clip' or 'state'")
            continue
        if seq.duration is not None and cue.at >= seq.duration:
            warnings.append(where + ": at_ms " + str(cue.at) + " is past the end of the sequence, it will never play")

        if hasClip:
            cue.kind = "clip"
            clip = rc["clip"]
            if isinstance(clip, str):
                clip = {"name": clip}
            if not isinstance(clip, dict) or not str(clip.get("name", "")).strip():
                errors.append(where + ": 'clip' needs a 'name' (an animation name)")
                continue
            cue.clipName = str(clip["name"]).strip()
            if not clipExists(cue.clipName):
                errors.append(where + ": no animation named " + repr(cue.clipName))
            cue.fit = str(clip.get("fit", "stretch")).lower()
            if cue.fit not in ("stretch", "loop"):
                errors.append(where + ": clip 'fit' must be \"stretch\" or \"loop\"")
            cue.brightness = _num(clip.get("brightness"), "brightness", 0, 100, errors, where, default=100)
            cue.speed = _num(clip.get("speed"), "speed", 0.05, 20, errors, where, default=1.0, integer=False)
            cue.dur = _num(rc.get("duration_ms"), "duration_ms", 1, None, errors, where)
        else:
            cue.kind = "state"
            st = rc["state"]
            if not isinstance(st, dict):
                errors.append(where + ": 'state' must be an object")
                continue
            mode = str(st.get("mode", "")).upper()
            if mode == "HSI":
                cue.state = {"mode": "HSI",
                             "hue": _num(st.get("hue"), "hue", 0, 360, errors, where, default=0),
                             "sat": _num(st.get("sat"), "sat", 0, 100, errors, where, default=100),
                             "bri": _num(st.get("bri"), "bri", 0, 100, errors, where, default=100)}
            elif mode == "CCT":
                cue.state = {"mode": "CCT",
                             "temp": _num(st.get("temp"), "temp", 32, 85, errors, where, default=56),
                             "bri": _num(st.get("bri"), "bri", 0, 100, errors, where, default=100)}
            else:
                errors.append(where + ": state 'mode' must be \"HSI\" or \"CCT\"")
                continue
            cue.fade = _num(st.get("fade_ms", rc.get("fade_ms")), "fade_ms", 0, None, errors, where, default=0)
            cue.dur = _num(rc.get("duration_ms"), "duration_ms", 0, None, errors, where, default=0)

        if resolveTarget is not None and not resolveTarget(cue.target):
            warnings.append(where + ": target " + repr(cue.target) + " matches no light right now")
        seq.cues.append(cue)

    if errors:
        return None, errors, warnings
    return seq, errors, warnings


# ============================================================================
# COMPOSITOR
# ============================================================================

class ShowCompositor:
    """Owns every player, arbitrates layers per light, and queues writes for the worker.

    All state sits behind one re-entrant lock. Commands run under it and then tick
    once, so a stop has already released its lights when the call returns (the HTTP
    and GUI code relies on that, as it relied on stopAnimation() waiting before).
    """

    def __init__(self, hooks, clock=time.monotonic):
        self.hooks = hooks
        self.clock = clock
        self.lock = threading.RLock()
        self.layers = {LAYER_SHOW: None, LAYER_EFFECT: None, LAYER_OVERRIDE: None}
        self.effectQueue = []
        self.owner = {}       # idx -> layer driving it
        self.baseStates = {}  # idx -> bytes to restore when no layer drives it
        self.lastSent = {}    # idx -> bytes this compositor last queued
        self.lastCmd = {}
        self.mailbox = {}     # idx -> (bytes, parallel)
        self.released = {}   # idx -> base bytes just restored, until a base write replaces them
        self._deferred = []
        self._lightCount = None
        self._thread = None
        self._running = False
        self._wake = threading.Event()

    # ---------------------------------------------------------------- thread
    def startThread(self):
        if self._thread is not None:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="showCompositor", daemon=True)
        self._thread.start()

    def stopThread(self):
        self._running = False
        self._wake.set()

    def _run(self):
        period = TICK_MS / 1000.0
        nextT = self.clock()
        while self._running:
            if not self.anyActive():
                self._wake.wait()
                self._wake.clear()
                nextT = self.clock()
                continue
            now = self.clock()
            self.tick(now)
            nextT += period
            if nextT < now:
                nextT = now + period  # skipped ticks are not replayed; positions come from the clock
            delay = nextT - self.clock()
            if delay > 0:
                time.sleep(delay)  # time.sleep is high resolution on Windows from Python 3.11

    def tick(self, now=None):
        with self.lock:
            self._tickLocked(self.clock() if now is None else now)
            deferred, self._deferred = self._deferred, []
        for fn in deferred:
            fn()

    def _nowMs(self, now):
        return now * 1000.0

    # -------------------------------------------------------------- commands
    def _command(self, fn, now=None):
        now = self.clock() if now is None else now
        with self.lock:
            result = fn(self._nowMs(now))
            self._tickLocked(now)
            deferred, self._deferred = self._deferred, []
        for d in deferred:
            d()
        self._wake.set()
        return result

    def playAnimation(self, player, layer, queueMode="queue", now=None):
        """Start an AnimationPlayer. Returns "playing", "queued" or "queue_full"."""
        def run(nowMs):
            if layer == LAYER_EFFECT and queueMode != "replace" and self.layers[LAYER_EFFECT] is not None:
                if len(self.effectQueue) >= EFFECT_QUEUE_MAX:
                    return "queue_full"
                self.effectQueue.append(player)
                self._status("queued", LAYER_EFFECT, player)
                return "queued"
            old = self.layers[layer]
            if old is not None:
                if layer == LAYER_OVERRIDE:
                    # Chaining keeps the original revert target; the old animation's lights hold
                    # their last frame until the new one ends, as in v1.3.0.
                    player.carry = {i: c for i, c in old.lastOut.items()}
                    self._status("end", layer, old, reason="chained")
                else:
                    self._endPlayer(layer, old, nowMs, "replaced")
            player.start(nowMs)
            self.layers[layer] = player
            self._status("start", layer, player)
            return "playing"
        return self._command(run, now)

    def stopLayer(self, layer, clearQueue=False, now=None):
        def run(nowMs):
            stopped = False
            if layer == LAYER_EFFECT and clearQueue:
                self.effectQueue = []
            p = self.layers.get(layer)
            if p is not None:
                self._endPlayer(layer, p, nowMs, "stopped")
                stopped = True
            return stopped
        return self._command(run, now)

    def playSequence(self, player, startMs=0, now=None):
        def run(nowMs):
            old = self.layers[LAYER_SHOW]
            if old is not None:
                self._endPlayer(LAYER_SHOW, old, nowMs, "replaced")
            player.start(nowMs, startMs)
            self.layers[LAYER_SHOW] = player
            self._status("start", LAYER_SHOW, player)
            return True
        return self._command(run, now)

    def _seq(self):
        p = self.layers[LAYER_SHOW]
        return p if isinstance(p, SequencePlayer) else None

    def pauseSequence(self, now=None):
        def run(nowMs):
            p = self._seq()
            if p is None or p.userPaused:
                return False
            if not p.autoPaused:
                p.clock.pause(nowMs)
            p.userPaused = True
            self._status("pause", LAYER_SHOW, p)
            return True
        return self._command(run, now)

    def resumeSequence(self, now=None):
        def run(nowMs):
            p = self._seq()
            if p is None or not p.userPaused:
                return False
            p.userPaused = False
            if not p.autoPaused:
                p._fromCache = {}
                p._precomputeFades()  # the base may have changed while paused
                p.clock.resume(nowMs)
            self._status("resume", LAYER_SHOW, p)
            return True
        return self._command(run, now)

    def seekSequence(self, posMs, now=None):
        def run(nowMs):
            p = self._seq()
            if p is None:
                return False
            p.clock.seek(nowMs, max(0, posMs))
            return True
        return self._command(run, now)

    def setSequencePosition(self, posMs, now=None):
        def run(nowMs):
            p = self._seq()
            if p is None:
                return None
            return p.clock.setPosition(nowMs, max(0, posMs))
        return self._command(run, now)

    def stopSequence(self, now=None):
        def run(nowMs):
            p = self._seq()
            if p is None:
                return False
            self._endPlayer(LAYER_SHOW, p, nowMs, "stopped")
            return True
        return self._command(run, now)

    # ------------------------------------------------- worker-side interface
    def interceptBaseWrite(self, idx, value):
        """Called by the BLE write paths for every base-layer (non-show) write.

        Returns (blocked, shownBytes). A light a layer is driving keeps showing the
        layer; the write becomes its new revert target instead. Otherwise the write
        goes ahead and any show value still queued for that light is dropped, so a
        stale revert can't land on top of it.
        """
        with self.lock:
            if self.owner.get(idx, 0) > 0:
                if isinstance(value, (list, tuple)) and len(value) > 1:
                    self.baseStates[idx] = list(OFF_BYTES) if value[0] == 0 else list(value)
                return True, self.lastSent.get(idx)
            self.mailbox.pop(idx, None)
            self.released.pop(idx, None)
            return False, None

    def takeMailbox(self):
        with self.lock:
            box, self.mailbox = self.mailbox, {}
            return box

    def hasPending(self):
        return bool(self.mailbox)

    def anyActive(self):
        with self.lock:
            return any(p is not None for p in self.layers.values()) or bool(self.effectQueue)

    def layerActive(self, layer):
        with self.lock:
            return self.layers.get(layer) is not None

    def sequenceActive(self):
        with self.lock:
            return self._seq() is not None

    def status(self, now=None):
        now = self.clock() if now is None else now
        nowMs = self._nowMs(now)
        with self.lock:
            layers = {}
            for layer, p in self.layers.items():
                layers[LAYER_NAMES[layer]] = p.describe(nowMs) if p is not None else None
            layers["effect_queue"] = [p.name for p in self.effectQueue]
            seq = self._seq()
            return {"layers": layers,
                    "sequence": seq.describe(nowMs) if seq is not None else None,
                    "owners": dict(self.owner)}

    # --------------------------------------------------------------- internals
    def _status(self, event, layer, player, **extra):
        info = {"event": event, "layer": LAYER_NAMES[layer], "name": player.name, "kind": player.kind}
        info.update(extra)
        self._deferred.append(lambda: self.hooks.onStatus(info))

    def _endPlayer(self, layer, player, nowMs, reason):
        """Remove a player. Its lights fall to the next active layer on this tick."""
        if self.layers.get(layer) is player:
            self.layers[layer] = None
        commit = False
        if isinstance(player, SequencePlayer):
            if player.seq.end == "hold" and reason == "finished":
                commit = True
            elif player.seq.end.startswith("preset:") and reason == "finished":
                n = int(player.seq.end[7:])
                self._deferred.append(lambda: self.hooks.recallPreset(n))
        else:
            revert = player.revert if player.revert is not None else self.hooks.globalRevert()
            commit = not revert
        if commit:
            # "Don't revert": the last frame becomes the state the lights return to.
            for idx, cmd in player.lastOut.items():
                b = self.hooks.encode(idx, cmd)
                if b is not None:
                    self.baseStates[idx] = list(b)
        self._status("end", layer, player, reason=reason)
        if layer == LAYER_EFFECT and self.effectQueue and self.layers[LAYER_EFFECT] is None:
            nxt = self.effectQueue.pop(0)
            nxt.start(nowMs)
            self.layers[LAYER_EFFECT] = nxt
            self._status("start", LAYER_EFFECT, nxt)

    def _tickLocked(self, now):
        nowMs = self._nowMs(now)
        count = self.hooks.lightCount()
        if count != self._lightCount:
            self._lightCount = count
            for p in list(self.layers.values()) + self.effectQueue:
                if p is not None:
                    p.refreshMap()

        seq = self._seq()
        if seq is not None and seq.seq.oninterrupt == "pause":
            interrupted = self.layers[LAYER_EFFECT] is not None or self.layers[LAYER_OVERRIDE] is not None
            if interrupted and not seq.autoPaused:
                if not seq.userPaused:
                    seq.clock.pause(nowMs)
                seq.autoPaused = True
            elif not interrupted and seq.autoPaused:
                seq.autoPaused = False
                if not seq.userPaused:
                    seq.clock.resume(nowMs)

        frames = {}
        for layer in (LAYER_SHOW, LAYER_EFFECT, LAYER_OVERRIDE):
            p = self.layers[layer]
            if p is None:
                continue
            out, finished = p.frame(nowMs)
            if finished:
                self._endPlayer(layer, p, nowMs, "finished")
                p = self.layers[layer]
                if p is None:
                    continue
                out, finished = p.frame(nowMs)
            frames[layer] = (out, p.parallel)

        lights = set(self.owner)
        for out, _ in frames.values():
            lights.update(out)
        queued = False
        for idx in lights:
            win = 0
            if not self.hooks.isLocked(idx):
                for layer in (LAYER_OVERRIDE, LAYER_EFFECT, LAYER_SHOW):
                    if layer in frames and idx in frames[layer][0]:
                        win = layer
                        break
            prev = self.owner.get(idx, 0)
            if win > 0:
                if prev == 0 and idx not in self.baseStates:
                    # A revert queued moments ago may not have reached the light's stored value yet
                    cur = self.released.pop(idx, None) or self.hooks.currentBytes(idx)
                    if isinstance(cur, (list, tuple)) and len(cur) > 3:
                        self.baseStates[idx] = list(cur)
                self.owner[idx] = win
                out, parallel = frames[win]
                cmd = out[idx]
                if cmd != self.lastCmd.get(idx) or prev != win:
                    self.lastCmd[idx] = cmd
                    b = self.hooks.encode(idx, cmd)
                    if b is not None and b != self.lastSent.get(idx):
                        self.mailbox[idx] = (list(b), parallel)
                        self.lastSent[idx] = list(b)
                        queued = True
            elif prev > 0:
                del self.owner[idx]
                self.lastCmd.pop(idx, None)
                sent = self.lastSent.pop(idx, None)
                b = self.baseStates.pop(idx, None)
                if b is not None:
                    self.released[idx] = b
                if b is not None and b != sent:
                    self.mailbox[idx] = (b, True)
                    queued = True
                elif b is None:
                    self.mailbox.pop(idx, None)
        if queued:
            self._deferred.append(self.hooks.wake)
