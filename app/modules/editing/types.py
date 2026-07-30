"""Typed input contract (spec §4.0) + internal EDL / alignment structures.

These are plain dataclasses so the whole planning layer imports with zero heavy deps
and is trivially unit-testable. The canonical persisted model lives in ``app.core.models``
(``Scene``, ``PacingTemplate``, ``VideoJob``); ``worker.py`` maps DB rows onto the
``SceneSpec`` / ``PacingSpec`` shapes below (see ``worker._scene_spec_from_row``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

NormalizeMode = Literal["crop_cover", "blurred_pad"]
CaptionMode = Literal["karaoke", "static"]


# --------------------------------------------------------------------------- #
# §4.0 input contract (reproduced from §01/§02)
# --------------------------------------------------------------------------- #
@dataclass
class SceneSpec:
    """One authored scene resolved to a local clip (module input contract, §4.0)."""

    id: str
    index: int                       # authoring order from the Script module
    kind: Literal["avatar", "broll"]
    is_hook: bool                     # exactly ONE scene per job is the hook
    is_payoff: bool                   # 0..n payoff/"reveal" moments -> speed ramp
    asset_path: str                   # local path of the generated clip (MediaAsset)
    vo_start_ms: int                  # this scene's span inside the clean VO track
    vo_end_ms: int
    target_duration_ms: int | None = None   # optional per-shot override from template
    no_crop: bool = False             # packshot flag -> blurred-pad instead of crop-cover
    source_duration_ms: int | None = None    # probed clip length (optional)


@dataclass
class PacingSpec:
    """Pacing template (§4.0 / §02)."""

    id: str
    shot_count: int
    per_shot_ms: list[int]
    bpm_hint: float | None = None
    max_avg_cut_ms: int = 2500
    ramp_factor: float = 1.6


@dataclass
class JobSpec:
    """Everything the render worker needs, resolved from a ``VideoJob`` (§4.0)."""

    id: str
    scenes: list[SceneSpec]
    pacing: PacingSpec
    vo_path: str                      # the CLEAN VO (pre-music) — caption alignment source
    music_path: str | None = None
    fps: int = 30


# --------------------------------------------------------------------------- #
# EDL (Edit Decision List) — the retimed, normalized shot plan (§4A)
# --------------------------------------------------------------------------- #
@dataclass
class Shot:
    """A single hard-cut shot after hook-first / beat-fit / ramp planning."""

    scene_id: str
    input_index: int                  # ffmpeg -i ordinal for this shot's source clip
    source_path: str
    kind: Literal["avatar", "broll"]
    normalize: NormalizeMode
    is_hook: bool
    is_payoff: bool
    # frame-exact boundaries on the shipped (retimed) timeline
    start_frame: int
    end_frame: int
    # source in/out (seconds) — where to trim the source clip
    src_in_s: float
    src_out_s: float
    # audio: this shot's slice of the clean VO
    vo_start_ms: int
    vo_end_ms: int
    ramp_factor: float = 1.0          # 1.0 = no ramp; >1 speeds up (payoff)

    @property
    def duration_frames(self) -> int:
        return max(0, self.end_frame - self.start_frame)

    def duration_ms(self, fps: int = 30) -> float:
        return self.duration_frames * 1000.0 / fps


@dataclass
class EDL:
    """The complete render plan (video + audio EDL mirror each other exactly, §4A)."""

    job_id: str
    fps: int
    shots: list[Shot]
    bpm: float
    beat_times: list[float] = field(default_factory=list)
    music_path: str | None = None
    vo_path: str = ""

    @property
    def shot_count(self) -> int:
        return len(self.shots)

    def total_frames(self) -> int:
        return sum(s.duration_frames for s in self.shots)

    def total_duration_s(self) -> float:
        return self.total_frames() / self.fps

    def avg_cut_ms(self) -> float:
        if not self.shots:
            return 0.0
        return sum(s.duration_ms(self.fps) for s in self.shots) / len(self.shots)

    def as_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "fps": self.fps,
            "bpm": self.bpm,
            "beat_times": self.beat_times,
            "music_path": self.music_path,
            "vo_path": self.vo_path,
            "shots": [
                {
                    "scene_id": s.scene_id,
                    "input_index": s.input_index,
                    "source_path": s.source_path,
                    "kind": s.kind,
                    "normalize": s.normalize,
                    "is_hook": s.is_hook,
                    "is_payoff": s.is_payoff,
                    "start_frame": s.start_frame,
                    "end_frame": s.end_frame,
                    "src_in_s": s.src_in_s,
                    "src_out_s": s.src_out_s,
                    "vo_start_ms": s.vo_start_ms,
                    "vo_end_ms": s.vo_end_ms,
                    "ramp_factor": s.ramp_factor,
                }
                for s in self.shots
            ],
        }


# --------------------------------------------------------------------------- #
# Alignment structures (§4B)
# --------------------------------------------------------------------------- #
@dataclass
class WordTiming:
    word: str
    start: float           # seconds on the clean-VO timeline
    end: float
    score: float = 1.0     # per-word alignment confidence


@dataclass
class Segment:
    text: str
    start: float
    end: float
    words: list[WordTiming] = field(default_factory=list)
    # "acoustic" = a real Thai align-model produced these times; "interpolated" = drift risk
    align_type: Literal["acoustic", "interpolated"] = "acoustic"


@dataclass
class AlignResult:
    segments: list[Segment]
    language: str = "th"
    # meta["type"] == "torchaudio" means a real acoustic model aligned (see §4B.3)
    meta: dict = field(default_factory=dict)
    degraded: bool = False   # True -> Thai align model absent -> all-static fallback (§4D.4)
