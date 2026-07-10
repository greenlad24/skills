"""DSP front-end: per-hop audio features from raw PCM.

Per the v2 design (docs/TEAM_REVIEW_SYNTHESIS.md §2.0): 48 kHz mono
downmix, Hann STFT N=2048 hop=512 (~94 fps at 48 kHz); per hop we emit
magnitude spectrum, 40-band log-mel, RMS dB, spectral flux, centroid,
band energies, and a YIN-lite F0 estimate with a voicing confidence.

Pure numpy; a full front-end costs well under 5% of one core.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

NEG_INF_DB = -90.0


@dataclass
class HopFeatures:
    t: float                  # audio-clock time of the hop end (seconds)
    rms_db: float
    flux: float               # normalized spectral flux (0..~1)
    centroid_hz: float
    tilt_db: float            # high-band minus low-band energy (spectral tilt)
    band_db: dict             # {"lf": .., "vocal": .., "presence": .., "hf": ..}
    logmel: np.ndarray        # (40,) log-mel energies
    f0_hz: float              # 0.0 when unvoiced
    voicing: float            # 0..1 periodicity confidence (YIN-lite)


BANDS = {
    "lf": (0.0, 200.0),
    "vocal": (200.0, 4000.0),
    "presence": (2000.0, 5000.0),
    "hf": (6000.0, 24000.0),
}


def _hz_to_mel(f):
    return 2595.0 * np.log10(1.0 + np.asarray(f) / 700.0)


def _mel_to_hz(m):
    return 700.0 * (10.0 ** (np.asarray(m) / 2595.0) - 1.0)


def mel_filterbank(n_mels: int, n_fft: int, sr: int,
                   fmin: float = 50.0, fmax: float = 8000.0) -> np.ndarray:
    """Triangular mel filterbank, shape (n_mels, n_fft//2+1)."""
    mel_pts = np.linspace(_hz_to_mel(fmin), _hz_to_mel(fmax), n_mels + 2)
    hz_pts = _mel_to_hz(mel_pts)
    bins = np.floor((n_fft + 1) * hz_pts / sr).astype(int)
    bins = np.clip(bins, 0, n_fft // 2)
    fb = np.zeros((n_mels, n_fft // 2 + 1))
    for i in range(n_mels):
        lo, mid, hi = bins[i], bins[i + 1], bins[i + 2]
        if mid > lo:
            fb[i, lo:mid] = (np.arange(lo, mid) - lo) / (mid - lo)
        if hi > mid:
            fb[i, mid:hi] = (hi - np.arange(mid, hi)) / (hi - mid)
    return fb


class Frontend:
    """Streaming feature extractor. Feed PCM chunks of any size; it emits
    one HopFeatures per hop (512 samples at 48 kHz ≈ 10.7 ms)."""

    def __init__(self, samplerate: int = 48000, n_fft: int = 2048,
                 hop: int = 512, n_mels: int = 40):
        self.sr = samplerate
        self.n_fft = n_fft
        self.hop = hop
        self.window = np.hanning(n_fft).astype(np.float64)
        self.melfb = mel_filterbank(n_mels, n_fft, samplerate)
        self.freqs = np.fft.rfftfreq(n_fft, 1.0 / samplerate)
        self._buf = np.zeros(0, dtype=np.float64)
        self._prev_mag: Optional[np.ndarray] = None
        self._samples_seen = 0
        # YIN-lite runs on the analysis window itself
        self._f0_min, self._f0_max = 70.0, 1000.0

    # -- helpers ------------------------------------------------------------
    def _band_db(self, power: np.ndarray) -> dict:
        out = {}
        total_guard = 1e-12
        for name, (lo, hi) in BANDS.items():
            mask = (self.freqs >= lo) & (self.freqs < hi)
            e = float(np.sum(power[mask])) + total_guard
            out[name] = 10.0 * np.log10(e)
        return out

    def _yin_lite(self, frame: np.ndarray) -> tuple:
        """Cumulative-mean-normalized autocorrelation pitch estimate.
        Returns (f0_hz, voicing 0..1)."""
        x = frame - frame.mean()
        if float(np.max(np.abs(x))) < 1e-6:
            return 0.0, 0.0
        n = len(x)
        # autocorrelation via FFT
        fsize = 1 << (2 * n - 1).bit_length()
        spec = np.fft.rfft(x, fsize)
        ac = np.fft.irfft(spec * np.conj(spec))[:n]
        if ac[0] <= 0:
            return 0.0, 0.0
        ac = ac / ac[0]
        lag_min = int(self.sr / self._f0_max)
        lag_max = min(int(self.sr / self._f0_min), n - 1)
        if lag_max <= lag_min + 2:
            return 0.0, 0.0
        seg = ac[lag_min:lag_max]
        best = int(np.argmax(seg))
        conf = float(seg[best])
        lag = lag_min + best
        # parabolic refinement
        if 0 < best < len(seg) - 1:
            a, b, c = seg[best - 1], seg[best], seg[best + 1]
            denom = a - 2 * b + c
            if abs(denom) > 1e-12:
                lag = lag + 0.5 * float((a - c) / denom)
        f0 = self.sr / lag if lag > 0 else 0.0
        conf = max(0.0, min(1.0, conf))
        if conf < 0.30:
            return 0.0, conf
        return float(f0), conf

    # -- streaming ----------------------------------------------------------
    def process(self, pcm: np.ndarray) -> List[HopFeatures]:
        """pcm: float32/float64 array, shape (n,) mono or (n, ch) —
        multichannel is downmixed. Returns features for each completed hop."""
        if pcm.ndim == 2:
            pcm = pcm.mean(axis=1)
        self._buf = np.concatenate([self._buf, pcm.astype(np.float64)])
        out: List[HopFeatures] = []
        while len(self._buf) >= self.n_fft:
            frame = self._buf[:self.n_fft]
            self._samples_seen += self.hop
            self._buf = self._buf[self.hop:]
            out.append(self._analyze(frame))
        return out

    def _analyze(self, frame: np.ndarray) -> HopFeatures:
        t = (self._samples_seen + self.n_fft - self.hop) / self.sr
        rms = float(np.sqrt(np.mean(frame ** 2)))
        rms_db = 20.0 * np.log10(rms + 1e-9)
        rms_db = max(rms_db, NEG_INF_DB)

        spec = np.fft.rfft(frame * self.window)
        mag = np.abs(spec)
        power = mag ** 2

        if self._prev_mag is None:
            flux = 0.0
        else:
            d = mag - self._prev_mag
            up = np.sqrt(np.sum(np.maximum(d, 0.0) ** 2))
            norm = np.sqrt(np.sum(self._prev_mag ** 2)) + 1e-9
            flux = float(min(up / norm, 1.0))
        self._prev_mag = mag

        total = float(np.sum(power)) + 1e-12
        centroid = float(np.sum(self.freqs * power) / total)
        bands = self._band_db(power)
        tilt = bands["hf"] - bands["lf"]
        logmel = np.log10(self.melfb @ power + 1e-10)
        f0, voicing = self._yin_lite(frame)

        return HopFeatures(t=t, rms_db=float(rms_db), flux=flux,
                           centroid_hz=centroid, tilt_db=float(tilt),
                           band_db=bands, logmel=logmel,
                           f0_hz=f0, voicing=voicing)
