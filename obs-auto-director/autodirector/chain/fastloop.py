"""Adaptive voice chain — the fast DSP control loop.

Manages a per-speaker chain of NATIVE OBS filters over obs-websocket:

    noise suppression -> expander -> [user's VSTs, untouched] ->
    gain -> compressor -> 3-band EQ -> limiter

The plugin owns only its "AD:"-prefixed filters; anything else on the
source (the user's VSTs) is left alone, kept between the expander and the
gain stage. All parameter movement goes through Rails (clamp + slew) and
follows engineer discipline:

* expander threshold follows the measured room floor, moves ONLY while
  the speaker is silent, one dB at a time
* gain stages the speaker toward the target speech level (open loop —
  measurements are pre-chain, so corrections cannot feed back)
* compressor threshold rides measured speech peaks
* EQ makes small, slow tilt corrections toward a target voice curve and
  stops when close (auto-EQ; broad strokes only — surgical work stays in
  the user's VSTs)
* limiter is a static safety ceiling
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

from .measure import Snapshot
from .rails import Rail

log = logging.getLogger("autodirector.chain")

PREFIX = "AD: "
F_SUPPRESS = PREFIX + "Noise Suppression"
F_EXPANDER = PREFIX + "Expander"
F_GAIN = PREFIX + "Gain"
F_COMP = PREFIX + "Compressor"
F_EQ = PREFIX + "EQ"
F_LIMIT = PREFIX + "Limiter"

# OBS filter kind ids (obs-filters module).
K_SUPPRESS = "noise_suppress_filter"
K_EXPANDER = "expander_filter"
K_GAIN = "gain_filter"
K_COMP = "compressor_filter"
K_EQ = "basic_eq_filter"
K_LIMIT = "limiter_filter"


@dataclass
class ChainConfig:
    target_speech_db: float = -20.0   # desired average speech level
    target_tilt_db: float = -14.0     # desired hf-lf tilt for a voice
    eq_deadband_db: float = 3.0       # stop correcting when this close
    expander_margin_db: float = 8.0   # threshold above measured floor
    comp_headroom_db: float = 6.0     # threshold below speech peaks
    limiter_threshold_db: float = -3.0


class VoiceChain:
    """One speaker's adaptive chain. Call adapt() every ~2 s."""

    def __init__(self, obs, source: str, cfg: Optional[ChainConfig] = None):
        self.obs = obs
        self.source = source
        self.cfg = cfg or ChainConfig()
        self.ensured = False
        self.available: set = set()
        self._create_failed: set = set()
        self.rails: Dict[str, Rail] = {
            "expander_threshold": Rail("expander_threshold", -45.0,
                                       lo=-60.0, hi=-25.0, max_step=1.0),
            "gain_db": Rail("gain_db", 0.0, lo=-12.0, hi=12.0, max_step=0.5),
            "comp_threshold": Rail("comp_threshold", -14.0,
                                   lo=-30.0, hi=-5.0, max_step=1.0),
            "eq_low": Rail("eq_low", 0.0, lo=-4.0, hi=4.0, max_step=0.5),
            "eq_high": Rail("eq_high", 0.0, lo=-4.0, hi=4.0, max_step=0.5),
        }

    # -- setup -----------------------------------------------------------
    def ensure_filters(self) -> bool:
        """Create missing AD filters and keep our slots ordered around the
        user's own filters. Safe to call repeatedly; no-op while OBS is
        down (fail-safe)."""
        filters = self.obs.get_filters(self.source)
        if filters is None:
            return False
        existing = {f.get("filterName") for f in filters}
        cfg = self.cfg
        spec = [
            (F_SUPPRESS, K_SUPPRESS, {"method": "rnnoise"}),
            (F_EXPANDER, K_EXPANDER, {
                "presets": "expander", "ratio": 4.0, "detector": "RMS",
                "threshold": self.rails["expander_threshold"].value,
                "attack_time": 5, "release_time": 120, "output_gain": 0.0}),
            (F_GAIN, K_GAIN, {"db": self.rails["gain_db"].value}),
            (F_COMP, K_COMP, {
                "ratio": 3.0, "threshold": self.rails["comp_threshold"].value,
                "attack_time": 6, "release_time": 60, "output_gain": 0.0}),
            (F_EQ, K_EQ, {"low": self.rails["eq_low"].value, "mid": 0.0,
                          "high": self.rails["eq_high"].value}),
            (F_LIMIT, K_LIMIT, {"threshold": cfg.limiter_threshold_db,
                                "release_time": 60}),
        ]
        for name, kind, settings in spec:
            if name in existing or self.obs.create_filter(
                    self.source, name, kind, settings):
                self.available.add(name)
            elif name not in self._create_failed:
                self._create_failed.add(name)
                log.warning("voice-chain filter unavailable (%s / %s) — "
                            "continuing without it", name, kind)
        # Order: suppression + expander first; our output stages last —
        # the user's VSTs stay in the middle, untouched.
        if F_SUPPRESS in self.available:
            self.obs.set_filter_index(self.source, F_SUPPRESS, 0)
        if F_EXPANDER in self.available:
            self.obs.set_filter_index(self.source, F_EXPANDER, 1)
        current = self.obs.get_filters(self.source) or []
        tail = len(current)
        for i, name in enumerate([F_GAIN, F_COMP, F_EQ, F_LIMIT]):
            if name in self.available:
                self.obs.set_filter_index(self.source, name, tail - 4 + i)
        # Core = gain staging + compression; anything else is a bonus a
        # single missing filter must never take the whole chain down.
        self.ensured = F_GAIN in self.available and F_COMP in self.available
        return self.ensured

    # -- fast loop ---------------------------------------------------------
    def adapt(self, snap: Snapshot, speaking_now: bool) -> Dict[str, float]:
        """One control tick (~2 s cadence). Returns the params that moved."""
        if not self.ensured and not self.ensure_filters():
            return {}
        cfg = self.cfg
        moved: Dict[str, float] = {}

        # Expander threshold: follow the room floor, never mid-sentence.
        if F_EXPANDER in self.available and not speaking_now \
                and snap.floor_db > -85.0:
            rail = self.rails["expander_threshold"]
            if rail.step_toward(snap.floor_db + cfg.expander_margin_db):
                moved["expander_threshold"] = rail.value

        if snap.speech_db > -85.0:
            rail = self.rails["gain_db"]
            if rail.step_toward(cfg.target_speech_db - snap.speech_db):
                moved["gain_db"] = rail.value

            rail = self.rails["comp_threshold"]
            post_gain_peak = snap.peak_db + self.rails["gain_db"].value
            if rail.step_toward(post_gain_peak - cfg.comp_headroom_db):
                moved["comp_threshold"] = rail.value

            # Auto-EQ: slow tilt correction with a deadband.
            err = snap.tilt_db - cfg.target_tilt_db
            if F_EQ in self.available and abs(err) > cfg.eq_deadband_db:
                corr = max(-0.5, min(0.5, -err / 8.0))
                lo_rail, hi_rail = self.rails["eq_low"], self.rails["eq_high"]
                if hi_rail.step_toward(hi_rail.value + corr):
                    moved["eq_high"] = hi_rail.value
                if lo_rail.step_toward(lo_rail.value - corr):
                    moved["eq_low"] = lo_rail.value

        self._push(moved)
        return moved

    def nudge(self, param: str, delta: float) -> float:
        """Bounded relative adjustment (AI review path)."""
        rail = self.rails.get(param)
        if rail is None:
            return 0.0
        applied = rail.nudge(delta)
        if applied:
            self._push({param: rail.value})
        return applied

    def freeze(self, param: str, frozen: bool = True) -> None:
        if param in self.rails:
            self.rails[param].frozen = frozen

    # -- OBS writes ----------------------------------------------------------
    def _push(self, moved: Dict[str, float]) -> None:
        if not moved:
            return
        if "expander_threshold" in moved:
            self.obs.set_filter_settings(self.source, F_EXPANDER,
                                         {"threshold": moved["expander_threshold"]})
        if "gain_db" in moved:
            self.obs.set_filter_settings(self.source, F_GAIN,
                                         {"db": moved["gain_db"]})
        if "comp_threshold" in moved:
            self.obs.set_filter_settings(self.source, F_COMP,
                                         {"threshold": moved["comp_threshold"]})
        if "eq_low" in moved or "eq_high" in moved:
            self.obs.set_filter_settings(self.source, F_EQ, {
                "low": self.rails["eq_low"].value,
                "high": self.rails["eq_high"].value})
