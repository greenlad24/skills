"""Program sweetening chain: subtle EQ / compression on the broadcast
feed, applied in OBS.

Per-channel EQ/comp *inside* Studio One is not reliably automatable
from outside (MCU exposes faders/mutes/pans; plugin parameters are
not a stable public surface). The professional split: per-channel
BALANCE rides happen in Studio One via faders (mcu.py), and the subtle
"make the sum sound right" layer — gentle tonal correction, glue
compression, a safety limiter, YouTube loudness — happens on the OBS
audio source that carries the Studio One mix. The user's pre-mix stays
their sound; this is a light mastering touch.

Reuses the exact rails discipline of the podcast voice chain, with
music-appropriate constants: slower, gentler, wide deadbands.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

from ..chain.rails import Rail
from ..dsp.frontend import NEG_INF_DB

log = logging.getLogger("autodirector.program")

PREFIX = "AD: "
F_EQ = PREFIX + "Program EQ"
F_COMP = PREFIX + "Program Glue"
F_LIMIT = PREFIX + "Program Limiter"
K_EQ = "basic_eq_filter"
K_COMP = "compressor_filter"
K_LIMIT = "limiter_filter"


@dataclass
class ProgramConfig:
    target_tilt_db: float = -10.0   # full-mix spectral tilt target
    eq_deadband_db: float = 4.0     # music: correct only clear imbalance
    target_loud_db: float = -16.0   # streaming-loudness-ish program level
    comp_ratio: float = 1.6         # glue, not squash
    limiter_threshold_db: float = -1.5


class ProgramChain:
    """Adaptive master-bus chain on the OBS source carrying the S1 mix."""

    def __init__(self, obs, source: str,
                 cfg: Optional[ProgramConfig] = None):
        self.obs = obs
        self.source = source
        self.cfg = cfg or ProgramConfig()
        self.ensured = False
        self.rails: Dict[str, Rail] = {
            "master_eq_low": Rail("master_eq_low", 0.0, -3.0, 3.0, 0.25),
            "master_eq_high": Rail("master_eq_high", 0.0, -3.0, 3.0, 0.25),
            "master_comp_threshold": Rail("master_comp_threshold", -12.0,
                                          -24.0, -6.0, 0.5),
        }
        self.available: set = set()
        self._create_failed: set = set()
        self._loud_ema: Optional[float] = None
        self._tilt_ema: Optional[float] = None

    def ensure_filters(self) -> bool:
        """Per-filter tolerant: a single unavailable filter kind must
        never brick the whole chain — the others keep adapting and the
        missing one's rails simply stay parked."""
        filters = self.obs.get_filters(self.source)
        if filters is None:
            return False
        existing = {f.get("filterName") for f in filters}
        spec = [
            (F_EQ, K_EQ, {"low": 0.0, "mid": 0.0, "high": 0.0}),
            (F_COMP, K_COMP, {"ratio": self.cfg.comp_ratio,
                              "threshold":
                                  self.rails["master_comp_threshold"].value,
                              "attack_time": 25, "release_time": 250,
                              "output_gain": 0.0}),
            (F_LIMIT, K_LIMIT, {"threshold": self.cfg.limiter_threshold_db,
                                "release_time": 100}),
        ]
        for name, kind, settings in spec:
            if name in existing or self.obs.create_filter(
                    self.source, name, kind, settings):
                self.available.add(name)
            elif name not in self._create_failed:
                self._create_failed.add(name)
                log.warning("program filter unavailable (%s / %s) — "
                            "continuing without it", name, kind)
        # Core = the safety pieces; EQ is a bonus.
        self.ensured = F_COMP in self.available and F_LIMIT in self.available
        return self.ensured

    # -- measurement + slow adaptation --------------------------------------
    def note_master(self, rms_db: float, tilt_db: float) -> None:
        if rms_db <= NEG_INF_DB + 1.0:
            return
        self._loud_ema = rms_db if self._loud_ema is None else \
            self._loud_ema + 0.005 * (rms_db - self._loud_ema)
        self._tilt_ema = tilt_db if self._tilt_ema is None else \
            self._tilt_ema + 0.005 * (tilt_db - self._tilt_ema)

    def adapt(self) -> Dict[str, float]:
        """Very slow corrective tick (~ every few seconds)."""
        if not self.ensured and not self.ensure_filters():
            return {}
        moved: Dict[str, float] = {}
        cfg = self.cfg
        if self._tilt_ema is not None and F_EQ in self.available:
            err = self._tilt_ema - cfg.target_tilt_db
            if abs(err) > cfg.eq_deadband_db:
                corr = max(-0.25, min(0.25, -err / 12.0))
                hi, lo = self.rails["master_eq_high"], self.rails["master_eq_low"]
                if hi.step_toward(hi.value + corr):
                    moved["master_eq_high"] = hi.value
                if lo.step_toward(lo.value - corr):
                    moved["master_eq_low"] = lo.value
        if self._loud_ema is not None:
            # Louder-than-target program: lean on the glue a touch harder.
            over = self._loud_ema - cfg.target_loud_db
            rail = self.rails["master_comp_threshold"]
            if over > 2.0 and rail.step_toward(rail.value - 0.5):
                moved["master_comp_threshold"] = rail.value
            elif over < -2.0 and rail.step_toward(rail.value + 0.5):
                moved["master_comp_threshold"] = rail.value
        self._push(moved)
        return moved

    def nudge(self, param: str, delta: float) -> float:
        rail = self.rails.get(param)
        if rail is None:
            return 0.0
        applied = rail.nudge(delta)
        if applied:
            self._push({param: rail.value})
        return applied

    def measurements(self) -> dict:
        return {"loud_db": round(self._loud_ema, 1)
                if self._loud_ema is not None else None,
                "tilt_db": round(self._tilt_ema, 1)
                if self._tilt_ema is not None else None,
                "settings": {p: round(r.value, 1)
                             for p, r in self.rails.items()}}

    def _push(self, moved: Dict[str, float]) -> None:
        if not moved:
            return
        if ("master_eq_low" in moved or "master_eq_high" in moved) \
                and F_EQ in self.available:
            self.obs.set_filter_settings(self.source, F_EQ, {
                "low": self.rails["master_eq_low"].value,
                "high": self.rails["master_eq_high"].value})
        if "master_comp_threshold" in moved:
            self.obs.set_filter_settings(self.source, F_COMP, {
                "threshold": self.rails["master_comp_threshold"].value})
