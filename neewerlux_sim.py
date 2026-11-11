"""Simulated Neewer lights for NeewerLux.

A SimDevice stands in for a Bluetooth device found by a scan, and SimClient for the
BleakClient that talks to it. The client takes the same packets a real light does
(power, CCT, HSI, scene, the split brightness and temperature packets older lights
use, and the power and channel queries), keeps the light's resulting state, and
answers queries through the notification callback, so every code path above the
Bluetooth library runs unchanged. No Qt and no Bluetooth here, so the test harness
uses the same classes.

One assumption is unverified on real hardware: a colour command to a light in standby
turns it on (WAKE_ON_WRITE). Lumiere chose to send a power-on before every write
because it couldn't rely on either behaviour.
"""

import asyncio
import random
import time

SIM_MAC_PREFIX = "5E:11:00:00:00:"  # 0x5E is a locally administered address, never a real light's
WAKE_ON_WRITE = True

# Rig presets: 1 to 4 lights, added in this order. Sweep order runs left to right
# around the room: front left, rear left, rear right, front right.
RIG_LIGHTS = [
    {"label": "Key", "role": "key", "side": "right", "order": 4, "model": "RGB660"},
    {"label": "Fill", "role": "fill", "side": "left", "order": 1, "model": "RGB660"},
    {"label": "Rim", "role": "rim", "side": "right", "order": 3, "model": "RGB660"},
    {"label": "Ambient", "role": "ambient", "side": "left", "order": 2, "model": "RGB660"},
]
CCT_ONLY_LIGHT = {"label": "Practical", "role": "practical", "side": "centre", "order": 5, "model": "SNL660"}
SIM_PREFERRED_ID_BASE = 90  # simulated lights get IDs 91 and up, clear of real lights' 1, 2, 3...


def checksum(data):
    return sum(data) & 0xFF


class SimFaults:
    """Fault injection, all off by default. dropRate: share of writes silently lost.
    disconnectMeanSec: average time between simulated drop-outs (0 = never)."""

    def __init__(self, dropRate=0.0, disconnectMeanSec=0.0, seed=None):
        self.dropRate = dropRate
        self.disconnectMeanSec = disconnectMeanSec
        self.rng = random.Random(seed)

    def nextDisconnect(self):
        if self.disconnectMeanSec <= 0:
            return None
        return time.monotonic() + self.rng.expovariate(1.0 / self.disconnectMeanSec)


class SimLightState:
    """What the light is actually showing, built only from packets it accepted."""

    def __init__(self):
        self.power = True
        self.mode = "CCT"
        self.hue, self.sat, self.bri, self.temp, self.scene = 0, 100, 20, 56, 1
        self.channel = 1
        self.accepted = 0
        self.rejected = 0
        self.lastRejected = None  # the most recent packet it ignored, for diagnosing
        self.dropped = 0
        self.lastKind = ""

    def toCommand(self):
        if not self.power:
            return {"mode": "OFF"}
        if self.mode == "HSI":
            return {"mode": "HSI", "hue": self.hue, "sat": self.sat, "bri": self.bri}
        if self.mode == "ANM":
            return {"mode": "ANM", "scene": self.scene, "bri": self.bri}
        return {"mode": "CCT", "temp": self.temp, "bri": self.bri}


def decodePacket(data, state):
    """Apply one written packet to a light state. Returns what kind of packet it was:
    ON, OFF, CCT, HSI, ANM, BRI, TEMP, QUERY_POWER, QUERY_CHANNEL or BAD (wrong header,
    length or checksum; a real light ignores those, so the state is left alone)."""
    d = list(data)
    if len(d) < 4 or d[0] != 120 or checksum(d[:-1]) != d[-1] or d[2] != len(d) - 4:
        state.rejected += 1
        state.lastRejected = d
        return "BAD"
    cmd = d[1]
    kind = "BAD"
    if cmd == 129 and len(d) == 5:
        if d[3] == 1:
            state.power, kind = True, "ON"
        elif d[3] == 2:
            state.power, kind = False, "OFF"
    elif cmd == 135 and len(d) == 6:
        state.mode, state.bri, state.temp, kind = "CCT", d[3], d[4], "CCT"
    elif cmd == 134 and len(d) == 8:
        state.mode, state.hue, state.sat, state.bri, kind = "HSI", d[3] + (d[4] << 8), d[5], d[6], "HSI"
    elif cmd == 136 and len(d) == 6:
        state.mode, state.bri, state.scene, kind = "ANM", d[3], d[4], "ANM"
    elif cmd == 130 and len(d) == 5:  # older lights: brightness on its own
        state.mode, state.bri, kind = "CCT", d[3], "BRI"
    elif cmd == 131 and len(d) == 5:  # older lights: colour temperature on its own
        state.mode, state.temp, kind = "CCT", d[3], "TEMP"
    elif cmd == 133 and len(d) == 4:
        kind = "QUERY_POWER"
    elif cmd == 132 and len(d) == 4:
        kind = "QUERY_CHANNEL"
    if kind == "BAD":
        state.rejected += 1
        state.lastRejected = d
        return kind
    if kind in ("CCT", "HSI", "ANM", "BRI", "TEMP") and WAKE_ON_WRITE:
        state.power = True
    if not kind.startswith("QUERY"):
        state.accepted += 1
        state.lastKind = kind
    return kind


class SimDevice:
    """Stands in for a bleak BLEDevice: an address, a name, and the light's state."""

    def __init__(self, address, name, faults=None, latencyMs=(5, 20)):
        self.address = address
        self.name = name
        self.details = None
        self.state = SimLightState()
        self.faults = faults or SimFaults()
        self.latencyMs = latencyMs
        self.onWrite = None  # optional callback(address, bytes) for test recorders

    def makeClient(self):
        return SimClient(self)


class SimClient:
    """Stands in for bleak's BleakClient, with the calls NeewerLux makes."""

    def __init__(self, device):
        self.device = device
        self.address = device.address
        self._connected = False
        self._notify = None
        self._dropAt = None

    @property
    def is_connected(self):
        if self._connected and self._dropAt is not None and time.monotonic() >= self._dropAt:
            self._connected = False  # a simulated drop-out, noticed the next time anyone looks
            self._notify = None
        return self._connected

    async def connect(self, **kwargs):
        await asyncio.sleep(0.05)
        self._connected = True
        self._dropAt = self.device.faults.nextDisconnect()
        return True

    async def disconnect(self):
        self._connected = False
        self._notify = None
        return True

    async def start_notify(self, uuid, callback, **kwargs):
        if not self.is_connected:
            raise RuntimeError("simulated light is not connected")
        if self._notify is not None:
            raise RuntimeError("notifications already started")  # bleak raises here too
        self._notify = callback

    async def stop_notify(self, uuid):
        self._notify = None

    async def write_gatt_char(self, uuid, data, response=False):
        if not self.is_connected:
            raise RuntimeError("simulated light is not connected")
        lo, hi = self.device.latencyMs
        if hi > 0:
            await asyncio.sleep(random.uniform(lo, hi) / 1000.0)
        if self.device.onWrite is not None:
            self.device.onWrite(self.address, bytes(data))
        faults = self.device.faults
        if faults.dropRate > 0 and faults.rng.random() < faults.dropRate:
            self.device.state.dropped += 1
            return
        kind = decodePacket(data, self.device.state)
        if kind.startswith("QUERY") and self._notify is not None:
            if kind == "QUERY_POWER":
                reply = [120, 2, 1, 1 if self.device.state.power else 2]
            else:
                reply = [120, 1, 1, self.device.state.channel]
            reply.append(checksum(reply))
            callback = self._notify
            asyncio.get_running_loop().call_later((lo + hi) / 2000.0, callback, None, bytearray(reply))


def buildRig(count, includeCCTOnly=False, faults=None):
    """Simulated lights for a rig preset. Returns a list of (SimDevice, preset) pairs;
    preset holds the role, side, sweep order and preferred ID to use when the light has
    no saved preferences yet."""
    # Numbered by position in the full rig, so a light keeps its address (and with it its
    # saved preferences) whichever preset is chosen; the CCT-only light is always number 5
    lights = list(enumerate(RIG_LIGHTS[:max(0, min(len(RIG_LIGHTS), count))], start=1))
    if includeCCTOnly:
        lights.append((len(RIG_LIGHTS) + 1, CCT_ONLY_LIGHT))
    rig = []
    for n, spec in lights:
        device = SimDevice(SIM_MAC_PREFIX + "%02X" % n, "SIM-" + spec["model"] + "-" + spec["label"],
                           faults=faults)
        preset = dict(spec)
        preset["preferredID"] = SIM_PREFERRED_ID_BASE + n
        rig.append((device, preset))
    return rig


def isSimulated(device):
    return isinstance(device, SimDevice)
