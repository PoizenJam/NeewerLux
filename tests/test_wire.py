"""Bluetooth packet tests: fixed byte vectors for every packet NeewerLux sends, and the
simulator's decoder checked against NeewerLux's encoder.

The expected bytes were taken from the v1.3.0 encoder and checked by hand against the
packet layout (header 120, command, payload length, payload, checksum = sum mod 256), so
any change to what goes over the air fails here. Runs without Qt or Bluetooth.
Run: python tests/test_wire.py
"""
import ast
import asyncio
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import neewerlux_sim as sim  # noqa: E402

GOLDEN = [
    ("CCT", {"brightness": 100, "temp": 56}, [120, 135, 2, 100, 56, 157]),
    ("CCT", {"brightness": 0, "temp": 32}, [120, 135, 2, 0, 32, 33]),
    ("CCT", {"brightness": 50, "temp": 85}, [120, 135, 2, 50, 85, 136]),
    ("CCT", {"brightness": 20, "temp": 100}, [120, 135, 2, 20, 100, 121]),
    ("HSI", {"HSI_H": 0, "HSI_S": 100, "HSI_I": 100}, [120, 134, 4, 0, 0, 100, 100, 202]),
    ("HSI", {"HSI_H": 255, "HSI_S": 50, "HSI_I": 50}, [120, 134, 4, 255, 0, 50, 50, 101]),
    ("HSI", {"HSI_H": 256, "HSI_S": 0, "HSI_I": 1}, [120, 134, 4, 0, 1, 0, 1, 4]),
    ("HSI", {"HSI_H": 300, "HSI_S": 100, "HSI_I": 60}, [120, 134, 4, 44, 1, 100, 60, 207]),
    ("HSI", {"HSI_H": 360, "HSI_S": 100, "HSI_I": 100}, [120, 134, 4, 104, 1, 100, 100, 51]),
    ("ANM", {"brightness": 100, "animation": 1}, [120, 136, 2, 100, 1, 103]),
    ("ANM", {"brightness": 10, "animation": 9}, [120, 136, 2, 10, 9, 21]),
]
SPLIT_GOLDEN = [
    ([120, 135, 2, 100, 56, 157], [[120, 130, 1, 100, 95], [120, 131, 1, 56, 52]]),
    ([120, 135, 2, 7, 32, 0], [[120, 130, 1, 7, 2], [120, 131, 1, 32, 28]]),
]
POWER = {"ON": [120, 129, 1, 1, 251], "OFF": [120, 129, 1, 2, 252]}
QUERIES = {"power": [120, 133, 0, 253], "channel": [120, 132, 0, 252]}

FAILED = []


def check(cond, msg):
    if not cond:
        FAILED.append(msg)
        print("FAIL", msg)


def encoder():
    """NeewerLux's own encoder functions, lifted out of NeewerLux.py so this test needs
    neither Qt nor bleak."""
    src = io.open(os.path.join(ROOT, "NeewerLux.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    ns = {"CCTSlider": -1}
    exec("\n".join(ast.get_source_segment(src, n) for n in tree.body if isinstance(n, ast.FunctionDef) and
                   n.name in ("calculateChecksum", "calculateByteString", "calculateSeparateBytestrings")), ns)
    return ns


def t_golden(enc):
    for mode, kw, expected in GOLDEN:
        got = enc["calculateByteString"](True, colorMode=mode, **kw)
        check(got == expected, "%s %s encoded as %s, expected %s" % (mode, kw, got, expected))
        check(sum(expected[:-1]) % 256 == expected[-1] and expected[2] == len(expected) - 4,
              "golden vector %s is not well formed" % expected)
    for full, expected in SPLIT_GOLDEN:
        got = enc["calculateSeparateBytestrings"](full)
        check(got == expected, "split %s gave %s, expected %s" % (full, got, expected))
    for name, packet in list(POWER.items()) + list(QUERIES.items()):
        check(sum(packet[:-1]) % 256 == packet[-1], name + " packet checksum")


def t_decoderRoundTrip(enc):
    for mode, kw, packet in GOLDEN:
        st = sim.SimLightState()
        kind = sim.decodePacket(packet, st)
        check(kind == mode, "decoded %s as %s" % (packet, kind))
        cmd = st.toCommand()
        if mode == "CCT":
            check(cmd == {"mode": "CCT", "temp": kw["temp"], "bri": kw["brightness"]}, "CCT round trip %s" % cmd)
        elif mode == "HSI":
            check(cmd == {"mode": "HSI", "hue": kw["HSI_H"], "sat": kw["HSI_S"], "bri": kw["HSI_I"]}, "HSI round trip %s" % cmd)
        else:
            check(cmd == {"mode": "ANM", "scene": kw["animation"], "bri": kw["brightness"]}, "ANM round trip %s" % cmd)
    st = sim.SimLightState()
    for packet in SPLIT_GOLDEN[0][1]:
        sim.decodePacket(packet, st)
    check(st.toCommand() == {"mode": "CCT", "temp": 56, "bri": 100}, "split packets round trip %s" % st.toCommand())
    st = sim.SimLightState()
    check(sim.decodePacket(POWER["OFF"], st) == "OFF" and st.toCommand() == {"mode": "OFF"}, "power off")
    check(sim.decodePacket(POWER["ON"], st) == "ON" and st.power, "power on")


def t_badPacketsIgnored():
    st = sim.SimLightState()
    before = st.toCommand()
    for bad in ([120, 135, 2, 100, 56, 158], [121, 135, 2, 100, 56, 158], [120, 135, 3, 100, 56, 158], [120, 135], [120, 99, 0, 219]):
        check(sim.decodePacket(bad, st) == "BAD", "accepted a bad packet %s" % bad)
    check(st.toCommand() == before and st.rejected == 5, "bad packets changed the state")


def t_clientQueriesAndFaults():
    async def run():
        dev = sim.SimDevice("5E:11:00:00:00:01", "SIM-RGB660-Key", latencyMs=(0, 0))
        client = dev.makeClient()
        try:
            await client.write_gatt_char("w", bytearray(GOLDEN[0][2]))
            check(False, "write before connect should fail")
        except RuntimeError:
            pass
        check(await client.connect(), "connect")
        replies = []
        await client.start_notify("n", lambda sender, data: replies.append(list(data)))
        try:
            await client.start_notify("n", lambda s, d: None)
            check(False, "a second start_notify should fail, as bleak's does")
        except RuntimeError:
            pass
        await client.write_gatt_char("w", bytearray(QUERIES["power"]))
        await client.write_gatt_char("w", bytearray(POWER["OFF"]))
        await client.write_gatt_char("w", bytearray(QUERIES["power"]))
        await client.write_gatt_char("w", bytearray(QUERIES["channel"]))
        await asyncio.sleep(0.01)
        check(replies[:3] == [[120, 2, 1, 1, 124], [120, 2, 1, 2, 125], [120, 1, 1, 1, 123]], "query replies %s" % replies)
        await client.write_gatt_char("w", bytearray(GOLDEN[4][2]))
        check(dev.state.power and dev.state.mode == "HSI", "a colour command wakes the light (WAKE_ON_WRITE)")

        lossy = sim.SimDevice("5E:11:00:00:00:02", "SIM-RGB660-Fill", faults=sim.SimFaults(dropRate=1.0, seed=1), latencyMs=(0, 0))
        lc = lossy.makeClient()
        await lc.connect()
        await lc.write_gatt_char("w", bytearray(GOLDEN[4][2]))
        check(lossy.state.mode == "CCT" and lossy.state.dropped == 1, "dropped write still changed the light")

        flaky = sim.SimDevice("5E:11:00:00:00:03", "SIM-RGB660-Rim", faults=sim.SimFaults(disconnectMeanSec=0.001, seed=2), latencyMs=(0, 0))
        fc = flaky.makeClient()
        await fc.connect()
        await asyncio.sleep(0.05)
        check(not fc.is_connected, "simulated drop-out did not disconnect")
        fc2 = flaky.makeClient()
        check(await fc2.connect(), "reconnect after a drop-out")
    asyncio.run(run())


def t_rigPresets():
    for n in range(0, 5):
        rig = sim.buildRig(n)
        check(len(rig) == n, "preset %d has %d lights" % (n, len(rig)))
    rig = sim.buildRig(4, includeCCTOnly=True)
    roles = [p["role"] for _, p in rig]
    check(roles == ["key", "fill", "rim", "ambient", "practical"], "preset roles %s" % roles)
    check(len({d.address for d, _ in rig}) == 5 and all(d.address.startswith(sim.SIM_MAC_PREFIX) for d, _ in rig), "addresses")
    check([p["preferredID"] for _, p in rig] == [91, 92, 93, 94, 95], "preferred IDs")
    check(rig[4][0].name == "SIM-SNL660-Practical", "CCT-only light name picks a CCT-only model")


def main():
    enc = encoder()
    t_golden(enc)
    t_decoderRoundTrip(enc)
    t_badPacketsIgnored()
    t_clientQueriesAndFaults()
    t_rigPresets()
    print("wire tests:", "PASS" if not FAILED else "FAIL (" + str(len(FAILED)) + ")")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
