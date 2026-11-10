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

    def selectedLights(self):
        return list(self.rows)

    def returnTableInfo(self, row, col):
        return "ON"


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
    time.sleep(0.7)
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
    rig.get("animate=Strobe|1|10|100|true|2", 0.6)  # legacy URL = override layer
    last = rig.rec.last(rig.mac(FILL))
    check(last[5] == 100 and hueOf(last) in (60, 120), "after the override ends the light must return to the sequence, got " + str(last))
    check(rig.getJSON("status_json")["sequence"]["state"] == "playing", "sequence keeps running under an override")


def t_onInterruptPause(rig):
    seq = stepSequence("oip", [0, 90, 180, 270], 500, on_interrupt="pause")
    rig.post("/NeewerLux/sequence", {"action": "play", "sequence": seq}, 0.3)
    rig.get("animate=Strobe|1|10|100|true|10||effect", 0.2)  # 10 loops of 100 ms (v1.3.0 hold timing)
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
    check(seq is not None and not warnings, "shipped example: %s %s" % (errors, warnings))


def t_guidSidecar(rig):
    """macOS addresses are GUIDs; their sidecars must still load show settings."""
    guid = "6F3A1C2E-0000-4000-8000-00000000ABCD"
    light = rig.nl.availableLights[AMB]
    oldDevice = light[0]
    light[0] = harness.FakeDevice(guid)
    path = os.path.join(rig.workdir, "light_prefs", guid)
    try:
        open(path, "w", encoding="utf-8").write("Ambient||||0|practical|left|0||60|-1|")
        rig.nl.loadLightAliases()
        check(rig.nl.lightShowPrefs.get(guid, {}).get("role") == "practical", "GUID sidecar not loaded")
        check(rig.nl.getLightShowPref(AMB, "maxBri") == 60, "GUID light limit")
    finally:
        light[0] = oldDevice
        os.remove(path)
        rig.nl.loadLightAliases()


def t_statusShape(rig):
    st = rig.getJSON("status_json")
    check(set(st) == {"layers", "sequence", "lights"}, "status keys")
    check([l["role"] for l in st["lights"]] == ["key", "fill", "rim", "ambient"], "roles in status")
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


TESTS = [t_maxBrightnessHTTP, t_maxBrightnessAnimationAndSequence, t_minBrightness, t_globalDefaultLimit,
         t_slidersExempt, t_lockedLight, t_roleTargets, t_effectOverPartOfRigRejoinsInSync, t_revertToPresetAtEnd,
         t_endPreset, t_holdAtEnd, t_pauseRevertsAndResumes, t_seekAndSetPosition, t_effectQueueReplaceFull,
         t_effectCap, t_overrideOverSequence, t_onInterruptPause, t_baseWriteDuringSequenceBecomesRevertTarget,
         t_manualCommandStopsAnimationAndReverts, t_postBatchDelivers, t_postPlayEmptyName,
         t_sequenceValidateSaveListPlay, t_clipStretchAndTarget, t_docExamplesValidate, t_guidSidecar, t_statusShape, t_driftVirtualClock]


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
