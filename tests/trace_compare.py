"""Runs the test suites recording every write, and compares two such traces.

The suites run in real time, so two runs of the same code never send exactly the same frames
(a fade sampled a few ms apart gives other in-between values, and short tests catch a fade at
different points). What does hold between runs is the value each light is left on at the end
of each test (one segment per harness reset), so that is what must match; the allowance for
timing is calibrated on two runs of unchanged code (MAX_FINALS_DIFFERING). The similarity of
the whole value sequences (repeats collapsed, times ignored, difflib ratio) is printed for the
lowest-scoring tests as a pointer, not judged. The virtual-clock corpus in record_writes.py is
the exact check; this one covers what only the suites reach.

  python tests/record_writes.py --trace run DIR        run the suites, write DIR/<suite>.jsonl
  python tests/record_writes.py --trace compare A B    compare two such folders
"""
import difflib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Suites that reset the rig between tests, so each test is a segment. smoke_gui and test_webui
# never reset: their one segment ends wherever the suite's teardown catches the lights (5 of
# their 8 lights ended differently in calibration), so they say nothing here.
SUITES = ["test_show", "test_timeline_editor"]
# Two runs of 1.5.0 m1a (v1.4.2 code) in the sandbox left 2 of 192 (test, light) pairs on a
# different value (test_show 72 and 73, timing tests); allowed twice that.
MAX_FINALS_DIFFERING = 4


def run(outDir):
    os.makedirs(outDir, exist_ok=True)
    failed = []
    for suite in SUITES:
        env = dict(os.environ, NL_WRITE_TRACE=os.path.join(os.path.abspath(outDir), suite + ".jsonl"))
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        print("running " + suite, flush=True)
        rc = subprocess.call([sys.executable, os.path.join(HERE, suite + ".py")], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rc:
            failed.append(suite)
    if failed:
        print("these suites failed, so their traces may be cut short: " + ", ".join(failed))
    return 1 if failed else 0


def _collapsed(writes):
    perLight = {}
    for _, mac, data in writes:
        seq = perLight.setdefault(mac, [])
        value = tuple(data)
        if not seq or seq[-1] != value:
            seq.append(value)
    return perLight


def scores(dirA, dirB):
    """[(score, suite, segment, mac, lenA, lenB, final values equal)] for every test and light in
    either trace; a missing trace or a different number of tests gives one entry with mac set to
    the reason."""
    out = []
    for suite in SUITES:
        pa, pb = os.path.join(dirA, suite + ".jsonl"), os.path.join(dirB, suite + ".jsonl")
        if not (os.path.exists(pa) and os.path.exists(pb)):
            out.append((0.0, suite, -1, "trace missing", 0, 0, False))
            continue
        with open(pa, encoding="utf-8") as f:
            segA = [json.loads(line) for line in f if line.strip()]
        with open(pb, encoding="utf-8") as f:
            segB = [json.loads(line) for line in f if line.strip()]
        if len(segA) != len(segB):
            out.append((0.0, suite, -1, "%d tests against %d" % (len(segA), len(segB)), 0, 0, False))
            continue
        for i, (a, b) in enumerate(zip(segA, segB)):
            ca, cb = _collapsed(a), _collapsed(b)
            for mac in sorted(set(ca) | set(cb)):
                x, y = ca.get(mac, []), cb.get(mac, [])
                ratio = difflib.SequenceMatcher(None, x, y, autojunk=False).ratio() if (x or y) else 1.0
                out.append((ratio, suite, i, mac, len(x), len(y), x[-1:] == y[-1:]))
    return out


def compare(dirA, dirB):
    res = scores(dirA, dirB)
    res.sort()
    print("lowest similarities (not judged):")
    for r in res[:8]:
        print("  %.3f  %-12s test %3d  %-18s %5d / %5d values" % r[:6])
    differing = [r for r in res if not r[6]]
    for r in differing:
        print("  ends differently: %s test %d, %s" % (r[1], r[2], r[3]))
    ok = len(differing) <= MAX_FINALS_DIFFERING
    print("suite traces: %d of %d lights end a test on a different value (allowed %d): %s"
          % (len(differing), len(res), MAX_FINALS_DIFFERING, "PASS" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv):
    if len(argv) >= 2 and argv[0] == "run":
        return run(argv[1])
    if len(argv) >= 3 and argv[0] == "compare":
        return compare(argv[1], argv[2])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
