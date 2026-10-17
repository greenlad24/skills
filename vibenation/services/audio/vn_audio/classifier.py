"""Live sound recognition: what is actually being played on the role-switching channels.

Channel 11 can be congas, a singing voice or a guest brass player; 15 sax or flute; 16
harmonica or a singing voice. Channels 9 and 10 are always voice, but the singer's register
(male/female, from the median pitch) moves the HPF, mud band and de-esser.

How it works (cheap, CPU only):
  * YAMNet (Google, AudioSet 521 classes, Apache-2.0) as TFLite, one 0.975 s window
    (15600 samples at 16 kHz) per channel at most every ~2 s, only while that source is
    playing. One window costs ~5-7 ms on one core.
  * DSP features on the same window: YIN pitch (median f0 + pitch strength) and an onset
    rate for percussiveness. They back up YAMNet where it is weak (it has no "conga" class)
    and give the register on 9/10.
  * Switcher: a role is switched only after 8 s of consistent classification (report:
    "Role switches require 8 seconds of consistent classification"); a human role-lock
    disables auto-switching on that channel.

Runs in a background thread at nice +10, single-threaded inference, never in the JACK
callback. The analyzer hands it raw venue blocks; the copy into the ring buffer is O(block).
"""

from __future__ import annotations

import csv
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy import signal

log = logging.getLogger('vn_audio.classifier')

MODEL_DIR = os.environ.get('VN_MODELS', os.path.join(os.path.dirname(__file__), '..', 'models'))
SR_IN, SR = 48000, 16000
WIN = 15600  # YAMNet input: 0.975 s at 16 kHz
WIN_IN = WIN * 3

ROLE_CHANNELS: dict[int, tuple[str, ...]] = {11: ('congas', 'voice', 'brass'), 15: ('sax', 'flute'), 16: ('harmonica', 'voice')}
REGISTER_CHANNELS = (9, 10)
WATCH = tuple(sorted(set(ROLE_CHANNELS) | set(REGISTER_CHANNELS)))

SWITCH_SECONDS = 8.0  # consistent classification needed before a role switch
REGISTER_SECONDS = 16.0  # a singer change is rarer than a role change: ask for twice as long
MAX_GAP = 6.0  # a streak survives silences/unclear windows up to this long
HOP = 2.0  # seconds between windows on one channel
MIN_CONF = 0.55  # a window below this confidence neither extends nor breaks a streak

# YAMNet class names per role (AudioSet ontology). Wind instrument counts half for sax and flute.
ROLE_CLASSES: dict[str, dict[str, float]] = {
    'voice': {'Speech': 0.6, 'Singing': 1.0, 'Choir': 1.0, 'Humming': 0.8, 'Rapping': 0.8, 'Vocal music': 0.7, 'Chant': 0.7, 'Yodeling': 0.7},
    'congas': {'Drum': 1.0, 'Percussion': 1.0, 'Tabla': 1.0, 'Drum roll': 0.8, 'Snare drum': 0.6, 'Bass drum': 0.6, 'Drum kit': 0.6,
               'Tambourine': 0.6, 'Cowbell': 0.6, 'Clapping': 0.5, 'Rattle (instrument)': 0.6, 'Wood block': 0.6, 'Salsa music': 0.4},
    'brass': {'Brass instrument': 1.0, 'Trombone': 1.0, 'Trumpet': 1.0, 'French horn': 1.0},
    'sax': {'Saxophone': 1.0, 'Clarinet': 0.6, 'Wind instrument, woodwind instrument': 0.5},
    'flute': {'Flute': 1.0, 'Wind instrument, woodwind instrument': 0.5},
    'harmonica': {'Harmonica': 1.0, 'Accordion': 0.7},
}
REGISTER_SPLIT_HZ = 240.0  # median sung f0: male singers mostly below, female above


# ---------------- model ----------------

class Yamnet:
    def __init__(self, model_dir: str = MODEL_DIR):
        from ai_edge_litert.interpreter import Interpreter  # pip ai-edge-litert (TFLite runtime)
        path = os.path.join(model_dir, 'yamnet.tflite')
        if not os.path.exists(path):
            raise FileNotFoundError(f'{path} missing: run services/audio/tools/fetch_models.sh')
        self.it = Interpreter(path, num_threads=1)
        self.it.allocate_tensors()
        self.inp = self.it.get_input_details()[0]['index']
        self.out = self.it.get_output_details()[0]['index']
        with open(os.path.join(model_dir, 'yamnet_class_map.csv')) as fh:
            self.names = [r['display_name'] for r in csv.DictReader(fh)]
        idx = {n: i for i, n in enumerate(self.names)}
        self.role_idx = {r: [(idx[c], w) for c, w in cl.items() if c in idx] for r, cl in ROLE_CLASSES.items()}
        self.lock = threading.Lock()

    def scores(self, x16: np.ndarray) -> np.ndarray:
        x = np.ascontiguousarray(x16[-WIN:], dtype=np.float32)
        if len(x) < WIN:
            x = np.pad(x, (WIN - len(x), 0))
        with self.lock:
            self.it.set_tensor(self.inp, x)
            self.it.invoke()
            return self.it.get_tensor(self.out)[0].copy()

    def role_scores(self, s: np.ndarray) -> dict[str, float]:
        return {r: float(max(s[i] * w for i, w in ix)) for r, ix in self.role_idx.items()}

    def top(self, s: np.ndarray, k: int = 3) -> list[tuple[str, float]]:
        return [(self.names[i], round(float(s[i]), 2)) for i in np.argsort(s)[::-1][:k]]


# ---------------- DSP features ----------------

def to16k(x48: np.ndarray) -> np.ndarray:
    return signal.resample_poly(np.asarray(x48, dtype=np.float32), 1, 3).astype(np.float32)


def yin(x: np.ndarray, sr: int = SR, fmin: float = 70.0, fmax: float = 1000.0, n: int = 1024, hop: int = 512) -> tuple[np.ndarray, np.ndarray]:
    """YIN (de Cheveigné & Kawahara 2002), vectorised. Returns per-frame f0 (Hz, 0 = unvoiced)
    and the minimum of the cumulative-mean-normalised difference (low = strongly periodic)."""
    tmin, tmax = int(sr / fmax), int(sr / fmin)
    if len(x) < n + tmax:
        return np.zeros(0), np.ones(0)
    frames = np.lib.stride_tricks.sliding_window_view(x, n + tmax)[::hop]
    w = n
    # difference function d(tau) = sum (x_j - x_{j+tau})^2 over a window of w, via FFT autocorrelation
    sq = np.cumsum(np.pad(frames * frames, ((0, 0), (1, 0))), axis=1)
    e0 = sq[:, w] - sq[:, 0]
    taus = np.arange(tmax + 1)
    e_tau = sq[:, taus + w] - sq[:, taus]
    nfft = 1 << int(np.ceil(np.log2(2 * (n + tmax))))
    F = np.fft.rfft(frames, nfft)
    A = np.fft.rfft(frames[:, :w], nfft)
    r = np.fft.irfft(F * np.conj(A), nfft)[:, : tmax + 1]
    d = e0[:, None] + e_tau - 2 * r
    d[:, 0] = 0
    cm = np.cumsum(d[:, 1:], axis=1) / np.arange(1, tmax + 1)
    dn = np.ones_like(d)
    dn[:, 1:] = d[:, 1:] / np.maximum(cm, 1e-12)
    seg = dn[:, tmin:]
    dmin = seg.min(axis=1)
    # first dip below threshold, else the global minimum
    below = seg < 0.15
    first = np.where(below.any(axis=1), below.argmax(axis=1), seg.argmin(axis=1))
    # walk to the local minimum after the first dip
    k = first.copy()
    for _ in range(8):
        nxt = np.minimum(k + 1, seg.shape[1] - 1)
        better = seg[np.arange(len(k)), nxt] < seg[np.arange(len(k)), k]
        k = np.where(better, nxt, k)
    tau = k + tmin
    f0 = np.where(dmin < 0.25, sr / np.maximum(tau, 1), 0.0)
    loud = e0 / w > 1e-7  # ignore near-silent frames
    f0 = np.where(loud, f0, 0.0)
    return f0, np.where(loud, dmin, 1.0)


def onset_rate(x: np.ndarray, sr: int = SR) -> tuple[float, float]:
    """Onsets per second (spectral-flux peaks) and attack sharpness (mean flux peak over median),
    a cheap percussiveness measure: hand drums score high on both."""
    f, t, Z = signal.stft(x, sr, nperseg=512, noverlap=512 - 160, boundary=None, padded=False)
    mag = np.log1p(100 * np.abs(Z))
    flux = np.maximum(0, np.diff(mag, axis=1)).sum(axis=0)
    if len(flux) < 5:
        return 0.0, 0.0
    med = float(np.median(flux)) + 1e-6
    thr = med * 2.5 + 0.5
    pk, _ = signal.find_peaks(flux, height=thr, distance=6)
    sharp = float(np.mean(flux[pk]) / med) if len(pk) else 0.0
    return len(pk) / (len(x) / sr), sharp


@dataclass
class Window:
    ch: int
    role: str | None  # best allowed role on a role channel (None = unclear)
    conf: float
    scores: dict[str, float]
    f0: float  # median f0 of voiced frames (Hz, 0 = none)
    voiced: float  # fraction of strongly periodic frames
    onsets: float
    sharp: float
    register: str | None = None
    reg_conf: float = 0.0
    top: list = field(default_factory=list)


def classify(model: Yamnet, ch: int, x48: np.ndarray) -> Window:
    """Classify one ~1 s window of a channel's raw input (48 kHz mono)."""
    x = to16k(x48)
    peak = float(np.max(np.abs(x))) or 1.0
    x = x / peak * 0.5  # level-independent (soundcheck trims vary)
    s = model.scores(x)
    rs = model.role_scores(s)
    f0s, dmin = yin(x)
    voiced_mask = f0s > 0
    voiced = float(np.mean(voiced_mask)) if len(f0s) else 0.0
    f0 = float(np.median(f0s[voiced_mask])) if voiced_mask.sum() >= 3 else 0.0
    ons, sharp = onset_rate(x)
    w = Window(ch, None, 0.0, {}, round(f0, 1), round(voiced, 2), round(ons, 1), round(sharp, 1), top=model.top(s))
    roles = ROLE_CHANNELS.get(ch)
    if roles:
        sc = {r: rs[r] for r in roles}
        if 'congas' in sc:
            # YAMNet has no conga class and a hand drum is barely pitched: back it with the DSP.
            perc = min(1.0, max(0.0, (ons - 2.0) / 4.0)) * min(1.0, max(0.0, (sharp - 3.0) / 4.0)) * (1.0 - voiced)
            sc['congas'] = max(sc['congas'], 0.6 * perc)
        w.scores = {r: round(v, 3) for r, v in sc.items()}
        best = max(sc, key=sc.get)
        total = sum(sc.values())
        if sc[best] >= 0.08 and total > 0:
            # confidence: share of the evidence among this channel's roles, damped if YAMNet is unsure
            w.role, w.conf = best, round(float(sc[best] / total) * min(1.0, 0.5 + sc[best]), 2)
    if ch in REGISTER_CHANNELS or w.role == 'voice':
        if f0 > 0 and voiced >= 0.3 and (rs['voice'] >= 0.15 or ch in REGISTER_CHANNELS):
            w.register = 'female' if f0 >= REGISTER_SPLIT_HZ else 'male'
            # distance from the split in semitones, saturating at 4 st
            st = abs(12 * np.log2(f0 / REGISTER_SPLIT_HZ))
            w.reg_conf = round(float(min(1.0, 0.5 + st / 8) * min(1.0, voiced / 0.5)), 2)
    return w


# ---------------- switch logic (pure, unit-tested) ----------------

@dataclass
class Streak:
    label: str
    since: float
    last: float
    n: int = 1
    conf_sum: float = 0.0

    @property
    def seconds(self) -> float:
        return self.last - self.since

    @property
    def conf(self) -> float:
        return self.conf_sum / self.n


class Switcher:
    """Hysteresis for one channel's role (or register). A new label is applied only after it
    was the classification for `need` seconds with nothing else in between (gaps up to MAX_GAP
    allowed, low-confidence windows ignored). A lock freezes the current label."""

    def __init__(self, current: str | None, need: float = SWITCH_SECONDS, min_conf: float = MIN_CONF, max_gap: float = MAX_GAP):
        self.current = current
        self.need, self.min_conf, self.max_gap = need, min_conf, max_gap
        self.locked = False
        self.streak: Streak | None = None

    def set(self, label: str | None, lock: bool | None = None) -> None:
        self.current = label
        if lock is not None:
            self.locked = lock
        self.streak = None

    def update(self, label: str | None, conf: float, t: float) -> dict | None:
        """Feed one window. Returns {'from', 'to', 'confidence', 'seconds'} when a switch is confirmed."""
        if self.streak and t - self.streak.last > self.max_gap:
            self.streak = None
        if label is None or conf < self.min_conf:
            return None
        if self.streak is None or self.streak.label != label:
            self.streak = Streak(label, t, t, 1, conf)
        else:
            self.streak.last = t
            self.streak.n += 1
            self.streak.conf_sum += conf
        s = self.streak
        if self.locked or label == self.current or s.seconds < self.need:
            return None
        ev = {'from': self.current, 'to': label, 'confidence': round(s.conf, 2), 'seconds': round(s.seconds, 1)}
        self.current = label
        return ev


# ---------------- live wiring ----------------

class LiveClassifier:
    """Owns ring buffers for the watched channels and the background inference thread.

    push(raw)          analyzer worker thread: raw venue block (n, 16) at 48 kHz
    activity(flags)    engine, each 100 ms frame: [playing(n) for n in 1..16]
    on_event(ev)       called for every confident window (for the UI / director)
    on_switch(ch, kind, ev)  called on a confirmed role ('role') or register ('register') change
    """

    def __init__(self, roles: dict[int, str], registers: dict[int, str | None], locks: dict[int, bool],
                 on_switch: Callable[[int, str, dict], None], on_event: Callable[[dict], None] | None = None):
        self.model = Yamnet()
        self.buf = np.zeros((WIN_IN, len(WATCH)), dtype=np.float32)
        self.col = {ch: i for i, ch in enumerate(WATCH)}
        self.w = 0  # write index
        self.filled = 0
        self.lock = threading.Lock()
        self.playing = [False] * 16
        self.since_play = {ch: 0.0 for ch in WATCH}  # when the channel started playing (need a full window)
        self.last_run = {ch: 0.0 for ch in WATCH}
        self.roles = {ch: Switcher(roles.get(ch)) for ch in ROLE_CHANNELS}
        for ch, sw in self.roles.items():
            sw.locked = bool(locks.get(ch))
        self.regs = {ch: Switcher(registers.get(ch), need=REGISTER_SECONDS) for ch in REGISTER_CHANNELS}
        self.latest: dict[int, dict] = {}
        self.on_switch, self.on_event = on_switch, on_event
        self.cpu_s = 0.0  # thread CPU seconds spent (for the CPU report)
        self.t0 = time.time()
        self.runs = 0
        threading.Thread(target=self._loop, name='classifier', daemon=True).start()

    def push(self, raw: np.ndarray) -> None:
        x = raw[:, [c - 1 for c in WATCH]]
        n = len(x)
        if n >= WIN_IN:
            x, n = x[-WIN_IN:], WIN_IN
        with self.lock:
            end = self.w + n
            if end <= WIN_IN:
                self.buf[self.w:end] = x
            else:
                k = WIN_IN - self.w
                self.buf[self.w:] = x[:k]
                self.buf[: n - k] = x[k:]
            self.w = end % WIN_IN
            self.filled = min(WIN_IN, self.filled + n)

    def window(self, ch: int) -> np.ndarray:
        with self.lock:
            return np.roll(self.buf[:, self.col[ch]], -self.w).copy()

    def activity(self, flags: list[bool]) -> None:
        now = time.time()
        for ch in WATCH:
            on = flags[ch - 1]
            if on and not self.playing[ch - 1]:
                self.since_play[ch] = now
            self.playing[ch - 1] = on

    def _loop(self) -> None:
        try:
            os.nice(10)  # Linux: per-thread; keeps inference behind the audio and mix threads
        except OSError:
            pass
        while True:
            time.sleep(0.25)
            now = time.time()
            if self.filled < WIN_IN:
                continue
            due = [ch for ch in WATCH if self.playing[ch - 1] and now - self.since_play[ch] >= 1.0 and now - self.last_run[ch] >= HOP]
            if not due:
                continue
            ch = min(due, key=lambda c: self.last_run[c])  # one channel per tick spreads the load
            self.last_run[ch] = now
            c0 = time.thread_time()
            try:
                w = classify(self.model, ch, self.window(ch))
            except Exception as e:  # noqa: BLE001 - recognition must never take the engine down
                log.warning('classify ch %d failed: %s', ch, e)
                continue
            self.cpu_s += time.thread_time() - c0
            self.runs += 1
            self._handle(w, now)

    def _handle(self, w: Window, now: float) -> None:
        ch = w.ch
        if ch in self.roles:
            sw = self.roles[ch]
            ev = sw.update(w.role, w.conf, now)
            st = sw.streak
            info = {'ch': ch, 'role': w.role, 'confidence': w.conf, 'seconds': round(st.seconds, 1) if st and st.label == w.role else 0.0,
                    'current': sw.current, 'locked': sw.locked}
            if w.register:
                info['register'] = w.register
            self.latest[ch] = info
            if self.on_event and w.role:
                self.on_event(info)
            if ev:
                self.on_switch(ch, 'role', ev)
        if ch in self.regs:
            sw = self.regs[ch]
            ev = sw.update(w.register, w.reg_conf, now)
            st = sw.streak
            info = {'ch': ch, 'register': w.register, 'f0': w.f0, 'confidence': w.reg_conf,
                    'seconds': round(st.seconds, 1) if st and st.label == w.register else 0.0, 'current': sw.current}
            self.latest[ch] = info
            if self.on_event and w.register:
                self.on_event(info)
            if ev:
                self.on_switch(ch, 'register', ev)

    def cpu_percent(self) -> float:
        """Inference CPU as % of one core since start."""
        return round(100 * self.cpu_s / max(1e-6, time.time() - self.t0), 2)
