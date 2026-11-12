"""Offline tests for sound modes: the analysis (tempo, beats, bands, silence) fed with synthetic
signals, the shipped sound modes against worst-case signals with the flash guard off, and the
mode file checks. No sound card needed. Run: python tests/test_audio.py
Skips (and passes) when numpy, part of the optional audio group, isn't installed."""
import glob
import json
import math
import os
import sys
import traceback

sys.argv = [sys.argv[0]]
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

try:
    import numpy as np
except ImportError:
    print("audio tests: SKIP (numpy, from the optional audio group, isn't installed)")
    sys.exit(0)

import neewerlux_audio as au  # noqa: E402
import neewerlux_show as show  # noqa: E402

SR = au.SAMPLE_RATE
RESULTS = []


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ------------------------------------------------------------------ synthetic signals

def clicks(bpm, secs, amp=0.8, offset=0.0):
    x = np.zeros(int(secs * SR))
    n = int(0.01 * SR)
    burst = amp * np.exp(-np.linspace(0, 8, n)) * np.random.default_rng(1).uniform(-1, 1, n)
    times, t = [], offset
    while t < secs - 0.02:
        i = int(t * SR)
        x[i:i + n] += burst
        times.append(t)
        t += 60.0 / bpm
    return x, times


def kickHats(bpm, secs):
    x = np.zeros(int(SR * secs))
    p = 60.0 / bpm
    t = np.arange(int(0.15 * SR)) / SR
    kick = 0.9 * np.sin(2 * np.pi * (50 + 80 * np.exp(-t * 30)) * t) * np.exp(-t * 12)
    n = int(0.03 * SR)
    hat = 0.25 * np.random.default_rng(3).uniform(-1, 1, n) * np.exp(-np.linspace(0, 6, n))
    b = 0.0
    while b < secs - 0.5:
        i = int(b * SR)
        x[i:i + len(kick)] += kick
        for k in range(4):
            j = int((b + k * p / 4) * SR)
            x[j:j + n] += hat * (1.0 if k == 2 else 0.5)
        b += p
    return x


def tone(freq, secs, amp=0.3):
    return amp * np.sin(2 * np.pi * freq * np.arange(int(secs * SR)) / SR)


def gated(source, rate, duty=0.5):
    t = np.arange(len(source)) / SR
    return source * (((t * rate) % 1.0) < duty)


def noise(secs, amp=0.7, seed=5):
    return np.random.default_rng(seed).uniform(-amp, amp, int(SR * secs))


def worstCases():
    t = np.arange(int(SR * 12)) / SR
    switching = 0.5 * np.where(((t * 4) % 1.0) < 0.5, np.sin(2 * np.pi * 60 * t), np.sin(2 * np.pi * 9000 * t))
    return {"clicks 180 BPM": clicks(180, 12)[0], "clicks 100 BPM": clicks(100, 12)[0],
            "kick and hats 128 BPM": kickHats(128, 12), "noise bursts 8 Hz": gated(noise(12), 8),
            "noise bursts 3 Hz": gated(noise(12), 3), "noise bursts 1.5 Hz": gated(noise(12), 1.5),
            "loud and silent every 0.3 s": gated(noise(12, 0.9), 1 / 0.3), "bass and treble switching 4 Hz": switching}


def beatTimes(features):
    out, last = [], 0
    for f in features:
        if f["beat"] != last:
            out.append(f["t"])
            last = f["beat"]
    return out


# ------------------------------------------------------------------ analysis

def t_tempoOfClickTracks():
    """Tempo within 2% from 70 to 175 BPM (no octave errors), and beats land on the clicks. A
    bare pulse faster than that may read at half speed, which still lands on every other click."""
    worst = 0.0
    for bpm in (70, 90, 100, 120, 128, 140, 160, 174, 180, 195):
        x, clickT = clicks(bpm, 20)
        fs = au.Analyzer().analyze(x)
        got = fs[-1]["bpm"]
        ok = abs(got / bpm - 1) < 0.02 or (bpm > 175 and abs(got / (bpm / 2.0) - 1) < 0.02)
        check(ok, "%d BPM read as %.1f" % (bpm, got))
        if bpm > 175:
            continue  # at half speed either click can be "the" beat; only the tempo is checked
        errs = [min(abs(b - c) for c in clickT) for b in beatTimes(fs) if 8 < b < 19.5]
        check(len(errs) >= int(10 * got / 60), "%d BPM: only %d beats in 11.5 s" % (bpm, len(errs)))
        worst = max(worst, float(np.median(errs)))
        check(max(errs) < 0.08, "%d BPM: a beat %.0f ms off its click" % (bpm, max(errs) * 1000))
    RESULTS.append("    click tracks 70 to 195 BPM: tempo within 2%%, beats a median %.0f ms after the clicks at worst" % (worst * 1000))


def t_tempoOfDrumPattern():
    """Kick on the beat under sixteenth-note hi-hats (louder on the off-beat): the beat, not
    the hats, from 90 to 175 BPM."""
    for bpm in (90, 110, 124, 132, 150, 160, 174):
        got = au.Analyzer().analyze(kickHats(bpm, 14))[-1]["bpm"]
        check(abs(got / bpm - 1) < 0.02, "kick and hats at %d read as %.1f" % (bpm, got))


def t_tempoChange():
    """A change from 100 to 140 BPM is followed within a few seconds; a single odd estimate
    doesn't flip it."""
    a, _ = clicks(100, 14)
    b, _ = clicks(140, 14)
    fs = au.Analyzer().analyze(np.concatenate((a, b)))
    hop = au.HOP / SR
    at = lambda secs: fs[int(secs / hop)]["bpm"]
    check(abs(at(13.5) / 100 - 1) < 0.02, "before the change: %.1f" % at(13.5))
    switched = next((f["t"] for f in fs if f["t"] > 14 and abs(f["bpm"] / 140 - 1) < 0.02), None)
    check(switched is not None and switched < 14 + 6.0, "the new tempo was followed at %s s" % switched)
    RESULTS.append("    100 to 140 BPM at 14 s: followed at %.1f s" % switched)


def t_bandsAndCentroid():
    seen = {}
    for freq, band in ((80, "low"), (1000, "mid"), (8000, "high")):
        f = au.Analyzer().analyze(tone(freq, 3))[-1]
        check(f[band] > 0.9 and all(f[b] < 0.2 for b in ("low", "mid", "high") if b != band),
              "%d Hz should be all %s: %s" % (freq, band, {b: f[b] for b in ("low", "mid", "high")}))
        seen[freq] = f["centroid"]
    check(seen[80] < seen[1000] < seen[8000], "the centroid rises with frequency: %s" % seen)


def t_silenceAndGaps():
    """True silence reads as 0 and stops the beat clock; the gaps between drum hits don't."""
    fs = au.Analyzer().analyze(np.concatenate((kickHats(120, 8), np.zeros(SR * 4))))
    hop = au.HOP / SR
    music = fs[int(1.0 / hop):int(7.5 / hop)]
    check(not any(f["silent"] for f in music), "gaps between hits were taken for silence")
    end = fs[int(10 / hop):]
    check(all(f["silent"] and f["level"] == 0 for f in end), "silence reads as silent, level 0")
    check(len({f["beat"] for f in end}) == 1, "the beat clock stops in silence")


def t_levelIsRelative():
    """Level uses the whole range for quiet and loud material alike, and a drop reads low."""
    quiet = au.Analyzer().analyze(gated(noise(6, 0.01), 2))
    loud = au.Analyzer().analyze(gated(noise(6, 0.8), 2))
    peakQ = max(f["level"] for f in quiet[100:])
    peakL = max(f["level"] for f in loud[100:])
    check(peakQ > 0.9 and peakL > 0.9, "peaks read near 1 at -40 dB and -2 dB: %.2f, %.2f" % (peakQ, peakL))
    fs = au.Analyzer().analyze(np.concatenate((noise(4, 0.8), noise(2, 0.05))))
    # 24 dB under a peak that has been decaying for 2 s (about 4 dB): about a third of the range
    check(fs[-1]["level"] < 0.4, "24 dB quieter reads low: %.2f" % fs[-1]["level"])


# ------------------------------------------------------------------ sound modes

ROLES = {"key": [0], "fill": [1], "rim": [2], "background": [3], "practical": [], "all": [0, 1, 2, 3]}


def resolve(target):
    out = []
    for part in str(target).split(";"):
        for i in ROLES.get(part.strip().lstrip("@").split(".")[0], []):
            if i not in out:
                out.append(i)
    return out


def shippedModes():
    modes = []
    for path in sorted(glob.glob(os.path.join(ROOT, "light_prefs", "sound_modes", "*.json"))):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        mode, errors, _ = show.parseSoundMode(data)
        check(mode is not None, "%s: %s" % (os.path.basename(path), errors))
        modes.append(mode)
    return modes


def play(mode, features):
    """Run a SoundPlayer over a list of per-hop features on a virtual clock; returns each
    light's distinct commands as (seconds, command)."""
    hopMs = 1000.0 * au.HOP / SR
    cur = [None]
    player = show.SoundPlayer(mode, resolve, lambda: cur[0])
    player.start(0.0)
    samples, t, fi = {}, 0.0, 0
    while t < len(features) * hopMs:
        while fi < len(features) - 1 and (fi + 1) * hopMs <= t:
            fi += 1
        cur[0] = features[fi]
        out, finished = player.frame(t)
        check(not finished, "a sound mode never finishes")
        for idx, cmd in out.items():
            s = samples.setdefault(idx, [])
            if not s or s[-1][1] != cmd:
                s.append((t / 1000.0, cmd))
        t = player.nextChange(t)
    return samples


def t_shippedModesValid():
    names = [m.name for m in shippedModes()]
    check(names == ["Bands", "Beat Chase", "Colour Drift", "Pulse", "Warm Glow"], "shipped modes: %s" % names)


def t_shippedModesUnderFlashLimit():
    """Every shipped mode stays at or under 2 flashes a second on every light with the guard
    off, judged on its colours and again as if every light were white (a CCT-only light
    shows colours as white, a bigger luminance swing)."""
    worst, worstAt = 0.0, ""
    feats = {name: au.Analyzer().analyze(x) for name, x in worstCases().items()}
    for mode in shippedModes():
        for name, fs in feats.items():
            for idx, s in play(mode, fs).items():
                r = show.analyzeFlashes(s)
                white = show.analyzeFlashes([(t, {"mode": "CCT", "temp": 56, "bri": c["bri"]}) for t, c in s])
                rate = max(r["flashes"], r["red"], white["flashes"])
                if rate > worst:
                    worst, worstAt = rate, "%s, %s, light %d" % (mode.name, name, idx + 1)
                check(rate <= show.SOUND_FLASH_LIMIT, "%s on %s: light %d flashes %.1f a second" % (mode.name, name, idx + 1, rate))
    RESULTS.append("    5 modes x %d worst-case signals: at most %.1f flashes a second (%s)" % (len(feats), worst, worstAt))


def t_modesMoveWithTheMusic():
    """The limiter doesn't freeze them: on a drum pattern every driven light swings through at
    least 30% of its part's brightness range."""
    fs = au.Analyzer().analyze(kickHats(124, 12))
    for mode in shippedModes():
        ranges = {}
        for part in mode.parts:
            lo = mode.floor if part["floor"] is None else part["floor"]
            hi = mode.ceiling if part["ceiling"] is None else part["ceiling"]
            for idx in resolve(part["target"]):
                ranges[idx] = hi - lo
        for idx, s in play(mode, fs).items():
            bris = [c["bri"] for t, c in s if t > 3]
            check(max(bris) - min(bris) >= 0.3 * ranges[idx], "%s: light %d barely moves (%s to %s of a %d-point range)"
                  % (mode.name, idx + 1, min(bris), max(bris), ranges[idx]))


def t_modesAimAtRoles():
    """Key never driven by a shipped mode; Bands puts highs on the fill as asked."""
    fs = au.Analyzer().analyze(kickHats(124, 6))
    for mode in shippedModes():
        lights = set(play(mode, fs))
        check(0 not in lights, "%s drives the key light" % mode.name)
        check(lights >= {2, 3}, "%s drives the rim and background: %s" % (mode.name, sorted(lights)))
        if mode.name == "Bands":
            check(1 in lights, "Bands drives the fill (highs)")


def t_beatChase():
    """Beat Chase steps through its lights in turn on the beat, every other beat above 150 BPM."""
    mode = [m for m in shippedModes() if m.name == "Beat Chase"][0]
    for bpm, expectSteps in ((120, 1), (170, 2)):
        x, _ = clicks(bpm, 16)
        fs = au.Analyzer().analyze(x)
        s = play(mode, fs)
        brightest = []
        for t in np.arange(8, 15, 0.02):
            row = {i: [c for tt, c in s[i] if tt <= t][-1]["bri"] for i in (2, 3)}
            top = max(row, key=row.get)
            if not brightest or brightest[-1][1] != top:
                brightest.append((t, top))
        gaps = np.diff([t for t, _ in brightest])
        check(len(brightest) >= 4, "%d BPM: the chase moved %d times in 7 s" % (bpm, len(brightest)))
        stepS = expectSteps * 60.0 / bpm
        check(abs(float(np.median(gaps)) - stepS) < 0.06, "%d BPM: steps %.2f s apart, expected %.2f" % (bpm, float(np.median(gaps)), stepS))


def t_warmGlowIsWhiteOnly():
    mode = [m for m in shippedModes() if m.name == "Warm Glow"][0]
    for idx, s in play(mode, au.Analyzer().analyze(kickHats(110, 6))).items():
        temps = {c["temp"] for _, c in s}
        check(all(c["mode"] == "CCT" for _, c in s) and min(temps) >= 29 and max(temps) <= 43,
              "Warm Glow sends colour temperatures 2900 to 4300 K: %s" % sorted(temps))


def t_silenceSettlesAtTheFloor():
    mode = [m for m in shippedModes() if m.name == "Pulse"][0]
    s = play(mode, au.Analyzer().analyze(np.concatenate((kickHats(120, 4), np.zeros(SR * 5)))))
    for idx in s:
        check(s[idx][-1][1]["bri"] == mode.floor, "light %d settles at the floor in silence: %s" % (idx + 1, s[idx][-1]))


def t_modeValidation():
    base = {"format": 1, "name": "X", "palette": [{"hue": 10, "sat": 90}], "parts": [{"target": "@rim", "drive": "level", "colour": 0}]}
    ok, errors, _ = show.parseSoundMode(base)
    check(ok is not None, errors)
    cases = [({"palette": [{"hue": 10}, {"temp": 3200}]}, "mix"),
             ({"parts": [{"target": "@rim", "colour": 3}]}, "not in the palette"),
             ({"floor": 80, "ceiling": 20}, "floor can't be above ceiling"),
             ({"parts": [{"target": "@rim", "drive": "loud"}]}, "drive must be one of"),
             ({"parts": []}, "parts must be a non-empty list"),
             ({"sensitivity": 9}, "sensitivity must be"),
             ({"name": ""}, "needs a name"),
             ({"parts": [{"drive": "level"}]}, "needs a target")]
    for change, expect in cases:
        data = dict(base)
        data.update(change)
        mode, errors, _ = show.parseSoundMode(data)
        check(mode is None and any(expect in e for e in errors), "%s: expected %r in %s" % (change, expect, errors))
    _, _, warns = show.parseSoundMode(dict(base, parts=[{"target": "@practical"}]), resolveTarget=resolve)
    check(warns and "matches no light" in warns[0], "a target matching nothing warns: %s" % warns)
    changed, errors = show.soundModeWithParams(ok, {"sensitivity": 2.5, "ceiling": 50})
    check(changed is not None and changed.sensitivity == 2.5 and changed.ceiling == 50, errors)
    bad, errors = show.soundModeWithParams(ok, {"parts": []})
    check(bad is None and "can't change parts" in errors[0], errors)


def t_docExamplesValidate():
    """Every JSON example in docs/SOUND_MODES.md that looks like a mode is valid."""
    text = open(os.path.join(ROOT, "docs", "SOUND_MODES.md"), encoding="utf-8").read()
    blocks = [b.split("```", 1)[0] for b in text.split("```json")[1:]]
    count = 0
    for b in blocks:
        data = json.loads(b)
        if isinstance(data, dict) and "parts" in data:
            mode, errors, _ = show.parseSoundMode(data)
            check(mode is not None, "docs example %s: %s" % (data.get("name"), errors))
            count += 1
    check(count >= 2, "docs examples checked: %d" % count)


TESTS = [t_tempoOfClickTracks, t_tempoOfDrumPattern, t_tempoChange, t_bandsAndCentroid, t_silenceAndGaps,
         t_levelIsRelative, t_shippedModesValid, t_shippedModesUnderFlashLimit, t_modesMoveWithTheMusic,
         t_modesAimAtRoles, t_beatChase, t_warmGlowIsWhiteOnly, t_silenceSettlesAtTheFloor, t_modeValidation,
         t_docExamplesValidate]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print("PASS", t.__name__)
        except Exception as e:
            failed += 1
            print("FAIL", t.__name__, "-", e)
            if not isinstance(e, AssertionError):
                traceback.print_exc()
        for line in RESULTS:
            print(line)
        RESULTS.clear()
    print("audio tests:", len(TESTS) - failed, "passed,", failed, "failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
