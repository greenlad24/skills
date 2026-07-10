"""Level-based voice activity detection with an adaptive noise floor."""

from __future__ import annotations

from typing import List, Optional

NEG_INF_DB = -90.0


class LevelVAD:
    """Voice/vocal activity detection from a level meter (dB).

    Tracks an adaptive noise floor (fast downward, slow upward, and never
    while the signal is hot) and applies attack/release times so the
    activity flag is stable rather than fluttering with every syllable.
    """

    def __init__(self, margin_db: float = 8.0, attack_s: float = 0.25,
                 release_s: float = 2.5, floor_db: float = -60.0):
        self.margin_db = margin_db
        self.attack_s = attack_s
        self.release_s = release_s
        self.floor_db = floor_db
        self.active = False
        self._hot_since: Optional[float] = None
        self._last_hot_t = -1e9

    def update(self, t: float, level_db: float) -> bool:
        level_db = max(level_db if level_db == level_db else NEG_INF_DB,
                       NEG_INF_DB)  # NaN/-inf guard

        # Muted / disconnected input is "no signal", not "a very quiet room":
        # learning a floor from it would poison the detector (floor collapses
        # to -90, then ordinary room tone reads as hot forever).
        if level_db <= NEG_INF_DB + 1.0:
            hot = False
        else:
            hot = level_db >= self.floor_db + self.margin_db
            # Adapt the noise floor using the pre-update floor.
            if level_db < self.floor_db:
                self.floor_db += 0.3 * (level_db - self.floor_db)
            elif not hot:
                self.floor_db += 0.005 * (level_db - self.floor_db)
            else:
                # Bounded recovery so a poisoned (too-low) floor can climb
                # back even if the signal never drops below it again. The
                # target keeps 6 dB of headroom under the hot threshold, so
                # recovery can never turn the current signal not-hot.
                target = level_db - self.margin_db - 6.0
                if self.floor_db < target:
                    self.floor_db += 0.002 * (target - self.floor_db)
            self.floor_db = min(self.floor_db, -25.0)

        if hot:
            if self._hot_since is None:
                self._hot_since = t
            self._last_hot_t = t
            if not self.active and (t - self._hot_since) >= self.attack_s:
                self.active = True
        else:
            self._hot_since = None
            if self.active and (t - self._last_hot_t) >= self.release_s:
                self.active = False
        return self.active

    def resync(self, t: float) -> None:
        """Restart timers after a time discontinuity (stall, pause/resume),
        so the gap is not counted as attack or release time."""
        self._hot_since = None
        if self.active:
            self._last_hot_t = t


def apply_crosstalk_gate(talking: List[bool], levels: List[float],
                         gate_db: float = 6.0) -> List[bool]:
    """Suppress mic bleed between physically co-located mics: if several
    mics read hot at once, only mics within gate_db of the loudest are
    treated as genuinely talking. (Used with per-mic capture; irrelevant
    for single-mixed-channel setups.)"""
    if sum(talking) < 2 or not levels:
        return talking
    loudest = max(lvl for talk, lvl in zip(talking, levels) if talk)
    return [talk and lvl >= loudest - gate_db
            for talk, lvl in zip(talking, levels)]
