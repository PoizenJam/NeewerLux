"""Offline tests for sound modes: the analysis (tempo, beats, bands, silence) fed with synthetic
signals, the shipped sound modes against worst-case signals with the flash guard off, and the
mode file checks. No sound card needed. Run: python tests/test_audio.py
Skips (and passes) when numpy, part of the optional audio group, isn't installed."""
import glob
import json
import math
import os
import sys
import time
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
    """Every shipped mode is valid (shippedModes checks), the first five are still there, there
    is plenty of choice, and every mode is tagged with an energy and a feel for draft styles."""
    modes = shippedModes()
    names = [m.name for m in modes]
    check({"Bands", "Beat Chase", "Colour Drift", "Pulse", "Warm Glow"} <= set(names) and len(names) >= 50, "shipped modes: %s" % names)
    for m in modes:
        check(len([t for t in m.tags if t in ("calm", "lively", "intense")]) == 1 and
              len([t for t in m.tags if t in ("smooth", "punchy", "hard")]) == 1, "%s: one energy and one feel tag: %s" % (m.name, m.tags))
    bad = show.parseSoundMode({"name": "x", "parts": [{"target": "@rim"}], "tags": "loud"})[1]
    check(any("tags" in e for e in bad), "tags must be a list: %s" % bad)


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
    RESULTS.append("    %d modes x %d worst-case signals: at most %.1f flashes a second (%s)" % (len(shippedModes()), len(feats), worst, worstAt))


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


def t_hardModesSnap():
    """Smoothing 0 is a hard cut: Hard Chase lights each step at its ceiling and drops it
    straight to its floor, with nothing in between (Robert saw lights not reaching black)."""
    mode = next(m for m in shippedModes() if m.name == "Hard Chase")
    saved = dict(ROLES)
    ROLES.update({"practical": [4]})
    try:
        s = play(mode, au.Analyzer().analyze(kickHats(128, 12)))
    finally:
        ROLES.clear(); ROLES.update(saved)
    for idx, seq in s.items():
        values = {c["bri"] for t, c in seq if t > 3}
        check(values == {0, 100}, "light %d: only fully off or fully on: %s" % (idx + 1, sorted(values)))


def t_beatBlinkPaced():
    """Beat-driven lights flash on every beat up to 120 BPM and on every other beat above it,
    evenly, so the 2-a-second limit never has to hold a flash back."""
    mode = next(m for m in shippedModes() if m.name == "Beat Blink")
    for bpm, every in ((100, 1), (128, 2)):
        fs = au.Analyzer().analyze(clicks(bpm, 12)[0])
        beats = len([b for b in beatTimes(fs) if 3 < b < 11.5])
        seq = [(t, c["bri"]) for t, c in play(mode, fs)[2] if 3 < t < 11.5]
        rises = [t for (t0, a), (t, b) in zip(seq, seq[1:]) if a == 0 and b > 0]
        gaps = [b - a for a, b in zip(rises, rises[1:])]
        check(abs(len(rises) - beats / every) <= 1.5 and gaps and max(gaps) - min(gaps) < 0.15,
              "%d BPM: a flash every %d beat(s): %d flashes for %d beats, gaps %s" % (bpm, every, len(rises), beats, [round(g, 2) for g in gaps]))


def t_brightnessCurve():
    """curve spends more of the movement at the dim end: the same music sits lower with 2 than
    with 1; it must be 1 to 3."""
    base = next(m for m in shippedModes() if m.name == "Pulse")
    fs = au.Analyzer().analyze(kickHats(128, 8))
    mean = {}
    for curve in (1.0, 2.0):
        m, errors = show.soundModeWithParams(base, {"curve": curve})
        check(m is not None, str(errors))
        vals = [c["bri"] for t, c in play(m, fs)[3] if t > 2]
        mean[curve] = sum(vals) / len(vals)
    check(mean[2.0] < mean[1.0] - 5, "lower with curve 2: %s" % mean)
    check(show.soundModeWithParams(base, {"curve": 4})[0] is None, "curve over 3 is refused")


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
             ({"range_db": 3}, "range_db must be"),
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
    check(bad is None and any("parts must be a non-empty list" in e for e in errors), errors)
    bad, errors = show.soundModeWithParams(ok, {"name": "Other"})
    check(bad is None and "can't change name" in errors[0], errors)
    wide, _ = show.soundModeWithParams(ok, {"range_db": 30})
    check(wide.rangeDb == 30 and ok.rangeDb == 18, "range_db defaults to 18 and can be set")


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


def t_colourCycle():
    """Colour "cycle" goes round the palette (back to its first colour) over cycle_s, blending
    between colours; one colour goes once round the colour wheel; it can't be set faster than
    4 s or a second per colour."""
    base = {"name": "Cycle", "floor": 50, "ceiling": 50, "parts": [{"target": "@rim", "drive": "level", "colour": "cycle"}]}
    mode, errors, _ = show.parseSoundMode(dict(base, palette=[{"hue": 0, "sat": 100}, {"hue": 120, "sat": 100}, {"hue": 240, "sat": 100}], cycle_s=6))
    check(mode is not None, str(errors))
    player = show.SoundPlayer(mode, resolve, lambda: {"level": 0.5})
    player.start(1000.0)
    hues = {}
    for ms in range(0, 6001, 50):
        out, _ = player.frame(1000.0 + ms)
        hues[ms] = out[2]["hue"]
    check(hues[0] == 0 and hues[2000] == 120 and hues[4000] == 240 and hues[6000] == 0, "palette colours on time: %s" % [hues[k] for k in (0, 2000, 4000, 6000)])
    check(hues[1000] == 60 and hues[5000] == 300, "blending between them (the short way round): %d, %d" % (hues[1000], hues[5000]))
    steps = [abs((hues[k + 50] - hues[k] + 540) % 360 - 180) for k in range(0, 6000, 50)]
    check(max(steps) <= 4, "a smooth drift, at most %d degrees a frame" % max(steps))
    one, errors, _ = show.parseSoundMode(dict(base, palette=[{"hue": 200, "sat": 70}], cycle_s=8))
    player = show.SoundPlayer(one, resolve, lambda: {"level": 0.5})
    player.start(0.0)
    seen = [player.frame(float(ms))[0][2] for ms in (0, 2000, 4000)]
    check([c["hue"] for c in seen] == [200, 290, 20] and all(c["sat"] == 70 for c in seen), "one colour goes round the wheel: %s" % seen)
    white, errors, _ = show.parseSoundMode(dict(base, palette=[{"temp": 3200}]))
    player = show.SoundPlayer(white, resolve, lambda: {"level": 0.5})
    player.start(0.0)
    check({player.frame(float(ms))[0][2]["temp"] for ms in (0, 5000, 9000)} == {32}, "one white stays put")
    check(mode.cycleS == 6 and white.cycleS == 20, "default 20 s")
    for pal, cyc, ok in (([{"hue": 0}], 3, False), ([{"hue": 0}], 4, True), ([{"hue": h} for h in range(0, 360, 60)], 5, False),
                         ([{"hue": h} for h in range(0, 360, 60)], 6, True)):
        m, errors, _ = show.parseSoundMode(dict(base, palette=pal, cycle_s=cyc))
        check((m is not None) == ok, "%d colours, cycle_s %s: %s" % (len(pal), cyc, errors))
    many, _, _ = show.parseSoundMode(dict(base, palette=[{"hue": h} for h in range(0, 360, 12)]))
    check(many.cycleS == 30, "the default stretches to a second a colour: %s" % many.cycleS)


def t_voices():
    """Several modes at once on different lights: assign moves lights between modes, release
    takes them out (the player reports when none are left), and each mode drives only its own."""
    pulse = show.parseSoundMode({"name": "A", "floor": 10, "ceiling": 10, "palette": [{"hue": 10, "sat": 100}],
                                 "parts": [{"target": "@rim;@background", "drive": "level", "colour": 0}]})[0]
    other = show.parseSoundMode({"name": "B", "floor": 90, "ceiling": 90, "palette": [{"hue": 200, "sat": 100}],
                                 "parts": [{"target": "@key", "drive": "level", "colour": 0},
                                           {"target": "@rim", "drive": "high", "colour": 0, "floor": 40, "ceiling": 40}]})[0]
    player = show.SoundPlayer(pulse, resolve, lambda: {"level": 0.5, "high": 0.5})
    player.start(0.0)
    check(sorted(player.lights()) == [2, 3] and player.name == "A", "the mode's own targets")
    player.assign(other, [2, 1])
    out, _ = player.frame(0.0)
    check(out[3]["hue"] == 10 and out[2]["hue"] == 200 and out[1]["hue"] == 200, "lights follow their mode: %s" % out)
    check(out[2]["bri"] == 40 and out[1]["bri"] == 90, "each assigned light follows the part naming it, else the first: %s" % out)
    check(player.name == "B" and player.assignments() == [{"mode": "A", "lights": None}, {"mode": "B", "lights": [1, 2]}], str(player.assignments()))
    player.assign(pulse, [1])
    check(player.assignments()[-1] == {"mode": "A", "lights": [1]} and player.voices[1].lights == [2], str(player.assignments()))
    check(not player.release([2, 3]) and sorted(player.lights()) == [1], "release some")
    check(player.release([1]) and player.lights() == [], "release the last")
    player.assign(other)
    check(player.assignments() == [{"mode": "B", "lights": None}], "no lights: replaces every assignment")


def t_retryNow():
    """Refresh tries a failed device again at once instead of at the next 2 s retry."""
    import time
    fails = [1]
    def factory(device):
        if fails[0]:
            fails[0] = 0
            raise OSError("device unplugged")
        return au.ArraySource(np.zeros(SR), name="back")
    engine = au.AudioEngine(factory)
    engine.start("")
    end = time.monotonic() + 3
    while not engine.error:
        check(time.monotonic() < end, "the failure is reported")
        time.sleep(0.01)
    t0 = time.monotonic()
    engine.retry()
    while engine.features() is None:
        check(time.monotonic() < t0 + 1.5, "retry() reopens it well before the 2 s retry")
        time.sleep(0.01)
    check(engine.deviceName == "back" and not engine.error, "recovered")
    engine.stop()


def t_silenceMeansFloor():
    """When the sound stops (silent blocks, or the device delivering nothing), every shipped
    mode's lights settle exactly on their floor, the lit light of a chase included."""
    rng = np.random.default_rng(3)
    t = np.arange(int(6 * SR)) / SR
    music = 0.3 * np.sin(2 * np.pi * 110 * t) + 0.6 * ((t % 0.5) < 0.05) * rng.standard_normal(len(t))
    for name in ("Pulse", "Bands", "Beat Chase", "Colour Drift", "Warm Glow"):
        with open(os.path.join(ROOT, "light_prefs", "sound_modes", name + ".json"), encoding="utf-8") as f:
            mode = show.parseSoundMode(json.load(f))[0]
        floors = {}
        for pi, part in enumerate(mode.parts):
            for idx in resolve(part["target"]):
                floors[idx] = mode.floor if part["floor"] is None else part["floor"]
        for kind in ("silent blocks", "no data"):
            an = au.Analyzer(SR)
            latest = {"f": None}
            player = show.SoundPlayer(mode, resolve, lambda: latest["f"])
            player.start(0.0)
            hopMs = au.HOP / SR * 1000.0
            ms, pos, nextFrame, out = 0.0, 0, 0.0, {}
            while ms < 16000:
                if ms < 6000:
                    latest["f"] = an.process(music[pos:pos + au.HOP]); pos += au.HOP
                else:
                    latest["f"] = an.process(np.zeros(au.HOP)) if kind == "silent blocks" else None
                ms += hopMs
                while nextFrame <= ms:
                    out, _ = player.frame(nextFrame)
                    nextFrame += player.frameMs
            got = {idx: c["bri"] for idx, c in out.items()}
            check(got == floors, "%s, %s: 10 s after the sound stops %s, floors %s" % (name, kind, got, floors))


def _syntheticSong(sr=44100, bpm=126.0, offset=0.3, plan=(("intro", 8), ("verse", 16), ("chorus", 16), ("break", 8), ("chorus", 16), ("outro", 8))):
    """A song with a known tempo, first beat and sections: kicks (accented on each bar's first
    beat), bass, hats and a pad at different levels per section."""
    rng = np.random.default_rng(7)
    beat = 60.0 / bpm
    total = offset + sum(b for _, b in plan) * 4 * beat + 1.0
    t = np.arange(int(total * sr)) / sr
    x = np.zeros(len(t))
    kickLen = int(0.12 * sr)
    kt = np.arange(kickLen) / sr
    kick = np.sin(2 * np.pi * (50 + 80 * np.exp(-kt * 30)) * kt) * np.exp(-kt * 25)
    hatLen = int(0.03 * sr)
    hat = rng.standard_normal(hatLen) * np.exp(-np.arange(hatLen) / sr * 150)
    look = {"intro": (0.0, 0.0, 0.0, 0.05), "verse": (0.5, 0.15, 0.0, 0.05), "chorus": (0.9, 0.25, 0.25, 0.08),
            "break": (0.0, 0.0, 0.0, 0.12), "outro": (0.15, 0.0, 0.0, 0.03), "build": (0.5, 0.15, 0.0, 0.05)}
    bounds, pos = [], offset
    for name, bars in plan:
        kickAmp, bassAmp, hatAmp, padAmp = look[name]
        start, end = pos, pos + bars * 4 * beat
        bounds.append(start)
        seg = (t >= start) & (t < end)
        x[seg] += padAmp * (np.sin(2 * np.pi * 220 * t[seg]) + np.sin(2 * np.pi * 277 * t[seg]))
        x[seg] += bassAmp * np.sin(2 * np.pi * 55 * t[seg])
        if name == "build":
            # a noise riser over the verse loop: louder and brighter towards the end
            ramp = ((t[seg] - start) / (end - start)) ** 2
            noise = rng.standard_normal(int(np.sum(seg)))
            x[seg] += 0.35 * ramp * np.diff(noise, prepend=0.0)
        for k in range(bars * 4):
            at = int((start + k * beat) * sr)
            if kickAmp:
                x[at:at + kickLen] += kick[:len(x[at:at + kickLen])] * kickAmp * (1.0 if k % 4 == 0 else 0.6)
            if hatAmp:
                h = int((start + (k + 0.5) * beat) * sr)
                x[h:h + hatLen] += hat[:len(x[h:h + hatLen])] * hatAmp
        pos = end
    return x * 0.5, sr, [int(round(b * 1000)) for b in bounds[1:]]


def t_songAnalysis():
    """A whole song: tempo and first beat, bars on the accented beat, sections at the changes
    with sensible levels, energy and waveform shapes; given tempo and offset are used."""
    x, sr, bounds = _syntheticSong()
    a = au.analyzeSong(x, sr)
    check(abs(a["bpm"] - 126.0) < 0.15, "tempo %s" % a["bpm"])
    period = 60000.0 / 126.0
    off = (a["offset_ms"] - 300.0 + period / 2) % period - period / 2
    check(abs(off) < 15, "first beat %s ms (300 expected)" % a["offset_ms"])
    check(a["confidence"] >= 0.8, "confidence %s" % a["confidence"])
    check(abs(a["duration_ms"] - len(x) * 1000 / sr) <= 1 and a["beats"][1] - a["beats"][0] in (476, 477), "beats every %d ms" % (a["beats"][1] - a["beats"][0]))
    barOff = (a["bars"][0] - 300.0) % (4 * period)
    check(min(barOff, 4 * period - barOff) < 20, "bars start on the accented beat: %s" % a["bars"][:3])
    starts = [s["start_ms"] for s in a["sections"][1:]]
    for b in bounds:
        check(any(abs(s - b) <= period * 4 + 5 for s in starts), "a section starts near %d ms: %s" % (b, starts))
    check(len(starts) <= len(bounds) + 2, "not many more sections than changes: %s" % starts)
    def levelAt(ms):
        return next(s["level"] for s in a["sections"] if s["start_ms"] <= ms < s["end_ms"])
    chorus, quiet = bounds[1] + 8 * 4 * period, bounds[2] + 4 * 4 * period  # middle of the first chorus, of the break
    check(levelAt(chorus) == 3 and levelAt(quiet) <= 2 and levelAt(1000) == 1,
          "levels: chorus %d, drumless break %d, intro %d" % (levelAt(chorus), levelAt(quiet), levelAt(1000)))
    def labelAt(ms):
        return next(s["label"] for s in a["sections"] if s["start_ms"] <= ms < s["end_ms"])
    middle = lambda i: (bounds[i - 1] if i else 0) + ((bounds[i] if i < len(bounds) else a["duration_ms"]) - (bounds[i - 1] if i else 0)) / 2
    labels = [labelAt(middle(i)) for i in range(6)]
    check(labels == ["Intro", "Groove", "Drop", "Breakdown", "Drop", "Outro"], "named by what changes: %s" % labels)
    groupAt = lambda ms: next(s["group"] for s in a["sections"] if s["start_ms"] <= ms < s["end_ms"])
    check(groupAt(middle(2)) == groupAt(middle(4)) and a["sections"][0]["group"] == "A" and groupAt(middle(3)) != groupAt(middle(2)),
          "repeats share a group: %s" % [(s["label"], s["group"]) for s in a["sections"]])
    check(all(s["label"] in au.SECTION_LABELS for s in a["sections"]), "only the documented names")
    check(all(0 <= v <= 1 for v in a["energy"]) and len(a["energy"]) == math.ceil(a["duration_ms"] / 250) or
          abs(len(a["energy"]) - a["duration_ms"] / 250) <= 1, "energy every 250 ms")
    check(len(a["waveform"]) == au.SONG_WAVEFORM_POINTS and max(a["waveform"]) == 1.0, "waveform")
    fixed = au.analyzeSong(x, sr, bpm=63, offsetMs=1234)
    check(fixed["bpm"] == 63 and fixed["offset_ms"] == 1234 % round(60000 / 63) and fixed["confidence"] is None, "given tempo and offset are kept: %s %s" % (fixed["bpm"], fixed["offset_ms"]))


def t_songRiser():
    """A riser over the end of a verse loop, before the chorus, is a Build of its own."""
    x, sr, bounds = _syntheticSong(plan=(("intro", 8), ("verse", 16), ("build", 8), ("chorus", 16), ("outro", 8)))
    a = au.analyzeSong(x, sr)
    mid = (bounds[1] + bounds[2]) / 2
    sec = next(s for s in a["sections"] if s["start_ms"] <= mid < s["end_ms"])
    check(sec["label"] == "Build", "the riser is a Build: %s" % [(s["start_ms"], s["label"]) for s in a["sections"]])
    verse = next(s for s in a["sections"] if s["start_ms"] <= bounds[0] + 2000 < s["end_ms"])
    check(verse["label"] != "Build", "the verse before it is not")


FAKE_FINDER = r"""
import json, os, sys, time
song, out, how = sys.argv[1], sys.argv[2], sys.argv[3]
assert os.path.isfile(song), song
if how == "slow":
    time.sleep(5)
if how == "fail":
    print("model not found", file=sys.stderr)
    sys.exit(3)
segs = [{"start": 0.0, "end": 16.0, "label": "intro"}, {"start": 16.0, "end": 47.0, "label": "verse"},
        {"start": 47.0, "end": 76.0, "label": "chorus"}, {"start": 76.0, "end": 200.0, "label": "outro"}]
if how == "stdout":
    print(json.dumps(segs))
elif how == "file":
    os.makedirs(os.path.join(out, "struct"))
    with open(os.path.join(out, "struct", os.path.splitext(os.path.basename(song))[0] + ".json"), "w") as f:
        json.dump({"path": song, "bpm": 126, "segments": segs}, f)
else:
    print("nothing useful")
"""


def finderCommand(script, how):
    return '"%s" "%s" "{song}" "{out}" %s' % (sys.executable, script, how)


def t_externalSections():
    """Another section finder: run without a shell (a song path with spaces and quotes arrives
    as one argument), its segments read from its output or a file it writes, its failures
    reported; analyzeSong puts sections on the bar nearest its boundaries and keeps its labels."""
    import tempfile
    import soundfile
    x, sr, bounds = _syntheticSong()
    with tempfile.TemporaryDirectory() as d:
        script = os.path.join(d, "finder.py")
        with open(script, "w") as f:
            f.write(FAKE_FINDER)
        song = os.path.join(d, "it's a \"song\" & more.wav" if os.name != "nt" else "it's a song & more.wav")
        soundfile.write(song, x, sr)
        for how in ("stdout", "file"):
            segs, why = au.externalSections(finderCommand(script, how), song)
            check(segs and why == "" and [s["start_ms"] for s in segs] == [0, 16000, 47000, 76000] and segs[2]["label"] == "chorus",
                  "%s: %s %s" % (how, segs, why))
        segs, why = au.externalSections(finderCommand(script, "fail"), song)
        check(segs is None and "exit code 3" in why and "model not found" in why, why)
        segs, why = au.externalSections(finderCommand(script, "nothing"), song)
        check(segs is None and "no segments" in why, why)
        segs, why = au.externalSections(finderCommand(script, "slow"), song, timeoutS=1)
        check(segs is None and "longer than 1 s" in why, why)
        segs, why = au.externalSections('"no such program here" "{song}"', song)
        check(segs is None and "no program" in why, why)
        segs = au.externalSections(finderCommand(script, "file"), song)[0]
    a = au.analyzeSong(x, sr, segments=segs)
    period = 60000.0 / 126.0
    starts = [s["start_ms"] for s in a["sections"]]
    check(len(starts) >= 4 and all(any(abs(s - b) <= 4 * period for s in starts) for b in (16000, 47000, 76000)),
          "sections start on the bars nearest the finder's boundaries: %s" % starts)
    mid = lambda ms: next(s for s in a["sections"] if s["start_ms"] <= ms < s["end_ms"])
    check(mid(60000)["ai_label"] == "chorus" and mid(30000)["ai_label"] == "verse" and all(s["label"] in au.SECTION_LABELS for s in a["sections"]),
          "its labels kept as ai_label, ours as label: %s" % [(s["label"], s["ai_label"]) for s in a["sections"]])


def t_songFiles():
    """Song files decode (WAV, FLAC and MP3 where libsndfile can write it for the test)."""
    import tempfile
    import soundfile
    x, sr, _ = _syntheticSong(plan=(("chorus", 8),))
    with tempfile.TemporaryDirectory() as d:
        for ext, fmt in ((".wav", "WAV"), (".flac", "FLAC"), (".mp3", "MP3")):
            path = os.path.join(d, "song" + ext)
            try:
                soundfile.write(path, np.column_stack([x, x]), sr, format=fmt)
            except Exception:
                check(ext == ".mp3", "writing %s" % ext)
                continue
            y, ysr = au.loadSong(path)
            check(ysr == sr and abs(len(y) - len(x)) < sr, "%s decodes" % ext)
            check(abs(au.analyzeSong(y, ysr)["bpm"] - 126.0) < 0.3, "%s analyses" % ext)
    check(au.songAvailable() == (True, ""), "song import available here")


def t_beatScorer():
    """tests/beat_score.py scores what it should: beats fired on the true grid score 100% with
    nothing false, beats fired half a beat late score nothing and are all false, and its song
    mode takes the reference grid from the song analysis."""
    import beat_score
    _, truth = beat_score.render(beat_score.CASES["clicks120"])
    def fake(times):
        out, n = [], 0
        for k in range(int(truth[-1][0] / 0.01) + 50):
            t = k * 0.01
            while n < len(times) and times[n] <= t:
                n += 1
            out.append({"t": t, "beat": n, "bpm": 120.0})
        return out
    exact = beat_score.score(fake([b[0] for b in truth]), truth)
    check(exact["hit"] == 1.0 and exact["false_per_min"] == 0 and exact["tempo_ok"] == 1.0, "on the grid: %s" % exact)
    check(abs(exact["lock_s"] - truth[3][0]) < 1e-9, "locked on the 4th beat: %s" % exact["lock_s"])
    late = beat_score.score(fake([b[0] + 0.25 for b in truth]), truth)
    check(late["lock_s"] is None and late["false_per_min"] > 100, "half a beat late: %s" % late)
    import tempfile
    import soundfile
    x, sr, _ = _syntheticSong(plan=(("chorus", 16),))
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "steady.wav")
        soundfile.write(path, x, sr)
        song = beat_score.runSong(path)
    check(abs(song["reference_bpm"] - 126.0) < 0.3, "song reference tempo %s" % song["reference_bpm"])


def t_beatTracking():
    """The live beat tracker on tests/beat_score.py's cases, with room below what it scores
    today. Phase comes from the kick, so an off-beat bass, a dotted riff or 2-step don't pull it
    off the beat; a trusted tempo holds through a breakdown with no drums and a short stop;
    beats land within a few ms of the sound, not 30 to 50 ms late."""
    import beat_score
    need = {"clicks120": 0.95, "house": 0.95, "riff": 0.95, "breakdown": 0.95, "garage": 0.85,
            "jump": 0.75, "ramp": 0.6, "roll": 0.95, "quiet": 0.9, "sparse_intro": 0.9}
    lines = []
    for name, least in need.items():
        r = beat_score.runCase(name)
        check(r["hit"] is not None and r["hit"] >= least, "%s: %s of beats hit, want %d%% (%s)" % (name, r["hit"], least * 100, r))
        lines.append("%s %d%%" % (name, round(r["hit"] * 100)))
        if name in ("clicks120", "house", "riff", "breakdown"):
            check(abs(r["offset_ms"]) <= 20, "%s: beats %s ms off the sound" % (name, r["offset_ms"]))
    br = beat_score.runCase("breakdown")
    check(br["segments"][1]["hit"] >= 0.9, "the beat holds through 32 bars of pads: %s" % br["segments"])
    # half-time reads at half speed: fine for lights, which flash every other beat above 120 anyway
    half = beat_score.runCase("halftime")
    check(half["tempo_ok"] + half["related"].get("x1/2", 0) >= 0.95, "half-time: %s" % half)
    RESULTS.append("    beats hit: " + ", ".join(lines))


def t_beatsStopInLongSilence():
    """Through a stop of a few seconds the clock keeps time without firing beats (sound modes
    sit at their floor), and the first beat after it is on time."""
    import beat_score
    x, truth = beat_score.render(beat_score.CASES["quiet"])
    fs = au.Analyzer().analyze(x)
    fired = beat_score.firedBeats(fs)
    silence = [t for t, _, seg in truth if seg == 1]
    start, end = silence[0], silence[-1] + 60.0 / 128
    inside = [t for t in fired if start + au.BEAT_SILENCE_GRACE_S + 0.1 < t < end - 0.05]
    check(not inside, "beats fired %d s into the silence: %s" % (au.BEAT_SILENCE_GRACE_S, inside))
    after = [t for t, _, seg in truth if seg == 2][:4]
    for t in after:
        check(min(abs(f - t) for f in fired) <= beat_score.TOLERANCE_S, "beat at %.2f s after the stop missed" % t)


def t_tempoRange():
    """A narrower tempo range settles half- and double-speed readings, and the setting checks
    its values. Half-time (kick on 1, snare on 3) reads 70 by default and 140 in 120 to 180;
    drum and bass at 174 reads 87 in 60 to 120. A tempo outside a new range is dropped."""
    import beat_score
    x, _ = beat_score.render(beat_score.CASES["halftime"])
    hop = au.HOP / SR
    def settled(an):
        fs = an.analyze(x)
        return float(np.median([f["bpm"] for f in fs if f["t"] > 12]))
    check(abs(settled(au.Analyzer()) - 70) < 2, "half-time by default: %.1f" % settled(au.Analyzer()))
    check(abs(settled(au.Analyzer(tempoRange=(120, 180))) - 140) < 2, "half-time in 120 to 180")
    d, _ = beat_score.render([beat_score._seg(24, 174, "dnb")])
    got = float(np.median([f["bpm"] for f in au.Analyzer(tempoRange=(60, 120)).analyze(d) if f["t"] > 12]))
    check(abs(got - 87) < 2, "drum and bass in 60 to 120: %.1f" % got)
    check(au.validTempoRange(85, 175) == (85.0, 175.0), "a good range")
    for bad in ((30, 100), (100, 260), (100, 105), ("x", 120), (None, None)):
        check(au.validTempoRange(*bad) is None, "refused %s" % (bad,))
    an = au.Analyzer()
    an.analyze(x[:int(12 * SR)])
    check(abs(an.bpm - 70) < 2, "reads 70 first")
    an.setTempoRange(120, 180)
    check(an.bpm == 0 and an.nextBeat is None, "a tempo outside the new range is dropped")
    RESULTS.append("    half-time %.1f by default, %.1f in 120 to 180; drum and bass %.1f in 60 to 120"
                   % (settled(au.Analyzer()), settled(au.Analyzer(tempoRange=(120, 180))), got))


def t_kickDrive():
    """The analysis counts kick drum hits (not snares or hi-hats), and a part with the Kick drive
    flashes on them: on 2-step's kick on the "and" of 3 as well as on beat 1, never more than
    once in SOUND_KICK_GAP_MS, falling back to the floor between."""
    import beat_score
    segs = beat_score.CASES["garage"]
    x, truth = beat_score.render(segs)
    fs = au.Analyzer().analyze(x)
    kicks = []
    for k, (bt, bpm, _) in enumerate(truth):
        for st, _ in beat_score.PATTERNS["garage"]["kick"]:
            if st // 4 == k % 4:
                kicks.append(bt + (st % 4) * 60.0 / bpm / 4)
    heard, last = [], 0
    for f in fs:
        if f["kick"] != last:
            heard.append(f["t"])
            last = f["kick"]
    found = sum(1 for k in kicks if min(abs(h - k) for h in heard) < 0.06)
    check(found >= 0.9 * len(kicks), "kicks heard: %d of %d" % (found, len(kicks)))
    check(len(heard) <= 1.1 * len(kicks), "%d kicks counted for %d played (snares or hats counted)" % (len(heard), len(kicks)))
    mode, errors, _ = show.parseSoundMode({"name": "K", "floor": 0, "ceiling": 100, "smoothing": 0,
                                            "parts": [{"target": "@rim", "drive": "kick", "colour": 0}]})
    check(mode is not None, "kick drive validates: %s" % errors)
    flashes, lit = [], False
    for t, cmd in play(mode, fs)[ROLES["rim"][0]]:
        if cmd["bri"] >= 90 and not lit:
            flashes.append(t)
        lit = cmd["bri"] >= 90
    check(len(flashes) >= 0.75 * len(kicks), "flashed %d times for %d kicks" % (len(flashes), len(kicks)))
    gaps = np.diff(flashes)
    check(min(gaps) >= show.SOUND_KICK_GAP_MS / 1000.0 - 0.03, "flashes %.0f ms apart" % (min(gaps) * 1000))
    onKick = sum(1 for t in flashes if min(abs(t - k) for k in kicks) < 0.08)
    check(onKick >= 0.9 * len(flashes), "flashes on kicks: %d of %d" % (onKick, len(flashes)))
    RESULTS.append("    2-step: %d of %d kicks heard, %d flashes (all within 80 ms of a kick: %d), at least %.0f ms apart"
                   % (found, len(kicks), len(flashes), onKick, min(gaps) * 1000))


def t_midiClock():
    """MIDI clock: the tempo from 24 pulses a beat (steady through a millisecond of jitter), a
    beat on every 24th pulse, Start counting from its first pulse, Stop holding the count and
    Continue carrying on, Song Position (sixteenths) moving it, nothing when the pulses stop;
    and a MIDI clock, while it arrives, setting the beat sound modes follow in place of the one
    heard."""
    import neewerlux_midi as midi
    rng = np.random.default_rng(4)
    clk = midi.MidiClock(clock=lambda: 0.0)
    t = 0.0
    def pulses(n, bpm):
        nonlocal t
        for _ in range(n):
            clk.feed(midi.CLOCK, t=t + rng.uniform(-0.001, 0.001))
            t += 60.0 / bpm / midi.CLOCKS_PER_BEAT
    pulses(24 * 8, 120)
    check(abs(clk.bpm() - 120) < 0.5, "tempo from pulses: %.2f" % clk.bpm())
    check(clk.beat == 8 and not clk.playing, "a bare clock counts beats: %d" % clk.beat)
    f = clk.features(now=t)
    check(f["bpm"] == round(clk.bpm(), 2) and f["beat"] == 8 and f["confidence"] == 1.0, f)
    check(clk.features(now=t + midi.STALE_S + 0.1) is None, "nothing once the pulses stop")
    check(clk.feed(midi.START, t=t) == "start" and clk.playing, "Start")
    pulses(1, 120)
    check(clk.beat == 9, "Start counts a beat on its first pulse: %d" % clk.beat)
    pulses(24 * 2 - 1, 120)
    check(clk.beat == 10 and clk.position == 8, "two beats after Start: beat %d, position %d" % (clk.beat, clk.position))
    check(clk.feed(midi.STOP, t=t) == "stop" and not clk.playing, "Stop")
    pulses(48, 120)
    check(clk.beat == 10, "no beats while stopped (the clock keeps the tempo): %d" % clk.beat)
    check(clk.feed(midi.SONG_POSITION, 16, 0, t=t) == "position" and clk.position == 16, "Song Position: %d" % clk.position)
    check(clk.feed(midi.CONTINUE, t=t) == "continue" and clk.playing, "Continue")
    pulses(1, 120)
    check(clk.beat == 11, "from a bar line a beat lands on the first pulse: %d" % clk.beat)
    pulses(24 * 8, 140)
    check(abs(clk.bpm() - 140) < 0.5, "a tempo change followed within two beats: %.2f" % clk.bpm())

    class FakeInput:
        def __init__(self, name, onMessage):
            self.name, self.onMessage, self.closed = name, onMessage, False
        def open(self):
            if self.name != "Fake In":
                raise OSError("MIDI input " + repr(self.name) + " isn't connected")
        def close(self):
            self.closed = True
    events = []
    mgr = midi.MidiManager(inputFactory=FakeInput, onTransport=lambda e, c: events.append((e, c.position)))
    check(mgr.start("Missing") and not mgr.connected, "a missing input reports an error")
    check(mgr.start("Fake In") == "" and mgr.connected, "the input opens")
    send = mgr._input.onMessage
    send(midi.SONG_POSITION, 0x10, 0x01)
    send(midi.START, 0, 0)
    mgr.wait()
    check([e for e, _ in events] == ["position", "start"], "transport events, in order: %s" % events)
    first = mgr._input
    mgr.start("")
    check(first.closed and not mgr.connected and mgr.features() is None, "choosing none closes it")

    eng = au.AudioEngine(sourceFactory=lambda dev: au.ArraySource(kickHats(124, 8)))
    eng.start("")
    try:
        end = time.monotonic() + 8
        while time.monotonic() < end and not (eng.features() or {}).get("bpm"):
            time.sleep(0.1)
        heard = eng.features()
        check(heard and abs(heard["bpm"] - 124) < 3, "the sound's own tempo first: %s" % heard)
        eng.beatSource = lambda: {"bpm": 100.0, "beat": 77, "beat_phase": 0.5, "beat_t": 1.0, "confidence": 1.0}
        f = eng.features()
        check(f["bpm"] == 100.0 and f["beat"] == 77 and "level" in f, "MIDI sets the beat, the sound the levels: %s" % f)
        eng.beatSource = lambda: None
        check(abs(eng.features()["bpm"] - 124) < 3, "the sound's tempo again once MIDI stops")
    finally:
        eng.stop()


TESTS = [t_tempoOfClickTracks, t_tempoOfDrumPattern, t_tempoChange, t_bandsAndCentroid, t_silenceAndGaps,
         t_levelIsRelative, t_shippedModesValid, t_shippedModesUnderFlashLimit, t_modesMoveWithTheMusic,
         t_modesAimAtRoles, t_beatChase, t_hardModesSnap, t_beatBlinkPaced, t_brightnessCurve, t_warmGlowIsWhiteOnly, t_silenceSettlesAtTheFloor, t_modeValidation,
         t_docExamplesValidate, t_colourCycle, t_voices, t_retryNow, t_silenceMeansFloor, t_songAnalysis, t_songRiser, t_externalSections, t_songFiles, t_beatScorer, t_beatTracking, t_beatsStopInLongSilence, t_tempoRange, t_kickDrive, t_midiClock]


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
