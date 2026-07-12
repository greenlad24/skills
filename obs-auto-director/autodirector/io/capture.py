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
                 blocksize: int = 1024, loopback: bool = False):
        self.device = device
        self.samplerate = samplerate
        self.channels = channels
        self.blocksize = blocksize
        self.loopback = loopback
        self._chunks: List[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream = None
        self._loop_stop: Optional[threading.Event] = None
        self._last_cb_t = 0.0
        self.samples_captured = 0

    # ------------------------------------------------------------------
    @staticmethod
    def list_devices() -> str:
        import sounddevice as sd
        return str(sd.query_devices())

    def start(self) -> None:
        if self.loopback:
            self._start_loopback()
            return
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

    def _start_loopback(self) -> None:
        """Windows: WASAPI loopback — capture any OUTPUT device (e.g. what
        OBS monitors to) natively, no virtual cable installed. The
        capability ships inside the app (`soundcard` is bundled).

        Hardening (see docs/TEAM_REVIEW: loopback research):
        * never capture 1 channel (documented soundcard/WASAPI garbage
          bug) — capture >=2 and downmix
        * render keep-alive silence into the endpoint so loopback packets
          keep flowing during quiet moments; otherwise the watchdog would
          read silence as 'audio dead' and freeze cuts, and the audio
          clock would drift on soundcard's wall-clock zero-fill heuristic
        * blocksize > numframes per the soundcard README
        * COM objects created on the worker thread; exceptions logged
        """
        import logging
        log = logging.getLogger("autodirector.capture")
        import soundcard as sc  # bundled on Windows builds

        spk = sc.get_speaker(str(self.device)) if self.device \
            else sc.default_speaker()
        cap_ch = max(2, self.channels)
        self._loop_stop = threading.Event()
        stop = self._loop_stop

        # Keep-alive: silence into the endpoint keeps the render engine
        # pumping (PortAudio #935 class of starvation). Best-effort — the
        # soundcard >=0.4.3 zero-fill heuristic remains the fallback.
        self._keepalive = None
        try:
            import sounddevice as sd
            idx = next(
                i for i, d in enumerate(sd.query_devices())
                if d["max_output_channels"] > 0 and spk.name in d["name"]
                and sd.query_hostapis(d["hostapi"])["name"]
                == "Windows WASAPI")
            self._keepalive = sd.OutputStream(
                device=idx, samplerate=self.samplerate, channels=1,
                dtype="float32",
                callback=lambda out, f, t, s: out.fill(0.0))
            self._keepalive.start()
        except Exception:
            self._keepalive = None

        # Readiness handshake: device activation happens on the worker
        # thread, but start() must not report success for a dead capture —
        # rebuild()/the UI rely on start() raising synchronously.
        ready = threading.Event()
        state = {"error": None}

        def _run():
            try:
                mic = sc.get_microphone(spk.name, include_loopback=True)
                with mic.recorder(samplerate=self.samplerate,
                                  channels=cap_ch,
                                  blocksize=self.blocksize * 2) as rec:
                    ready.set()
                    while not stop.is_set():
                        data = rec.record(numframes=self.blocksize)
                        if self.channels == 1:
                            data = data.mean(axis=1, keepdims=True)
                        elif data.shape[1] > self.channels:
                            data = data[:, :self.channels]
                        with self._lock:
                            self._chunks.append(
                                np.ascontiguousarray(data,
                                                     dtype=np.float32))
                        self._last_cb_t = time.monotonic()
                        self.samples_captured += len(data)
            except Exception as e:
                # alive() decays to False -> the app freezes cuts; leave
                # a diagnostic and drop the running marker immediately.
                log.exception("loopback capture thread died")
                state["error"] = e
                self._stream = None
                ready.set()

        self._loop_thread = threading.Thread(target=_run, daemon=True,
                                             name="wasapi-loopback")
        self._loop_thread.start()
        if not ready.wait(timeout=5.0):
            state["error"] = RuntimeError(
                "loopback capture did not start within 5s")
        if state["error"] is not None:
            self.stop()
            raise RuntimeError(
                f"WASAPI loopback capture failed: {state['error']}")
        self._last_cb_t = time.monotonic()
        self._stream = "loopback"  # marks the capture as running

    def stop(self) -> None:
        if self._loop_stop is not None:
            self._loop_stop.set()
            thread = getattr(self, "_loop_thread", None)
            if thread is not None:
                thread.join(timeout=2.0)  # record() returns within ~2 blocks
            self._loop_stop = None
            self._loop_thread = None
            keepalive = getattr(self, "_keepalive", None)
            if keepalive is not None:
                try:
                    keepalive.stop()
                    keepalive.close()
                except Exception:
                    pass
                self._keepalive = None
            self._stream = None
            return
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
