"""Stem analysis: per-channel listening for the Mix Engineer.

Studio One routes each channel's direct out to a multi-channel virtual
device (BlackHole 16ch); we meter every stem individually — activity,
loudness balance, spectral placement — which is what the AI engineer
reasons over, and what gives the director ground-truth vocal activity.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from ..core.vad import LevelVAD, NEG_INF_DB
from ..dsp.frontend import Frontend, HopFeatures


@dataclass
class StemConfig:
    channel: int                # 0-based channel in the capture device
    name: str                   # "Lead Vox", "Guitar L", ...
    role: str = ""              # "lead_vocal" | "backing_vocal" | "" generic


ROLE_KEYWORDS = [
    ("lead_vocal", ["lead vox", "lead voc", "ld vox", "main vox", "vox 1",
                    "lead", "ldvox"]),
    ("backing_vocal", ["bgv", "backing", "back vox", "bvox", "harmony",
                       "harm ", "choir", "vox 2", "vox 3"]),
    ("lead_vocal", ["vox", "voc", "sing"]),   # bare "Vox" => lead
    ("drums", ["kick", "snare", "tom", "hat", "oh ", "overhead", "drum",
               "cymbal", "perc"]),
    ("bass", ["bass", "sub"]),
    ("guitar", ["gtr", "guitar", "git"]),
    ("keys", ["keys", "piano", "synth", "organ", "rhodes", "pad"]),
    ("horns", ["horn", "sax", "trump", "tromb", "brass"]),
    ("strings", ["violin", "cello", "string", "fiddle"]),
]


def infer_role(name: str) -> str:
    """Instrument role from a channel name ('Kick', 'Gtr L', 'Lead Vox').
    Channel names come straight from Studio One via the MCU scribble
    strips, so this usually needs no manual mapping."""
    low = f" {name.lower()} "
    for role, keys in ROLE_KEYWORDS:
        for k in keys:
            if k in low:
                return role
    return ""


@dataclass
class StemSnapshot:
    name: str
    role: str
    active: bool
    level_db: float             # instantaneous
    loud_db: float              # EMA loudness while active
    floor_db: float
    presence_db: float          # 2-5 kHz energy while active (masking band)
    activity_ratio: float       # fraction of recent time active
    dead: bool                  # silent while the rest of the band plays


class StemAnalyzer:
    """Per-stem metering over one multi-channel capture."""

    def __init__(self, stems: List[StemConfig], hop_rate: float = 93.75):
        self.stems = stems
        n = int(30.0 * hop_rate)
        self._fes = [Frontend() for _ in stems]
        self._vads = [LevelVAD(margin_db=8.0, attack_s=0.1, release_s=0.5)
                      for _ in stems]
        self._level = [NEG_INF_DB] * len(stems)
        self._loud: List[Optional[float]] = [None] * len(stems)
        self._presence: List[Optional[float]] = [None] * len(stems)
        self._activity = [deque(maxlen=n) for _ in stems]
        self._active = [False] * len(stems)
        self._last_active_t = [-1e9] * len(stems)
        self._clock = 0.0

    # ------------------------------------------------------------------
    def process(self, pcm: np.ndarray, clock: float) -> None:
        """pcm: (n, channels) float array from the capture device."""
        self._clock = clock
        if pcm.ndim == 1:
            pcm = pcm[:, None]
        for i, stem in enumerate(self.stems):
            if stem.channel >= pcm.shape[1]:
                continue
            for hop in self._fes[i].process(pcm[:, stem.channel]):
                self._ingest(i, hop)

    def _ingest(self, i: int, hop: HopFeatures) -> None:
        active = self._vads[i].update(hop.t, hop.rms_db)
        self._active[i] = active
        self._level[i] = hop.rms_db
        self._activity[i].append(1.0 if active else 0.0)
        if active:
            self._last_active_t[i] = hop.t
            self._loud[i] = hop.rms_db if self._loud[i] is None else \
                self._loud[i] + 0.01 * (hop.rms_db - self._loud[i])
            pres = hop.band_db["presence"]
            self._presence[i] = pres if self._presence[i] is None else \
                self._presence[i] + 0.01 * (pres - self._presence[i])

    # ------------------------------------------------------------------
    def vocal_activity(self) -> Optional[bool]:
        """Ground truth for the director: is a lead-vocal stem active?
        None when no stem is tagged lead_vocal."""
        leads = [i for i, s in enumerate(self.stems)
                 if s.role == "lead_vocal"]
        if not leads:
            return None
        return any(self._active[i] for i in leads)

    def band_playing(self) -> bool:
        return sum(1 for a in self._active if a) >= 2

    def masking_score(self) -> Optional[float]:
        """How badly non-vocal stems crowd the vocal's presence band
        (2-5 kHz) while the vocal is active. >0 means the band is louder
        than the vocal where the vocal lives."""
        leads = [i for i, s in enumerate(self.stems)
                 if s.role == "lead_vocal" and self._active[i]
                 and self._presence[i] is not None]
        if not leads:
            return None
        vocal_pres = max(self._presence[i] for i in leads)
        others = [self._presence[i] for i, s in enumerate(self.stems)
                  if s.role not in ("lead_vocal", "backing_vocal")
                  and self._active[i] and self._presence[i] is not None]
        if not others:
            return None
        crowd = 10.0 * np.log10(sum(10.0 ** (p / 10.0) for p in others))
        return float(crowd - vocal_pres)

    def snapshots(self) -> Dict[str, StemSnapshot]:
        out = {}
        band_on = self.band_playing()
        for i, stem in enumerate(self.stems):
            ratio = float(np.mean(self._activity[i])) \
                if self._activity[i] else 0.0
            dead = (band_on and not self._active[i]
                    and (self._clock - self._last_active_t[i]) > 30.0
                    and ratio < 0.02)
            out[stem.name] = StemSnapshot(
                name=stem.name, role=stem.role, active=self._active[i],
                level_db=round(max(self._level[i], NEG_INF_DB), 1),
                loud_db=round(self._loud[i], 1)
                if self._loud[i] is not None else NEG_INF_DB,
                floor_db=round(self._vads[i].floor_db, 1),
                presence_db=round(self._presence[i], 1)
                if self._presence[i] is not None else NEG_INF_DB,
                activity_ratio=round(ratio, 3),
                dead=dead)
        return out
