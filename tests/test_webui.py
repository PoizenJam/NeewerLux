"""Web dashboard test: loads the real dashboard in a headless browser (Qt WebEngine, part of
PySide6) against the fake-Bluetooth harness, and drives every show feature through the page:
Stage tiles, table swatches, sequence list, play, pause, resume, seek, stop, render, reload,
light preferences and global preferences. Any JavaScript error fails the test.

Run: python tests/test_webui.py
"""

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
        js(page, """document.getElementById('lpRole').value = 'practical';
                    document.getElementById('lpMaxBri').value = '45';
                    document.getElementById('lpLocked').checked = true;
                    document.getElementById('lpName').value = 'Web Named';
                    saveLightPrefs();""")
        spin(600)
        mac = nl.availableLights[1][0].address.upper()
        prefs = nl.lightShowPrefs.get(mac, {})
        check(prefs.get("role") == "practical" and prefs.get("maxBri") == 45 and prefs.get("locked") is True, "show prefs: " + str(prefs))
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
                    document.getElementById('lpRole').value = 'ambient'; document.getElementById('lpSide').value = 'centre';
                    document.getElementById('lpOrder').value = '0'; document.getElementById('lpEyeline').checked = false;
                    document.getElementById('lpMaxBri').value = '-1'; document.getElementById('lpMinBri').value = '-1';
                    document.getElementById('lpLocked').checked = false; document.getElementById('lpName').value = '';
                    saveLightPrefs();""")
        spin(600)
        check(mac not in nl.lightShowPrefs and not os.path.exists(sidecar), "all-default light prefs should remove the sidecar")

    def globalPrefs():
        js(page, """document.getElementById('gpEnvMax').value = '80'; document.getElementById('gpSeqFps').value = '15';
                    document.getElementById('gpSim').value = '3'; saveGlobalPrefs();""")
        spin(600)
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
                    document.getElementById('gpSeqFps').value = '20'; document.getElementById('gpSim').value = '0'; saveGlobalPrefs();""")
        spin(600)
        check(nl.envMaxBri == 100 and not os.path.exists(nl.globalPrefsFile), "defaults again should remove the prefs file")
        js(page, "window.scrollTo(0, 0)")
        spin(300)
        view.grab().save(os.path.join(rig.workdir, "webui.png"))
        print("    screenshots: " + os.path.join(rig.workdir, "webui.png") + ", webui_render.png, webui_settings.png")

    def securityPrefsRefused():
        r = rig.post("/NeewerLux/settings", {"action": "set_global", "settings": {"acceptable_HTTP_IPs": "0."}})
        check(not r["success"] and "can't be changed" in r["errors"][0], "network settings must stay desktop-only: " + str(r))

    for name, fn in [("stage tiles and swatches", stage), ("sequence list", sequenceList),
                     ("play, pause, resume, seek, stop", playPauseSeekStop), ("render", render),
                     ("reload", reload), ("light preferences", lightPrefs), ("global preferences", globalPrefs),
                     ("network settings stay desktop-only", securityPrefsRefused)]:
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
