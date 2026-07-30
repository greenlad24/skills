"""Render / caption / compliance configuration for the editing module (spec §4E).

These are the module's own constants — they mirror the YAML block in §4E. They are
plain dataclasses (not settings) so the pure builders can be imported and unit-tested
without any environment. Only run-mode flags (``DRY_RUN``) come from ``app.core.config``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Render target (§4E)
# --------------------------------------------------------------------------- #
WIDTH = 1080
HEIGHT = 1920
FPS = 30
PIX_FMT = "yuv420p"


@dataclass(frozen=True)
class RenderConfig:
    width: int = WIDTH
    height: int = HEIGHT
    fps: int = FPS
    pix_fmt: str = PIX_FMT
    # video
    vcodec: str = "libx264"
    preset: str = "medium"
    crf: int = 18
    profile: str = "high"
    color: str = "bt709"
    # audio
    acodec: str = "aac"
    abitrate: str = "192k"
    target_lufs: float = -14.0
    true_peak_dbtp: float = -1.5
    lra: float = 11.0
    faststart: bool = True
    # deterministic re-render (§4D.2): pin threads for bit-exactness in regression tests
    deterministic_threads: int | None = 1


@dataclass(frozen=True)
class CaptionStyle:
    renderer: str = "libass"                 # NOT drawtext (§4B.5)
    font: str = "Noto Sans Thai"             # or Sarabun / bold TikTok weight
    fontsdir: str = "/usr/share/fonts/thai"
    size: int = 84
    primary: str = "&H00FFFFFF"              # white fill (ASS BGR + alpha)
    highlight: str = "&H0000E5FF"            # karaoke sweep colour (TikTok yellow)
    outline: int = 4
    shadow: int = 2
    align: int = 8                           # 8 = top-center
    margin_v: int = 280                      # sits in the upper third
    karaoke_conf_threshold: float = 0.5


@dataclass(frozen=True)
class DisclosureConfig:
    """AI-generated disclosure (§4C)."""

    text: str = "สร้างโดย AI  •  AI-generated"
    window_s: tuple[float, float] = (0.0, 3.0)
    # Bake into final.mp4 (TikTok Shop). When true the render pass burns a disclosure-
    # only ASS into the base video and the caption pass omits the badge (no double label).
    in_base: bool = True
    font: str = "Noto Sans Thai"
    size: int = 44


@dataclass(frozen=True)
class PacingConfig:
    max_avg_cut_ms: int = 2500
    default_bpm: float = 100.0
    ramp_factor: float = 1.6


@dataclass(frozen=True)
class EditingConfig:
    render: RenderConfig = field(default_factory=RenderConfig)
    caption: CaptionStyle = field(default_factory=CaptionStyle)
    disclosure: DisclosureConfig = field(default_factory=DisclosureConfig)
    pacing: PacingConfig = field(default_factory=PacingConfig)


# Module-level default singleton (importers use this).
CONFIG = EditingConfig()
