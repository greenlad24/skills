"""4A planning-engine tests (pure — no ffmpeg/librosa)."""

from __future__ import annotations

import math

import pytest

from app.modules.editing.edl import (
    atempo_chain,
    build_edl,
    fit_pacing,
    frames_per_beat,
    hook_first,
    ramp_setpts_factor,
    snap_to_beat_frame,
    synth_beat_grid,
    validate_scenes,
)
from app.modules.editing.types import JobSpec, PacingSpec, SceneSpec


def _scene(i, hook=False, payoff=False, kind="avatar", no_crop=False):
    return SceneSpec(
        id=f"s{i}",
        index=i,
        kind=kind,
        is_hook=hook,
        is_payoff=payoff,
        asset_path=f"/clips/{i}.mp4",
        vo_start_ms=i * 2000,
        vo_end_ms=i * 2000 + 2000,
        no_crop=no_crop,
    )


def test_hook_first_promotes_single_hook():
    scenes = [_scene(0), _scene(1, hook=True), _scene(2)]
    ordered = hook_first(scenes)
    assert ordered[0].id == "s1"
    assert [s.id for s in ordered[1:]] == ["s0", "s2"]  # relative order preserved


def test_validate_scenes_requires_exactly_one_hook():
    with pytest.raises(ValueError):
        validate_scenes([_scene(0), _scene(1)])  # zero hooks
    with pytest.raises(ValueError):
        validate_scenes([_scene(0, hook=True), _scene(1, hook=True)])  # two hooks
    validate_scenes([_scene(0, hook=True), _scene(1)])  # ok


def test_frames_per_beat_math():
    assert frames_per_beat(120, 30) == pytest.approx(15.0)
    assert frames_per_beat(100, 30) == pytest.approx(18.0)
    assert round(frames_per_beat(128, 30)) == 14


def test_snap_to_beat_frame_quantizes_to_integer_frame():
    beats = [0.0, 0.5, 1.0, 1.5]
    # 0.52s -> nearest beat 0.5s -> frame 15 at fps 30
    assert snap_to_beat_frame(0.52, beats, 30) == 15
    assert isinstance(snap_to_beat_frame(0.52, beats, 30), int)


def test_synth_beat_grid_even_spacing():
    grid = synth_beat_grid(120, 4)  # 0.5s per beat
    assert grid == [0.0, 0.5, 1.0, 1.5]


def test_atempo_chain_decomposition():
    assert atempo_chain(1.6) == [1.6]
    assert atempo_chain(3.2) == [2.0, 1.6]
    # slow-down below 0.5 chains too
    assert atempo_chain(0.25) == [0.5, 0.5]


def test_ramp_setpts_factor():
    assert ramp_setpts_factor(1.6) == pytest.approx(0.625)


def test_fit_pacing_enforces_sub_2500_average():
    beats = synth_beat_grid(120, 40)  # dense grid
    # deliberately-too-long slots
    frames = fit_pacing(4, [4000, 4000, 4000, 4000], beats, 2500, 30)
    durs = []
    prev = 0
    for f in frames:
        durs.append((f - prev) * 1000 / 30)
        prev = f
    assert sum(durs) / len(durs) < 2500
    assert all(b > a for a, b in zip([0, *frames], frames))  # strictly increasing


def test_build_edl_hook_first_and_pacing():
    scenes = [_scene(0), _scene(1, hook=True), _scene(2, payoff=True), _scene(3, no_crop=True, kind="broll")]
    pacing = PacingSpec(id="p", shot_count=4, per_shot_ms=[1500, 1500, 1500, 1500],
                        bpm_hint=120, max_avg_cut_ms=2500, ramp_factor=1.6)
    job = JobSpec(id="job1", scenes=scenes, pacing=pacing, vo_path="/vo.wav", music_path=None)
    edl = build_edl(job)
    assert edl.shot_count == 4
    assert edl.shots[0].is_hook is True                 # T-2: hook is shot 0
    assert edl.avg_cut_ms() < 2500                       # T-2: sub-2.5s average
    # payoff shot carries a ramp; blurred_pad for the no_crop packshot
    payoff = next(s for s in edl.shots if s.scene_id == "s2")
    assert payoff.ramp_factor == pytest.approx(1.6)
    packshot = next(s for s in edl.shots if s.scene_id == "s3")
    assert packshot.normalize == "blurred_pad"
    # frame boundaries are contiguous (hard cuts, no gaps)
    for a, b in zip(edl.shots, edl.shots[1:]):
        assert a.end_frame == b.start_frame


def test_build_edl_no_music_uses_bpm_hint_grid():
    scenes = [_scene(0, hook=True), _scene(1)]
    pacing = PacingSpec(id="p", shot_count=2, per_shot_ms=[2000, 2000], bpm_hint=100)
    job = JobSpec(id="j", scenes=scenes, pacing=pacing, vo_path="/vo.wav", music_path=None)
    edl = build_edl(job)
    assert edl.bpm == 100.0
    assert len(edl.beat_times) > 0
    assert not any(math.isnan(t) for t in edl.beat_times)
