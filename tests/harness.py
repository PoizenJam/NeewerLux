"""Offline test harness for NeewerLux: real code paths, fake Bluetooth.

boot() copies a NeewerLux checkout's code and animation/sequence files into a temp
folder (so tests never write into the repo), imports it, replaces the four lights
with stand-ins whose write_gatt_char records (monotonic time, MAC, bytes), starts
the real worker thread and the real HTTP server on a free local port.

The stand-in lights use the model name NEEWER-RGB176, which the worker already skips
for power/channel reads, so no BLE reads are needed.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

LIGHT_NAME = "NEEWER-RGB176"
# Robert's rig: front right key, front left fill, rear right rim, rear left ambient
RIG = [
    ("AA:00:00:00:00:01", "Key", {"role": "key", "side": "right", "order": 4}),
    ("AA:00:00:00:00:02", "Fill", {"role": "fill", "side": "left", "order": 1}),
    ("AA:00:00:00:00:03", "Rim", {"role": "rim", "side": "right", "order": 3}),
    ("AA:00:00:00:00:04", "Ambient", {"role": "ambient", "side": "left", "order": 2}),
]
START_BYTES = [120, 135, 2, 20, 56, 157]  # CCT 5600K 20%


class Recorder:
    def __init__(self):
        self.lock = threading.Lock()
        self.writes = []

    def add(self, mac, data):
        with self.lock:
            self.writes.append((time.monotonic(), mac, list(data)))

    def clear(self):
        with self.lock:
            self.writes = []

    def snapshot(self):
        with self.lock:
            return list(self.writes)

    def last(self, mac):
        for t, m, d in reversed(self.snapshot()):
            if m == mac and len(d) > 2 and d[1] != 129:
                return d
        return None


class FakeDevice:
    def __init__(self, address):
        self.address = address
        self.name = LIGHT_NAME


class FakeClient:
    def __init__(self, address, recorder):
        self.address = address
        self.recorder = recorder
        self.is_connected = True

    async def write_gatt_char(self, uuid, data, response=False):
        self.recorder.add(self.address, data)


class Rig:
    """A booted NeewerLux module plus helpers."""

    def __init__(self, nl, port, recorder, workdir):
        self.nl = nl
        self.port = port
        self.rec = recorder
        self.workdir = workdir

    def get(self, query, wait=0.0):
        url = "http://127.0.0.1:" + str(self.port) + "/NeewerLux/doAction?" + query
        if "nopage" not in query:
            url += "&nopage"
        with urllib.request.urlopen(url, timeout=10) as r:
            body = r.read()
        if wait:
            time.sleep(wait)
        return body

    def getJSON(self, query):
        url = "http://127.0.0.1:" + str(self.port) + "/NeewerLux/doAction?" + query
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    def post(self, path, body, wait=0.0):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:" + str(self.port) + path, data=data,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            out = json.loads(r.read().decode("utf-8"))
        if wait:
            time.sleep(wait)
        return out

    def mac(self, i):
        return RIG[i][0]

    def reset(self, bytesForAll=None):
        """Stop everything, put every light back to a known state, clear the recorder."""
        nl = self.nl
        if getattr(nl, "showEngine", None) is not None:
            nl.stopAnimation("override")
            nl.stopAnimation("effect", clearQueue=True)
            nl.stopAnimation("show")
            nl.showEngine.stopSequence()
        elif nl.animationRunning:
            nl.stopAnimation()
        time.sleep(0.4)
        for light in nl.availableLights:
            light[3] = list(bytesForAll or START_BYTES)
        if getattr(nl, "showEngine", None) is not None:
            with nl.showEngine.lock:
                nl.showEngine.released.clear()
                nl.showEngine.mailbox.clear()
        nl.animRevertOnFinish = True
        self.rec.clear()

    def setShowPrefs(self, i, **prefs):
        mac = self.mac(i)
        base = dict(self.nl.SHOW_PREF_DEFAULTS)
        base.update(self.nl.lightShowPrefs.get(mac, {}))
        base.update(prefs)
        self.nl.lightShowPrefs[mac] = base


def _copyTree(src, dst):
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        if name.endswith(".py") or name.endswith(".toml"):
            shutil.copy2(os.path.join(src, name), dst)
    for sub in ("animations", "sequences"):
        s = os.path.join(src, "light_prefs", sub)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(dst, "light_prefs", sub))
    os.makedirs(os.path.join(dst, "light_prefs"), exist_ok=True)


def boot(srcDir, verbose=False, roles=True):
    workdir = tempfile.mkdtemp(prefix="nlharness_")
    _copyTree(srcDir, workdir)
    sys.argv = [os.path.join(workdir, "NeewerLux.py")]
    sys.path.insert(0, workdir)
    spec = importlib.util.spec_from_file_location("NeewerLux", sys.argv[0])
    nl = importlib.util.module_from_spec(spec)
    sys.modules["NeewerLux"] = nl
    spec.loader.exec_module(nl)

    nl.loadPrefsFile()
    nl.printDebug = verbose
    nl.findLightsOnStartup = False
    nl.autoReconnectOnDisconnect = False
    nl.setUpAsyncio()

    rec = Recorder()
    lights = []
    for i, (mac, name, prefs) in enumerate(RIG):
        lights.append([FakeDevice(mac), FakeClient(mac, rec), "", list(START_BYTES), [3200, 5600], False, True,
                       ["---", "---"], 0, -50])
    nl.availableLights = lights
    nl.loadAllAnimations()
    nl.loadLightAliases()
    if hasattr(nl, "loadAllSequences"):
        nl.loadAllSequences()
        nl.initShowEngine()
        if roles:
            for mac, name, prefs in RIG:
                p = dict(nl.SHOW_PREF_DEFAULTS)
                p.update(prefs)
                nl.lightShowPrefs[mac] = p

    worker = threading.Thread(target=nl.workerThread, args=(nl.asyncioEventLoop,), name="workerThread", daemon=True)
    worker.start()
    server = nl.ThreadingHTTPServer(("127.0.0.1", 0), nl.NLPythonServer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.3)
    return Rig(nl, server.server_address[1], rec, workdir)
