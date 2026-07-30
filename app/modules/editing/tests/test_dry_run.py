"""DRY_RUN render-path tests: produce placeholder outputs with no heavy ffmpeg."""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.modules.editing.render import write_placeholder_mp4
from app.modules.editing.types import JobSpec, PacingSpec, SceneSpec
from app.modules.editing.worker import run_edit


def _job():
    scenes = [
        SceneSpec("h", 0, "avatar", True, False, "missing://h", 0, 2000),
        SceneSpec("p", 1, "broll", False, False, "missing://p", 2000, 3800, no_crop=True),
        SceneSpec("r", 2, "avatar", False, True, "missing://r", 3800, 6200),
    ]
    pacing = PacingSpec("pace", 3, [2000, 1800, 2400], bpm_hint=120, ramp_factor=1.6)
    return JobSpec("dryjob", scenes, pacing, vo_path="missing://vo", music_path=None)


def test_write_placeholder_mp4_is_deterministic_and_valid(tmp_path):
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    write_placeholder_mp4(str(a))
    write_placeholder_mp4(str(b))
    da, dbytes = a.read_bytes(), b.read_bytes()
    assert da == dbytes                       # deterministic (T-9 friendly)
    assert da[4:8] == b"ftyp"                 # structurally an MP4
    assert 0 < len(da) < 2048                 # tiny placeholder


def test_run_edit_dry_run_produces_both_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    outputs = run_edit(_job(), "dryjob", dry_run=True)

    for p in (outputs.final_mp4, outputs.final_captioned_mp4):
        assert Path(p).exists()
        assert Path(p).read_bytes()[4:8] == b"ftyp"

    # artifacts retained for deterministic re-render (§4D.2)
    assert Path(outputs.ass_path).exists()
    assert Path(outputs.edl_path).exists()
    assert Path(outputs.manifest_path).exists()
    # disclosure baked into base (in_base default) -> separate disclosure.ass exists
    assert outputs.disclosure_ass_path and Path(outputs.disclosure_ass_path).exists()

    # acceptance-lite (T-2)
    assert outputs.shot_count == 3
    assert outputs.avg_cut_ms < 2500


def test_run_edit_outputs_under_job_output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    outputs = run_edit(_job(), "dryjob2", dry_run=True)
    assert outputs.final_mp4.endswith("jobs/dryjob2/output/final.mp4")
    assert outputs.final_captioned_mp4.endswith("jobs/dryjob2/output/final_captioned.mp4")
