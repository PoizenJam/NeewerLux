"""Offscreen GUI smoke test: builds the real main window against the fake rig and
exercises the new widgets. Run: QT_QPA_PLATFORM=offscreen python tests/smoke_gui.py"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness  # noqa: E402


def pumpUntil(app, cond, timeout, what):
    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end, "timed out waiting for " + what
        app.processEvents()
        time.sleep(0.01)


def checkWorkerUsesGuiThread(nl, app, win):
    """The worker reaches the window only through signals: a discovery's table refresh runs on the
    GUI thread and the worker waits for it (updateLights reorders the lights it then connects by
    index), and the selection it sends to is the GUI's copy."""
    import threading
    nl.threadAction = "quit"
    pumpUntil(app, lambda: nl.threadAction == "finished", 10, "the harness worker to stop")
    nl.threadAction = ""
    calls = []
    realUpdate = win.updateLights

    def recordUpdate(*a, **k):
        calls.append(threading.current_thread() is threading.main_thread())
        time.sleep(0.2)
        realUpdate(*a, **k)
        calls.append(nl.threadAction)  # still the scan's result: the worker hasn't moved on
    win.updateLights = recordUpdate

    async def noScan():
        return "scanned"
    realFind, nl.findDevices = nl.findDevices, noScan
    nl.autoConnectToLights = False
    threading.Thread(target=nl.workerThread, args=(nl.asyncioEventLoop,), name="workerThread", daemon=True).start()
    nl.threadAction = "discover"
    pumpUntil(app, lambda: len(calls) == 2 and nl.threadAction == "", 10, "the discovery to finish")
    assert calls == [True, "scanned"], "updateLights ran on the GUI thread and the worker waited for it: %r" % calls
    win.updateLights = realUpdate
    nl.findDevices = realFind

    win.lightTable.selectRow(2)
    app.processEvents()
    assert win.selectionSnapshot() == [2], win.selectionSnapshot()
    win.lightTable.clearSelection()
    app.processEvents()
    assert win.selectionSnapshot() == []
    print("worker to GUI on signals: PASS")


def checkWriteErrorKeepsWorker(nl, app, win):
    """A send that fails outside the per-light write (here a selection naming a light that has
    gone) leaves the worker idle and alive. It used to set threadAction to False (the CLI's
    error result), and the worker's next loop died on False.startswith."""
    worker = [t for t in __import__("threading").enumerate() if t.name == "workerThread"]
    realSnapshot = win.selectionSnapshot
    win.selectionSnapshot = lambda: [99]
    try:
        nl.threadAction = "send"
        pumpUntil(app, lambda: nl.threadAction != "send", 10, "the send to finish")
        time.sleep(0.3)
        assert nl.threadAction == "" and all(t.is_alive() for t in worker), \
            "after a failed send the worker is idle and alive: %r, alive %s" % (nl.threadAction, [t.is_alive() for t in worker])
    finally:
        win.selectionSnapshot = realSnapshot
    print("failed send keeps the worker: PASS")


SMALL_SCREEN = (1280, 720)  # every window must fit a screen this size


def tooBig(widget):
    """Whether a window can't be made small enough for SMALL_SCREEN."""
    widget.ensurePolished()
    hint, least = widget.minimumSizeHint(), widget.minimumSize()
    w, h = max(hint.width(), least.width()), max(hint.height(), least.height())
    return (w, h) if w > SMALL_SCREEN[0] or h > SMALL_SCREEN[1] else None


def widthBreakdown(win):
    """The main window's parts and their minimum widths, to show what holds it wide."""
    parts = [(w.objectName() or type(w).__name__, w.minimumSizeHint().width()) for w in win.centralWidget().children()
             if hasattr(w, "minimumSizeHint") and w.isVisible()]
    tabs = win.ColorModeTabWidget
    parts += [("tab " + tabs.tabText(i), tabs.widget(i).minimumSizeHint().width()) for i in range(tabs.count())]
    tb = win.findChild(type(win.centralWidget()), "toolbarWidget")
    if tb is not None:
        parts += [("button " + w.text(), w.minimumSizeHint().width()) for w in tb.findChildren(type(win.turnOffButton))]
    return ", ".join("%s %d" % p for p in parts)


def fixedTables(widget):
    """Tables in widget whose columns the user can't drag (none Interactive), or with a stretching
    column, which makes each divider move the one to its left."""
    from PySide6.QtWidgets import QTableWidget, QHeaderView
    bad = []
    for t in widget.findChildren(QTableWidget):
        hdr = t.horizontalHeader()
        if (not any(hdr.sectionResizeMode(c) == QHeaderView.Interactive for c in range(t.columnCount())) or
                any(hdr.sectionResizeMode(c) == QHeaderView.Stretch for c in range(t.columnCount()))):
            bad.append(t.objectName() or "%d-column table" % t.columnCount())
    return bad


def checkFlashRates(nl, app, win):
    """The Animations list shows each animation's flash rate at the chosen speed, over the limit in red."""
    nl.savedAnimations["Test Strobe"] = {"name": "Test Strobe", "loop": True, "keyframes": [
        {"hold_ms": 80, "fade_ms": 0, "lights": {"*": {"mode": "CCT", "temp": 56, "bri": 100}}},
        {"hold_ms": 80, "fade_ms": 0, "lights": {"*": {"mode": "CCT", "temp": 56, "bri": 0}}}]}
    try:
        win.animSpeedCombo.setCurrentText("1x")
        win.animRefreshList()
        items = {win.animList.item(r).data(nl.Qt.UserRole): win.animList.item(r) for r in range(win.animList.count())}
        strobe, calm = items["Test Strobe"], items[sorted(n for n in items if n and n != "Test Strobe")[0]]
        assert "over the limit" in strobe.text() and strobe.foreground().color().red() > 200, strobe.text()
        assert "flashes/s" in calm.text() or "no flashes" in calm.text(), calm.text()
        win.animSpeedCombo.setCurrentText("0.25x")
        app.processEvents()
        assert "over the limit" not in items["Test Strobe"].text(), "the rate follows the speed: " + items["Test Strobe"].text()
        win.animSpeedCombo.setCurrentText("1x")
    finally:
        del nl.savedAnimations["Test Strobe"]
        win.animRefreshList()
    print("Animation flash rates: PASS")


def checkSoundTab(nl, app, win, rig):
    """1.4.0: the Sound tab starts, tunes, edits, saves and stops a sound mode, live."""
    if nl.audio.np is None:
        assert win.soundControls.isHidden() and win.soundUnavailableLabel.text(), "without numpy the tab is a note"
        print("Sound tab: SKIP (numpy not installed)")
        return
    np = nl.audio.np
    t = np.arange(int(0.15 * 48000)) / 48000
    kick = 0.9 * np.sin(2 * np.pi * (50 + 80 * np.exp(-t * 30)) * t) * np.exp(-t * 12)
    signal = np.zeros(int(48000 * 16 * 60 / 124.0))
    for b in range(16):
        i = int(b * 48000 * 60 / 124.0)
        signal[i:i + len(kick)] += kick[:len(signal) - i]
    nl.audioEngine.sourceFactory = lambda device: nl.audio.ArraySource(signal, name="smoke signal")
    win.soundShowAvailability()
    assert not win.soundControls.isHidden(), "the tab's controls show when sound modes can run"
    tabs = win.ColorModeTabWidget
    assert win.TAB_SOUND == tabs.indexOf(win.ANM) + 1 and win.TAB_ANIM == win.TAB_SOUND + 1, "Sound sits after Scene"
    win.ColorModeTabWidget.setCurrentIndex(win.TAB_SOUND)
    win.show()
    win.soundRefreshModes("Pulse")
    assert win.soundModeCombo.count() == len(nl.savedSoundModes) and win.soundModeCombo.currentText() == "Pulse"
    assert win.soundPartsTable.rowCount() == 1 and win.soundPaletteBox.count() == 1
    win.soundStart()
    pumpUntil(app, lambda: nl.showEngine.soundPlayer() is not None, 3, "Pulse to start")
    player = nl.showEngine.soundPlayer()
    win.soundSliders["sensitivity"][0].setValue(250)
    win.soundSliders["range_db"][0].setValue(10)
    win.soundSliders["floor"][0].setValue(90)  # past the ceiling: carries it along
    assert player.mode.sensitivity == 2.5 and player.mode.rangeDb == 10, "sliders apply live"
    assert player.mode.floor == 90 and player.mode.ceiling == 90, (player.mode.floor, player.mode.ceiling)
    win.soundSliders["floor"][0].setValue(20)
    win.soundSliders["curve"][0].setValue(15)
    assert player.mode.curve == 1.5 and win.soundSliders["curve"][1].text() == "x1.5", "the curve slider applies live"
    hueSpin = win.soundPaletteBox.itemAt(0).widget().findChildren(nl.SpinBoxWithButtons)[0]
    hueSpin.setValue(120)
    assert player.mode.palette[0]["hue"] == 120, "palette edits apply live"
    combo = win.soundPalettePresetCombo
    assert combo.findData("Neon") > 0, "the saved palettes are listed"
    win.soundPalettePresetChosen(combo.findData("Neon"))
    assert player.mode.palette == nl.savedPalettes["Neon"] and win.soundPaletteBox.count() == 3, "loading a saved palette applies live"
    colourCombo = win.soundPartsTable.cellWidget(0, 2)
    colourCombo.setCurrentIndex(colourCombo.findData("cycle"))
    colourCombo.activated.emit(colourCombo.currentIndex())
    win.soundCycleSpin.setValue(9)
    assert player.mode.parts[0]["colour"] == "cycle" and player.mode.cycleS == 9, "Cycles and its time apply live"
    win.soundCycleSpin.setValue(2)
    assert win.soundCycleSpin.value() == 4, "the cycle can't go under 4 s"
    win.soundAddPartRow({"target": "@fill", "drive": "high", "colour": 0}, True)
    assert 1 in player.lights(), "an added part drives its lights: %r" % player.lights()
    win.soundPaletteKind.setCurrentIndex(1)
    win.soundPaletteKindChosen(1)
    assert player.mode.palette == [{"temp": 2900}, {"temp": 4300}], "switching to whites applies live"
    pumpUntil(app, lambda: (nl.soundStatus()["levels"] or {}).get("level", 0) > 0, 3, "levels")
    # the "Loaded palette" note gives way to the status after 4 s
    pumpUntil(app, lambda: win.soundRefreshStatus() or "Playing Pulse" in win.soundStatusLabel.text(), 6, "the status after the note")
    assert "smoke signal" in win.soundStatusLabel.text(), win.soundStatusLabel.text()
    assert any(bar.value() > 0 for bar in win.soundMeters.values()), "the meters move"
    assert win.soundDeviceCombo.count() >= 1 and win.prefsSoundDeviceCombo.count() == win.soundDeviceCombo.count()
    win.resize(1100, 760)
    app.processEvents()
    lightsCol = win.soundPartsTable.columnWidth(0)
    assert lightsCol >= 180, "the Lights column has room for a target: %d px" % lightsCol
    colour = win.soundPartsTable.cellWidget(0, 2)
    fm = colour.fontMetrics()
    widest = max(fm.horizontalAdvance(colour.itemText(i)) for i in range(colour.count()))
    assert win.soundPartsTable.columnWidth(2) >= widest + 20, "the Colour column fits 'Steps on the beat': %d < %d" % (win.soundPartsTable.columnWidth(2), widest + 20)
    assert colour.view().minimumWidth() >= widest, "its list opens wide enough to read"
    assert not fixedTables(win), "every table's columns can be dragged: %s" % fixedTables(win)
    target = win.soundPartsTable.cellWidget(0, 0)
    long = "@rim;@background;@practical;@back.left;@high"
    target.setEditText(long)
    target.lineEdit().editingFinished.emit()
    app.processEvents()
    need = target.fontMetrics().horizontalAdvance(long) + 30
    assert win.soundPartsTable.columnWidth(0) >= need, "the Lights column widens to a long target: %d < %d" % (win.soundPartsTable.columnWidth(0), need)
    assert target.width() >= need, "and the drop-down with it: %d" % target.width()
    hdr = win.soundPartsTable.horizontalHeader()
    before = [hdr.sectionPosition(c) for c in range(4)]
    win.soundPartsTable.setColumnWidth(1, win.soundPartsTable.columnWidth(1) + 40)
    after = [hdr.sectionPosition(c) for c in range(4)]
    assert after[:2] == before[:2] and after[2] == before[2] + 40, "widening Brightness moves the columns to its right, not its left: %s %s" % (before, after)
    shot = os.path.join(rig.workdir, "sound_tab.png")
    win.grab().save(shot)
    win.soundPartsTable.grab().save(os.path.join(rig.workdir, "sound_parts.png"))
    print("sound tab screenshot:", shot)
    realGet, realQ = nl.QInputDialog.getText, nl.QMessageBox.question
    nl.QInputDialog.getText = staticmethod(lambda *a, **k: ("Smoke Sound", True))
    nl.QMessageBox.question = staticmethod(lambda *a, **k: nl.QMessageBox.Yes)
    try:
        win.soundPaletteSave()
        assert nl.savedPalettes.get("Smoke Sound") == [{"temp": 2900}, {"temp": 4300}], "save a palette"
        assert win.soundPalettePresetCombo.currentData() == "Smoke Sound"
        win.soundPaletteDelete()
        assert "Smoke Sound" not in nl.savedPalettes, "delete a palette"
        win.soundSaveAs()
        assert "Smoke Sound" in nl.savedSoundModes and win.soundModeCombo.currentText() == "Smoke Sound", "save as"
        saved = nl.savedSoundModes["Smoke Sound"]
        assert saved["palette"] == [{"temp": 2900}, {"temp": 4300}] and len(saved["parts"]) == 2 and saved["range_db"] == 10
        assert nl.savedSoundModes["Pulse"].get("sensitivity") == 1.0, "the original is untouched"
        win.soundDelete()
        assert "Smoke Sound" not in nl.savedSoundModes, "delete"
    finally:
        nl.QInputDialog.getText, nl.QMessageBox.question = realGet, realQ
    win.soundRefreshModes("Colour Drift")
    tabs.setCurrentIndex(win.TAB_SOUND)
    win.lightTable.clearSelection()
    win.selectRows([0])
    win.selectionChanged()
    assert tabs.currentIndex() == win.TAB_SOUND, "picking a light on the Sound tab stays there"
    win.soundStartSelectedButton.click()
    pumpUntil(app, lambda: nl.soundStatus()["assignments"][-1:] == [{"mode": "Colour Drift", "lights": [1]}], 3,
              "the selected light on Colour Drift: %s, %s" % (win.soundStatusLabel.text(), nl.soundStatus()["assignments"]))
    win.soundRefreshStatus()
    assert "Colour Drift on 1" in win.soundStatusLabel.text(), win.soundStatusLabel.text()
    nl.stopSound()
    win.soundRefreshStatus()
    assert nl.showEngine.soundPlayer() is None and not win.soundStopButton.isEnabled()
    win.ColorModeTabWidget.setCurrentIndex(0)
    print("Sound tab: PASS")


def checkOwnSwatches(nl, app, win):
    """1.4.0: + saves the colour being edited as a swatch, every swatch grid redraws, a click
    on yours picks it, removing one redraws them all; the animation editor has the wheel and
    swatches for an HSI frame."""
    import json
    from neewerlux_ui import SWATCH_STORE, ColourPickDialog
    from neewerlux_anim_editor import AnimationEditorDialog
    SWATCH_STORE.replace([])
    # measured on the HSI tab, where the swatches' layout counts towards the window's minimum
    tabs = win.ColorModeTabWidget
    lastTab = tabs.currentIndex()
    tabs.setCurrentWidget(win.HSI)
    app.processEvents()
    emptySize = win.minimumSizeHint()
    dlg = ColourPickDialog(30, 80, win)
    for slider, v in ((win.Slider_HSI_1_H, 200), (win.Slider_HSI_2_S, 40)):
        slider.blockSignals(True)  # no send to the lights: only the + button is under test
        slider.setValue(v)
        slider.blockSignals(False)
    win.hsiSwatches.addButton.click()
    assert SWATCH_STORE.items == [{"hue": 200, "sat": 40}], SWATCH_STORE.items
    assert len(win.hsiSwatches.userButtons) == 1 and len(dlg.swatches.userButtons) == 1, "every swatch grid shows it"
    with open(nl.swatchesFile, encoding="utf-8") as f:
        assert json.load(f) == [{"hue": 200, "sat": 40}], "saved to swatches.json"
    dlg.swatches.userButtons[0].click()
    assert dlg.value() == (200, 40), dlg.value()
    dlg.swatches.addButton.click()
    assert len(SWATCH_STORE.items) == 1, "the same colour isn't saved twice"
    ed = AnimationEditorDialog(win, {"name": "Spin", "loop": True, "keyframes": [
        {"hold_ms": 100, "fade_ms": 0, "lights": {"*": {"mode": "HSI", "hue": 0, "sat": 100, "bri": 50}}}]}, "Spin")
    ed._table.selectRow(0)
    assert not ed._pickRow.isHidden(), "the animation editor shows the wheel and swatches for HSI"
    assert len(ed._pickRow.swatches.userButtons) == 1, "with your swatches"
    ed._pickRow.swatches.userButtons[0].click()
    assert (ed._p1Spin.value(), ed._p2Spin.value()) == (200, 40), (ed._p1Spin.value(), ed._p2Spin.value())
    SWATCH_STORE.remove(0)
    assert not win.hsiSwatches.userButtons and not dlg.swatches.userButtons and not ed._pickRow.swatches.userButtons, "removed everywhere"
    for i in range(30):
        SWATCH_STORE.add(i * 7, 60)
    assert len(SWATCH_STORE.items) == SWATCH_STORE.LIMIT, "at most %d" % SWATCH_STORE.LIMIT
    rows = ed._pickRow.swatches
    assert rows.buttons[0].height() == 22 and ed._pickRow.scroll.height() >= 2 * 22 + rows.grid.verticalSpacing(), "two full rows show"
    assert ed._pickRow.scroll.height() == ed._pickRow.scroll.maximumHeight() and ed._pickRow.sizeHint().height() <= 50, \
        "a full set of swatches scrolls in the editor rather than growing it"
    app.processEvents()
    assert win.minimumSizeHint() == emptySize, "a full set of swatches doesn't change the main window's minimum: %s, was %s" % (
        win.minimumSizeHint(), emptySize)
    if tooBig(win):
        # not a swatch failure (the size is the same as with none): the main window's own check comes later
        print("note: the main window's minimum here is %s (%s)" % (tooBig(win), widthBreakdown(win)))
    tabs.setCurrentIndex(lastTab)
    b = win.hsiSwatches.buttons[0]
    assert (b.height(), win.hsiSwatches.addButton.height()) == (22, 22), \
        "the theme doesn't stretch the swatches or hide the +: %s" % ((b.height(), win.hsiSwatches.addButton.height()),)
    assert win.hsiSwatches.addButton.text() == "+"
    ed.close()
    dlg.close()
    SWATCH_STORE.replace([])
    nl._saveSwatches([])


def checkColourAndPresetFade(nl, app, win):
    """1.4.0: the HSI tab's wheel and swatches set the sliders (and follow them); a global
    preset recalled from its button with a fade goes through the compositor's fade and doesn't
    send the sliders."""
    win.Slider_HSI_1_H.setValue(10)
    win.hsiSwatches.buttons[4].click()  # green
    assert (win.Slider_HSI_1_H.value(), win.Slider_HSI_2_S.value()) == (120, 100), "a swatch sets the sliders"
    win.hsiWheel.picked.emit(200, 40)
    assert (win.Slider_HSI_1_H.value(), win.Slider_HSI_2_S.value()) == (200, 40), "the wheel sets the sliders"
    win.Slider_HSI_1_H.setValue(300)
    assert win.hsiWheel.hue == 300 and win.hsiWheel.sat == 40, "the sliders move the wheel's marker"
    from neewerlux_ui import ColourPickDialog
    dlg = ColourPickDialog(30, 80, win)
    dlg.swatches.buttons[7].click()  # blue
    assert dlg.value() == (225, 100), dlg.value()
    dlg.close()
    nl.customLightPresets[5] = [[-1, [4, 60, 270, 90]]]
    nl.presetFades[5] = 400
    fades, sends = [], []
    realFade = nl.showEngine.fadeBase
    nl.showEngine.fadeBase = lambda lights, ms, **kw: fades.append((sorted(lights), ms)) or set(lights)
    win._holdSliderSend = False
    nl.livePreview = True
    realSend = win.startSend
    try:
        win.lightTable.selectAll()
        app.processEvents()
        nl.threadAction = ""
        nl.recallCustomPreset(5)
        app.processEvents()
        assert fades == [(list(range(len(nl.availableLights))), 400)], "the global preset fades in: %s" % fades
        assert nl.threadAction in ("", "HTTP"), "the sliders weren't sent: %r" % nl.threadAction
        assert win.Slider_HSI_1_H.value() == 270 and win.Slider_HSI_3_L.value() == 60, "the sliders show the preset"
    finally:
        nl.showEngine.fadeBase = realFade
        nl.presetFades.pop(5, None)
        nl.customLightPresets[5] = nl.getDefaultPreset(5)
    print("colour wheel and preset fades: PASS")


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
    checkWorkerUsesGuiThread(nl, app, win)
    checkWriteErrorKeepsWorker(nl, app, win)
    checkSoundTab(nl, app, win, rig)
    checkFlashRates(nl, app, win)
    checkColourAndPresetFade(nl, app, win)
    checkOwnSwatches(nl, app, win)

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
    longTiles = [dict(t, name=n, simulated=True) for t, n in zip(stage.view.tiles, ["SIM-RGB660-Fill", "SIM-RGB660-Background", "NEEWER-RGB660 PRO", "A very long custom light name"])]
    stage.view.setTiles(longTiles)
    stage.resize(200, 100)  # smaller than it can be: the minimum size must win
    app.processEvents()
    tileW, swatchH, gap, line, sline = stage.view._geometry()
    scale = stage.view._scale()  # the grid views shrink to fit, to half size at most
    assert stage.view.height() >= (swatchH + line + 2 * sline) * scale, "Stage view is shorter than one tile"
    fm = QFontMetrics(stage.view._smallFont())
    assert tileW >= fm.horizontalAdvance("Background  HSI 100%"), "detail line doesn't fit the tile"
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
    assert stage.view.viewMode == "plan", "plan is the default view"
    app.processEvents()
    pos = {stage.view.tiles[n]["side"] + "/" + stage.view.tiles[n]["depth"]: (x, y) for n, x, y in stage.view._layout()}
    assert pos["left/front"][0] < pos["right/front"][0] and pos["left/front"][1] < pos["left/back"][1], pos
    shotPlan = os.path.join(rig.workdir, "stage_plan.png")
    stage.grab().save(shotPlan)
    print("stage plan screenshot:", shotPlan)
    stage.viewCombo.setCurrentIndex(1)  # height view: high row above low
    app.processEvents()
    hy = {stage.view.tiles[n]["height"]: y for n, x, y in stage.view._layout()}
    assert hy["high"] < hy["middle"] < hy["low"], hy
    shotH = os.path.join(rig.workdir, "stage_height.png")
    stage.grab().save(shotH)
    print("stage height screenshot:", shotH)
    stage.viewCombo.setCurrentIndex(0)
    full = stage.view.sizeHint()
    stage.resize(int(full.width() * 0.6), int(full.height() * 0.6) + 60)
    app.processEvents()
    s = stage.view._scale()
    n, x, y = stage.view._layout()[0]
    from PySide6.QtCore import QPoint
    hit = stage.view._tileAt(QPoint(int((x + 10) * s), int((y + 10) * s)))
    assert s < 0.8 and not tooBig(stage) and hit is stage.view.tiles[n], \
        "the plan shrinks to fit a small window and hovering still finds the tile: scale %.2f, %s" % (s, tooBig(stage))
    stage.grab().save(os.path.join(rig.workdir, "stage_small.png"))
    stage.timer.start(50)
    win._updateShowStatus()
    swatch = win.lightTable.item(0, 0).data(nl.Qt.DecorationRole)
    assert swatch is not None, "no swatch on the first light row"
    stage.hide()
    assert not stage.timer.isActive(), "Stage polling must stop while hidden"
    nl.sequenceControl("stop")
    from neewerlux_stage import RenderDialog
    result = nl.renderSequence("Example - Four Light Demo")
    png = nl.renderSequencePNG(result)
    seeks = []
    dlg = RenderDialog(png, result["sequence"], win, axis=result["axis"], position=lambda: 10000, seek=seeks.append)
    dlg.show()
    app.processEvents()
    assert dlg.strip.positionMs == 10000, "play marker follows the position"
    a = result["axis"]
    mid = a["x0"] + a["width"] // 2
    assert abs(dlg.strip.msAt(mid) - (a["start_ms"] + a["end_ms"]) / 2) < 100, "strip x maps to time"
    dlg._clicked(dlg.strip.msAt(mid))
    assert seeks and abs(seeks[0] - (a["start_ms"] + a["end_ms"]) / 2) < 100, "clicking the strip seeks: %r" % seeks
    dlg.close()

    # The Stage remembers its view and size; a fresh one sizes itself to the lights
    from neewerlux_stage import StageWindow
    remembered = []
    fresh = StageWindow(nl.getStageTiles, win, remember=lambda v, g: remembered.append((v, g)))
    hint = fresh.view.sizeHint()
    assert fresh.view.tiles and fresh.height() >= hint.height(), "a new Stage window fits its lights: %s vs %s" % (fresh.size(), hint)
    fresh.show(); app.processEvents()
    fresh.viewCombo.setCurrentIndex(1)
    app.processEvents()
    assert remembered and remembered[-1][0] == "height", "changing the view is remembered: %r" % remembered
    # not below the window's minimum, which depends on the fonts (offscreen Qt on Windows has none of its own)
    w, h = max(1000, fresh.minimumWidth()), max(720, fresh.minimumHeight())
    fresh.resize(w, h); app.processEvents()
    fresh.close(); app.processEvents()
    assert remembered[-1][0] == "height" and remembered[-1][1].endswith("%d,%d" % (w, h)), "closing remembers the size: %r" % remembered
    again = StageWindow(nl.getStageTiles, win, view=remembered[-1][0], geometry=remembered[-1][1])
    assert again.view.viewMode == "height" and again.width() == w and again.height() == h, "reopens the same way"
    again.close()
    nl._rememberStageWindow("height", "10,10,800,600")
    assert nl.stageView == "height" and "stageView=height" in open(nl.globalPrefsFile, encoding="utf-8").read(), "kept in the prefs file"
    nl._rememberStageWindow("plan", "")

    # Editors: fades and a tall default size
    from neewerlux_anim_editor import AnimationEditorDialog
    ed = AnimationEditorDialog(win, {"name": "Fade Test", "loop": True, "fade_in_ms": 300, "keyframes": []}, "Fade Test")
    assert ed.height() >= 680, "the animation editor opens tall: %d" % ed.height()
    assert ed._fadeInSpin.value() == 300 and ed._fadeOutSpin.value() == -1
    ed._fadeOutSpin.setValue(700)
    r = ed.getResult()
    assert r.get("fade_in_ms") == 300 and r.get("handback_fade_ms") == 700, r
    ed._fadeInSpin.setValue(-1)
    assert "fade_in_ms" not in ed.getResult(), "Global removes the field"
    ed.close()
    from neewerlux_timeline import SequenceSettingsDialog
    sd = SequenceSettingsDialog({"name": "x", "fade_in_ms": 250}, 8, win)
    assert sd.fadeIn.value() == 250 and sd.fadeOut.value() == -1
    sd.fadeOut.setValue(900)
    seqOut = {"name": "x", "fade_in_ms": 250}
    sd.apply(seqOut)
    assert seqOut.get("fade_in_ms") == 250 and seqOut.get("handback_fade_ms") == 900, seqOut
    assert win.fadeInSpin.value() == nl.fadeInMs and win.handbackFadeSpin.value() == nl.handbackFadeMs

    # Spin boxes: Qt's own arrows end up under the text area on Windows, and Qt 6.12 squashes the
    # text of NoButtons boxes, so every spin box hides its arrows through the theme and keeps a
    # usable text area. Walks the main window, every editor and the modal dialogs (exec intercepted).
    from PySide6.QtWidgets import QAbstractSpinBox, QStyle, QStyleOptionSpinBox, QComboBox
    from PySide6.QtCore import QRect
    from neewerlux_ui import SpinBoxWithButtons, DoubleSpinBoxWithButtons

    def nativeSpins(root):
        bad = []
        for w in root.findChildren(QAbstractSpinBox):
            # as it will be on screen: a dialog that was built but never shown isn't styled yet,
            # and Qt 6.11 then reserves the arrows' room
            w.ensurePolished()
            opt = QStyleOptionSpinBox()
            opt.initFrom(w)
            opt.rect = QRect(0, 0, 120, 30)
            opt.buttonSymbols = w.buttonSymbols()
            opt.subControls = QStyle.SC_All
            opt.frame = True
            edit = w.style().subControlRect(QStyle.CC_SpinBox, opt, QStyle.SC_SpinBoxEditField, w)
            if w.property("arrows") != "none" or edit.width() < 100:
                bad.append("%s/%s (text %d px)" % (root.windowTitle() or type(root).__name__,
                                                   w.parent().objectName() or type(w.parent()).__name__, edit.width()))
        return bad

    native = nativeSpins(win)
    seen = []
    realExec = nl.pyside_exec

    def inspect(dlg):
        seen.append(dlg.windowTitle())
        assert not tooBig(dlg), "%s fits a %dx%d screen: its minimum is %s" % ((dlg.windowTitle(),) + SMALL_SCREEN + (tooBig(dlg),))
        native.extend(nativeSpins(dlg))
        assert not fixedTables(dlg), "%s: every table's columns can be dragged: %s" % (dlg.windowTitle(), fixedTables(dlg))
        if dlg.windowTitle().startswith("Edit Preset"):
            sound = [c for c in dlg.findChildren(QComboBox) if c.findData("Pulse") >= 0]
            assert sound and sound[0].itemData(0) == "", "the preset editor offers a sound mode per light"
            from neewerlux_ui import ColourPickRow
            rows = dlg.findChildren(ColourPickRow)
            assert len(rows) == 1, "the preset editor has the wheel and swatches"
            modes = [c for c in dlg.findChildren(QComboBox) if c.findText("HSI") >= 0]
            modes[0].setCurrentText("HSI")
            assert not rows[0].isHidden(), "shown for an HSI light"
            rows[0].set(30, 70)
            assert rows[0].get() == (30, 70), "they set the hue and saturation: %s" % (rows[0].get(),)
        return 0
    nl.pyside_exec = inspect
    try:
        win._openPresetEditor(0)
        win.animNew()
        win._animEditJSON(sorted(nl.savedAnimations)[0])
    finally:
        nl.pyside_exec = realExec
    assert len(seen) == 3, "the three modal editors opened: %r" % seen
    ed = AnimationEditorDialog(win, {"name": "Spin", "loop": True, "keyframes": [
        {"hold_ms": 100, "fade_ms": 0, "lights": {"*": {"mode": "HSI", "hue": 0, "sat": 100, "bri": 50}}}]}, "Spin")
    native.extend(nativeSpins(ed))
    assert not fixedTables(ed), "animation editor: every table's columns can be dragged"
    assert not tooBig(ed), "the animation editor fits a small screen: %s" % (tooBig(ed),)
    ed.close()
    native.extend(nativeSpins(SequenceSettingsDialog({"name": "x"}, 8, win)))
    from neewerlux_timeline import SequenceEditor
    win.seqOpenEditor(sorted(nl.savedSequences)[0])
    app.processEvents()
    for w in app.topLevelWidgets():
        if isinstance(w, SequenceEditor):
            assert not tooBig(w), "the sequence editor fits a small screen: %s" % (tooBig(w),)
            column = w.stage.parentWidget()
            scales = []
            for size, name in (((1100, 700), "editor_small.png"), ((1600, 1250), "editor_tall.png")):
                w.resize(*size)
                w.show()
                app.processEvents()
                app.processEvents()
                spare = column.height() - w.stage.geometry().bottom()
                assert spare < 40, "%dx%d: the preview fills its part of the column (%d px spare)" % (size + (spare,))
                scales.append(w.stage._scale())
                w.grab().save(os.path.join(rig.workdir, name))
            # how much depends on the font (toolbars and tracks take the rest), so only a clear gain is required
            assert scales[1] > scales[0] + 0.1, "the preview grows with the window: %s" % scales
            w.resize(1100, 700)
            app.processEvents()
            propsArea = w.props.parentWidget().parentWidget()
            assert propsArea.viewport().width() >= w.props.minimumSizeHint().width(), \
                "the properties panel is never narrower than its fields: %d < %d" % (propsArea.viewport().width(), w.props.minimumSizeHint().width())
            w.resize(1600, 1250)
            app.processEvents()
            before, sizes = w.stage.height(), w.vSplit.sizes()
            w.vSplit.setSizes([sizes[0] + 80, sizes[1] - 80])
            app.processEvents()
            assert w.stage.height() < before - 40, "the divider between tracks and preview moves: %d then %d" % (before, w.stage.height())
            native.extend(nativeSpins(w))
            native.extend(nativeSpins(w._tempoDialog()))
            w.close()
    from neewerlux_timeline import SongDraftDialog
    assert win.seqFromSongButton.text() == "From song..."
    win.songSectionCommandOnCheck.setChecked(False)
    assert not win.songSectionCommandField.isEnabled() and not win.songFinderNamesCheck.isEnabled(), "turning the finder off greys out its settings"
    win.songSectionCommandOnCheck.setChecked(True)
    assert win.songSectionCommandField.isEnabled()
    songDialog = SongDraftDialog(nl.SongDraftHost(), win)
    assert not tooBig(songDialog) and not tooBig(win), "the song dialog and the main window fit a small screen: %s %s (%s)" % (
        tooBig(songDialog), tooBig(win), widthBreakdown(win))
    native.extend(nativeSpins(songDialog))
    assert songDialog.styleCombo.count() >= 25 and songDialog.styleNote.text(), "the song dialog lists the draft styles"
    styles = songDialog.editStyles()
    app.processEvents()
    assert not tooBig(styles) and not fixedTables(styles), "the style editor fits a small screen and its columns drag: %s %s" % (tooBig(styles), fixedTables(styles))
    assert styles.styleCombo.currentText() == songDialog.styleCombo.currentText() and styles.behaviourButtons["Build"].text() == "build"
    native.extend(nativeSpins(styles))
    styles.close()
    songDialog.close()
    assert not native, "spin boxes with Qt arrows or no room for text (use SpinBoxWithButtons or hideSpinArrows): %r" % native
    sb = SpinBoxWithButtons(minVal=0, maxVal=1000)
    sb.setSingleStep(100); sb.setSpecialValueText("Global")
    sb._plus.click(); sb._plus.click(); sb._minus.click()
    assert sb.value() == 100 and sb.text() == "100", (sb.value(), sb.text())
    sb.setValue(0)
    assert sb.text() == "Global"
    got = []
    sb.valueChanged.connect(got.append)
    sb.blockSignals(True); sb.setValue(5); sb.blockSignals(False); sb.setValue(6)
    assert got == [6], "blockSignals reaches the inner box: %r" % got
    dsb = DoubleSpinBoxWithButtons(minVal=0.0, maxVal=2.0)
    dsb.setSingleStep(0.25); dsb._plus.click()
    assert abs(dsb.value() - 0.25) < 1e-9
    sb.resize(160, 30); sb.show(); app.processEvents()
    assert sb._spin.lineEdit().width() > 60, "the value has room to show: %d" % sb._spin.lineEdit().width()
    sb.close()

    # Light Prefs round trip through the sidecar file
    win.lightTable.selectRow(0)
    win.ColorModeTabWidget.setCurrentIndex(win.TAB_LIGHTPREFS)
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
    picker.aimButtons["back-right"].click()
    savedMac = nl.availableLights[win.selectedLights()[0]][0].address
    win.checkLightPrefs()
    app.processEvents()
    assert win.ColorModeTabWidget.currentIndex() == win.TAB_LIGHTPREFS, "saving stays on Light Preferences"
    assert win.selectedLights() and nl.availableLights[win.selectedLights()[0]][0].address == savedMac, "saving keeps the light selected"
    mac = rig.mac(0)
    sidecar = os.path.join(rig.workdir, "light_prefs", mac.replace(":", ""))
    assert os.path.exists(sidecar), "sidecar not written"
    fields = open(sidecar, encoding="utf-8").read().split("|")
    assert fields[5:15] == ["practical", "left", "4", "", "45", "-1", "True", "back", "high", "back-right"], fields
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
    picker.aimButtons["you"].click()
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
    win.songSectionCommandField.setText("finder {song}")
    win.songSectionCommandOnCheck.setChecked(False)
    nl.globalPrefsFile = os.path.join(rig.workdir, "light_prefs", "NeewerLux.prefs")
    win.saveGlobalPrefs()
    text = open(nl.globalPrefsFile, encoding="utf-8").read()
    assert "envMaxBri=80" in text and "seqFrameRate=15" in text and "simulatedLights=3" in text and "simulatedCCTOnly=1" in text, text
    assert "songSectionCommand=finder {song}" in text and "songSectionCommandOn=0" in text, text
    nl.envMaxBri, nl.seqFrameRate, nl.simulatedLights, nl.simulatedCCTOnly, nl.songSectionCommandOn = 100, 20, 0, False, True
    nl.loadPrefsFile(nl.globalPrefsFile)
    assert nl.envMaxBri == 80 and nl.seqFrameRate == 15 and nl.simulatedLights == 3 and nl.simulatedCCTOnly is True
    assert nl.songSectionCommand == "finder {song}" and nl.songSectionCommandOn is False, "the finder is kept but off"
    win.setupGlobalLightPrefsTab(True)
    assert win.envMaxBriSpin.value() == 100 and win.effectMaxSecondsSpin.value() == 30 and win.simulatedLightsCombo.currentIndex() == 0
    assert win.songSectionCommandOnCheck.isChecked() and win.songSectionCommandField.text() == ""
    nl.songSectionCommand, nl.songSectionCommandOn = "", True

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
    assert win.lightRoleCombo.currentText() == "Rim / back" and win.lightMaxBriSpin.value() == 33, (win.lightRoleCombo.currentText(), win.lightMaxBriSpin.value())

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
