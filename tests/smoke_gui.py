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
    nl.globalPrefsFile = os.path.join(rig.workdir, "light_prefs", "NeewerLux.prefs")
    win.saveGlobalPrefs()
    text = open(nl.globalPrefsFile, encoding="utf-8").read()
    assert "envMaxBri=80" in text and "seqFrameRate=15" in text, text
    nl.envMaxBri, nl.seqFrameRate = 100, 20
    nl.loadPrefsFile(nl.globalPrefsFile)
    assert nl.envMaxBri == 80 and nl.seqFrameRate == 15
    win.setupGlobalLightPrefsTab(True)
    assert win.envMaxBriSpin.value() == 100 and win.effectMaxSecondsSpin.value() == 30
    print("GUI smoke test: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
