import subprocess
from pathlib import Path

import numpy as np
import pytest
from fixtures import make_footage, sample_plan

from studio.editor import elements as E, matcher, media, render, sfx, text as T, timeline
from studio.plan_schema import OVERLAY_TYPES, normalize_plan


@pytest.fixture(scope="module")
def footage(tmp_path_factory):
    d = tmp_path_factory.mktemp("footage")
    make_footage(d)
    return d


def test_every_overlay_type_has_a_builder():
    assert set(OVERLAY_TYPES) == set(E.BUILDERS)


def test_every_overlay_builds_sprites():
    plan = normalize_plan(sample_plan())
    ctx = E.Ctx(plan["videos"][0])
    for t in OVERLAY_TYPES:
        o = {"type": t, "text": "ทดสอบ 199", "sub_text": "590", "items": ["นุ่ม", "ส่งฟรี"], "emoji": "🔥",
             "at": 0, "dur": 2, "position": "auto", "color": "auto", "target_x": 0.5, "target_y": 0.5}
        els = E.build_overlay(o, 0, 2, ctx)
        if t == "emoji_sticker" and T.emoji_sprite("🔥", 50) is None:
            continue  # no colour-emoji font on this machine
        assert els, t
        for el in els:
            img = el.draw(0.5) if el.draw else el.sprite
            assert img.width > 1 and img.height > 1


def test_thai_highlight_never_orphans_marks():
    runs = T.safe_splits("ที่นอนนุ่มเด้ง", ["นุ่ม"])
    assert "".join(r[0] for r in runs) == "ที่นอนนุ่มเด้ง"
    for chunk, _ in runs:
        assert ord(chunk[0]) not in T.COMBINING


def test_matcher_by_name_then_order(footage):
    plan = normalize_plan(sample_plan())
    a = matcher.auto_match(plan, [str(p) for p in footage.iterdir()])
    assert a["shots"]["V1-S01"] == "V1-S01.mp4"
    assert a["shots"]["V1-S02"] == "v1_s2.mov"
    assert a["shots"]["V1-S03"] == "V1S03.mp4"
    assert "music_track.mp3" in a["music"]
    assert matcher.vo_video_from_name("V2-VO.m4a") == "V2"


def test_probe_and_speech_islands(footage):
    info = media.probe(footage / "V2-S01.mp4")
    assert info["has_audio"] and abs(info["duration"] - 4.5) < 0.2 and info["width"] == 1080
    isl = media.speech_islands(footage / "V2-S01.mp4")
    assert len(isl) == 2
    assert abs(isl[0][0] - 0.6) < 0.15 and abs(isl[1][1] - 3.7) < 0.15


def test_timeline_resolution(footage, tmp_path):
    plan = normalize_plan(sample_plan())
    a = matcher.auto_match(plan, [str(p) for p in footage.iterdir() if p.name != "product_1.jpg"])
    v1, v2 = plan["videos"]
    R = timeline.resolve(v1, a, footage, [], {}, tmp_path)
    assert len(R.segments) == 5 and not R.missing
    assert R.total == pytest.approx(sum(s.dur for s in R.segments), abs=0.05)
    assert any(e.anim_in == "caption" for e in R.elements)
    assert R.progress_color is not None
    R2 = timeline.resolve(v2, a, footage, [str(footage / "product_1.jpg")], {}, tmp_path)
    talking = [s for s in R2.segments if s.use_audio]
    # V2-S01 is used by 2 beats (beat 4's unknown shot falls back to it); each use is
    # split into 2 jump-cut pieces with the pauses removed.
    assert len(talking) == 4
    assert sum(s.dur for s in talking[:2]) < 3.0  # 4.5s clip minus silences
    assert any(s.kind == "image" for s in R2.segments)  # product_photo shot uses the product image
    assert "V2-S02" in R2.missing                 # no file → placeholder card


def test_sfx_bank_is_normalized():
    for name in sfx.BANK:
        y = sfx.get(name)
        assert len(y) > 100 and 0.2 < float(np.max(np.abs(y))) <= 0.56


def test_full_render(footage, tmp_path):
    plan = normalize_plan(sample_plan())
    a = matcher.auto_match(plan, [str(p) for p in footage.iterdir()])
    R = timeline.resolve(plan["videos"][0], a, footage, [], {}, tmp_path)
    out = render.render(R, tmp_path / "v1.mp4", tmp_path, music=footage / "music_track.mp3",
                        settings={"render_preset": "ultrafast", "render_crf": 30})
    info = media.probe(out)
    assert info["width"] == 1080 and info["height"] == 1920 and info["has_audio"]
    assert abs(info["duration"] - R.total) < 0.15
