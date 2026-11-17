"""Records every write NeewerLux sends to its lights, to prove a refactor changes none of them.

The corpus runs the real code (show compositor, NeewerLux's hooks, brightness limits, the
CCT-only fallback, the flash guard, the BLE write paths) on a virtual clock, with the worker
replaced by a loop that drains its queues in the worker's order. Every shipped animation,
sequence and sound mode plays, plus scenarios for the hand-overs between layers and base
writes; items named desktop/ run with a main window, through the preset buttons and sliders.
An exception in an item is recorded as its last write ("error"), so it fails that item only.
The clock is virtual, so the result is exact: the same code gives the same writes,
and a refactor that keeps behaviour gives the same writes too. Writes are compared per light
(the order between lights in one synchronized send is not behaviour).

  python tests/record_writes.py                compare against tests/baselines/writes_corpus.json.gz
  python tests/record_writes.py --record       write that baseline (only before a product change, never to make a refactor pass)
  python tests/record_writes.py --only Strobe  run the items whose name contains Strobe, print their writes
  python tests/record_writes.py --trace ...    the test-suite trace (see trace_compare below)

The baseline holds every write, so a mismatch names the item, the light, the first write
that differs and both values.
"""
import gzip
import json
import math
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import harness  # noqa: E402

BASELINE = os.path.join(HERE, "baselines", "writes_corpus.json.gz")
ANIMATION_RUN_S = 12.0      # stopped here (most loop forever), then handed back
SEQUENCE_MAX_S = 90.0       # long starter sequences are cut here
SOUND_RUN_S = 8.0
TAIL_S = 1.5                # after the stop: hand-back fades and reverts
FPS = 20                    # animation update rate: enough frames to cover keyframe fades
MAX_STEPS = 400000


class VirtualRun:
    """One booted NeewerLux driven on a virtual clock."""

    def __init__(self, rig):
        self.rig = rig
        self.nl = rig.nl
        self.show = rig.nl.show
        self.vt = 0.0
        self.writes = []
        self.files = {}
        self.heldAt = {}
        for i in range(len(harness.RIG)):
            dev = rig.device(i)
            dev.latencyMs = (0, 0)  # no sleeps: a synchronized send writes in a fixed order
            dev.onWrite = self._onWrite
        nl = self.nl
        nl.audioEngine.sourceFactory = lambda device: None  # not the soundcard: sound modes need only numpy then
        nl.audioEngine.start = lambda *a, **k: None
        nl.audioEngine.stop = lambda *a, **k: None
        nl.audioEngine.features = lambda: self.show.syntheticSoundFeatures(self.vt * 1000.0, 120.0)
        self.lights = rig.lightsSnapshot()  # restored before each item: a restart scenario rebuilds them
        self.app = None
        self.win = None

    def clock(self):
        return self.vt

    def _onWrite(self, mac, data):
        if len(data) > 1 and data[1] in (132, 133):
            return
        self.writes.append((round(self.vt * 1000.0, 3), mac, list(data)))

    def fresh(self, setup=None, gui=False):
        """Everything back to a known state, with a new compositor and flash guards on this clock.
        gui: a new main window (desktop items), else none, as with HTTP alone."""
        nl, show = self.nl, self.show
        self.vt = 0.0
        self.writes = []
        self.files = {}
        self.heldAt = {}
        for path in self._prefsFiles():
            os.remove(path)
        nl.rememberLightsOnExit = False
        nl.rememberPresetsOnExit = True
        nl.presetNames.clear()
        self.rig.restoreLights(self.lights)
        self.newEngine()
        nl.flashGuardEnabled = True
        nl.eyelineFlash = "same"
        nl.cctFallbackMode = "convert"
        nl.animRevertOnFinish = True
        nl.handbackFadeMs = 0
        nl.fadeInMs = 0
        nl.livePreview = True
        nl.animParallelWrites = True
        nl.animationRunning = False
        nl.currentAnimationName = ""
        nl.threadAction = ""
        nl._pendingSends.clear()
        nl._flashHeld.clear()
        nl._lightsOff.clear()
        nl._lastWritten.clear()
        nl.presetSounds.clear()
        nl.presetFades.clear()
        nl.customLightPresets[:] = nl.buildDefaultPresets(nl.numOfPresets)
        self.rig.resetLights(on=True)
        for i, (mac, _, prefs) in enumerate(harness.RIG):
            p = dict(nl.SHOW_PREF_DEFAULTS)
            p.update(prefs)
            nl.lightShowPrefs[mac] = p
        self._window(gui)
        nl.threadAction = ""
        if setup:
            setup(self)

    def newEngine(self):
        """A new compositor and flash guards on this clock, as at start."""
        nl, show = self.nl, self.show
        nl.showEngine = show.ShowCompositor(nl._ShowHooks(), clock=self.clock)
        nl.flashGuard = show.FlashGuard(clock=self.clock)
        for key, guard in list(nl.eyelineGuards.items()):
            nl.eyelineGuards[key] = show.FlashGuard(limit=guard.limit, clock=self.clock)

    def _window(self, gui):
        """A new main window for each desktop item, so sliders and selection left by one item
        can't change the next (a slider set to the value it already has sends nothing)."""
        nl = self.nl
        if self.win is not None:
            # not close(): its closeEvent is the app's quit path
            self.win.deleteLater()
            self.app.processEvents()
            self.win = None
        nl.mainWindow = None
        if gui:
            self.app = nl.QApplication.instance() or nl.QApplication([])
            self.win = nl.MainWindow()
            nl.mainWindow = self.win
            self.win.updateLights()
            self.app.processEvents()

    def restart(self):
        """Quit with Remember light settings on exit, start again: the lights are rebuilt from
        their saved files, with a new compositor."""
        self.captureFiles()
        self.rig.rediscover()
        self.newEngine()
        if self.win is not None:
            self.win.updateLights()

    def _prefsFiles(self):
        folder = os.path.join(self.rig.workdir, "light_prefs")
        names = [mac.replace(":", "") for mac, _, _ in harness.RIG] + [os.path.basename(self.nl.customLightPresetsFile)]
        return [os.path.join(folder, n) for n in names if os.path.exists(os.path.join(folder, n))]

    def captureFiles(self):
        """What saving does now: each light's side-car file (with Remember light settings on exit)
        and the presets file, recorded with this item as file:<name>."""
        nl = self.nl
        nl.rememberLightsOnExit = True
        for i in range(len(harness.RIG)):
            nl.saveLightPrefs(i)
        nl.savePresetsToFile()
        for path in self._prefsFiles():
            with open(path, encoding="utf-8") as f:
                self.files["file:" + os.path.basename(path)] = [[0, f.read()]]

    def drain(self):
        """One pass of the worker's queues, in its order: thread actions, queued sends, values
        the flash guard held back (once 40 ms have passed), show frames."""
        nl, loop = self.nl, self.nl.asyncioEventLoop
        action = nl.threadAction
        if action == "send":
            nl.threadAction = loop.run_until_complete(nl.writeToLight())
        elif action.startswith("psend|"):
            loop.run_until_complete(nl.parallelWriteToLights([int(x) for x in action.split("|")[1:]]))
            nl.threadAction = ""
        elif action not in ("", "HTTP"):
            result = nl.processMultipleSends(loop, action)
            nl.threadAction = result if result is not None else ""
        if nl.threadAction == "" and nl._pendingSends:
            pending = nl._takePendingSends()
            if pending:
                loop.run_until_complete(nl.parallelWriteToLights(pending))
        self._noteHeld()
        due = [i for i, t in sorted(self.heldAt.items()) if self.vt - t >= 0.04 - 1e-9]
        if due and nl.threadAction == "":
            for i in due:
                nl._flashHeld.pop(i, None)
                self.heldAt.pop(i, None)
            loop.run_until_complete(nl.parallelWriteToLights(due, fromShow=True))
        if nl.threadAction == "" and nl.showEngine.hasPending():
            nl.sendShowFrames(loop, nl.showEngine.takeMailbox())
        self._noteHeld()

    def _noteHeld(self):
        for i in list(self.nl._flashHeld):
            self.heldAt.setdefault(i, self.vt)
        for i in list(self.heldAt):
            if i not in self.nl._flashHeld:
                del self.heldAt[i]

    def run(self, events, untilS):
        """events: [(seconds, fn(run))], run in order at their times. Returns this item's writes
        per light: {mac: [[ms, bytes], ...]}."""
        events = sorted(events, key=lambda e: e[0])
        try:
            self.drain()  # what the setup sent goes out first, as the worker would have sent it
            self._loop(events, untilS)
        except Exception as e:
            self.writes.append((round(self.vt * 1000.0, 3), "error", "%s: %s" % (type(e).__name__, e)))
        out = {}
        for ms, mac, data in self.writes:
            out.setdefault(mac, []).append([ms, data])
        out.update(self.files)
        return out

    def _loop(self, events, untilS):
        eng = None
        steps = 0
        while True:
            eng = self.nl.showEngine
            while events and events[0][0] <= self.vt + 1e-9:
                result = events.pop(0)[1](self)
                if isinstance(result, dict) and result.get("success") is False:
                    raise RuntimeError("an event failed at %.3f s: %r" % (self.vt, result))
                eng = self.nl.showEngine
                self.drain()
            eng.tick(self.vt)
            self.drain()
            nxt = math.inf
            if eng.anyActive():
                nxt = eng.nextDueMs(self.vt * 1000.0) / 1000.0
            if self.heldAt:
                nxt = min(nxt, min(self.heldAt.values()) + 0.04)
            if events:
                nxt = min(nxt, events[0][0])
            if nxt > untilS:
                break
            self.vt = max(nxt, self.vt)
            steps += 1
            if steps > MAX_STEPS:
                raise RuntimeError("no end after %d steps at %.3f s" % (steps, self.vt))


# ------------------------------------------------------------------ the corpus

def _started(result):
    """startAnimation's result, raising when it didn't start (a renamed shipped animation)."""
    if result is False:
        raise RuntimeError("animation did not start")
    return result


def _http(run, query):
    run.rig.get(query)


def _post(run, path, body):
    run.rig.post(path, body)


def _savePreset(run, index, entries, fadeMs=None):
    body = {"action": "save", "index": index, "name": "P%d" % index, "entries": entries}
    if fadeMs is not None:
        body["fade_ms"] = fadeMs
    _post(run, "/NeewerLux/presets", body)


def _settings(run, **values):
    _post(run, "/NeewerLux/settings", {"action": "set_global", "settings": values})


def _snapshotEntries():
    return [{"target": "1", "mode": "CCT", "bri": 60, "temp": 4400},
            {"target": "2", "mode": "HSI", "bri": 50, "hue": 200, "sat": 80},
            {"target": "3", "mode": "HSI", "bri": 90, "hue": 20, "sat": 100},
            {"target": "4", "mode": "CCT", "bri": 30, "temp": 3200}]


def _anyName(names, *prefer):
    for p in prefer:
        if p in names:
            return p
    return sorted(names)[0]


def items(nl):
    """[(name, setup, events, untilS)]: the whole corpus, in a fixed order."""
    out = []
    for name in sorted(nl.savedAnimations):
        out.append(("animation/" + name, None,
                    [(0.0, lambda r, n=name: _started(r.nl.startAnimation(n, r.nl.asyncioEventLoop, fps=FPS))),
                     (ANIMATION_RUN_S, lambda r: r.nl.stopAnimation())], ANIMATION_RUN_S + TAIL_S))
    for name in sorted(nl.savedSequences):
        seq, _, _ = nl.buildSequence(nl.savedSequences[name])
        length = min(SEQUENCE_MAX_S, (seq.duration or 30000) / 1000.0 if seq is not None else 30.0)
        out.append(("sequence/" + name, None,
                    [(0.0, lambda r, n=name: r.nl.startSequence(n)),
                     (length, lambda r: r.nl.showEngine.stopSequence())], length + TAIL_S))
    for name in sorted(nl.savedSoundModes):
        out.append(("sound/" + name, None,
                    [(0.0, lambda r, n=name: r.nl.startSound(n)),
                     (SOUND_RUN_S, lambda r: r.nl.stopSound())], SOUND_RUN_S + TAIL_S))
    out.extend(scenarios(nl))
    return out


def scenarios(nl):
    anims = set(nl.savedAnimations)
    seqs = set(nl.savedSequences)
    chase = _anyName(anims, "Rainbow Chase")
    flash = _anyName(anims, "Alternating Flash")
    strobe = _anyName(anims, "Strobe")
    wash = _anyName(anims, "Color Wash")
    demo = _anyName(seqs, "Example - Four Light Demo")

    def anim(name, **kw):
        return lambda r: _started(r.nl.startAnimation(name, r.nl.asyncioEventLoop, fps=FPS, **kw))

    def preset(n):
        return lambda r: r.nl.recallCustomPreset(n - 1, False, r.nl.asyncioEventLoop)

    inlineEndPreset = {"format": 1, "name": "Ends on preset", "duration_ms": 4000, "end": "preset:2",
                       "cues": [{"at_ms": 0, "target": "*", "state": {"mode": "HSI", "hue": 120, "sat": 100, "bri": 70}},
                                {"at_ms": 1000, "target": "*", "state": {"mode": "HSI", "hue": 120, "sat": 100, "bri": 20, "fade_ms": 800}},
                                {"at_ms": 2000, "target": "@rim", "state": {"mode": "CCT", "temp": 32, "bri": 90}}]}
    inlineSound = {"format": 1, "name": "Sound cue", "duration_ms": 6000, "end": "revert",
                   "cues": [{"at_ms": 0, "duration_ms": 3000, "target": "@rim;@background", "sound": "Pulse"},
                            {"at_ms": 3000, "target": "*", "state": {"mode": "HSI", "hue": 300, "sat": 90, "bri": 60, "fade_ms": 800}}]}

    sceneAnim = {"name": "Scenes", "loop": True, "keyframes": [
        {"hold_ms": 600, "fade_ms": 0, "lights": {"1": {"mode": "SCENE", "scene": 2, "bri": 60}, "4": {"mode": "SCENE", "scene": 7, "bri": 40}}},
        {"hold_ms": 600, "fade_ms": 300, "lights": {"1": {"mode": "HSI", "hue": 50, "sat": 100, "bri": 60}, "4": {"mode": "CCT", "temp": 44, "bri": 70}}}]}
    presetMix = [
        (1, [{"target": "-1", "mode": "HSI", "bri": 55, "hue": 15, "sat": 90}], None),
        (2, _snapshotEntries(), 600),
        (3, [{"target": "1", "mode": "CCT", "bri": 70, "temp": 5200}, {"target": "2", "mode": "CCT", "bri": 40, "temp": 3600, "off": True},
             {"target": "3", "mode": "Scene", "bri": 50, "scene": 6}, {"target": "4", "mode": "HSI", "bri": 20, "hue": 330, "sat": 60, "off": True}], 0),
        (4, [{"target": "-1", "mode": "CCT", "bri": 35, "temp": 2900}], 1500),
        (5, [dict(_snapshotEntries()[2], sound="Beat Chase"), dict(_snapshotEntries()[3], sound="Pulse"), _snapshotEntries()[0]], None),
    ]

    def savePresetMix(r):
        for idx, entries, fade in presetMix:
            _savePreset(r, idx, entries, fade)

    def reloadPresets(r):
        # what a restart does: read the saved file back, then the next save must write the same file
        r.nl.savePresetsToFile()
        r.nl.customLightPresets[:] = r.nl.buildDefaultPresets(r.nl.numOfPresets)
        r.nl.presetFades.clear()
        r.nl.presetSounds.clear()
        r.nl.presetNames.clear()
        r.nl.loadCustomPresets(r.nl.customLightPresetsFile)

    S = []
    S.append(("scenario/preset during sequence", lambda r: _savePreset(r, 2, _snapshotEntries()),
              [(0.0, lambda r: r.nl.startSequence(demo)), (3.0, preset(2)),
               (8.0, lambda r: r.nl.showEngine.stopSequence())], 10.0))
    S.append(("scenario/effect over sequence with fades", lambda r: _settings(r, fadeInMs=400, handbackFadeMs=600),
              [(0.0, lambda r: r.nl.startSequence(demo)), (2.0, anim(flash, layer="effect", queueMode="replace")),
               (6.0, lambda r: r.nl.stopAnimation("effect")), (9.0, lambda r: r.nl.showEngine.stopSequence())], 11.0))
    S.append(("scenario/effect queue", None,
              [(0.0, anim(flash, layer="effect", maxLoops=1)), (0.5, anim(wash, layer="effect", maxLoops=1)),
               (1.0, anim(chase, layer="effect", maxLoops=1))], 30.0))
    S.append(("scenario/sound taken over by light command and preset", lambda r: _savePreset(r, 3, [{"target": "-1", "mode": "CCT", "bri": 40, "temp": 5000}]),
              [(0.0, lambda r: r.nl.startSound("Pulse")), (2.0, lambda r: _http(r, "light=3&mode=HSI&hue=240&sat=100&bri=50")),
               (4.0, preset(3)), (6.0, lambda r: r.nl.stopSound())], 8.0))
    S.append(("scenario/sound on some lights", None,
              [(0.0, lambda r: r.nl.startSound("Pulse", lights="@rim")), (1.0, lambda r: r.nl.startSound("Bands", lights="@background")),
               (3.0, lambda r: r.nl.stopSound(lights="@rim")), (5.0, lambda r: r.nl.stopSound())], 7.0))
    S.append(("scenario/off during show", lambda r: _http(r, "light=2&mode=HSI&hue=140&sat=60&bri=35"),
              [(0.0, anim(chase, layer="show")), (2.0, lambda r: _http(r, "light=2&off")),
               (3.0, lambda r: r.captureFiles()),
               (4.0, lambda r: _http(r, "light=2&on")), (6.0, lambda r: r.nl.stopAnimation("show"))], 8.0))
    S.append(("scenario/locked light", lambda r: r.rig.setShowPrefs(1, locked=True),
              [(0.0, anim(chase)), (5.0, lambda r: r.nl.stopAnimation())], 6.5))
    S.append(("scenario/brightness limits", lambda r: (r.rig.setShowPrefs(2, maxBri=40), r.rig.setShowPrefs(3, minBri=20)),
              [(0.0, anim(chase)), (4.0, lambda r: _http(r, "light=3&mode=HSI&hue=10&sat=100&bri=100")),
               (4.5, lambda r: _http(r, "light=4&mode=CCT&temp=4000&bri=5")),
               (5.0, lambda r: r.nl.stopAnimation()), (5.5, lambda r: _http(r, "light=3&mode=CCT&temp=5600&bri=100"))], 6.5))
    S.append(("scenario/cct-only convert", lambda r: r.rig.setCCTOnly(3, True),
              [(0.0, anim(chase)), (5.0, lambda r: r.nl.stopAnimation()), (5.5, lambda r: _http(r, "light=4&mode=HSI&hue=0&sat=100&bri=80")),
               (6.0, lambda r: _http(r, "light=4&mode=SCENE&scene=4&bri=70")),
               (6.5, lambda r: _started(r.nl.startAnimation(sceneAnim, r.nl.asyncioEventLoop, fps=FPS))),
               (9.0, lambda r: r.nl.stopAnimation()), (9.5, lambda r: r.captureFiles())], 10.0))
    S.append(("scenario/cct-only ignore", lambda r: (r.rig.setCCTOnly(3, True), _settings(r, cctFallbackMode="ignore")),
              [(0.0, anim(chase)), (5.0, lambda r: r.nl.stopAnimation())], 6.5))
    S.append(("scenario/no revert", lambda r: setattr(r.nl, "animRevertOnFinish", False),
              [(0.0, anim(wash)), (3.0, lambda r: r.nl.stopAnimation()), (4.0, anim(chase)), (6.0, lambda r: r.nl.stopAnimation())], 7.0))
    S.append(("scenario/chained override", None,
              [(0.0, anim(chase)), (2.0, anim(wash)), (4.0, lambda r: r.nl.stopAnimation())], 5.0))
    S.append(("scenario/pause seek resume", None,
              [(0.0, lambda r: r.nl.startSequence(demo)), (2.0, lambda r: r.nl.showEngine.pauseSequence()),
               (3.0, lambda r: r.nl.showEngine.seekSequence(5000)), (4.0, lambda r: r.nl.showEngine.resumeSequence()),
               (6.0, lambda r: r.nl.showEngine.setSequencePosition(1000)), (9.0, lambda r: r.nl.showEngine.stopSequence())], 10.0))
    S.append(("scenario/watchdog", None,
              [(0.0, lambda r: r.nl.startSequence(demo, watchdogMs=1000)), (0.5, lambda r: r.nl.showEngine.setSequencePosition(500)),
               (3.0, lambda r: r.nl.showEngine.setSequencePosition(4000)), (6.0, lambda r: r.nl.showEngine.stopSequence())], 7.0))
    S.append(("scenario/sequence brightness", None,
              [(0.0, lambda r: r.nl.startSequence(demo, brightness=50)), (6.0, lambda r: r.nl.showEngine.stopSequence())], 7.0))
    S.append(("scenario/preset fades", lambda r: (_savePreset(r, 2, _snapshotEntries(), fadeMs=800),
                                                   _savePreset(r, 3, [{"target": "-1", "mode": "HSI", "bri": 70, "hue": 280, "sat": 100}], fadeMs=1200)),
              [(0.5, preset(2)), (0.9, preset(3)), (3.0, preset(2)), (3.5, lambda r: _http(r, "light=1&mode=CCT&temp=3200&bri=20"))], 5.0))
    S.append(("scenario/global fade in and hand back", lambda r: _settings(r, fadeInMs=700, handbackFadeMs=900),
              [(0.0, anim(chase, layer="show")), (3.0, anim(flash, layer="effect", queueMode="replace")),
               (5.0, lambda r: r.nl.stopAnimation("effect")), (7.0, lambda r: r.nl.stopAnimation("show"))], 9.0))
    S.append(("scenario/sequence ends on preset", lambda r: _savePreset(r, 2, _snapshotEntries()),
              [(0.0, lambda r: r.nl.startSequence(inlineEndPreset))], 6.0))
    S.append(("scenario/sequence with sound cue", None,
              [(0.0, lambda r: r.nl.startSequence(inlineSound))], 7.5))
    S.append(("scenario/preset as effect", lambda r: _savePreset(r, 2, _snapshotEntries()),
              [(0.0, lambda r: r.nl.startSound("Pulse")), (1.0, lambda r: r.nl.playPresetEffect(1, 2000)),
               (5.0, lambda r: r.nl.stopSound())], 6.5))
    S.append(("scenario/preset with sound", lambda r: _savePreset(r, 2, [dict(_snapshotEntries()[2], sound="Pulse"), _snapshotEntries()[0]]),
              [(0.0, lambda r: r.nl.startSound("Bands")), (1.0, preset(2)), (4.0, lambda r: r.nl.stopSound())], 5.5))
    S.append(("scenario/flash guard holds", None,
              [(0.0, lambda r: _started(r.nl.startAnimation(strobe, r.nl.asyncioEventLoop, 4.0, fps=FPS))), (4.0, lambda r: r.nl.stopAnimation())], 5.0))
    S.append(("scenario/eye line calm", lambda r: (r.rig.setShowPrefs(2, eyeline=True), setattr(r.nl, "eyelineFlash", "calm")),
              [(0.0, anim(flash)), (5.0, lambda r: r.nl.stopAnimation())], 6.0))
    S.append(("scenario/eye line calm strobe", lambda r: (r.rig.setShowPrefs(2, eyeline=True), setattr(r.nl, "eyelineFlash", "calm")),
              [(0.0, anim(strobe)), (14.0, lambda r: r.nl.stopAnimation())], 15.5))
    S.append(("scenario/eye line gentler strobe", lambda r: (r.rig.setShowPrefs(1, eyeline=True), setattr(r.nl, "eyelineFlash", "gentler")),
              [(0.0, anim(strobe)), (8.0, lambda r: r.nl.stopAnimation())], 9.5))
    S.append(("scenario/batch and power", None,
              [(0.0, lambda r: _http(r, "batch=1:HSI:30:100:50;2:CCT:3200:80;3:OFF;4:ANM:3:60")),
               (1.0, lambda r: _http(r, "light=3&on")), (1.5, lambda r: _http(r, "light=4&mode=SCENE&scene=5&bri=40")),
               (2.0, lambda r: _http(r, "light=1;2&mode=HSI&hue=100&sat=50&bri=30"))], 3.0))
    S.append(("scenario/off and on during sound hand back to base", None,
              [(0.0, lambda r: _http(r, "light=*&mode=CCT&temp=33&bri=40")), (0.5, lambda r: r.nl.startSound("Pulse")),
               (1.5, lambda r: _http(r, "light=3&off")), (2.0, lambda r: _http(r, "light=3&on")),
               (3.0, lambda r: r.captureFiles()), (3.5, lambda r: r.nl.stopSound()), (4.0, lambda r: _http(r, "light=3&off"))], 5.5))
    S.append(("scenario/off and on during show hand back to base", None,
              [(0.0, lambda r: _http(r, "light=2&mode=HSI&hue=60&sat=70&bri=45")), (0.5, anim(chase, layer="show")),
               (2.0, lambda r: _http(r, "light=2&off")), (3.0, lambda r: _http(r, "light=2&on")),
               (4.0, lambda r: r.captureFiles()), (5.0, lambda r: r.nl.stopAnimation("show"))], 6.5))
    S.append(("scenario/presets saved, reloaded and recalled", savePresetMix,
              [(0.1, reloadPresets)] + [(0.5 + k * 1.5, preset(n)) for k, n in enumerate((1, 2, 3, 4, 5, 2))] +
              [(11.0, lambda r: r.nl.stopSound()), (11.5, lambda r: r.captureFiles())], 12.5))
    S.append(("scenario/animation on target", None,
              [(0.0, anim(chase, layer="show", target="@rim;@background")), (4.0, lambda r: r.nl.stopAnimation("show"))], 5.0))
    S.extend(moreScenarios(nl, demo, chase, flash, wash, preset, anim))
    return S


def moreScenarios(nl, demo, chase, flash, wash, preset, anim):
    """Added for 1.5.0 m1a: the paths the first corpus left out (the Scene-mode global preset,
    the desktop's buttons and sliders, presets over effects, all lights off and on, sound on a
    CCT-only light, per-light CCT ranges, a restart from saved light files, serial writes)."""
    sceneGlobal = [{"target": "-1", "mode": "Scene", "bri": 50, "scene": 6}]
    cctAnim = {"name": "CCT sweep", "loop": True, "keyframes": [
        {"hold_ms": 500, "fade_ms": 0, "lights": {"*": {"mode": "CCT", "temp": 32, "bri": 60}}},
        {"hold_ms": 500, "fade_ms": 1000, "lights": {"*": {"mode": "CCT", "temp": 85, "bri": 90}}}]}

    def recall(n):
        return lambda r: _post(r, "/NeewerLux/presets", {"action": "recall", "index": n})

    def desktopPreset(n):
        return lambda r: r.nl.recallCustomPreset(n - 1)

    def select(rows):
        def go(r):
            r.win.lightTable.clearSelection()
            r.win.selectRows(rows)
        return go

    def sliders(**values):
        def go(r):
            for name, v in values.items():
                getattr(r.win, name).setValue(v)
        return go

    def setLight(i, **settings):
        return lambda r: _post(r, "/NeewerLux/settings", {"action": "set_light", "light": i, "settings": settings})

    def desktopSetup(r):
        _savePreset(r, 1, [{"target": "-1", "mode": "CCT", "bri": 45, "temp": 3900}])
        _savePreset(r, 2, [{"target": "-1", "mode": "HSI", "bri": 65, "hue": 210, "sat": 85}])
        _savePreset(r, 3, sceneGlobal)
        _savePreset(r, 4, [{"target": "-1", "mode": "Scene", "bri": 30, "scene": 2}], fadeMs=600)
        _savePreset(r, 5, _snapshotEntries())
        _savePreset(r, 6, [{"target": "-1", "mode": "HSI", "bri": 80, "hue": 20, "sat": 100}], fadeMs=500)

    S = []
    S.append(("scenario/scene global preset", lambda r: (_savePreset(r, 3, sceneGlobal),
                                                          _savePreset(r, 4, [{"target": "-1", "mode": "Scene", "bri": 25, "scene": 8}], fadeMs=800)),
              [(0.5, lambda r: _http(r, "use_preset=3")), (1.5, lambda r: r.nl.startSequence(demo)),
               (3.0, lambda r: _http(r, "use_preset=3")), (6.0, lambda r: r.nl.showEngine.stopSequence()),
               (7.5, lambda r: _http(r, "use_preset=4")), (9.0, recall(3)), (9.5, lambda r: _http(r, "use_preset=4&layer=effect&hold=1500")),
               (11.5, lambda r: r.captureFiles())], 12.5))
    S.append(("desktop/presets, sliders and power", desktopSetup,
              [(0.0, desktopPreset(3)), (1.0, desktopPreset(1)), (2.0, desktopPreset(2)), (3.0, desktopPreset(4)),
               (4.5, desktopPreset(5)), (5.5, select([1, 2])), (5.6, desktopPreset(6)),
               (6.5, select([1, 2])), (6.6, lambda r: r.win.ColorModeTabWidget.setCurrentIndex(0)),
               (6.7, sliders(Slider_CCT_Hue=41, Slider_CCT_Bright=55)),
               (7.5, select([0, 3])), (7.6, lambda r: r.win.ColorModeTabWidget.setCurrentIndex(1)),
               (7.7, sliders(Slider_HSI_1_H=300, Slider_HSI_2_S=70, Slider_HSI_3_L=40)),
               (8.5, select([2])), (8.6, lambda r: r.win.ColorModeTabWidget.setCurrentIndex(2)),
               (8.7, sliders(Slider_ANM_Brightness=35)), (8.8, lambda r: r.win.computeValueANM(5)),
               (9.5, select([0, 1, 2, 3])), (9.6, lambda r: r.win.turnLightOff()), (10.5, lambda r: r.win.turnLightOn()),
               (11.0, lambda r: r.captureFiles())], 12.0))
    S.append(("desktop/preset over a sequence", desktopSetup,
              [(0.0, lambda r: r.nl.startSequence(demo)), (2.0, desktopPreset(3)), (3.5, desktopPreset(6)),
               (5.0, desktopPreset(5)), (7.0, lambda r: r.nl.showEngine.stopSequence())], 9.0))
    S.append(("scenario/preset during effect and queue", lambda r: (_savePreset(r, 2, _snapshotEntries()),
                                                                     _savePreset(r, 3, [{"target": "-1", "mode": "HSI", "bri": 60, "hue": 100, "sat": 90}], fadeMs=700)),
              [(0.0, anim(flash, layer="effect", maxLoops=2)), (0.3, anim(wash, layer="effect", maxLoops=1)),
               (1.0, preset(2)), (2.5, preset(3)), (4.0, lambda r: _http(r, "use_preset=3&layer=effect&hold=1000&queue=replace"))], 20.0))
    S.append(("scenario/all off and on during show", lambda r: _http(r, "light=*&mode=CCT&temp=4800&bri=55"),
              [(0.0, anim(chase, layer="show")), (2.0, lambda r: _http(r, "light=*&off")), (3.0, lambda r: r.captureFiles()),
               (4.0, lambda r: _http(r, "light=*&on")), (6.0, lambda r: r.nl.stopAnimation("show"))], 8.0))
    S.append(("scenario/all off and on during sound", lambda r: _http(r, "light=*&mode=HSI&hue=30&sat=50&bri=45"),
              [(0.0, lambda r: r.nl.startSound("Beat Chase")), (2.0, lambda r: _http(r, "light=*&off")),
               (3.0, lambda r: _http(r, "light=*&on")), (5.0, lambda r: r.nl.stopSound())], 6.5))
    S.append(("scenario/sound on cct-only light", lambda r: r.rig.setCCTOnly(2, True),
              [(0.0, lambda r: r.nl.startSound("Colour Drift")), (5.0, lambda r: r.nl.stopSound())], 6.5))
    S.append(("scenario/sound on cct-only light ignored", lambda r: (r.rig.setCCTOnly(2, True), _settings(r, cctFallbackMode="ignore")),
              [(0.0, lambda r: r.nl.startSound("Colour Drift")), (5.0, lambda r: r.nl.stopSound())], 6.5))
    S.append(("scenario/per-light cct range", setLight(0, tempRange=[4000, 5000]),
              [(0.0, lambda r: _http(r, "light=1&mode=CCT&temp=3200&bri=50")), (0.5, lambda r: _http(r, "light=1&mode=CCT&temp=5600&bri=50")),
               (1.0, lambda r: _started(r.nl.startAnimation(cctAnim, r.nl.asyncioEventLoop, fps=FPS))),
               (5.0, lambda r: r.nl.stopAnimation()), (5.5, lambda r: r.captureFiles())], 6.5))
    S.append(("scenario/restart from saved light settings",
              lambda r: (setLight(0, tempRange=[3000, 6000])(r), setLight(3, cctOnly=True)(r),
                         _savePreset(r, 2, _snapshotEntries(), fadeMs=600)),
              [(0.0, lambda r: _http(r, "batch=1:CCT:3300:70;2:HSI:250:90:40;3:ANM:4:55;4:HSI:10:100:80")),
               (1.0, lambda r: _http(r, "light=3&off")), (1.5, lambda r: r.restart()),
               (2.0, anim(chase)), (5.0, lambda r: r.nl.stopAnimation()), (6.5, preset(2)),
               (8.0, lambda r: r.captureFiles())], 9.0))
    S.append(("scenario/serial writes", lambda r: setattr(r.nl, "animParallelWrites", False),
              [(0.0, anim(chase)), (1.2, lambda r: r.nl.stopAnimation())], 2.0))  # short: this path sleeps 50 ms a light
    return S


def runCorpus(only=None, quiet=False):
    rig = harness.boot(ROOT, worker=False)
    rig.nl.NLPythonServer.log_message = lambda *a: None
    run = VirtualRun(rig)
    result = {}
    started = time.time()
    for name, setup, events, untilS in items(rig.nl):
        if only and only.lower() not in name.lower():
            continue
        run.fresh(setup, gui=name.startswith("desktop/"))
        result[name] = run.run(events, untilS)
        if not quiet:
            n = sum(len(v) for v in result[name].values())
            print("  %-60s %6d writes" % (name, n), flush=True)
    run._window(False)
    if not quiet:
        print("%d items in %.0f s" % (len(result), time.time() - started))
    return result


def compare(base, now):
    """Mismatch messages: items missing or new, and the first differing write per light."""
    problems = []
    for name in sorted(set(base) | set(now)):
        if name not in now:
            problems.append(name + ": missing from this run")
            continue
        if name not in base:
            problems.append(name + ": not in the baseline")
            continue
        a, b = base[name], now[name]
        for mac in sorted(set(a) | set(b)):
            wa, wb = a.get(mac, []), b.get(mac, [])
            for k in range(max(len(wa), len(wb))):
                x = wa[k] if k < len(wa) else None
                y = wb[k] if k < len(wb) else None
                if x != y:
                    problems.append("%s, %s, write %d of %d/%d: baseline %s, now %s" % (name, mac, k + 1, len(wa), len(wb), x, y))
                    break
    return problems


def main(argv):
    if "--trace" in argv:
        import trace_compare
        return trace_compare.main([a for a in argv if a != "--trace"])
    only = None
    if "--only" in argv:
        only = argv[argv.index("--only") + 1]
    sys.argv = [sys.argv[0]]
    result = runCorpus(only, quiet="--quiet" in argv)
    if only:
        for name, perLight in result.items():
            print(name)
            for mac, writes in sorted(perLight.items()):
                for ms, data in writes:
                    print("   %10.3f  %s  %s" % (ms, mac, data))
        return 0
    if "--record" in argv:
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        with gzip.open(BASELINE, "wt", encoding="utf-8") as f:
            json.dump(result, f, separators=(",", ":"), sort_keys=True)
        print("recorded %d items to %s" % (len(result), os.path.relpath(BASELINE, ROOT)))
        return 0
    with gzip.open(BASELINE, "rt", encoding="utf-8") as f:
        base = json.load(f)
    problems = compare(base, result)
    for p in problems[:40]:
        print("MISMATCH " + p)
    if len(problems) > 40:
        print("... and %d more" % (len(problems) - 40))
    total = sum(len(w) for v in result.values() for w in v.values())
    print("write recorder: %d items, %d writes, %s" % (len(result), total, "PASS" if not problems else "%d FAILED" % len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
