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
    # Plan view: lights in their cells, front row at the top, your left on the left
    stage.view.setFont(stage.font())
    stage.timer.stop()  # keep these test tiles on screen instead of the live ones
    planTiles = [dict(t, side=sd, depth=dp, height=h) for t, (sd, dp, h) in zip(stage.view.tiles,
                 [("right", "front", "middle"), ("left", "front", "low"), ("right", "back", "high"), ("left", "back", "middle")])]
    stage.view.setTiles(planTiles)
    stage.planCheck.setChecked(True)
    app.processEvents()
    pos = {stage.view.tiles[n]["side"] + "/" + stage.view.tiles[n]["depth"]: (x, y) for n, x, y in stage.view._layout()}
    assert pos["left/front"][0] < pos["right/front"][0] and pos["left/front"][1] < pos["left/back"][1], pos
    shotPlan = os.path.join(rig.workdir, "stage_plan.png")
    stage.grab().save(shotPlan)
    print("stage plan screenshot:", shotPlan)
    stage.planCheck.setChecked(False)
    stage.timer.start(50)
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
    picker = win.lightPositionPicker
    others = {k: b.text() for k, b in picker.cells.items()}
    assert "NEEWER" in others[("left", "beside")], "other lights should show in the picker: %r" % others
    picker.cells[("left", "back")].click()
    picker.heightButtons["high"].click()
    assert picker.value() == ("left", "back", "high") and picker.cells[("left", "back")].text().startswith("This light")
    win.lightMaxBriSpin.setValue(45)
    win.lightLockedCheck.setChecked(True)
    win.checkLightPrefs()
    mac = rig.mac(0)
    sidecar = os.path.join(rig.workdir, "light_prefs", mac.replace(":", ""))
    assert os.path.exists(sidecar), "sidecar not written"
    fields = open(sidecar, encoding="utf-8").read().split("|")
    assert fields[5:14] == ["practical", "left", "4", "", "45", "-1", "True", "back", "high"], fields
    nl.lightShowPrefs.clear()
    nl.loadLightAliases()
    assert nl.lightShowPrefs[mac]["maxBri"] == 45 and nl.lightShowPrefs[mac]["locked"] is True
    assert nl.returnLightIndexesFromMacAddress("@practical") == [0]
    assert nl.returnLightIndexesFromMacAddress("@back.left.high") == [0]
    win.lightTable.selectRow(0)
    app.processEvents()
    win.setupLightPrefsTab(0)
    assert win.lightPositionPicker.value() == ("left", "back", "high"), "position reloads into the picker"
    picker.cells[("centre", "beside")].click()
    picker.heightButtons["middle"].click()
    win.checkLightPrefs()
    fields = open(sidecar, encoding="utf-8").read().split("|")
    assert len(fields) == 12 and fields[6] == "centre", "no position fields when the position is the default: %r" % fields

    # Apply Settings only shows on the slider tabs, and only with live preview off
    tabs = win.ColorModeTabWidget
    win.show()
    win.livePreview_check.setChecked(False)
    for i, want in ((0, True), (1, True), (2, True), (win.TAB_GLOBALPREFS, False), (win.TAB_LIGHTPREFS, False), (win.TAB_ANIM, False)):
        tabs.setCurrentIndex(i)
        app.processEvents()
        assert win.applyButton.isVisible() == want, "Apply Settings on tab %s should be %s" % (tabs.tabText(i), "shown" if want else "hidden")
    win.livePreview_check.setChecked(True)
    tabs.setCurrentIndex(0)
    app.processEvents()
    assert not win.applyButton.isVisible(), "hidden with live preview on"

    # Save Global Preferences highlights while there are unsaved changes
    win.setupGlobalLightPrefsTab()
    assert not win.globalPrefsDirty and "unsaved" not in win.saveGlobalPrefsButton.text()
    nl.globalPrefsFile = os.path.join(rig.workdir, "light_prefs", "NeewerLux.prefs")
    win.envMaxBriSpin.setValue(81)
    assert win.globalPrefsDirty and "unsaved" in win.saveGlobalPrefsButton.text(), "a change must highlight Save"
    win.saveGlobalPrefs()
    assert not win.globalPrefsDirty, "saving clears the highlight"
    win.setupGlobalLightPrefsTab(True)
    assert win.globalPrefsDirty, "Reset to defaults is unsaved until saved"
    win.setupGlobalLightPrefsTab()
    assert not win.globalPrefsDirty

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

    # Flash guard: on by default; unticking asks, and saying No keeps it on
    win.setupGlobalLightPrefsTab()
    assert win.flashGuardCheck.isChecked() and nl.flashGuardEnabled
    real = nl.QMessageBox.warning
    try:
        nl.QMessageBox.warning = staticmethod(lambda *a, **k: nl.QMessageBox.No)
        win.flashGuardCheck.setChecked(False)
        assert win.flashGuardCheck.isChecked(), "saying No must keep the guard on"
        nl.QMessageBox.warning = staticmethod(lambda *a, **k: nl.QMessageBox.Yes)
        win.flashGuardCheck.setChecked(False)
        assert not win.flashGuardCheck.isChecked()
        win.saveGlobalPrefs()
        assert not nl.flashGuardEnabled and "flashGuard=0" in open(nl.globalPrefsFile, encoding="utf-8").read()
        win.flashGuardCheck.setChecked(True)
        win.saveGlobalPrefs()
        assert nl.flashGuardEnabled and "flashGuard" not in open(nl.globalPrefsFile, encoding="utf-8").read()
    finally:
        nl.QMessageBox.warning = real

    # Sequences have their own tab, after Animations; clearing the selection keeps you there
    tabs = win.ColorModeTabWidget
    assert tabs.tabText(win.TAB_SEQ) == "Sequences" and win.TAB_SEQ == win.TAB_ANIM + 1
    assert win.seqList.parent() is not None and win.seqTab.isAncestorOf(win.seqList)
    assert not win.animTab.isAncestorOf(win.seqList)
    tabs.setCurrentIndex(win.TAB_SEQ)
    win.lightTable.clearSelection()
    app.processEvents()
    assert tabs.currentIndex() == win.TAB_SEQ, "clearing the light selection must not leave the Sequences tab"
    tabs.setCurrentIndex(win.TAB_GLOBALPREFS)
    win.lightTable.clearSelection()
    app.processEvents()
    assert tabs.currentIndex() == win.TAB_GLOBALPREFS, "nor Global Preferences"
    win.seqRefreshList()
    for i in range(win.seqList.count()):
        if win.seqList.item(i).data(nl.Qt.UserRole) == "Starter - Countdown":
            win.seqList.setCurrentRow(i)
    app.processEvents()
    assert "Starter - Countdown" in win.seqInfoLabel.text() and "21 cues" in win.seqInfoLabel.text(), win.seqInfoLabel.text()
    win.resize(1200, 760)
    tabs.setCurrentIndex(win.TAB_SEQ)
    app.processEvents()
    shot = os.path.join(rig.workdir, "sequences_tab.png")
    win.grab().save(shot)
    print("sequences tab screenshot:", shot)
    win.lightTable.selectRow(0)
    app.processEvents()
    tabs.setCurrentIndex(win.TAB_LIGHTPREFS)
    win.setupLightPrefsTab(0)
    app.processEvents()
    win.lightPrefs.ensureWidgetVisible(win.lightPositionPicker)
    app.processEvents()
    shot = os.path.join(rig.workdir, "light_prefs_tab.png")
    win.grab().save(shot)
    print("light preferences screenshot:", shot)
    print("GUI smoke test: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
