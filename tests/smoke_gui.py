"""Offscreen GUI smoke test: builds the real main window against the fake rig and
exercises the new widgets. Run: QT_QPA_PLATFORM=offscreen python tests/smoke_gui.py"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness  # noqa: E402


def main():
    rig = harness.boot(os.path.dirname(HERE))
    nl = rig.nl
    nl.NLPythonServer.log_message = lambda *a: None
    app = nl.QApplication.instance() or nl.QApplication([])
    win = nl.MainWindow()
    nl.mainWindow = win
    win.setupGlobalLightPrefsTab()
    win.updateLights()
    app.processEvents()

    # Sequences panel and status timer
    nl.savedSequences["Smoke"] = {"format": 1, "name": "Smoke", "duration_ms": 1500,
                                  "cues": [{"at_ms": 0, "state": {"mode": "HSI", "hue": 10, "sat": 100, "bri": 50}}]}
    win.seqRefreshList()
    assert win.seqList.count() == len(nl.savedSequences)
    for i in range(win.seqList.count()):
        if win.seqList.item(i).data(nl.Qt.UserRole) == "Smoke":
            win.seqList.setCurrentRow(i)
    win.seqPlay()
    time.sleep(0.3)
    win._updateShowStatus()
    assert "Smoke" in win.seqStatusLabel.text(), win.seqStatusLabel.text()
    win.seqPauseResume()
    win._updateShowStatus()
    assert "paused" in win.seqStatusLabel.text() and win.seqPauseButton.text() == "Resume"
    win.seqPauseResume()
    nl.startAnimation("Strobe", None, 1.0, True, fps=10, maxLoops=0)
    time.sleep(0.2)
    win._updateShowStatus()
    assert win.animStatusLabel.text().startswith("Playing: Strobe"), win.animStatusLabel.text()
    nl.stopAnimation()
    win._updateShowStatus()
    assert win.animStatusLabel.text() == "Stopped"
    nl.sequenceControl("stop")
    win._updateShowStatus()
    assert win.seqStatusLabel.text() == "No sequence playing"

    # Stage window, table swatches and the render dialog
    nl.startSequence({"format": 1, "name": "StageCheck", "duration_ms": 3000,
                      "cues": [{"at_ms": 0, "target": "@left", "state": {"mode": "HSI", "hue": 280, "sat": 90, "bri": 70}},
                               {"at_ms": 0, "target": "@rim", "state": {"mode": "HSI", "hue": 20, "sat": 100, "bri": 90}}]})
    time.sleep(0.4)
    win.openStage()
    app.processEvents()
    stage = win._stageWindow
    stage.refresh()
    assert len(stage.view.tiles) == 4 and stage.view.tiles[0]["layer"] == "show", stage.view.tiles
    stage.resize(600, 220)
    app.processEvents()
    shot = os.path.join(rig.workdir, "stage.png")
    stage.grab().save(shot)
    print("stage screenshot:", shot)
    # Large font (like 150% Windows scaling) with long simulated names: tiles must grow, not clip
    from PySide6.QtGui import QFont, QFontMetrics
    big = QFont(stage.font())
    big.setPointSizeF(max(14.0, big.pointSizeF() * 1.6))
    stage.view.setFont(big)
    longTiles = [dict(t, name=n, simulated=True) for t, n in zip(stage.view.tiles, ["SIM-RGB660-Fill", "SIM-RGB660-Ambient", "NEEWER-RGB660 PRO", "A very long custom light name"])]
    stage.view.setTiles(longTiles)
    stage.resize(200, 100)  # smaller than it can be: the minimum size must win
    app.processEvents()
    tileW, swatchH, gap, line, sline = stage.view._geometry()
    assert stage.view.height() >= swatchH + line + 2 * sline, "Stage view is shorter than one tile"
    fm = QFontMetrics(stage.view._smallFont())
    assert tileW >= fm.horizontalAdvance("Ambient  HSI 100%"), "detail line doesn't fit the tile"
    stage.resize(stage.view.sizeHint().width() + 20, stage.view.sizeHint().height() + 60)
    app.processEvents()
    shotBig = os.path.join(rig.workdir, "stage_bigfont.png")
    stage.grab().save(shotBig)
    print("stage screenshot (large font):", shotBig)
    win._updateShowStatus()
    swatch = win.lightTable.item(0, 0).data(nl.Qt.DecorationRole)
    assert swatch is not None, "no swatch on the first light row"
    stage.hide()
    assert not stage.timer.isActive(), "Stage polling must stop while hidden"
    nl.sequenceControl("stop")
    from neewerlux_stage import RenderDialog
    result = nl.renderSequence("Example - Four Light Demo")
    dlg = RenderDialog(nl.renderSequencePNG(result), result["sequence"], win)
    dlg.show()
    app.processEvents()
    dlg.close()

    # Light Prefs round trip through the sidecar file
    win.lightTable.selectRow(0)
    app.processEvents()
    win.setupLightPrefsTab(0)
    assert win.lightRoleCombo.currentText() == "Key"
    win.lightRoleCombo.setCurrentIndex(nl.LIGHT_ROLES.index("practical"))
    win.lightSideCombo.setCurrentIndex(nl.LIGHT_SIDES.index("centre"))
    win.lightMaxBriSpin.setValue(45)
    win.lightLockedCheck.setChecked(True)
    win.checkLightPrefs()
    mac = rig.mac(0)
    sidecar = os.path.join(rig.workdir, "light_prefs", mac.replace(":", ""))
    assert os.path.exists(sidecar), "sidecar not written"
    fields = open(sidecar, encoding="utf-8").read().split("|")
    assert fields[5:12] == ["practical", "centre", "4", "", "45", "-1", "True"], fields
    nl.lightShowPrefs.clear()
    nl.loadLightAliases()
    assert nl.lightShowPrefs[mac]["maxBri"] == 45 and nl.lightShowPrefs[mac]["locked"] is True
    assert nl.returnLightIndexesFromMacAddress("@practical") == [0]

    # Global prefs save and reload
    win.envMaxBriSpin.setValue(80)
    win.seqFrameRateSpin.setValue(15)
    win.simulatedLightsCombo.setCurrentIndex(3)
    win.simulatedCCTOnlyCheck.setChecked(True)
    nl.globalPrefsFile = os.path.join(rig.workdir, "light_prefs", "NeewerLux.prefs")
    win.saveGlobalPrefs()
    text = open(nl.globalPrefsFile, encoding="utf-8").read()
    assert "envMaxBri=80" in text and "seqFrameRate=15" in text and "simulatedLights=3" in text and "simulatedCCTOnly=1" in text, text
    nl.envMaxBri, nl.seqFrameRate, nl.simulatedLights, nl.simulatedCCTOnly = 100, 20, 0, False
    nl.loadPrefsFile(nl.globalPrefsFile)
    assert nl.envMaxBri == 80 and nl.seqFrameRate == 15 and nl.simulatedLights == 3 and nl.simulatedCCTOnly is True
    win.setupGlobalLightPrefsTab(True)
    assert win.envMaxBriSpin.value() == 100 and win.effectMaxSecondsSpin.value() == 30 and win.simulatedLightsCombo.currentIndex() == 0

    # Settings changed from the web dashboard show up in the window, and the window's next
    # Save keeps them (the file isn't overwritten with stale widget values)
    r = nl.setWebGlobalSettings({"envMaxBri": 70, "effectMaxSeconds": 45})
    assert r["success"], r
    app.processEvents()
    assert win.envMaxBriSpin.value() == 70 and win.effectMaxSecondsSpin.value() == 45, (win.envMaxBriSpin.value(), win.effectMaxSecondsSpin.value())
    win.saveGlobalPrefs()
    text = open(nl.globalPrefsFile, encoding="utf-8").read()
    assert "envMaxBri=70" in text and "effectMaxSeconds=45" in text, text
    win.lightTable.selectRow(1)
    app.processEvents()
    win.setupLightPrefsTab(1)
    r = nl.setWebLightSettings(1, {"role": "rim", "maxBri": 33})
    assert r["success"], r
    app.processEvents()
    assert win.lightRoleCombo.currentText() == "Rim" and win.lightMaxBriSpin.value() == 33, (win.lightRoleCombo.currentText(), win.lightMaxBriSpin.value())
    print("GUI smoke test: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
