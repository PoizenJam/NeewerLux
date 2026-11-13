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

import math
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
BPM_MIN, BPM_MAX = 60.0, 200.0
BPM_PRIOR = 120.0          # tempos far from this (in octaves) are less likely
STALE_S = 0.5              # features older than this are treated as no signal

_captureState = None


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

    def __init__(self, sampleRate=SAMPLE_RATE, hop=HOP):
        self.sr = float(sampleRate)
        self.hop = int(hop)
        self.fps = self.sr / self.hop
        self.window = np.hanning(FFT_SIZE).astype(np.float64)
        self._winPower = float(np.mean(self.window ** 2))
        freqs = np.fft.rfftfreq(FFT_SIZE, 1.0 / self.sr)
        self.freqs = freqs
        self.bandMasks = {k: (freqs >= lo) & (freqs < hi) for k, (lo, hi) in BANDS.items()}
        self.centroidMask = (freqs >= 40.0) & (freqs <= 12000.0)
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
        if self.quiet:
            flux = 0.0

        self.onsetEnv = np.roll(self.onsetEnv, -1)
        self.onsetEnv[-1] = flux

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
        bpm = BPM_MIN
        while bpm <= BPM_MAX:
            lag = 60.0 * self.fps / bpm
            # the period itself and its double support a tempo. A strong peak at half the period
            # counts against it, but only when twice this tempo is itself a plausible tempo:
            # eighth notes over a 124 BPM beat are not a 248 BPM song
            score = at(lag) + 0.5 * at(2 * lag)
            if 2 * bpm <= BPM_MAX:
                score -= 0.35 * max(0.0, at(lag / 2))
            score *= math.exp(-0.5 * (math.log2(bpm / BPM_PRIOR) / 0.8) ** 2)
            if score > bestScore:
                best, bestScore = bpm, score
            bpm += 0.25
        if best is None or bestScore <= 0:
            return
        lag = 60.0 * self.fps / best
        cand = 60.0 * self.fps / lag
        self.confidence = float(max(0.0, min(1.0, at(lag))))
        if self.bpm <= 0:
            self.bpm = cand
        elif abs(cand / self.bpm - 1.0) < 0.04:
            self.bpm += (cand - self.bpm) * 0.3
        elif self._pendingBpm is not None and abs(cand / self._pendingBpm - 1.0) < 0.04:
            self._pendingCount += 1
            if self._pendingCount >= 3:  # a new tempo three times running: the song changed tempo
                self.bpm = cand
                self._pendingBpm = None
        else:
            self._pendingBpm, self._pendingCount = cand, 1
        self.period = 60.0 / self.bpm
        self._alignPhase()

    def _alignPhase(self):
        """Find where the beats fall: the offset whose comb of beat times collects the most
        onset energy over the last few seconds."""
        p = self.period * self.fps
        filled = min(self.frames, self.histLen)
        k = int(min(4.0 * self.fps, filled) // p)
        if k < 2:
            return
        env = self.onsetEnv
        best, bestScore = 0, -1.0
        for off in range(int(math.ceil(p))):
            idx = [len(env) - 1 - int(round(off + j * p)) for j in range(k)]
            score = float(sum(env[i] for i in idx if i >= 0))
            if score > bestScore:
                best, bestScore = off, score
        lastBeat = self.t - best / self.fps
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
        if self.silent and self.t - self.silentSince > 1.0:
            self.nextBeat = None  # the beat clock stops in silence and re-aligns when sound returns
            return
        while self.t >= self.nextBeat:
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
    computed in chunks (a long song as one FFT matrix would need gigabytes)."""
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
    out = {k: np.zeros(n) for k in ("rms", "low", "mid", "high", "centroid", "flux", "lowflux")}
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
        bands = np.zeros((m, 24))
        valid = bandIdx >= 0
        for b in range(24):
            sel = valid & (bandIdx == b)
            if np.any(sel):
                bands[:, b] = np.sum(power[:, sel], axis=1)
        logMag = np.log1p(1e4 * bands)
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


def analyzeSong(samples, sampleRate, bpm=None, offsetMs=None):
    """Analyse a whole mono song. Assumes a steady tempo (most produced music has one).

    bpm and offsetMs, when given, are used instead of the estimates (offsetMs: when the first
    beat falls). Returns {"duration_ms", "bpm", "offset_ms", "confidence", "beats" (ms),
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

    sections = _sections(feats, fps, bars, durationMs, energy, step)
    return {"duration_ms": durationMs, "bpm": round(bpm, 2), "offset_ms": int(round(offsetMs)), "confidence": confidence,
            "beats": beats, "bars": bars, "energy": [round(float(v), 3) for v in energy], "energy_step_ms": step,
            "waveform": [round(float(v), 3) for v in waveform], "sections": sections}


def _sections(feats, fps, bars, durationMs, energy, energyStep):
    """Split the song where its sound changes, on bar lines: per bar, loudness, bass, treble,
    brightness and busyness; a boundary where the bars before and after differ most."""
    edges = [0] + [b for b in bars if b > 0] + [durationMs]
    edges = sorted(set(edges))
    if len(edges) < 3:
        return [_section(0, durationMs, energy, energyStep)]
    rows = []
    for a, b in zip(edges[:-1], edges[1:]):
        i, j = int(a * fps / 1000.0), max(int(a * fps / 1000.0) + 1, int(b * fps / 1000.0))
        seg = {k: feats[k][i:j] for k in ("rms", "low", "high", "centroid", "flux")}
        rows.append([20.0 * math.log10(max(float(np.sqrt(np.mean(seg["rms"] ** 2))), 1e-9)),
                     20.0 * math.log10(max(float(np.mean(seg["low"])), 1e-9)),
                     20.0 * math.log10(max(float(np.mean(seg["high"])), 1e-9)),
                     float(np.mean(seg["centroid"])) * 30.0,
                     float(np.mean(seg["flux"])) * 30.0 / (float(np.max(feats["flux"])) or 1.0)])
    f = np.array(rows)
    f = (f - np.mean(f, axis=0)) / (np.std(f, axis=0) + 1e-9)
    nb = len(f)
    w = SECTION_NOVELTY_BARS
    novelty = np.zeros(nb)
    for i in range(1, nb):
        a, b = f[max(0, i - w):i], f[i:min(nb, i + w)]
        if len(a) and len(b):
            novelty[i] = float(np.linalg.norm(np.mean(a, axis=0) - np.mean(b, axis=0)))
    # phrases are usually 4 or 8 bars long: favour boundaries on those, counting from the first
    # bar (row 0 is the stretch before it when the first beat isn't at 0)
    first = 1 if edges[1] in bars and edges[0] not in bars else 0
    weighted = novelty * np.array([1.3 if (i - first) % 8 == 0 else 1.15 if (i - first) % 4 == 0 else 1.0 for i in range(nb)])
    threshold = float(np.mean(novelty[1:]) + 0.25 * np.std(novelty[1:])) if nb > 2 else 1e9
    picked = []
    for i in np.argsort(-weighted):
        i = int(i)
        if i < SECTION_MIN_BARS or nb - i < SECTION_MIN_BARS or weighted[i] < threshold:
            continue
        if all(abs(i - p) >= SECTION_MIN_BARS for p in picked):
            picked.append(i)
    # a long stretch that changes little is still split, where it changes most (a draft needs
    # somewhere to move)
    while True:
        bounds = [0] + sorted(picked) + [nb]
        longest = max(zip(bounds[:-1], bounds[1:]), key=lambda ab: ab[1] - ab[0])
        a, b = longest
        if b - a <= SECTION_MAX_BARS:
            break
        inside = [i for i in range(a + SECTION_MIN_BARS, b - SECTION_MIN_BARS + 1)]
        picked.append(max(inside, key=lambda i: weighted[i]))
    cuts = [0] + sorted(edges[i] for i in picked) + [durationMs]
    secs = [_section(a, b, energy, energyStep) for a, b in zip(cuts[:-1], cuts[1:])]
    # intensity: loudness and busyness (onsets) together, so a loud pad without drums still
    # reads as a quiet passage
    busy = []
    for sec in secs:
        i, j = int(sec["start_ms"] * fps / 1000.0), max(int(sec["start_ms"] * fps / 1000.0) + 1, int(sec["end_ms"] * fps / 1000.0))
        busy.append(float(np.mean(feats["flux"][i:j])))
    def rel(vals):
        lo, hi = min(vals), max(vals)
        return [(v - lo) / (hi - lo) if hi > lo else 0.5 for v in vals]
    for sec, e, b in zip(secs, rel([sec["energy"] for sec in secs]), rel(busy)):
        intensity = 0.5 * e + 0.5 * b
        sec["level"] = 1 if intensity < 0.34 else 3 if intensity > 0.66 else 2
    _labelSections(secs)
    return secs


def _section(a, b, energy, energyStep):
    i, j = int(a // energyStep), max(int(a // energyStep) + 1, int(b // energyStep))
    vals = energy[i:j]
    return {"start_ms": int(a), "end_ms": int(b), "energy": round(float(np.mean(vals)) if len(vals) else 0.0, 3)}


def _labelSections(secs):
    """Suggested names from the energy levels; only a starting point for a person to rename."""
    for k, s in enumerate(secs):
        nxt = secs[k + 1]["level"] if k + 1 < len(secs) else None
        prv = secs[k - 1]["level"] if k > 0 else None
        if k == 0 and len(secs) > 1 and s["level"] < 3:
            s["label"] = "Intro"
        elif k == len(secs) - 1 and len(secs) > 1 and s["level"] < 3:
            s["label"] = "Outro"
        elif s["level"] == 3:
            s["label"] = "Chorus"
        elif nxt == 3 and s["level"] == 2:
            s["label"] = "Build"
        elif s["level"] == 1 and prv == 3:
            s["label"] = "Break"
        else:
            s["label"] = "Verse"


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
                    analyzer = Analyzer(src.sampleRate)
                    checkAt = time.monotonic() + 5.0
                    while not self._stop.is_set():
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
