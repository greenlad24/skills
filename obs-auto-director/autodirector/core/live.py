"""Live show director: singer cam on vocals, paced instrumental rotation."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional

from .pacing import Cut, PacingEngine
from .vad import NEG_INF_DB


@dataclass
class LiveConfig:
    singer_scene: str
    instrumental_scenes: List[str] = field(default_factory=list)
    min_shot_s: float = 4.0          # v2: raised from 3.0 (relaxed switching)
    post_vocal_hold_s: float = 1.6   # linger on singer after the phrase ends
    cut_interval_s: float = 7.0      # base instrumental shot length
    cut_jitter: float = 0.35         # +/- fraction of interval (feels human)
    cutaway_every_s: float = 25.0    # brief cutaway during long vocals; 0=off
    cutaway_len_s: float = 3.0
    energy_pacing: bool = True       # louder sections -> faster cutting


class LiveDirector:
    """Directs a live music show.

    Vocals in  -> priority cut to the singer, and hold. (v2 policy: vocals
                  present means the MAIN singer scene, always — backing
                  vocals never trigger cuts to anyone else.)
    Vocals out -> linger a beat (post_vocal_hold), then rotate through the
                  instrumental scenes. The first instrumental cut prefers
                  the first scene in the list (put your wide shot there —
                  after a vocal phrase, pulling out wide reads best).
    Long vocal -> optional short cutaway, then back to the singer.
    """

    def __init__(self, cfg: LiveConfig, rng: Optional[random.Random] = None):
        self.cfg = cfg
        self.rng = rng or random.Random()
        self.pace = PacingEngine(cfg.min_shot_s)
        self.vocal = False
        self._vocal_start = 0.0
        self._cutaway_ref = 0.0        # last time we were "fresh" on singer
        self._cutaway_end: Optional[float] = None
        self._next_rotate_t: Optional[float] = None
        self._fresh_instrumental = True
        self._energy_ema: Optional[float] = None
        self._energy_dev = 3.0
        self._last_energy = NEG_INF_DB

    # -- energy tracking ----------------------------------------------------
    def _note_energy(self, level_db: float) -> None:
        if level_db <= NEG_INF_DB:
            return
        if self._energy_ema is None:
            self._energy_ema = level_db
            return
        diff = level_db - self._energy_ema
        self._energy_ema += 0.01 * diff
        self._energy_dev += 0.01 * (abs(diff) - self._energy_dev)

    def _shot_len(self) -> float:
        base = self.cfg.cut_interval_s
        jit = self.cfg.cut_jitter
        length = base * self.rng.uniform(1.0 - jit, 1.0 + jit)
        if (self.cfg.energy_pacing and self._energy_ema is not None
                and self._last_energy > NEG_INF_DB):
            # Louder-than-usual sections cut faster, quiet ones slower.
            z = (self._last_energy - self._energy_ema) / max(self._energy_dev, 1.5)
            length *= min(max(1.0 - 0.15 * z, 0.6), 1.4)
        return max(length, self.cfg.min_shot_s)

    def _pick_instrumental(self) -> Optional[str]:
        scenes = [s for s in self.cfg.instrumental_scenes if s]
        if not scenes:
            return None
        if self._fresh_instrumental and scenes[0] != self.pace.scene:
            return scenes[0]
        options = [s for s in scenes if s != self.pace.scene] or scenes
        return self.rng.choice(options)

    def defer_rotation(self, t: float, delay_s: float = 0.6) -> None:
        """Hold the instrumental rotation briefly — used while vocal
        evidence is building, so we don't burn a cut to another shot a
        beat before the singer comes in."""
        if not self.vocal:
            target = t + delay_s
            if self._next_rotate_t is None or self._next_rotate_t < target:
                self._next_rotate_t = target

    # -- main tick ----------------------------------------------------------
    def update(self, t: float, vocal_active: bool,
               energy_db: Optional[float] = None) -> Optional[Cut]:
        self._last_energy = energy_db if energy_db is not None else NEG_INF_DB
        if energy_db is not None:
            self._note_energy(energy_db)

        if vocal_active and not self.vocal:
            self.vocal = True
            self._vocal_start = t
            self._cutaway_ref = t
            self._cutaway_end = None
            self._next_rotate_t = None
            return self.pace.request(t, self.cfg.singer_scene,
                                     "vocals in — cut to singer",
                                     priority=True)
        if self.vocal and not vocal_active:
            self.vocal = False
            self._fresh_instrumental = True
            self._next_rotate_t = t + self.cfg.post_vocal_hold_s
            self._cutaway_end = None

        if self.vocal:
            return self._update_vocal(t)
        return self._update_instrumental(t)

    def _update_vocal(self, t: float) -> Optional[Cut]:
        cfg = self.cfg
        if self._cutaway_end is not None:
            if t >= self._cutaway_end:
                self._cutaway_end = None
                self._cutaway_ref = t
                return self.pace.request(t, cfg.singer_scene,
                                         "back to singer", priority=True)
            return None  # riding out the cutaway
        if (cfg.cutaway_every_s > 0 and cfg.instrumental_scenes
                and (t - self._cutaway_ref) >= cfg.cutaway_every_s):
            scene = self._pick_instrumental()
            if scene:
                cut = self.pace.request(t, scene, "cutaway during long vocal")
                if cut:
                    self._cutaway_end = t + cfg.cutaway_len_s
                    return cut
        return self.pace.request(t, cfg.singer_scene, "hold singer")

    def _update_instrumental(self, t: float) -> Optional[Cut]:
        if not self.cfg.instrumental_scenes:
            return None
        if t < self.pace.external_hold_until:
            # Operator cut manually: let their shot ride, resume rotation
            # only after the hold expires.
            self._next_rotate_t = max(self._next_rotate_t or 0.0,
                                      self.pace.external_hold_until)
            return None
        if self._next_rotate_t is None:  # engaged mid-instrumental
            self._next_rotate_t = t
        if t < self._next_rotate_t:
            return None
        scene = self._pick_instrumental()
        if not scene:
            return None
        cut = self.pace.request(t, scene, "instrumental — next shot")
        if cut or scene == self.pace.scene:
            self._fresh_instrumental = False
            self._next_rotate_t = t + self._shot_len()
        return cut
