"""Per-speaker voice measurement: what a broadcast engineer reads off
their meters, computed from the speaker's own captured audio (pre-OBS).

Because the analyzer captures the mic device directly, all measurements
are *pre-chain*: the control loops are open-loop and cannot oscillate
through their own corrections.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..dsp.frontend import HopFeatures, NEG_INF_DB


@dataclass
class Snapshot:
    """One reviewable measurement set for a speaker."""
    floor_db: float = NEG_INF_DB      # room noise while silent
    speech_db: float = NEG_INF_DB     # average speech level
    peak_db: float = NEG_INF_DB       # recent speech peaks
    tilt_db: float = 0.0              # spectral tilt during speech (hf-lf)
    crest_db: float = 0.0             # peak - average (dynamics)
    gate_chatter_per_min: float = 0.0 # VAD flips: gate instability signal
    clip_events: int = 0              # near-0 dBFS hits
    talk_ratio: float = 0.0           # fraction of time talking


class SpeakerMeter:
    """Streaming per-speaker measurement from hop features + VAD state."""

    def __init__(self, window_s: float = 30.0, hop_rate: float = 93.75):
        n = int(window_s * hop_rate)
        self._silent_rms: deque = deque(maxlen=n)
        self._speech_rms: deque = deque(maxlen=n)
        self._speech_tilt: deque = deque(maxlen=n)
        self._talking = deque(maxlen=n)
        self._flips: deque = deque(maxlen=n)
        self._last_active: Optional[bool] = None
        self._clip_events = 0
        self._window_s = window_s

    def update(self, hop: HopFeatures, active: bool) -> None:
        if active:
            self._speech_rms.append(hop.rms_db)
            self._speech_tilt.append(hop.tilt_db)
        elif hop.rms_db > NEG_INF_DB + 1.0:
            self._silent_rms.append(hop.rms_db)
        self._talking.append(1.0 if active else 0.0)
        flip = self._last_active is not None and active != self._last_active
        self._flips.append(1.0 if flip else 0.0)
        self._last_active = active
        if hop.rms_db > -1.0:
            self._clip_events += 1

    def snapshot(self) -> Snapshot:
        s = Snapshot()
        if self._silent_rms:
            s.floor_db = float(np.percentile(self._silent_rms, 20))
        if self._speech_rms:
            arr = np.array(self._speech_rms)
            s.speech_db = float(arr.mean())
            s.peak_db = float(np.percentile(arr, 95))
            s.crest_db = s.peak_db - s.speech_db
        if self._speech_tilt:
            s.tilt_db = float(np.mean(self._speech_tilt))
        if self._talking:
            s.talk_ratio = float(np.mean(self._talking))
            covered_s = len(self._talking) / 93.75
            s.gate_chatter_per_min = float(
                sum(self._flips) / max(covered_s, 1.0) * 60.0)
        s.clip_events = self._clip_events
        return s
