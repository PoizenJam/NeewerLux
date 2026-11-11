"""Plays the same HTTP URLs against v1.3.0 and the current code and compares what each
light receives. Run: python tests/compare_legacy.py <path to an unmodified v1.3.0 checkout>

Each run is its own process through the harness (fake Bluetooth, real worker, real
HTTP server). Per light, consecutive duplicate writes are collapsed and the value
sequences must match one v1.3.0 run exactly; v1.3.0 runs several times because it is
not deterministic. Timing is reported, not compared, because v1.3.0's engine drifts.

This compares the engines, so the current code runs with v1.3.0's animation files and with
the flash guard off: 1.3.3 slowed the shipped animations that flashed more than 3 times a
second and added the guard, and tests/test_show.py checks both of those.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# (query, seconds to wait afterwards). Covers mode commands, batch, presets, power,
# animations with each pipe field, stop, chaining with and without revert.
LEGACY_RUNS = 3

SCENARIO = [
    ("light=1&mode=CCT&temp=45&bri=60", 0.6),
    ("light=*&mode=HSI&hue=120&sat=100&bri=40", 0.6),
    ("batch=1:HSI:0:100:50;2:CCT:56:80;3:OFF", 0.6),
    ("light=3&on", 0.6),
    ("use_preset=2", 0.8),
    ("animate=Strobe|1.0|10|80|true|3", 1.4),
    ("animate=Key%20Fill%20Rim|4|10|100", 1.25),
    ("stop_animate", 0.6),
    ("animate=Police%20Flash|1|10|100|true|2", 0.3),
    ("animate=Heartbeat|1|10|100|false|0|false", 3.0),
    ("light=2&mode=CCT&temp=50&bri=30", 0.6),
    ("animate=Color%20Wash|2|8|60|false|0|true", 4.0),
    ("animate=Spotlight|1|5|100", 0.8),
    ("stop_animate", 0.8),
]
# Left out on purpose: a mode command while an animation plays (e.g. animate=Spotlight then
# light=1&mode=HSI...). v1.3.0 logs "Reverting lights to pre-animation state" but the next
# command's send overwrites the revert, so the other lights stay on the animation's last
# frame. The current code completes the revert. tests/test_show.py checks the new behaviour.


def run(srcDir, outPath, animSrc=None):
    sys.path.insert(0, HERE)
    import harness
    import shutil
    rig = harness.boot(srcDir, roles=False, model="RGB176")
    if hasattr(rig.nl, "flashGuardEnabled"):
        rig.nl.flashGuardEnabled = False
    if animSrc:
        src = os.path.join(animSrc, "light_prefs", "animations")
        dst = os.path.join(rig.workdir, "light_prefs", "animations")
        for name in os.listdir(src):
            shutil.copy2(os.path.join(src, name), os.path.join(dst, name))
        rig.nl.loadAllAnimations()
    rig.reset()
    t0 = None
    for query, wait in SCENARIO:
        rig.get(query, wait)
    writes = rig.rec.snapshot()
    t0 = writes[0][0] if writes else 0
    json.dump([[round(t - t0, 4), m, d] for t, m, d in writes], open(outPath, "w"))


def collapse(trace):
    perLight = {}
    for t, m, d in trace:
        seq = perLight.setdefault(m, [])
        if not seq or seq[-1][1] != d:
            seq.append((t, d))
    return perLight


def trace(src, label, animSrc=None):
    out = os.path.join(HERE, "_trace_" + label + ".json")
    subprocess.run([sys.executable, "-I", os.path.abspath(__file__), "--run", src, out] + ([animSrc] if animSrc else []), check=True)
    t = collapse(json.load(open(out)))
    os.remove(out)
    return t


def values(t):
    return {m: [d for _, d in v] for m, v in t.items()}


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "--run":
        run(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
        return 0
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    legacyDir = os.path.abspath(sys.argv[1])
    # v1.3.0 is not deterministic here (its animation thread and the worker race over
    # threadAction), so it runs several times and the current code must match one run exactly.
    legacyRuns = [trace(legacyDir, "v1_3_0_" + str(i)) for i in range(LEGACY_RUNS)]
    current = trace(ROOT, "current", legacyDir)
    distinct = []
    for r in legacyRuns:
        if values(r) not in [values(x) for x in distinct]:
            distinct.append(r)
    print("v1.3.0 gave", len(distinct), "different result(s) in", LEGACY_RUNS, "runs")
    match = next((r for r in legacyRuns if values(r) == values(current)), None)
    if match is not None:
        for mac in sorted(current):
            ta = [t for t, _ in match[mac]]
            tb = [t for t, _ in current[mac]]
            worst = max((abs(x - y) for x, y in zip(ta, tb)), default=0)
            print("same", mac, len(tb), "distinct writes, largest timing difference %.0f ms" % (worst * 1000))
        print("legacy URL comparison: PASS (matches a v1.3.0 run exactly)")
        return 0
    a, b = legacyRuns[0], current
    for mac in sorted(set(a) | set(b)):
        va = [d for _, d in a.get(mac, [])]
        vb = [d for _, d in b.get(mac, [])]
        if va != vb:
            n = next((i for i in range(min(len(va), len(vb))) if va[i] != vb[i]), min(len(va), len(vb)))
            print("DIFF", mac, "values", len(va), "vs", len(vb), "first difference at #" + str(n),
                  va[n:n + 3], "vs", vb[n:n + 3])
    print("legacy URL comparison: FAIL (no v1.3.0 run matched)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
