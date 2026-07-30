"""4A filtergraph / command builder tests (pure — no ffmpeg invoked)."""

from __future__ import annotations

from app.modules.editing.edl import build_edl
from app.modules.editing.filtergraph import (
    build_burn_command,
    build_cut_command,
    build_filter_complex,
)
from app.modules.editing.types import JobSpec, PacingSpec, SceneSpec


def _job(music=None):
    scenes = [
        SceneSpec("h", 0, "avatar", True, False, "/h.mp4", 0, 2000),
        SceneSpec("p", 1, "broll", False, False, "/p.mp4", 2000, 3800, no_crop=True),
        SceneSpec("r", 2, "avatar", False, True, "/r.mp4", 3800, 6200),
    ]
    pacing = PacingSpec("p", 3, [2000, 1800, 2400], bpm_hint=120, ramp_factor=1.6)
    return JobSpec("job", scenes, pacing, vo_path="/vo.wav", music_path=music)


def test_filter_complex_hard_cut_concat_no_transitions():
    edl = build_edl(_job(music="/music.mp3"))
    fc, inputs = build_filter_complex(edl)
    assert "concat=n=3:v=1:a=0[vraw]" in fc
    # hard cuts only — no crossfades / dissolves
    assert "xfade" not in fc
    assert "dissolve" not in fc
    # Thai text never via drawtext
    assert "drawtext" not in fc


def test_filter_complex_normalization_and_ramp():
    edl = build_edl(_job(music="/music.mp3"))
    fc, _ = build_filter_complex(edl)
    # every branch normalizes to 1080x1920
    assert "scale=1080:1920:force_original_aspect_ratio=increase" in fc
    assert "crop=1080:1920" in fc
    # blurred-pad packshot branch present
    assert "boxblur=40:8" in fc
    # payoff ramp: setpts scaled by 1/1.6 = 0.625
    assert "setpts=0.625" in fc
    assert "atempo=1.6" in fc


def test_filter_complex_music_ducking_and_master():
    edl = build_edl(_job(music="/music.mp3"))
    fc, inputs = build_filter_complex(edl)
    assert "sidechaincompress=threshold=0.03:ratio=8" in fc
    assert "loudnorm=I=-14" in fc
    # inputs: 3 shots + vo + music
    assert inputs == ["/h.mp4", "/p.mp4", "/r.mp4", "/vo.wav", "/music.mp3"]


def test_filter_complex_without_music_uses_vo_master():
    edl = build_edl(_job(music=None))
    fc, inputs = build_filter_complex(edl)
    assert "sidechaincompress" not in fc
    assert "loudnorm=I=-14" in fc
    assert inputs[-1] == "/vo.wav"


def test_disclosure_baked_into_base_uses_libass():
    edl = build_edl(_job(music="/music.mp3"))
    fc, _ = build_filter_complex(edl, disclosure_ass="/r/disclosure.ass")
    assert "subtitles=" in fc            # libass
    assert "drawtext" not in fc          # never drawtext for the Thai label
    assert "[vout]" in fc


def test_build_cut_command_argv_shape():
    edl = build_edl(_job(music="/music.mp3"))
    argv = build_cut_command(edl, "/out/final.mp4")
    assert argv[0] == "ffmpeg"
    assert "-filter_complex" in argv
    assert argv[-1] == "/out/final.mp4"
    assert "-movflags" in argv and "+faststart" in argv
    assert "libx264" in argv
    assert "-map" in argv
    # deterministic threads pinned for T-9
    assert "-threads" in argv


def test_build_burn_command_uses_subtitles_and_copies_audio():
    argv = build_burn_command("/out/final.mp4", "/r/captions.ass", "/out/final_captioned.mp4")
    joined = " ".join(argv)
    assert "subtitles=" in joined
    assert "drawtext" not in joined
    # audio must not be re-encoded on the caption pass
    assert argv[argv.index("-c:a") + 1] == "copy"
    assert argv[-1] == "/out/final_captioned.mp4"
