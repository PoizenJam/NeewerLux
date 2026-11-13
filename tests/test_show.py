"""Behaviour tests for brightness limits, locked lights, layers and sequences.

Runs the real NeewerLux code through tests/harness.py (fake Bluetooth). The drift
test runs the compositor on a virtual clock; --long also runs a 5-minute wall-clock
sequence through the worker and the fake lights.
Run: python tests/test_show.py [--long] [--drift-only]
"""
import json
import os
import random
import sys
import time
import traceback
import urllib.request

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # the render strip test creates a Qt app
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import harness  # noqa: E402

KEY, FILL, RIM, AMB = 0, 1, 2, 3
RESULTS = []


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def bri(d):
    """Brightness byte of a CCT, HSI or ANM write."""
    if d is None:
        return None
    return d[6] if d[1] == 134 else d[3]


def hsi(hue, sat=100, b=100):
    return {"mode": "HSI", "hue": hue, "sat": sat, "bri": b}


def stepSequence(name, steps, stepMs=500, target="*", **extra):
    """State cues on one target, one hue per step, every stepMs."""
    cues = [{"at_ms": i * stepMs, "target": target, "state": hsi(h, 100, 60)} for i, h in enumerate(steps)]
    seq = {"format": 1, "name": name, "duration_ms": len(steps) * stepMs, "cues": cues}
    seq.update(extra)
    return seq


def hueOf(d):
    return d[3] + (d[4] << 8) if d and d[1] == 134 else None


def writesFor(rig, i, since=0.0):
    return [(t, d) for t, m, d in rig.rec.snapshot() if m == rig.mac(i) and t >= since]


def waitFor(rig, i, since, done, timeout):
    """Writes to light i since `since`, once one satisfies done(bytes) or the timeout passes.
    Windows schedules the worker less tightly than Linux, so fixed short windows are flaky."""
    end = time.monotonic() + timeout
    while True:
        w = [d for t, d in writesFor(rig, i, since)]
        if any(done(d) for d in w) or time.monotonic() > end:
            time.sleep(0.1)  # anything sent just after still counts
            return [d for t, d in writesFor(rig, i, since)]
        time.sleep(0.02)


class StubWindow:
    """Just enough of MainWindow for the slider send path."""

    class _Sig:
        def emit(self, *a):
            pass

    def __init__(self, rows):
        self.rows = rows
        self._tableUpdateSignal = self._Sig()
        self._logSignal = self._Sig()
        self._sequenceListSignal = self._Sig()
        self._lightPowerSignal = self._Sig()

    def selectionSnapshot(self):
        return list(self.rows)


# ---------------------------------------------------------------------------- tests

def t_maxBrightnessHTTP(rig):
    rig.setShowPrefs(KEY, maxBri=40)
    rig.get("light=1&mode=CCT&temp=56&bri=100", 0.5)
    check(bri(rig.rec.last(rig.mac(KEY))) == 40, "key CCT not clamped to 40: " + str(rig.rec.last(rig.mac(KEY))))
    rig.get("light=1&mode=HSI&hue=10&sat=100&bri=90", 0.5)
    check(bri(rig.rec.last(rig.mac(KEY))) == 40, "key HSI not clamped to 40")
    rig.get("light=2&mode=CCT&temp=56&bri=100", 0.5)
    check(bri(rig.rec.last(rig.mac(FILL))) == 100, "fill should be unclamped")


def t_maxBrightnessAnimationAndSequence(rig):
    rig.setShowPrefs(KEY, maxBri=40)
    rig.get("animate=Strobe|1|10|100|true|2", 0.8)
    keyB = [bri(d) for _, d in writesFor(rig, KEY) if d[1] != 129]
    check(keyB and max(keyB) <= 40, "animation exceeded key limit: " + str(keyB))
    check(max(bri(d) for _, d in writesFor(rig, FILL)) == 100, "fill should reach 100")
    rig.rec.clear()
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": stepSequence("clamp", [0, 120], 300)}, 0.9)
    keyB = [bri(d) for _, d in writesFor(rig, KEY)]
    check(keyB and max(keyB) <= 40, "sequence exceeded key limit: " + str(keyB))


def t_minBrightness(rig):
    rig.setShowPrefs(FILL, minBri=20)
    rig.get("light=2&mode=CCT&temp=56&bri=5", 0.5)
    check(bri(rig.rec.last(rig.mac(FILL))) == 20, "fill floor not applied")
    rig.get("light=2&mode=CCT&temp=56&bri=0", 0.5)
    check(bri(rig.rec.last(rig.mac(FILL))) == 0, "0% must pass the floor")


def t_globalDefaultLimit(rig):
    rig.nl.envMaxBri = 50
    try:
        rig.get("light=4&mode=CCT&temp=56&bri=90", 0.5)
        check(bri(rig.rec.last(rig.mac(AMB))) == 50, "global default ceiling not applied")
        rig.setShowPrefs(AMB, maxBri=70)
        rig.get("light=4&mode=CCT&temp=56&bri=90", 0.5)
        check(bri(rig.rec.last(rig.mac(AMB))) == 70, "per-light limit should override the global default")
    finally:
        rig.nl.envMaxBri = 100


def t_slidersExempt(rig):
    nl = rig.nl
    rig.setShowPrefs(KEY, maxBri=30)
    nl.mainWindow = StubWindow([KEY])
    try:
        nl.sendValue = [120, 135, 2, 100, 56, 157]
        nl.threadAction = "send"
        nl.workerWakeEvent.set()
        time.sleep(0.9)
    finally:
        nl.mainWindow = None
    check(bri(rig.rec.last(rig.mac(KEY))) == 100, "manual slider path must be exempt: " + str(rig.rec.last(rig.mac(KEY))))


def t_lockedLight(rig):
    rig.setShowPrefs(KEY, locked=True)
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": stepSequence("locked", [0, 60, 120], 400)}, 0.6)
    check(not writesFor(rig, KEY), "locked key received sequence writes")
    check(hueOf(rig.rec.last(rig.mac(FILL))) in (0, 60), "fill should follow the sequence")
    rig.get("light=1&mode=CCT&temp=40&bri=33", 0.4)
    check(bri(rig.rec.last(rig.mac(KEY))) == 33, "manual command to a locked light must go through during a sequence")
    rig.get("animate=Strobe|1|10|100|true|2||effect||*", 0.6)
    check(all(d[1] == 135 for _, d in writesFor(rig, KEY)), "locked key received effect writes")


def t_roleTargets(rig):
    nl = rig.nl
    check(nl.returnLightIndexesFromMacAddress("@rim") == [RIM], "@rim")
    check(nl.returnLightIndexesFromMacAddress("@left") == [FILL, AMB], "@left in sweep order: " + str(nl.returnLightIndexesFromMacAddress("@left")))
    check(nl.returnLightIndexesFromMacAddress("@right") == [RIM, KEY], "@right in sweep order")
    check(nl.returnLightIndexesFromMacAddress("@rim.right") == [RIM], "@rim.right")
    check(nl.returnLightIndexesFromMacAddress("@rim.left") == [], "@rim.left is empty on this rig")
    check(nl.returnLightIndexesFromMacAddress("@all") == [FILL, AMB, RIM, KEY], "@all in sweep order")
    check(nl.returnLightIndexesFromMacAddress("@key;3") == [KEY, RIM], "mixed list")
    check(nl.returnLightIndexesFromMacAddress("@bogus") == [], "unknown role matches nothing")


def t_positionTargetsAndSweep(rig):
    """1.3.3: depth (front, beside, back) and height (low, middle, high) next to side; targets
    combine with dots; automatic sweep order follows position; saved, shown and refused."""
    nl = rig.nl
    S = "/NeewerLux/settings"
    try:
        _positionChecks(rig, nl, S)
    finally:  # put the files back to the harness rig, so later reloads don't pick this up
        for i, (mac, _, prefs) in enumerate(harness.RIG):
            rig.post(S, {"action": "set_light", "light": i, "settings": dict(prefs, depth="beside", height="middle")})


def _positionChecks(rig, nl, S):
    # the harness rig sets explicit sweep orders; position settings for this test
    layout = {KEY: ("right", "front", "middle"), FILL: ("left", "front", "low"),
              RIM: ("right", "back", "high"), AMB: ("left", "back", "middle")}
    for i, (side, depth, height) in layout.items():
        # the harness keeps roles in memory only, and set_light reloads the light files, so send the role too
        settings = dict(harness.RIG[i][2], side=side, depth=depth, height=height, order=0)
        r = rig.post(S, {"action": "set_light", "light": i, "settings": settings})
        check(r["success"], "set_light position: " + str(r))
    R = nl.returnLightIndexesFromMacAddress
    check(R("@front") == [FILL, KEY], "@front in sweep order: " + str(R("@front")))
    check(R("@back") == [AMB, RIM], "@back")
    check(R("@high") == [RIM] and R("@low") == [FILL] and R("@middle") == [AMB, KEY], "heights")
    check(R("@back.left") == [AMB] and R("@front.right.middle") == [KEY] and R("@rim.high") == [RIM], "combinations: %s %s %s" % (R("@back.left"), R("@front.right.middle"), R("@rim.high")))
    check(R("@beside") == [], "nobody beside you")
    # automatic order: left to right, then front to back
    check(R("@all") == [FILL, AMB, KEY, RIM], "auto sweep order by position: " + str(R("@all")))
    # a set order still wins
    rig.post(S, {"action": "set_light", "light": RIM, "settings": dict(harness.RIG[RIM][2], side="right", depth="back", height="high", order=1)})
    check(R("@all")[0] == RIM, "a set sweep order comes first")
    # shown everywhere the side is
    lj = rig.getJSON("list_json")
    entry = [l for l in lj["lights"] if l.get("role") == "fill"][0]
    check(entry.get("depth") == "front" and entry.get("height") == "low", "list_json: " + str(entry))
    st = [l for l in rig.getJSON("status_json")["lights"] if l["role"] == "rim"][0]
    check(st.get("depth") == "back" and st.get("height") == "high", "status_json")
    g = rig.post(S, {"action": "get"})
    check(g["depths"] == ["front", "beside", "back"] and g["heights"] == ["low", "middle", "high"], "settings get lists the choices")
    # saved in the light's file and read back
    sidecar = os.path.join(rig.workdir, "light_prefs", rig.mac(RIM).replace(":", ""))
    fields = open(sidecar, encoding="utf-8").read().split("|")
    check(fields[12:14] == ["back", "high"], "sidecar fields: " + str(fields))
    nl.lightShowPrefs.clear()
    nl.loadLightAliases()
    check(nl.getLightShowPref(RIM, "depth") == "back" and nl.getLightShowPref(RIM, "height") == "high", "reloaded from the file")
    # bad values are refused
    r = rig.post(S, {"action": "set_light", "light": KEY, "settings": {"depth": "under", "height": "tall"}})
    check(not r["success"] and len(r["errors"]) == 2, "bad position refused: " + str(r))
    # the timeline editor offers the new targets
    choices = [v for _, v in nl.SequenceEditorHost().targetChoices()] if hasattr(nl, "SequenceEditorHost") else []
    check(not choices or all(t in choices for t in ("@front", "@beside", "@back", "@low", "@middle", "@high")), "editor target choices")


def t_animationModeValidation(rig):
    """A keyframe light without a known mode is refused on save instead of silently not playing."""
    A = "/NeewerLux/animate"
    bad = {"name": "Harness Bad Mode", "keyframes": [{"hold_ms": 500, "fade_ms": 0, "lights": {"*": {"mode": "SPARKLE", "bri": 50}}}]}
    r = rig.post(A, {"action": "save", "animation": bad, "overwrite": True})
    check(not r["success"] and "SPARKLE" in r["errors"][0], "an unknown mode is refused: " + str(r))
    bad["keyframes"][0]["lights"]["*"] = {"hue": 10}
    r = rig.post(A, {"action": "save", "animation": bad, "overwrite": True})
    check(not r["success"], "a missing mode is refused")
    good = dict(bad, keyframes=[{"hold_ms": 500, "fade_ms": 0, "lights": {"*": {"mode": "ANM", "scene": 4, "bri": 50}, "2": {"mode": "OFF"}}}])
    r = rig.post(A, {"action": "save", "animation": good, "overwrite": True})
    check(r["success"], "ANM and OFF are accepted: " + str(r))
    # SCENE is another name for ANM, and plays
    scene = {"name": "Harness Bad Mode", "keyframes": [{"hold_ms": 600, "fade_ms": 0, "lights": {"*": {"mode": "SCENE", "scene": 4, "bri": 50}}}]}
    r = rig.post(A, {"action": "save", "animation": scene, "overwrite": True})
    check(r["success"], "SCENE is accepted: " + str(r))
    t0 = time.monotonic()
    rig.get("animate=Harness%20Bad%20Mode|1|10|100|false|||effect", 0.4)
    check(any(d[1] == 136 for _, d in writesFor(rig, FILL, t0)), "a SCENE keyframe sends a scene command")
    rig.post(A, {"action": "delete", "name": "Harness Bad Mode"})


def t_exactAnimationTiming(rig):
    """1.3.3: holds last exactly as long as the file says. v1.3.0 floored them to 50 ms ticks,
    so a 130 ms hold played as 100 ms and speed 3 on a 220 ms hold played as 50 ms."""
    A = "/NeewerLux/animate"
    anim = {"name": "Harness Exact", "loop": True, "keyframes": [
        {"hold_ms": 130, "fade_ms": 0, "lights": {"*": {"mode": "HSI", "hue": 0, "sat": 100, "bri": 100}}},
        {"hold_ms": 130, "fade_ms": 0, "lights": {"*": {"mode": "HSI", "hue": 200, "sat": 100, "bri": 100}}}]}
    rig.post(A, {"action": "save", "animation": anim, "overwrite": True})
    nl = rig.nl
    nl.flashGuardEnabled = False  # hue-only changes at the same brightness, but keep the guard out of the timing
    try:
        t0 = time.monotonic()
        rig.get("animate=Harness%20Exact|1|10|100|true", 2.0)
        rig.get("stop_animate", 0.2)
        w = [(t, hueOf(d)) for t, d in writesFor(rig, FILL, t0) if d[1] == 134]
        changes = [t for (_, a), (t, b) in zip(w, w[1:]) if a != b]
        gaps = sorted(b - a for a, b in zip(changes, changes[1:]))
        med = gaps[len(gaps) // 2] if gaps else 0
        RESULTS.append("    130 ms holds: median %.0f ms between colour changes (v1.3.0 rounded to 100 ms)" % (med * 1000))
        check(0.12 <= med <= 0.14, "130 ms holds played as %.0f ms" % (med * 1000))
        # speed scales evenly: 3x on 130 ms is 43 ms (v1.3.0: the 50 ms minimum)
        t1 = time.monotonic()
        rig.get("animate=Harness%20Exact|2|10|100|true", 1.2)
        rig.get("stop_animate", 0.2)
        w = [(t, hueOf(d)) for t, d in writesFor(rig, FILL, t1) if d[1] == 134]
        changes = [t for (_, a), (t, b) in zip(w, w[1:]) if a != b]
        gaps = sorted(b - a for a, b in zip(changes, changes[1:]))
        med = gaps[len(gaps) // 2] if gaps else 0
        check(0.055 <= med <= 0.075, "speed 2 should give 65 ms holds, got %.0f ms" % (med * 1000))
    finally:
        nl.flashGuardEnabled = True
        rig.post(A, {"action": "delete", "name": "Harness Exact"})


def t_handbackFade(rig):
    """1.3.3: when a layer lets go of a light it fades back instead of cutting (Global
    Preferences, Hand-back fade; a sequence can set its own). Starts and manual commands
    stay instant; brightness moves continuously across a mode change."""
    nl = rig.nl
    nl.handbackFadeMs = 500
    try:
        rig.get("light=*&mode=CCT&temp=56&bri=20", 0.4)  # base: CCT 20%
        seq = stepSequence("hb", [200], 600)              # HSI 200, 100% for 0.6 s, then revert
        t0 = time.monotonic()
        rig.post("/NeewerLux/sequence", {"action": "play", "sequence": seq}, 1.6)
        w = [(t - t0, list(d)) for t, d in writesFor(rig, FILL, t0)]
        hsi = [x for x in w if x[1][1] == 134]
        check(hsi and hsi[0][0] < 0.15, "the sequence starts at once: " + str(w[:2]))
        last = rig.rec.last(rig.mac(FILL))
        check(last[1] == 135 and bri(last) == 20, "ends back on the base state: " + str(last))
        # between the sequence's end (0.6 s) and the base, intermediate frames: HSI with falling
        # saturation and brightness, no dip below the target brightness
        mid = [d for t, d in w if 0.62 < t < 1.2 and d[1] == 134]
        check(len(mid) >= 4, "fades over several frames, got %d: %s" % (len(mid), [d for _, d in w][-8:]))
        sats = [d[5] for d in mid]
        bris = [d[6] for d in mid]
        check(sats == sorted(sats, reverse=True) and min(sats) < 100, "saturation falls towards white: " + str(sats))
        check(bris == sorted(bris, reverse=True) and min(bris) >= 20, "brightness moves down without a dip: " + str(bris))
        tBase = min(t for t, d in w if d[1] == 135 and t > 0.6)
        check(0.4 <= tBase - 0.6 <= 0.75, "the fade takes about 0.5 s, took %.0f ms" % ((tBase - 0.6) * 1000))
        RESULTS.append("    hand-back fade: %d frames, %.0f ms, saturation %s" % (len(mid), (tBase - 0.6) * 1000, sats))
        # a manual command during a hand-back is instant
        rig.post("/NeewerLux/sequence", {"action": "play", "sequence": seq}, 0.7)
        t1 = time.monotonic()
        rig.get("light=2&mode=CCT&temp=40&bri=60", 0.15)
        after = [(t - t1, list(d)) for t, d in writesFor(rig, FILL, t1)]
        check(after and after[-1][1][1] == 135 and bri(after[-1][1]) == 60 and after[-1][0] < 0.12,
              "a manual command during the fade lands at once: " + str(after[-3:]))
        # per-sequence override: 0 = cut
        rig.get("light=*&mode=CCT&temp=56&bri=20", 0.6)
        seq0 = dict(seq, handback_fade_ms=0)
        t2 = time.monotonic()
        rig.post("/NeewerLux/sequence", {"action": "play", "sequence": seq0}, 1.0)
        w2 = [(t - t2, list(d)) for t, d in writesFor(rig, FILL, t2)]
        check(not [d for t, d in w2 if 0.62 < t and d[1] == 134 and d[5] < 100], "handback_fade_ms 0 cuts: " + str(w2[-4:]))
    finally:
        nl.handbackFadeMs = 0


def t_fadeInEverywhere(rig):
    """1.3.3: fades into presets, animations (including one replacing another) and sequences,
    from the global Fade in or each item's own; the item overrides the global."""
    nl = rig.nl
    A = "/NeewerLux/animate"
    try:
        rig.get("light=*&mode=CCT&temp=56&bri=20", 0.4)
        # a preset with its own fade, global off
        nl.fadeInMs = 0
        idx = 1  # preset 2
        rig.post("/NeewerLux/presets", {"action": "save", "index": idx + 1, "fade_ms": 600,
                                        "entries": [{"light": "*", "mode": "CCT", "temp": 3200, "bri": 20}]})
        check(nl.presetFades.get(idx) == 600, "preset fade saved: %r" % nl.presetFades)
        t0 = time.monotonic()
        rig.get("use_preset=2", 0.9)
        w = [(t - t0, list(d)) for t, d in writesFor(rig, FILL, t0) if d[1] == 135]
        temps = [d[4] for _, d in w]
        check(len(temps) >= 6 and temps == sorted(temps, reverse=True) and temps[-1] == 32, "preset fades from 5600K to 3200K: " + str(temps))
        # from the first step, not the request: a busy moment before the recall isn't the fade
        check(0.4 <= w[-1][0] - w[0][0] <= 0.7, "over about 0.6 s: %.0f ms from the first step: %s" % ((w[-1][0] - w[0][0]) * 1000, [(round(t, 3), d[4]) for t, d in w]))
        # a preset without its own fade follows the global
        rig.post("/NeewerLux/presets", {"action": "save", "index": idx + 1, "fade_ms": None,
                                        "entries": [{"light": "*", "mode": "CCT", "temp": 5600, "bri": 20}]})
        check(idx not in nl.presetFades, "fade cleared")
        t1 = time.monotonic()
        rig.get("use_preset=2")
        w = waitFor(rig, FILL, t1, lambda d: d[1] == 135 and d[4] == 56, 1.5)
        temps = [d[4] for d in w if d[1] == 135]
        check(temps and temps[-1] == 56 and set(temps) <= {32, 56}, "global 0: the preset cuts to 5600K: " + str(temps))
        # an animation's own fade in from its file, overridden by the URL
        anim = {"name": "Harness Fade", "loop": True, "fade_in_ms": 500, "keyframes": [
            {"hold_ms": 1000, "fade_ms": 0, "lights": {"*": {"mode": "HSI", "hue": 120, "sat": 100, "bri": 60}}}]}
        rig.post(A, {"action": "save", "animation": anim, "overwrite": True})
        t2 = time.monotonic()
        rig.get("animate=Harness%20Fade|1|10|100|true|||effect", 0.8)
        w = [list(d) for t, d in writesFor(rig, FILL, t2) if d[1] == 134]
        sats = [d[5] for d in w]
        check(len(sats) >= 5 and sats[0] < 50 and sats[-1] == 100, "the animation fades in (saturation rises from white): " + str(sats))
        rig.get("stop_layer=effect", 0.3)
        rig.get("light=*&mode=CCT&temp=56&bri=20", 0.3)
        t3 = time.monotonic()
        rig.get("animate=Harness%20Fade|1|10|100|true|||effect|||0", 0.3)
        w = [list(d) for t, d in writesFor(rig, FILL, t3) if d[1] == 134]
        check(w and w[0][5] == 100, "the URL's fade in 0 overrides the file: " + str(w[:3]))
        # one animation replacing another blends with the global fade in
        nl.fadeInMs = 400
        anim2 = dict(anim, name="Harness Fade 2", keyframes=[{"hold_ms": 1000, "fade_ms": 0, "lights": {"*": {"mode": "HSI", "hue": 240, "sat": 100, "bri": 60}}}])
        anim2.pop("fade_in_ms")
        rig.post(A, {"action": "save", "animation": anim2, "overwrite": True})
        t4 = time.monotonic()
        rig.get("animate=Harness%20Fade%202|1|10|100|true|||effect|replace", 0.6)
        hues = [hueOf(d) for t, d in writesFor(rig, FILL, t4) if d[1] == 134]
        check(len(hues) >= 4 and hues[-1] == 240 and any(120 < h < 240 for h in hues), "replacing blends hue 120 to 240: " + str(hues))
        rig.get("stop_layer=effect", 0.6)
        # a sequence's own fade in
        nl.fadeInMs = 0
        rig.get("light=*&mode=CCT&temp=56&bri=20", 0.6)
        seq = stepSequence("fin", [200], 800, fade_in_ms=400)
        t5 = time.monotonic()
        rig.post("/NeewerLux/sequence", {"action": "play", "sequence": seq}, 0.6)
        w = [list(d) for t, d in writesFor(rig, FILL, t5) if d[1] == 134]
        check(len(w) >= 4 and w[0][5] < 60 and w[-1][5] == 100, "the sequence fades in: " + str([d[5] for d in w]))
    finally:
        nl.fadeInMs = 0
        nl.presetFades.pop(1, None)
        for n in ("Harness Fade", "Harness Fade 2"):
            rig.post(A, {"action": "delete", "name": n})


def t_fadesOnlyBetweenItems(rig):
    """1.3.3: Fade in and Fade back smooth the change into and out of an item, never what happens
    inside it. An animation's hard cuts stay hard cuts (it is held on its first frame while it fades
    in, then runs as written), lights a sequence picks up or drops while running cut, and
    restarting the same animation cuts."""
    nl = rig.nl
    programmed = {(0, 100, 100), (0, 0, 100), (0, 100, 5)}  # Ambulance: red, white, dim red

    def hsi(t0, a, b):
        return [(hueOf(d), d[5], d[6]) for t, d in writesFor(rig, FILL, t0) if d[1] == 134 and a <= t - t0 <= b]
    try:
        runs = {}
        for fin, back in ((0, 0), (400, 500)):
            nl.fadeInMs, nl.handbackFadeMs = fin, back
            rig.get("light=*&mode=CCT&temp=56&bri=20", 0.6)
            tReq = time.monotonic()
            rig.get("light=*&animate=Ambulance", 2.2)
            # windows count from the animation's first write, not the request: a slower request
            # (Windows) would otherwise move its first keyframe in or out of the window
            t0 = writesFor(rig, FILL, tReq)[0][0]
            runs[fin] = hsi(t0, fin / 1000.0 + 0.03, 2.2)
            if fin:
                blend = hsi(t0, 0, fin / 1000.0 - 0.03)
                check(len(blend) >= 4 and blend[-1][1] > blend[0][1], "it fades in from white towards red: " + str(blend))
            rig.get("stop_animation=1", 0.8)
        for fin, vals in runs.items():
            check(len(vals) >= 6 and set(vals) <= programmed,
                  "fade in %d ms: only Ambulance's own colours once it runs, got %s" % (fin, sorted(set(vals) - programmed)))
        check(runs[0][:6] == runs[400][:6], "the same keyframes in the same order with and without fades: %s / %s" % (runs[0][:6], runs[400][:6]))

        # a sequence: Fill joins at 0.4 s and leaves at 0.8 s while the sequence keeps running. With
        # Fade in 0.4 s the sequence holds its first frame for 0.4 s, so those are 0.8 and 1.2 s.
        rig.get("light=*&mode=CCT&temp=56&bri=20", 0.6)
        seq = {"format": 1, "name": "join", "duration_ms": 1400, "cues": [
            {"at_ms": 0, "target": "@key", "state": {"mode": "HSI", "hue": 30, "sat": 100, "bri": 60}},
            {"at_ms": 400, "duration_ms": 400, "target": "@fill", "state": {"mode": "HSI", "hue": 200, "sat": 100, "bri": 60}}]}
        t1 = time.monotonic()
        rig.post("/NeewerLux/sequence", {"action": "play", "sequence": seq}, 1.6)
        w = [(t - t1, list(d)) for t, d in writesFor(rig, FILL, t1)]
        hsiW = [(round(t, 2), hueOf(d), d[5]) for t, d in w if d[1] == 134]
        check(hsiW and all((h, sat) == (200, 100) for _, h, sat in hsiW) and 0.75 < hsiW[0][0] < 0.95,
              "Fill cuts to its cue at 0.8 s, no blend: " + str(hsiW))
        back = [d for t, d in w if t > 1.15 and d[1] == 135]
        check(back and bri(back[0]) == 20 and len(back) == 1, "and cuts back when its cue ends: " + str(w))
        keyW = [list(d) for t, d in writesFor(rig, KEY, t1)]
        check(len([d for d in keyW if d[1] == 134 and d[5] < 100]) >= 3, "Key still fades in at the start: " + str(keyW[:5]))
        tail = []
        end = time.monotonic() + 3.0  # waits for the outcome: Windows schedules the worker less tightly
        while time.monotonic() < end and not (len(tail) >= 4 and tail[-1][1][1] == 135):
            time.sleep(0.02)
            tail = [(round(t - t1, 3), d) for t, d in writesFor(rig, KEY, t1 + 1.8)]
        check(len(tail) >= 4 and tail[-1][1][1] == 135, "and fades back at the end (s after play, bytes): " + str(tail[-4:]))

        # restarting the same animation cuts
        nl.fadeInMs = 400
        rig.get("animate=Ambulance|1|10|100|true|||effect", 0.8)
        t2 = time.monotonic()
        rig.get("animate=Ambulance|1|10|100|true|||effect|replace", 0.6)
        vals = hsi(t2, 0, 0.6)
        check(vals and set(vals) <= programmed, "a restart cuts: " + str(vals))
        rig.get("stop_layer=effect", 0.8)
    finally:
        nl.fadeInMs, nl.handbackFadeMs = 0, 0


def t_blendCommands(rig):
    """Pure checks of the fade maths."""
    b = rig.nl.show.blendCommands
    check(b({"mode": "HSI", "hue": 350, "sat": 100, "bri": 50}, {"mode": "HSI", "hue": 10, "sat": 100, "bri": 50}, 0.5)["hue"] == 0, "hue goes the short way round")
    m = b({"mode": "CCT", "temp": 56, "bri": 80}, {"mode": "HSI", "hue": 120, "sat": 100, "bri": 40}, 0.5)
    check(m == {"mode": "HSI", "hue": 120, "sat": 50, "bri": 60}, "CCT to HSI starts white: " + str(m))
    m = b({"mode": "HSI", "hue": 120, "sat": 100, "bri": 40}, {"mode": "CCT", "temp": 56, "bri": 80}, 0.5)
    check(m == {"mode": "HSI", "hue": 120, "sat": 50, "bri": 60}, "HSI to CCT fades to white first: " + str(m))
    m = b({"mode": "ANM", "scene": 4, "bri": 50}, {"mode": "CCT", "temp": 56, "bri": 10}, 0.5)
    check(m == {"mode": "ANM", "scene": 4, "bri": 30}, "scene brightness moves first: " + str(m))
    check(b({"mode": "OFF"}, {"mode": "CCT", "temp": 56, "bri": 10}, 0.5)["mode"] == "CCT", "power commands cut")


def t_effectOverPartOfRigRejoinsInSync(rig):
    hues = [0, 40, 80, 120, 160, 200, 240, 280, 320, 20, 60, 100]
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": stepSequence("sync", hues, 500)}, 0.7)
    tEffect = time.monotonic()
    rig.get("animate=Strobe|1|10|100|true|3||effect||@rim", 1.6)
    rimW = writesFor(rig, RIM, tEffect)
    strobe = [d for _, d in rimW if d[5] == 0]  # Strobe is white (sat 0)
    check(len(strobe) >= 4, "rim did not play the effect: " + str(rimW[:4]))
    fillDuring = [d for _, d in writesFor(rig, FILL, tEffect)]
    check(all(d[5] == 100 for d in fillDuring), "fill must stay on the sequence during a rim effect")
    lastStrobeT = max(t for t, d in rimW if d[5] == 0)
    back = [(t, d) for t, d in rimW if t > lastStrobeT]
    check(back, "rim never returned to the sequence")
    tBack, dBack = back[0]
    # In sync: the rim comes back on the hue the fill was showing at that moment
    fillAtBack = [d for t, d in writesFor(rig, FILL) if t <= tBack + 0.02]
    check(hueOf(dBack) == hueOf(fillAtBack[-1]), "rim rejoined on hue %s, fill was on %s" % (hueOf(dBack), hueOf(fillAtBack[-1])))
    check(tBack - lastStrobeT < 0.25, "rim took %.0f ms to return" % ((tBack - lastStrobeT) * 1000))


def t_revertToPresetAtEnd(rig):
    rig.get("use_preset=2", 0.6)
    preset = [rig.rec.last(rig.mac(i)) for i in range(4)]
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": stepSequence("end", [0, 200], 400)}, 1.2)
    for i in range(4):
        check(rig.rec.last(rig.mac(i)) == preset[i], "light %d did not return to the preset: %s vs %s" % (i, rig.rec.last(rig.mac(i)), preset[i]))


def t_endPreset(rig):
    rig.get("light=*&mode=CCT&temp=56&bri=50", 0.5)
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": stepSequence("endp", [0], 400, end="preset:3")}, 1.0)
    expected = rig.nl.calculateByteString(True, colorMode="CCT", brightness=0, temp=56)  # preset 3: 5600K 0%
    check(rig.rec.last(rig.mac(FILL)) == expected, "end preset:3 not applied: " + str(rig.rec.last(rig.mac(FILL))))


def t_holdAtEnd(rig):
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": stepSequence("hold", [0, 77], 300, end="hold")}, 0.9)
    check(hueOf(rig.rec.last(rig.mac(FILL))) == 77, "end hold should leave the last frame")


def t_pauseRevertsAndResumes(rig):
    rig.get("light=*&mode=CCT&temp=45&bri=25", 0.5)
    base = rig.rec.last(rig.mac(FILL))
    hues = [0, 30, 60, 90, 120, 150, 180, 210]
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": stepSequence("pause", hues, 500)}, 1.25)
    r = rig.post("/NeewerLux/sequence", {"action": "pause"}, 0.3)
    check(r["success"], "pause failed")
    check(rig.rec.last(rig.mac(FILL)) == base, "pause should revert to the base state")
    p1 = rig.getJSON("status_json")["sequence"]["position_ms"]
    time.sleep(0.8)
    p2 = rig.getJSON("status_json")["sequence"]["position_ms"]
    check(p1 == p2, "position moved while paused")
    check(1150 <= p1 <= 1450, "paused at an unexpected position %d" % p1)
    tRes = time.monotonic()
    rig.post("/NeewerLux/sequence", {"action": "resume"}, 0.15)
    after = writesFor(rig, FILL, tRes)
    check(after and hueOf(after[0][1]) == hues[p1 // 500], "resume should continue at the paused cue (hue %s), got %s" % (hues[p1 // 500], after[0][1] if after else None))
    time.sleep(3.2)
    check(rig.rec.last(rig.mac(FILL)) == base, "sequence should end and revert after the resume")


def t_seekAndSetPosition(rig):
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": stepSequence("seek", list(range(0, 360, 10)), 1000)}, 0.2)
    rig.post("/NeewerLux/sequence", {"action": "seek", "ms": 10000}, 0.2)
    pos = rig.getJSON("status_json")["sequence"]["position_ms"]
    check(10150 <= pos <= 10400, "seek landed at %d" % pos)
    check(hueOf(rig.rec.last(rig.mac(FILL))) == 100, "seek should show the cue at 10 s")
    st0 = rig.getJSON("status_json")["sequence"]["position_ms"]
    t0 = time.monotonic()
    r = rig.post("/NeewerLux/sequence", {"action": "set_position", "ms": st0 + 100})
    check(r["correction"] == "slew", "100 ms offset should slew")
    time.sleep(1.0)
    gained = rig.getJSON("status_json")["sequence"]["position_ms"] - st0 - (time.monotonic() - t0) * 1000
    check(30 <= gained <= 75, "slew should gain about 50 ms per second, gained %.0f" % gained)
    r = rig.post("/NeewerLux/sequence", {"action": "set_position", "ms": 30000})
    check(r["correction"] == "jump", "large offset should jump")


def t_effectQueueReplaceFull(rig):
    nl = rig.nl
    rig.post("/NeewerLux/animate", {"action": "play", "name": "Strobe", "loop": True, "maxLoops": 3, "layer": "effect"})
    r = rig.post("/NeewerLux/animate", {"action": "play", "name": "Police Flash", "loop": True, "maxLoops": 1, "layer": "effect"})
    check(r["result"] == "queued", "second effect should queue: " + str(r))
    st = rig.getJSON("status_json")
    check(st["layers"]["effect"]["name"] == "Strobe" and st["layers"]["effect_queue"] == ["Police Flash"], "queue state wrong: " + json.dumps(st["layers"]))
    time.sleep(1.5)  # three Strobe loops (400 ms each since 1.3.3 slowed it under 3 flashes a second)
    st = rig.getJSON("status_json")
    check(st["layers"]["effect"] and st["layers"]["effect"]["name"] == "Police Flash", "queued effect did not start")
    r = rig.post("/NeewerLux/animate", {"action": "play", "name": "Heartbeat", "layer": "effect", "mode": "replace"})
    st = rig.getJSON("status_json")
    check(r["result"] == "playing" and st["layers"]["effect"]["name"] == "Heartbeat", "replace should preempt")
    for _ in range(nl.show.EFFECT_QUEUE_MAX):
        rig.post("/NeewerLux/animate", {"action": "play", "name": "Strobe", "layer": "effect"})
    r = rig.post("/NeewerLux/animate", {"action": "play", "name": "Strobe", "layer": "effect"})
    check(r["success"] is False and r["result"] == "queue_full", "queue should be full: " + str(r))
    rig.post("/NeewerLux/animate", {"action": "stop", "layer": "effect", "clear_queue": True}, 0.3)
    st = rig.getJSON("status_json")
    check(st["layers"]["effect"] is None and not st["layers"]["effect_queue"], "stop with clear_queue")


def t_effectCap(rig):
    rig.nl.effectMaxSeconds = 1
    try:
        rig.get("animate=Police%20Flash|1|10|100|true|0||effect", 0.5)
        check(rig.getJSON("status_json")["layers"]["effect"] is not None, "effect should be playing")
        time.sleep(0.8)
        check(rig.getJSON("status_json")["layers"]["effect"] is None, "looping effect should stop at the cap")
    finally:
        rig.nl.effectMaxSeconds = 30


def t_overrideOverSequence(rig):
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": stepSequence("ovr", [0, 60, 120, 180, 240, 300], 500)}, 0.3)
    rig.get("animate=Strobe|1|10|100|true|2", 1.2)  # legacy URL = override layer; two 440 ms loops
    last = rig.rec.last(rig.mac(FILL))
    check(last[5] == 100 and hueOf(last) in (60, 120, 180), "after the override ends the light must return to the sequence, got " + str(last))
    check(rig.getJSON("status_json")["sequence"]["state"] == "playing", "sequence keeps running under an override")


def t_onInterruptPause(rig):
    seq = stepSequence("oip", [0, 90, 180, 270], 500, on_interrupt="pause")
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": seq}, 0.3)
    rig.get("animate=Strobe|1|10|100|true|2||effect", 0.2)  # 2 loops of 440 ms
    p1 = rig.getJSON("status_json")["sequence"]["position_ms"]
    time.sleep(0.3)
    p2 = rig.getJSON("status_json")["sequence"]["position_ms"]
    check(p1 == p2, "on_interrupt pause should freeze the clock during an effect")
    time.sleep(0.8)
    p3 = rig.getJSON("status_json")["sequence"]["position_ms"]
    check(p3 > p2, "clock should run again after the effect")


def t_baseWriteDuringSequenceBecomesRevertTarget(rig):
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": stepSequence("held", [0, 100, 200], 400)}, 0.3)
    rig.get("light=2&mode=CCT&temp=50&bri=77", 0.3)
    check(all(bri(d) != 77 for _, d in writesFor(rig, FILL)), "a light the sequence drives must not show a manual change")
    time.sleep(1.0)
    check(bri(rig.rec.last(rig.mac(FILL))) == 77, "sequence end should revert the fill to the manual change")


def t_manualCommandStopsAnimationAndReverts(rig):
    # The one intended difference from v1.3.0 (see tests/compare_legacy.py)
    rig.get("light=*&mode=CCT&temp=40&bri=30", 0.5)
    before = rig.rec.last(rig.mac(FILL))
    rig.get("animate=Spotlight|1|5|100", 0.8)
    rig.get("light=1&mode=HSI&hue=200&sat=50&bri=70", 0.6)
    check(hueOf(rig.rec.last(rig.mac(KEY))) == 200, "key should take the manual command")
    for i in (FILL, RIM, AMB):
        check(rig.rec.last(rig.mac(i)) == before, "light %d should revert to its pre-animation state" % i)


def t_postBatchDelivers(rig):
    for n in range(5):
        r = rig.post("/NeewerLux/batch", {"commands": [{"light": "2", "mode": "CCT", "temp": 50, "bri": 10 + n}]}, 0.35)
        check(r["success"], "batch rejected: " + str(r))
        check(bri(rig.rec.last(rig.mac(FILL))) == 10 + n, "POST batch #%d never reached the light" % n)


def t_postPlayEmptyName(rig):
    r = rig.post("/NeewerLux/animate", {"action": "play"})
    check(r["success"] is False, "empty name should fail cleanly: " + str(r))


def t_sequenceValidateSaveListPlay(rig):
    bad = {"format": 1, "name": "bad", "duration_ms": 1000,
           "cues": [{"at_ms": 0, "target": "@rim", "clip": {"name": "No Such Clip"}, "duration_ms": 500},
                    {"at_ms": 100, "state": {"mode": "HSI", "hue": 400}},
                    {"at_ms": 200, "state": {"mode": "RGB"}}]}
    r = rig.post("/NeewerLux/sequence", {"action": "validate", "sequence": bad})
    check(not r["success"] and len(r["errors"]) == 3, "validate should report 3 errors: " + str(r["errors"]))
    check("cue 0" in r["errors"][0] and "No Such Clip" in r["errors"][0], "errors should name the cue: " + r["errors"][0])
    good = stepSequence("Harness Saved", [0, 120], 300)
    good["description"] = "made by the harness"
    r = rig.post("/NeewerLux/sequence", {"action": "save", "sequence": good})
    check(r["success"], "save failed: " + str(r))
    check(os.path.exists(os.path.join(rig.workdir, "light_prefs", "sequences", "Harness Saved.json")), "file not written")
    r = rig.post("/NeewerLux/sequence", {"action": "save", "sequence": good})
    check(not r["success"], "saving over an existing name needs overwrite")
    names = [s["name"] for s in rig.post("/NeewerLux/sequence", {"action": "list"})["sequences"]]
    check("Harness Saved" in names, "saved sequence missing from list")
    rig.get("sequence=play|harness%20saved", 0.3)
    check(rig.getJSON("status_json")["sequence"]["name"] == "Harness Saved", "GET play by lowercased name")
    rig.get("sequence=stop", 0.2)
    check(rig.getJSON("status_json")["sequence"] is None, "GET stop")


def t_clipStretchAndTarget(rig):
    seq = {"format": 1, "name": "clip", "duration_ms": 2000,
           "cues": [{"at_ms": 0, "duration_ms": 2000, "target": "@left",
                     "clip": {"name": "Police Flash", "fit": "stretch", "brightness": 50}}]}
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": seq}, 2.3)
    check(not writesFor(rig, RIM) and not writesFor(rig, KEY), "clip must only touch its target")
    fillB = {bri(d) for _, d in writesFor(rig, FILL)}
    check(fillB and max(fillB - {20}) <= 50, "clip brightness 50%% not applied: " + str(fillB))


def t_docExamplesValidate(rig):
    """Every JSON example in docs/SEQUENCE_FORMAT.md and the shipped example must validate."""
    import re
    doc = open(os.path.join(ROOT, "docs", "SEQUENCE_FORMAT.md"), encoding="utf-8").read()
    checked = 0
    for block in re.findall(r"```json\n(.*?)```", doc, re.S):
        try:
            items = [json.loads(block)]
        except ValueError:
            items = [json.loads(line) for line in block.splitlines() if line.strip()]
        for item in items:
            if "$schema" in item:
                continue
            seqData = item if "cues" in item else {"format": 1, "name": "doc", "duration_ms": 60000, "cues": [item]}
            seq, errors, _ = rig.nl.buildSequence(seqData)
            check(seq is not None, "doc example failed: " + str(errors))
            checked += 1
    check(checked >= 5, "expected several doc examples, found %d" % checked)
    rig.nl.loadAllSequences()
    ex = rig.nl.savedSequences.get("Example - Four Light Demo")
    check(ex is not None, "shipped example sequence missing")
    seq, errors, warnings = rig.nl.buildSequence(ex)
    # the harness rig has no practical light, so only the @practical cues may warn
    others = [w for w in warnings if "'@practical' matches no light" not in w]
    check(seq is not None and not others, "shipped example: %s %s" % (errors, others))


def t_guidSidecar(rig):
    """macOS addresses are GUIDs; their sidecars must still load show settings."""
    guid = "6F3A1C2E-0000-4000-8000-00000000ABCD"
    light = rig.nl.availableLights[AMB]
    oldDevice, oldClient = light[0], light[1]
    # Detach the connection while the address is swapped: otherwise the worker's status poll
    # can subscribe this client under the GUID, and after the swap back the light's replies
    # keep going to the GUID's slot (a test artefact; a real light's address never changes)
    light[1] = ""
    light[0] = rig.nl.sim.SimDevice(guid, oldDevice.name)
    path = os.path.join(rig.workdir, "light_prefs", guid)
    try:
        open(path, "w", encoding="utf-8").write("Ambient||||0|practical|left|0||60|-1|")
        rig.nl.loadLightAliases()
        check(rig.nl.lightShowPrefs.get(guid, {}).get("role") == "practical", "GUID sidecar not loaded")
        check(rig.nl.getLightShowPref(AMB, "maxBri") == 60, "GUID light limit")
    finally:
        light[0] = oldDevice
        light[1] = oldClient
        rig.nl._forgetNotify(guid)
        os.remove(path)
        rig.nl.loadLightAliases()


def t_statusShape(rig):
    st = rig.getJSON("status_json")
    check(set(st) == {"apiVersion", "layers", "sequence", "lights", "flashGuard", "stage", "handbackFadeMs", "fadeInMs", "sound"}, "status keys: " + str(sorted(st)))
    check(set(st["layers"]) == {"sound", "show", "effect", "override", "effect_queue"}, "layers: " + str(sorted(st["layers"])))
    check([l["role"] for l in st["lights"]] == ["key", "fill", "rim", "background"], "roles in status")
    check(all(l["layer"] == "base" for l in st["lights"]), "idle lights are on base")


def t_driftVirtualClock(rig):
    """5-minute sequence on a virtual clock: ticks every 10 ms with up to 8 ms of jitter
    and an occasional 40 ms stall. Every cue onset must land within 20 ms of schedule,
    and the error must not grow over time."""
    show = rig.nl.show

    class Hooks:
        def __init__(self):
            self.sent = []
            self.clock = 0.0

        def resolve(self, target):
            return [0]

        def lightCount(self):
            return 1

        def encode(self, idx, cmd):
            return [cmd.get("hue", 0)]

        def currentBytes(self, idx):
            return [1, 2, 3, 4, 5]

        def isLocked(self, idx):
            return False

        def wake(self):
            pass

        def globalRevert(self):
            return True

        def recallPreset(self, n):
            pass

        def onStatus(self, info):
            pass

    hooks = Hooks()
    vt = [0.0]
    comp = show.ShowCompositor(hooks, clock=lambda: vt[0])
    stepMs = 7300
    n = int(300000 // stepMs)
    seqData = {"format": 1, "name": "drift", "duration_ms": 300000,
               "cues": [{"at_ms": i * stepMs, "state": {"mode": "HSI", "hue": (i * 7) % 360 + 1}} for i in range(n)]}
    seq, errors, _ = show.parseSequence(seqData, lambda c: True)
    check(seq is not None, str(errors))
    player = show.SequencePlayer(seq, hooks.resolve, lambda c: None, lambda i: None)
    comp.playSequence(player, 0, now=0.0)
    rnd = random.Random(7)
    onsets = {}
    k = 0
    while vt[0] < 300.0:
        k += 1
        vt[0] = k * 0.010 + rnd.uniform(0, 0.008) + (0.040 if rnd.random() < 0.002 else 0)
        comp.tick(vt[0])
        box = comp.takeMailbox()
        if 0 in box:
            onsets.setdefault(box[0][0][0], vt[0])
    errs = []
    for i in range(n):
        hue = (i * 7) % 360 + 1
        if hue in onsets:
            errs.append((i * stepMs, onsets[hue] * 1000 - i * stepMs))
    check(len(errs) == n, "missing onsets: %d of %d" % (len(errs), n))
    worst = max(abs(e) for _, e in errs)
    firstHalf = sum(e for t, e in errs if t < 150000) / max(1, len([1 for t, _ in errs if t < 150000]))
    secondHalf = sum(e for t, e in errs if t >= 150000) / max(1, len([1 for t, _ in errs if t >= 150000]))
    RESULTS.append("    virtual 5-minute sequence: %d cue onsets, worst %.1f ms, mean %.1f ms (first half) vs %.1f ms (second half)" % (n, worst, firstHalf, secondHalf))
    check(worst < 20, "cue onset error %.1f ms" % worst)
    check(abs(secondHalf - firstHalf) < 3, "error grows over time")


def t_driftWallClock(rig, seconds):
    """Wall-clock run through the real compositor thread, worker and fake lights.

    Drift is the change in onset error between the first and last 30 cues (it must stay
    under 20 ms). Jitter is reported separately: the 99th percentile must stay under
    20 ms; single spikes from the OS scheduler are reported, not failed."""
    stepMs = 1000
    n = seconds * 1000 // stepMs
    seqData = {"format": 1, "name": "wall", "duration_ms": seconds * 1000,
               "cues": [{"at_ms": i * stepMs, "target": "1", "state": hsi((i * 7) % 360 + 1, 100, 50)} for i in range(n)]}
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": seqData}, seconds + 0.6)
    w = [(t, hueOf(d)) for t, d in writesFor(rig, KEY) if d[1] == 134]
    first = {}
    for t, h in w:
        first.setdefault(h, t)
    t0 = first.get(1)
    errs = []
    for i in range(n):
        h = (i * 7) % 360 + 1
        if h in first:
            errs.append((first[h] - t0) * 1000 - i * stepMs)
    check(len(errs) >= n - 1, "missing onsets in wall-clock run: %d of %d" % (len(errs), n))
    k = min(30, len(errs) // 3)
    med = lambda xs: sorted(xs)[len(xs) // 2]
    drift = med(errs[-k:]) - med(errs[:k])
    ordered = sorted(errs)
    p99 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.99))]
    over = sum(1 for e in errs if e > 20)
    RESULTS.append("    wall-clock %d s sequence: %d cue onsets; drift %.1f ms (median of last %d vs first %d); "
                   "median %.1f ms, p99 %.1f ms, max %.1f ms, %d over 20 ms" % (seconds, len(errs), drift, k, k, med(errs), p99, max(errs), over))
    check(abs(drift) < 20, "drift %.1f ms" % drift)
    check(p99 < 20, "p99 onset error %.1f ms" % p99)


# ----------------------------------------------------------------- 1.3.2: simulator, stage, render

def t_simStateFollowsCommands(rig):
    rig.get("light=1&mode=HSI&hue=200&sat=80&bri=60", 0.4)
    rig.get("light=2&mode=CCT&temp=40&bri=30", 0.4)
    rig.get("light=3&off", 0.4)
    nl = rig.nl
    check(nl.availableLights[KEY][0].state.toCommand() == {"mode": "HSI", "hue": 200, "sat": 80, "bri": 60}, "key state")
    check(nl.availableLights[FILL][0].state.toCommand() == {"mode": "CCT", "temp": 40, "bri": 30}, "fill state")
    check(nl.availableLights[RIM][0].state.toCommand() == {"mode": "OFF"}, "rim off")
    rejected = [(l[0].address, l[0].state.lastRejected) for l in nl.availableLights if l[0].state.rejected]
    check(not rejected, "lights rejected packets: " + str(rejected))


def t_statusPollThroughNotifications(rig):
    # The worker polls every few seconds while idle; a round takes longer on Windows, where
    # short sleeps round up to the 15.6 ms timer tick, so wait for a full round rather than a fixed time
    expected = [["ON" if l[0].state.power else "STBY", 1] for l in rig.nl.availableLights]
    end = time.monotonic() + 12
    while time.monotonic() < end and [l[7] for l in rig.nl.availableLights] != expected:
        time.sleep(0.25)
    statuses = [l[7] for l in rig.nl.availableLights]
    check(statuses == expected, "status poll results %s, lights are %s" % (statuses, expected))
    check(all(rig.nl._notifyClients.get(l[0].address) is l[1] for l in rig.nl.availableLights), "one subscription per light")


def t_cctOnlySplitPackets(rig):
    nl = rig.nl
    nl.availableLights[AMB][5] = True  # behave like an older CCT-only light
    try:
        rig.get("light=4&mode=CCT&temp=45&bri=35", 0.5)
        st = nl.availableLights[AMB][0].state
        check(st.toCommand() == {"mode": "CCT", "temp": 45, "bri": 35} and st.lastKind in ("BRI", "TEMP"), "split CCT: %s %s" % (st.toCommand(), st.lastKind))
        rig.get("light=4&mode=HSI&hue=0&sat=100&bri=50", 0.5)
        check(st.mode == "CCT", "an HSI command must reach a CCT-only light as CCT (fallback), got " + st.mode)
    finally:
        nl.availableLights[AMB][5] = False


def t_cctOnlyDisplayAndRender(rig):
    """A CCT-only light is asked for colour but shows white: the Stage, swatches, status and
    render must show what it was sent, not what was asked for. Uses the real-light display
    path (last written bytes), since only simulated lights report their own state."""
    nl = rig.nl
    nl.availableLights[AMB][5] = True
    try:
        rig.get("light=4&mode=HSI&hue=0&sat=100&bri=50", 0.5)
        mac = nl.availableLights[AMB][0].address
        check(nl._lastWritten[mac][1] == 135, "recorded output should be the converted CCT value: " + str(nl._lastWritten.get(mac)))
        check(nl.availableLights[AMB][3][1] == 134, "the requested HSI value stays in [3] for presets and reverts")
        dev = nl.availableLights[AMB][0]
        real = nl.sim.isSimulated
        nl.sim.isSimulated = lambda d: False if d is dev else real(d)
        try:
            cmd, rgb = nl.getLightDisplayState(AMB)[:2]
            check(cmd["mode"] == "CCT" and cmd["bri"] == 50, "display state of a CCT-only light: " + str(cmd))
            check(abs(rgb[0] - rgb[2]) < 120 and rgb[1] > 60, "a CCT-only light should look white-ish, not red: " + str(rgb))
            del nl._lastWritten[mac]
            check(nl.getLightDisplayState(AMB)[0]["mode"] == "CCT", "before anything is recorded, display converts [3]")
        finally:
            nl.sim.isSimulated = real
        r = nl.renderSequence(stepSequence("cctonly", [240], 300, target="@fill"))
        byRole = {l["role"]: l["id"] for l in r["lights"]}
        ambBase = [c for c in r["changes"][byRole["background"]] if c[4] == "base"]
        check(ambBase and ambBase[0][3] == "CCT", "render base of a CCT-only light should be CCT: " + str(ambBase[:1]))
        r = nl.renderSequence(stepSequence("cctonly2", [240], 300, target="@background"))
        seqCh = [c for c in r["changes"][byRole["background"]] if c[4] == "sequence"]
        check(seqCh and all(c[3] == "CCT" for c in seqCh), "render of colour cues on a CCT-only light: " + str(seqCh[:2]))
    finally:
        nl.availableLights[AMB][5] = False


def t_dimColoursStayVisible(rig):
    show = rig.nl.show
    dim = show.commandToRGB({"mode": "HSI", "hue": 0, "sat": 100, "bri": 3})
    check(dim[0] >= 100, "a light at 3% should still read as lit: " + str(dim))
    check(show.commandToRGB({"mode": "HSI", "hue": 0, "sat": 100, "bri": 0}) == (0, 0, 0), "0% is dark")
    check(show.commandToRGB({"mode": "HSI", "hue": 0, "sat": 100, "bri": 100})[0] == 255, "100% is full colour")


def t_stageTilesAndStatusColours(rig):
    rig.get("light=*&mode=HSI&hue=0&sat=100&bri=100", 0.5)
    tiles = rig.nl.getStageTiles()
    check([t["role"] for t in tiles] == ["fill", "background", "rim", "key"], "stage tiles in sweep order: " + str([t["role"] for t in tiles]))
    check(all(t["rgb"] == (255, 0, 0) and t["linked"] and t["simulated"] for t in tiles), "stage tile colours: " + str([t["rgb"] for t in tiles]))
    st = rig.getJSON("status_json")
    check(all(l["color"] == "#ff0000" and l["mode"] == "HSI" and l["bri"] == 100 for l in st["lights"]), "status_json colours")
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": stepSequence("tiles", [120, 240], 600)}, 0.3)
    check(all(t["layer"] == "show" for t in rig.nl.getStageTiles()), "tiles should show the sequence layer")


def t_renderMatchesPlayback(rig):
    hues = [0, 60, 120, 180, 240, 300]
    seq = stepSequence("rendercheck", hues, 400, target="@left")
    seq["cues"].append({"at_ms": 1000, "duration_ms": 600, "target": "@rim", "clip": {"name": "Heartbeat", "fit": "stretch"}})
    r = rig.post("/NeewerLux/sequence", {"action": "render", "sequence": seq})
    check(r["success"], "render failed: " + str(r.get("errors")))
    byName = {l["role"]: l["id"] for l in r["lights"]}
    fillChanges = r["changes"][byName["fill"]]
    check([c[4] for c in fillChanges].count("sequence") == len(hues), "fill should change once per cue: " + str(fillChanges))
    check(all(c[4] == "base" for c in r["changes"][byName["key"]]), "the key isn't targeted, so it stays on base")
    rimSeq = [c for c in r["changes"][byName["rim"]] if c[4] == "sequence"]
    check(rimSeq and rimSeq[0][0] == 1000 and r["changes"][byName["rim"]][-1][4] == "base", "rim clip window: " + str(r["changes"][byName["rim"]][:3]))
    check(len(r["cues"]) == len(hues) + 1 and r["cues"][-1]["what"].startswith("Heartbeat"), "cue list")
    # Now play it for real and compare the fill's colours, in order, with the render
    tStart = time.monotonic()
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": seq}, 2.8)
    played = []
    for t, d in writesFor(rig, FILL, tStart):
        h = hueOf(d)
        if h is not None and (not played or played[-1] != h):
            played.append(h)
    rendered = [int(c[1][1:3], 16) for c in fillChanges if c[4] == "sequence"]
    check(played[:len(hues)] == hues, "played hues %s" % played)
    check(len(rendered) == len(hues), "rendered %d sequence changes" % len(rendered))


def t_renderRespectsLimitsAndLocks(rig):
    rig.setShowPrefs(FILL, maxBri=30)
    rig.setShowPrefs(RIM, locked=True)
    r = rig.nl.renderSequence(stepSequence("limits", [0, 90], 300))
    byRole = {l["role"]: l["id"] for l in r["lights"]}
    check(all(c[2] <= 30 for c in r["changes"][byRole["fill"]] if c[4] == "sequence"), "render ignored the fill's max brightness")
    check(all(c[4] == "base" for c in r["changes"][byRole["rim"]]), "render drove a locked light")


def t_renderPNG(rig):
    r = rig.post("/NeewerLux/sequence", {"action": "render", "name": "Example - Four Light Demo", "format": "png"})
    check(not r["success"] and "window" in r["errors"][0], "png without the app should explain why: " + str(r))
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        from PySide2.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    url = "http://127.0.0.1:%d/NeewerLux/sequence" % rig.port
    import urllib.request
    req = urllib.request.Request(url, data=json.dumps({"action": "render", "name": "Example - Four Light Demo", "format": "png", "width": 800}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read()
        ctype = resp.headers.get("Content-Type")
    check(ctype == "image/png" and body[:8] == b"\x89PNG\r\n\x1a\n", "png response: %s, %r" % (ctype, body[:8]))
    with open(os.path.join(rig.workdir, "render.png"), "wb") as f:
        f.write(body)
    RESULTS.append("    render strip: %d bytes, saved to %s" % (len(body), os.path.join(rig.workdir, "render.png")))
    del app


def t_addSimulatedRig(rig):
    """Runs last: appends a preset rig to the harness's four lights, then removes it."""
    nl = rig.nl
    before = len(nl.availableLights)
    try:
        added = nl.addSimulatedLights(2, includeCCTOnly=True)
        check(added == 3, "added %d lights" % added)
        newLights = nl.availableLights[before:]
        check([l[0].name for l in newLights] == ["SIM-RGB660-Key", "SIM-RGB660-Fill", "SIM-SNL660-Practical"], "names")
        check([l[8] for l in newLights] == [91, 92, 95], "preferred IDs %s" % [l[8] for l in newLights])
        check(newLights[2][5] is True and newLights[2][4] == [3200, 5600], "CCT-only light takes its model's specs")
        check(nl.getLightShowPref(before + 2, "role") == "practical", "preset role")
        check(nl.addSimulatedLights(2, includeCCTOnly=True) == 0, "adding the same rig twice must not duplicate it")
        check(nl.returnLightIndexesFromMacAddress("91") == [before], "ID 91 resolves to the simulated key")
    finally:
        for l in nl.availableLights[before:]:
            nl.lightShowPrefs.pop(l[0].address.upper(), None)
        del nl.availableLights[before:]


# ----------------------------------------------------------------- 1.3.3: HTTP API fixes

def t_batchKelvin(rig):
    r = rig.post("/NeewerLux/batch", {"commands": [{"light": "2", "mode": "CCT", "temp": 4300, "bri": 40}]}, 0.4)
    check(r["success"], str(r))
    last = rig.rec.last(rig.mac(FILL))
    check(last[1] == 135 and last[4] == 43, "JSON temp in Kelvin: sent " + str(last))
    rig.post("/NeewerLux/batch", {"commands": [{"light": "2", "mode": "CCT", "temp": 50, "bri": 40}]}, 0.4)
    check(rig.rec.last(rig.mac(FILL))[4] == 50, "hundreds of Kelvin still work")


def t_batchCoalescesUnderLoad(rig):
    """A Stream Deck dial: 40 requests as fast as possible, from 4 threads at once. None
    may be refused, and the light must end on the last value sent."""
    import threading as _t
    refused = []
    lock = _t.Lock()
    def burst(start):
        for n in range(start, 40, 4):
            r = rig.post("/NeewerLux/batch", {"commands": [{"light": "2", "mode": "CCT", "temp": 50, "bri": n + 1}]})
            if not r.get("success"):
                with lock:
                    refused.append(r)
    threads = [_t.Thread(target=burst, args=(k,)) for k in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    check(not refused, "batch requests refused: " + str(refused[:2]))
    final = rig.post("/NeewerLux/batch", {"commands": [{"light": "2", "mode": "CCT", "temp": 50, "bri": 77}]}, 0.5)
    check(final["success"] and bri(rig.rec.last(rig.mac(FILL))) == 77, "the last value must win: " + str(rig.rec.last(rig.mac(FILL))))
    writes = [d for _, d in writesFor(rig, FILL) if d[1] == 135]
    check(len(writes) <= 41, "coalescing should never write more often than requested (%d writes)" % len(writes))


def t_getDuringBusyWorkerNotDropped(rig):
    """A light command arriving while the worker is mid-preset used to be dropped after a
    5 s wait; now it's queued and sent as soon as the worker is free."""
    nl = rig.nl
    real = nl.processMultipleSends
    def slow(loop, action, updateGUI=True):
        if action == "slowtest":
            time.sleep(6)  # longer than the old 5 s wait
            return ""
        return real(loop, action, updateGUI)
    nl.processMultipleSends = slow
    try:
        nl.threadAction = "slowtest"
        time.sleep(0.4)  # the worker is now stuck in it
        t0 = time.monotonic()
        rig.get("light=3&mode=HSI&hue=90&sat=100&bri=50")
        check(time.monotonic() - t0 < 1.0, "a light command shouldn't wait for the worker")
        time.sleep(6.5)
    finally:
        nl.processMultipleSends = real
    check(hueOf(rig.rec.last(rig.mac(RIM))) == 90, "queued command never sent: " + str(rig.rec.last(rig.mac(RIM))))


def t_batchStopsOverrideAnimation(rig):
    rig.get("light=*&mode=CCT&temp=40&bri=30", 0.5)
    before = rig.rec.last(rig.mac(FILL))
    rig.get("animate=Spotlight|1|5|100", 0.8)
    check(rig.nl.animationRunning, "animation should be playing")
    rig.post("/NeewerLux/batch", {"commands": [{"light": "1", "mode": "HSI", "hue": 200, "sat": 50, "bri": 70}]}, 0.8)
    check(not rig.nl.animationRunning, "POST batch should stop the override animation, as GET does")
    check(hueOf(rig.rec.last(rig.mac(KEY))) == 200, "key should keep the batch command")
    check(rig.rec.last(rig.mac(FILL)) == before, "other lights revert to their pre-animation state")


def t_batchDuringSequenceBecomesRevertTarget(rig):
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": stepSequence("bseq", [120, 240], 400, target="@all")}, 0.3)
    rig.post("/NeewerLux/batch", {"commands": [{"light": "1", "mode": "CCT", "temp": 3300, "bri": 25}]}, 0.3)
    check(rig.nl.showEngine.status()["sequence"] is not None, "a batch must not stop a sequence")
    rig.post("/NeewerLux/sequence", {"action": "stop"}, 0.5)
    last = rig.rec.last(rig.mac(KEY))
    check(last[1] == 135 and last[3] == 25 and last[4] == 33, "after the sequence the key returns to the batch value: " + str(last))


def t_listJsonStructured(rig):
    rig.get("light=1&mode=CCT&temp=4500&bri=60", 0.4)
    rig.get("light=2&mode=HSI&hue=10&sat=90&bri=30", 0.4)
    data = rig.getJSON("list_json")
    check(data["apiVersion"] == 2 and data["version"] == rig.nl.NEEWERLUX_VERSION, "apiVersion and version")
    key = data["lights"][0]
    check(key["setting"] == {"mode": "CCT", "temp": 4500, "bri": 60}, "setting in Kelvin: " + str(key["setting"]))
    check(key["output"]["mode"] == "CCT" and key["output"]["color"].startswith("#"), "output: " + str(key["output"]))
    check(data["lights"][1]["setting"] == {"mode": "HSI", "hue": 10, "sat": 90, "bri": 30}, "HSI setting")
    check(key["cctRange"] == [3200, 5600] and key["cctOnly"] is False, "capabilities: %s %s" % (key["cctRange"], key["cctOnly"]))
    check(key["role"] == "key" and key["layer"] == "base" and key["power"] in ("on", "standby", None), "show fields and power")
    check(isinstance(key["status"], str), "the display string stays for older clients")
    check(any(sq["name"] == "Example - Four Light Demo" for sq in data["sequences"]), "sequences listed")
    check(rig.getJSON("status_json")["apiVersion"] == 2, "status_json carries apiVersion")


def t_commandsDontWaitForStatusPoll(rig):
    """Status polling reads each light in turn; with slow replies (a real light, or Windows'
    15.6 ms timer) a round takes a while. Light commands and show starts must not wait for it."""
    nl = rig.nl
    old = [l[0].latencyMs for l in nl.availableLights]
    nl.flashGuardEnabled = False  # this test changes colour faster than the guard allows; it measures polling
    try:
        for l in nl.availableLights:
            l[0].latencyMs = (60, 60)  # each status query takes about 60 ms to answer
        worst = 0.0
        for n in range(8):
            time.sleep(0.37)  # land at different points of the poll cycle
            t0 = time.monotonic()
            rig.post("/NeewerLux/batch", {"commands": [{"light": "2", "mode": "CCT", "temp": 50, "bri": 20 + n}]})
            while time.monotonic() - t0 < 2.0 and bri(rig.rec.last(rig.mac(FILL)) or [0] * 8) != 20 + n:
                time.sleep(0.005)
            worst = max(worst, time.monotonic() - t0)
        RESULTS.append("    command latency with 60 ms status replies: worst %.0f ms" % (worst * 1000))
        check(worst < 0.25, "a command waited %.0f ms behind status polling" % (worst * 1000))
        worstSeq = 0.0
        for n in range(6):
            time.sleep(0.41)
            hue = 30 + n * 40
            t0 = time.monotonic()
            rig.post("/NeewerLux/sequence", {"action": "play", "sequence": stepSequence("pollstart", [hue], 300, target="2")})
            while time.monotonic() - t0 < 2.0 and hueOf(rig.rec.last(rig.mac(FILL)) or [0] * 8) != hue:
                time.sleep(0.005)
            worstSeq = max(worstSeq, time.monotonic() - t0)
            rig.post("/NeewerLux/sequence", {"action": "stop"})
        RESULTS.append("    sequence start latency with 60 ms status replies: worst %.0f ms" % (worstSeq * 1000))
        check(worstSeq < 0.25, "a sequence's first cue waited %.0f ms behind status polling" % (worstSeq * 1000))
    finally:
        for l, lat in zip(nl.availableLights, old):
            l[0].latencyMs = lat
        nl.flashGuardEnabled = True


# ----------------------------------------------------------------- 1.3.3: editors over HTTP

def t_presetEditAPI(rig):
    nl = rig.nl
    P = "/NeewerLux/presets"
    n0 = rig.post(P, {"action": "list"})["presets"]
    count = len(n0)
    entries = [{"target": "1", "mode": "HSI", "hue": 120, "sat": 80, "bri": 40},
               {"target": "@rim", "mode": "CCT", "temp": 4300, "bri": 60},
               {"target": "3", "mode": "Scene", "scene": 4, "bri": 30}]
    r = rig.post(P, {"action": "save", "index": 2, "name": "Web Edit", "entries": entries})
    check(r["success"], str(r))
    got = rig.post(P, {"action": "get", "index": 2})["preset"]
    check(got["name"] == "Web Edit" and got["custom"] and not got["global"], "saved preset: " + str(got))
    check(got["entries"][1] == {"target": "@rim", "mode": "CCT", "bri": 60, "temp": 43}, "Kelvin stored as hundreds: " + str(got["entries"][1]))
    check(nl.customLightPresets[1][0] == ["1", [4, 40, 120, 80]], "storage format: " + str(nl.customLightPresets[1][0]))
    text = open(nl.customLightPresetsFile, encoding="utf-8").read()
    check("presetName1=Web Edit" in text and "customPreset1=1|4|40|120|80" in text, "presets file: " + text)
    rig.post(P, {"action": "rename", "index": 2, "name": "Renamed"})
    check(nl.presetNames.get(1) == "Renamed", "rename")
    rig.post(P, {"action": "move", "index": 2, "direction": "left"})
    check(nl.presetNames.get(0) == "Renamed" and nl.customLightPresets[0][0][0] == "1", "move left")
    r = rig.post(P, {"action": "duplicate", "index": 1})
    check(r["preset"]["index"] == 2 and r["preset"]["name"] == "Renamed (copy)" and len(nl.customLightPresets) == count + 1, "duplicate: " + str(r))
    rig.post(P, {"action": "delete", "index": 2})
    check(len(nl.customLightPresets) == count and nl.presetNames.get(0) == "Renamed", "delete")
    r = rig.post(P, {"action": "add"})
    check(r["preset"]["index"] == count + 1 and len(nl.customLightPresets) == count + 1, "add")
    rig.get("light=*&mode=HSI&hue=33&sat=100&bri=44", 0.4)
    r = rig.post(P, {"action": "snapshot", "index": count + 1})
    check(not r["preset"]["global"] and all(e["hue"] == 33 for e in r["preset"]["entries"]), "snapshot: " + str(r["preset"]["entries"][:1]))
    rig.get("light=*&mode=CCT&temp=5600&bri=10", 0.4)
    rig.post(P, {"action": "recall", "index": count + 1}, 1.0)
    check(hueOf(rig.rec.last(rig.mac(RIM))) == 33, "recall over POST")
    rig.post(P, {"action": "delete", "index": count + 1})
    bad = rig.post(P, {"action": "save", "index": 999, "entries": entries})
    check(not bad["success"], "unknown preset refused")
    off = [{"target": "2", "mode": "HSI", "hue": 10, "sat": 100, "bri": 50, "off": True}]
    rig.post(P, {"action": "save", "index": 1, "entries": off})
    check(nl.customLightPresets[0][0][1][0] == 7 and rig.post(P, {"action": "get", "index": 1})["preset"]["entries"][0].get("off"), "an off light survives an edit")


def t_animationEditAPI(rig):
    nl = rig.nl
    A = "/NeewerLux/animate"
    anim = {"name": "Web Anim", "loop": True, "keyframes": [
        {"hold_ms": 200, "fade_ms": 0, "lights": {"*": {"mode": "HSI", "hue": 10, "sat": 100, "bri": 50}}},
        {"hold_ms": 200, "fade_ms": 100, "lights": {"*": {"mode": "HSI", "hue": 200, "sat": 100, "bri": 50}}}]}
    r = rig.post(A, {"action": "save", "animation": anim})
    check(r["success"] and "Web Anim" in nl.savedAnimations, str(r))
    check(not rig.post(A, {"action": "save", "animation": anim})["success"], "saving over an existing name needs overwrite")
    anim["keyframes"][0]["hold_ms"] = 300
    check(rig.post(A, {"action": "save", "animation": anim, "original": "Web Anim"})["success"], "editing in place")
    got = rig.post(A, {"action": "get", "name": "web anim"})["animation"]
    check(got["keyframes"][0]["hold_ms"] == 300, "get returns the saved version")
    anim["name"] = "Web Anim Renamed"
    check(rig.post(A, {"action": "save", "animation": anim, "original": "Web Anim"})["success"], "rename")
    check("Web Anim" not in nl.savedAnimations and not os.path.exists(os.path.join(nl.animationsDir, "Web Anim.json")), "old name removed")
    r = rig.post(A, {"action": "duplicate", "name": "Web Anim Renamed"})
    check(r["animation"] == "Web Anim Renamed (copy)" and r["animation"] in nl.savedAnimations, "duplicate")
    for n in ("Web Anim Renamed", "Web Anim Renamed (copy)"):
        check(rig.post(A, {"action": "delete", "name": n})["success"], "delete " + n)
    check("Web Anim Renamed" not in nl.savedAnimations, "deleted")
    check(not rig.post(A, {"action": "save", "animation": {"name": "x", "keyframes": []}})["success"], "empty animation refused")
    check(rig.post(A, {"action": "reload"})["count"] == len(nl.savedAnimations), "reload")


def t_sequenceEditAPI(rig):
    nl = rig.nl
    S = "/NeewerLux/sequence"
    seq = stepSequence("Web Seq", [10, 20], 300)
    check(rig.post(S, {"action": "save", "sequence": seq})["success"], "save new")
    got = rig.post(S, {"action": "get", "name": "web seq"})
    check(got["success"] and got["sequence"]["name"] == "Web Seq", "get")
    seq["name"] = "Web Seq 2"
    r = rig.post(S, {"action": "save", "sequence": seq, "original": "Web Seq"})
    check(r["success"] and "Web Seq" not in nl.savedSequences and "Web Seq 2" in nl.savedSequences, "rename: " + str(r))
    check(len(nl._sequenceFilesNamed("Web Seq")) == 0 and len(nl._sequenceFilesNamed("Web Seq 2")) == 1, "files follow the rename")
    nl.loadAllSequences()
    check("Web Seq" not in nl.savedSequences, "the old name doesn't come back on reload")
    rig.post(S, {"action": "play", "name": "Web Seq 2"}, 0.2)
    check(rig.post(S, {"action": "delete", "name": "Web Seq 2"})["success"], "delete")
    check(nl.showEngine.status()["sequence"] is None, "deleting the playing sequence stops it")
    check("Web Seq 2" not in nl.savedSequences and not nl._sequenceFilesNamed("Web Seq 2"), "deleted")


# ----------------------------------------------------------------- 1.3.3: flash guard

FAST = {"name": "Harness Fast Strobe", "loop": True, "keyframes": [
    {"hold_ms": 80, "fade_ms": 0, "lights": {"*": {"mode": "HSI", "hue": 0, "sat": 0, "bri": 100}}},
    {"hold_ms": 80, "fade_ms": 0, "lights": {"*": {"mode": "HSI", "hue": 0, "sat": 0, "bri": 0}}}]}


def _writtenFlashes(rig, i, since):
    show = rig.nl.show
    samples = [(t, show.bytesToCommand(list(d))) for t, d in writesFor(rig, i, since) if d[1] in (134, 135)]
    return show.analyzeFlashes(samples)


def t_flashGuardLimitsOutput(rig):
    nl = rig.nl
    rig.post("/NeewerLux/animate", {"action": "save", "animation": FAST, "overwrite": True})
    try:
        check(nl.flashGuardEnabled, "the flash guard is on by default")
        held0 = rig.getJSON("status_json")["flashGuard"]["held"]
        t0 = time.monotonic()
        rig.post("/NeewerLux/animate", {"action": "play", "name": FAST["name"], "loop": True, "layer": "effect", "rate": 20}, 3.0)
        rig.post("/NeewerLux/animate", {"action": "stop", "layer": "effect"}, 0.3)
        got = _writtenFlashes(rig, FILL, t0)
        st = rig.getJSON("status_json")["flashGuard"]
        RESULTS.append("    6 flashes/s animation with the guard on: lights got %.1f flashes/s at most, %d frames held"
                       % (got["flashes"], st["held"] - held0))
        check(got["flashes"] <= 3, "the guard let %.1f flashes a second through" % got["flashes"])
        # evenly spread, not three quick flashes then a pause: gaps between brightness changes
        show = nl.show
        lum = [(t, show.flashLevel(show.bytesToCommand(list(d)))[0]) for t, d in writesFor(rig, FILL, t0) if d[1] in (134, 135)]
        changes = [t for (_, a), (t, b) in zip(lum, lum[1:]) if abs(a - b) >= 0.1]  # time of the write that changed it
        gaps = sorted(b - a for a, b in zip(changes, changes[1:]))
        RESULTS.append("    gaps between flashes: shortest %.0f ms, median %.0f ms" % (gaps[0] * 1000, gaps[len(gaps) // 2] * 1000))
        check(gaps and gaps[0] >= 0.17, "flashes should be spread out, shortest gap %.0f ms" % (gaps[0] * 1000))
        check(st["enabled"] and st["held"] > held0, "status_json reports held frames")
        # off: the same animation flashes at its own rate (so the guard is what limited it)
        r = rig.post("/NeewerLux/settings", {"action": "set_global", "settings": {"flashGuardEnabled": False}})
        check(r["success"] and not nl.flashGuardEnabled, "turning it off over HTTP")
        check("flashGuard=0" in open(nl.globalPrefsFile, encoding="utf-8").read(), "off is saved as flashGuard=0")
        t1 = time.monotonic()
        rig.post("/NeewerLux/animate", {"action": "play", "name": FAST["name"], "loop": True, "layer": "effect", "rate": 20}, 2.0)
        rig.post("/NeewerLux/animate", {"action": "stop", "layer": "effect"}, 0.3)
        off = _writtenFlashes(rig, FILL, t1)
        check(off["flashes"] > 4, "with the guard off the animation flashes at its own rate, got %.1f" % off["flashes"])
    finally:
        rig.post("/NeewerLux/settings", {"action": "set_global", "settings": {"flashGuardEnabled": True}})
        rig.post("/NeewerLux/animate", {"action": "delete", "name": FAST["name"]})
    check(nl.flashGuardEnabled and not os.path.exists(nl.globalPrefsFile), "back on: the default, nothing saved")


def t_flashGuardRedFlashes(rig):
    """Saturated red alternating with blue isn't a big luminance change for a light at full
    brightness, but WCAG counts it as a red flash."""
    nl = rig.nl
    red = {"name": "Harness Red Blue", "loop": True, "keyframes": [
        {"hold_ms": 100, "fade_ms": 0, "lights": {"*": {"mode": "HSI", "hue": 0, "sat": 100, "bri": 100}}},
        {"hold_ms": 100, "fade_ms": 0, "lights": {"*": {"mode": "HSI", "hue": 240, "sat": 100, "bri": 100}}}]}
    rig.post("/NeewerLux/animate", {"action": "save", "animation": red, "overwrite": True})
    try:
        t0 = time.monotonic()
        rig.post("/NeewerLux/animate", {"action": "play", "name": red["name"], "loop": True, "layer": "effect", "rate": 20}, 2.5)
        rig.post("/NeewerLux/animate", {"action": "stop", "layer": "effect"}, 0.3)
        got = _writtenFlashes(rig, FILL, t0)
        check(got["red"] <= 3 and got["flashes"] <= 3, "red flashes got through: " + str(got))
    finally:
        rig.post("/NeewerLux/animate", {"action": "delete", "name": red["name"]})


def t_shippedContentUnderFlashLimit(rig):
    """No shipped animation (at 1x speed, as the GUI, URLs and the dashboard play them by
    default) or sequence flashes more than 3 times a second, before the guard."""
    nl = rig.nl
    over = []
    worst = (0.0, "")
    for name in sorted(nl.savedAnimations):
        if name.startswith("Harness "):
            continue
        r = nl.animationFlashReport(name, 1.0)
        check(r is not None, "couldn't check " + name)
        rate = max(r["worst"], r["worstRed"])
        worst = max(worst, (rate, name))
        if rate > 3:
            over.append((name, r["worst"], r["worstRed"]))
    for name in sorted(nl.savedSequences):
        r = nl.renderSequence(name, stepMs=10)
        if r.get("success"):
            rate = max(r["flashes"]["worst"], r["flashes"]["worstRed"])
            worst = max(worst, (rate, name))
            if rate > 3:
                over.append((name, r["flashes"]["worst"], r["flashes"]["worstRed"]))
    RESULTS.append("    shipped content: highest flash rate %.1f/s (%s), %d animations, %d sequences checked"
                   % (worst[0], worst[1], len(nl.savedAnimations), len(nl.savedSequences)))
    check(not over, "shipped content over 3 flashes a second: " + str(over))
    check(rig.post("/NeewerLux/sequence", {"action": "render", "name": "Example - Four Light Demo"})["flashes"]["limit"] == 3, "render reports flashes")


# ----------------------------------------------------------------- 1.4.0: compositor wakes only when due

def _compositorRun(nl, start, endMs, fine):
    """Play one item on a virtual clock and record every write. fine=True ticks every
    millisecond (what the old 5 ms loop approximated); otherwise it ticks only at
    nextDueMs, as the compositor thread does. Transition fades are on (300 ms in, 500 ms back)."""
    show = nl.show
    base = list(harness.START_BYTES)

    class Hooks:
        def lightCount(self): return len(nl.availableLights)
        def encode(self, idx, cmd): return tuple(sorted(cmd.items()))
        def currentBytes(self, idx): return list(base)
        def shownCommand(self, idx): return show.bytesToCommand(base)
        def isLocked(self, idx): return False
        def wake(self): pass
        def globalRevert(self): return True
        def recallPreset(self, n): pass
        def onStatus(self, info): pass
        def fadeInMs(self): return 300
        def handbackMs(self): return 500

    vt = [0.0]
    comp = show.ShowCompositor(Hooks(), clock=lambda: vt[0])
    writes = []

    def drain():
        for idx, (b, _) in comp.takeMailbox().items():
            writes.append((vt[0] * 1000, idx, b))
    start(comp)
    drain()
    ticks = 0
    while comp.anyActive() and vt[0] * 1000 < endMs + 2000:
        if fine:
            vt[0] = round(vt[0] + 0.001, 6)
        else:
            vt[0] = comp.nextDueMs(vt[0] * 1000) / 1000.0
        comp.tick(vt[0])
        ticks += 1
        drain()
    return writes, ticks


def _virtualCompositor(show, handbackMs=500, fadeInMs=0):
    base = list(harness.START_BYTES)

    class Hooks:
        def lightCount(self): return 1
        def encode(self, idx, cmd): return tuple(sorted(cmd.items()))
        def currentBytes(self, idx): return list(base)
        def shownCommand(self, idx): return show.bytesToCommand(base)
        def isLocked(self, idx): return False
        def wake(self): pass
        def globalRevert(self): return True
        def recallPreset(self, n): pass
        def onStatus(self, info): pass
        def fadeInMs(self): return fadeInMs
        def handbackMs(self): return handbackMs

    vt = [0.0]
    comp = show.ShowCompositor(Hooks(), clock=lambda: vt[0])

    def run(until):
        writes = []
        while vt[0] < until:
            vt[0] = round(vt[0] + 0.01, 3)
            comp.tick(vt[0])
            writes += [(vt[0], dict(b) if isinstance(b[0], tuple) else show.bytesToCommand(b))  # base bytes are raw
                       for _, (b, _) in comp.takeMailbox().items()]
        return writes
    return comp, vt, run


def t_handBackToRunningLayerFades(rig):
    """1.4.0 fix: Fade back also applies when an item ends and a lower layer that is still
    running takes its lights back (an effect ending over a sequence, a sequence ending over a
    sound mode), and when a sequence reverts on pause. 1.3.3 cut in both cases."""
    show = rig.nl.show
    seq, errors, _ = show.parseSequence({"format": 1, "name": "bed", "duration_ms": 60000, "cues": [
        {"at_ms": 0, "state": {"mode": "HSI", "hue": 200, "sat": 100, "bri": 60}}]}, lambda c: True)
    comp, vt, run = _virtualCompositor(show)
    comp.playSequence(show.SequencePlayer(seq, lambda t: [0], lambda n: None, lambda i: None), 0, now=0.0)
    anim = {"name": "flash", "keyframes": [{"hold_ms": 1000, "fade_ms": 0, "lights": {"*": {"mode": "HSI", "hue": 30, "sat": 100, "bri": 90}}}]}
    comp.playAnimation(show.AnimationPlayer("flash", show.AnimationTimeline(anim, stepped=True), lambda t: [0]),
                       show.LAYER_EFFECT, now=0.5)
    w = [x for x in run(3.0) if x[0] > 1.0]
    hues = [c.get("hue") for _, c in w]
    check(len(w) >= 8 and hues[-1] == 200 and any(30 < h < 200 for h in hues[:-1]),
          "an effect ending over a sequence fades back to it: %s" % w[:4])
    check(1.9 < w[-1][0] < 2.1, "over the 0.5 s Fade back: last step at %.2f s" % w[-1][0])

    seqR, _, _ = show.parseSequence({"format": 1, "name": "p", "duration_ms": 60000, "pause_mode": "revert", "cues": [
        {"at_ms": 0, "state": {"mode": "HSI", "hue": 200, "sat": 100, "bri": 60}}]}, lambda c: True)
    comp, vt, run = _virtualCompositor(show)
    comp.playSequence(show.SequencePlayer(seqR, lambda t: [0], lambda n: None, lambda i: None), 0, now=0.0)
    run(1.0)
    comp.pauseSequence(now=1.0)
    w = run(2.5)
    check(len(w) >= 8 and w[-1][1].get("mode") == "CCT", "a sequence reverting on pause fades back to the base: %s" % w[:3])


# ----------------------------------------------------------------- 1.4.0: sound modes

def _soundSignal(nl):
    """Real-time stand-in for a sound card: a looping kick and hi-hat pattern at 124 BPM."""
    np = nl.audio.np
    sr = nl.audio.SAMPLE_RATE
    p = 60.0 / 124
    secs = 16 * p  # a whole number of bars, so the loop keeps time
    x = np.zeros(int(sr * secs))
    t = np.arange(int(0.15 * sr)) / sr
    kick = 0.9 * np.sin(2 * np.pi * (50 + 80 * np.exp(-t * 30)) * t) * np.exp(-t * 12)
    n = int(0.03 * sr)
    hat = 0.25 * np.random.default_rng(3).uniform(-1, 1, n) * np.exp(-np.linspace(0, 6, n))
    b = 0.0
    while b < secs - p / 2:
        x[int(b * sr):int(b * sr) + len(kick)] += kick
        for k in range(4):
            j = int((b + k * p / 4) * sr)
            x[j:j + n] += hat[:len(x) - j] * (1.0 if k == 2 else 0.5)
        b += p
    nl.audioEngine.sourceFactory = lambda device: nl.audio.ArraySource(x, name="test signal")


def _layers(rig):
    return [l["layer"] for l in rig.getJSON("status_json")["lights"]]


def _waitLayers(rig, want, timeout=4.0):
    """Wait until each light's layer matches want (a list, None = don't care)."""
    end = time.monotonic() + timeout
    while True:
        got = _layers(rig)
        if all(w is None or w == g for w, g in zip(want, got)) or time.monotonic() > end:
            return got
        time.sleep(0.05)


def _needsNumpy(rig):
    if rig.nl.audio.np is None:
        RESULTS.append("    skipped: numpy (optional audio group) isn't installed")
        return True
    return False


def t_soundModeHTTP(rig):
    """Start, switch, tune and stop a sound mode over HTTP: it drives only the lights its parts
    aim at, on the sound layer, and reports live levels."""
    nl = rig.nl
    if _needsNumpy(rig):
        return
    _soundSignal(nl)
    t0 = time.monotonic()
    r = rig.post("/NeewerLux/sound", {"action": "start", "mode": "pulse"})
    check(r["success"] and r["mode"] == "Pulse", r)
    w = waitFor(rig, RIM, t0, lambda d: hueOf(d) == 265, 3.0)
    check(any(hueOf(d) == 265 for d in w), "the rim takes Pulse's colour: %s" % w[-3:])
    got = _waitLayers(rig, ["base", "base", "sound", "sound"])
    check(got == ["base", "base", "sound", "sound"], "Pulse drives rim and background on the sound layer only: %s" % got)
    end = time.monotonic() + 5
    st = rig.post("/NeewerLux/sound", {"action": "status"})
    while time.monotonic() < end and not (st["levels"] and st["levels"]["bpm"] > 0):
        time.sleep(0.2)
        st = rig.post("/NeewerLux/sound", {"action": "status"})
    check(st["running"] and st["mode"] == "Pulse" and st["capturing"] and st["deviceName"] == "test signal", st)
    check(abs(st["levels"]["bpm"] / 124 - 1) < 0.03, "status reports the tempo: %s" % st["levels"])
    sj = rig.getJSON("status_json")
    check(sj["sound"]["running"] and sj["layers"]["sound"]["name"] == "Pulse", "status_json shows the sound layer: %s" % sj["layers"])
    time.sleep(max(0.0, t0 + 5.0 - time.monotonic()))
    bris = [bri(d) for t, d in writesFor(rig, AMB, t0 + 3.0)]
    check(bris and max(bris) - min(bris) >= 10, "the background moves with the music: %s" % bris[-12:])
    r = rig.post("/NeewerLux/sound", {"action": "set", "params": {"ceiling": 40}})
    check(r["success"] and r["params"]["ceiling"] == 40, r)
    t1 = time.monotonic()
    time.sleep(1.0)
    check(all(bri(d) <= 40 for d in [d for t, d in writesFor(rig, AMB, t1 + 0.3)]), "the new ceiling applies at once")
    rig.get("sound=mode|Bands", 0.2)
    got = _waitLayers(rig, ["base", "sound", "sound", "sound"])
    check(got == ["base", "sound", "sound", "sound"], "Bands adds the fill (highs): %s" % got)
    r = rig.post("/NeewerLux/sound", {"action": "set", "params": {"parts": []}})
    check(not r["success"], "set rejects an invalid mode")
    rig.post("/NeewerLux/sound", {"action": "stop"})
    got = _waitLayers(rig, ["base"] * 4)
    check(got == ["base"] * 4, "stop hands every light back: %s" % got)
    st = rig.post("/NeewerLux/sound", {"action": "status"})
    check(not st["running"] and not st["capturing"] and st["lastMode"] == "Bands", st)
    check(nl.soundMode == "Bands" and "soundMode=Bands" in open(nl.globalPrefsFile, encoding="utf-8").read(), "the last mode is remembered")
    rig.get("sound=start", 0.3)
    check(rig.post("/NeewerLux/sound", {"action": "status"})["mode"] == "Bands", "sound=start plays the last mode")
    rig.get("stop_layer=all", 0.3)
    check(not rig.post("/NeewerLux/sound", {"action": "status"})["running"], "stop_layer=all stops sound too")
    nl._rememberSound(mode="Pulse")


def t_soundUnderShowAndEffects(rig):
    """Sound is a bed: a sequence and an effect take the lights they drive, and give them back
    to the sound mode when they end."""
    nl = rig.nl
    if _needsNumpy(rig):
        return
    _soundSignal(nl)
    rig.post("/NeewerLux/sound", {"action": "start", "mode": "Pulse"})
    check(_waitLayers(rig, [None, None, "sound", "sound"]) [2:] == ["sound", "sound"], "Pulse running")
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": stepSequence("over", [120, 150], 600, target="@rim")})
    got = _waitLayers(rig, ["base", "base", "show", "sound"])
    check(got == ["base", "base", "show", "sound"], "the sequence takes the rim, the background keeps the sound: %s" % got)
    got = _waitLayers(rig, ["base", "base", "sound", "sound"], 4.0)
    check(got == ["base", "base", "sound", "sound"], "when it ends the rim goes back to the sound mode: %s" % got)
    rig.get("animate=Heartbeat|1|10|100|true|0||effect|replace|@background", 0.2)
    got = _waitLayers(rig, [None, None, "sound", "effect"])
    check(got[3] == "effect", "an effect plays over the sound mode: %s" % got)
    rig.get("stop_layer=effect", 0.2)
    got = _waitLayers(rig, [None, None, "sound", "sound"])
    check(got[3] == "sound", "and the sound mode carries on after it: %s" % got)
    rig.post("/NeewerLux/sound", {"action": "stop"})


def t_soundRespectsLimitsAndLocks(rig):
    nl = rig.nl
    if _needsNumpy(rig):
        return
    _soundSignal(nl)
    rig.setShowPrefs(AMB, maxBri=30)
    rig.setShowPrefs(RIM, locked=True)
    try:
        t0 = time.monotonic()
        r = rig.post("/NeewerLux/sound", {"action": "start", "mode": "Pulse", "params": {"floor": 50, "ceiling": 100}})
        check(r["success"], r)
        w = waitFor(rig, AMB, t0, lambda d: d[1] == 134, 3.0)
        time.sleep(1.5)
        bris = [bri(d) for t, d in writesFor(rig, AMB, t0) if d[1] == 134]
        check(bris and max(bris) <= 30, "the background's 30%% limit holds: %s" % bris[-8:])
        check(not [d for t, d in writesFor(rig, RIM, t0)], "a Locked light gets nothing from the sound mode")
    finally:
        rig.post("/NeewerLux/sound", {"action": "stop"})


def t_soundUnavailable(rig):
    """Without the audio packages the feature says why and nothing else changes."""
    nl = rig.nl
    real = nl.audio.available
    nl.audio.available = lambda: (False, "Sound features need numpy")
    try:
        r = rig.post("/NeewerLux/sound", {"action": "start", "mode": "Pulse"})
        check(not r["success"] and "numpy" in r["errors"][0], r)
        st = rig.getJSON("status_json")["sound"]
        check(st["available"] is False and "numpy" in st["reason"] and not st["running"], st)
        check(rig.post("/NeewerLux/sound", {"action": "list"})["success"], "the mode files still list")
    finally:
        nl.audio.available = real


def t_soundModeFilesHTTP(rig):
    nl = rig.nl
    mode = {"format": 1, "name": "Test Glow", "palette": [{"temp": 3000}], "parts": [{"target": "@background", "drive": "level"}]}
    r = rig.post("/NeewerLux/sound", {"action": "validate", "mode": dict(mode, floor=90, ceiling=10)})
    check(not r["success"] and r["errors"], r)
    check(rig.post("/NeewerLux/sound", {"action": "save", "mode": mode})["success"], "save")
    check(not rig.post("/NeewerLux/sound", {"action": "save", "mode": mode})["success"], "saving over needs overwrite")
    renamed = dict(mode, name="Test Glow 2")
    check(rig.post("/NeewerLux/sound", {"action": "save", "mode": renamed, "original": "Test Glow"})["success"], "rename")
    names = [m["name"] for m in rig.post("/NeewerLux/sound", {"action": "list"})["modes"]]
    check("Test Glow 2" in names and "Test Glow" not in names, names)
    check(rig.post("/NeewerLux/sound", {"action": "get", "name": "test glow 2"})["mode"]["palette"] == [{"temp": 3000}], "get")
    check(rig.post("/NeewerLux/sound", {"action": "delete", "name": "Test Glow 2"})["success"], "delete")
    check(not os.path.exists(os.path.join(nl.soundModesDir, "Test Glow 2.json")), "the file is gone")


def t_offWinsDuringShows(rig):
    """1.4.0: switching a light off works whatever is playing. Off takes it out of every layer
    (the sequence carries on with the others) until it's turned on, when the sequence takes it
    back; a show powers on any light that is off when it takes it (lights in standby ignore
    colour commands)."""
    nl = rig.nl
    rig.get("light=*&off", 0.4)
    t0 = time.monotonic()
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": stepSequence("power", [10, 60, 110, 160, 210, 260, 310], 600)})
    w = waitFor(rig, RIM, t0, lambda d: d[1] == 134, 2.0)
    kinds = [(d[1], d[3]) if d[1] == 129 else d[1] for d in w]
    check(kinds and kinds[0] == (129, 1) and 134 in kinds, "a show powers a light on before its first colour: %s" % kinds[:4])
    t1 = time.monotonic()
    rig.get("light=3&off", 0.6)
    w = writesFor(rig, RIM, t1)
    check(w and w[0][1][1] == 129 and w[0][1][3] == 2, "Off reaches the light during a sequence: %s" % [d for _, d in w][:3])
    check(len(w) == 1, "and the sequence leaves it off: %s" % [d for _, d in w])
    check(_layers(rig)[RIM] == "base" and _layers(rig)[KEY] == "show", "the others stay on the sequence: %s" % _layers(rig))
    t2 = time.monotonic()
    rig.get("light=3&on", 0.2)
    w = waitFor(rig, RIM, t2, lambda d: d[1] == 134, 1.5)
    check(w and w[0][1] == 129 and any(d[1] == 134 for d in w), "On brings it back into the sequence: %s" % [d[1] for d in w])
    check(_layers(rig)[RIM] == "show", "back on the show layer")
    rig.post("/NeewerLux/sequence", {"action": "stop"})


def t_manualWriteReleasesSound(rig):
    """1.4.0: recalling a preset or moving a slider on a light the sound layer drives takes that
    light out of the sound layer and shows the new state at once; the layer (and its capture)
    stops when it has no lights left. A command to a light it doesn't drive leaves it playing;
    Off takes a light out only until it is switched back on."""
    nl = rig.nl
    if _needsNumpy(rig):
        return
    _soundSignal(nl)
    rig.post("/NeewerLux/sound", {"action": "start", "mode": "Pulse"})
    check(_waitLayers(rig, [None, None, "sound", "sound"])[2:] == ["sound", "sound"], "Pulse running")
    rig.get("light=1&mode=CCT&temp=40&bri=30", 0.4)
    check(rig.post("/NeewerLux/sound", {"action": "status"})["running"], "a command to the key (not driven) leaves it playing")
    rig.get("light=4&off", 0.4)
    st = rig.post("/NeewerLux/sound", {"action": "status"})
    check(st["running"] and _layers(rig)[AMB] == "base", "Off on the background takes only that light out")
    t0 = time.monotonic()
    rig.get("light=3&mode=CCT&temp=32&bri=40", 0.6)
    w = writesFor(rig, RIM, t0)
    check(w and w[-1][1][1] == 135 and w[-1][1][4] == 32, "the rim shows the command at once: %s" % [d for _, d in w][-2:])
    st = rig.post("/NeewerLux/sound", {"action": "status"})
    check(st["running"] and _layers(rig)[RIM] == "base", "the rim leaves the sound layer; the background (off) still follows it")
    rig.get("light=4&mode=CCT&temp=45&bri=20", 0.6)
    st = rig.post("/NeewerLux/sound", {"action": "status"})
    check(not st["running"] and not st["capturing"], "a command to its last light stops the sound layer and capture: %s" % st)
    check(_waitLayers(rig, ["base"] * 4) == ["base"] * 4, "every light is back on the base")

    rig.post("/NeewerLux/presets", {"action": "save", "index": 3, "entries": [{"light": "*", "mode": "CCT", "temp": 45, "bri": 25}]})
    rig.post("/NeewerLux/sound", {"action": "start", "mode": "Pulse"})
    check(_waitLayers(rig, [None, None, "sound", "sound"])[2:] == ["sound", "sound"], "Pulse running again")
    t1 = time.monotonic()
    rig.get("use_preset=3", 0.8)
    check(not rig.post("/NeewerLux/sound", {"action": "status"})["running"], "recalling a global preset stops it")
    w = writesFor(rig, AMB, t1)
    check(w and w[-1][1][1] == 135 and w[-1][1][4] == 45, "and the preset shows: %s" % [d for _, d in w][-2:])


def t_presetFadeTakesLightsFromSound(rig):
    """A preset recalled with a fade (its own or the global Fade in) takes the lights it sets out
    of the sound layer like one without, fading them from the sound's look to the preset; a
    light the preset sets following sound keeps following it."""
    nl = rig.nl
    if _needsNumpy(rig):
        return
    _soundSignal(nl)
    nl.fadeInMs = 400
    try:
        rig.post("/NeewerLux/presets", {"action": "save", "index": 3, "entries": [{"light": "*", "mode": "CCT", "temp": 45, "bri": 25}]})
        rig.post("/NeewerLux/sound", {"action": "start", "mode": "Pulse"})
        check(_waitLayers(rig, [None, None, "sound", "sound"])[2:] == ["sound", "sound"], "Pulse running")
        t0 = time.monotonic()
        rig.get("use_preset=3", 0.1)
        st = rig.post("/NeewerLux/sound", {"action": "status"})
        check(not st["running"] and not st["capturing"], "a global preset with a fade stops sound: %s" % st)
        done = lambda: [d for _, d in writesFor(rig, AMB, t0)][-1:] == [[120, 135, 2, 25, 45, 71]]
        end = time.monotonic() + 3
        while not done() and time.monotonic() < end:
            time.sleep(0.02)
        w = writesFor(rig, AMB, t0)
        check(done() and len(w) >= 3, "and the light fades to the preset: %s" % [d for _, d in w][-3:])

        rig.post("/NeewerLux/presets", {"action": "save", "index": 4, "entries": [
            {"target": "AA:00:00:00:00:03", "mode": "CCT", "temp": 45, "bri": 25},
            {"target": "AA:00:00:00:00:04", "mode": "HSI", "hue": 100, "sat": 80, "bri": 50, "sound": "Colour Drift"}]})
        rig.post("/NeewerLux/sound", {"action": "start", "mode": "Pulse"})
        _waitLayers(rig, [None, None, "sound", "sound"])
        rig.get("use_preset=4", 0.1)
        st = rig.post("/NeewerLux/sound", {"action": "status"})
        check(st["assignments"] == [{"mode": "Colour Drift", "lights": [4]}], "the rim leaves sound, the background follows Colour Drift: %s" % st["assignments"])
        check(_waitLayers(rig, ["base", "base", "base", "sound"]) == ["base", "base", "base", "sound"], "layers")
        rig.post("/NeewerLux/sound", {"action": "stop"})
    finally:
        nl.fadeInMs = 0


def t_soundOnSomeLights(rig):
    """1.4.0: a sound mode can be put on some lights only (HTTP GET and POST): those lights leave
    whatever sound they followed, the rest play on; stop with lights takes only those out."""
    nl = rig.nl
    if _needsNumpy(rig):
        return
    _soundSignal(nl)
    rig.post("/NeewerLux/sound", {"action": "start", "mode": "Pulse"})
    check(_waitLayers(rig, [None, None, "sound", "sound"])[2:] == ["sound", "sound"], "Pulse on its own targets")
    rig.get("sound=start|Colour%20Drift|1", 0.2)
    check(_waitLayers(rig, ["sound", "base", "sound", "sound"]) == ["sound", "base", "sound", "sound"], "the key joins, on Colour Drift")
    st = rig.post("/NeewerLux/sound", {"action": "status"})
    check(st["assignments"] == [{"mode": "Pulse", "lights": None}, {"mode": "Colour Drift", "lights": [1]}], str(st["assignments"]))
    rig.post("/NeewerLux/sound", {"action": "start", "mode": "colour drift", "lights": "3"})
    st = rig.post("/NeewerLux/sound", {"action": "status"})
    check(st["assignments"] == [{"mode": "Pulse", "lights": None}, {"mode": "Colour Drift", "lights": [1, 3]}],
          "the rim moves from Pulse to Colour Drift: %s" % st["assignments"])
    player = nl.showEngine.soundPlayer()
    check([sorted(set(i for ls in v.partLights for i in ls)) for v in player.voices] == [[AMB], [KEY, RIM]], "lights per mode")
    r = rig.post("/NeewerLux/sound", {"action": "set", "mode": "Pulse", "params": {"floor": 33}})
    check(r["success"] and player.voices[0].mode.floor == 33 and player.voices[1].mode.floor != 33, "set changes only the named mode")
    r = rig.post("/NeewerLux/sound", {"action": "set", "mode": "Bands", "params": {"floor": 33}})
    check(not r["success"] and "isn't playing" in r["errors"][0], str(r))
    # the chase in Beat Chase steps through the lights it was given, in sweep order
    rig.post("/NeewerLux/sound", {"action": "start", "mode": "Beat Chase", "lights": "1;2"})
    chase = nl.showEngine.soundPlayer().voices[-1]
    check(chase.partLights == [[FILL, KEY]], "assigned lights join the chase in sweep order: %s" % chase.partLights)
    rig.get("sound=stop|1;2;3", 0.2)
    check(_waitLayers(rig, ["base", "base", "base", "sound"]) == ["base", "base", "base", "sound"], "stop on some lights")
    st = rig.post("/NeewerLux/sound", {"action": "status"})
    check(st["running"] and st["assignments"] == [{"mode": "Pulse", "lights": None}], str(st["assignments"]))
    r = rig.post("/NeewerLux/sound", {"action": "start", "mode": "Pulse", "lights": "@nothing"})
    check(not r["success"] and "no light matches" in r["errors"][0], str(r))
    rig.post("/NeewerLux/sound", {"action": "stop", "lights": "4"})
    st = rig.post("/NeewerLux/sound", {"action": "status"})
    check(not st["running"] and not st["capturing"], "stopping its last light stops the layer and capture")
    rig.post("/NeewerLux/sound", {"action": "start", "mode": "Pulse", "lights": "2"})
    check(_waitLayers(rig, ["base", "sound", "base", "base"]) == ["base", "sound", "base", "base"], "a start with lights when nothing plays")
    rig.post("/NeewerLux/sound", {"action": "stop"})


def t_presetSounds(rig):
    """1.4.0: a snapshot preset can set lights following a sound mode; their preset colour is
    what they return to. A snapshot taken while sound plays saves it; the prefs line round-trips
    and moves with the preset."""
    nl = rig.nl
    if _needsNumpy(rig):
        return
    _soundSignal(nl)
    entries = [{"target": "AA:00:00:00:00:03", "mode": "HSI", "hue": 100, "sat": 80, "bri": 50, "sound": "Pulse"},
               {"target": "AA:00:00:00:00:01", "mode": "CCT", "temp": 40, "bri": 30},
               {"target": "-1", "mode": "CCT", "temp": 40, "bri": 30, "sound": "Pulse"}]
    r = rig.post("/NeewerLux/presets", {"action": "save", "index": 4, "entries": entries[:2]})
    check(r["success"], str(r))
    got = rig.post("/NeewerLux/presets", {"action": "get", "index": 4})["preset"]["entries"]
    check(got[0].get("sound") == "Pulse" and "sound" not in got[1], "the editor entries carry it: %s" % got)
    check(nl.entriesToSounds(entries) == {"AA:00:00:00:00:03": "Pulse"}, "global entries can't follow sound")
    t0 = time.monotonic()
    rig.get("use_preset=4", 0.2)
    check(_waitLayers(rig, ["base", "base", "sound", "base"]) == ["base", "base", "sound", "base"], "the rim follows Pulse, alone")
    st = rig.post("/NeewerLux/sound", {"action": "status"})
    check(st["assignments"] == [{"mode": "Pulse", "lights": [3]}], str(st["assignments"]))
    check(any(d[1] == 135 and d[4] == 40 for _, d in writesFor(rig, KEY, t0)), "the key gets its colour")
    check(not any(d[1] == 134 and d[3] == 100 and d[6] == 50 for _, d in writesFor(rig, RIM, t0)), "the rim isn't written its colour")
    t1 = time.monotonic()
    rig.post("/NeewerLux/sound", {"action": "stop"})
    _waitLayers(rig, ["base"] * 4)
    back = lambda: [d for _, d in writesFor(rig, RIM, t1)][-1:] == [[120, 134, 4, 100, 0, 80, 50, 232]]
    end = time.monotonic() + 2
    while not back() and time.monotonic() < end:
        time.sleep(0.02)
    check(back(), "and returns to its preset colour: %s" % [d for _, d in writesFor(rig, RIM, t1)][-2:])

    line = nl.presetSoundLine(3)  # preset 4
    check(line == "presetSound3=AA:00:00:00:00:03|Pulse", line)
    nl.presetSounds.clear()
    nl.parsePresetSoundLine(line)
    check(nl.presetSounds == {3: {"AA:00:00:00:00:03": "Pulse"}}, "the prefs line round-trips: %s" % nl.presetSounds)
    rig.post("/NeewerLux/presets", {"action": "move", "index": 4, "direction": "left"})
    check(nl.presetSounds == {2: {"AA:00:00:00:00:03": "Pulse"}}, "it moves with the preset: %s" % nl.presetSounds)

    rig.post("/NeewerLux/sound", {"action": "start", "mode": "Pulse"})
    _waitLayers(rig, [None, None, "sound", "sound"])
    nl.saveCustomPreset("snapshot", 6)
    following = sorted(nl.presetSounds.get(6, {}).values())
    check(following == ["Pulse", "Pulse"] and len(nl.customLightPresets[6]) == 4, "a snapshot saves the lights following sound: %s" % nl.presetSounds.get(6))
    rig.get("light=*&mode=CCT&temp=56&bri=40", 0.5)
    check(not rig.post("/NeewerLux/sound", {"action": "status"})["running"], "a write to every light stops it")
    nl.saveCustomPreset("snapshot", 6)
    check(6 not in nl.presetSounds, "a snapshot without sound clears it")


def _songAnalysis(show, bpm, durationMs=96000, offsetMs=250):
    """An analysis result like neewerlux_audio.analyzeSong's, for drafting without audio."""
    beats, bars = show.songGrid(durationMs, bpm, offsetMs)
    cuts = [0] + bars[2::8] + [durationMs]
    levels = [1, 2, 3, 1, 3, 2, 3, 1, 2, 3, 1, 3, 2, 3, 2, 1] * 4
    sections = [{"start_ms": a, "end_ms": b, "energy": 0.3 * levels[i], "level": levels[i], "label": "S%d" % i}
                for i, (a, b) in enumerate(zip(cuts[:-1], cuts[1:]))]
    return {"duration_ms": durationMs, "bpm": bpm, "offset_ms": offsetMs, "beats": beats, "bars": bars, "sections": sections}


def t_songDrafts(rig):
    """1.4.0: drafts from a song analysis validate, never drive the key, keep every light under
    the flash limit (before the guard) at any tempo, and carry the tempo and sections."""
    nl = rig.nl
    show = nl.show
    for bpm in (60, 90, 120, 128, 150, 174, 200):
        a = _songAnalysis(show, bpm)
        for style in show.DRAFT_STYLES:
            seq, errors = show.draftSequence(a, style, "Draft %s %d" % (style, bpm))
            check(not errors, str(errors))
            built, errs, _ = nl.buildSequence(seq)
            check(built is not None, "%s at %d BPM validates: %s" % (style, bpm, errs))
            check(not any("key" in c["target"] for c in seq["cues"]), "never the key")
            check({c["target"] for c in seq["cues"]} == set(show.DRAFT_TARGETS.values()), "every group has cues")
            r = nl.renderSequence(seq, 25)
            fl = r["flashes"]
            check(fl["worst"] <= 2.5 and fl["worstRed"] <= 2.5, "%s at %d BPM: %s flashes a second at worst (red %s)" % (style, bpm, fl["worst"], fl["worstRed"]))
            check(seq["tempo"] == {"bpm": bpm, "offset_ms": a["bars"][0]} and len(seq["sections"]) == len(a["sections"]), "tempo and sections")
    a = _songAnalysis(show, 128)
    concert = show.draftSequence(a, "concert")[0]
    neon = show.draftSequence(a, "Neon")[0]
    subtle = show.draftSequence(a, "Subtle")[0]
    check(len(subtle["cues"]) == 3 * len(a["sections"]), "Subtle: one look per section")
    pulses = [c for c in concert["cues"] if c.get("duration_ms")]
    loud = [s for s in a["sections"] if s["level"] == 3]
    check(pulses and all(any(s["start_ms"] <= c["at_ms"] < s["end_ms"] for s in loud) for c in pulses), "pulses only in the loudest sections")
    check(all(c["at_ms"] in a["beats"] for c in pulses), "on the beat")
    check(len([c for c in neon["cues"] if not c.get("duration_ms")]) > len(concert["cues"]) - len(pulses), "Neon swaps colours")
    # a corrected tempo: sections move to the nearest bar of the new grid
    moved, _ = show.draftSequence(a, "Subtle", bpm=64, offsetMs=500)
    grid = show.songGrid(a["duration_ms"], 64, 500)[1]
    check(all(s["start_ms"] in grid or s["start_ms"] == 0 for s in moved["sections"]) and moved["tempo"] == {"bpm": 64, "offset_ms": 500},
          "sections snap to the new bars: %s" % [s["start_ms"] for s in moved["sections"]])
    check(show.draftSequence(a, "Disco")[1] == ["style must be one of Subtle, Concert, Neon"], "unknown style")
    check(show.draftSequence({"duration_ms": 1000}, "Neon")[1], "an incomplete analysis is an error")


def _songFile(path, bpm=128.0, seconds=40.0, sr=22050):
    """A WAV with kicks on the beat (accented each bar) and a louder half."""
    import numpy as np
    import soundfile
    t = np.arange(int(seconds * sr)) / sr
    x = 0.05 * np.sin(2 * np.pi * 220 * t)
    kt = np.arange(int(0.1 * sr)) / sr
    kick = np.sin(2 * np.pi * (50 + 80 * np.exp(-kt * 30)) * kt) * np.exp(-kt * 25)
    beat = 60.0 / bpm
    k = 0
    while k * beat + 0.2 < seconds - 0.2:
        at = int((0.2 + k * beat) * sr)
        amp = (1.0 if k % 4 == 0 else 0.6) * (0.9 if 0.2 + k * beat > seconds / 2 else 0.35)
        x[at:at + len(kick)] += kick[:len(x[at:at + len(kick)])] * amp
        k += 1
    soundfile.write(path, x * 0.5, sr)


def t_songHTTP(rig):
    """1.4.0: analyze a song file by path or upload it, draft a sequence from the analysis (or a
    path), optionally saving it."""
    import tempfile
    nl = rig.nl
    try:
        import soundfile  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        print("  (skipped: needs numpy and soundfile)")
        return
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "My Song.wav")
        _songFile(path)
        a = rig.post("/NeewerLux/sequence", {"action": "analyze", "path": path})
        check(a["success"] and abs(a["bpm"] - 128) < 0.3 and a["song"] == "My Song" and a["sections"], "analyze by path: %s" % {k: a.get(k) for k in ("success", "bpm", "errors")})
        bad = rig.post("/NeewerLux/sequence", {"action": "analyze", "path": os.path.join(d, "nothing.mp3")})
        check(not bad["success"] and "no file" in bad["errors"][0], str(bad))
        bad = rig.post("/NeewerLux/sequence", {"action": "analyze", "path": path[:-4] + ".txt"})
        check(not bad["success"] and "must be one of" in bad["errors"][0], str(bad))
        with open(path, "rb") as f:
            data = f.read()
        req = urllib.request.Request("http://127.0.0.1:%d/NeewerLux/song?name=Uploaded%%20Song.wav&bpm=64" % rig.port, data=data,
                                     headers={"Content-Type": "application/octet-stream"}, method="POST")
        up = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
        check(up["success"] and up["song"] == "Uploaded Song" and up["bpm"] == 64, "upload with a given tempo: %s" % {k: up.get(k) for k in ("success", "bpm", "song", "errors")})
        check(not [f for f in os.listdir(tempfile.gettempdir()) if f.endswith(".wav") and os.path.getsize(os.path.join(tempfile.gettempdir(), f)) == len(data)],
              "the upload's temporary file is removed")

        dr = rig.post("/NeewerLux/sequence", {"action": "draft", "analysis": a, "style": "Neon", "name": "Drafted"})
        check(dr["success"] and dr["sequence"]["name"] == "Drafted" and dr["flashes"]["worst"] <= 3 and "Drafted" not in nl.savedSequences,
              "draft from an analysis, not saved: %s" % {k: dr.get(k) for k in ("success", "errors", "flashes")})
        dr = rig.post("/NeewerLux/sequence", {"action": "draft", "path": path, "style": "subtle", "save": True, "artist": "PoizenJam"})
        check(dr["success"] and dr.get("saved") and nl.savedSequences.get("My Song", {}).get("artist") == "PoizenJam", "draft from a path, saved under the song's name: %s" % dr.get("errors"))
        again = rig.post("/NeewerLux/sequence", {"action": "draft", "path": path, "save": True})
        check(not again["success"] and "exists" in again["errors"][0], "saving over needs overwrite: %s" % again["errors"])
        check(not rig.post("/NeewerLux/sequence", {"action": "draft", "analysis": a, "style": "Disco"})["success"], "unknown style")
        rig.post("/NeewerLux/sequence", {"action": "delete", "name": "My Song"})


def t_paletteLibrary(rig):
    """1.4.0: saved palettes over HTTP (list, save, delete) and by name in start and set."""
    nl = rig.nl
    pals = rig.post("/NeewerLux/sound", {"action": "palettes"})
    names = [p["name"] for p in pals["palettes"]]
    check(all(n in names for n in ("Neon", "Sunset", "Ocean", "Rainbow", "Warm Whites")), str(names))
    mine = [{"hue": 10, "sat": 90}, {"hue": 50, "sat": 90}]
    check(rig.post("/NeewerLux/sound", {"action": "save_palette", "name": "Test Pal", "palette": mine})["success"], "save")
    check(os.path.exists(os.path.join(nl.palettesDir, "Test Pal.json")), "the file is written")
    r = rig.post("/NeewerLux/sound", {"action": "save_palette", "name": "test pal", "palette": mine[:1]})
    check(not r["success"] and "exists" in r["errors"][0], str(r))
    check(rig.post("/NeewerLux/sound", {"action": "save_palette", "name": "test pal", "palette": mine[:1], "overwrite": True})["success"], "overwrite")
    check(nl.savedPalettes == {**{n: nl.savedPalettes[n] for n in names}, "test pal": mine[:1]} and len(os.listdir(nl.palettesDir)) == 6,
          "one file, renamed: %s" % os.listdir(nl.palettesDir))
    r = rig.post("/NeewerLux/sound", {"action": "save_palette", "name": "Bad", "palette": [{"hue": 1}, {"temp": 3000}]})
    check(not r["success"] and "not a mix" in r["errors"][0], str(r))
    nl.loadAllSoundModes()
    check(nl.savedPalettes.get("test pal") == mine[:1], "reloads from disk")
    if not _needsNumpy(rig):
        _soundSignal(nl)
        r = rig.post("/NeewerLux/sound", {"action": "start", "mode": "Pulse", "params": {"palette": "neon"}})
        check(r["success"] and nl.showEngine.soundPlayer().mode.palette == nl.savedPalettes["Neon"], str(r))
        r = rig.post("/NeewerLux/sound", {"action": "set", "params": {"palette": "Test Pal"}})
        check(r["success"] and nl.showEngine.soundPlayer().mode.palette == mine[:1], str(r))
        r = rig.post("/NeewerLux/sound", {"action": "set", "params": {"palette": "Nope"}})
        check(not r["success"] and "no palette named" in r["errors"][0], str(r))
        rig.post("/NeewerLux/sound", {"action": "stop"})
    check(rig.post("/NeewerLux/sound", {"action": "delete_palette", "name": "TEST PAL"})["success"], "delete")
    check("test pal" not in nl.savedPalettes and not os.path.exists(os.path.join(nl.palettesDir, "Test Pal.json")), "gone")
    check(not rig.post("/NeewerLux/sound", {"action": "delete_palette", "name": "Test Pal"})["success"], "deleting it twice fails")


def t_compositorWakesOnlyWhenDue(rig):
    """Ticking only when a light's output can change sends exactly what ticking every
    millisecond sends (same commands, each within the 1 ms the fine ticker can lag), for
    every shipped sequence and animation, with transition fades in and out."""
    nl = rig.nl
    show = nl.show
    items = []
    for name in sorted(nl.savedSequences):
        seq, errors, _ = nl.buildSequence(nl.savedSequences[name])
        check(seq is not None, "%s: %s" % (name, errors))
        mk = lambda seq=seq: show.SequencePlayer(seq, nl._showResolve, lambda n: nl.savedAnimations.get(nl.resolveAnimationName(n)),
                                                 nl._sequenceBaseCommand)
        items.append(("sequence " + name, lambda comp, mk=mk: comp.playSequence(mk(), 0, now=0.0), min(seq.duration, 40000) + 1))
    for name in sorted(nl.savedAnimations):
        anim = nl.savedAnimations[name]
        for speed in (1.0, 2.0):
            tl = show.AnimationTimeline(anim, speed=speed, fps=10, loop=True, maxLoops=2, stepped=True)
            dur = tl.duration if tl.duration is not None else 8000
            mk = lambda tl=tl, name=name: show.AnimationPlayer(name, tl, nl._showResolve, maxMs=8000)
            items.append(("animation %s x%g" % (name, speed),
                          lambda comp, mk=mk: comp.playAnimation(mk(), show.LAYER_OVERRIDE, now=0.0), min(dur, 8000)))
    fineTicks = dueTicks = 0
    for label, start, endMs in items:
        ref, nFine = _compositorRun(nl, start, endMs, True)
        got, nDue = _compositorRun(nl, start, endMs, False)
        fineTicks += nFine
        dueTicks += nDue
        check(len(ref) == len(got), "%s: %d writes ticking every ms, %d ticking when due" % (label, len(ref), len(got)))
        for (t1, i1, b1), (t2, i2, b2) in zip(ref, got):
            check(i1 == i2 and b1 == b2 and -0.15 <= t1 - t2 <= 1.01,
                  "%s: %s at %.1f ms ticking every ms, %s at %.1f ms ticking when due" % (label, (i1, b1), t1, (i2, b2), t2))
    RESULTS.append("    %d items: %d ticks when due against %d ticking every ms (%.1f%%)"
                   % (len(items), dueTicks, fineTicks, 100.0 * dueTicks / max(1, fineTicks)))


TESTS = [t_maxBrightnessHTTP, t_maxBrightnessAnimationAndSequence, t_minBrightness, t_globalDefaultLimit,
         t_slidersExempt, t_lockedLight, t_roleTargets, t_effectOverPartOfRigRejoinsInSync, t_revertToPresetAtEnd,
         t_endPreset, t_holdAtEnd, t_pauseRevertsAndResumes, t_seekAndSetPosition, t_effectQueueReplaceFull,
         t_effectCap, t_overrideOverSequence, t_onInterruptPause, t_baseWriteDuringSequenceBecomesRevertTarget,
         t_manualCommandStopsAnimationAndReverts, t_postBatchDelivers, t_postPlayEmptyName,
         t_sequenceValidateSaveListPlay, t_clipStretchAndTarget, t_docExamplesValidate, t_guidSidecar, t_statusShape, t_driftVirtualClock,
         t_simStateFollowsCommands, t_statusPollThroughNotifications, t_cctOnlySplitPackets,
         t_cctOnlyDisplayAndRender, t_dimColoursStayVisible,
         t_stageTilesAndStatusColours, t_renderMatchesPlayback, t_renderRespectsLimitsAndLocks, t_renderPNG,
         t_batchKelvin, t_batchCoalescesUnderLoad, t_getDuringBusyWorkerNotDropped, t_batchStopsOverrideAnimation,
         t_batchDuringSequenceBecomesRevertTarget, t_listJsonStructured,
         t_presetEditAPI, t_animationEditAPI, t_sequenceEditAPI, t_commandsDontWaitForStatusPoll,
         t_flashGuardLimitsOutput, t_flashGuardRedFlashes, t_shippedContentUnderFlashLimit,
         t_positionTargetsAndSweep, t_animationModeValidation, t_exactAnimationTiming, t_handbackFade, t_blendCommands, t_fadeInEverywhere,
         t_fadesOnlyBetweenItems,
         t_addSimulatedRig, t_compositorWakesOnlyWhenDue, t_handBackToRunningLayerFades,
         t_soundModeHTTP, t_soundUnderShowAndEffects, t_soundRespectsLimitsAndLocks, t_soundUnavailable, t_soundModeFilesHTTP,
         t_offWinsDuringShows, t_manualWriteReleasesSound, t_presetFadeTakesLightsFromSound, t_soundOnSomeLights,
         t_presetSounds, t_paletteLibrary, t_songDrafts, t_songHTTP]


def main():
    long = "--long" in sys.argv
    onlyDrift = "--drift-only" in sys.argv
    rig = harness.boot(ROOT)
    rig.nl.NLPythonServer.log_message = lambda *a: None
    failed = 0
    tests = ([] if onlyDrift else list(TESTS)) + [lambda r: t_driftWallClock(r, 300 if long else 20)]
    for t in tests:
        name = getattr(t, "__name__", "t_driftWallClock")
        if name == "<lambda>":
            name = "t_driftWallClock"
        rig.reset()
        for mac, _, prefs in harness.RIG:
            p = dict(rig.nl.SHOW_PREF_DEFAULTS)
            p.update(prefs)
            rig.nl.lightShowPrefs[mac] = p
        try:
            t(rig)
            print("PASS", name)
        except Exception as e:
            failed += 1
            print("FAIL", name, "-", e)
            if not isinstance(e, AssertionError):
                traceback.print_exc()
        for line in RESULTS:
            print(line)
        RESULTS.clear()
    print("show tests:", len(tests) - failed, "passed,", failed, "failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
