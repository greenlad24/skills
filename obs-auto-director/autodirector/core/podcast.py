"""Podcast director: floor-holding conversation logic and shot selection."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional

from .pacing import Cut, PacingEngine
from .vad import NEG_INF_DB


@dataclass
class SpeakerCfg:
    name: str
    medium_scene: str
    closeup_scene: str


@dataclass
class PodcastConfig:
    speakers: List[SpeakerCfg] = field(default_factory=list)
    wide_scene: str = ""              # optional two-shot
    min_shot_s: float = 3.5           # v2: raised from 2.6 (relaxed switching)
    pause_tolerance_s: float = 1.2    # holder keeps floor through short pauses
    backchannel_max_s: float = 0.9    # "mm-hm" never steals the floor
    interrupt_commit_s: float = 1.6   # sustained overlap steals the floor
    closeup_after_s: float = 10.0     # push in once someone holds forth
    closeup_grace_s: float = 3.0      # wait up to this for a natural beat
    closeup_max_s: float = 25.0       # then relax back out for variety
    emphasis_db: float = 6.0          # sudden loudness => earlier close-up
    emphasis_hold_s: float = 1.0
    park_after_s: float = 6.0         # dead air: release floor, rest on wide
    utter_debounce_s: float = 0.3     # a blip this short continues an utterance
    rapid_window_s: float = 10.0      # N floor changes in this window ...
    rapid_cuts: int = 3               # ... sends us to the wide shot
    rapid_calm_s: float = 6.0


class _SpeakerState:
    def __init__(self) -> None:
        self.talking = False
        self.utter_start = 0.0
        self.last_talk_t = -1e9
        self.level_ema: Optional[float] = None
        self.talk_accum = 0.0
        self.emph_since: Optional[float] = None


class PodcastDirector:
    """Directs a two-person (or N-person) conversation.

    Floor logic: the current speaker keeps the floor through pauses shorter
    than pause_tolerance; short interjections never steal it; a sustained
    interruption does. Shot logic: a floor change lands on the new
    speaker's MEDIUM; hold the floor and we push to the CLOSE-UP — on a
    natural micro-pause when possible — then relax back to medium after a
    while. A flurry of floor changes cuts to the wide two-shot until the
    exchange settles. Dead air parks the floor on the wide.
    """

    def __init__(self, cfg: PodcastConfig):
        self.cfg = cfg
        self.pace = PacingEngine(cfg.min_shot_s)
        self.speakers = [_SpeakerState() for _ in cfg.speakers]
        self.holder: Optional[int] = None
        self.floor_since = 0.0
        self.shot = "medium"          # "medium" | "close"
        self.shot_since = 0.0
        self.wide = False
        self.changes: deque = deque(maxlen=16)
        self._pending = ("", False)   # (reason, priority) for the next cut
        self._dt = 0.05
        self._last_t: Optional[float] = None

    # -- helpers ------------------------------------------------------------
    def _silence_for(self, t: float, i: int) -> float:
        return t - self.speakers[i].last_talk_t

    def _utter_len(self, t: float, i: int) -> float:
        st = self.speakers[i]
        return (t - st.utter_start) if st.talking else 0.0

    def _take_floor(self, t: float, i: int, reason: str, priority: bool) -> None:
        self.holder = i
        self.floor_since = t
        self.shot = "medium"
        self.shot_since = t
        self.changes.append(t)
        self._note_transition(reason, priority)

    def _note_transition(self, reason: str, priority: bool) -> None:
        self._pending = (reason, priority)

    # -- main tick ----------------------------------------------------------
    def update(self, t: float, talking: List[bool],
               levels: Optional[List[float]] = None) -> Optional[Cut]:
        cfg = self.cfg
        if self._last_t is not None:
            raw_dt = t - self._last_t
            if raw_dt > 0.5:
                # Time discontinuity (UI stall, pause/resume): the gap must
                # not be counted as utterance length or holder silence —
                # otherwise a fused pre/post-gap backchannel reads as a long
                # interruption and steals the floor.
                self._dt = 0.25
                for st in self.speakers:
                    if st.talking:
                        st.utter_start = t
                if self.holder is not None:
                    self.speakers[self.holder].last_talk_t = t
            else:
                self._dt = max(raw_dt, 1e-3)
        self._last_t = t

        # 1. Bookkeeping per speaker.
        for i, st in enumerate(self.speakers):
            talk = talking[i] if i < len(talking) else False
            if talk and not st.talking:
                # Debounced: a sub-utter_debounce_s dropout (detector
                # flicker) continues the same utterance rather than
                # restarting the interrupt-commit clock.
                if (t - st.last_talk_t) >= cfg.utter_debounce_s:
                    st.utter_start = t
            st.talking = talk
            if talk:
                st.last_talk_t = t
                st.talk_accum += self._dt
                if levels and i < len(levels) and levels[i] > NEG_INF_DB:
                    lvl = levels[i]
                    if st.level_ema is None:
                        st.level_ema = lvl
                    else:
                        st.level_ema += 0.005 * (lvl - st.level_ema)

        # 2. Floor logic.
        if self.holder is None:
            candidates = [i for i, st in enumerate(self.speakers) if st.talking]
            if candidates:
                first = max(candidates, key=lambda i: self._utter_len(t, i))
                self._take_floor(t, first,
                                 f"{cfg.speakers[first].name} opens",
                                 priority=True)
        else:
            h = self.holder
            challengers = [
                i for i, st in enumerate(self.speakers)
                if i != h and st.talking
                and self._utter_len(t, i) >= cfg.backchannel_max_s
            ]
            if challengers:
                c = max(challengers, key=lambda i: self._utter_len(t, i))
                holder_silent = self._silence_for(t, h)
                if holder_silent >= cfg.pause_tolerance_s:
                    self._take_floor(t, c,
                                     f"{cfg.speakers[c].name} takes the floor",
                                     priority=True)
                elif (self._utter_len(t, c) >= cfg.interrupt_commit_s
                      and (t - self.floor_since) >= cfg.interrupt_commit_s):
                    # The overlap must also outlast the last floor change,
                    # so a fresh holder can't be instantly stolen from by a
                    # challenger whose utterance merely started earlier.
                    self._take_floor(t, c,
                                     f"{cfg.speakers[c].name} interrupts",
                                     priority=False)

        # 2b. Dead air: nobody talking and the holder silent for a while —
        # release the floor and rest on the wide (if any) rather than
        # eventually pushing in on a silent face.
        if (self.holder is not None
                and not any(s.talking for s in self.speakers)
                and (t - self.speakers[self.holder].last_talk_t)
                >= cfg.park_after_s):
            self.holder = None
            self.wide = False
            self.changes.clear()
            self._pending = ("", False)
            if cfg.wide_scene:
                return self.pace.request(t, cfg.wide_scene,
                                         "dead air — resting on wide")
            return None

        if self.holder is None:
            return None
        h = self.holder
        st = self.speakers[h]
        sp = cfg.speakers[h]

        # 3. Rapid-exchange wide shot.
        if cfg.wide_scene:
            recent = [c for c in self.changes if t - c <= cfg.rapid_window_s]
            if not self.wide and len(recent) >= cfg.rapid_cuts:
                self.wide = True
                self._note_transition("rapid exchange — going wide", True)
            elif self.wide and self.changes and \
                    (t - self.changes[-1]) >= cfg.rapid_calm_s:
                self.wide = False
                self.shot = "medium"
                self.shot_since = t
                self.changes.clear()  # settled: stale changes must not
                                      # immediately re-trigger the wide
                self._note_transition(
                    f"exchange settled — back to {sp.name}", False)

        # 4. Shot escalation (only when not wide).
        if not self.wide:
            emphatic = False
            if (levels and h < len(levels) and st.level_ema is not None
                    and st.talk_accum > 3.0 and st.talking
                    and levels[h] > st.level_ema + cfg.emphasis_db):
                if st.emph_since is None:
                    st.emph_since = t
                emphatic = (t - st.emph_since) >= cfg.emphasis_hold_s
            else:
                st.emph_since = None

            if self.shot == "medium":
                held = t - self.shot_since
                # Push-ins require a holder who is actually holding forth —
                # dead air must not read as a "micro-pause to cut on".
                recently_active = (t - st.last_talk_t) < 2.0
                if emphatic:
                    self.shot = "close"
                    self.shot_since = t
                    self._note_transition(
                        f"{sp.name} gets emphatic — push in", False)
                elif held >= cfg.closeup_after_s and recently_active and (
                        not st.talking  # micro-pause: a natural beat to cut on
                        or held >= cfg.closeup_after_s + cfg.closeup_grace_s):
                    self.shot = "close"
                    self.shot_since = t
                    self._note_transition(
                        f"{sp.name} holding forth — close-up", False)
            elif self.shot == "close":
                if (t - self.shot_since) >= cfg.closeup_max_s:
                    self.shot = "medium"
                    self.shot_since = t
                    self._note_transition("variety — back to medium", False)

        # 5. Resolve desired scene and request the cut.
        if self.wide:
            desired = cfg.wide_scene
        else:
            desired = sp.closeup_scene if self.shot == "close" else sp.medium_scene
        reason, priority = self._pending
        cut = self.pace.request(t, desired, reason or "shot sync", priority)
        if cut:
            self._pending = ("", False)
        return cut
