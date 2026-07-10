"""Safety rails for live parameter automation.

Every automated parameter move — DSP fast loop or AI review — passes
through a Rail: hard min/max clamps and a maximum step per update (slew).
An adaptive chain that misbehaves mid-show is worse than a static one;
the rails make the worst case 'slightly suboptimal', never 'audible pump'.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Rail:
    name: str
    value: float
    lo: float
    hi: float
    max_step: float          # per update tick of the owning loop
    frozen: bool = False     # user veto: AI/auto may not move this

    def clamp(self, x: float) -> float:
        return max(self.lo, min(self.hi, x))

    def step_toward(self, target: float) -> bool:
        """Move one bounded step toward target. Returns True if moved."""
        if self.frozen:
            return False
        target = self.clamp(target)
        delta = target - self.value
        if abs(delta) < 1e-3:
            return False
        step = max(-self.max_step, min(self.max_step, delta))
        self.value = self.clamp(self.value + step)
        return True

    def nudge(self, delta: float) -> float:
        """Bounded relative move (AI review path). Returns applied delta."""
        if self.frozen:
            return 0.0
        before = self.value
        self.value = self.clamp(self.value +
                                max(-self.max_step, min(self.max_step, delta)))
        return self.value - before
