"""Web dashboard test: loads the real dashboard in a headless browser (Qt WebEngine, part of
PySide6) against the fake-Bluetooth harness, and drives every show feature through the page:
Stage tiles, table swatches, sequence list, play, pause, resume, seek, stop, render, reload,
light preferences and global preferences. Any JavaScript error fails the test.

Run: python tests/test_webui.py
"""

import json
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import harness  # noqa: E402

try:
    from PySide6.QtCore import QUrl, QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError as e:
    print("web UI test: SKIPPED (Qt WebEngine not available: %s)" % e)
    sys.exit(0)

EXAMPLE = "Example - Four Light Demo"


class Page(QWebEnginePage):
    def __init__(self):
        super().__init__()
        self.errors = []

    def javaScriptConsoleMessage(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            self.errors.append("%s (line %d)" % (message, line))


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def js(page, code, timeout=5000):
    """Run JavaScript and return its result, pumping Qt events until it arrives."""
    box = {}
    loop = QEventLoop()

    def done(result):
        box["r"] = result
        loop.quit()

    if "const " in code or "let " in code:
        code = "{" + code + "}"  # each snippet gets its own scope, so names can repeat
    page.runJavaScript(code, 0, done)
    QTimer.singleShot(timeout, loop.quit)
    loop.exec()
    if "r" not in box:
        raise AssertionError("JavaScript didn't answer: " + code[:80])
    return box["r"]


def waitFor(page, code, what, timeout=8.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if js(page, code):
            return
        spin(100)
    raise AssertionError("timed out waiting for " + what)


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    rig = harness.boot(ROOT)
    rig.nl.NLPythonServer.log_message = lambda *a: None
    nl = rig.nl
    if nl.audio.np is not None:
        # a looping kick at 124 BPM stands in for the sound card
        np = nl.audio.np
        t = np.arange(int(0.15 * 48000)) / 48000
        kick = 0.9 * np.sin(2 * np.pi * (50 + 80 * np.exp(-t * 30)) * t) * np.exp(-t * 12)
        signal = np.zeros(int(48000 * 16 * 60 / 124.0))
        for b in range(16):
            i = int(b * 48000 * 60 / 124.0)
            signal[i:i + len(kick)] += kick[:len(signal) - i]
        nl.audioEngine.sourceFactory = lambda device: nl.audio.ArraySource(signal, name="web test signal")
    app = QApplication.instance() or QApplication([])
    page = Page()
    view = QWebEngineView()  # a shown view, so the page counts as visible (it skips polling when hidden)
    view.setPage(page)
    view.resize(1400, 1000)
    view.show()
    loaded = QEventLoop()
    page.loadFinished.connect(lambda ok: loaded.quit())
    page.load(QUrl("http://127.0.0.1:%d/" % rig.port))
    QTimer.singleShot(15000, loaded.quit)
    loaded.exec()
    results = []

    def step(name, fn):
        try:
            fn()
            results.append(("PASS", name, ""))
        except AssertionError as e:
            results.append(("FAIL", name, str(e)))

    def stage():
        waitFor(page, "document.querySelectorAll('.stage-tile').length === 4", "4 stage tiles")
        rig.get("light=*&mode=HSI&hue=120&sat=100&bri=100", 0.5)
        waitFor(page, "[...document.querySelectorAll('.stage-box')].every(b => b.style.background.includes('0, 255, 0'))", "green tiles")
        check(js(page, "document.querySelectorAll('[data-swatch]').length") == 4, "table swatches")
        check(js(page, "document.querySelector('[data-swatch]').style.background").startswith("rgb(0, 255, 0"), "swatch colour")
        # plan view: each light in its cell (the harness rig is fill and background on the left,
        # key and rim on the right, all beside you by default)
        js(page, "setStageView('plan')")
        waitFor(page, "document.getElementById('stageGrid').classList.contains('stage-plan')", "plan layout")
        check(js(page, "document.querySelectorAll('#stageGrid svg[aria-label=\"camera\"]').length") >= 1, "the camera is drawn")
        waitFor(page, "document.querySelectorAll('#stageGrid .stage-tile').length === 4", "4 tiles in the plan")
        cells = json.loads(js(page, "JSON.stringify([...document.querySelectorAll('#stageGrid .pc')].map(c => [c.dataset.cell, c.querySelectorAll('.stage-tile').length]))"))
        got = {c: n for c, n in cells if n}
        check(got == {"left/beside": 2, "right/beside": 2}, "plan cells: " + str(got))
        check(js(page, "document.querySelectorAll('#stageGrid .hb').length") == 4, "height gauges")
        js(page, "setStageView('height')")
        waitFor(page, "document.querySelector('#stageGrid .pc[data-cell=\"left/middle\"]') !== null", "height view rows")
        js(page, "document.getElementById('stageGrid').scrollIntoView()")
        spin(400)
        view.grab().save(os.path.join(rig.workdir, "webui_plan.png"))
        js(page, "setStageView('strip')")
        waitFor(page, "document.getElementById('stageGrid').classList.contains('stage-grid')", "strip layout again")

    def sequenceList():
        waitFor(page, "[...document.querySelectorAll('#seqList .anim-item strong')].some(s => s.textContent === %r)" % EXAMPLE, "example in the list")

    def selectExample():
        js(page, "[...document.querySelectorAll('#seqList .anim-item')].find(i => i.querySelector('strong').textContent === %r).click()" % EXAMPLE)

    def playPauseSeekStop():
        selectExample()
        js(page, "seqPlay()")
        waitFor(page, "document.getElementById('seqStatus').textContent.startsWith('Playing: %s')" % EXAMPLE, "playing status")
        st = nl.showEngine.status()["sequence"]
        check(st is not None and st["state"] == "playing", "engine should be playing: " + str(st))
        js(page, "seqPauseResume()")
        waitFor(page, "document.getElementById('seqPauseBtn').textContent === 'Resume'", "paused")
        check(nl.showEngine.status()["sequence"]["state"] == "paused", "engine should be paused")
        js(page, "seqPauseResume()")
        waitFor(page, "document.getElementById('seqPauseBtn').textContent === 'Pause'", "resumed")
        # click three quarters along the progress bar
        js(page, """(() => { const b = document.getElementById('seqProgress').getBoundingClientRect();
                    seqSeek({clientX: b.left + b.width * 0.75}); })()""")
        spin(400)
        pos = nl.showEngine.status()["sequence"]["position_ms"]
        check(29000 <= pos <= 32000, "seek to 75%% of 40 s, got %d ms" % pos)
        js(page, "seqCmd('stop')")
        waitFor(page, "document.getElementById('seqStatus').textContent === 'No sequence playing'", "stopped")
        check(nl.showEngine.status()["sequence"] is None, "engine should have no sequence")

    def render():
        selectExample()
        js(page, "seqRender()")
        waitFor(page, "document.getElementById('renderModal').classList.contains('open')", "render dialog")
        check(js(page, "document.getElementById('renderCanvas').width") >= 700, "render canvas size")
        # a pixel in the middle of the first light's row must be coloured, not the background
        px = js(page, """(() => { const c = document.getElementById('renderCanvas');
                         const d = c.getContext('2d').getImageData(Math.floor(c.width * 0.6), 24 + 13, 1, 1).data;
                         return [d[0], d[1], d[2]]; })()""")
        check(px != [24, 24, 24], "render row is empty: " + str(px))
        check(js(page, "document.getElementById('renderCues').textContent.includes('@key')"), "cue list")
        spin(200)
        view.grab().save(os.path.join(rig.workdir, "webui_render.png"))
        js(page, "closeRender()")
        # with the sequence playing, the render shows a play marker, and a click seeks
        js(page, "seqPlay()")
        waitFor(page, "lastStatus && lastStatus.sequence && lastStatus.sequence.name === %r" % EXAMPLE, "playing")
        js(page, "seqRender()")
        waitFor(page, "document.getElementById('renderMarker').style.display === 'block'", "play marker shown")
        js(page, """(() => { const c = document.getElementById('renderCanvas'), r = c.getBoundingClientRect();
                    renderSeekClick({target: c, clientX: r.left + r.width * 0.9}); })()""")
        spin(400)
        pos = nl.getShowStatus()["sequence"]["position_ms"]
        check(pos > 25000, "clicking the render seeks: %s" % pos)
        js(page, "closeRender(); seqCmd('stop')")
        spin(300)

    def reload():
        path = os.path.join(rig.workdir, "light_prefs", "sequences", "Web Reload Check.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"format": 1, "name": "Web Reload Check", "duration_ms": 1000, "cues": [{"at_ms": 0, "target": "@all", "state": {"mode": "CCT", "temp": 40, "bri": 30}}]}')
        js(page, "seqReload()")
        waitFor(page, "[...document.querySelectorAll('#seqList strong')].some(s => s.textContent === 'Web Reload Check')", "reloaded sequence")

    def lightPrefs():
        js(page, "toggleSettings()")
        waitFor(page, "document.getElementById('lpLight').options.length === 4", "light list in settings")
        js(page, "document.getElementById('lpLight').value = '1'; fillLightPrefs();")
        # the position picker: click a cell and a height
        check(js(page, "document.querySelectorAll('#lpPos .pos-cell').length") == 9, "3 x 3 position grid")
        js(page, "document.querySelector('#lpPos .pos-cell[data-side=\"left\"][data-depth=\"back\"]').click()")
        js(page, "document.querySelector('#lpPos .pos-h[data-height=\"high\"]').click()")
        js(page, "document.querySelector('#lpPos .pos-aim button[data-aim=\"back\"]').click()")
        js(page, "document.getElementById('lpPos').scrollIntoView()")
        spin(300)
        view.grab().save(os.path.join(rig.workdir, "webui_position.png"))
        check(js(page, "document.querySelector('#lpPos .pos-cell.sel').dataset.side + '/' + document.querySelector('#lpPos .pos-cell.sel').dataset.depth") == "left/back", "picked cell")
        js(page, """document.getElementById('lpRole').value = 'practical';
                    document.getElementById('lpMaxBri').value = '45';
                    document.getElementById('lpLocked').checked = true;
                    document.getElementById('lpName').value = 'Web Named';
                    saveLightPrefs();""")
        spin(600)
        mac = nl.availableLights[1][0].address.upper()
        prefs = nl.lightShowPrefs.get(mac, {})
        check(prefs.get("role") == "practical" and prefs.get("maxBri") == 45 and prefs.get("locked") is True, "show prefs: " + str(prefs))
        check((prefs.get("side"), prefs.get("depth"), prefs.get("height"), prefs.get("aim")) == ("left", "back", "high", "back"), "position: " + str(prefs))
        check(nl.returnLightIndexesFromMacAddress("@back.left.high") == [1], "position targets")
        check(nl.availableLights[1][2] == "Web Named", "custom name")
        sidecar = os.path.join(rig.workdir, "light_prefs", nl.availableLights[1][0].address.replace(":", ""))
        check(os.path.exists(sidecar) and "Web Named" in open(sidecar, encoding="utf-8").read(), "sidecar file")
        # bad input is refused, nothing changes
        js(page, "document.getElementById('lpMaxBri').value = '400'; saveLightPrefs();")
        spin(500)
        check(nl.lightShowPrefs[mac]["maxBri"] == 45, "out-of-range max brightness must be refused")
        check(js(page, "document.getElementById('commandLog').textContent.includes('not saved')"), "refusal shown in the log")
        # put it back to defaults: the sidecar is deleted, as on the desktop
        js(page, """document.getElementById('lpLight').value = '1'; fillLightPrefs();
                    document.getElementById('lpRole').value = 'background'; lpPos = {side: 'centre', depth: 'beside', height: 'middle', aim: 'you'};
                    document.getElementById('lpOrder').value = '0'; document.getElementById('lpEyeline').checked = false;
                    document.getElementById('lpMaxBri').value = '-1'; document.getElementById('lpMinBri').value = '-1';
                    document.getElementById('lpLocked').checked = false; document.getElementById('lpName').value = '';
                    saveLightPrefs();""")
        spin(600)
        check(mac not in nl.lightShowPrefs and not os.path.exists(sidecar), "all-default light prefs should remove the sidecar")

    def globalPrefs():
        check("unsaved" not in js(page, "document.getElementById('gpSaveBtn').textContent"), "clean after loading")
        js(page, """const el = document.getElementById('gpEnvMax'); el.value = '80'; el.dispatchEvent(new Event('input'));""")
        check("unsaved" in js(page, "document.getElementById('gpSaveBtn').textContent"), "a change highlights Save")
        js(page, """document.getElementById('gpSeqFps').value = '15'; document.getElementById('gpCamera').value = 'front-left';
                    document.getElementById('gpEyelineFlash').value = 'gentler'; document.getElementById('gpHandback').value = '300';
                    document.getElementById('gpSim').value = '3'; saveGlobalPrefs();""")
        spin(600)
        check((nl.cameraPosition, nl.eyelineFlash, nl.handbackFadeMs) == ("front-left", "gentler", 300),
              "new global settings: %s %s %s" % (nl.cameraPosition, nl.eyelineFlash, nl.handbackFadeMs))
        check("unsaved" not in js(page, "document.getElementById('gpSaveBtn').textContent"), "saving clears the highlight")
        check(nl.envMaxBri == 80 and nl.seqFrameRate == 15 and nl.simulatedLights == 3, "globals: %s %s %s" % (nl.envMaxBri, nl.seqFrameRate, nl.simulatedLights))
        text = open(nl.globalPrefsFile, encoding="utf-8").read()
        check("envMaxBri=80" in text and "seqFrameRate=15" in text and "simulatedLights=3" in text, "prefs file: " + text)
        js(page, "document.getElementById('seqList').scrollIntoView()")
        spin(300)
        view.grab().save(os.path.join(rig.workdir, "webui_settings.png"))
        js(page, "document.getElementById('gpEnvMin').value = '90'; saveGlobalPrefs();")
        spin(500)
        check(nl.envMinBri == 0, "min above max must be refused")
        js(page, """document.getElementById('gpEnvMax').value = '100'; document.getElementById('gpEnvMin').value = '0';
                    document.getElementById('gpSeqFps').value = '20'; document.getElementById('gpSim').value = '0';
                    document.getElementById('gpCamera').value = 'front'; document.getElementById('gpEyelineFlash').value = 'same';
                    document.getElementById('gpHandback').value = '500'; saveGlobalPrefs();""")
        spin(600)
        check(nl.envMaxBri == 100 and not os.path.exists(nl.globalPrefsFile), "defaults again should remove the prefs file")
        nl.handbackFadeMs = 0  # back to the harness setting
        js(page, "window.scrollTo(0, 0)")
        spin(300)
        view.grab().save(os.path.join(rig.workdir, "webui.png"))
        print("    screenshots: " + os.path.join(rig.workdir, "webui.png") + ", webui_render.png, webui_settings.png, webui_timeline.png, webui_plan.png, webui_position.png, webui_sound.png")

    def flashGuardSetting():
        check(js(page, "document.getElementById('gpFlashGuard').checked") is True, "the guard shows as on")
        page.runJavaScript("window.confirm = () => false")
        js(page, "const b = document.getElementById('gpFlashGuard'); b.checked = false; gpFlashGuardChanged(b);")
        check(js(page, "document.getElementById('gpFlashGuard').checked") is True, "cancelling the warning keeps it on")
        page.runJavaScript("window.confirm = () => true")
        js(page, "const b = document.getElementById('gpFlashGuard'); b.checked = false; gpFlashGuardChanged(b); saveGlobalPrefs();")
        spin(600)
        check(nl.flashGuardEnabled is False, "turned off from the web")
        js(page, "document.getElementById('gpFlashGuard').checked = true; saveGlobalPrefs();")
        spin(600)
        check(nl.flashGuardEnabled is True, "and back on")

    def securityPrefsRefused():
        r = rig.post("/NeewerLux/settings", {"action": "set_global", "settings": {"acceptable_HTTP_IPs": "0."}})
        check(not r["success"] and "can't be changed" in r["errors"][0], "network settings must stay desktop-only: " + str(r))

    def presetEditor():
        P = "/NeewerLux/presets"
        # right-click menu has the desktop's entries
        js(page, "presetMenu({preventDefault(){}, clientX: 200, clientY: 200}, 2)")
        items = json.loads(js(page, "JSON.stringify([...document.querySelectorAll('#popupMenu div')].map(d => d.textContent))"))
        check(items == ["Recall", "Save current lights here", "Edit preset...", "Rename...", "Move left", "Move right", "Duplicate", "Delete"], "preset menu: " + str(items))
        js(page, "hideMenu(); peOpen(2)")
        waitFor(page, "document.getElementById('presetModal').classList.contains('open') && document.querySelectorAll('#peRows tr').length >= 1", "preset editor")
        js(page, """peAdd(); peRender();
                    const rows = document.querySelectorAll('#peRows tr'); const last = rows[rows.length - 1];
                    last.querySelector('.pe-target').value = '2'; last.querySelector('.pe-mode').value = 'HSI';
                    last.querySelector('.pe-mode').onchange();""")
        js(page, """const rows = document.querySelectorAll('#peRows tr'); const last = rows[rows.length - 1];
                    last.querySelector('.pe-hue').value = '275'; last.querySelector('.pe-bri').value = '35';
                    document.querySelectorAll('#peRows tr')[0].querySelector('.pe-target').value = '1';
                    document.getElementById('peName').value = 'Web Preset'; document.getElementById('peFade').value = '450'; peSave();""")
        spin(700)
        got = rig.post(P, {"action": "get", "index": 2})["preset"]
        check(got.get("fade_ms") == 450 and nl.presetFades.get(1) == 450, "preset fade from the web editor: " + str(got.get("fade_ms")))
        check(got["name"] == "Web Preset" and {"target": "2", "mode": "HSI", "bri": 35, "hue": 275, "sat": 100} in got["entries"], "saved from the web editor: " + str(got))
        check(not js(page, "document.getElementById('presetModal').classList.contains('open')"), "editor closes after saving")
        waitFor(page, "[...document.querySelectorAll('#presetGrid .preset-btn')].some(b => b.textContent.includes('Web Preset'))", "preset button shows the name")
        count = len(nl.customLightPresets)
        js(page, "presetAction('duplicate', 2, 'dup')")
        spin(500)
        check(len(nl.customLightPresets) == count + 1 and nl.presetNames.get(2) == "Web Preset (copy)", "duplicate from the web")
        check(nl.presetFades.get(2) == 450, "the copy keeps the fade")
        js(page, "presetAction('move', 3, 'moved', {direction: 'left'})")
        spin(500)
        check(nl.presetNames.get(1) == "Web Preset (copy)", "move from the web")
        js(page, "presetAction('delete', 2, 'deleted')")
        spin(500)
        check(len(nl.customLightPresets) == count, "delete from the web")
        nl.presetFades.clear()

    def animationEditor():
        A = "/NeewerLux/animate"
        js(page, "animNew()")
        waitFor(page, "document.getElementById('animModal').classList.contains('open')", "animation editor")
        js(page, """document.getElementById('aeName').value = 'Web Built';
                    document.getElementById('aeFadeIn').value = '250';
                    aeAddFrame();
                    document.getElementById('aeHold').value = '750'; aeFrameField();
                    aeAddLight();""")
        js(page, """const rows = document.querySelectorAll('#aeLights tr'); const r = rows[rows.length - 1];
                    r.querySelector('.ae-mode').value = 'CCT'; r.querySelector('.ae-mode').onchange();""")
        js(page, """const rows = document.querySelectorAll('#aeLights tr'); const r = rows[rows.length - 1];
                    r.querySelector('.ae-temp').value = '4100'; r.querySelector('.ae-bri').value = '60'; r.querySelector('.ae-bri').onchange();""")
        js(page, "aeSave()")
        spin(700)
        anim = nl.savedAnimations.get("Web Built")
        check(anim is not None and len(anim["keyframes"]) == 2, "saved from the web editor: " + str(anim))
        check(anim.get("fade_in_ms") == 250 and "handback_fade_ms" not in anim, "fades from the web editor: " + str(anim))
        kf = anim["keyframes"][1]
        check(kf["hold_ms"] == 750 and "*" not in kf["lights"] and kf["lights"]["1"] == {"mode": "CCT", "temp": 41, "bri": 60}, "frame 2: " + str(kf))
        # edit through the JSON tab, rename
        js(page, "selectedAnim = 'Web Built'; animEdit()")
        waitFor(page, "document.getElementById('animModal').classList.contains('open') && document.getElementById('aeName').value === 'Web Built'", "edit opens")
        js(page, """aeTab('json'); const kf = JSON.parse(document.getElementById('aeJsonText').value);
                    kf[0].fade_ms = 333; document.getElementById('aeJsonText').value = JSON.stringify(kf);
                    aeTab('visual'); document.getElementById('aeName').value = 'Web Built 2'; aeSave();""")
        spin(700)
        check("Web Built" not in nl.savedAnimations and nl.savedAnimations["Web Built 2"]["keyframes"][0]["fade_ms"] == 333, "JSON edit and rename")
        js(page, "selectedAnim = 'Web Built 2'; animDuplicate()")
        spin(600)
        check("Web Built 2 (copy)" in nl.savedAnimations, "duplicate")
        imported = {"name": "Web Imported", "loop": False, "keyframes": [{"hold_ms": 100, "fade_ms": 0, "lights": {"*": {"mode": "ON"}}}]}
        js(page, "animImport({files: [new File([%r], 'x.json')], value: ''})" % json.dumps(imported))
        spin(700)
        check("Web Imported" in nl.savedAnimations, "import from a file")
        page.runJavaScript("window.confirm = () => true")
        for n in ("Web Built 2", "Web Built 2 (copy)", "Web Imported"):
            js(page, "selectedAnim = %r; animDelete()" % n)
            spin(400)
        check(not any(n.startswith("Web ") for n in nl.savedAnimations), "delete")
        js(page, "document.getElementById('animParallel').checked = false; selectedAnim = 'Strobe'; playAnimation()")
        spin(500)
        check(nl.animParallelWrites is False, "the Parallel box reaches the player")
        js(page, "stopAnimation(); document.getElementById('animParallel').checked = true")
        nl.animParallelWrites = True
        spin(300)

    def until(cond, what, timeout=5.0):
        end = time.monotonic() + timeout
        while not cond():
            check(time.monotonic() < end, "timed out waiting for " + what)
            spin(50)

    def soundPanel():
        if nl.audio.np is None:
            waitFor(page, "document.getElementById('sndUnavailable').style.display === 'block'", "the note saying sound needs numpy")
            return
        waitFor(page, "!!sndDraft && document.getElementById('sndMode').options.length === %d" % len(nl.savedSoundModes), "the sound modes")
        js(page, "document.getElementById('sndMode').value = 'Pulse'; sndModeChosen('Pulse')")
        waitFor(page, "sndName === 'Pulse' && document.querySelectorAll('#sndParts .snd-part').length === 1", "Pulse in the editor")
        check(js(page, "document.getElementById('sndDevice').options.length") >= 1, "the device menu lists something")
        js(page, "sndStart()")
        until(lambda: nl.showEngine.soundPlayer() is not None, "Pulse to start")
        player = nl.showEngine.soundPlayer()
        js(page, "sndSlider('sensitivity', 250); sndSlider('floor', 90)")
        until(lambda: player.mode.sensitivity == 2.5 and player.mode.ceiling == 90, "sliders to apply live")
        js(page, "sndSlider('floor', 20); sndPal(0, 'hue', 120)")
        until(lambda: player.mode.palette[0]["hue"] == 120 and player.mode.floor == 20, "a palette edit to apply live")
        js(page, "sndPartAdd(); sndPart(1, 'target', '@fill'); sndPart(1, 'drive', 'high')")
        until(lambda: len(player.mode.parts) == 2 and player.mode.parts[1]["target"] == "@fill" and player.mode.parts[1]["drive"] == "high",
              "an added part to apply live")
        js(page, "sndPaletteKind('cct')")
        until(lambda: player.mode.palette == [{"temp": 2900}, {"temp": 4300}], "whites to apply live")
        waitFor(page, "document.getElementById('sndStatus').textContent.indexOf('Playing Pulse') === 0 && document.querySelectorAll('#sndMeters .snd-meter').length === 5", "the status and meters")
        js(page, "document.getElementById('soundCard').scrollIntoView()")
        spin(400)
        view.grab().save(os.path.join(rig.workdir, "webui_sound.png"))
        page.runJavaScript("window.prompt = () => 'Web Sound'; window.confirm = () => true")
        js(page, "sndSaveAs()")
        until(lambda: "Web Sound" in nl.savedSoundModes, "save as")
        saved = nl.savedSoundModes["Web Sound"]
        check(saved["palette"] == [{"temp": 2900}, {"temp": 4300}] and len(saved["parts"]) == 2 and saved["sensitivity"] == 2.5, str(saved))
        check(nl.savedSoundModes["Pulse"].get("sensitivity") == 1.0, "the original is untouched")
        waitFor(page, "sndName === 'Web Sound'", "the saved copy selected")
        js(page, "sndDelete()")
        until(lambda: "Web Sound" not in nl.savedSoundModes, "delete")
        js(page, "sndStop()")
        until(lambda: nl.showEngine.soundPlayer() is None, "stop")
        js(page, "window.scrollTo(0, 0)")

    def timelineEditor():
        page.runJavaScript("window.confirm = () => true")
        js(page, "selectedSeq = %r; tlOpenSelected()" % EXAMPLE)
        waitFor(page, "!!(tl && tl.render && document.getElementById('tlModal').classList.contains('open'))", "timeline editor with a render")
        tracks = json.loads(js(page, "JSON.stringify(tl.tracks.map(t => t.id))"))
        check(len([t for t in tracks if t is not None]) == 4, "one track per light: " + str(tracks))
        check(js(page, "document.querySelectorAll('#tlStage .stage-tile').length") == 4, "preview tiles")
        spin(300)
        view.grab().save(os.path.join(rig.workdir, "webui_timeline.png"))
        # double-click a hold tail on the first track at 25.3 s (snap 1 s)
        n0 = js(page, "tl.seq.cues.length")
        js(page, """document.getElementById('tlSnap').value = '1000';
                    const cv = document.getElementById('tlCanvas'), r = cv.getBoundingClientRect(), m = tlMetrics();
                    cv.dispatchEvent(new MouseEvent('dblclick', {bubbles: true, clientX: r.left + tlX(25300), clientY: r.top + m.rulerH + m.rowH * 0.4}));""")
        spin(300)
        check(js(page, "tl.seq.cues.length") == n0 + 1, "double-click adds a cue")
        cue = json.loads(js(page, "JSON.stringify(tl.seq.cues[tl.seq.cues.length - 1])"))
        check(cue["at_ms"] == 25000 and "state" in cue, "snapped new cue: " + str(cue))
        # drag it 2 s right
        js(page, """const cv = document.getElementById('tlCanvas'), r = cv.getBoundingClientRect(), m = tlMetrics();
                    const y = r.top + m.rulerH + m.rowH * 0.4, x0 = r.left + tlX(25000) + 3, x1 = r.left + tlX(27000) + 3;
                    cv.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0, clientX: x0, clientY: y}));
                    for (let k = 1; k <= 6; k++) window.dispatchEvent(new MouseEvent('mousemove', {bubbles: true, clientX: x0 + (x1 - x0) * k / 6, clientY: y}));
                    window.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, clientX: x1, clientY: y}));""")
        spin(300)
        check(js(page, "tl.seq.cues[tl.seq.cues.length - 1].at_ms") == 27000, "drag moves the cue")
        js(page, "tlUndo()")
        check(js(page, "tl.seq.cues[tl.seq.cues.length - 1].at_ms") == 25000, "undo")
        js(page, "tlRedo()")
        # properties: colour, then switch to a clip
        js(page, """document.getElementById('tpHue').value = '200'; document.getElementById('tpBri').value = '55';
                    document.getElementById('tpFade').value = '1200'; tlPropChanged();""")
        st = json.loads(js(page, "JSON.stringify(tl.seq.cues[tl.seq.cues.length - 1].state)"))
        check(st.get("hue") == 200 and st.get("bri") == 55 and st.get("fade_ms") == 1200, "colour properties: " + str(st))
        js(page, "document.getElementById('tpTarget').value = '@rim'; tlPropChanged();")
        spin(400)
        check(js(page, "tl.seq.cues[tl.seq.cues.length - 1].target") == "@rim", "target")
        js(page, "document.getElementById('tpKind').value = 'clip'; tlPropChanged();")
        js(page, "document.getElementById('tpClip').value = 'Heartbeat'; document.getElementById('tpFit').value = 'loop'; document.getElementById('tpDur').value = '3000'; tlPropChanged();")
        cue = json.loads(js(page, "JSON.stringify(tl.seq.cues[tl.seq.cues.length - 1])"))
        check(cue.get("clip") == {"name": "Heartbeat", "fit": "loop"} and cue.get("duration_ms") == 3000, "clip properties: " + str(cue))
        # copy, paste at the playhead, delete
        js(page, "tlCopy(); tlSetPlayhead(33000); tlPaste(tlSnapMs(tl.playhead));")
        check(js(page, "tl.seq.cues[tl.seq.cues.length - 1].at_ms") == 33000, "paste at the playhead")
        js(page, "tlDelete()")
        check(js(page, "tl.seq.cues.length") == n0 + 1, "delete")
        # settings, save under a new name (renames)
        js(page, "tlSettingsToggle(); document.getElementById('tlEnd').value = 'hold'; document.getElementById('tlFadeOut').value = '800'; tlSettingsApply();")
        check(js(page, "tl.seq.end") == "hold", "settings")
        check(js(page, "tl.seq.handback_fade_ms") == 800 and js(page, "tl.seq.fade_in_ms === undefined"), "fade settings")
        js(page, "document.getElementById('tlName').value = 'Web Timeline'; tlNameEdited(); tlSave(false)")
        spin(800)
        check("Web Timeline" in nl.savedSequences and EXAMPLE not in nl.savedSequences, "save renames: " + str(list(nl.savedSequences)))
        saved = nl.savedSequences["Web Timeline"]
        check(saved.get("end") == "hold" and any(isinstance(c.get("clip"), dict) and c["clip"]["name"] == "Heartbeat" and c["at_ms"] == 27000 for c in saved["cues"]), "edits saved")
        # screen-only preview leaves the lights alone; Send to lights plays from the playhead
        js(page, "tlSetPlayhead(0); tlPlay()")
        spin(500)
        js(page, "tlPause()")
        check(js(page, "tl.playhead") >= 300 and nl.showEngine.status()["sequence"] is None, "screen-only preview")
        js(page, "document.getElementById('tlSend').checked = true; tlSendToggled(); tlSetPlayhead(4000); tlPlay()")
        spin(800)
        st = nl.showEngine.status()["sequence"]
        check(st is not None and st["name"] == "Web Timeline" and 4300 <= st["position_ms"] <= 5800, "Send to lights: " + str(st))
        js(page, "tlPause()")
        spin(400)
        check(nl.showEngine.status()["sequence"] is None, "pausing stops the lights")
        js(page, "document.getElementById('tlSend').checked = false; tlSendToggled(); tlClose()")
        # +New from a starter
        js(page, "tlOpen(null, 'Starter - Countdown')")
        waitFor(page, "!!(tl && tl.original === null && tl.seq.name === 'Countdown' && tl.render)", "editor on a copy of a starter")
        check(js(page, "tl.seq.cues.length") == 21, "starter copied")
        js(page, "tl.dirty = false; tlClose()")
        # New, Duplicate, Delete from the panel
        js(page, "tlOpen(null)")
        waitFor(page, "!!(tl && tl.original === null && tl.render)", "new sequence")
        js(page, "tlSave(false)")
        spin(700)
        check(any(n.startswith("New Sequence") for n in nl.savedSequences), "a new sequence saves")
        js(page, "tlClose(); selectedSeq = 'Web Timeline'; seqDuplicate()")
        spin(800)
        check("Web Timeline (copy)" in nl.savedSequences, "duplicate")
        js(page, "selectedSeq = 'Web Timeline (copy)'; seqDelete()")
        spin(600)
        check("Web Timeline (copy)" not in nl.savedSequences, "delete")

    for name, fn in [("stage tiles and swatches", stage), ("sequence list", sequenceList),
                     ("play, pause, resume, seek, stop", playPauseSeekStop), ("render", render),
                     ("reload", reload), ("light preferences", lightPrefs), ("global preferences", globalPrefs), ("flash guard setting", flashGuardSetting),
                     ("network settings stay desktop-only", securityPrefsRefused), ("preset editor and menu", presetEditor),
                     ("animation editor, import, duplicate, delete", animationEditor), ("timeline editor", timelineEditor),
                     ("sound panel", soundPanel)]:
        step(name, fn)
    if page.errors:
        results.append(("FAIL", "no JavaScript errors", "; ".join(page.errors[:5])))
    failed = 0
    for status, name, msg in results:
        print(status, name + ((" - " + msg) if msg else ""))
        failed += status == "FAIL"
    print("web UI tests: %d passed, %d failed" % (len(results) - failed, failed))
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
