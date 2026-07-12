"""Stereo-mix analysis: fully automatic mixing evidence WITHOUT stems.

For rigs where 16-channel stem capture isn't possible with zero installs
(e.g. macOS <= 12 without an RME/MOTU-class interface), the Mix Engineer
listens to the STEREO PROGRAM MIX — the same feed OBS broadcasts — and
still drives faders automatically, on tighter rails:

* vocal presence from the calibrated/heuristic VocalPresence stack
* masking proxy: presence-band (2-5 kHz) energy while the vocal is in
  (P_on) vs. instrumental-only moments (P_off); the vocal's own
  contribution is estimated by energy subtraction
* mid/side split: lead vocals are center-panned, so side-channel
  presence energy is nearly pure "crowd"
* spectral balance + loudness + crest factor vs. a soundcheck reference

The AI loop consumes these instead of per-stem measurements
(analysis_mode = "stereo") and is allowed smaller automatic moves:
the named lead-vocal fader +-1.5 dB per review, instrument trims
+-1.0 dB, master sweetening as usual.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from ..core.vad import LevelVAD, NEG_INF_DB
from ..dsp.frontend import Frontend
from ..dsp.vocal import VocalPresence


def _ema(prev: Optional[float], x: float, a: float = 0.01) -> float:
    return x if prev is None else prev + a * (x - prev)


class StereoMixAnalyzer:
    """Streaming program-mix analysis (mono or stereo input)."""

    def __init__(self, vocal_detector: Optional[VocalPresence] = None):
        self._fe_mid = Frontend()
        self._fe_side = Frontend()
        self.det = vocal_detector or VocalPresence()
        self._band_vad = LevelVAD(margin_db=8.0, attack_s=0.3, release_s=1.0)
        self.vocal_conf = 0.0
        self._p_on: Optional[float] = None    # presence dB, vocal in
        self._p_off: Optional[float] = None   # presence dB, band only
        self._side_presence: Optional[float] = None
        self._loud: Optional[float] = None
        self._tilt: Optional[float] = None
        self._bands: Dict[str, Optional[float]] = {}
        self._peak_win: list = []
        self._active = False
        self.active_seconds = 0.0
        self.reference: Dict[str, float] = {}
        self._clock = 0.0

    # ------------------------------------------------------------------
    def process(self, pcm: np.ndarray, clock: float) -> None:
        self._clock = clock
        if pcm.ndim == 2 and pcm.shape[1] >= 2:
            mid = (pcm[:, 0] + pcm[:, 1]) * 0.5
            side = (pcm[:, 0] - pcm[:, 1]) * 0.5
        else:
            mid = pcm if pcm.ndim == 1 else pcm[:, 0]
            side = np.zeros_like(mid)
        side_hops = self._fe_side.process(side)
        for i, hop in enumerate(self._fe_mid.process(mid)):
            conf = self.det.update(hop)
            self.vocal_conf = conf
            self._active = self._band_vad.update(hop.t, hop.rms_db)
            if self._active:
                self.active_seconds += 512.0 / 48000.0
                self._loud = _ema(self._loud, hop.rms_db)
                self._tilt = _ema(self._tilt, hop.tilt_db)
                for k, v in hop.band_db.items():
                    self._bands[k] = _ema(self._bands.get(k), v)
                pres = hop.band_db["presence"]
                if conf > 0.6:
                    self._p_on = _ema(self._p_on, pres)
                elif conf < 0.35:
                    self._p_off = _ema(self._p_off, pres)
                if i < len(side_hops):
                    self._side_presence = _ema(
                        self._side_presence,
                        side_hops[i].band_db["presence"])
                self._peak_win.append(hop.rms_db)
                del self._peak_win[:-400]

    # ------------------------------------------------------------------
    def masking_db(self) -> Optional[float]:
        """Positive = the band crowds the vocal where it lives."""
        if self._p_on is None or self._p_off is None:
            return None
        on_lin = 10.0 ** (self._p_on / 10.0)
        off_lin = 10.0 ** (self._p_off / 10.0)
        vocal_contrib = max(on_lin - off_lin, off_lin * 1e-3)
        contrib_db = 10.0 * np.log10(vocal_contrib)
        return float(np.clip(self._p_off - contrib_db, -30.0, 30.0))

    def set_reference(self) -> None:
        """Soundcheck snapshot of the program sound."""
        self.reference = {}
        if self._loud is not None:
            self.reference["loud_db"] = self._loud
        if self._tilt is not None:
            self.reference["tilt_db"] = self._tilt
        for k, v in self._bands.items():
            if v is not None:
                self.reference[f"band_{k}"] = v

    def measurements(self) -> dict:
        crest = None
        if self._peak_win and self._loud is not None:
            crest = round(float(np.percentile(self._peak_win, 95))
                          - self._loud, 1)
        out = {
            "band_playing": self._active,
            "vocal_conf": round(self.vocal_conf, 2),
            "loud_db": round(self._loud, 1) if self._loud is not None else None,
            "tilt_db": round(self._tilt, 1) if self._tilt is not None else None,
            "crest_db": crest,
            "vocal_masking_db": self.masking_db(),
            "side_presence_db": round(self._side_presence, 1)
            if self._side_presence is not None else None,
        }
        if self.reference:
            if self._loud is not None and "loud_db" in self.reference:
                out["loud_vs_soundcheck_db"] = round(
                    self._loud - self.reference["loud_db"], 1)
            if self._tilt is not None and "tilt_db" in self.reference:
                out["tilt_vs_soundcheck_db"] = round(
                    self._tilt - self.reference["tilt_db"], 1)
        return out
