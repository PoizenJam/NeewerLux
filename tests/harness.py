"""Offline test harness for NeewerLux: real code paths, fake Bluetooth.

boot() copies a NeewerLux checkout's code and animation/sequence files into a temp
folder (so tests never write into the repo), imports it, replaces the four lights
with stand-ins whose write_gatt_char records (monotonic time, MAC, bytes), starts
the real worker thread and the real HTTP server on a free local port.

The stand-in lights are neewerlux_sim simulated lights, so packets are decoded, power and
channel queries are answered through notifications, and the worker's status polling runs.
compare_legacy.py boots with model "RGB176" (a light that skips status polling) because
v1.3.0's polling would otherwise add timing noise to an exact comparison.
"""
import atexit
import copy
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

# Robert's rig: front right key, front left fill, rear right rim, rear left background
RIG = [
    ("AA:00:00:00:00:01", "Key", {"role": "key", "side": "right", "order": 4}),
    ("AA:00:00:00:00:02", "Fill", {"role": "fill", "side": "left", "order": 1}),
    ("AA:00:00:00:00:03", "Rim", {"role": "rim", "side": "right", "order": 3}),
    ("AA:00:00:00:00:04", "Background", {"role": "background", "side": "left", "order": 2}),
]
START_BYTES = [120, 135, 2, 20, 56, 77]  # CCT 5600K 20%
# A file to keep every write in, one segment per clear() (each test resets): trace_compare.py
# compares two such traces, to show a refactor left the suites' writes alone.
TRACE_PATH = os.environ.get("NL_WRITE_TRACE")


class Recorder:
    def __init__(self):
        self.lock = threading.Lock()
        self.writes = []
        self.segment = None
        if TRACE_PATH:
            # one JSON line per test, written when the next one starts, and the last at exit
            open(TRACE_PATH, "w").close()
            self.segment = []
            self.segmentStart = time.monotonic()
            atexit.register(self._saveSegment)
            # test_webui and test_timeline_editor end with os._exit, which skips atexit
            realExit = os._exit

            def exitSaving(code):
                with self.lock:
                    self._saveSegment()
                realExit(code)
            os._exit = exitSaving

    def add(self, mac, data):
        if len(data) > 1 and data[1] in (132, 133):
            return  # status queries from the worker's poll, not light changes
        with self.lock:
            now = time.monotonic()
            self.writes.append((now, mac, list(data)))
            if self.segment is not None:
                self.segment.append([round((now - self.segmentStart) * 1000.0, 1), mac, list(data)])

    def clear(self):
        with self.lock:
            self.writes = []
            if self.segment is not None:
                self._saveSegment()
                self.segment = []
                self.segmentStart = time.monotonic()

    def _saveSegment(self):
        with open(TRACE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(self.segment, separators=(",", ":")) + "\n")

    def snapshot(self):
        with self.lock:
            return list(self.writes)

    def last(self, mac):
        for t, m, d in reversed(self.snapshot()):
            if m == mac and len(d) > 2 and d[1] != 129:
                return d
        return None


def _simModule(nl):
    """The simulator module NeewerLux itself imported (so its isinstance checks see our
    lights), or this checkout's copy when booting a version that predates it."""
    if hasattr(nl, "sim"):
        return nl.sim
    spec = importlib.util.spec_from_file_location("neewerlux_sim_harness",
                                                  os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "neewerlux_sim.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
        if hasattr(nl, "handbackFadeMs"):
            nl.handbackFadeMs = 0  # most tests check exact values right after a hand-back; t_handbackFade turns it on
        if getattr(nl, "showEngine", None) is not None:
            nl.stopAnimation("override")
            nl.stopAnimation("effect", clearQueue=True)
            nl.stopAnimation("show")
            nl.showEngine.stopSequence()
            if hasattr(nl, "stopSound"):
                nl.stopSound()
        elif nl.animationRunning:
            nl.stopAnimation()
        time.sleep(0.4)
        self.resetLights(bytesForAll)
        if getattr(nl, "showEngine", None) is not None:
            with nl.showEngine.lock:
                nl.showEngine.released.clear()
                nl.showEngine.mailbox.clear()
        nl.animRevertOnFinish = True
        if hasattr(nl, "presetSounds"):
            nl.presetSounds.clear()
        self.rec.clear()

    def resetLights(self, bytesForAll=None, on=None):
        """Every light holding bytesForAll (default START_BYTES) as its stored value; on sets
        their on/off flag too."""
        for light in self.nl.availableLights:
            if hasattr(self.nl, "Light"):
                light.state = self.nl.neewer.decode(list(bytesForAll or START_BYTES))
            else:  # v1.3.0's positional lists, for compare_legacy
                light[3] = list(bytesForAll or START_BYTES)
            if on is not None:
                light.on = bool(on)

    def device(self, i):
        """Light i's simulated device (its onWrite and latencyMs can be changed)."""
        return self.nl.availableLights[i].device

    def setCCTOnly(self, i, cctOnly):
        self.nl.availableLights[i].cctOnly = bool(cctOnly)

    def lightsSnapshot(self):
        """Everything held for each light, and its device's name, for restoreLights."""
        return [(light.device, light.client, light.device.name,
                 copy.deepcopy({k: v for k, v in vars(light).items() if k not in ("device", "client")}))
                for light in self.nl.availableLights]

    def restoreLights(self, snapshot):
        """The lights as lightsSnapshot found them: the same devices and links, every value
        back, and the list holding them alone (rediscover rebuilds it)."""
        self.nl.availableLights[:] = []
        for device, client, name, values in snapshot:
            device.name = name
            self.nl.availableLights.append(self.nl.Light(device, client, **copy.deepcopy(values)))

    def rediscover(self):
        """What a restart does to the lights: a scan finds them again and findDevices builds each
        from its saved preferences file, then each is linked. The same simulated devices come
        back, in rig order."""
        nl = self.nl
        devices = [light.device for light in nl.availableLights]

        async def scan(return_adv=False):
            return {d.address: (d, None) for d in devices}

        real = nl.BleakScanner
        nl.BleakScanner = type("SimScanner", (), {"discover": staticmethod(scan)})
        try:
            nl.availableLights[:] = []
            nl.asyncioEventLoop.run_until_complete(nl.findDevices())
        finally:
            nl.BleakScanner = real
        for light in nl.availableLights:
            client = light.device.makeClient()
            client._connected = True
            light.client = client

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
    for sub in ("animations", "sequences", "sound_modes", "palettes", "draft_styles"):
        s = os.path.join(src, "light_prefs", sub)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(dst, "light_prefs", sub))
    os.makedirs(os.path.join(dst, "light_prefs"), exist_ok=True)


def boot(srcDir, verbose=False, roles=True, model="RGB660", worker=True):
    """worker False leaves the worker thread and the compositor's thread unstarted, for a
    caller that ticks the compositor and drains the writes itself (record_writes.py)."""
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
    simLib = _simModule(nl)
    lights = []
    for i, (mac, name, prefs) in enumerate(RIG):
        device = simLib.SimDevice(mac, "NEEWER-" + model, latencyMs=(1, 3))
        device.onWrite = rec.add
        client = device.makeClient()
        client._connected = True
        if hasattr(nl, "Light"):
            lights.append(nl.Light(device, client, "", nl.neewer.decode(START_BYTES), [3200, 5600], False, True, prefId=0, rssi=-50))
        else:  # v1.3.0 for compare_legacy: positional lists
            lights.append([device, client, "", list(START_BYTES), [3200, 5600], False, True, ["---", "---"], 0, -50])
    nl.availableLights = lights
    nl.loadAllAnimations()
    nl.loadLightAliases()
    if hasattr(nl, "loadAllSequences"):
        nl.loadAllSequences()
        if hasattr(nl, "loadAllSoundModes"):
            nl.loadAllSoundModes()
        nl.initShowEngine()
        if not worker:
            nl.showEngine.stopThread()
        if roles:
            for mac, name, prefs in RIG:
                p = dict(nl.SHOW_PREF_DEFAULTS)
                p.update(prefs)
                nl.lightShowPrefs[mac] = p

    if worker:
        threading.Thread(target=nl.workerThread, args=(nl.asyncioEventLoop,), name="workerThread", daemon=True).start()
    server = nl.ThreadingHTTPServer(("127.0.0.1", 0), nl.NLPythonServer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.3)
    if hasattr(nl, "handbackFadeMs"):
        nl.handbackFadeMs = 0  # see Rig.reset
    return Rig(nl, server.server_address[1], rec, workdir)
