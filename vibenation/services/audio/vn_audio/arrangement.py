"""Arrangement follower: keeps the mix up with a band whose line-up changes all night.

Singers come and go, swap lead and backing; players come and go, take solos, go back to rhythm.
Every analyzer frame (10/s) this decides, per channel, a small "arrangement offset" (dB) that the
graph adds to the fader (and so to the post-fader sends):

  lead vocal     0 dB    the singing voice that carries the song (most continuous + loudest)
  backing vocal  -3 dB   any other voice singing at the same time
  solo           +2 dB   a melodic instrument that takes over while no lead vocal sings
                         (user rule: the balance stays almost the same all night, so these moves are small)
  muted          (off)   a supporting channel (CORE excluded) whose player has been silent for 8 s (user rule:
                         "not playing = muted until playing consistently"): no bleed, no mud.
                         CORE channels (guitar amp, piano, vocals, bass DI, synth bass) are never muted
                         unless silent for 10 minutes, and open again on the first played frame.
                         It opens when the player plays consistently (5 of the last 6 frames)
                         or at once on a strong entry (within 6 dB of the working level).
                         Vocal mics (user rule): open on the first sung frame, close only after
                         5 minutes with nobody singing.

Pure logic, no audio: testable offline on the stems (tools/arrangement_sim.py).
Moves are smooth (no clicks): opening from mute is fast, closing is a slow fade, and balance moves
glide at 0.5 dB/s so nobody hears them (user, 17 Oct 2026).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

FPS = 10
VOICES = (9, 10)                      # always-voice channels (ch 11 / 16 join when the classifier says voice)
SOLOISTS = (5, 6)                     # guitar amp and piano (6 = pair 6+7). Sax, harmonica, guitar DI, DI 1 and congas 2 are
                                      # supporting channels and never solo (user, 18 Oct 2026)
PAIRS = {6: (6, 7)}                   # a stereo pair moves together
AUTOMUTE = tuple(range(4, 17))        # everything but kick, snare, overheads
LINE = (4, 6, 7, 8, 12, 14)           # DI/line inputs: no bleed, so any signal means playing

BACKING_DB = -3.0
SOLO_DB = 2.0
MUTE_DB = -60.0
MUTE_AFTER_S = 8.0
VOICE_MUTE_AFTER_S = 300.0            # vocal mics stay open 5 min after the last singing
CORE = (5, 6, 7, 9, 10, 12, 14)       # user rule: never auto-muted unless silent this long (drums never)
CORE_MUTE_AFTER_S = 600.0
STRONG_DB = -26.0                     # within 6 dB of the -20 dBFS working level: open at once
LEAD_SWITCH_S = 2.0                   # a new lead must win for this long (hysteresis)
SOLO_START_S = 3.0
VOCAL_REST_S = 4.0                    # a solo needs the lead vocal resting this long (not a breath)
PHRASE_GAP_S = 3.0                    # gaps between sung phrases shorter than this still count as singing
SOLO_END_S = 1.5
UP_DB_PER_FRAME = 30.0                # open: -60 -> 0 in 0.2 s
DOWN_DB_PER_FRAME = 1.0               # close: a 6 s fade
GLIDE_DB_PER_FRAME = 0.05             # balance moves (lead/backing/solo): 0.5 dB/s, unnoticeable


@dataclass
class ChannelState:
    hist: deque = field(default_factory=lambda: deque(maxlen=4 * FPS))       # 4 s of (playing, level)
    ref: deque = field(default_factory=lambda: deque(maxlen=60 * FPS))       # 60 s of active levels
    silent_s: float = 99.0
    offset: float = 0.0
    muted: bool = True                                                        # until it plays (CORE: open from the start)


class Arrangement:
    def __init__(self) -> None:
        self.ch = {n: ChannelState(silent_s=0.0, muted=False) if n in CORE else ChannelState() for n in range(1, 17)}
        self.lead: int | None = None
        self.challenger: tuple[int, float] | None = None   # (channel, seconds winning)
        self.solo: int | None = None
        self.solo_cand: tuple[int, float] | None = None
        self.solo_end_s = 0.0
        self.voices = list(VOICES)
        self.held: set[int] = set()                         # channels a human holds: never moved

    # ---------- inputs ----------

    def frame(self, playing: dict[int, bool], level: dict[int, float], raw: dict[int, float] | None = None) -> dict[int, float]:
        """playing: source itself playing (not bleed); level: its level after trim (dB);
        raw: input level before trim (line inputs count any signal as playing).
        Returns the arrangement offset per channel (only channels that changed)."""
        dt = 1 / FPS
        for n, c in self.ch.items():
            p = playing.get(n, False) or (n in LINE and raw is not None and raw.get(n, -120.0) > -60)
            c.hist.append((p, level.get(n, -120.0)))
            c.silent_s = 0.0 if p else c.silent_s + dt
            if p:
                c.ref.append(level.get(n, -120.0))
            voice = n in self.voices
            if c.muted:
                recent = list(c.hist)[-6:]
                if ((voice or n in CORE) and p) or sum(1 for q, _ in recent if q) >= 5 or (p and level.get(n, -120.0) > STRONG_DB):
                    c.muted = False
            elif c.silent_s >= (CORE_MUTE_AFTER_S if n in CORE else VOICE_MUTE_AFTER_S if voice else MUTE_AFTER_S):
                c.muted = True
        self._follow_lead(dt)
        self._follow_solo(dt)
        return self._targets()

    # ---------- lead / backing ----------

    def _vocal_score(self, n: int) -> float:
        h = self.ch[n].hist
        on = [lvl for p, lvl in h if p]
        if not on:
            return -999.0
        return len(on) / len(h) * 20 + sorted(on)[len(on) // 2]  # continuity first, then level

    def _follow_lead(self, dt: float) -> None:
        singing = [n for n in self.voices if self.ch[n].silent_s < 1.5]
        if not singing:
            self.challenger = None
            if self.lead is not None and self.ch[self.lead].silent_s > 6:
                self.lead = None  # nobody has sung for a while: next voice in is lead at once
            return
        best = max(singing, key=self._vocal_score)
        if self.lead is None or self.lead not in singing and self.ch[self.lead].silent_s > 3:
            self.lead, self.challenger = best, None
            return
        if best == self.lead:
            self.challenger = None
            return
        if self.challenger and self.challenger[0] == best:
            self.challenger = (best, self.challenger[1] + dt)
        else:
            self.challenger = (best, dt)
        if self.challenger[1] >= LEAD_SWITCH_S and self._vocal_score(best) > self._vocal_score(self.lead) + 3:
            self.lead, self.challenger = best, None

    def lead_singing(self) -> bool:
        return self.lead is not None and self.ch[self.lead].silent_s < PHRASE_GAP_S

    def vocal_resting(self) -> bool:
        return all(self.ch[n].silent_s >= VOCAL_REST_S for n in self.voices)

    # ---------- solo / rhythm ----------

    def _lift(self, n: int) -> float:
        """How far a player is above their own running level, now (2 s), in dB."""
        c = self.ch[n]
        recent = [lvl for p, lvl in list(c.hist)[-2 * FPS:] if p]
        if len(recent) < 1.5 * FPS or len(c.ref) < 20 * FPS:
            return -99.0
        return sorted(recent)[len(recent) // 2] - sorted(c.ref)[len(c.ref) // 2]

    def _follow_solo(self, dt: float) -> None:
        if self.solo is not None:
            voice_back = any(self.ch[n].silent_s == 0 for n in self.voices)
            ends = voice_back or self.ch[self.solo].silent_s > 1.0 or self._lift(self.solo) < 0
            self.solo_end_s = self.solo_end_s + dt if ends else 0.0
            if self.solo_end_s >= SOLO_END_S:
                self.solo, self.solo_end_s = None, 0.0
            return
        if not self.vocal_resting():
            self.solo_cand = None
            return
        cands = [(self._lift(n), n) for n in SOLOISTS if self.ch[n].silent_s == 0 and self._lift(n) >= 2.0]
        if not cands:
            self.solo_cand = None
            return
        _, best = max(cands)
        self.solo_cand = (best, self.solo_cand[1] + dt) if self.solo_cand and self.solo_cand[0] == best else (best, dt)
        if self.solo_cand[1] >= SOLO_START_S:
            self.solo, self.solo_cand = best, None

    # ---------- outputs ----------

    def role(self, n: int) -> str:
        if n in AUTOMUTE and self.ch[n].muted:
            return 'muted'
        if n == self.lead:
            return 'lead'
        if n in self.voices and self.ch[n].silent_s < 1.5:
            return 'backing'
        if self.solo is not None and n in PAIRS.get(self.solo, (self.solo,)):
            return 'solo'
        return ''

    def _targets(self) -> dict[int, float]:
        want_db = {'lead': 0.0, 'backing': BACKING_DB, 'solo': SOLO_DB, 'muted': MUTE_DB, '': 0.0}
        changed = {}
        for n, c in self.ch.items():
            if n in self.held:
                continue
            want = want_db[self.role(n)]
            if want > c.offset and c.offset < -20:
                step = UP_DB_PER_FRAME    # opening from mute: fast, the first notes count
            elif want == MUTE_DB:
                step = DOWN_DB_PER_FRAME  # closing: a slow fade
            else:
                step = GLIDE_DB_PER_FRAME # lead/backing/solo moves glide: a musician shouldn't hear them
            new = c.offset + max(-step, min(step, want - c.offset))
            if abs(new - c.offset) >= 0.01:
                c.offset = round(new, 2)
                changed[n] = c.offset
        return changed

    def summary(self) -> dict:
        return {
            'lead': self.lead if self.lead_singing() else None,
            'backing': [n for n in self.voices if self.role(n) == 'backing'],
            'solo': self.solo,
            'muted': [n for n in AUTOMUTE if self.role(n) == 'muted'],
        }
