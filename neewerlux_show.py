"""Show engine for NeewerLux: animation timelines, sequences and priority layers.

This module holds no BLE or Qt code. NeewerLux.py hands the compositor a hooks
object (target resolution, command encoding, current light bytes, locked
flags, worker wake-up, preset recall, status) so the same engine runs in the
GUI, in --http mode and in the offline test harness.

Layers, lowest to highest: base (0, manual and presets, owned by NeewerLux.py),
sound (1, a sound mode following live audio, a bed under everything else), show (2,
sequences or a background animation), effect (3, queued triggered effects), override
(4, the legacy one-animation-at-a-time slot). Each light is driven by the highest
layer whose current frame includes it; covered layers keep their clocks running.
"""

import bisect
import math
import random
import threading
import time

LAYER_BASE = 0
LAYER_SOUND = 1
LAYER_SHOW = 2
LAYER_EFFECT = 3
LAYER_OVERRIDE = 4
LAYER_BY_NAME = {"base": LAYER_BASE, "sound": LAYER_SOUND, "show": LAYER_SHOW, "effect": LAYER_EFFECT, "override": LAYER_OVERRIDE}
LAYER_NAMES = {v: k for k, v in LAYER_BY_NAME.items()}
LAYER_FADE = 5  # a light fading to a newly recalled preset; reported as base, not a layer you can play on
LAYER_NAMES[LAYER_FADE] = "base"

SEQUENCE_FORMAT = 1
DEFAULT_SEQUENCE_FPS = 20
MAX_FPS = 30
SLEW_RATE = 0.05          # set_position corrects at most 5% faster or slower than real time
SLEW_MAX_MS = 250         # larger offsets jump instead of slewing
EFFECT_QUEUE_MAX = 10
IDLE_TICK_MS = 100        # longest the compositor sleeps while anything plays: it also notices
                          # changes made outside it (a light connecting, Locked, positions)

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
    tuple of ints, or None when the colour isn't known (a bare ON). Brightness is compressed
    into the upper part of the range: an LED panel at 5% is still obviously lit in a room,
    so any lit light keeps at least 40% of its colour on screen and only 0% shows as dark."""
    if not cmd:
        return None
    mode = str(cmd.get("mode", "")).upper()
    if mode == "OFF":
        return (0, 0, 0)
    bri = max(0, min(100, cmd.get("bri", 100)))
    level = 0.0 if bri == 0 else 0.4 + 0.6 * (bri / 100.0) ** 0.5
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


# ============================================================================
# FLASH SAFETY (photosensitivity)
# ============================================================================
# Thresholds follow WCAG 2.x "three flashes": a flash is a pair of opposing changes in
# relative luminance of at least 10% of full, where the darker state is below 0.80, and a
# red flash is a pair of opposing transitions involving a saturated red. No more than three
# of either in any one-second period. WCAG was written for screens; a light fills more of
# the view, so these are a floor, not a guarantee. Luminance here is the colour's relative
# luminance times the brightness percentage (assumes output follows brightness).
FLASH_LIMIT_PER_SECOND = 3
FLASH_LUMINANCE_STEP = 0.10
FLASH_DARK_CEILING = 0.80
# The guard counts over a slightly longer window than a second: Bluetooth delivery jitters
# by a few tens of milliseconds, and the limit has to hold for what the light shows.
GUARD_WINDOW_S = 1.15


def _linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def flashLevel(cmd):
    """(relative luminance 0-1, is saturated red) for a light command, or None if unknown.
    Scenes run inside the light's firmware and can't be measured, so they read as None."""
    if not cmd:
        return None
    mode = str(cmd.get("mode", "")).upper()
    if mode == "OFF":
        return (0.0, False)
    bri = max(0, min(100, cmd.get("bri", 100))) / 100.0
    if mode == "HSI":
        h = (cmd.get("hue", 0) % 360) / 60.0
        sat = max(0, min(100, cmd.get("sat", 100))) / 100.0
        x = sat * (1 - abs(h % 2 - 1))
        r, g, b = [(sat, x, 0), (x, sat, 0), (0, sat, x), (0, x, sat), (x, 0, sat), (sat, 0, x)][int(h) % 6]
        m = 1 - sat
        rgb = ((r + m) * 255, (g + m) * 255, (b + m) * 255)
        hue = cmd.get("hue", 0) % 360
        red = (hue <= 20 or hue >= 340) and sat >= 0.8 and bri >= 0.2
    elif mode == "CCT":
        rgb = kelvinToRGB(cmd.get("temp", 56) * 100)
        red = False
    else:
        return None
    lum = 0.2126 * _linear(rgb[0]) + 0.7152 * _linear(rgb[1]) + 0.0722 * _linear(rgb[2])
    return (lum * bri, red)


class FlashCounter:
    """Counts flashes for one light from a stream of (time, level) samples, the way the
    guard and the content checks both see them: luminance transitions are tracked as
    swings from the last turning point, so a slow fade counts once when it completes."""

    def __init__(self):
        self.lastLum = None
        self.anchor = None       # luminance at the last turning point
        self.direction = 0       # +1 rising, -1 falling, 0 unknown
        self.transitions = []    # times of counted luminance transitions
        self.lastRed = None
        self.redTransitions = []

    def _wouldTransition(self, lum):
        """The transition direction lum would complete from the current anchor, or 0."""
        if self.anchor is None:
            return 0
        delta = lum - self.anchor
        if abs(delta) >= FLASH_LUMINANCE_STEP and min(lum, self.anchor) < FLASH_DARK_CEILING:
            return 1 if delta > 0 else -1
        return 0

    def check(self, t, level, limit=FLASH_LIMIT_PER_SECOND, window=1.0, paced=False):
        """True if moving to level at time t would exceed the limit in the last window.
        paced: also keep transitions evenly spaced (at least window / (2 x limit) apart), so a
        fast strobe is spread out into a slower, even one instead of bursts and pauses."""
        if level is None:
            return False
        lum, red = level
        gap = window / (2.0 * limit)
        d = self._wouldTransition(lum)
        if d and d != self.direction:
            recent = [x for x in self.transitions if t - x < window]
            if (len(recent) + 1) / 2.0 > limit:
                return True
            if paced and self.transitions and t - self.transitions[-1] < gap:
                return True
        if self.lastRed is not None and red != self.lastRed:
            recent = [x for x in self.redTransitions if t - x < window]
            if (len(recent) + 1) / 2.0 > limit:
                return True
            if paced and self.redTransitions and t - self.redTransitions[-1] < gap:
                return True
        return False

    def add(self, t, level):
        if level is None:
            return
        lum, red = level
        if self.anchor is None:
            self.anchor, self.lastLum, self.lastRed = lum, lum, red
            return
        d = self._wouldTransition(lum)
        if d:
            if d != self.direction:
                self.transitions.append(t)
                self.direction = d
            self.anchor = lum
        elif self.direction and (lum - self.anchor) * self.direction > 0:
            self.anchor = lum  # still moving the same way: extend the swing
        if self.lastRed is not None and red != self.lastRed:
            self.redTransitions.append(t)
        self.lastLum, self.lastRed = lum, red
        cutoff = t - 2.0
        self.transitions = [x for x in self.transitions if x >= cutoff]
        self.redTransitions = [x for x in self.redTransitions if x >= cutoff]

    @staticmethod
    def worstRate(times):
        """Most flashes (transition pairs) in any one-second window of a list of times."""
        times = sorted(times)
        best, j = 0, 0
        for i in range(len(times)):
            while times[i] - times[j] >= 1.0:
                j += 1
            best = max(best, i - j + 1)
        return best / 2.0


def analyzeFlashes(samples):
    """samples: list of (time_s, cmd) for one light, in time order. Returns
    {"flashes": worst flashes in any second, "red": worst red flashes in any second}."""
    counter = FlashCounter()
    allLum, allRed = [], []
    for t, cmd in samples:
        level = flashLevel(cmd)
        before, beforeRed = len(counter.transitions), len(counter.redTransitions)
        counter.add(t, level)
        allLum += counter.transitions[before:] if len(counter.transitions) > before else []
        allRed += counter.redTransitions[beforeRed:] if len(counter.redTransitions) > beforeRed else []
    return {"flashes": FlashCounter.worstRate(allLum), "red": FlashCounter.worstRate(allRed)}


class FlashGuard:
    """Runtime limit applied to what is actually sent to each light. A frame that would
    push a light past the limit, or come sooner than an even spacing allows, is held back
    (the light keeps its last value until a frame is allowed), so a fast strobe becomes a
    slower, even one rather than bursts of three with pauses between."""

    def __init__(self, limit=FLASH_LIMIT_PER_SECOND, clock=None):
        import time as _time
        self.limit = limit
        self.clock = clock or _time.monotonic
        self.counters = {}
        self.held = 0

    def allow(self, key, cmd, current=None):
        """current: what the light shows now, used the first time a light is seen so the
        first change counts against it."""
        level = flashLevel(cmd)
        t = self.clock()
        counter = self.counters.get(key)
        if counter is None:
            counter = self.counters[key] = FlashCounter()
            counter.add(t - 10.0, flashLevel(current))
        if counter.check(t, level, self.limit, GUARD_WINDOW_S, paced=True):
            self.held += 1
            return False
        counter.add(t, level)
        return True

    def forget(self, key):
        self.counters.pop(key, None)


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

KEYFRAME_MODES = ("HSI", "CCT", "ANM", "ON", "OFF")
MODE_ALIASES = {"SCENE": "ANM", "SCN": "ANM"}  # what the README, HTTP commands and the editor call scenes


def _normaliseKeyframe(kf):
    """A keyframe with mode aliases ("SCENE") spelled the way the engine expects ("ANM")."""
    if not isinstance(kf, dict) or not isinstance(kf.get("lights"), dict):
        return kf
    if not any(isinstance(p, dict) and str(p.get("mode", "")).upper() in MODE_ALIASES for p in kf["lights"].values()):
        return kf
    out = dict(kf)
    out["lights"] = {key: (dict(p, mode=MODE_ALIASES[str(p.get("mode", "")).upper()])
                           if isinstance(p, dict) and str(p.get("mode", "")).upper() in MODE_ALIASES else p)
                     for key, p in kf["lights"].items()}
    return out


def animationErrors(anim):
    """Problems that would make parts of an animation silently do nothing: a light entry
    without a mode, or with a mode lights don't understand. Scenes can be "ANM" or "SCENE"."""
    errors = []
    tags = anim.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) and t.strip() for t in tags):
        errors.append("\"tags\" must be a list of words")
    for i, kf in enumerate(anim.get("keyframes", []) or []):
        if not isinstance(kf, dict):
            errors.append("keyframe %d isn't an object" % (i + 1))
            continue
        lights = kf.get("lights", {})
        if not isinstance(lights, dict):
            errors.append("keyframe %d: \"lights\" must be an object" % (i + 1))
            continue
        for key, params in lights.items():
            mode = str(params.get("mode", "")).upper() if isinstance(params, dict) else ""
            mode = MODE_ALIASES.get(mode, mode)
            if mode not in KEYFRAME_MODES:
                errors.append("keyframe %d, light %r: mode %r isn't one of HSI, CCT, SCENE (or ANM), ON, OFF"
                              % (i + 1, key, params.get("mode") if isinstance(params, dict) else params))
    return errors


class _Segment:
    __slots__ = ("start", "fadeDur", "steps", "holdDur", "kf", "prev", "snapBefore")


class AnimationTimeline:
    """Evaluates an animation at any time offset instead of stepping through sleeps.

    Holds and fades last exactly as long as the file says (divided by the speed).
    stepped=True is for animations played on their own: a fade moves in whole steps of
    the rate interval (fps updates a second), so the rate keeps limiting Bluetooth writes.
    Without it (clips in sequences) fades are continuous, sampled at the sequence frame rate.
    legacy=True reproduces the v1.3.0 engine's rounding (holds floored to 50 ms ticks with
    a 50 ms minimum, fades a whole number of 1/fps steps long); NeewerLux itself stopped
    using it in 1.3.3, and tests/test_timeline.py keeps it checked against a v1.3.0 replay.
    """

    def __init__(self, anim, speed=1.0, fps=5, briScale=1.0, loop=None, maxLoops=0, legacy=False, stepped=False):
        self.keyframes = [_normaliseKeyframe(k) for k in (anim.get("keyframes", []) or [])]
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
        self.stepped = stepped

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
        steps = max(1, int(fadeDur // self.stepMs)) if (self.stepped and fadeDur > 0) else 0
        return fadeDur, steps, holdDur

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

    def nextChange(self, t):
        """The first time after t at which frameAt can return something different, or None
        when it never will (finished, or holding its last frame)."""
        if not self.keyframes:
            return None
        if t < 0:
            return 0.0
        if t < self.d0:
            return self._nextInPass(self.pass0, self.starts0, t, 0.0)
        if not self.loop:
            return None
        n = int((t - self.d0) // self.dL)
        if self.maxLoops > 0 and 1 + n >= self.maxLoops:
            return None
        base = self.d0 + n * self.dL
        return self._nextInPass(self.passL, self.startsL, t - base, base)

    def _nextInPass(self, segs, starts, local, base):
        seg = segs[max(0, bisect.bisect_right(starts, local) - 1)]
        within = local - seg.start
        if seg.fadeDur > 0 and within < seg.fadeDur:
            if not seg.steps:
                return base + local + self.stepMs  # continuous: whoever samples it decides the rate
            step = seg.fadeDur / seg.steps
            return base + seg.start + (int(within // step) + 1) * step
        return base + seg.start + seg.fadeDur + seg.holdDur

    def _evalPass(self, segs, starts, local):
        seg = segs[max(0, bisect.bisect_right(starts, local) - 1)]
        kf = self.keyframes[seg.kf]
        state = dict(seg.snapBefore)
        within = local - seg.start
        lights = kf.get("lights", {})

        if seg.fadeDur > 0 and within < seg.fadeDur:
            if seg.steps:
                k = int(within // (seg.fadeDur / seg.steps))  # each step is fadeDur / steps long
                t = min(1.0, (k + 1) / seg.steps)
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
                 parallel=True, legacy=False, fadeInMs=None, fadeOutMs=None):
        self.name = name
        self.fadeInMs = fadeInMs      # fade when it takes a light; None = the global setting
        self.fadeOutMs = fadeOutMs    # fade when it lets go of one; None = the global setting
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
        return max(0.0, nowMs - self.startMs)

    def frame(self, nowMs):
        t = nowMs - self.startMs   # negative while it fades in: the timeline shows its first frame
        state, finished, self.kfIndex = self.timeline.frameAt(t)
        if self.maxMs is not None and t >= self.maxMs:
            finished = True
        out = dict(self.carry)
        for key, cmd in state.items():
            for idx in self.keyMap.get(key, ()):
                out[idx] = cmd
        self.lastOut = out
        return out, finished

    def nextChange(self, nowMs):
        """When the next frame can differ (monotonic ms), or None."""
        n = self.timeline.nextChange(nowMs - self.startMs)
        if self.maxMs is not None and (n is None or n > self.maxMs):
            n = self.maxMs
        return None if n is None else self.startMs + n

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
        if not self.playing or nowMs < self.anchor:   # before the anchor: held while it fades in
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
                 "speed", "state", "fade", "soundMode", "raw")


class Sequence:
    __slots__ = ("name", "duration", "fps", "end", "pausemode", "oninterrupt", "handbackMs", "fadeInMs", "cues", "raw")


class SequencePlayer:
    kind = "sequence"
    parallel = True
    revert = True

    def __init__(self, seq, resolver, clipLookup, baseCmd, features=None):
        self.seq = seq
        self.features = features or (lambda: None)  # live sound analysis, for sound cues
        self.fadeInMs = seq.fadeInMs     # from the file; the play request can override both
        self.fadeOutMs = seq.handbackMs
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
        self.soundPlayers = {}    # sound cue index -> SoundPlayer on that cue's lights
        self._soundFrames = {}    # sound cue index -> its output this frame (while it plays)
        self._soundActive = set()
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
            if cue.kind == "sound" and cue.soundMode is not None:
                self.soundPlayers[cue.index] = SoundPlayer(cue.soundMode, self.resolver, self.features, targetIdx)
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
            if cue.kind == "sound":
                # this frame's output while it plays; its last output for a fade that follows it
                sp = self.soundPlayers.get(cue.index)
                frame = self._soundFrames.get(cue.index) if cue.index in self._soundActive else (sp.lastOut if sp else None)
                v = (frame or {}).get(idx)
                if v is None:
                    continue
                return dict(v)
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
        self._runSoundCues(pos, nowMs)
        out = {}
        for idx in self.lightCues:
            v = self._evalLight(idx, pos)
            if v is not None:
                out[idx] = v
        self.lastOut = out
        return out, False

    def _runSoundCues(self, pos, nowMs):
        """Step the sound cues playing at pos (each starts afresh when the playhead enters it)."""
        self._soundFrames = {}
        for cue in self.seq.cues:
            sp = self.soundPlayers.get(cue.index)
            if sp is None:
                continue
            if cue.at <= pos < cue.at + cue.dur:
                if cue.index not in self._soundActive:
                    self._soundActive.add(cue.index)
                    sp.start(nowMs)
                self._soundFrames[cue.index] = sp.frame(nowMs)[0]
            else:
                self._soundActive.discard(cue.index)

    def hasSoundCues(self):
        return bool(self.soundPlayers)

    def nextChange(self, nowMs):
        """When the next frame can differ (monotonic ms), or None while paused. Cue onsets and
        ends land exactly; inside a fade or clip it is the next frame of the cue's own grid
        (see _stepped), skipping a clip's holds."""
        c = self.clock
        if not c.playing or (self.userPaused and self.seq.pausemode == "revert"):
            return None
        if nowMs < c.anchor:
            return c.anchor   # held on its first frame while it fades in
        if c.slewTotal:
            return nowMs + self.frameMs
        pos = self.position(nowMs)
        nxt = self.seq.duration
        for cue in self.seq.cues:
            end = cue.at + cue.dur if cue.dur > 0 else None
            if cue.at > pos:
                nxt = min(nxt, cue.at)
                continue
            if end is not None:
                if end <= pos:
                    continue
                nxt = min(nxt, end)
            if cue.kind == "clip":
                tl = self.timelines.get(cue.index)
                if tl is None:
                    continue
                tau = self._stepped(pos - cue.at)
                scale = 1.0
                if cue.fit == "stretch":
                    scale = (cue.dur / tl.d0) if (cue.dur > 0 and tl.d0 > 0) else 0.0
                    tau = tau / scale if scale else 0.0
                n = tl.nextChange(tau)
                if n is None:
                    continue
                # the first frame of the cue's grid that samples the clip at or after its change
                k = math.ceil(n * scale / self.frameMs - 1e-9)
            elif cue.kind == "sound":
                sp = self.soundPlayers.get(cue.index)
                if sp is not None:
                    nxt = min(nxt, pos + sp.frameMs)  # live: frames at the mode's rate
                continue
            elif cue.fade > 0 and pos < cue.at + cue.fade:
                k = 0
            else:
                continue
            k = max(k, int((pos - cue.at) // self.frameMs) + 1)
            nxt = min(nxt, cue.at + k * self.frameMs)
        return nowMs + (nxt - pos)

    def describe(self, nowMs):
        return {"type": "sequence", "name": self.name, "state": self.state,
                "position_ms": int(self.position(nowMs)), "duration_ms": int(self.seq.duration)}


def syntheticSoundFeatures(tMs, bpm=120.0, offsetMs=0):
    """Sound analysis for a song that isn't there: a steady four-on-the-floor beat at bpm (kick
    on every beat, hi-hat between), so previews and renders can show what a sound cue's mode
    does. Same keys as the live analysis."""
    period = 60000.0 / (bpm or 120.0)
    pos = (tMs - offsetMs) / period
    beat = int(math.floor(pos)) if pos >= 0 else -1
    phase = pos - math.floor(pos)
    kick = math.exp(-phase * 7.0)
    hat = math.exp(-abs(phase - 0.5) * 14.0)
    return {"level": 0.45 + 0.45 * kick, "low": 0.15 + 0.8 * kick, "mid": 0.4 + 0.15 * kick, "high": 0.2 + 0.6 * hat,
            "centroid": 0.35 + 0.3 * hat, "silent": False, "beat": beat, "bpm": float(bpm or 120.0)}


def animationFlashRate(anim, speed=1.0):
    """An animation's worst flashes in any second, played on its own at speed (looped, as
    the Animations tab plays it): {"flashes", "red"}, the worst over its lights, before the
    flash guard. Firmware scenes can't be measured and count as steady."""
    tl = AnimationTimeline(anim, speed=speed, fps=FLASH_CHECK_FPS, loop=True, legacy=False)
    loopMs = tl.d0 if tl.d0 > 0 else 1000
    endMs = int(min(60000, max(6000, loopMs * 3)))
    samples = {}
    for k in range(int(endMs * FLASH_CHECK_FPS / 1000)):
        tau = k * 1000.0 / FLASH_CHECK_FPS
        state, _, _ = tl.frameAt(tau)
        for key, cmd in state.items():
            if cmd.get("mode") in ("HSI", "CCT"):
                samples.setdefault(key, []).append((tau / 1000.0, cmd))
    worst = {"flashes": 0.0, "red": 0.0}
    for smp in samples.values():
        r = analyzeFlashes(smp)
        worst = {"flashes": max(worst["flashes"], r["flashes"]), "red": max(worst["red"], r["red"])}
    return worst


FLASH_CHECK_FPS = 30  # frames a second when measuring an animation's flash rate


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


def parseSequence(data, clipExists, defaultFps=DEFAULT_SEQUENCE_FPS, resolveTarget=None, soundLookup=None):
    """Validate a sequence dict. Returns (Sequence or None, errors, warnings).

    soundLookup(spec) gives a sound cue's mode: (SoundMode or None, errors), from its "sound"
    object ({"mode": name, plus any values to change}). Without it sound cues are checked
    for shape only and play nothing.

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
    # how long the lights take to fade back when this sequence lets go of them (None = the global setting)
    seq.handbackMs = None if data.get("handback_fade_ms") is None else \
        _num(data.get("handback_fade_ms"), "handback_fade_ms", 0, 10000, errors, "sequence")
    # how long the lights take to fade in when this sequence takes them (None = the global setting)
    seq.fadeInMs = None if data.get("fade_in_ms") is None else \
        _num(data.get("fade_in_ms"), "fade_in_ms", 0, 10000, errors, "sequence")

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
        cue.state, cue.clipName, cue.fade, cue.soundMode = None, None, 0, None
        cue.fit, cue.brightness, cue.speed = "stretch", 100, 1.0
        hasClip, hasState, hasSound = "clip" in rc, "state" in rc, "sound" in rc
        if hasClip + hasState + hasSound != 1:
            errors.append(where + ": needs exactly one of 'clip', 'state' or 'sound'")
            continue
        if seq.duration is not None and cue.at >= seq.duration:
            warnings.append(where + ": at_ms " + str(cue.at) + " is past the end of the sequence, it will never play")

        if hasSound:
            cue.kind = "sound"
            spec = rc["sound"]
            if isinstance(spec, str):
                spec = {"mode": spec}
            if not isinstance(spec, dict) or not str(spec.get("mode", "")).strip():
                errors.append(where + ": 'sound' needs a 'mode' (a sound mode name)")
                continue
            if soundLookup is not None:
                cue.soundMode, soundErrors = soundLookup(spec)
                errors.extend(where + ": " + e for e in soundErrors)
            cue.dur = _num(rc.get("duration_ms"), "duration_ms", 1, None, errors, where)
        elif hasClip:
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
# HAND-BACK FADES
# ============================================================================
# ============================================================================
# SOUND MODES
# ============================================================================

# ---------------------------------------------------------------- song drafts

DRAFT_STYLE_FORMAT = 1
DRAFT_SECTIONS = ("Intro", "Groove", "Build", "Drop", "Breakdown", "Outro")
DRAFT_BEHAVIOURS = ("fade_up", "fade_down", "hold", "drift", "colour_bars", "pulse", "build", "hit_chase", "animation", "sound")
DRAFT_BEHAVIOUR_NOTES = {
    "fade_up": "Starts dark and fades up to the look over the section.",
    "fade_down": "Fades from the look down to dark by the section's end.",
    "hold": "One look for the section, arriving on its first beat.",
    "drift": "Dim, with slow colour changes every four bars.",
    "colour_bars": "A new colour every bar (every other bar below full energy); brightness follows the energy.",
    "pulse": "The rim pulses on the beat over a darker look; colour changes every four bars.",
    "build": "Pulses that speed up to the limit while the light rises, then a blackout on the last beat.",
    "hit_chase": "Everything hits full on the first beat, then a chase across rim, background and practical with a new colour each bar.",
    "animation": "Plays an animation from the section's pool, looped in time with the tempo.",
    "sound": "Hands the lights to a sound mode from the section's pool for the section.",
}
DRAFT_DEFAULT_BEHAVIOUR = {"Intro": "fade_up", "Groove": "pulse", "Build": "build", "Drop": "hit_chase",
                           "Breakdown": "drift", "Outro": "fade_down"}
# names other section finders use, for analyses that have no NeewerLux kind
_DRAFT_SECTION_ALIASES = {"verse": "Groove", "inst": "Groove", "instrumental": "Groove", "solo": "Drop", "chorus": "Drop",
                          "pre-chorus": "Build", "prechorus": "Build", "bridge": "Breakdown", "break": "Breakdown",
                          "start": "Intro", "end": "Outro"}
DRAFT_INTENSITIES = ("low", "medium", "high")
DRAFT_GROUPS = ("fill", "rim", "background", "practical")
DRAFT_TARGETS = {"fill": "@fill", "rim": "@rim", "background": "@background", "practical": "@practical"}
DRAFT_CHASE_GROUPS = ("rim", "background", "practical")
DRAFT_PULSE_MIN_S = 0.5      # a light pulses at most twice a second (a pulse is one flash)
DRAFT_CLIP_MAX_FLASHES = 2.0 # animations drawn into drafts stay at or under this, as pulses do
DRAFT_CLIP_SPEEDS = (0.5, 2.0)
DRAFT_FILL_SAT = 0.45        # the fill gets a pale version of its colour
# (darkest, brightest) per group for each intensity; energy moves between them
_DRAFT_BRI = {"low": {"fill": (8, 20), "rim": (8, 45), "background": (8, 40), "practical": (8, 35)},
              "medium": {"fill": (12, 28), "rim": (8, 75), "background": (10, 65), "practical": (10, 55)},
              "high": {"fill": (15, 35), "rim": (6, 100), "background": (8, 90), "practical": (8, 80)}}


def _draftPool(data, where, errors):
    """{"tags": every one of these, "exclude": none of these, "names": these whatever their tags}."""
    if data is None:
        data = {}
    if not isinstance(data, dict):
        errors.append(where + " must be an object")
        return {"tags": [], "exclude": [], "names": []}
    pool = {}
    for key in ("tags", "exclude", "names"):
        v = data.get(key, [])
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            errors.append("%s.%s must be a list of words" % (where, key))
            v = []
        pool[key] = [x.strip() if key == "names" else x.strip().lower() for x in v if x.strip()]
    bad = [k for k in data if k not in pool]
    if bad:
        errors.append("%s: unknown %s" % (where, ", ".join(sorted(bad))))
    return pool


def parseDraftStyle(data, paletteLookup=None):
    """Check a draft style (the format is in docs/SEQUENCE_FORMAT.md). paletteLookup(name) gives
    a saved palette's colours or None. Returns (style or None, errors); the style carries
    "colours", the palette's colours."""
    errors = []
    if not isinstance(data, dict):
        return None, ["a draft style must be a JSON object"]
    if data.get("format", DRAFT_STYLE_FORMAT) != DRAFT_STYLE_FORMAT:
        errors.append("format must be %d" % DRAFT_STYLE_FORMAT)
    style = {"format": DRAFT_STYLE_FORMAT, "name": str(data.get("name", "")).strip(),
             "description": str(data.get("description", "")).strip()}
    if not style["name"]:
        errors.append("a draft style needs a name")
    genres = data.get("genres", [])
    if not isinstance(genres, list) or not all(isinstance(g, str) for g in genres):
        errors.append("genres must be a list of words")
        genres = []
    style["genres"] = [g.strip().lower() for g in genres if g.strip()]
    palette = data.get("palette")
    if isinstance(palette, str):
        colours = paletteLookup(palette) if paletteLookup else None
        if colours is None:
            errors.append("no palette named " + repr(palette))
            colours = []
        style["palette"] = palette.strip()
    else:
        colours, perrs = parsePalette(palette)
        errors += perrs
        style["palette"] = colours
    style["colours"] = [dict(c) for c in colours]
    style["intensity"] = str(data.get("intensity", "medium")).strip().lower()
    if style["intensity"] not in DRAFT_INTENSITIES:
        errors.append("intensity must be one of " + ", ".join(DRAFT_INTENSITIES))
    for key in ("use_animations", "use_sound_modes"):
        v = data.get(key, True)
        if not isinstance(v, bool):
            errors.append(key + " must be true or false")
            v = True
        style[key] = v
    sections = data.get("sections", {})
    if not isinstance(sections, dict):
        errors.append("sections must be an object")
        sections = {}
    unknown = [k for k in sections if k not in DRAFT_SECTIONS]
    if unknown:
        errors.append("sections: unknown %s (use %s)" % (", ".join(unknown), ", ".join(DRAFT_SECTIONS)))
    style["sections"] = {}
    for kind in DRAFT_SECTIONS:
        sec = sections.get(kind, {})
        where = "sections." + kind
        if not isinstance(sec, dict):
            errors.append(where + " must be an object")
            sec = {}
        beh = sec.get("behaviour", DRAFT_DEFAULT_BEHAVIOUR[kind])
        beh = [beh] if isinstance(beh, str) else beh
        if not isinstance(beh, list) or not beh or not all(isinstance(b, str) for b in beh):
            errors.append(where + ".behaviour must be a behaviour or a list of them")
            beh = [DRAFT_DEFAULT_BEHAVIOUR[kind]]
        beh = [b.strip().lower() for b in beh]
        bad = [b for b in beh if b not in DRAFT_BEHAVIOURS]
        if bad:
            errors.append("%s.behaviour: unknown %s (use %s)" % (where, ", ".join(bad), ", ".join(DRAFT_BEHAVIOURS)))
        extra = [k for k in sec if k not in ("behaviour", "animations", "sound_modes")]
        if extra:
            errors.append("%s: unknown %s" % (where, ", ".join(sorted(extra))))
        style["sections"][kind] = {"behaviour": beh,
                                   "animations": _draftPool(sec.get("animations"), where + ".animations", errors),
                                   "sound_modes": _draftPool(sec.get("sound_modes"), where + ".sound_modes", errors)}
    if errors:
        return None, errors
    return style, []


def draftStyleFile(style):
    """A parsed style as it's saved (without the resolved colours)."""
    out = {k: style[k] for k in ("format", "name", "description", "genres", "palette", "intensity", "use_animations", "use_sound_modes")}
    out["sections"] = {kind: {"behaviour": sec["behaviour"][0] if len(sec["behaviour"]) == 1 else list(sec["behaviour"]),
                              **{p: {k: v for k, v in sec[p].items() if v} for p in ("animations", "sound_modes") if any(sec[p].values())}}
                       for kind, sec in style["sections"].items()}
    return out


def draftPoolMatches(pool, items):
    """Names of items ({name: data with "tags"}) a pool allows, before the flash check."""
    names = {n.lower() for n in pool.get("names", [])}
    tags, exclude = set(pool.get("tags", [])), set(pool.get("exclude", []))
    out = []
    for name, data in items.items():
        have = {str(t).lower() for t in (data.get("tags") or [])} if isinstance(data, dict) else set()
        if name.lower() in names or (not names or tags) and tags <= have and not exclude & have:
            out.append(name)
    return sorted(out, key=str.lower)


def draftPoolText(pool):
    """A pool as the editors show it: tags, -excluded tags and names, separated by commas."""
    return ", ".join(pool.get("tags", []) + ["-" + t for t in pool.get("exclude", [])] + pool.get("names", []))


def draftPoolFromText(text, itemNames):
    """The editors' pool text read back: a word starting with - is excluded, a word naming an
    item (itemNames) picks that item, any other word is a tag the item must have."""
    known = {n.lower(): n for n in itemNames}
    pool = {"tags": [], "exclude": [], "names": []}
    for word in str(text or "").split(","):
        word = word.strip()
        if not word:
            continue
        if word.startswith("-"):
            pool["exclude"].append(word[1:].strip().lower())
        elif word.lower() in known:
            pool["names"].append(known[word.lower()])
        else:
            pool["tags"].append(word.lower())
    return pool


def matchDraftStyle(styles, genres):
    """The style ({name: parsed style}) whose genres best fit the given genres (most important
    first, as a music database lists them), or None. Exact matches count most, then one genre
    containing the other, then shared words."""
    if isinstance(genres, str):
        genres = [g for g in genres.split(",")]
    query = [str(g).strip().lower() for g in (genres or []) if str(g).strip()]
    best, bestScore = None, 0.0
    for name, style in styles.items():
        score = 0.0
        for i, q in enumerate(query):
            qWords = set(q.replace("-", " ").split())
            fit = 0.0
            for g in style.get("genres", []):
                gWords = set(g.replace("-", " ").split())
                if g == q:
                    fit = max(fit, 3.0)
                elif gWords <= qWords or qWords <= gWords:
                    # the more of the longer name the shorter one covers, the better
                    fit = max(fit, 1.0 + min(len(gWords), len(qWords)) / float(max(len(gWords), len(qWords))))
                elif qWords & gWords:
                    fit = max(fit, len(qWords & gWords) / float(len(qWords | gWords)))
            score += fit / (1.0 + 0.5 * i)
        if score > bestScore:
            best, bestScore = name, score
    return best


def songGrid(durationMs, bpm, offsetMs):
    """Beats (ms) from offsetMs every beat to the end, and bars: every fourth beat from the first."""
    period = 60000.0 / float(bpm)
    offsetMs = float(offsetMs) % period
    beats = [int(round(offsetMs + k * period)) for k in range(int((durationMs - offsetMs) // period) + 1)]
    return beats, beats[::4]


def _draftKind(sec):
    for raw in (sec.get("kind"), sec.get("label")):
        word = str(raw or "").strip().lower()
        for kind in DRAFT_SECTIONS:
            if word.startswith(kind.lower()):
                return kind
        for alias, kind in _DRAFT_SECTION_ALIASES.items():
            if word.startswith(alias):
                return kind
    return "Groove"


_clipRates = {}  # (animation, speed): flash rate, for drafts (the same few animations at a few speeds)


def _clipSpeed(anim, period):
    """The speed at which one loop of the animation lasts a whole number of beats (1, 2, 4 ... 64)
    nearest its own speed, within DRAFT_CLIP_SPEEDS, or None."""
    tl = AnimationTimeline(anim, fps=FLASH_CHECK_FPS, loop=True)
    loopMs = tl.dL if anim.get("loop") and tl.dL > 0 else tl.d0
    if loopMs <= 0:
        return None
    fits = [loopMs / (n * period) for n in (1, 2, 4, 8, 16, 32, 64)]
    fits = [s for s in fits if DRAFT_CLIP_SPEEDS[0] <= s <= DRAFT_CLIP_SPEEDS[1]]
    return round(min(fits, key=lambda s: abs(math.log(s))), 4) if fits else None


def draftSequence(analysis, style, name=None, bpm=None, offsetMs=None, animations=None, soundModes=None, roles=None):
    """A first-draft sequence for a song from neewerlux_audio.analyzeSong's result, shaped by a
    draft style (parseDraftStyle): each section plays its kind's behaviour (Intro, Groove,
    Build, Drop, Breakdown, Outro, from the section's kind or label), brightness follows the
    energy bar by bar between the style's intensity limits, and colours come from its palette.
    A part that repeats (the same group) gets the same behaviour, colours and pool pick; other
    sections of the same kind take the next ones, for variety. animations and soundModes
    ({name: data}) are the pools' sources; roles is the set of roles the rig has (the chase
    skips missing ones). Drives the fill, rim, background and practical lights, never the key,
    and keeps each light at or under 2 flashes a second. bpm and offsetMs (a bar's first beat)
    replace the analysed tempo, moving the sections to the nearest bar line. Returns
    (sequence, errors)."""
    if not isinstance(style, dict) or "sections" not in style:
        return None, ["style must be a draft style"]
    try:
        durationMs = int(analysis["duration_ms"])
        sections = list(analysis["sections"])
        tempo = float(bpm if bpm else analysis["bpm"])
    except (KeyError, TypeError, ValueError) as e:
        return None, ["analysis is missing " + str(e)]
    if not 30 <= tempo <= 300 or durationMs <= 0 or not sections:
        return None, ["analysis needs a duration, sections and a tempo of 30 to 300 BPM"]
    period = 60000.0 / tempo
    if bpm or offsetMs is not None:
        beats, bars = songGrid(durationMs, tempo, analysis.get("offset_ms", 0) if offsetMs is None else offsetMs)
        snapped = sorted({0} | {min(bars, key=lambda b: abs(b - s["start_ms"])) for s in sections[1:]})
        sections = [dict(s, start_ms=a, end_ms=b) for s, a, b in zip(sections, snapped, snapped[1:] + [durationMs]) if b > a]
    else:
        beats = list(analysis.get("beats") or songGrid(durationMs, tempo, analysis.get("offset_ms", 0))[0])
        bars = list(analysis.get("bars") or beats[::4])
    animations = animations or {}
    soundModes = soundModes or {}
    roles = set(roles) if roles else set(DRAFT_GROUPS)
    chaseGroups = [g for g in DRAFT_CHASE_GROUPS if g in roles] or ["rim"]
    lightGroups = ["fill"] + chaseGroups
    briRange = _DRAFT_BRI[style["intensity"]]
    colours = style["colours"] or [{"hue": 35, "sat": 60}]
    pulseEvery = next(n for n in (1, 2, 4, 8) if n * period >= DRAFT_PULSE_MIN_S * 1000)
    rng = random.Random("%s|%d|%.2f" % (style["name"], durationMs, tempo))

    # energy per bar, 0 to 1 within the song, from the analysis's energy curve when it has one
    energy, step = analysis.get("energy") or [], int(analysis.get("energy_step_ms") or 250)
    barEnergy = {}
    if energy:
        means = []
        for t, nxt in zip(bars, bars[1:] + [durationMs]):
            vals = energy[int(t // step):max(int(t // step) + 1, int(nxt // step))]
            means.append(sum(vals) / len(vals) if vals else 0.0)
        ordered = sorted(means)
        lo, hi = ordered[int(0.1 * (len(ordered) - 1))], ordered[int(0.95 * (len(ordered) - 1))]
        barEnergy = {t: max(0.0, min(1.0, (m - lo) / (hi - lo))) if hi > lo else 0.5 for t, m in zip(bars, means)}

    def energyAt(t, sec):
        level = (max(1, min(3, int(sec.get("level", 2)))) - 1) / 2.0
        if not barEnergy:
            return level
        bar = max([b for b in bars if b <= t] or [bars[0]])
        return 0.6 * barEnergy.get(bar, level) + 0.4 * level

    def bri(group, e):
        lo, hi = briRange[group]
        return int(round(lo + (hi - lo) * max(0.0, min(1.0, e))))

    def colour(k):
        return colours[k % len(colours)]

    cues = []
    def state(at, group, c, b, fade=0, label=None, duration=None):
        if group not in lightGroups:
            return
        if "temp" in c:
            # sequences take 3200 to 8500 K
            st = {"mode": "CCT", "temp": max(32, min(85, int(round(c["temp"] / 100.0)))), "bri": int(b)}
        else:
            sat = c["sat"] * DRAFT_FILL_SAT if group == "fill" else c["sat"]
            st = {"mode": "HSI", "hue": int(c["hue"]) % 360, "sat": int(round(sat)), "bri": int(b)}
        st["fade_ms"] = int(max(0, fade))
        cue = {"at_ms": int(max(0, at)), "target": DRAFT_TARGETS[group], "state": st}
        if duration:
            cue["duration_ms"] = int(duration)
        if label:
            cue["label"] = label
        cues.append(cue)

    def look(at, off, e, fade, label=None, scale=1.0):
        """Every light to the section's colours at energy e (scale dims the colour lights)."""
        for n, g in enumerate(lightGroups):
            state(at, g, colour(off + (3 if g == "fill" else DRAFT_CHASE_GROUPS.index(g))),
                  bri(g, e) if g == "fill" else bri(g, e * scale), fade, label if n == 0 else None)

    # pool candidates in a fixed shuffled order per kind, checked lazily (the flash check takes a few ms)
    clipCache = {}
    def clipFor(animName):
        if animName not in clipCache:
            anim = animations[animName]
            keyframes = anim.get("keyframes") or []
            ok = keyframes and not any(str(lp.get("mode", "")).upper() in ("SCENE", "ANM")
                                       for kf in keyframes for lp in (kf.get("lights") or {}).values() if isinstance(lp, dict))
            speed = _clipSpeed(anim, period) if ok else None
            if speed is not None:
                rateKey = (repr(anim), speed)
                if rateKey not in _clipRates:
                    _clipRates[rateKey] = animationFlashRate(anim, speed)
                fr = _clipRates[rateKey]
                if fr["flashes"] > DRAFT_CLIP_MAX_FLASHES or fr["red"] > DRAFT_CLIP_MAX_FLASHES:
                    speed = None
            clipCache[animName] = speed
        return clipCache[animName]

    pools = {}
    for kind, sec in style["sections"].items():
        anims = draftPoolMatches(sec["animations"], animations) if style["use_animations"] else []
        modes = draftPoolMatches(sec["sound_modes"], soundModes) if style["use_sound_modes"] else []
        rng.shuffle(anims)
        rng.shuffle(modes)
        pools[kind] = {"animation": anims, "sound": modes}

    keys, colourOffsets = {}, {}
    def pick(n, candidates, ok=lambda x: True):
        """The n-th usable candidate, wrapping round; checks only as many as it needs."""
        usable = []
        for c in candidates:
            if ok(c):
                usable.append(c)
                if len(usable) > n:
                    return c
        return usable[n % len(usable)] if usable else None

    for i, sec in enumerate(sections):
        a, b = int(sec["start_ms"]), int(sec["end_ms"])
        kind = _draftKind(sec)
        level = max(1, min(3, int(sec.get("level", 2))))
        # a repeated part plays the same way; a new one of the same kind takes the next option
        key = (kind, sec.get("group") or i)
        if key not in keys:
            keys[key] = sum(1 for k in keys if k[0] == kind)
            colourOffsets[key] = len(colourOffsets)
        n, off = keys[key], colourOffsets[key]
        label = sec.get("label") or kind
        secBars = [t for t in bars if a <= t < b] or [a]
        secBeats = [t for t in beats if a <= t < b] or [a]
        eSec = energyAt(a, sec)

        choices = []
        for beh in style["sections"][kind]["behaviour"]:
            if beh == "animation" and pick(0, pools[kind]["animation"], clipFor) is None:
                continue
            if beh == "sound" and not pools[kind]["sound"]:
                continue
            choices.append(beh)
        beh = choices[n % len(choices)] if choices else DRAFT_DEFAULT_BEHAVIOUR[kind]
        arrive = int(min(period / 2, (b - a) / 4))

        if beh == "fade_up":
            for g in lightGroups:
                state(a, g, colour(off), briRange[g][0] if g == "fill" else 0, 0 if i == 0 else arrive, label if g == "fill" else None)
            up = int(min(b - a, period))
            look(a + up, off, energyAt(b - 1, sec), max(0, b - a - up - arrive))
        elif beh == "fade_down":
            look(a, off, eSec, arrive, label)
            down = a + int(min(4 * period, (b - a) / 4))
            for g in lightGroups:
                state(down, g, colour(off + (3 if g == "fill" else DRAFT_CHASE_GROUPS.index(g))),
                      briRange[g][0] if g == "fill" else 0, max(0, b - down - arrive))
        elif beh == "hold":
            fade = int(min(4 * period, (a - int(sections[i - 1]["start_ms"])) / 2)) if i else 2000
            look(a - fade if i else 0, off, eSec, fade, label)
        elif beh == "drift":
            look(a, off, eSec, 2 * period, label, scale=0.45)
            for k, t in enumerate(secBars[4::4], start=1):
                for g in chaseGroups:
                    state(t, g, colour(off + k + DRAFT_CHASE_GROUPS.index(g)), bri(g, energyAt(t, sec) * 0.45), 3 * period)
        elif beh == "colour_bars":
            look(a, off, eSec, arrive, label)
            every = 1 if level == 3 else 2
            for k, t in enumerate(secBars[every::every], start=1):
                for g in chaseGroups:
                    state(t, g, colour(off + k + DRAFT_CHASE_GROUPS.index(g)), bri(g, energyAt(t, sec)), period / 4)
        elif beh == "pulse":
            look(a, off, eSec, arrive, label, scale=0.4)
            rimNow = {}
            for k, t in enumerate(secBars):
                c = off + k // 4
                e = energyAt(t, sec)
                for g in chaseGroups:
                    if k and (k % 4 == 0 or g != "rim"):
                        state(t, g, colour(c + DRAFT_CHASE_GROUPS.index(g)), bri(g, e * 0.4), period / 4)
                rimNow[t] = colour(c)
            if level >= 2:
                every = pulseEvery * (1 if level == 3 else 2)
                for t in secBeats[::every]:
                    bar = max(x for x in secBars if x <= t) if t >= secBars[0] else secBars[0]
                    state(t, "rim", rimNow[bar], bri("rim", 0.75 + 0.25 * energyAt(t, sec)), 0, duration=period * 0.35)
        elif beh == "build":
            last = secBeats[-1] if len(secBeats) > 1 else b
            look(a, off, 0.15, arrive, label, scale=1.0)
            rise = a + int(period)
            for g in chaseGroups:
                state(rise, g, colour(off + DRAFT_CHASE_GROUPS.index(g)), bri(g, 0.55), max(0, last - rise - period))
            # pulses every 2 bars, then every bar, half bar and beat, never faster than twice a second
            span, t, k = max(1, last - a), secBeats[0], 0
            while t < last:
                pos = (t - a) / span
                every = 8 if pos < 0.5 else 4 if pos < 0.75 else 2 if pos < 0.875 else 1
                every = max(every, pulseEvery)
                peak = 0.6 + 0.4 * pos
                dur = min(period * 0.4, every * period * 0.35)
                if t + dur < last:
                    for g in chaseGroups:
                        state(t, g, colour(off + DRAFT_CHASE_GROUPS.index(g)), bri(g, peak), 0, duration=dur)
                k += every
                t = secBeats[k] if k < len(secBeats) else last
            if last < b:
                for g in lightGroups:
                    state(last, g, colour(off), briRange[g][0] if g == "fill" else 0, 0)
        elif beh == "hit_chase":
            lit = lambda g, e: bri(g, 0.8 + 0.2 * e)
            dim = lambda g: bri(g, 0.12)
            for n2, g in enumerate(lightGroups):
                state(a, g, colour(off + (3 if g == "fill" else 0)), bri(g, 1.0), 0, label if n2 == 0 else None)
            groups = chaseGroups if len(chaseGroups) > 1 else chaseGroups * 2
            # a light is lit one step in len(groups): one flash per cycle, at most twice a second
            stepEvery = next(m for m in (1, 2, 4, 8) if m * period * len(groups) >= DRAFT_PULSE_MIN_S * 1000)
            for s, t in enumerate(secBeats[stepEvery::stepEvery], start=1):
                barNo = sum(1 for x in secBars if x <= t) - 1
                on = groups[s % len(groups)]
                e = energyAt(t, sec)
                if len(chaseGroups) > 1:
                    for g in chaseGroups:
                        state(t, g, colour(off + barNo), lit(g, e) if g == on else dim(g), period * 0.1)
                else:
                    state(t, on, colour(off + barNo), lit(on, e) if s % 2 == 0 else dim(on), period * 0.1)
        elif beh == "animation":
            animName = pick(n, pools[kind]["animation"], clipFor)
            state(a, "fill", colour(off + 3), bri("fill", eSec), arrive, label)
            cues.append({"at_ms": a, "duration_ms": b - a, "target": ";".join(DRAFT_TARGETS[g] for g in chaseGroups),
                         "clip": {"name": animName, "fit": "loop", "speed": clipFor(animName),
                                  "brightness": int(round(briRange["rim"][1] * (0.6 + 0.4 * eSec)))}})
        elif beh == "sound":
            modeName = pick(n, pools[kind]["sound"])
            spec = {"mode": modeName}
            parts = (soundModes[modeName].get("parts") or []) if isinstance(soundModes[modeName], dict) else []
            used = [p.get("colour") for p in parts if isinstance(p, dict) and isinstance(p.get("colour"), int)]
            if style["colours"] and (not used or max(used) < len(style["colours"])):
                spec["palette"] = [dict(c) for c in style["colours"]]
            state(a, "fill", colour(off + 3), bri("fill", eSec), arrive, label)
            cues.append({"at_ms": a, "duration_ms": b - a, "target": ";".join(DRAFT_TARGETS[g] for g in chaseGroups), "sound": spec})

    seq = {"format": 1, "name": name or "Draft", "duration_ms": durationMs, "end": "revert",
           "description": "Drafted from the song (" + style["name"] + " style, " + ("%g" % round(tempo, 2)) + " BPM)",
           "tempo": {"bpm": round(tempo, 2), "offset_ms": int(round(bars[0] if bars else 0))},
           "sections": [{"start_ms": int(s["start_ms"]), "end_ms": int(s["end_ms"]), "label": s.get("label", ""),
                         "level": int(s.get("level", 2)), **{k: s[k] for k in ("group", "kind") if s.get(k)}} for s in sections],
           "cues": sorted(cues, key=lambda c: c["at_ms"])}
    return seq, []


SOUND_MODE_FORMAT = 1
SOUND_DRIVES = ("level", "low", "mid", "high", "beat")
SOUND_COLOURS = ("centroid", "beat", "cycle")  # besides a palette index
SOUND_FLASH_LIMIT = 2       # flashes a second a sound mode allows itself; the flash guard (3) is the backstop
SOUND_FLASH_WINDOW_S = 1.05 # a little over a second: evenly paced transitions 0.25 s apart would put five
                            # in one closed second on a 50 ms frame grid
SOUND_CHASE_MAX_BPM = 150   # faster than this, chases step on every other beat
SOUND_BLINK_MAX_BPM = 120   # faster than this, Beat-driven lights flash on every other beat (one flash per beat at 120 BPM is the 2/s limit)
SOUND_ATTACK_MS = 60        # how fast a light rises to a louder value (less with low Smoothing, none at 0)
SOUND_COLOUR_STEP_MS = 400  # how long a palette step (colour "beat") takes to blend
SOUND_SETTLE_MS = 300       # a value held this long is written even if under the write deadband,
                            # so a fade ends exactly on its floor or ceiling
SOUND_DEFAULT_CURVE = 2.0   # brightness = floor + (ceiling - floor) * value ** curve; 1 is straight
SOUND_CYCLE_MIN_S = 4       # colour "cycle": at least this long round the palette, and at least
                            # a second per colour, so a cycle can't turn into colour flashing
ANALYSIS_RANGE_DB = 30.0    # the analysis reads this many dB under the recent peak as 0 (neewerlux_audio.NORM_RANGE_DB)


class SoundMode:
    __slots__ = ("name", "description", "tags", "sensitivity", "rangeDb", "floor", "ceiling", "smoothing", "curve", "fps", "palette",
                 "cycleS", "parts", "fadeInMs", "handbackMs", "raw")


def _modeNum(data, key, default, lo, hi, errors, integer=False):
    if key not in data:
        return default
    v = data[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        errors.append("%s must be a number" % key)
        return default
    if not lo <= v <= hi:
        errors.append("%s must be %s to %s" % (key, lo, hi))
        return default
    return int(round(v)) if integer else float(v)


def parsePalette(palette):
    """Check a palette: a list of colours, all {"hue", "sat"} or all {"temp"} (Kelvin).
    Returns (the palette, errors)."""
    errors = []
    if not isinstance(palette, list) or not palette:
        return [], ["palette must be a list of colours"]
    out, kinds = [], set()
    for i, entry in enumerate(palette):
        if not isinstance(entry, dict):
            errors.append("palette[%d] must be an object" % i)
            continue
        if "temp" in entry:
            pe = {"temp": _modeNum(entry, "temp", 5600, 2700, 10000, errors, integer=True)}
            kinds.add("CCT")
        else:
            pe = {"hue": _modeNum(entry, "hue", 0, 0, 360, errors, integer=True) % 360,
                  "sat": _modeNum(entry, "sat", 100, 0, 100, errors, integer=True)}
            kinds.add("HSI")
        out.append(pe)
    if len(kinds) > 1:
        errors.append("palette colours must all be hue/sat or all temp (Kelvin), not a mix")
    return out, errors


def parseSoundMode(data, defaultFps=DEFAULT_SEQUENCE_FPS, resolveTarget=None):
    """Check a sound mode (the format is in docs/SOUND_MODES.md). Returns (SoundMode or None,
    errors, warnings)."""
    errors, warnings = [], []
    if not isinstance(data, dict):
        return None, ["a sound mode must be a JSON object"], []
    if data.get("format", SOUND_MODE_FORMAT) != SOUND_MODE_FORMAT:
        errors.append("format must be %d" % SOUND_MODE_FORMAT)
    m = SoundMode()
    m.raw = data
    m.name = str(data.get("name", "")).strip()
    if not m.name:
        errors.append("a sound mode needs a name")
    m.description = str(data.get("description", ""))
    m.tags = data.get("tags", [])
    if not isinstance(m.tags, list) or not all(isinstance(t, str) and t.strip() for t in m.tags):
        errors.append("tags must be a list of words")
        m.tags = []
    m.sensitivity = _modeNum(data, "sensitivity", 1.0, 0.1, 5.0, errors)
    m.rangeDb = _modeNum(data, "range_db", 18.0, 6.0, ANALYSIS_RANGE_DB, errors)
    m.floor = _modeNum(data, "floor", 10, 0, 100, errors, integer=True)
    m.ceiling = _modeNum(data, "ceiling", 75, 0, 100, errors, integer=True)
    if m.floor > m.ceiling:
        errors.append("floor can't be above ceiling")
    m.smoothing = _modeNum(data, "smoothing", 0.5, 0.0, 1.0, errors)
    m.curve = _modeNum(data, "curve", SOUND_DEFAULT_CURVE, 1.0, 3.0, errors)
    m.fps = _modeNum(data, "fps", defaultFps, 1, MAX_FPS, errors, integer=True)
    m.fadeInMs = _modeNum(data, "fade_in_ms", None, 0, 10000, errors, integer=True)
    m.handbackMs = _modeNum(data, "handback_fade_ms", None, 0, 10000, errors, integer=True)

    m.palette, palErrors = parsePalette(data.get("palette", [{"hue": 240, "sat": 100}]))
    errors += palErrors
    minCycle = max(SOUND_CYCLE_MIN_S, len(m.palette))
    m.cycleS = _modeNum(data, "cycle_s", max(20.0, minCycle), 1, 600, errors)
    if m.cycleS < minCycle:
        errors.append("cycle_s must be at least %d (%d s, and a second per palette colour)" % (minCycle, SOUND_CYCLE_MIN_S))

    m.parts = []
    parts = data.get("parts")
    if not isinstance(parts, list) or not parts:
        errors.append("parts must be a non-empty list")
        parts = []
    for i, part in enumerate(parts):
        if not isinstance(part, dict):
            errors.append("parts[%d] must be an object" % i)
            continue
        p = {"target": str(part.get("target", "")).strip(), "drive": str(part.get("drive", "level")).lower(),
             "colour": part.get("colour", 0), "chase": bool(part.get("chase", False))}
        if not p["target"]:
            errors.append("parts[%d] needs a target" % i)
        if p["drive"] not in SOUND_DRIVES:
            errors.append("parts[%d].drive must be one of %s" % (i, ", ".join(SOUND_DRIVES)))
        c = p["colour"]
        if isinstance(c, bool) or not (isinstance(c, int) or c in SOUND_COLOURS):
            errors.append("parts[%d].colour must be a palette index, \"centroid\", \"beat\" or \"cycle\"" % i)
        elif isinstance(c, int) and not 0 <= c < max(1, len(m.palette)):
            errors.append("parts[%d].colour %d is not in the palette" % (i, c))
        sub = []
        p["floor"] = _modeNum(part, "floor", None, 0, 100, sub, integer=True)
        p["ceiling"] = _modeNum(part, "ceiling", None, 0, 100, sub, integer=True)
        errors += ["parts[%d].%s" % (i, e) for e in sub]
        lo = m.floor if p["floor"] is None else p["floor"]
        hi = m.ceiling if p["ceiling"] is None else p["ceiling"]
        if lo > hi:
            errors.append("parts[%d]: floor can't be above ceiling" % i)
        if resolveTarget is not None and p["target"] and not resolveTarget(p["target"]):
            warnings.append("parts[%d] target %s matches no light right now" % (i, p["target"]))
        m.parts.append(p)
    return (None if errors else m), errors, warnings


def soundModeWithParams(mode, params, defaultFps=DEFAULT_SEQUENCE_FPS):
    """The mode with some values changed (sensitivity, range_db, floor, ceiling, smoothing,
    curve, palette, cycle_s, fps, parts), checked like a saved mode. Returns (SoundMode or None, errors)."""
    allowed = ("sensitivity", "range_db", "floor", "ceiling", "smoothing", "curve", "palette", "cycle_s", "fps", "parts")
    if not isinstance(params, dict):
        return None, ["params must be an object"]
    bad = [k for k in params if k not in allowed]
    if bad:
        return None, ["can't change %s (only %s)" % (", ".join(bad), ", ".join(allowed))]
    raw = dict(mode.raw)
    raw.update(params)
    m, errors, _ = parseSoundMode(raw, defaultFps)
    return m, errors


def _lerpPalette(palette, pos):
    """A colour at pos (0 to 1) along the palette, blending neighbouring entries (hue the short
    way round)."""
    if len(palette) == 1:
        return dict(palette[0])
    x = max(0.0, min(1.0, pos)) * (len(palette) - 1)
    i = min(int(x), len(palette) - 2)
    return _blendEntry(palette[i], palette[i + 1], x - i)


def _cyclePalette(palette, pos):
    """A colour at pos (0 to 1) round the palette and back to its first colour. A single
    colour goes once round the colour wheel; a single white stays put."""
    if len(palette) == 1:
        e = palette[0]
        return dict(e) if "temp" in e else {"hue": (e["hue"] + pos * 360.0) % 360, "sat": e["sat"]}
    x = (pos % 1.0) * len(palette)
    i = int(x) % len(palette)
    return _blendEntry(palette[i], palette[(i + 1) % len(palette)], x - int(x))


def _blendEntry(a, b, t):
    if "temp" in a:
        return {"temp": a["temp"] + (b["temp"] - a["temp"]) * t}
    diff = (b["hue"] - a["hue"] + 540) % 360 - 180
    return {"hue": (a["hue"] + diff * t) % 360, "sat": a["sat"] + (b["sat"] - a["sat"]) * t}


def _soundClose(a, b):
    """Changes too small to be worth a Bluetooth write."""
    if a is None or b is None or a.get("mode") != b.get("mode") or abs(a["bri"] - b["bri"]) >= 2:
        return False
    if a["mode"] == "CCT":
        return a["temp"] == b["temp"]
    return abs((a["hue"] - b["hue"] + 540) % 360 - 180) < 3 and abs(a["sat"] - b["sat"]) < 3


class _SoundVoice:
    """One sound mode on some lights: the mode's own targets (lights None, less any lights
    taken out), or the lights given, each following the first part whose target includes it
    (the first part when none does)."""

    def __init__(self, mode, lights=None):
        self.mode = mode
        self.lights = None if lights is None else list(lights)
        self.excluded = set()
        self.partLights = []
        self._env = {}          # (part, light) -> 0..1
        self._levelEnv = 0.0
        self._presence = 0.0    # 1 while there is sound, easing to 0 in silence
        self._centroid = {}     # part -> smoothed centroid
        self._step = {}         # part -> chase step / palette step
        self._stepAt = {}       # part -> ms when the palette step changed
        self._beatEnv = {}      # part -> beat envelope
        self._blinkAt = {}      # part -> when its last Beat flash began

    def drop(self, lights):
        if self.lights is None:
            self.excluded |= set(lights)
        else:
            self.lights = [i for i in self.lights if i not in lights]

    def refreshMap(self, resolver):
        resolved = [list(resolver(p["target"])) for p in self.mode.parts]
        if self.lights is None:
            self.partLights = [[i for i in r if i not in self.excluded] for r in resolved]
            return
        self.partLights = [[] for _ in resolved]
        for idx in self.lights:
            pi = next((k for k, r in enumerate(resolved) if idx in r), 0)
            self.partLights[pi].append(idx)
        sweep = list(resolver("@all"))
        for pi, lights in enumerate(self.partLights):
            # chases run in the part's own order, then the lights it didn't name in sweep order
            order = resolved[pi]
            lights.sort(key=lambda i: (0, order.index(i)) if i in order else (1, sweep.index(i) if i in sweep else i))

    def frame(self, f, nowMs, dt, blinkBeat, stepBeat, startMs):
        mode = self.mode
        # Smoothing 0 is a hard cut both ways: lights snap to each new value
        attack = min(SOUND_ATTACK_MS, mode.smoothing * 4 * SOUND_ATTACK_MS)
        release = mode.smoothing * 1620.0
        up = 1.0 - math.exp(-dt / attack) if attack > 0 else 1.0
        down = 1.0 - math.exp(-dt / release) if release > 0 else 1.0
        def driveOf(key):
            # the analysis spans 30 dB; a smaller range makes the same music swing further
            v = f.get(key, 0.0)
            if v > 0:
                v = max(0.0, 1.0 - (1.0 - v) * ANALYSIS_RANGE_DB / mode.rangeDb)
            return min(1.0, v * mode.sensitivity)
        level = driveOf("level")
        self._levelEnv += (level - self._levelEnv) * (up if level > self._levelEnv else down)
        present = 1.0 if f and not f.get("silent", True) else 0.0
        self._presence += (present - self._presence) * (up if present > self._presence else down)

        out = {}
        for pi, part in enumerate(mode.parts):
            lights = self.partLights[pi] if pi < len(self.partLights) else []
            if not lights:
                continue
            lo = mode.floor if part["floor"] is None else part["floor"]
            hi = mode.ceiling if part["ceiling"] is None else part["ceiling"]
            colour = part["colour"]
            if stepBeat and (part["chase"] or colour == "beat"):
                self._step[pi] = self._step.get(pi, 0) + 1
                self._stepAt[pi] = nowMs
            if part["drive"] == "beat":
                # full for half a beat, then falling at the Smoothing speed (gone at once at 0)
                if blinkBeat:
                    self._blinkAt[pi] = nowMs
                held = nowMs - self._blinkAt.get(pi, -1e9) < 30000.0 / (f.get("bpm") or 200.0)
                be = 1.0 if held else self._beatEnv.get(pi, 0.0) * (1.0 - down)
                self._beatEnv[pi] = be
                drive = be
            else:
                drive = driveOf(part["drive"])

            if colour == "centroid":
                c = self._centroid.get(pi, f.get("centroid", 0.0))
                c += (f.get("centroid", c) - c) * (1.0 - math.exp(-dt / (300.0 + mode.smoothing * 3000.0)))
                self._centroid[pi] = c
                entry = _lerpPalette(mode.palette, c)
            elif colour == "beat":
                n = len(mode.palette)
                k = self._step.get(pi, 0)
                t = min(1.0, (nowMs - self._stepAt.get(pi, -1e9)) / SOUND_COLOUR_STEP_MS)
                entry = _blendEntry(mode.palette[(k - 1) % n], mode.palette[k % n], t)
            elif colour == "cycle":
                entry = _cyclePalette(mode.palette, (nowMs - startMs) / (mode.cycleS * 1000.0))
            else:
                entry = mode.palette[colour]

            for li, idx in enumerate(lights):
                if part["chase"]:
                    # the lit light keeps some brightness through quiet passages, but not silence:
                    # with no beats the chase can't step, and no sound means the floor
                    on = li == self._step.get(pi, 0) % len(lights)
                    # a chase on the Beat lights each step fully; otherwise louder music, brighter step
                    lit = 1.0 if part["drive"] == "beat" else 0.4 + 0.6 * self._levelEnv
                    target = (1.0 if on else 0.0) * lit * self._presence
                else:
                    target = drive
                key = (pi, idx)
                env = self._env.get(key, 0.0)
                env += (target - env) * (up if target > env else down)
                self._env[key] = env
                # eyes notice a change at the dim end far more than near full, so the curve spends
                # more of the movement down there
                bri = int(round(lo + (hi - lo) * env ** mode.curve))
                if "temp" in entry:
                    out[idx] = {"mode": "CCT", "temp": int(round(entry["temp"] / 100.0)), "bri": bri}
                else:
                    out[idx] = {"mode": "HSI", "hue": int(round(entry["hue"])) % 360, "sat": int(round(entry["sat"])), "bri": bri}
        return out


class SoundPlayer:
    """Sound modes on the sound layer: one mode on its own targets, or several modes each on
    lights assigned to it (assign). features() returns the latest analysis (a dict from
    neewerlux_audio.Analyzer) or None; frames never wait on audio. It never finishes; it is
    stopped, or ends when release() leaves it no lights."""
    kind = "sound"
    parallel = True
    revert = True
    maxMs = None

    def __init__(self, mode, resolver, features, lights=None):
        self.resolver = resolver
        self.features = features
        self.startMs = 0.0
        self.lastOut = {}
        self.latest = None
        self.voices = []
        self._lastMs = None
        self._lastBeat = None
        self._beats = 0
        self._counters = {}     # light -> (FlashCounter as white, FlashCounter on its colour) (SOUND_FLASH_LIMIT)
        self._sent = {}         # light -> command last output
        self._held = {}         # light -> (command computed, ms it has been the same since)
        self.assign(mode, lights)

    def assign(self, mode, lights=None):
        """lights (indexes) follow mode from now on, leaving whatever they followed; None
        means mode on its own targets, replacing every assignment."""
        if lights is None:
            self.voices = [_SoundVoice(mode)]
        else:
            lights = list(dict.fromkeys(lights))
            for v in self.voices:
                v.drop(lights)
            same = next((v for v in self.voices if v.lights is not None and v.mode.name.lower() == mode.name.lower()), None)
            if same is None:
                self.voices.append(_SoundVoice(mode, lights))
            else:
                same.mode = mode
                same.lights += lights
                self.voices.remove(same)
                self.voices.append(same)  # the latest assignment names the player
            self._modesChanged()
            self._dropEmpty()
        self._modesChanged()

    def setMode(self, mode):
        """New values for a mode that is playing (every assignment of it), keeping its lights."""
        for v in self.voices:
            if v.mode.name.lower() == mode.name.lower():
                v.mode = mode
        self._modesChanged()

    def release(self, lights):
        """Take lights out of every assignment. Returns True when no light is left."""
        for v in self.voices:
            v.drop(lights)
        self.refreshMap()
        empty = not self.lights()
        self._dropEmpty()
        self._modesChanged()
        return empty

    def _dropEmpty(self):
        """Forget modes left with no lights (keeping one, so the player always has a mode)."""
        self.voices = [v for v in self.voices if any(v.partLights)] or self.voices[-1:]

    def _modesChanged(self):
        self.mode = self.voices[-1].mode
        self.name = self.mode.name
        self.fadeInMs = self.mode.fadeInMs
        self.fadeOutMs = self.mode.handbackMs
        self.frameMs = 1000.0 / max(v.mode.fps for v in self.voices)
        self.refreshMap()

    def refreshMap(self):
        for v in self.voices:
            v.refreshMap(self.resolver)

    def lights(self):
        return [i for v in self.voices for lights in v.partLights for i in lights]

    def drives(self, idx):
        return any(idx in lights for v in self.voices for lights in v.partLights)

    def assignments(self):
        """[{"mode", "lights"}] with lights as indexes; lights None for a mode on its own targets."""
        return [{"mode": v.mode.name, "lights": sorted(set(i for ls in v.partLights for i in ls)) if v.lights is not None else None}
                for v in self.voices]

    def start(self, nowMs):
        self.startMs = nowMs

    def nextChange(self, nowMs):
        if nowMs < self.startMs:
            return self.startMs
        return self.startMs + (int((nowMs - self.startMs) // self.frameMs) + 1) * self.frameMs

    def frame(self, nowMs):
        f = self.features() or {}
        self.latest = f or None
        dt = min(200.0, nowMs - self._lastMs) if self._lastMs is not None else self.frameMs
        self._lastMs = nowMs
        beat = f.get("beat")
        newBeat = beat is not None and self._lastBeat is not None and beat != self._lastBeat
        self._lastBeat = beat
        if newBeat:
            self._beats += 1
        # every other beat when every beat would be too fast: steady, rather than the limiter
        # holding back flashes here and there
        stepBeat = newBeat and (f.get("bpm", 0) <= SOUND_CHASE_MAX_BPM or self._beats % 2 == 0)
        blinkBeat = newBeat and (f.get("bpm", 0) <= SOUND_BLINK_MAX_BPM or self._beats % 2 == 0)

        out = {}
        for v in self.voices:
            out.update(v.frame(f, nowMs, dt, blinkBeat, stepBeat, self.startMs))

        t = nowMs / 1000.0
        for idx, cmd in out.items():
            prev = self._sent.get(idx)
            held = self._held.get(idx)
            if held is None or held[0] != cmd:
                held = self._held[idx] = (cmd, nowMs)
            settled = nowMs - held[1] >= SOUND_SETTLE_MS
            if _soundClose(prev, cmd) and not (settled and cmd != prev):
                out[idx] = prev
                continue
            counters = self._counters.get(idx)
            if counters is None:
                counters = self._counters[idx] = (FlashCounter(), FlashCounter())
            # judged as if it were white (a CCT-only light shows colours as white, which swings
            # further in luminance than the colour does) and on its real colour (a colour step at
            # the same brightness, yellow to blue, is a swing white doesn't show)
            colour = flashLevel(cmd) or (0.0, False)
            white = flashLevel({"mode": "CCT", "temp": 56, "bri": cmd["bri"]}) or (0.0, False)
            levels = ((white[0], colour[1]), colour)
            if prev is not None and any(c.check(t, lv, SOUND_FLASH_LIMIT, SOUND_FLASH_WINDOW_S, paced=True)
                                        for c, lv in zip(counters, levels)):
                out[idx] = prev
                continue
            for c, lv in zip(counters, levels):
                c.add(t, lv)
            self._sent[idx] = cmd
        self.lastOut = out
        return dict(out), False

    def describe(self, nowMs):
        f = self.latest or {}
        return {"type": "sound", "name": self.name, "level": f.get("level", 0.0), "low": f.get("low", 0.0),
                "mid": f.get("mid", 0.0), "high": f.get("high", 0.0), "centroid": f.get("centroid", 0.0),
                "bpm": f.get("bpm", 0.0), "beat": f.get("beat", 0), "signal": bool(f) and not f.get("silent", True),
                "assignments": self.assignments()}


def _revertsOnPause(player):
    return isinstance(player, SequencePlayer) and player.userPaused and player.seq.pausemode == "revert"


HANDBACK_FPS = 20  # updates a second while a light fades back (keeps Bluetooth writes modest)


def _lerp(a, b, t):
    return a + (b - a) * t


def blendCommands(a, b, t):
    """A command t (0 to 1) of the way from a to b, for fading a light back when a layer
    lets go of it. Brightness (CCT and scene brightness, HSI intensity) moves continuously
    even across a mode change:
      HSI to CCT    saturation falls to 0 (white) while brightness moves, then CCT;
      CCT to HSI    HSI from saturation 0 at once, then the colour comes in;
      scene to X    the scene's brightness moves, then X; X to scene: the reverse.
    Lights can't blend between modes themselves, so the switch is one step at matched
    brightness. Power commands and unknown values cut."""
    if not a or not b or t >= 1.0:
        return b
    ma, mb = a.get("mode"), b.get("mode")
    if ma not in ("HSI", "CCT", "ANM") or mb not in ("HSI", "CCT", "ANM"):
        return b
    bri = int(round(_lerp(a.get("bri", 100), b.get("bri", 100), t)))
    if ma == mb == "HSI":
        h0, h1 = a.get("hue", 0) % 360, b.get("hue", 0) % 360
        d = ((h1 - h0 + 180) % 360) - 180  # the short way round
        return {"mode": "HSI", "hue": int(round(h0 + d * t)) % 360,
                "sat": int(round(_lerp(a.get("sat", 100), b.get("sat", 100), t))), "bri": bri}
    if ma == mb == "CCT":
        return {"mode": "CCT", "temp": int(round(_lerp(a.get("temp", 56), b.get("temp", 56), t))), "bri": bri}
    if ma == "HSI" and mb == "CCT":
        return {"mode": "HSI", "hue": a.get("hue", 0), "sat": int(round(_lerp(a.get("sat", 100), 0, t))), "bri": bri}
    if ma == "CCT" and mb == "HSI":
        return {"mode": "HSI", "hue": b.get("hue", 0), "sat": int(round(_lerp(0, b.get("sat", 100), t))), "bri": bri}
    if ma == "ANM":  # to anything: keep the scene while its brightness moves
        return {"mode": "ANM", "scene": a.get("scene", 1), "bri": bri}
    return {"mode": "ANM", "scene": b.get("scene", 1), "bri": bri}  # into a scene: switch, then brightness


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
        self.layers = {LAYER_SOUND: None, LAYER_SHOW: None, LAYER_EFFECT: None, LAYER_OVERRIDE: None}
        self.effectQueue = []
        self.owner = {}       # idx -> layer driving it
        self.baseStates = {}  # idx -> bytes to restore when no layer drives it
        self.knownBase = {}   # idx -> the last colour set outside the layers (survives Off and On)
        self.lastSent = {}    # idx -> bytes this compositor last queued
        self.lastCmd = {}
        self.mailbox = {}     # idx -> (bytes, parallel)
        self.released = {}   # idx -> base bytes just restored, until a base write replaces them
        self.fades = {}      # idx -> (start ms, duration ms, command faded from, layer handed to; 0 = base)
        self._absorbUntil = 0.0  # a sequence ending on a preset: its recall becomes the fade's target, not a cut
        self.ownerPlayer = {} # idx -> the player driving it (to tell a replacement from the same player)
        self._deferred = []
        # {light: the player that was driving it} for lights switched off by hand during a show:
        # no layer drives them until a write turns them on, or that player ends
        self.poweredOff = {}
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
        # Ticks only when some light's output can change (or a command arrives), instead of
        # every few ms; positions come from the clock, so when it ticks doesn't move anything.
        while self._running:
            if not self.anyActive():
                self._wake.wait()
                self._wake.clear()
                continue
            now = self.clock()
            self.tick(now)
            self._sleepUntil(self.nextDueMs(self._nowMs(now)) / 1000.0)

    def _sleepUntil(self, due):
        # Event waits are only ~15 ms accurate on Windows, time.sleep is precise from Python
        # 3.11: wait for commands most of the way, then sleep the last stretch.
        delay = due - self.clock()
        if delay > 0.03:
            if self._wake.wait(delay - 0.02):
                self._wake.clear()
                return
            delay = due - self.clock()
        if delay > 0:
            time.sleep(delay)

    def nextDueMs(self, nowMs):
        """The next time a tick could send something: a player's next change, a transition
        fade's next step, at most IDLE_TICK_MS away."""
        with self.lock:
            due = nowMs + IDLE_TICK_MS
            for p in self.layers.values():
                if p is not None:
                    n = p.nextChange(nowMs)
                    if n is not None and n < due:
                        due = n
            stepMs = 1000.0 / HANDBACK_FPS
            for start, _, _, _ in self.fades.values():
                due = min(due, start + (int((nowMs - start) // stepMs) + 1) * stepMs)
        # A boundary computed to land exactly now can still sit a rounding error before the
        # change it predicts; the next tick then follows 0.1 ms later rather than never.
        return max(due, nowMs + 0.1)

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
            self._beginPlayer(layer, player, nowMs, old)
            return "playing"
        return self._command(run, now)

    def playSound(self, player, now=None):
        """Put a SoundPlayer on the sound layer, replacing the one there."""
        return self.playAnimation(player, LAYER_SOUND, "replace", now)

    def soundPlayer(self):
        with self.lock:
            return self.layers[LAYER_SOUND]

    def assignSound(self, mode, lights, now=None):
        """lights follow mode on the sound layer that is playing. False when none is."""
        def run(nowMs):
            player = self.layers[LAYER_SOUND]
            if player is None:
                return False
            player.assign(mode, lights)
            return True
        return self._command(run, now)

    def releaseSound(self, lights, now=None):
        """lights stop following sound (they fade back); the layer stops when none are left.
        Returns "released", "stopped", or None when no sound layer is playing."""
        def run(nowMs):
            player = self.layers[LAYER_SOUND]
            if player is None:
                return None
            if player.release(lights):
                self._endPlayer(LAYER_SOUND, player, nowMs, "stopped")
                return "stopped"
            return "released"
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
            self._beginPlayer(LAYER_SHOW, player, nowMs, old, startMs)
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

        Two writes always go ahead: Off, which also takes the light out of every layer
        until a later write turns it back on or the item that was driving it ends
        (switching a light off must work, whatever is playing), and any write to a light
        the sound layer drives, which takes that light out of the sound layer (it would otherwise
        never respond), stopping the sound layer when it has no lights left.
        """
        deferred = []
        with self.lock:
            off = isinstance(value, (list, tuple)) and len(value) > 3 and (value[0] == 0 or (value[1] == 129 and value[3] == 2))
            power = off or (isinstance(value, (list, tuple)) and len(value) > 1 and value[1] == 129)
            if not power and isinstance(value, (list, tuple)) and len(value) > 3:
                self.knownBase[idx] = list(value)
            if off and self.owner.get(idx, 0) > 0:
                self.poweredOff[idx] = self.ownerPlayer.get(idx)
            elif not off:
                self.poweredOff.pop(idx, None)
            sound = self.layers[LAYER_SOUND]
            if sound is not None and not power and sound.drives(idx) and sound.release([idx]):
                self._endPlayer(LAYER_SOUND, sound, self._nowMs(self.clock()), "manual")
            fade = self.fades.get(idx)
            if fade is not None and fade[3] == 0 and self.clock() > self._absorbUntil:
                # fading back to its base state and a manual command arrives: that's instant
                self._release(idx)
            player = self.ownerPlayer.get(idx)
            ended = player is not None and all(player is not p for p in self.layers.values())
            soundLetGo = isinstance(player, SoundPlayer) and (ended or not player.drives(idx))
            if off or (soundLetGo and self.owner.get(idx, 0) > 0):
                self._release(idx)
            if self.owner.get(idx, 0) > 0:
                if isinstance(value, (list, tuple)) and len(value) > 1:
                    self.baseStates[idx] = list(OFF_BYTES) if value[0] == 0 else list(value)
                blocked = (True, self.lastSent.get(idx))
            else:
                self.mailbox.pop(idx, None)
                self.released.pop(idx, None)
                blocked = (False, None)
            deferred, self._deferred = self._deferred, []
        for d in deferred:
            d()
        self._wake.set()
        return blocked

    def baseFor(self, idx):
        """The state a light returns to when nothing drives it: its revert target while a layer
        drives it, otherwise what it shows."""
        with self.lock:
            if self.owner.get(idx, 0) > 0 and idx in self.baseStates:
                return list(self.baseStates[idx])
            return list(self.knownBase.get(idx) or self.hooks.currentBytes(idx) or []) or None

    def _release(self, idx):
        """Forget a light's layer state: it is the base's again, with nothing to fade back."""
        self.fades.pop(idx, None)
        self.owner.pop(idx, None)
        self.ownerPlayer.pop(idx, None)
        self.lastCmd.pop(idx, None)
        self.lastSent.pop(idx, None)
        self.baseStates.pop(idx, None)

    def takeMailbox(self):
        with self.lock:
            box, self.mailbox = self.mailbox, {}
            return box

    def hasPending(self):
        return bool(self.mailbox)

    def fadeBase(self, indexes, durMs, now=None, takeFromSound=True):
        """A preset was just recalled (each light's stored value is already the preset's):
        fade the lights no layer is driving from what they show to it, and make it the revert
        target for those a layer is driving. The sound layer lets go of them first, as for any
        manual write (takeFromSound False: the preset just set them following sound). Returns
        the indexes handled; the caller sends the rest the usual way."""
        def run(nowMs):
            sound = self.layers[LAYER_SOUND]
            taken = [idx for idx in indexes if takeFromSound and sound is not None and sound.drives(idx)]
            if taken and sound.release(taken):
                self._endPlayer(LAYER_SOUND, sound, nowMs, "manual")
            for idx in taken:
                if self.ownerPlayer.get(idx) is sound:
                    # showing the sound's look: fade from that like a light no layer drives
                    self.owner.pop(idx, None)
                    self.ownerPlayer.pop(idx, None)
            done = []
            for idx in indexes:
                to = self.hooks.currentBytes(idx)
                if not isinstance(to, (list, tuple)) or len(to) < 4:
                    continue
                to = list(OFF_BYTES) if to[0] == 0 else list(to)
                if to[0] != 0:
                    self.knownBase[idx] = list(to)
                fade = self.fades.get(idx)
                driven = self.owner.get(idx, 0) in (LAYER_SOUND, LAYER_SHOW, LAYER_EFFECT, LAYER_OVERRIDE) and not (fade and fade[3] == 0)
                if driven:
                    self.baseStates[idx] = to
                    done.append(idx)
                    continue
                fromCmd = self.lastCmd.get(idx) if fade else None
                fromCmd = fromCmd or self.hooks.shownCommand(idx)
                if durMs <= 0 or fromCmd is None or bytesToCommand(to) is None:
                    continue
                self.baseStates[idx] = to
                self.owner[idx] = LAYER_FADE
                self.ownerPlayer.pop(idx, None)
                self.lastCmd[idx] = fromCmd
                self.fades[idx] = (nowMs, float(durMs), fromCmd, 0)
                done.append(idx)
            return done
        return self._command(run, now)

    def anyActive(self):
        with self.lock:
            return any(p is not None for p in self.layers.values()) or bool(self.effectQueue) or bool(self.fades)

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

    def _beginPlayer(self, layer, player, nowMs, old=None, posMs=0.0):
        """Put a player on its layer. Its fade in (its own, else the global) is the only blending it
        gets: the player is held on its first frame for that long and then runs, so the keyframes
        and cues inside it play exactly as written. Restarting the same animation cuts."""
        if old is not None and player.kind == "animation" == old.kind and player.name == old.name:
            player.fadeInMs = 0
        hold = player.fadeInMs if player.fadeInMs is not None else \
            (self.hooks.fadeInMs() if hasattr(self.hooks, "fadeInMs") else 0)
        player.entryMs = nowMs
        if isinstance(player, SequencePlayer):
            player.start(nowMs + max(0, hold), posMs)
        else:
            player.start(nowMs + max(0, hold))
        self.layers[layer] = player
        self._status("start", layer, player)

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
                self._absorbUntil = self.clock() + 0.5
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
                    self.knownBase[idx] = list(b)
        self._status("end", layer, player, reason=reason)
        if layer == LAYER_EFFECT and self.effectQueue and self.layers[LAYER_EFFECT] is None:
            self._beginPlayer(LAYER_EFFECT, self.effectQueue.pop(0), nowMs, player)

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
        for layer in (LAYER_SOUND, LAYER_SHOW, LAYER_EFFECT, LAYER_OVERRIDE):
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

        playing = set(id(p) for p in self.layers.values() if p is not None)
        for idx in [i for i, p in self.poweredOff.items() if id(p) not in playing]:
            del self.poweredOff[idx]
        lights = set(self.owner)
        for out, _ in frames.values():
            lights.update(out)
        queued = False
        globalIn = self.hooks.fadeInMs() if hasattr(self.hooks, "fadeInMs") else 0
        globalBack = self.hooks.handbackMs() if hasattr(self.hooks, "handbackMs") else 0
        stepMs = 1000.0 / HANDBACK_FPS
        for idx in lights:
            win = 0
            if not self.hooks.isLocked(idx) and idx not in self.poweredOff:
                for layer in (LAYER_OVERRIDE, LAYER_EFFECT, LAYER_SHOW, LAYER_SOUND):
                    if layer in frames and idx in frames[layer][0]:
                        win = layer
                        break
            prev = self.owner.get(idx, 0)
            player = self.layers[win] if win > 0 else None
            oldPlayer = self.ownerPlayer.get(idx)
            fade = self.fades.get(idx)
            if win > 0 and prev == 0 and idx not in self.baseStates:
                # A revert queued moments ago may not have reached the light's stored value yet
                # the light's stored value can be a frame a layer sent (after Off and On during a
                # show it holds the last one), so the last base write wins over it
                cur = self.released.pop(idx, None) or self.knownBase.get(idx) or self.hooks.currentBytes(idx)
                if isinstance(cur, (list, tuple)) and len(cur) > 3:
                    self.baseStates[idx] = list(cur)
            # Who drives the light now, against who did (a fade in progress counts as heading for its target)
            was = fade[3] if fade is not None else (0 if prev == LAYER_FADE else prev)
            changed = win != was or (win > 0 and player is not oldPlayer)
            if changed:
                # Fades belong to transitions between items, never to what happens inside one: a
                # light an item picks up after it started, or drops while it keeps running, cuts
                # (the item's own cues and fades decide how it looks).
                # An item letting go (it ended, or a sequence reverted on pause) hands its lights
                # back with its Fade back, to the base or to a lower layer that is still running.
                handBack = oldPlayer is not None and win < was and (
                    all(oldPlayer is not p for p in self.layers.values()) or _revertsOnPause(oldPlayer))
                if handBack:
                    dur = oldPlayer.fadeOutMs if getattr(oldPlayer, "fadeOutMs", None) is not None else globalBack
                elif win > 0 and (win > was or player is not oldPlayer):   # an item starting: its fade in
                    starting = nowMs - getattr(player, "entryMs", -1e12) < 1.0
                    dur = (player.fadeInMs if player.fadeInMs is not None else globalIn) if starting else 0
                else:
                    dur = 0
                fromCmd = self.lastCmd.get(idx)
                if fromCmd is None and prev == 0:
                    fromCmd = self.hooks.shownCommand(idx) if hasattr(self.hooks, "shownCommand") else None
                self.fades.pop(idx, None)
                fade = None
                if dur > 0 and fromCmd is not None and not (win == 0 and self.baseStates.get(idx) is None):
                    fade = self.fades[idx] = (nowMs, float(dur), fromCmd, win)
                if win > 0:
                    self.ownerPlayer[idx] = player
                else:
                    self.ownerPlayer.pop(idx, None)
            if fade is not None:
                start, dur, fromCmd, _ = fade
                k = int((nowMs - start) // stepMs) + 1
                t = min(1.0, k * stepMs / dur)
                target = frames[win][0][idx] if win > 0 else bytesToCommand(self.baseStates.get(idx))
                if t >= 1.0 or target is None:
                    del self.fades[idx]
                    fade = None
                    if win > 0:
                        self.lastCmd.pop(idx, None)  # make sure the layer's own frame goes out next
                else:
                    cmd = blendCommands(fromCmd, target, t)
                    self.owner[idx] = win if win > 0 else (prev or LAYER_FADE)
                    if cmd != self.lastCmd.get(idx):
                        self.lastCmd[idx] = cmd
                        b = self.hooks.encode(idx, cmd)
                        if b is not None and b != self.lastSent.get(idx):
                            self.mailbox[idx] = (list(b), True)
                            self.lastSent[idx] = list(b)
                            queued = True
                    continue  # while fading to base the light stays owned, so base writes become the target
            if win > 0:
                self.owner[idx] = win
                self.ownerPlayer[idx] = player
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
                self.ownerPlayer.pop(idx, None)
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
