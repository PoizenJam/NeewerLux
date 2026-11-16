"""MIDI clock input for NeewerLux: tempo, beats and transport (Start, Continue, Stop, Song
Position) from a DAW, drum machine or sequencer, so sound modes can follow its beat exactly
and its transport can play sequences.

MidiClock is the clock logic, fed raw status bytes; it knows nothing about devices, so tests
drive it directly. WinMidiInput reads a Windows MIDI input through winmm (ctypes): python-rtmidi
has no wheels for the Python versions NeewerLux ships with, and winmm needs nothing installed.
MidiManager ties an input to a clock and reports transport changes.
"""
import queue
import sys
import threading
import time
from collections import deque

CLOCKS_PER_BEAT = 24        # MIDI clock pulses per quarter note
CLOCKS_PER_STEP = 6         # Song Position counts sixteenth notes, six pulses each
TEMPO_CLOCKS = 48           # pulses the tempo is averaged over (two beats): steady, and follows a change within a bar
STALE_S = 0.5               # no clock for this long: the source stopped sending (or was unplugged)

CLOCK, START, CONTINUE, STOP, SONG_POSITION = 0xF8, 0xFA, 0xFB, 0xFC, 0xF2


class MidiClock:
    """Feed it MIDI bytes; features() gives a tempo and beat clock in the same keys as the audio
    analysis (bpm, beat, beat_phase, beat_t), or None when no clock is arriving."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.ticks = deque(maxlen=TEMPO_CLOCKS + 1)
        self.pulses = 0          # since Start (or the last Song Position), for the beat count
        self.beat = 0            # counts up on each beat, like the audio analysis
        self.lastBeatT = None
        self.playing = False
        self.transportSeen = False  # a source that never sends Start/Stop (a bare clock) counts beats always
        self.position = 0        # Song Position, in sixteenth notes
        self.lastTick = None

    def feed(self, status, data1=0, data2=0, t=None):
        """One message. Returns the transport event it caused ("start", "continue", "stop",
        "position") or None."""
        t = self.clock() if t is None else t
        with self.lock:
            if status == CLOCK:
                self.ticks.append(t)
                self.lastTick = t
                if self.playing or not self.transportSeen:
                    if self.pulses % CLOCKS_PER_BEAT == 0:
                        self.beat += 1
                        self.lastBeatT = t
                    self.pulses += 1
                    if self.pulses % CLOCKS_PER_STEP == 0:
                        self.position += 1
                return None
            if status == START:
                self.transportSeen = True
                self.playing = True
                self.pulses = 0
                self.position = 0
                return "start"
            if status == CONTINUE:
                self.transportSeen = True
                self.playing = True
                return "continue"
            if status == STOP:
                self.transportSeen = True
                self.playing = False
                return "stop"
            if status == SONG_POSITION:
                self.position = (data1 & 0x7F) | ((data2 & 0x7F) << 7)
                self.pulses = self.position * CLOCKS_PER_STEP
                return "position"
            return None

    def bpm(self):
        with self.lock:
            return self._bpm()

    def _bpm(self):
        if len(self.ticks) < 7:  # a quarter of a beat: too few pulses to time
            return 0.0
        span = self.ticks[-1] - self.ticks[0]
        if span <= 0:
            return 0.0
        return 60.0 / (span / (len(self.ticks) - 1) * CLOCKS_PER_BEAT)

    def receiving(self, now=None):
        now = self.clock() if now is None else now
        return self.lastTick is not None and now - self.lastTick <= STALE_S

    def features(self, now=None):
        now = self.clock() if now is None else now
        with self.lock:
            if not (self.lastTick is not None and now - self.lastTick <= STALE_S):
                return None
            bpm = self._bpm()
            if bpm <= 0:
                return None
            period = 60.0 / bpm
            phase = 0.0 if self.lastBeatT is None else min(1.0, max(0.0, (now - self.lastBeatT) / period))
            return {"bpm": round(bpm, 2), "beat": self.beat, "beat_phase": round(phase, 3), "beat_t": self.lastBeatT,
                    "confidence": 1.0}

    def status(self, now=None):
        with self.lock:
            return {"bpm": round(self._bpm(), 2), "playing": self.playing, "position": self.position}


# ------------------------------------------------------------------ Windows MIDI input

def available():
    """(True, "") when MIDI input can be read here, else (False, why)."""
    if sys.platform != "win32":
        return False, "MIDI clock input is Windows-only for now"
    return True, ""


MIM_DATA = 0x3C3
CALLBACK_FUNCTION = 0x30000


_WINMM = None


def _winmm():
    global _WINMM
    if _WINMM is None:
        import ctypes
        from ctypes import wintypes
        winmm = ctypes.WinDLL("winmm")

        class MIDIINCAPSW(ctypes.Structure):
            _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD), ("vDriverVersion", wintypes.UINT),
                        ("szPname", wintypes.WCHAR * 32), ("dwSupport", wintypes.DWORD)]
        # declared, so 64-bit arguments (pointers, DWORD_PTR) aren't passed as 32-bit ints
        winmm.midiInGetNumDevs.restype = wintypes.UINT
        winmm.midiInGetDevCapsW.argtypes = [ctypes.c_size_t, ctypes.c_void_p, wintypes.UINT]
        winmm.midiInOpen.argtypes = [ctypes.POINTER(wintypes.HANDLE), wintypes.UINT, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD]
        for fn in (winmm.midiInStart, winmm.midiInStop, winmm.midiInReset, winmm.midiInClose):
            fn.argtypes = [wintypes.HANDLE]
        for fn in (winmm.midiInGetDevCapsW, winmm.midiInOpen, winmm.midiInStart, winmm.midiInStop, winmm.midiInReset, winmm.midiInClose):
            fn.restype = wintypes.UINT
        _WINMM = (ctypes, wintypes, winmm, MIDIINCAPSW)
    return _WINMM


def listInputs():
    """Names of the MIDI inputs, in device order ([] where MIDI isn't available)."""
    if not available()[0]:
        return []
    ctypes, wintypes, winmm, CAPS = _winmm()
    names = []
    for i in range(winmm.midiInGetNumDevs()):
        caps = CAPS()
        if winmm.midiInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
            names.append(caps.szPname)
    return names


class WinMidiInput:
    """One open Windows MIDI input, calling onMessage(status, data1, data2) for each short
    message on winmm's own thread."""

    def __init__(self, name, onMessage):
        self.name = name
        self.onMessage = onMessage
        self._handle = None
        self._callback = None

    def open(self):
        ctypes, wintypes, winmm, _ = _winmm()
        names = listInputs()
        if self.name not in names:
            raise OSError("MIDI input " + repr(self.name) + " isn't connected")
        proto = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.UINT, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t)

        def handler(handle, msg, instance, param1, param2):
            if msg == MIM_DATA:
                self.onMessage(param1 & 0xFF, (param1 >> 8) & 0x7F, (param1 >> 16) & 0x7F)
        self._callback = proto(handler)  # kept: winmm calls it until the input is closed
        handle = wintypes.HANDLE()
        err = winmm.midiInOpen(ctypes.byref(handle), names.index(self.name), ctypes.cast(self._callback, ctypes.c_void_p),
                               0, CALLBACK_FUNCTION)
        if err:
            raise OSError("couldn't open MIDI input " + repr(self.name) + " (error " + str(err) + "; another program may have it)")
        self._handle = handle
        winmm.midiInStart(handle)

    def close(self):
        if self._handle is None:
            return
        _, _, winmm, _ = _winmm()
        winmm.midiInStop(self._handle)
        winmm.midiInReset(self._handle)
        winmm.midiInClose(self._handle)
        self._handle = None


class MidiManager:
    """The chosen MIDI input and its clock. onTransport(event, clock) is called for Start,
    Continue, Stop and Song Position, in order, on a thread of its own: winmm's callback must
    return quickly, and starting a sequence doesn't."""

    def __init__(self, inputFactory=None, onTransport=None):
        self.inputFactory = inputFactory or WinMidiInput
        self.onTransport = onTransport
        self.device = ""
        self.error = ""
        self.clock = MidiClock()
        self._input = None
        self._events = queue.Queue()
        threading.Thread(target=self._dispatch, name="midiTransport", daemon=True).start()

    def _dispatch(self):
        while True:
            event, clock = self._events.get()
            try:
                self.onTransport(event, clock)
            finally:
                self._events.task_done()

    def wait(self):
        """Until every transport event so far has been handled (for tests)."""
        self._events.join()

    def start(self, device):
        """Open the named input ("" closes it). Returns "" or the error."""
        self.stop()
        self.device = str(device or "")
        self.error = ""
        if not self.device:
            return ""
        self.clock = MidiClock()
        try:
            self._input = self.inputFactory(self.device, self._message)
            self._input.open()
        except Exception as e:  # unplugged, in use by another program, or a driver error
            self._input = None
            self.error = (type(e).__name__ + ": " + str(e)).strip()
        return self.error

    def stop(self):
        if self._input is not None:
            self._input.close()
            self._input = None

    @property
    def connected(self):
        return self._input is not None

    def features(self):
        return self.clock.features() if self._input is not None else None

    def _message(self, status, data1, data2):
        event = self.clock.feed(status, data1, data2)
        if event and self.onTransport is not None:
            self._events.put((event, self.clock))
