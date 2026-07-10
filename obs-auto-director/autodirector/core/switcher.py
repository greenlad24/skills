"""EvidenceSwitcher: turns noisy confidence streams into calm decisions.

This is the "relaxed switching" layer. Detectors (vocal-in-mix, speaker
attribution, VADs) emit continuous confidences in [0, 1]; directors want
stable categorical decisions ("VOCAL", "speaker_1", ...). The switcher sits
between them and only changes its mind after sustained evidence:

* confidences are EMA-smoothed (tau ~0.25 s)
* a challenger must clear an enter threshold while the current state has
  fallen below an exit threshold (hysteresis: two moderately confident
  states mean *hold the current shot*)
* qualification must persist for a per-state dwell time, tracked by a
  leaky accumulator (brief detector flickers bleed evidence, not reset it)
* after every switch there is a cooldown
* returning to a state we recently left costs extra dwell (return
  penalty) — this is the anti-ping-pong rule
* an overwhelming, sustained confidence can switch with priority (bypassing
  cooldown but not the global rate cap)
* a hard rate cap bounds switches per minute no matter how adversarial the
  input is — a show with more than ~10 genuine action changes a minute is
  chaos, and the calm choice is to stop chasing it

The commit confidence of each switch is reported so downstream pacing can
extend the minimum shot length for lower-confidence cuts
(``min_shot_factor``).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class SwitchEvent:
    state: str
    prev_state: Optional[str]
    priority: bool
    commit_conf: float
    kind: str  # "initial" | "dwell" | "priority"


@dataclass
class SwitcherConfig:
    dwell_s: Dict[str, float] = field(default_factory=dict)  # per target state
    default_dwell_s: float = 1.0
    ema_tau_s: float = 0.25
    enter_conf: float = 0.65
    exit_conf: float = 0.40
    cooldown_s: float = 3.0
    priority_conf: float = 0.85
    priority_sustain_s: float = 1.5
    return_penalty: float = 1.5
    return_window_s: float = 20.0
    dwell_multiplier: float = 1.0     # calibration-quality driven, <= 1.5
    max_switches_per_min: int = 10    # hard rate cap, priority included
    evidence_leak: float = 2.0        # evidence lost per idle second (x dt)


def min_shot_factor(commit_conf: float) -> float:
    """Confidence-weighted minimum-shot extension: a cut committed at low
    confidence buys itself extra hold time before the next one."""
    return min(1.0 + (1.0 - max(0.0, min(1.0, commit_conf))), 2.0)


class EvidenceSwitcher:
    def __init__(self, cfg: SwitcherConfig,
                 initial: Optional[str] = None):
        self.cfg = cfg
        self.state = initial
        self.smoothed: Dict[str, float] = {}
        self._last_t: Optional[float] = None
        self._evidence: Dict[str, float] = {}
        self._prio_evidence: Dict[str, float] = {}
        self._last_switch_t = -1e9
        self._left_at: Dict[str, float] = {}
        self._switch_times: deque = deque(maxlen=64)

    # ------------------------------------------------------------------
    def _dwell_for(self, t: float, state: str) -> float:
        need = self.cfg.dwell_s.get(state, self.cfg.default_dwell_s)
        need *= max(1.0, min(self.cfg.dwell_multiplier, 1.5))
        if (t - self._left_at.get(state, -1e9)) <= self.cfg.return_window_s:
            need *= self.cfg.return_penalty
        return need

    def _rate_capped(self, t: float) -> bool:
        recent = [x for x in self._switch_times if t - x <= 60.0]
        return len(recent) >= self.cfg.max_switches_per_min

    def _commit(self, t: float, state: str, priority: bool,
                kind: str) -> SwitchEvent:
        prev = self.state
        if prev is not None:
            self._left_at[prev] = t
        self.state = state
        self._last_switch_t = t
        self._switch_times.append(t)
        self._evidence = {}
        self._prio_evidence = {}
        return SwitchEvent(state, prev, priority,
                           self.smoothed.get(state, 0.0), kind)

    # ------------------------------------------------------------------
    def update(self, t: float,
               confidences: Dict[str, float]) -> Optional[SwitchEvent]:
        cfg = self.cfg
        dt = 0.0 if self._last_t is None else max(t - self._last_t, 0.0)
        if dt > 0.5:
            dt = 0.05  # discontinuity: a stall must not count as dwell time
        self._last_t = t

        # Smooth (NaN/inf-proof) — first sample seeds the EMA directly.
        alpha = 1.0 if dt == 0.0 else 1.0 - math.exp(-dt / cfg.ema_tau_s)
        for s, c in confidences.items():
            if c != c or c == float("inf") or c == float("-inf"):
                c = 0.0
            c = max(0.0, min(1.0, c))
            prev = self.smoothed.get(s)
            self.smoothed[s] = c if prev is None else prev + alpha * (c - prev)

        if not self.smoothed:
            return None

        # Startup: adopt the first state that clears the enter bar.
        if self.state is None:
            best = max(self.smoothed, key=lambda s: self.smoothed[s])
            if self.smoothed[best] >= cfg.enter_conf:
                return self._commit(t, best, False, "initial")
            return None

        cur_conf = self.smoothed.get(self.state, 0.0)

        # Accumulate (leaky) evidence for every challenger.
        for s, conf in self.smoothed.items():
            if s == self.state:
                continue
            qualified = (conf >= cfg.enter_conf
                         and cur_conf <= cfg.exit_conf
                         and conf > cur_conf)
            e = self._evidence.get(s, 0.0)
            self._evidence[s] = (e + dt if qualified
                                 else max(0.0, e - cfg.evidence_leak * dt))
            pq = conf >= cfg.priority_conf and conf > cur_conf
            pe = self._prio_evidence.get(s, 0.0)
            self._prio_evidence[s] = pe + dt if pq else 0.0

        # Decide, strongest evidence first.
        for s in sorted(self._evidence,
                        key=lambda x: self._evidence[x], reverse=True):
            priority = self._prio_evidence.get(s, 0.0) >= cfg.priority_sustain_s
            earned = self._evidence.get(s, 0.0) >= self._dwell_for(t, s)
            if not (earned or priority):
                continue
            if self._rate_capped(t):
                return None  # hard cap: stop chasing a chaotic feed
            if not priority and (t - self._last_switch_t) < cfg.cooldown_s:
                continue
            return self._commit(t, s, priority,
                                "priority" if priority else "dwell")
        return None
