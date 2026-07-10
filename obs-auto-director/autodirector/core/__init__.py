"""Directing core: pure logic, no OBS or audio-device dependencies."""

from .pacing import Cut, PacingEngine
from .vad import NEG_INF_DB, LevelVAD, apply_crosstalk_gate
from .live import LiveConfig, LiveDirector
from .podcast import PodcastConfig, PodcastDirector, SpeakerCfg
from .switcher import (EvidenceSwitcher, SwitchEvent, SwitcherConfig,
                       min_shot_factor)

__all__ = [
    "Cut", "PacingEngine",
    "NEG_INF_DB", "LevelVAD", "apply_crosstalk_gate",
    "LiveConfig", "LiveDirector",
    "PodcastConfig", "PodcastDirector", "SpeakerCfg",
    "EvidenceSwitcher", "SwitchEvent", "SwitcherConfig", "min_shot_factor",
]
