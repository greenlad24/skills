"""Vocal presence in a full band mix, with per-show calibration.

Design (docs/TEAM_REVIEW_SYNTHESIS.md §2.1): a diagonal-LDA classifier over
a small set of vocal-discriminative features, learned from a calibration
wizard (~10 s of instrumental + ~10 s with vocals), emitting a confidence
in [0, 1] every hop. The EvidenceSwitcher downstream turns confidences
into calm VOCAL/INSTRUMENTAL decisions.

Features per rolling window (~0.7 s of hops):
  0. mean voicing (pitch salience)
  1. F0 continuity — fraction of voiced hop pairs with < 5% jump
  2. vibrato energy — 4-8 Hz modulation of the F0 track (in cents)
  3. syllabic modulation — 2-8 Hz modulation of the vocal-band envelope
  4. presence-band flux (1-4 kHz articulation)
  5. F0-in-vocal-register fraction (100-800 Hz)

Main-vs-backing policy (§2.2): vocals present -> the MAIN singer scene,
always. The optional enrolled pitch prior only *modulates* confidence
(bounded ±0.1); it never vetoes and never redirects a cut to anyone else.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from .frontend import HopFeatures

WINDOW_HOPS = 64          # ~0.68 s at 48 kHz / 512 hop
HOP_RATE = 48000 / 512.0  # ~93.75 Hz feature rate

# Heuristic fallback weights (used before any calibration has been run) —
# roughly "voiced, continuous, modulated energy in the vocal register".
_DEFAULT_W = np.array([3.0, 1.5, 1.0, 1.5, 0.5, 1.5])
_DEFAULT_B = -3.2


@dataclass
class CalibrationResult:
    w: np.ndarray
    b: float
    d_prime: float
    # d' < 1.5 means the mix is hard for these features: the app warns the
    # user and stretches switcher dwells by up to 1.5x.
    dwell_multiplier: float = 1.0

    @property
    def weak(self) -> bool:
        return self.d_prime < 1.5


@dataclass
class PitchPrior:
    """Enrolled main-singer pitch range (from ~15 s of solo singing)."""
    f0_lo: float
    f0_hi: float

    @classmethod
    def enroll(cls, f0_series: List[float]) -> Optional["PitchPrior"]:
        voiced = np.array([f for f in f0_series if f > 0])
        if len(voiced) < 30:
            return None
        lo, hi = np.percentile(voiced, [10, 90])
        return cls(float(lo * 0.85), float(hi * 1.15))


class VocalPresence:
    """Streaming vocal-presence confidence from front-end hop features."""

    def __init__(self, calibration: Optional[CalibrationResult] = None,
                 pitch_prior: Optional[PitchPrior] = None,
                 bias: float = 0.0):
        self.cal = calibration
        self.prior = pitch_prior
        self.bias = bias  # user sensitivity knob, in logit units
        self._voicing = deque(maxlen=WINDOW_HOPS)
        self._f0 = deque(maxlen=WINDOW_HOPS)
        self._venv = deque(maxlen=WINDOW_HOPS)   # vocal-band envelope (dB)
        self._pflux = deque(maxlen=WINDOW_HOPS)

    # ------------------------------------------------------------------
    def features(self) -> Optional[np.ndarray]:
        if len(self._voicing) < WINDOW_HOPS // 2:
            return None
        voicing = np.array(self._voicing)
        f0 = np.array(self._f0)
        venv = np.array(self._venv)
        pflux = np.array(self._pflux)

        mean_voicing = float(voicing.mean())

        voiced = f0 > 0
        pairs = voiced[1:] & voiced[:-1]
        if pairs.sum() >= 4:
            rel = np.abs(np.diff(f0)) / np.maximum(f0[:-1], 1.0)
            continuity = float(np.mean(rel[pairs] < 0.05))
        else:
            continuity = 0.0

        vibrato = self._modulation_energy(
            self._cents(f0), 4.0, 8.0) if voiced.sum() > WINDOW_HOPS // 3 \
            else 0.0
        syllabic = self._modulation_energy(venv, 2.0, 8.0)
        presence_flux = float(np.clip(pflux.mean() * 4.0, 0.0, 1.0))
        in_register = float(np.mean((f0 > 100.0) & (f0 < 800.0)))

        return np.array([mean_voicing, continuity, vibrato, syllabic,
                         presence_flux, in_register])

    @staticmethod
    def _cents(f0: np.ndarray) -> np.ndarray:
        out = np.zeros_like(f0)
        voiced = f0 > 0
        if voiced.any():
            ref = np.median(f0[voiced])
            out[voiced] = 1200.0 * np.log2(f0[voiced] / ref)
        return out

    @staticmethod
    def _modulation_energy(series: np.ndarray, lo_hz: float,
                           hi_hz: float) -> float:
        """Fraction of (detrended) series energy in [lo_hz, hi_hz]."""
        x = series - series.mean()
        if float(np.max(np.abs(x))) < 1e-9:
            return 0.0
        spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
        freqs = np.fft.rfftfreq(len(x), 1.0 / HOP_RATE)
        band = spec[(freqs >= lo_hz) & (freqs <= hi_hz)].sum()
        total = spec[freqs >= 0.5].sum() + 1e-12
        return float(np.clip(band / total, 0.0, 1.0))

    # ------------------------------------------------------------------
    def update(self, hop: HopFeatures) -> float:
        """Feed one hop; returns vocal confidence [0, 1]."""
        self._voicing.append(hop.voicing)
        self._f0.append(hop.f0_hz)
        self._venv.append(hop.band_db["vocal"])
        self._pflux.append(hop.flux)

        feats = self.features()
        if feats is None:
            return 0.0
        if self.cal is not None:
            logit = float(self.cal.w @ feats) + self.cal.b
        else:
            logit = float(_DEFAULT_W @ feats) + _DEFAULT_B
        logit += self.bias

        conf = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, logit))))

        # Enrolled main-singer pitch prior: bounded modulation, never a veto.
        if self.prior is not None and hop.f0_hz > 0:
            if self.prior.f0_lo <= hop.f0_hz <= self.prior.f0_hi:
                conf = min(1.0, conf + 0.05)
            else:
                conf = max(0.0, conf - 0.10)
        return conf


class Calibrator:
    """Learns the LDA from labelled feature windows.

    Usage: run the wizard — collect() during ~10 s of instrumental, then
    ~10 s with vocals — and finish() to get a CalibrationResult.
    """

    def __init__(self):
        self._instrumental: List[np.ndarray] = []
        self._vocal: List[np.ndarray] = []

    def collect(self, feats: Optional[np.ndarray], vocal: bool) -> None:
        if feats is None:
            return
        (self._vocal if vocal else self._instrumental).append(feats)

    def sample_counts(self) -> tuple:
        return len(self._instrumental), len(self._vocal)

    def finish(self) -> Optional[CalibrationResult]:
        if len(self._instrumental) < 20 or len(self._vocal) < 20:
            return None
        xi = np.stack(self._instrumental)
        xv = np.stack(self._vocal)
        mu_i, mu_v = xi.mean(axis=0), xv.mean(axis=0)
        var = 0.5 * (xi.var(axis=0) + xv.var(axis=0)) + 1e-4
        w = (mu_v - mu_i) / var
        b = float(-w @ ((mu_v + mu_i) / 2.0))

        # Scale so class centroids land at logit ±2 (conf ~0.88 / ~0.12).
        m = float(w @ mu_v + b)
        if abs(m) > 1e-9:
            w, b = w * (2.0 / m), b * (2.0 / m)

        proj_i, proj_v = xi @ w + b, xv @ w + b
        spread = math.sqrt(0.5 * (proj_i.var() + proj_v.var())) + 1e-9
        d_prime = abs(float(proj_v.mean() - proj_i.mean())) / spread
        dwell_mult = 1.0 if d_prime >= 1.5 else \
            min(1.5, 1.0 + (1.5 - d_prime) / 1.5)
        return CalibrationResult(w=w, b=b, d_prime=d_prime,
                                 dwell_multiplier=dwell_mult)
