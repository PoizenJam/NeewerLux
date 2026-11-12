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
        check(0.45 <= w[-1][0] <= 0.75, "over about 0.6 s: %.0f ms" % (w[-1][0] * 1000))
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
            t0 = time.monotonic()
            rig.get("light=*&animate=Ambulance", 2.2)
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
    check(set(st) == {"apiVersion", "layers", "sequence", "lights", "flashGuard", "stage", "handbackFadeMs", "fadeInMs"}, "status keys: " + str(sorted(st)))
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
         t_addSimulatedRig, t_compositorWakesOnlyWhenDue]


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
