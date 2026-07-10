"""Audio capture: device -> ring buffer, with a liveness watchdog.

macOS notes:
- CoreAudio allows multiple clients on one *input* device, so we can open
  the same interface OBS uses (band mixer, USB mics) with no extra install.
- For in-OBS-only mixes, set OBS Monitoring Device to BlackHole 2ch and
  capture BlackHole here (documented in the README).

sounddevice/PortAudio are imported lazily so the rest of the app (and the
test suite) never needs an audio stack present.
"""

from __future__ import annotations

import threading
import time
from typing import List, Optional

import numpy as np


class AudioCapture:
    """Opens an input device and buffers PCM chunks for the analyzer.

    The audio callback runs on the audio thread and only appends to a
    deque; the analyzer thread drains it with read(). If callbacks stop
    arriving (device unplugged, driver stall) `alive()` turns False —
    the app must treat that as *freeze cuts*, never as silence.
    """

    def __init__(self, device: Optional[object] = None,
                 samplerate: int = 48000, channels: int = 1,
                 blocksize: int = 1024):
        self.device = device
        self.samplerate = samplerate
        self.channels = channels
        self.blocksize = blocksize
        self._chunks: List[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream = None
        self._last_cb_t = 0.0
        self.samples_captured = 0

    # ------------------------------------------------------------------
    @staticmethod
    def list_devices() -> str:
        import sounddevice as sd
        return str(sd.query_devices())

    def start(self) -> None:
        import sounddevice as sd

        def _cb(indata, frames, time_info, status):
            with self._lock:
                self._chunks.append(np.copy(indata))
            self._last_cb_t = time.monotonic()
            self.samples_captured += frames

        self._stream = sd.InputStream(
            device=self.device, samplerate=self.samplerate,
            channels=self.channels, blocksize=self.blocksize,
            dtype="float32", callback=_cb)
        self._stream.start()
        self._last_cb_t = time.monotonic()

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

    # ------------------------------------------------------------------
    def read(self) -> Optional[np.ndarray]:
        """Drain all buffered audio as one array, or None if empty."""
        with self._lock:
            if not self._chunks:
                return None
            chunks, self._chunks = self._chunks, []
        return np.concatenate(chunks, axis=0)

    def alive(self, timeout_s: float = 0.5) -> bool:
        """True while the device is delivering callbacks."""
        return (self._stream is not None
                and (time.monotonic() - self._last_cb_t) < timeout_s)

    @property
    def audio_clock(self) -> float:
        """Stream time in seconds derived from captured samples — the
        director's clock (immune to wall-clock hiccups)."""
        return self.samples_captured / float(self.samplerate)
