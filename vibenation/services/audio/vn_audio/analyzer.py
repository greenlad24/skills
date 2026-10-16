"""Measures the mix: per-channel level and spectrum, master loudness (BS.1770),
true peak and limiter gain reduction. Runs as its own JACK client; the process
callback only queues buffers and the maths happens in a worker thread.
"""

from __future__ import annotations

import math
import queue
import threading
import time
from collections import deque

import jack
import numpy as np
from scipy import signal

SR = 48000
N_BANDS = 32
FFT = 4096


def db(x: float) -> float:
    return 20 * math.log10(max(x, 1e-9))


def k_weighting(sr: int) -> np.ndarray:
    """BS.1770-4 K-weighting at 48 kHz (pre-filter shelf + RLB high-pass), as SOS."""
    assert sr == 48000, 'mix engine runs at 48 kHz'
    shelf = [1.53512485958697, -2.69169618940638, 1.19839281085285, 1.0, -1.69065929318241, 0.73248077421585]
    rlb = [1.0, -2.0, 1.0, 1.0, -1.99004745483398, 0.99007225036621]
    return np.array([shelf, rlb])


def band_edges(n: int = N_BANDS, lo: float = 30, hi: float = 16000) -> np.ndarray:
    edges = np.geomspace(lo, hi, n + 1)
    return np.clip((edges / (SR / 2) * (FFT // 2)).astype(int), 1, FFT // 2)


class Loudness:
    """Momentary (400 ms), short-term (3 s) and gated integrated loudness."""

    def __init__(self, sr: int):
        self.sos = k_weighting(sr)
        self.zi = [signal.sosfilt_zi(self.sos) * 0 for _ in range(2)]
        self.blocks: deque[float] = deque(maxlen=30)  # 100 ms mean-square blocks (3 s)
        self.gating: list[float] = []  # 400 ms block energies for the integrated value
        self.sr = sr

    def reset_integrated(self) -> None:
        self.gating.clear()

    def push(self, stereo: np.ndarray) -> None:
        """stereo: (n, 2) float samples for ~100 ms."""
        ms = 0.0
        for c in range(2):
            y, self.zi[c] = signal.sosfilt(self.sos, stereo[:, c], zi=self.zi[c])
            ms += float(np.mean(y * y))
        self.blocks.append(ms)
        if len(self.blocks) >= 4:
            m = float(np.mean(list(self.blocks)[-4:]))
            if -0.691 + 10 * math.log10(max(m, 1e-12)) > -70:  # absolute gate
                self.gating.append(m)

    @staticmethod
    def _lufs(ms: float) -> float:
        return -0.691 + 10 * math.log10(max(ms, 1e-12))

    def momentary(self) -> float:
        return self._lufs(float(np.mean(list(self.blocks)[-4:]))) if self.blocks else -70

    def short_term(self) -> float:
        return self._lufs(float(np.mean(self.blocks))) if self.blocks else -70

    def integrated(self) -> float:
        if not self.gating:
            return -70
        g = np.array(self.gating[-36000:])  # last hour
        rel = self._lufs(float(np.mean(g))) - 10  # relative gate
        kept = g[-0.691 + 10 * np.log10(np.maximum(g, 1e-12)) > rel]
        return self._lufs(float(np.mean(kept))) if len(kept) else -70


class Analyzer:
    """Inputs: 16 channel taps (post-processing, pre-fader), master pre-limiter L/R, master L/R."""

    def __init__(self, client_name: str = 'vn_meter'):
        self.client = jack.Client(client_name, no_start_server=True)
        self.sr = self.client.samplerate
        self.ins = [self.client.inports.register(f'ch_{n}') for n in range(1, 17)]
        self.pre = [self.client.inports.register(f'pre_{s}') for s in 'lr']
        self.master = [self.client.inports.register(f'master_{s}') for s in 'lr']
        self.raw = [self.client.inports.register(f'raw_{n}') for n in range(1, 17)]  # venue feed, before any processing
        self.q: queue.Queue[np.ndarray] = queue.Queue(maxsize=400)
        self.hist = np.zeros((FFT, 16), dtype=np.float32)
        self.mhist = np.zeros(FFT, dtype=np.float32)
        self.loud = Loudness(self.sr)
        self.edges = band_edges()
        self.window = np.hanning(FFT).astype(np.float32)
        self.frame: dict = {}
        self.listeners: list = []
        self.peak_hold = np.full(16, -90.0)
        self.tp_tail: np.ndarray | None = None
        self.client.set_process_callback(self._process)
        threading.Thread(target=self._work, name='analyzer', daemon=True).start()
        self.client.activate()

    def _process(self, frames: int) -> None:
        buf = np.empty((frames, 36), dtype=np.float32)
        for i, p in enumerate(self.ins + self.pre + self.master + self.raw):
            buf[:, i] = p.get_array()
        try:
            self.q.put_nowait(buf)
        except queue.Full:
            pass

    def _bands(self, x: np.ndarray) -> list[float]:
        mag = np.abs(np.fft.rfft(x * self.window))[: FFT // 2] / (FFT / 4)
        e = self.edges
        return [round(db(float(np.max(mag[e[i] : max(e[i + 1], e[i] + 1)]))), 1) for i in range(N_BANDS)]

    def _work(self) -> None:
        pending: list[np.ndarray] = []
        need = int(self.sr / 10)  # analyse every 100 ms
        tp_up = 4
        while True:
            pending.append(self.q.get())
            if sum(len(b) for b in pending) < need:
                continue
            blk = np.concatenate(pending)
            pending.clear()
            ch, pre, mst, raw = blk[:, :16], blk[:, 16:18], blk[:, 18:20], blk[:, 20:36]
            n = len(blk)
            self.hist = np.roll(self.hist, -n, axis=0)
            self.hist[-n:] = ch[-FFT:] if n >= FFT else ch
            mono = mst.mean(axis=1)
            self.mhist = np.roll(self.mhist, -n)
            self.mhist[-n:] = mono[-FFT:] if n >= FFT else mono

            peak = np.max(np.abs(ch), axis=0)
            rms = np.sqrt(np.mean(ch * ch, axis=0))
            raw_rms = np.sqrt(np.mean(raw * raw, axis=0))
            self.loud.push(mst.astype(np.float64))
            # 4x oversampled true peak; keep a short tail so block edges don't ring.
            tp_in = np.concatenate([self.tp_tail, mst]) if self.tp_tail is not None else mst
            self.tp_tail = mst[-64:]
            up = signal.resample_poly(tp_in, tp_up, 1, axis=0)[tp_up * 64 if len(tp_in) > len(mst) else 0 :]
            true_peak = db(float(np.max(np.abs(up))))
            pre_peak = db(float(np.max(np.abs(pre))))
            post_peak = db(float(np.max(np.abs(mst))))
            self.frame = {
                't': time.time(),
                'peak': [round(db(float(v)), 1) for v in peak],
                'rms': [round(db(float(v)), 1) for v in rms],
                'raw': [round(db(float(v)), 1) for v in raw_rms],
                'spec': [self._bands(self.hist[:, i]) for i in range(16)],
                'master': {
                    'lufsM': round(self.loud.momentary(), 1),
                    'lufsS': round(self.loud.short_term(), 1),
                    'lufsI': round(self.loud.integrated(), 1),
                    'truePeak': round(true_peak, 1),
                    'prePeak': round(pre_peak, 1),
                    'peak': round(post_peak, 1),
                    'spec': self._bands(self.mhist),
                },
            }
            for fn in list(self.listeners):
                try:
                    fn(self.frame)
                except Exception:  # noqa: BLE001 - a bad listener must not stop metering
                    pass
