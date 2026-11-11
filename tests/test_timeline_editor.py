"""Timeline editor test: opens the real desktop editor offscreen against the fake rig and
edits a sequence with simulated mouse and keyboard input: add a cue by double-clicking a
track, drag it, resize a clip, change properties, undo and redo, copy and paste, save,
rename, and play with and without "Send to lights". Saves screenshots for a look.

Run: python tests/test_timeline_editor.py
"""
import json
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness  # noqa: E402

RESULTS = []


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    rig = harness.boot(os.path.dirname(HERE))
    nl = rig.nl
    nl.NLPythonServer.log_message = lambda *a: None
    app = nl.QApplication.instance() or nl.QApplication([])
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtCore import QPoint, Qt
    except ImportError:
        from PySide2.QtTest import QTest
        from PySide2.QtCore import QPoint, Qt
    import neewerlux_timeline as tl
    win = nl.MainWindow()
    nl.mainWindow = win
    win.updateLights()
    app.processEvents()

    def pump(ms=50):
        end = time.monotonic() + ms / 1000.0
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.005)

    def step(name, fn):
        try:
            fn()
            RESULTS.append(("PASS", name, ""))
        except AssertionError as e:
            RESULTS.append(("FAIL", name, str(e)))
        except Exception:
            import traceback
            RESULTS.append(("FAIL", name, traceback.format_exc()))

    state = {}

    def modelHelpers():
        check(tl.snapTime(1234, 100) == 1200 and tl.snapTime(1260, 100) == 1300, "fixed snap")
        check(tl.snapTime(1100, -1, bpm=120, offset=100) == 1100 and tl.snapTime(1300, -1, bpm=120, offset=100) == 1100, "beat snap with offset")
        check(tl.snapTime(370, -2, bpm=120) == 250, "half-beat snap")
        seq = {"duration_ms": 10000, "cues": [{"at_ms": 0, "state": {"mode": "HSI"}}, {"at_ms": 2000, "duration_ms": 1000, "clip": "x"},
                                              {"at_ms": 5000, "state": {"mode": "HSI"}}]}
        spans = tl.cueSpans(seq, [0, 1, 2])
        check(spans[0] == (0, 2000, True) and spans[1] == (2000, 3000, False) and spans[2] == (5000, 10000, True), "spans: " + str(spans))
        check(tl.colourAt([[0, "#000000"], [500, "#ffffff"]], 499)[1] == "#000000" and tl.colourAt([[0, "#000000"], [500, "#ffffff"]], 500)[1] == "#ffffff", "colourAt")

    def opens():
        win.seqRefreshList()
        for i in range(win.seqList.count()):
            if win.seqList.item(i).data(Qt.UserRole) == "Example - Four Light Demo":
                win.seqList.setCurrentRow(i)
        ed = win.seqEdit()
        check(ed is not None and ed.isVisible(), "editor window should open")
        ed.resize(1400, 820)
        pump(300)
        check(len([t for t in ed.tracks if t["index"] is not None]) == 4, "one track per light")
        check(ed.lastRender is not None and ed.lastRender["success"], "render on open")
        check(win.seqEdit() is ed, "editing the same sequence again brings the open window forward")
        ed.grab().save(os.path.join(rig.workdir, "editor.png"))
        RESULTS.append(("INFO", "screenshot", os.path.join(rig.workdir, "editor.png")))
        state["ed"] = ed

    def doubleClickAdds():
        ed = state["ed"]
        v = ed.view
        fm, rowH, rulerH, labelW = v.metrics()
        before = len(ed.seq["cues"])
        ed.snapCombo.setCurrentIndex([c[1] for c in tl.SNAP_CHOICES].index(1000))
        y = int(rulerH + rowH * 0.4)  # first track
        x = int(v.xFor(25300))  # empty stretch near the end
        QTest.mouseDClick(v, Qt.LeftButton, Qt.NoModifier, QPoint(x, y))
        pump(150)
        check(len(ed.seq["cues"]) == before + 1, "double-click should add a cue")
        cue = ed.seq["cues"][-1]
        check(cue["at_ms"] == 25000 and "state" in cue, "new cue snapped to 1 s: " + str(cue))
        check(cue["target"] == ed.tracks[0]["target"], "new cue targets the track's light")
        check(ed.selection == [len(ed.seq["cues"]) - 1] and ed.propStack.currentIndex() == 1, "new cue selected in the properties")
        state["new"] = len(ed.seq["cues"]) - 1

    def dragMoves():
        ed = state["ed"]
        v = ed.view
        i = state["new"]
        fm, rowH, rulerH, labelW = v.metrics()
        y = int(rulerH + rowH * 0.4)
        x0 = int(v.xFor(25000) + 3)
        x1 = int(v.xFor(27000) + 3)
        QTest.mousePress(v, Qt.LeftButton, Qt.NoModifier, QPoint(x0, y))
        for x in range(x0, x1 + 1, max(1, (x1 - x0) // 6)):
            QTest.mouseMove(v, QPoint(x, y))
            pump(10)
        QTest.mouseMove(v, QPoint(x1, y))
        QTest.mouseRelease(v, Qt.LeftButton, Qt.NoModifier, QPoint(x1, y))
        pump(150)
        check(ed.seq["cues"][i]["at_ms"] == 27000, "drag should move the cue to 27 s: %s" % ed.seq["cues"][i]["at_ms"])
        check(abs(ed.pStart.value() - 27.0) < 0.001, "properties follow the drag")

    def undoRedo():
        ed = state["ed"]
        i = state["new"]
        QTest.keyClick(ed, Qt.Key_Z, Qt.ControlModifier)
        pump(100)
        check(ed.seq["cues"][i]["at_ms"] == 25000, "undo puts the cue back")
        ed.redo()
        pump(100)
        check(ed.seq["cues"][i]["at_ms"] == 27000, "redo moves it again")

    def propertiesEdit():
        ed = state["ed"]
        i = state["new"]
        ed.setSelection([i])
        ed.pMode.setCurrentText("HSI")
        ed.pHue.setValue(222)
        ed.pBri.setValue(65)
        ed.pFade.setValue(1500)
        pump(100)
        st = ed.seq["cues"][i]["state"]
        check(st["mode"] == "HSI" and st["hue"] == 222 and st["bri"] == 65 and st["fade_ms"] == 1500, "colour properties: " + str(st))
        ed.pMode.setCurrentText("CCT")
        pump(50)
        ed.pTemp.setValue(4300)
        pump(50)
        st = ed.seq["cues"][i]["state"]
        check(st["mode"] == "CCT" and st["temp"] == 43 and "hue" not in st, "CCT properties stored in hundreds: " + str(st))
        idx = [ed.pTarget.itemData(k) for k in range(ed.pTarget.count())].index("@rim")
        ed.pTarget.setCurrentIndex(idx)
        ed._targetPicked(idx)
        pump(50)
        check(ed.seq["cues"][i]["target"] == "@rim", "picking a target stores the target, not its label: " + ed.seq["cues"][i]["target"])
        ed.pKind.setCurrentIndex(1)
        pump(80)
        cue = ed.seq["cues"][i]
        check("clip" in cue and "state" not in cue and cue["duration_ms"] > 0, "switching to a clip cue: " + str(cue))
        ed.pClip.setCurrentText("Heartbeat")
        ed.pFit.setCurrentIndex(1)
        ed.pDuration.setValue(3000)
        pump(80)
        check(ed.seq["cues"][i]["clip"] == {"name": "Heartbeat", "fit": "loop"} and ed.seq["cues"][i]["duration_ms"] == 3000, str(ed.seq["cues"][i]))

    def resizeEnd():
        ed = state["ed"]
        v = ed.view
        i = state["new"]
        fm, rowH, rulerH, labelW = v.metrics()
        row = next(r for r, t in enumerate(ed.tracks) if i in t["cues"])
        y = int(rulerH + rowH * row + rowH * 0.4)
        xEnd = int(v.xFor(30000))
        QTest.mousePress(v, Qt.LeftButton, Qt.NoModifier, QPoint(xEnd - 1, y))
        QTest.mouseMove(v, QPoint(xEnd + 10, y))
        QTest.mouseMove(v, QPoint(int(v.xFor(32000)), y))
        QTest.mouseRelease(v, Qt.LeftButton, Qt.NoModifier, QPoint(int(v.xFor(32000)), y))
        pump(150)
        check(ed.seq["cues"][i]["duration_ms"] == 5000, "dragging the right edge sets the length: %s" % ed.seq["cues"][i].get("duration_ms"))

    def copyPasteDelete():
        ed = state["ed"]
        i = state["new"]
        n = len(ed.seq["cues"])
        ed.setSelection([i])
        ed.setPlayhead(33000)
        ed.copySelection()
        ed.paste(ed.snap(ed.playhead))
        pump(80)
        check(len(ed.seq["cues"]) == n + 1 and ed.seq["cues"][-1]["at_ms"] == 33000, "paste at the playhead")
        QTest.keyClick(ed, Qt.Key_Delete)
        pump(80)
        check(len(ed.seq["cues"]) == n, "Delete removes the selected cue")

    def renderAndPreview():
        ed = state["ed"]
        ed.rerender()
        ed.setPlayhead(13000)
        pump(50)
        tiles = ed.stage.tiles
        check(len(tiles) == 4 and all(t["rgb"] for t in tiles), "preview tiles at the playhead: " + str(tiles))
        check(any(t["layer"] == "show" for t in tiles), "the sequence drives the preview")
        check(all(t.get("side") in ("left", "centre", "right") and t.get("depth") for t in tiles), "preview tiles carry positions")
        ed.planCheck.setChecked(True)
        pump(50)
        check(ed.stage.planMode and len(ed.stage._layout()) == 4, "plan view in the editor preview")
        ed.planCheck.setChecked(False)

    def saveAndRename():
        ed = state["ed"]
        ed.seq["name"] = "Editor Test Copy"
        ed.nameEdit.setText("Editor Test Copy")
        check(ed.save(), "save under a new name: " + ed.statusLabel.text())
        check("Editor Test Copy" in nl.savedSequences and "Example - Four Light Demo" not in nl.savedSequences, "saving a renamed sequence renames it")
        on = json.load(open(nl._sequenceFilesNamed("Editor Test Copy")[0], encoding="utf-8"))
        check(any(c.get("clip", {}).get("name") == "Heartbeat" for c in on["cues"] if isinstance(c.get("clip"), dict)), "edits are in the file")
        check(not ed.dirty and win.seqList.count() == len(nl.savedSequences), "clean after save, list refreshed")

    def playPreviewOnly():
        ed = state["ed"]
        rig.rec.clear()
        ed.setPlayhead(0)
        ed.play()
        pump(500)
        ed.pause()
        check(ed.playhead >= 300, "playhead advances: %d" % ed.playhead)
        check(nl.showEngine.status()["sequence"] is None and not [w for w in rig.rec.snapshot() if w[2][1] in (134, 135)], "screen-only preview doesn't touch the lights")

    def playToLights():
        ed = state["ed"]
        ed.sendCheck.setChecked(True)
        ed.setPlayhead(4000)
        ed.play()
        pump(700)
        st = nl.showEngine.status()["sequence"]
        check(st is not None and st["state"] == "playing" and st["name"] == "Editor Test Copy", "Send to lights plays the edit: " + str(st))
        check(4300 <= st["position_ms"] <= 5500, "from the playhead: %s" % st["position_ms"])
        ed.pause()
        pump(200)
        check(nl.showEngine.status()["sequence"] is None, "pausing the editor stops the lights")
        ed.sendCheck.setChecked(False)

    def panelButtons():
        ed = state["ed"]
        ed.close()
        pump(50)
        for i in range(win.seqList.count()):
            if win.seqList.item(i).data(Qt.UserRole) == "Editor Test Copy":
                win.seqList.setCurrentRow(i)
        win.seqDuplicate()
        check("Editor Test Copy (copy)" in nl.savedSequences, "Duplicate")
        for i in range(win.seqList.count()):
            if win.seqList.item(i).data(Qt.UserRole) == "Editor Test Copy (copy)":
                win.seqList.setCurrentRow(i)
        win.seqDelete(confirm=False)
        check("Editor Test Copy (copy)" not in nl.savedSequences and not nl._sequenceFilesNamed("Editor Test Copy (copy)"), "Delete")
        ed2 = win.seqNew(template="")
        pump(200)
        check(ed2.originalName is None and ed2.seq["name"].startswith("New Sequence") and len(ed2.seq["cues"]) == 1, "+New opens a blank sequence")
        check(ed2.save(), "a new sequence saves: " + ed2.statusLabel.text())
        ed2.close()
        ed3 = win.seqNew(template="Starter - Countdown")
        pump(200)
        check(ed3.originalName is None and ed3.seq["name"] == "Countdown" and len(ed3.seq["cues"]) == 21, "+New from a starter copies it under a new name: " + ed3.seq["name"])
        ed3.dirty = False
        ed3.close()

    def unmatchedTrack():
        ed = win.seqOpenEditor("Editor Test Copy")
        pump(200)
        has = any(t["index"] is None for t in ed.tracks)
        check(has, "the example's @practical cues show on a 'No matching light' track on a rig without one")
        ed.grab().save(os.path.join(rig.workdir, "editor_after.png"))
        RESULTS.append(("INFO", "screenshot", os.path.join(rig.workdir, "editor_after.png")))
        ed.close()

    for name, fn in [("model helpers", modelHelpers), ("opens on a saved sequence", opens), ("double-click adds a cue", doubleClickAdds),
                     ("drag moves a cue", dragMoves), ("undo and redo", undoRedo), ("properties panel", propertiesEdit),
                     ("drag a clip's end", resizeEnd), ("copy, paste, delete", copyPasteDelete), ("stage preview", renderAndPreview),
                     ("save and rename", saveAndRename), ("screen-only preview", playPreviewOnly), ("send to lights", playToLights),
                     ("panel New/Duplicate/Delete", panelButtons), ("unmatched cues track", unmatchedTrack)]:
        step(name, fn)
    failed = 0
    for status, name, msg in RESULTS:
        print(status, name + ((" - " + msg) if msg else ""))
        failed += status == "FAIL"
    print("timeline editor tests: %d passed, %d failed" % (sum(1 for r in RESULTS if r[0] == "PASS"), failed))
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
