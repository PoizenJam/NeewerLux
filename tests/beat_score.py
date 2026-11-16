"""Scores the live beat tracker (neewerlux_audio.Analyzer, what sound modes follow) against
known beat times, so changes to it can be measured instead of judged by ear.

Synthetic cases are built here from drum, bass and pad sounds on a known grid, each aimed at
one way live tracking goes wrong: off-beat bass, dotted-eighth riffs, tempo ramps and jumps,
long breakdowns with no kick, half-time, 2-step, drum rolls, a quiet patch, a sparse intro.
A song file can be scored too: its reference grid is the whole-song analysis (tempo and first
beat from analyzeSong, which assumes one tempo), so only use songs with a steady tempo, or
score only the stretch of a song where the reference holds (path@start-end, in seconds).

    python tests/beat_score.py                  all synthetic cases
    python tests/beat_score.py house breakdown  only those cases
    python tests/beat_score.py --song "C:\\Music\\Insomnia.mp3" [--song ...]
    python tests/beat_score.py --song "C:\\Music\\Space Cowboy.mp3@0-90"   only 0 to 90 s
    python tests/beat_score.py --json out.json  also write the numbers

A beat counts as hit when the tracker fires one within TOLERANCE_S of it. Columns:
lock (s until four beats in a row are hit), hit (share of beats hit after lock), false (beats
fired away from any real beat, per minute), offset (median ms the fired beats sit after the
real ones), tempo (share of time the reading is within 3% of the true tempo), and the share of
time it sits at a related tempo instead (x2, x1/2, x3/2, x2/3, x4/3, x3/4).
"""
import argparse
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import numpy as np  # noqa: E402

import neewerlux_audio as au  # noqa: E402

SR = au.SAMPLE_RATE
TOLERANCE_S = 0.07     # about what reads as "on the beat" for a light flash
TEMPO_OK = 0.03
WARMUP_S = 6.0         # tempo readings before this aren't scored (the tracker needs history)
RELATED = (("x2", 2.0), ("x1/2", 0.5), ("x3/2", 1.5), ("x2/3", 2 / 3), ("x4/3", 4 / 3), ("x3/4", 0.75))


# ------------------------------------------------------------------ sounds

def _env(n, decay):
    return np.exp(-np.arange(n) / SR * decay)


_RNG = np.random.default_rng(11)
_T15 = np.arange(int(0.15 * SR)) / SR
KICK = 0.9 * np.sin(2 * np.pi * (50 + 80 * np.exp(-_T15 * 30)) * _T15) * np.exp(-_T15 * 12)
_n = int(0.18 * SR)
SNARE = (0.45 * _RNG.uniform(-1, 1, _n) + 0.3 * np.sin(2 * np.pi * 190 * np.arange(_n) / SR)) * _env(_n, 22)
_n = int(0.12 * SR)
CLAP = 0.4 * _RNG.uniform(-1, 1, _n) * _env(_n, 30)
_n = int(0.04 * SR)
HAT = 0.22 * np.diff(_RNG.uniform(-1, 1, _n + 1)) * _env(_n, 90)
_n = int(0.22 * SR)
_tb = np.arange(_n) / SR
# a short sub-bass note with a hard attack: the low-band onset that can pass for a kick
BASS = 0.7 * np.sin(2 * np.pi * 55 * _tb) * np.minimum(1.0, _tb / 0.004) * _env(_n, 9)
_n = int(0.12 * SR)
_tr = np.arange(_n) / SR
RIFF = 0.35 * np.sign(np.sin(2 * np.pi * 110 * _tr)) * np.minimum(1.0, _tr / 0.003) * _env(_n, 18)
_n = int(0.01 * SR)
CLICK = 0.8 * np.exp(-np.linspace(0, 8, _n)) * np.random.default_rng(1).uniform(-1, 1, _n)
SOUNDS = {"kick": KICK, "snare": SNARE, "clap": CLAP, "hat": HAT, "bass": BASS, "riff": RIFF, "click": CLICK}

# Patterns on sixteenth-note steps of one 4/4 bar (0 = the downbeat, 4 = beat 2 ...),
# as {sound: [(step, velocity), ...]}
def _s(steps, vel=1.0):
    return [(s, vel) for s in steps]


PATTERNS = {
    "clicks": {"click": _s([0, 4, 8, 12])},
    # four on the floor with the bass on every off-beat, as in most house
    "house": {"kick": _s([0, 4, 8, 12]), "hat": _s([2, 6, 10, 14]), "clap": _s([4, 12], 0.8), "bass": _s([2, 6, 10, 14])},
    # a riff every three sixteenths (dotted eighths) over the kick
    "riff": {"kick": _s([0, 4, 8, 12]), "riff": _s([0, 3, 6, 9, 12, 15]), "hat": _s(range(16), 0.4)},
    "dnb": {"kick": _s([0, 10]), "snare": _s([4, 12]), "hat": _s(range(0, 16, 2), 0.6)},
    "boombap": {"kick": _s([0, 7, 10]), "snare": _s([4, 12]), "hat": _s(range(0, 16, 2), 0.6)},
    # kick on 1 and snare on 3 at full tempo: what half-time dubstep sounds like
    "halftime": {"kick": _s([0]), "snare": _s([8]), "hat": _s(range(0, 16, 2), 0.5)},
    # 2-step: the kick skips beat 3 and lands on the "and" of 3; hats shuffle
    "garage": {"kick": _s([0, 10]), "snare": _s([4, 12]), "hat": _s([2, 6, 10, 14]) + _s([3, 7, 11, 15], 0.4)},
    "hats_dotted": {"hat": _s([0, 3, 6, 9, 12, 15])},
    "pads": {},
    "silence": {},
    # a snare roll in sixteenths over the last two beats, rising, as before a drop
    "roll": {"kick": _s([0, 4]), "snare": [(s, 0.4 + 0.6 * (s - 8) / 7) for s in range(8, 16)]},
}
PAD_CHORDS = ((220.0, 261.63, 329.63), (196.0, 246.94, 293.66), (174.61, 220.0, 261.63), (196.0, 246.94, 311.13))


# ------------------------------------------------------------------ cases

def _seg(bars, bpm, pattern, pad=False, gain=1.0, bpm_to=None):
    return {"bars": bars, "bpm": bpm, "bpm_to": bpm_to, "pattern": pattern, "pad": pad, "gain": gain}


CASES = {
    "clicks120": [_seg(16, 120, "clicks")],
    "house": [_seg(24, 124, "house")],
    "riff": [_seg(24, 128, "riff")],
    "ramp": [_seg(8, 136, "dnb"), _seg(16, 136, "dnb", bpm_to=174), _seg(12, 174, "dnb")],
    "jump": [_seg(12, 100, "boombap"), _seg(16, 140, "boombap")],
    # 32 bars of pads with no drums between two drops: the beat should hold, then relock
    "breakdown": [_seg(16, 126, "house"), _seg(32, 126, "pads", pad=True), _seg(16, 126, "house", pad=True)],
    "halftime": [_seg(24, 140, "halftime")],
    "garage": [_seg(24, 132, "garage")],
    "roll": [_seg(7, 128, "house"), _seg(1, 128, "roll"), _seg(7, 128, "house"), _seg(1, 128, "roll"), _seg(8, 128, "house")],
    # two bars of near-silence (under the silence threshold) in the middle
    "quiet": [_seg(12, 128, "house"), _seg(2, 128, "silence"), _seg(12, 128, "house")],
    "sparse_intro": [_seg(8, 128, "hats_dotted"), _seg(16, 128, "house")],
}


def render(segments, sr=SR):
    """The case's audio and its true beats as (time, bpm there, segment index)."""
    beats = []
    t = 0.0
    for si, seg in enumerate(segments):
        n = seg["bars"] * 4
        b0, b1 = seg["bpm"], seg["bpm_to"] or seg["bpm"]
        for i in range(n):
            bpm = b0 + (b1 - b0) * i / n
            beats.append((t, bpm, si))
            t += 60.0 / bpm
    total = t + 1.0
    x = np.zeros(int(total * sr) + sr)
    bi = 0
    for si, seg in enumerate(segments):
        pattern = PATTERNS[seg["pattern"]]
        segBeats = [b for b in beats if b[2] == si]
        for k, (bt, bpm, _) in enumerate(segBeats):
            period = 60.0 / bpm
            beatInBar = k % 4
            for name, steps in pattern.items():
                snd = SOUNDS[name] * seg["gain"]
                for step, vel in steps:
                    if step // 4 != beatInBar:
                        continue
                    i = int((bt + (step % 4) * period / 4) * sr)
                    x[i:i + len(snd)] += vel * snd[:len(x) - i]
            if seg["pad"] and beatInBar == 0:
                # one chord per bar with a slow attack: a pulse on the bar line, if anything
                barLen = 4 * period
                m = int(barLen * sr)
                tt = np.arange(m) / sr
                chord = PAD_CHORDS[(k // 4) % len(PAD_CHORDS)]
                sig = sum(np.sin(2 * np.pi * f * tt) for f in chord) * 0.07 * np.minimum(1.0, tt / 0.6)
                i = int(bt * sr)
                x[i:i + m] += sig[:len(x) - i]
        bi += len(segBeats)
    if np.max(np.abs(x)) > 1.0:
        x /= np.max(np.abs(x))
    return x, beats


# ------------------------------------------------------------------ scoring

def firedBeats(features):
    out, last = [], 0
    for f in features:
        if f["beat"] != last:
            out.append(f["t"])
            last = f["beat"]
    return out


def score(features, truth, segments=None):
    """Numbers for one run. truth: [(time, bpm, segment index)]; features: Analyzer output."""
    fired = np.array(firedBeats(features))
    tt = np.array([b[0] for b in truth])

    def nearest(arr, v):
        if not len(arr):
            return None
        i = int(np.searchsorted(arr, v))
        cands = [arr[j] for j in (i - 1, i) if 0 <= j < len(arr)]
        return min(cands, key=lambda c: abs(c - v))

    hit = []
    for t, _, _ in truth:
        n = nearest(fired, t)
        hit.append(n is not None and abs(n - t) <= TOLERANCE_S)
    lock = None
    run = 0
    for (t, _, _), h in zip(truth, hit):
        run = run + 1 if h else 0
        if run >= 4:
            lock = t
            break
    offsets, false = [], 0
    for f in fired:
        n = nearest(tt, f)
        if n is not None and abs(f - n) <= TOLERANCE_S:
            offsets.append(f - n)
        else:
            false += 1
    after = [h for (t, _, _), h in zip(truth, hit) if lock is not None and t > lock]

    # tempo reading against the true tempo at each moment
    tempo = {"ok": 0}
    for name, _ in RELATED:
        tempo[name] = 0
    counted = 0
    j = 0
    for f in features:
        if f["t"] < WARMUP_S:
            continue
        while j + 1 < len(truth) and truth[j + 1][0] <= f["t"]:
            j += 1
        if f["t"] > truth[-1][0] + 60.0 / truth[-1][1]:
            break
        counted += 1
        got, want = f["bpm"], truth[j][1]
        if got <= 0:
            continue
        r = got / want
        if abs(r - 1) <= TEMPO_OK:
            tempo["ok"] += 1
            continue
        for name, ratio in RELATED:
            if abs(r / ratio - 1) <= TEMPO_OK:
                tempo[name] += 1
                break
    span = (truth[-1][0] - truth[0][0]) / 60.0 or 1.0
    out = {
        "lock_s": None if lock is None else round(lock, 2),
        "hit": None if not after else round(sum(after) / len(after), 3),
        "false_per_min": round(false / span, 1),
        "offset_ms": None if not offsets else round(float(np.median(offsets)) * 1000, 1),
        "tempo_ok": round(tempo["ok"] / counted, 3) if counted else None,
        "related": {k: round(v / counted, 3) for k, v in tempo.items() if k != "ok" and counted and v},
        "segments": [],
    }
    nseg = max(b[2] for b in truth) + 1
    for si in range(nseg):
        hs = [h for (t, _, s), h in zip(truth, hit) if s == si]
        seg = {"beats": len(hs), "hit": round(sum(hs) / len(hs), 3) if hs else None}
        if segments:
            seg["pattern"] = segments[si]["pattern"]
        out["segments"].append(seg)
    return out


def runCase(name):
    segments = CASES[name]
    x, truth = render(segments)
    return score(au.Analyzer().analyze(x), truth, segments)


def runSong(path, start=0.0, end=None):
    """Score a song from start to end (seconds; the tracker starts at start, as if the song
    began there). The reference grid comes from the whole song's analysis."""
    samples, sr = au.loadSong(path)
    analysis = au.analyzeSong(samples, sr)
    bpm, first = analysis["bpm"], analysis["offset_ms"] / 1000.0
    period = 60.0 / bpm
    duration = len(samples) / sr
    end = duration if end is None else min(end, duration)
    truth = []
    t = first
    while t < end - 0.5:
        if t >= start:
            truth.append((t - start, bpm, 0))
        t += period
    hop = max(1, int(round(au.HOP * sr / SR)))  # the same ~21 ms frames at the song's rate
    out = score(au.Analyzer(sampleRate=sr, hop=hop).analyze(samples[int(start * sr):int(end * sr)]), truth)
    out["reference_bpm"] = round(bpm, 2)
    return out


# ------------------------------------------------------------------ report

def _fmt(v, pct=False, unit=""):
    if v is None:
        return "-"
    return ("%d%%" % round(v * 100)) if pct else ("%g%s" % (v, unit))


def report(name, r):
    rel = ", ".join("%s %d%%" % (k, round(v * 100)) for k, v in r["related"].items()) or "-"
    print("%-14s lock %-6s hit %-5s false %-6s offset %-8s tempo %-5s related %s" % (
        name, _fmt(r["lock_s"]), _fmt(r["hit"], True), _fmt(r["false_per_min"], unit="/min"),
        _fmt(r["offset_ms"], unit=" ms"), _fmt(r["tempo_ok"], True), rel))
    if len(r["segments"]) > 1:
        print("%-14s by part: %s" % ("", "; ".join(
            "%s %s" % (s.get("pattern", i + 1), _fmt(s["hit"], True)) for i, s in enumerate(r["segments"]))))


def main(argv):
    ap = argparse.ArgumentParser(description="Score the live beat tracker.")
    ap.add_argument("cases", nargs="*", help="synthetic case names (default: all)")
    ap.add_argument("--song", action="append", default=[], help="a song file with a steady tempo")
    ap.add_argument("--json", help="also write the results to this file")
    args = ap.parse_args(argv)
    results = {}
    names = args.cases or ([] if args.song else list(CASES))
    for name in names:
        if name not in CASES:
            ap.error("unknown case %s (have: %s)" % (name, ", ".join(CASES)))
        results[name] = runCase(name)
        report(name, results[name])
    for arg in args.song:
        path, start, end = arg, 0.0, None
        span = re.match(r"^(.*)@(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$", arg)
        if span:
            path, start, end = span.group(1), float(span.group(2)), float(span.group(3))
        label = os.path.splitext(os.path.basename(path))[0][:14]
        results[arg] = runSong(path, start, end)
        report(label, results[arg])
        print("%-14s reference tempo %s BPM from the song analysis%s" % (
            "", results[arg]["reference_bpm"], " (%g to %g s)" % (start, end) if span else ""))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1)
    return results


if __name__ == "__main__":
    main(sys.argv[1:])
