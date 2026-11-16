"""Audio for NeewerLux: live capture and the analysis shared by sound modes and song import.

Analysis needs numpy; live capture also needs soundcard (inputs and Windows WASAPI loopback
through one API). Both are optional (the "audio" dependency group): without them
available() / captureAvailable() say why and NeewerLux hides the features.

The analyzer turns blocks of mono samples into features: level, low/mid/high band energy,
spectral centroid ("brightness" of the sound), onsets, a tempo estimate and a beat clock.
Level and bands are normalised against their own recent peaks (on a dB scale), so quiet
and loud material both use the whole 0 to 1 range; true silence reads as 0.

AudioEngine runs capture and analysis on a thread of its own and keeps only the latest
features; the show engine reads them each frame and never waits on audio.

analyzeSong works on a whole song file at once (soundfile decodes it): tempo, beat grid,
bars, an energy curve, a waveform for drawing, and sections, for drafting sequences.
"""

import glob
import json
import math
import os
import re
import shlex
import subprocess
import tempfile
import threading
import time

try:
    import numpy as np
except ImportError:
    np = None

SAMPLE_RATE = 48000
HOP = 1024                 # samples per analysis frame (about 21 ms at 48 kHz)
FFT_SIZE = 2048
BANDS = {"low": (20.0, 250.0), "mid": (250.0, 4000.0), "high": (4000.0, 16000.0)}
SILENCE_DB = -55.0         # below this (dBFS RMS) a block is quiet; quiet for SILENCE_HOLD_S is silence
SILENCE_HOLD_S = 0.3
NORM_RANGE_DB = 30.0       # a value this far under its recent peak reads as 0
PEAK_HALF_LIFE_S = 3.0     # how fast the normalising peaks forget a loud passage
TEMPO_WINDOW_S = 6.0       # onset history used for the tempo estimate
TEMPO_EVERY_S = 0.5
BPM_MIN, BPM_MAX = 60.0, 200.0  # the default tempo range
TEMPO_RANGE_LIMITS = (40.0, 250.0)  # how far the tempo range setting can go
TEMPO_RANGE_MIN_SPAN = 10.0
BPM_PRIOR = 120.0          # tempos far from this (in octaves) are less likely
STALE_S = 0.5              # features older than this are treated as no signal
KICK_BAND = (40.0, 150.0)  # where a kick drum's body is; phase comes from onsets here when there are any
KICK_WINDOW_S = 2.0        # kicks are present when this stretch holds at least KICK_MIN_COUNT kick onsets
KICK_MIN_COUNT = 2
KICK_REF_HALF_LIFE_S = 20.0  # how fast the reference for a strong kick onset forgets a loud passage
PHASE_WINDOW_S = 6.0       # onset history the beat phase is fitted to
PHASE_DECAY = 0.85         # each beat further back counts this much less, so a new phase shows sooner
PHASE_FLUX_WEIGHT = 0.3    # with kicks, the whole-spectrum onsets still count this much (snares, claps)
PHASE_LAG_S = 0.025        # how far an onset in the envelope trails the sound itself
TEMPO_BAR_WEIGHT = 0.5     # a pattern repeating every 4 beats (a bar) supports a tempo; a 3/2 or 4/3 reading has no such repeat
RELATED_TEMPOS = (2.0, 0.5, 1.5, 2.0 / 3.0, 4.0 / 3.0, 0.75)
TEMPO_CONFIRM = 3          # estimates in a row (every TEMPO_EVERY_S) that switch to a new tempo
TEMPO_CONFIRM_RELATED = 8  # ... when the new tempo is a related one: usually a fill or a riff, not a change
TRUST_S = 4.0              # a tempo steady this long with kicks is trusted, and held when the kicks stop
HOLD_MAX_S = 60.0          # longest a trusted tempo is held with no kicks (a breakdown, not a new song)
SILENCE_COAST_S = 4.0      # the beat clock keeps time through silence this long, then lets go
BEAT_SILENCE_GRACE_S = 1.0  # beats still count this long into a silence (gaps between sparse hits)
KICK_REFRACTORY_S = 0.1    # one kick counted per hit, however many frames its attack spans
KICK_HIT_SHARE = 0.5       # a kick counted for the Kick drive rises at least this much of a recent strong one
                           # (a third lets through too many off-beat bass notes; the tracker's own test is looser)

_captureState = None


def validTempoRange(lo, hi):
    """(lo, hi) as floats, or None when not numbers inside TEMPO_RANGE_LIMITS at least
    TEMPO_RANGE_MIN_SPAN apart."""
    try:
        lo, hi = float(lo), float(hi)
    except (TypeError, ValueError):
        return None
    if not (TEMPO_RANGE_LIMITS[0] <= lo and hi <= TEMPO_RANGE_LIMITS[1] and hi - lo >= TEMPO_RANGE_MIN_SPAN):
        return None
    return lo, hi


def available():
    """(True, "") when analysis can run, else (False, the reason)."""
    if np is None:
        return False, "Sound features need numpy (install the audio extras: uv sync --group audio)"
    return True, ""


def captureAvailable():
    """(True, "") when live capture can run, else (False, the reason). soundcard is imported
    once; on systems without an audio server its import itself fails, not just ImportError."""
    global _captureState
    ok, why = available()
    if not ok:
        return ok, why
    if _captureState is None:
        try:
            import soundcard  # noqa: F401
            _captureState = (True, "")
        except Exception as e:
            _captureState = (False, "Live sound needs the soundcard package and a working audio device (" +
                             (type(e).__name__ + ": " + str(e)).strip() + ")")
    return _captureState


def _db(x):
    return 20.0 * math.log10(max(x, 1e-12))


class Analyzer:
    """Feed it consecutive mono blocks of `hop` samples; each process() returns the features
    as of the end of that block. Times are seconds of audio processed."""

    def __init__(self, sampleRate=SAMPLE_RATE, hop=HOP, tempoRange=(BPM_MIN, BPM_MAX)):
        self.sr = float(sampleRate)
        self.bpmMin, self.bpmMax = tempoRange
        self.hop = int(hop)
        self.fps = self.sr / self.hop
        self.window = np.hanning(FFT_SIZE).astype(np.float64)
        self._winPower = float(np.mean(self.window ** 2))
        freqs = np.fft.rfftfreq(FFT_SIZE, 1.0 / self.sr)
        self.freqs = freqs
        self.bandMasks = {k: (freqs >= lo) & (freqs < hi) for k, (lo, hi) in BANDS.items()}
        self.centroidMask = (freqs >= 40.0) & (freqs <= 12000.0)
        self.kickMask = (freqs >= KICK_BAND[0]) & (freqs < KICK_BAND[1])
        # onsets are measured on 24 bands spaced evenly in pitch (40 Hz to 11 kHz), so a kick
        # drum counts as much as a hi-hat that covers many more FFT bins
        edges = np.geomspace(40.0, 11000.0, 25)
        self.fluxBands = [(int(np.searchsorted(freqs, lo)), max(int(np.searchsorted(freqs, hi)), int(np.searchsorted(freqs, lo)) + 1))
                          for lo, hi in zip(edges[:-1], edges[1:])]
        self.buf = np.zeros(FFT_SIZE)
        self.prevLogMag = None
        self.t = 0.0
        self.peakDecay = 0.5 ** (1.0 / (PEAK_HALF_LIFE_S * self.fps))
        self.peaks = {"level": 0.0, "low": 0.0, "mid": 0.0, "high": 0.0, "flux": 0.0}
        self.histLen = int(math.ceil(8.0 * self.fps))
        self.onsetEnv = np.zeros(self.histLen)
        self.kickEnv = np.zeros(self.histLen)
        self.prevKick = None
        self.kickRef = 0.0
        self.kickRefDecay = 0.5 ** (1.0 / (KICK_REF_HALF_LIFE_S * self.fps))
        self.kicksPresent = False
        self.kickCount = 0
        self.lastKick = -1.0
        self.trusted = False
        self._steadySince = None
        self._noKickSince = None
        self.frames = 0
        self.onsetCount = 0
        self.lastOnset = -1.0
        self.fluxRecent = []
        self.bpm = 0.0
        self.confidence = 0.0
        self._pendingBpm = None
        self._pendingCount = 0
        self._pendingPhase = None
        self.period = 0.0
        self.nextBeat = None
        self.lastBeat = None
        self.beatCount = 0
        self.silentSince = 0.0
        self.silent = True
        self.quiet = True
        self.quietSince = 0.0
        self.centroid = 0.0
        self._tempoEvery = max(1, int(round(TEMPO_EVERY_S * self.fps)))

    # -------------------------------------------------------------- per block
    def process(self, block):
        block = np.asarray(block, dtype=np.float64).reshape(-1)
        n = len(block)
        if n >= FFT_SIZE:
            self.buf = block[-FFT_SIZE:].copy()
        else:
            self.buf = np.concatenate((self.buf[n:], block))
        self.t += n / self.sr
        self.frames += 1

        rms = float(np.sqrt(np.mean(block ** 2))) if n else 0.0
        rmsDb = _db(rms)
        spec = np.fft.rfft(self.buf * self.window)
        power = spec.real ** 2 + spec.imag ** 2
        scale = 2.0 / (FFT_SIZE * FFT_SIZE * self._winPower)
        bandRms = {k: math.sqrt(float(np.sum(power[m])) * scale) for k, m in self.bandMasks.items()}

        mag = np.sqrt(power)
        cm = mag[self.centroidMask]
        total = float(np.sum(cm))
        if total > 0:
            c = float(np.sum(self.freqs[self.centroidMask] * cm) / total)
            cNorm = min(1.0, max(0.0, math.log2(max(c, 1.0) / 150.0) / math.log2(6000.0 / 150.0)))
        else:
            cNorm = 0.0

        bandPower = np.array([float(np.sum(power[a:b])) for a, b in self.fluxBands]) * scale
        logMag = np.log1p(1e4 * bandPower)
        flux = 0.0 if self.prevLogMag is None else float(np.sum(np.maximum(0.0, logMag - self.prevLogMag)))
        self.prevLogMag = logMag

        # a gap between notes isn't silence: only a stretch of quiet blocks is
        self.quiet = rmsDb < SILENCE_DB
        if not self.quiet:
            self.quietSince = None
        elif self.quietSince is None:
            self.quietSince = self.t - n / self.sr
        wasSilent = self.silent
        self.silent = self.quiet and self.t - self.quietSince >= SILENCE_HOLD_S
        if self.silent and not wasSilent:
            self.silentSince = self.t
        # amplitude, not log: on a log scale a bass note rising from quiet outweighs a louder
        # kick that lands while the last bass note is still sounding
        ampKick = math.sqrt(float(np.sum(power[self.kickMask])) * scale)
        kick = 0.0 if self.prevKick is None else max(0.0, ampKick - self.prevKick)
        self.prevKick = ampKick
        if self.quiet:
            flux = 0.0
            kick = 0.0

        self.onsetEnv = np.roll(self.onsetEnv, -1)
        self.onsetEnv[-1] = flux
        self.kickEnv = np.roll(self.kickEnv, -1)
        self.kickEnv[-1] = kick
        self.kickRef = max(kick, self.kickRef * self.kickRefDecay)
        if (not self.silent and kick > 0 and kick >= self.kickRef * KICK_HIT_SHARE
                and self.t - self.lastKick >= KICK_REFRACTORY_S):
            self.kickCount += 1
            self.lastKick = self.t

        out = {"t": self.t, "rms_db": round(rmsDb, 1), "silent": self.silent}
        for key, value in (("level", rms), ("low", bandRms["low"]), ("mid", bandRms["mid"]), ("high", bandRms["high"])):
            out[key] = self._normalise(key, value)
        if not self.silent:
            self.centroid += (cNorm - self.centroid) * 0.35  # light smoothing; modes smooth further
        out["centroid"] = round(self.centroid, 3)

        # Onsets: flux well above its recent average, at most one per 100 ms
        self.fluxRecent.append(flux)
        if len(self.fluxRecent) > int(self.fps * 0.5):
            self.fluxRecent.pop(0)
        mean = sum(self.fluxRecent) / len(self.fluxRecent)
        self.peaks["flux"] = max(flux, self.peaks["flux"] * self.peakDecay)
        strength = flux / self.peaks["flux"] if self.peaks["flux"] > 0 else 0.0
        if not self.silent and flux > 1.5 * mean + 0.05 * self.peaks["flux"] and self.t - self.lastOnset >= 0.1:
            self.onsetCount += 1
            self.lastOnset = self.t
        out["onset"] = self.onsetCount
        out["onset_strength"] = round(min(1.0, strength), 3)
        out["kick"] = self.kickCount

        if self.frames % self._tempoEvery == 0:
            self._estimateTempo()
        self._advanceBeats()
        out["bpm"] = round(self.bpm, 1)
        out["confidence"] = round(self.confidence, 3)
        out["beat"] = self.beatCount
        if self.lastBeat is not None and self.period > 0:
            out["beat_phase"] = round(min(1.0, max(0.0, (self.t - self.lastBeat) / self.period)), 3)
        else:
            out["beat_phase"] = 0.0
        out["beat_t"] = self.lastBeat
        return out

    def _normalise(self, key, value):
        """0 to 1 on a dB scale against the recent peak; 0 in silence. Quiet blocks don't move
        the peak, so the first sound after a pause isn't over-amplified."""
        if self.silent:
            return 0.0
        if not self.quiet:
            self.peaks[key] = max(value, self.peaks[key] * self.peakDecay)
        self.peaks[key] = max(self.peaks[key], 10 ** (SILENCE_DB / 20.0))
        rel = _db(value) - _db(self.peaks[key])
        return round(min(1.0, max(0.0, 1.0 + rel / NORM_RANGE_DB)), 3)

    # ------------------------------------------------------------ tempo/beats
    def _estimateTempo(self):
        w = int(TEMPO_WINDOW_S * self.fps)
        filled = min(self.frames, self.histLen)
        if filled < int(3.0 * self.fps) or (self.silent and self.t - self.silentSince > 1.0):
            if self.silent:
                self.confidence = 0.0
            return
        self.kicksPresent = self._countKicks() >= KICK_MIN_COUNT
        if self.kicksPresent:
            self._noKickSince = None
        elif self._noKickSince is None:
            self._noKickSince = self.t
        if self.trusted and not self.kicksPresent:
            if self.t - self._noKickSince < HOLD_MAX_S:
                return  # a breakdown: the beat clock keeps the trusted tempo and phase
            self.trusted = False
            self._steadySince = None
        x = self.onsetEnv[-min(w, filled):]
        # a little blur: beats at a fractional number of frames apart still line up
        x = np.convolve(x, (0.25, 0.5, 0.25), mode="same")
        x = x - np.mean(x)
        if not np.any(x):
            self.confidence = 0.0
            return
        n = len(x)
        spec = np.fft.rfft(x, 2 * n)
        ac = np.fft.irfft(spec.real ** 2 + spec.imag ** 2)[:n]
        if ac[0] <= 0:
            return
        ac = ac / ac[0]
        def at(lag):  # autocorrelation at a fractional lag
            i = int(lag)
            if i + 1 >= n or i < 1:
                return 0.0
            f = lag - i
            return float(ac[i] * (1 - f) + ac[i + 1] * f)
        best, bestScore = None, -1e9
        lo, hi = self.bpmMin, self.bpmMax
        prior = min(hi, max(lo, BPM_PRIOR))
        bpm = lo
        while bpm <= hi:
            lag = 60.0 * self.fps / bpm
            # the period itself and its double support a tempo. A strong peak at half the period
            # counts against it, but only when twice this tempo is itself a plausible tempo:
            # eighth notes over a 124 BPM beat are not a 248 BPM song
            score = at(lag) + 0.5 * at(2 * lag) + TEMPO_BAR_WEIGHT * at(4 * lag)
            if 2 * bpm <= hi:
                score -= 0.35 * max(0.0, at(lag / 2))
            score *= math.exp(-0.5 * (math.log2(bpm / prior) / 0.8) ** 2)
            if score > bestScore:
                best, bestScore = bpm, score
            bpm += 0.25
        if best is None or bestScore <= 0:
            return
        # refine: the autocorrelation at 1 to 4 periods pins the period down far finer than one
        # step of the search (0.25 BPM is 0.2% at 120, enough to drift a light off the beat)
        top = max(1, min(4, int((n - 2) // (60.0 * self.fps / best))))
        fine, fineScore = best, -1e9
        b = max(lo, best - 0.3)
        while b <= min(hi, best + 0.3):
            lag = 60.0 * self.fps / b
            sc = sum(at(m * lag) for m in range(1, top + 1))
            if sc > fineScore:
                fine, fineScore = b, sc
            b += 0.02
        lag = 60.0 * self.fps / best
        cand = fine
        self.confidence = float(max(0.0, min(1.0, at(lag))))
        if self.bpm <= 0:
            self.bpm = cand
        elif abs(cand / self.bpm - 1.0) < 0.04:
            self.bpm += (cand - self.bpm) * 0.3
            self._pendingBpm = None
        elif self._pendingBpm is not None and abs(cand / self._pendingBpm - 1.0) < 0.04:
            self._pendingCount += 1
            related = self.trusted and any(abs(cand / (self.bpm * r) - 1.0) < 0.04 for r in RELATED_TEMPOS)
            if self._pendingCount >= (TEMPO_CONFIRM_RELATED if related else TEMPO_CONFIRM):
                self.bpm = cand  # the song changed tempo
                self._pendingBpm = None
                self.trusted = False
                self._steadySince = None
        else:
            self._pendingBpm, self._pendingCount = cand, 1
        if self.kicksPresent and abs(cand / self.bpm - 1.0) < 0.02:
            if self._steadySince is None:
                self._steadySince = self.t
            if self.t - self._steadySince >= TRUST_S:
                self.trusted = True
        elif not self.trusted:
            self._steadySince = None
        self.period = 60.0 / self.bpm
        self._alignPhase()

    def setTempoRange(self, lo, hi):
        """Only look for tempos from lo to hi BPM. A tempo outside it is dropped at once."""
        self.bpmMin, self.bpmMax = float(lo), float(hi)
        if self.bpm and not lo <= self.bpm <= hi:
            self.bpm = 0.0
            self.period = 0.0
            self.nextBeat = None
            self._pendingBpm = None
            self.trusted = False
            self._steadySince = None

    def _countKicks(self):
        """Kick onsets in the last KICK_WINDOW_S: peaks in the kick band's envelope that are at
        least a third of a recent strong one."""
        w = int(KICK_WINDOW_S * self.fps)
        x = self.kickEnv[-w:]
        thr = self.kickRef / 3.0
        if thr <= 0:
            return 0
        peaks = (x[1:-1] >= thr) & (x[1:-1] >= x[:-2]) & (x[1:-1] > x[2:])
        return int(np.sum(peaks))

    def _alignPhase(self):
        """Find where the beats fall: the offset whose comb of beat times collects the most
        onset energy over the last few seconds, recent beats counting most. With kicks, the
        kick band leads: across the whole spectrum an off-beat bass note or busy hi-hats
        outweigh the kick."""
        p = self.period * self.fps
        filled = min(self.frames, self.histLen)
        k = int(min(PHASE_WINDOW_S * self.fps, filled) // p)
        if k < 2:
            return
        flux = self.onsetEnv / self.peaks["flux"] if self.peaks["flux"] > 0 else self.onsetEnv
        if self.kicksPresent and self.kickRef > 0:
            env = self.kickEnv / self.kickRef + PHASE_FLUX_WEIGHT * flux
        else:
            env = flux
        # quarter-frame steps between frames: a whole frame (21 ms) is too coarse for a beat
        n = len(env)
        offs = np.arange(0.0, p, 0.25)
        pos = (n - 1) - (offs[:, None] + np.arange(k)[None, :] * p)
        weights = PHASE_DECAY ** np.arange(k)
        scores = (np.interp(pos, np.arange(n), env) * weights).sum(axis=1)
        best = float(offs[int(np.argmax(scores))])
        lastBeat = self.t - best / self.fps - PHASE_LAG_S
        nxt = lastBeat + self.period
        while nxt <= self.t:
            nxt += self.period
        if self.nextBeat is None:
            self.nextBeat = nxt
            self._pendingPhase = None
            return
        # how far the found phase is from the running beat clock, folded to +- half a period
        diff = (nxt - self.nextBeat + self.period / 2) % self.period - self.period / 2
        if abs(diff) < 0.25 * self.period:
            self.nextBeat += diff * 0.5   # small drift: ease the clock towards it
            self._pendingPhase = None
        elif self._pendingPhase is not None and abs((diff - self._pendingPhase + self.period / 2) % self.period - self.period / 2) < 0.1 * self.period:
            self.nextBeat += diff         # the same new phase twice in a row: the beat really moved
            self._pendingPhase = None
        else:
            self._pendingPhase = diff
        if self.lastBeat is not None and self.nextBeat - self.lastBeat < 0.6 * self.period:
            self.nextBeat += self.period  # a correction must not fire the same beat twice

    def _advanceBeats(self):
        if self.nextBeat is None or self.period <= 0:
            return
        if self.silent:
            if self.t - self.silentSince > SILENCE_COAST_S:
                self.nextBeat = None  # the beat clock stops and re-aligns when sound returns
                self.trusted = False
                self._steadySince = None
                return
            if self.t - self.silentSince > BEAT_SILENCE_GRACE_S:
                # a longer stop (before a drop): keep time without beats, so the first beat
                # after it lands where it should and sound modes stay at their floor meanwhile
                while self.t + 0.5 * self.hop / self.sr >= self.nextBeat:
                    self.nextBeat += self.period
                return
        # fire on the block nearest the beat rather than the first one after it: half a block
        # (about 10 ms) sooner on average
        while self.t + 0.5 * self.hop / self.sr >= self.nextBeat:
            self.beatCount += 1
            self.lastBeat = self.nextBeat
            self.nextBeat += self.period

    def analyze(self, samples):
        """Run a whole mono signal through, one hop at a time; returns the features per hop."""
        samples = np.asarray(samples, dtype=np.float64).reshape(-1)
        out = []
        for i in range(0, len(samples) - self.hop + 1, self.hop):
            out.append(self.process(samples[i:i + self.hop]))
        return out


# ============================================================================
# CAPTURE
# ============================================================================

# ------------------------------------------------------------------ song files

SONG_EXTENSIONS = (".wav", ".flac", ".mp3", ".ogg", ".aiff", ".aif")
SONG_HOP_S = 0.01          # analysis frame step for whole songs
SONG_ENERGY_STEP_MS = 250
SONG_WAVEFORM_POINTS = 1200
SECTION_MIN_BARS = 4       # sections are at least this many bars long
SECTION_MAX_BARS = 32      # longer stretches are split where they change most
SECTION_NOVELTY_BARS = 4   # bars compared on each side of a possible section boundary
SECTION_REPEAT_BARS = 8    # bars on each side of a line when looking for blocks of alike bars
SECTION_GROUP_SIMILARITY = 0.45  # sections at least this alike (timbre and harmony) share a group


def songAvailable():
    """(True, "") when song files can be analysed, else (False, the reason)."""
    ok, why = available()
    if not ok:
        return ok, why
    try:
        import soundfile  # noqa: F401
    except Exception as e:
        return False, "Song import needs the soundfile package (install the audio extras: uv sync --group audio; " + \
            (type(e).__name__ + ": " + str(e)).strip() + ")"
    return True, ""


def loadSong(path):
    """Decode a song file (WAV, FLAC, MP3, OGG, AIFF) to (mono float samples, sample rate)."""
    import soundfile
    data, sr = soundfile.read(path, dtype="float32", always_2d=True)
    return data.mean(axis=1).astype(np.float64), int(sr)


def _songFrames(x, sr):
    """Per-frame level, band levels, centroid, low-band onset and onset flux for a whole signal,
    plus its timbre (24 log band levels, "bands") and harmony (12 pitch classes, "chroma") for
    finding repeats, computed in chunks (a long song as one FFT matrix would need gigabytes)."""
    hop = max(1, int(round(sr * SONG_HOP_S)))
    n = max(1, (len(x) - FFT_SIZE) // hop + 1) if len(x) >= FFT_SIZE else 1
    pad = np.concatenate([x, np.zeros(FFT_SIZE + hop)])
    window = np.hanning(FFT_SIZE)
    scale = 1.0 / (np.mean(window ** 2) * FFT_SIZE ** 2) * 2.0
    freqs = np.fft.rfftfreq(FFT_SIZE, 1.0 / sr)
    masks = {k: (freqs >= lo) & (freqs < hi) for k, (lo, hi) in BANDS.items()}
    cmask = (freqs >= 40.0) & (freqs <= 12000.0)
    edges = np.geomspace(40.0, 11000.0, 25)
    bandIdx = np.clip(np.searchsorted(edges, freqs) - 1, -1, 23)
    bandMap = np.zeros((len(freqs), 24))
    bandMap[bandIdx >= 0, bandIdx[bandIdx >= 0]] = 1.0
    chromaMap = np.zeros((len(freqs), 12))
    pitched = (freqs >= 55.0) & (freqs <= 5000.0)
    chromaMap[pitched, np.round(12.0 * np.log2(freqs[pitched] / 440.0)).astype(int) % 12] = 1.0
    out = {k: np.zeros(n) for k in ("rms", "low", "mid", "high", "centroid", "flux", "lowflux")}
    out["bands"] = np.zeros((n, 24), dtype=np.float32)
    out["chroma"] = np.zeros((n, 12), dtype=np.float32)
    prev = None
    chunk = 2048
    for start in range(0, n, chunk):
        m = min(chunk, n - start)
        idx = (start + np.arange(m))[:, None] * hop + np.arange(FFT_SIZE)[None, :]
        frames = pad[idx]
        out["rms"][start:start + m] = np.sqrt(np.mean(frames[:, :hop] ** 2, axis=1))  # this frame's own samples
        power = np.abs(np.fft.rfft(frames * window, axis=1)) ** 2 * scale
        for k, mask in masks.items():
            out[k][start:start + m] = np.sqrt(np.sum(power[:, mask], axis=1))
        cp = power[:, cmask]
        tot = np.sum(cp, axis=1)
        cent = np.sum(cp * freqs[cmask][None, :], axis=1) / np.maximum(tot, 1e-20)
        out["centroid"][start:start + m] = np.log2(np.maximum(cent, 40.0) / 40.0) / np.log2(12000.0 / 40.0)
        logMag = np.log1p(1e4 * (power @ bandMap))
        out["bands"][start:start + m] = logMag
        chroma = power @ chromaMap
        out["chroma"][start:start + m] = chroma / np.maximum(np.sum(chroma, axis=1, keepdims=True), 1e-20)
        if prev is None:
            prev = logMag[:1]
        diff = np.diff(np.vstack([prev, logMag]), axis=0)
        out["flux"][start:start + m] = np.sum(np.maximum(0.0, diff), axis=1)
        out["lowflux"][start:start + m] = np.sum(np.maximum(0.0, diff[:, :6]), axis=1)  # 40 to about 150 Hz: kicks
        prev = logMag[-1:]
    quiet = 20.0 * np.log10(np.maximum(out["rms"], 1e-12)) < SILENCE_DB
    out["flux"][quiet] = 0.0
    out["lowflux"][quiet] = 0.0
    return out, sr / hop


def _tempoScores(env, fps):
    """Tempo scores (the live analyzer's scoring) over 8 s windows of the whole song. Returns
    (bpms in 0.25 BPM steps, summed scores, each window's best bpm)."""
    bpms = np.arange(BPM_MIN, BPM_MAX + 0.001, 0.25)
    total = np.zeros(len(bpms))
    winners = []
    w, step = int(8.0 * fps), int(2.0 * fps)
    starts = range(0, max(1, len(env) - w + 1), step) if len(env) > w else [0]
    prior = np.exp(-0.5 * (np.log2(bpms / BPM_PRIOR) / 0.8) ** 2)
    for s in starts:
        x = np.convolve(env[s:s + w], (0.25, 0.5, 0.25), mode="same")
        x = x - np.mean(x)
        if not np.any(x):
            continue
        n = len(x)
        spec = np.fft.rfft(x, 2 * n)
        ac = np.fft.irfft(spec.real ** 2 + spec.imag ** 2)[:n]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        def at(lags):
            i = lags.astype(int)
            f = lags - i
            ok = (i >= 1) & (i + 1 < n)
            i = np.clip(i, 0, n - 2)
            return np.where(ok, ac[i] * (1 - f) + ac[i + 1] * f, 0.0)
        lag = 60.0 * fps / bpms
        score = at(lag) + 0.5 * at(2 * lag)
        score -= np.where(2 * bpms <= BPM_MAX, 0.35 * np.maximum(0.0, at(lag / 2)), 0.0)
        score = np.maximum(0.0, score) * prior
        total += score
        if np.any(score > 0):
            winners.append(float(bpms[int(np.argmax(score))]))
    return bpms, total, winners


def _combScore(env, fps, bpm):
    """Best (score, phase in frames) of a beat comb at bpm over the whole onset envelope."""
    p = 60.0 * fps / bpm
    n = len(env)
    k = np.arange(int(n // p) + 1)
    best, bestPhase = -1.0, 0.0
    for phase in np.arange(0.0, p, 1.0):
        pos = phase + k * p
        pos = pos[pos < n - 1]
        i = pos.astype(int)
        f = pos - i
        s = float(np.sum(env[i] * (1 - f) + env[i + 1] * f))
        if s > best:
            best, bestPhase = s, phase
    return best, bestPhase


def analyzeSong(samples, sampleRate, bpm=None, offsetMs=None, segments=None):
    """Analyse a whole mono song. Assumes a steady tempo (most produced music has one).

    bpm and offsetMs, when given, are used instead of the estimates (offsetMs: when the first
    beat falls). segments, from another section finder ([{"start_ms", "end_ms", "label"}],
    externalSections), sets where sections start (moved to the nearest bar line) and gives each
    section an "ai_label"; the names, levels and groups are still worked out here. Returns {"duration_ms", "bpm", "offset_ms", "confidence", "beats" (ms),
    "bars" (ms of each bar's first beat), "energy" (0 to 1 every SONG_ENERGY_STEP_MS),
    "energy_step_ms", "waveform" (peak 0 to 1 at SONG_WAVEFORM_POINTS points), "sections"
    ([{"start_ms", "end_ms", "energy" 0 to 1, "level" 1 to 3, "label"}])}."""
    x = np.asarray(samples, dtype=np.float64).reshape(-1)
    sr = float(sampleRate)
    durationMs = int(round(len(x) * 1000.0 / sr))
    feats, fps = _songFrames(x, sr)
    # an onset shows in the frame whose window is centred on it, half a window after the
    # frame's start time
    lagMs = FFT_SIZE / 2.0 / sr * 1000.0
    env = feats["flux"]
    env = env / (np.max(env) or 1.0)

    if bpm:
        bpm = float(bpm)
        confidence = None
    else:
        bpms, scores, winners = _tempoScores(env, fps)
        coarse = float(bpms[int(np.argmax(scores))]) if np.any(scores > 0) else BPM_PRIOR
        # refine: the tempo whose beat comb lines up best over the whole song (a 0.25 BPM error
        # drifts a beat in a few minutes)
        cands = np.arange(coarse - 0.5, coarse + 0.5001, 0.02)
        combs = [_combScore(env, fps, c)[0] for c in cands]
        bpm = float(cands[int(np.argmax(combs))])
        # how much of the song agrees: the share of 8 s windows whose own best tempo is this one
        confidence = round(sum(1 for w in winners if abs(w / bpm - 1.0) < 0.02) / len(winners), 3) if winners else 0.0
    periodMs = 60000.0 / bpm
    if offsetMs is None:
        phase = _combScore(env, fps, bpm)[1]
        offsetMs = (phase / fps) * 1000.0 + lagMs
    offsetMs = float(offsetMs) % periodMs
    beats = [int(round(offsetMs + k * periodMs)) for k in range(int((durationMs - offsetMs) // periodMs) + 1)]

    # bars start on the beat (of each four) with the most kick-drum onsets
    low = feats["lowflux"]
    def onsetAt(ms):
        i = int(round((ms - lagMs) * fps / 1000.0))
        lo, hi = max(0, i - 2), min(len(low), i + 3)
        return float(np.max(low[lo:hi])) if hi > lo else 0.0
    beatOnsets = [onsetAt(b) for b in beats]
    barPhase = max(range(4), key=lambda ph: sum(beatOnsets[ph::4])) if len(beats) >= 8 else 0
    bars = beats[barPhase::4]

    step = SONG_ENERGY_STEP_MS
    perStep = max(1, int(round(step * fps / 1000.0)))
    rms = feats["rms"]
    nSteps = int(math.ceil(len(rms) / perStep))
    stepRms = np.array([np.sqrt(np.mean(rms[i * perStep:(i + 1) * perStep] ** 2)) for i in range(nSteps)])
    stepDb = 20.0 * np.log10(np.maximum(stepRms, 1e-12))
    loud = np.percentile(stepDb, 95) if len(stepDb) else 0.0
    energy = np.clip(1.0 + (stepDb - loud) / NORM_RANGE_DB, 0.0, 1.0)

    blocks = max(1, len(x) // SONG_WAVEFORM_POINTS)
    usable = x[:blocks * SONG_WAVEFORM_POINTS] if len(x) >= SONG_WAVEFORM_POINTS else np.pad(x, (0, SONG_WAVEFORM_POINTS - len(x)))
    peaks = np.max(np.abs(usable.reshape(SONG_WAVEFORM_POINTS, -1)), axis=1)
    waveform = peaks / (np.max(peaks) or 1.0)

    sections = _sections(feats, fps, bars, durationMs, energy, step, segments)
    return {"duration_ms": durationMs, "bpm": round(bpm, 2), "offset_ms": int(round(offsetMs)), "confidence": confidence,
            "beats": beats, "bars": bars, "energy": [round(float(v), 3) for v in energy], "energy_step_ms": step,
            "waveform": [round(float(v), 3) for v in waveform], "sections": sections}


SECTION_COMMAND_TIMEOUT_S = 600  # an AI section finder can take minutes per song on a CPU


def externalSections(command, path, timeoutS=SECTION_COMMAND_TIMEOUT_S):
    """Run another section finder on a song: command is its command line, with {song} for the
    song's path and {out} for a folder it may write into. It's run without a shell (the song
    path goes in as one argument, never as shell text), in that folder, which is removed
    afterwards. It answers with JSON on its output or in a .json file in the folder: a list of
    segments, or an object with "segments", each {"start", "end"} in seconds (or "start_ms",
    "end_ms") and a "label" (All-In-One's allin1 writes this). Returns (segments sorted by start,
    as [{"start_ms", "end_ms", "label"}], "") or (None, why it failed)."""
    try:
        args = shlex.split(command, posix=os.name != "nt")
    except ValueError as e:
        return None, "the section finder command can't be read: " + str(e)
    if os.name == "nt":
        args = [a[1:-1] if len(a) >= 2 and a[0] == a[-1] == '"' else a for a in args]
    if not args:
        return None, "the section finder command is empty"
    with tempfile.TemporaryDirectory() as out:
        args = [a.replace("{song}", path).replace("{out}", out) for a in args]
        try:
            run = subprocess.run(args, cwd=out, capture_output=True, text=True, timeout=timeoutS,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))  # no console flashing up over the app
        except FileNotFoundError:
            return None, "couldn't run the section finder: no program " + repr(args[0])
        except subprocess.TimeoutExpired:
            return None, "the section finder took longer than %d s" % timeoutS
        if run.returncode:
            last = (run.stderr or run.stdout or "").strip().splitlines()[-1:]
            return None, "the section finder failed (exit code %d)%s" % (run.returncode, ": " + last[0][:200] if last else "")
        found = []
        try:
            found.append(json.loads(run.stdout))
        except ValueError:
            pass
        for name in sorted(glob.glob(os.path.join(out, "**", "*.json"), recursive=True)):
            try:
                with open(name, encoding="utf-8") as f:
                    found.append(json.load(f))
            except (OSError, ValueError):
                continue
    for data in found:
        segments = _parseSegments(data)
        if segments:
            return segments, ""
    return None, "the section finder gave no segments (a list of {start, end, label}, or an object with \"segments\")"


def _parseSegments(data):
    if isinstance(data, dict):
        data = data.get("segments")
    if not isinstance(data, list):
        return None
    out = []
    for seg in data:
        if not isinstance(seg, dict):
            return None
        try:
            if "start_ms" in seg:
                a, b = int(seg["start_ms"]), int(seg["end_ms"])
            else:
                a, b = int(round(float(seg["start"]) * 1000)), int(round(float(seg["end"]) * 1000))
        except (KeyError, TypeError, ValueError):
            return None
        if b > a:
            out.append({"start_ms": a, "end_ms": b, "label": str(seg.get("label", ""))})
    return sorted(out, key=lambda seg: seg["start_ms"]) or None


def _cosine(m):
    """Cosine similarity between the rows of m, each centred on the song's mean first."""
    m = m - np.mean(m, axis=0)
    m = m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)
    return m @ m.T


def _sections(feats, fps, bars, durationMs, energy, energyStep, segments=None):
    """Split the song on bar lines where its sound changes, group the sections that sound alike
    (the parts that repeat) and name them by how they compare with the rest of the song.

    Two kinds of change are looked for: in loudness, bass, treble, brightness and busyness
    (the bars before and after a line differ), and in timbre and harmony (the bar-by-bar
    similarity of the whole song shows a block ending there), which finds a new riff or chord
    loop at the same loudness."""
    edges = sorted(set([0] + [b for b in bars if b > 0] + [durationMs]))
    if len(edges) < 3:
        sec = _section(0, durationMs, energy, energyStep)
        sec.update(level=2, label="Groove", group="A")
        return [sec]
    rows, timbre, chroma, kick, busy, cent = [], [], [], [], [], []
    for a, b in zip(edges[:-1], edges[1:]):
        i, j = int(a * fps / 1000.0), max(int(a * fps / 1000.0) + 1, int(b * fps / 1000.0))
        seg = {k: feats[k][i:j] for k in ("rms", "low", "high", "centroid", "flux", "lowflux")}
        rows.append([20.0 * math.log10(max(float(np.sqrt(np.mean(seg["rms"] ** 2))), 1e-9)),
                     20.0 * math.log10(max(float(np.mean(seg["low"])), 1e-9)),
                     20.0 * math.log10(max(float(np.mean(seg["high"])), 1e-9)),
                     float(np.mean(seg["centroid"])) * 30.0,
                     float(np.mean(seg["flux"])) * 30.0 / (float(np.max(feats["flux"])) or 1.0),
                     float(np.mean(seg["lowflux"])) * 30.0 / (float(np.max(feats["lowflux"])) or 1.0)])
        t = np.mean(feats["bands"][i:j], axis=0)
        timbre.append(t - np.mean(t))  # the shape of the spectrum, not its loudness
        chroma.append(np.mean(feats["chroma"][i:j], axis=0))
        kick.append(float(np.mean(seg["lowflux"])))
        busy.append(float(np.mean(seg["flux"])))
        cent.append(float(np.mean(seg["centroid"])))
    nb = len(rows)
    f = np.array(rows)
    f = (f - np.mean(f, axis=0)) / (np.std(f, axis=0) + 1e-9)
    w = SECTION_NOVELTY_BARS
    level = np.zeros(nb)
    for i in range(1, nb):
        a, b = f[max(0, i - w):i], f[i:min(nb, i + w)]
        if len(a) and len(b):
            level[i] = float(np.linalg.norm(np.mean(a, axis=0) - np.mean(b, axis=0)))
    sim = 0.6 * _cosine(np.array(timbre)) + 0.4 * _cosine(np.array(chroma))
    # a checkerboard kernel slid down the diagonal scores where one block of alike bars ends and
    # another begins
    k = SECTION_REPEAT_BARS
    signs = np.r_[-np.ones(k), np.ones(k)]
    taper = np.exp(-0.5 * np.linspace(-1.5, 1.5, 2 * k) ** 2)
    kernel = np.outer(signs * taper, signs * taper)
    padded = np.pad(sim, k, mode="edge")
    block = np.maximum(0.0, [-float(np.sum(padded[i:i + 2 * k, i:i + 2 * k] * kernel)) for i in range(nb)])
    novelty = level / (np.max(level) or 1.0) + block / (np.max(block) or 1.0)
    # phrases are usually 4 or 8 bars long: favour boundaries on those, counting from the first
    # bar (row 0 is the stretch before it when the first beat isn't at 0)
    first = 1 if edges[1] in bars and edges[0] not in bars else 0
    weighted = novelty * np.array([1.3 if (i - first) % 8 == 0 else 1.15 if (i - first) % 4 == 0 else 1.0 for i in range(nb)])
    threshold = float(np.mean(novelty[1:]) + 0.25 * np.std(novelty[1:])) if nb > 2 else 1e9
    picked = []
    if segments:
        # another finder's boundaries, on the nearest bar line, at least 2 bars apart
        for seg in segments[1:]:
            i = min(range(nb), key=lambda r: abs(edges[r] - seg["start_ms"]))
            if 2 <= i <= nb - 2 and all(abs(i - p) >= 2 for p in picked):
                picked.append(i)
    else:
        for i in np.argsort(-weighted):
            i = int(i)
            if i < SECTION_MIN_BARS or nb - i < SECTION_MIN_BARS or weighted[i] < threshold:
                continue
            if all(abs(i - p) >= SECTION_MIN_BARS for p in picked):
                picked.append(i)
    # a long stretch that changes little is still split, where it changes most (a draft needs
    # somewhere to move)
    while not segments:
        bounds = [0] + sorted(picked) + [nb]
        a, b = max(zip(bounds[:-1], bounds[1:]), key=lambda ab: ab[1] - ab[0])
        if b - a <= SECTION_MAX_BARS:
            break
        picked.append(max(range(a + SECTION_MIN_BARS, b - SECTION_MIN_BARS + 1), key=lambda i: weighted[i]))
    spans = list(zip([0] + sorted(picked), sorted(picked) + [nb]))
    kick, busy, cent = np.array(kick), np.array(busy), np.array(cent)
    # kick against the song's typical bar, so one pounding stretch doesn't make the rest look empty
    kick = np.minimum(2.0, kick / (float(np.median(kick)) or 1e-9))
    loud = f[:, 0]
    spans = _splitRisers(spans, kick, busy, cent, loud)
    secs = []
    for a, b in spans:
        sec = _section(edges[a], edges[b], energy, energyStep)
        sec["_bars"] = (a, b)
        sec["_kick"] = float(np.mean(kick[a:b]))
        sec["_busy"] = float(np.mean(busy[a:b]))
        sec["_riser"] = _riser(cent[a:b], busy[a:b], loud[a:b])
        if segments:
            mid = (sec["start_ms"] + sec["end_ms"]) / 2
            sec["ai_label"] = next((seg["label"] for seg in segments if seg["start_ms"] <= mid < seg["end_ms"]), "")
        secs.append(sec)
    def rel(vals):
        lo, hi = min(vals), max(vals)
        return [(v - lo) / (hi - lo) if hi > lo else 0.5 for v in vals]
    # intensity: loudness, busyness and kick together, ranked within this song, so a loud pad
    # without drums still reads as a quiet passage and a song that is loud throughout still has
    # a peak
    for sec, e, bz, kk in zip(secs, rel([s["energy"] for s in secs]), rel([s["_busy"] for s in secs]), rel([s["_kick"] for s in secs])):
        sec["_intensity"] = (e + bz + kk) / 3.0
        sec["level"] = 1 if sec["_intensity"] < 0.34 else 3 if sec["_intensity"] > 0.66 else 2
    _groupSections(secs, sim)
    _labelSections(secs)
    for sec in secs:
        for key in [key for key in sec if key.startswith("_")]:
            del sec[key]
    return secs


def _riser(cent, busy, loud):
    """Whether bars rise into what follows: brighter and busier (or louder) towards the end,
    as a filter sweep, noise riser or drum roll does."""
    n = len(cent)
    if n < 4:
        return False
    q = max(1, n // 4)
    brighter = float(np.mean(cent[-q:]) - np.mean(cent[:q]))
    busier = float(np.mean(busy[-q:]) / (np.mean(busy[:q]) or 1e-9))
    louder = float(np.mean(loud[-q:]) - np.mean(loud[:q]))
    return brighter > 0.03 and (busier > 1.25 or louder > 0.5)


def _splitRisers(spans, kick, busy, cent, loud):
    """A long section whose last bars rise into a fuller one: those bars become their own
    section (a build often shares its loop with what comes before it)."""
    out = []
    for n, (a, b) in enumerate(spans):
        nxt = spans[n + 1] if n + 1 < len(spans) else None
        tail = 8 if b - a >= 16 else 4
        if (nxt is not None and b - a >= tail + SECTION_MIN_BARS and _riser(cent[b - tail:b], busy[b - tail:b], loud[b - tail:b])
                and not _riser(cent[a:b - tail], busy[a:b - tail], loud[a:b - tail])
                and np.mean(kick[nxt[0]:nxt[1]]) + np.mean(loud[nxt[0]:nxt[1]]) * 0.1 > np.mean(kick[a:b - tail]) + np.mean(loud[a:b - tail]) * 0.1):
            out += [(a, b - tail), (b - tail, b)]
        else:
            out.append((a, b))
    return out


def _groupSections(secs, sim):
    """Letter the sections that sound alike (timbre and harmony bar against bar) A, B, C... in
    the order they first appear: a repeated part gets the same letter each time."""
    groups = []
    for sec in secs:
        a, b = sec["_bars"]
        best, bestSim = None, SECTION_GROUP_SIMILARITY
        for g in groups:
            s = float(np.mean([np.mean(sim[a:b, c:d]) for c, d in (m["_bars"] for m in g)]))
            if s >= bestSim:
                best, bestSim = g, s
        if best is None:
            groups.append([sec])
        else:
            best.append(sec)
    for n, g in enumerate(groups):
        letter = chr(ord("A") + n) if n < 26 else "Z%d" % (n - 25)
        for sec in g:
            sec["group"] = letter


def _section(a, b, energy, energyStep):
    i, j = int(a // energyStep), max(int(a // energyStep) + 1, int(b // energyStep))
    vals = energy[i:j]
    return {"start_ms": int(a), "end_ms": int(b), "energy": round(float(np.mean(vals)) if len(vals) else 0.0, 3)}


SECTION_LABELS = ("Intro", "Groove", "Build", "Drop", "Breakdown", "Outro")


def _labelSections(secs):
    """Suggested names from how sections compare within the song, not loudness alone.

    The Drop is the most intense part of the song (a repeated part when it repeats), so even a
    song that pounds throughout has one; a Breakdown loses the kick; a Build rises into a Drop
    or into something clearly fuller; the Intro runs from the start until the beat is in and the
    Outro from where it goes after the last fuller part; everything else with a beat is a
    Groove. Only a starting point."""
    n = len(secs)
    top = max(s["_intensity"] for s in secs)
    for s in secs:
        s["_drop"] = s["_kick"] >= 0.8 and s["_intensity"] >= top - 0.2
    # a repeat of a Drop that is a little less intense is still that Drop (a quieter take on the
    # same loop, such as a verse, is not)
    dropGroups = {s["group"] for s in secs if s["_drop"]}
    for s in secs:
        s["_drop"] = s["_drop"] or (s["_kick"] >= 0.8 and s["group"] in dropGroups and s["_intensity"] >= top - 0.3)
    for k, s in enumerate(secs):
        nxt = secs[k + 1] if k + 1 < n else None
        bars = s["_bars"][1] - s["_bars"][0]
        if (k > 0 and nxt is not None and bars <= 16 and s["_riser"] and
                (nxt["_drop"] or nxt["_kick"] > s["_kick"] + 0.2 or nxt["_intensity"] > s["_intensity"] + 0.25)):
            s["label"] = "Build"  # a riser into something fuller, however loud the riser itself is
        elif s["_drop"]:
            s["label"] = "Drop"
        # without a riser, only a short stretch that keeps some beat and leads straight into the
        # Drop (no beat at all before a Drop is a Breakdown)
        elif (nxt is not None and nxt["_drop"] and bars <= 8 and s["_kick"] >= 0.5 and nxt["_kick"] > s["_kick"] + 0.3):
            s["label"] = "Build"
        elif s["_kick"] < 0.5:
            s["label"] = "Breakdown"
        else:
            s["label"] = "Groove"
    for k, s in enumerate(secs):
        # an intro that rises for a while is Intro until its last Build
        leadsOn = s["label"] == "Build" and k + 1 < n and secs[k + 1]["label"] == "Build"
        if (s["label"] in ("Build", "Drop") and not leadsOn) or (s["_kick"] >= 0.7 and not (k == 0 and n > 1 and s["level"] < 3)):
            break
        s["label"] = "Intro"
    for k in range(n - 1, 0, -1):
        s = secs[k]
        if s["label"] in ("Build", "Drop") or (s["_kick"] >= 0.7 and not (k == n - 1 and s["level"] < 3)):
            break
        s["label"] = "Outro"


def _initComOnThisThread():
    # WASAPI is COM: each thread that uses it must initialise COM first
    import sys
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0)


class SoundcardSource:
    """A capture device through soundcard. device "" is the loopback of the system's default
    output (what's playing); otherwise a microphone or loopback id from listDevices()."""

    def __init__(self, device=""):
        import soundcard as sc
        self._sc = sc
        self.device = device
        if device:
            self._mic = sc.get_microphone(device, include_loopback=True)
            self.name = self._mic.name
        else:
            speaker = sc.default_speaker()
            self._mic = sc.get_microphone(speaker.id, include_loopback=True)
            self.name = speaker.name
            self._defaultId = speaker.id
        self.sampleRate = SAMPLE_RATE
        self._rec = None

    def __enter__(self):
        self._rec = self._mic.recorder(samplerate=self.sampleRate, blocksize=HOP)
        self._rec.__enter__()
        return self

    def __exit__(self, *exc):
        self._rec.__exit__(*exc)

    def read(self):
        data = self._rec.record(numframes=HOP)
        return data.mean(axis=1) if data.ndim > 1 else data

    def stillCurrent(self):
        """False when following the default output and the default has changed."""
        return bool(self.device) or self._sc.default_speaker().id == self._defaultId


class ArraySource:
    """Plays a signal as if it were captured, in real time (tests, and checking modes against a
    file). Loops when it reaches the end."""

    def __init__(self, samples, sampleRate=SAMPLE_RATE, name="test signal", loop=True):
        self.samples = np.asarray(samples, dtype=np.float64).reshape(-1)
        self.sampleRate = sampleRate
        self.name = name
        self.loop = loop
        self._pos = 0
        self._next = None

    def __enter__(self):
        self._next = time.monotonic()
        return self

    def __exit__(self, *exc):
        pass

    def read(self):
        if self._pos + HOP > len(self.samples):
            if not self.loop:
                raise EOFError("end of signal")
            self._pos = 0
        block = self.samples[self._pos:self._pos + HOP]
        self._pos += HOP
        self._next += HOP / self.sampleRate
        delay = self._next - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        return block

    def stillCurrent(self):
        return True


def listDevices():
    """Capture choices: the default output's loopback first (id ""), then every output's
    loopback and every input. Each is {"id", "name", "loopback"}."""
    import soundcard as sc
    default = sc.default_speaker()
    out = [{"id": "", "name": "System output (now: " + default.name + ")", "loopback": True}]
    for mic in sc.all_microphones(include_loopback=True):
        out.append({"id": mic.id, "name": mic.name + (" (playback)" if mic.isloopback else ""),
                    "loopback": bool(mic.isloopback)})
    return out


class AudioEngine:
    """Capture and analysis on a thread of its own. features() returns the latest features, or
    None when nothing recent has been analysed (stopped, starting, or the device failed)."""

    def __init__(self, sourceFactory=None):
        self.sourceFactory = sourceFactory or SoundcardSource
        self.device = ""
        self.tempoRange = (BPM_MIN, BPM_MAX)
        self._newRange = None
        self.deviceName = ""
        self.error = ""
        self._thread = None
        self._stop = threading.Event()
        self._retry = threading.Event()
        self._lock = threading.Lock()
        self._latest = None
        self._latestAt = 0.0

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, device=""):
        if self.running and device == self.device:
            return
        self.stop()
        self.device = device
        self.error = ""
        self._stop.clear()
        self._retry.clear()
        self._thread = threading.Thread(target=self._run, name="audioCapture", daemon=True)
        self._thread.start()

    def retry(self):
        """Try a failed device again now instead of at the next 2 s retry."""
        self._retry.set()

    def stop(self):
        self._stop.set()
        self._retry.set()
        if self._thread is not None:
            self._thread.join(2.0)
        self._thread = None
        with self._lock:
            self._latest = None

    def setTempoRange(self, lo, hi):
        """Change the tempo range, at once if capturing (applied between blocks, on the capture thread)."""
        self.tempoRange = (float(lo), float(hi))
        self._newRange = self.tempoRange

    def features(self):
        with self._lock:
            if self._latest is None or time.monotonic() - self._latestAt > STALE_S:
                return None
            return dict(self._latest)

    def _run(self):
        _initComOnThisThread()
        while not self._stop.is_set():
            try:
                with self.sourceFactory(self.device) as src:
                    self.deviceName = src.name
                    self.error = ""
                    analyzer = Analyzer(src.sampleRate, tempoRange=self.tempoRange)
                    self._newRange = None
                    checkAt = time.monotonic() + 5.0
                    while not self._stop.is_set():
                        if self._newRange is not None:
                            analyzer.setTempoRange(*self._newRange)
                            self._newRange = None
                        f = analyzer.process(src.read())
                        with self._lock:
                            self._latest = f
                            self._latestAt = time.monotonic()
                        if time.monotonic() >= checkAt:
                            checkAt = time.monotonic() + 5.0
                            if not src.stillCurrent():
                                break  # the default output changed: reopen on the new one
            except Exception as e:  # a device unplugged or a driver error: report it and retry
                self.error = (type(e).__name__ + ": " + str(e)).strip()
                with self._lock:
                    self._latest = None
                self._retry.wait(2.0)
                self._retry.clear()


def _id3Text(data):
    """A text frame's value (first string), in its declared encoding."""
    if not data:
        return ""
    enc, raw = data[0], data[1:]
    codec = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}.get(enc, "latin-1")
    text = raw.decode(codec, errors="replace")
    return text.split("\x00")[0].strip()


def _id3Tags(path):
    """Artist and title from an MP3's ID3v2 tag (v2.3 and v2.4 text frames), or {}."""
    with open(path, "rb") as f:
        head = f.read(10)
        if len(head) < 10 or head[:3] != b"ID3" or head[3] not in (3, 4):
            return {}
        size = (head[6] << 21) | (head[7] << 14) | (head[8] << 7) | head[9]
        body = f.read(size)
    if head[5] & 0x40:  # an extended header comes first
        ext = int.from_bytes(body[:4], "big")
        body = body[(ext if head[3] == 4 else ext + 4):]
    found, pos = {}, 0
    while pos + 10 <= len(body):
        fid = body[pos:pos + 4]
        if not fid.strip(b"\x00"):
            break
        raw = body[pos + 4:pos + 8]
        # v2.4 frame sizes are syncsafe, v2.3 plain
        n = ((raw[0] << 21) | (raw[1] << 14) | (raw[2] << 7) | raw[3]) if head[3] == 4 else int.from_bytes(raw, "big")
        if fid in (b"TPE1", b"TIT2"):
            found["artist" if fid == b"TPE1" else "song"] = _id3Text(body[pos + 10:pos + 10 + n])
        pos += 10 + n
    return {k: v for k, v in found.items() if v}


def songTags(path, name=None):
    """{"artist", "song"} for a song file: from its tags (ID3 in MP3s; the title and artist
    soundfile reads from WAV, FLAC, OGG), else from its file name (or name, for an upload kept
    under a temporary one) like "Artist - Title" or "02 Title". Either may be empty."""
    tags = {}
    try:
        if str(path).lower().endswith(".mp3"):
            tags = _id3Tags(path)
        elif songAvailable():
            import soundfile
            with soundfile.SoundFile(path) as f:
                tags = {k: (getattr(f, a, "") or "").strip() for k, a in (("artist", "artist"), ("song", "title"))}
    except (OSError, RuntimeError, ValueError):
        tags = {}
    stem = re.sub(r"^\d{1,3}[\s._-]+", "", os.path.splitext(os.path.basename(str(name or path)))[0]).replace("_", " ").strip()
    artist, sep, title = stem.partition(" - ")
    guess = {"artist": artist.strip(), "song": title.strip()} if sep else {"artist": "", "song": stem}
    return {"artist": tags.get("artist") or guess["artist"], "song": tags.get("song") or guess["song"]}
