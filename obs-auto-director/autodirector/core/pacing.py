"""Cut pacing: the rules that keep automatic switching professional."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Cut:
    """A committed scene change, with the director's reasoning."""
    scene: str
    reason: str
    priority: bool = False


class PacingEngine:
    """Enforces professional pacing on cut requests.

    * never re-cuts to the scene we are already on
    * enforces a minimum shot duration, unless the cut is marked priority
      (e.g. vocals just came in — that cut must not wait)
    * respects manual operator cuts: an externally observed scene change
      restarts the shot clock and holds off non-priority cuts for
      ``override_hold_s``
    """

    def __init__(self, min_shot_s: float = 2.5, override_hold_s: float = 8.0):
        self.min_shot_s = min_shot_s
        self.override_hold_s = override_hold_s
        self.scene: Optional[str] = None
        self.last_cut_t = -1e9
        self.external_hold_until = -1e9
        self.min_shot_factor = 1.0  # confidence-weighted extension (switcher)

    def sync(self, t: float, scene: Optional[str]) -> None:
        """Tell the engine what is actually on program. A scene we did not
        cut to ourselves is a manual override: respect it — restart the
        shot clock and hold off non-priority cuts for a while instead of
        stomping the operator's cut on the next tick."""
        if scene and scene != self.scene:
            self.scene = scene
            self.last_cut_t = t
            self.external_hold_until = t + self.override_hold_s

    def request(self, t: float, scene: str, reason: str,
                priority: bool = False) -> Optional[Cut]:
        if not scene or scene == self.scene:
            return None
        if not priority and t < self.external_hold_until:
            return None
        if not priority and (t - self.last_cut_t) < \
                self.min_shot_s * self.min_shot_factor:
            return None
        self.scene = scene
        self.last_cut_t = t
        self.min_shot_factor = 1.0
        return Cut(scene, reason, priority)
