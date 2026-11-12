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
