import subprocess
from pathlib import Path

import numpy as np
import pytest
from fixtures import make_footage, sample_plan

from studio.editor import elements as E, matcher, media, render, text as T, timeline
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
    R = timeline.resolve(v1, a, footage, [], {"subtitles": True}, tmp_path)
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


def test_full_render(footage, tmp_path):
    plan = normalize_plan(sample_plan())
    a = matcher.auto_match(plan, [str(p) for p in footage.iterdir()])
    R = timeline.resolve(plan["videos"][0], a, footage, [], {}, tmp_path)
    out = render.render(R, tmp_path / "v1.mp4", tmp_path, music=footage / "music_track.mp3",
                        settings={"render_preset": "ultrafast", "render_crf": 30})
    info = media.probe(out)
    assert info["width"] == 1080 and info["height"] == 1920 and info["has_audio"]
    assert abs(info["duration"] - R.total) < 0.15


def test_matching_without_special_filenames(tmp_path):
    from fixtures import make_unnamed_footage
    expected = make_unnamed_footage(tmp_path)
    plan = normalize_plan(sample_plan())
    files = [str(p) for p in tmp_path.iterdir()]
    a = matcher.auto_match(plan, files)
    assert a["shots"] == expected["shots"]          # recording order + talk/b-roll/photo types
    assert a["vo"] == expected["vo"]                # speech-with-pauses → voice-over
    assert a["music"] == expected["music"]          # continuous → music
    assert a["unmatched"] == expected["unmatched"]  # earlier retake skipped, nothing shifted
    # manual choices survive re-matching
    a2 = matcher.auto_match(plan, files, {"shots": {"V1-S01": "IMG_0120.MOV"}, "vo": {}, "music": []})
    assert a2["shots"]["V1-S01"] == "IMG_0120.MOV"


def _take(path, spans, dur):
    expr = "+".join(f"between(t,{a},{b})" for a, b in spans)
    subprocess.run([media.ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"aevalsrc='if({expr},0.4*sin(2*PI*200*t),0)':s=48000:d={dur}", str(path)], check=True)


def test_own_voice_split_into_lines(tmp_path):
    from studio.editor import voice
    # 4 lines; line 2 has a tiny breath inside it; a 1.5 s pause before line 3
    spans = [(0.5, 1.7), (2.2, 3.0), (3.1, 4.0), (5.5, 6.3), (6.9, 8.4)]
    _take(tmp_path / "take.m4a", spans, 9)
    chunks = voice.split_recording(tmp_path / "take.m4a", [12, 17, 8, 15])
    assert chunks and len(chunks) == 4
    lens = [len(c) / 48000 for c in chunks]
    assert abs(lens[0] - 1.32) < 0.2          # 1.2 s speech + edges
    assert 1.6 < lens[1] < 2.2               # the 0.1 s inner breath stays inside line 2
    assert lens[2] < 1.2 and lens[3] < 1.8   # long pauses are not carried into lines


def test_own_voice_drives_beats(footage, tmp_path):
    plan = normalize_plan(sample_plan())
    v1 = plan["videos"][0]                    # voiceover video with 4 spoken beats
    spans = [(0.4, 1.9), (2.4, 3.6), (4.2, 5.3), (6.0, 7.2)]
    _take(footage / "voice_take.m4a", spans, 8)
    a = matcher.auto_match(plan, [str(p) for p in footage.iterdir()])
    assert a["vo"].get("V1") == "voice_take.m4a"
    R = timeline.resolve(v1, a, footage, [], {}, tmp_path)
    assert any("Using your voice-over" in n for n in R.notes)
    # each spoken beat lasts at least as long as its voice line → no drift between voice and picture
    spoken = [i for i, b in enumerate(v1["timeline"]) if b["vo_th"]]
    for i in spoken:
        t0, t1 = R.beats[i]
        assert t1 - t0 >= 0.9
    assert float(np.abs(R.speech).max()) > 0.3
    (footage / "voice_take.m4a").unlink()


def test_narration_video_audio_is_used(footage, tmp_path):
    nar_dir = tmp_path / "narration"
    nar_dir.mkdir()
    expr = "+".join(f"between(t,{a},{b})" for a, b in [(0.3, 1.5), (2.0, 3.2), (3.8, 5.0)])
    subprocess.run([media.ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x568:r=30:d=6",
                    "-f", "lavfi", "-i", f"aevalsrc='if({expr},0.4*sin(2*PI*190*t),0)':s=48000:d=6", "-shortest",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                    str(nar_dir / "IMG_0300.MOV")], check=True)
    plan = normalize_plan(sample_plan())
    a = matcher.auto_match(plan, [str(p) for p in footage.iterdir()])
    a["narration"] = matcher.match_narration(plan, [str(nar_dir / "IMG_0300.MOV")])
    assert a["narration"] == {"V1": "IMG_0300.MOV"}      # voice-over video gets it first
    a["narration"] = {"V2": "IMG_0300.MOV"}              # put it on the talking video instead
    R = timeline.resolve(plan["videos"][1], a, footage, [], {}, tmp_path / "w", narration_dir=nar_dir)
    assert any("Using your voice-over" in n for n in R.notes)
    assert not any(s.use_audio for s in R.segments)      # on-camera sound replaced by narration
    assert float(np.abs(R.speech).max()) > 0.3


def test_style_packs_change_motion():
    from studio.editor import styles
    plan = normalize_plan(sample_plan())
    o = plan["videos"][0]["timeline"][0]["overlays"][0]
    seen = set()
    for st in styles.STYLES:
        ctx = E.Ctx(dict(plan["videos"][0], anim_style=st))
        seen.add(E.build_overlay(o, 0, 2, ctx)[0].anim_in)
        cap = E.caption("ทดสอบ", [], 0, 1, ctx)
        assert cap.anim_in == styles.caption_anim(st)
    assert len(seen) >= 4
    # every new entrance renders mid-animation without errors
    from studio.editor.anim import IN_DUR, render_element
    spr = T.text_block("ทดสอบ")
    for name in IN_DUR:
        el = E.Element(start=0, end=2, cx=500, cy=900, sprite=spr, anim_in=name, in_dur=IN_DUR[name] or 0.1,
                       loop="float", out="pop_out")
        for t in (0.05, 0.2, 1.0, 1.95):
            render_element(el, t)


def test_finished_video_never_carries_a_rotation_tag(tmp_path):
    """ffmpeg 7.1 (Mac) can copy a phone clip's rotation tag into the output → whole video shown sideways."""
    ff = media.ffmpeg_exe()
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=1", "-c:v", "libx264",
                    "-preset", "ultrafast", str(tmp_path / "v.mp4")], check=True)
    subprocess.run([ff, "-v", "error", "-y", "-display_rotation", "90", "-i", str(tmp_path / "v.mp4"), "-c", "copy",
                    str(tmp_path / "tagged.mp4")], check=True)
    f = tmp_path / "tagged.mp4"
    assert render._rotation_tag(f) and media.probe(f)["width"] == 1920
    render._strip_rotation(f)
    assert not render._rotation_tag(f) and (media.probe(f)["width"], media.probe(f)["height"]) == (1080, 1920)
    (tmp_path / "p" / "renders").mkdir(parents=True)
    subprocess.run([ff, "-v", "error", "-y", "-display_rotation", "90", "-i", str(tmp_path / "v.mp4"), "-c", "copy",
                    str(tmp_path / "p" / "renders" / "V1_bouncy_100000.mp4")], check=True)
    assert render.fix_existing(tmp_path) == 1 and not render._rotation_tag(tmp_path / "p" / "renders" / "V1_bouncy_100000.mp4")
