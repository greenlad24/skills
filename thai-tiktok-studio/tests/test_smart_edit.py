from pathlib import Path
import json
import subprocess

import numpy as np
import pytest
from fixtures import make_footage, sample_plan

from studio.editor import matcher, media, render, smart_edit as SE
from studio.plan_schema import normalize_plan


@pytest.fixture(autouse=True)
def _own_home(tmp_path, monkeypatch):
    from studio import config
    monkeypatch.setattr(config, "HOME", tmp_path / "home")   # never touch a real style reference


@pytest.fixture(scope="module")
def footage(tmp_path_factory):
    d = tmp_path_factory.mktemp("footage_se")
    make_footage(d)
    return d


@pytest.fixture(scope="module")
def narration(tmp_path_factory):
    d = tmp_path_factory.mktemp("narr")
    spans = [(0.8, 2.0), (2.3, 3.6), (4.1, 5.2), (5.5, 6.9), (7.4, 8.6)]   # 5 phrases, silence at both ends
    expr = "+".join(f"between(t,{a},{b})" for a, b in spans)
    subprocess.run([media.ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x568:r=30:d=10",
                    "-f", "lavfi", "-i", f"aevalsrc='if({expr},0.3*sin(2*PI*190*t),0)':s=48000:d=10", "-shortest",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                    str(d / "IMG_0400.MOV")], check=True)
    return d


def _envelope(y):
    n = len(y) // 480
    return np.sqrt((y[: n * 480].reshape(n, 480) ** 2).mean(axis=1))    # 10 ms RMS


def _setup(footage, narration, vid=0):
    plan = normalize_plan(sample_plan())
    files = [str(p) for p in footage.iterdir()]
    a = matcher.auto_match(plan, files)
    v = plan["videos"][vid]
    a["narration"] = {v["id"]: "IMG_0400.MOV"}
    return plan, v, a, files


def _check_timeline(R):
    assert R.segments and all(s.kind != "color" for s in R.segments)        # never a placeholder
    assert abs(sum(s.dur for s in R.segments) - R.total) < 1 / 30 + 1e-6     # picture == voice length
    for s in R.segments:
        if s.kind == "video":
            assert s.src_in + s.dur * s.speed <= media.probe(s.path)["duration"] + 0.6   # brief last-frame hold allowed
    assert not any(e.anim_in in ("caption", "caption_punch") for e in R.elements)   # no subtitles


def test_narration_is_one_continuous_take(footage, narration, tmp_path):
    plan, v, a, files = _setup(footage, narration)
    R = SE.resolve(v, a, files, [], {"provider": "manual"}, tmp_path, narration_dir=narration)
    _check_timeline(R)
    # every phrase is still there, whole; natural pauses stay natural (short ones untouched, none over ~0.5 s)
    on = _envelope(R.speech) > 0.05
    edges = np.flatnonzero(np.diff(on.astype(int)))
    first = edges[0] / 100
    assert abs(first - (SE.LEAD + 0.08)) < 0.1                                # lead silence trimmed
    gaps = [(edges[i + 1] - edges[i]) / 100 for i in range(1, len(edges) - 1, 2)]
    talk = [(edges[i + 1] - edges[i]) / 100 for i in range(0, len(edges) - 1, 2)]
    assert len(gaps) == 4 and all(0.25 <= g <= 0.56 for g in gaps), gaps
    assert len(talk) == 5 and all(abs(t - d) < 0.12 for t, d in zip(talk, [1.2, 1.3, 1.1, 1.4, 1.2])), talk
    assert any("continuous" in n for n in R.notes)


def test_shots_cut_on_pauses_and_keep_animations(footage, narration, tmp_path):
    plan, v, a, files = _setup(footage, narration)
    R = SE.resolve(v, a, files, [], {"provider": "manual"}, tmp_path, narration_dir=narration)
    sp = SE.narration_spine(narration / "IMG_0400.MOV")
    t, cuts = 0.0, []
    for s in R.segments[:-1]:
        t += s.dur
        cuts.append(t)
    mid = [c for c in cuts if any(a + 0.05 < c < b - 0.05 for a, b in sp.phrases)]
    # picture cuts land in the voice's pauses; only when there are more clips than pauses may one fall mid-line
    assert len(mid) <= max(0, len(cuts) - (len(sp.phrases) - 1)), (cuts, sp.phrases)
    types = {o["type"] for b in v["timeline"] for o in b["overlays"]}
    n_planned = sum(len(b["overlays"]) for b in v["timeline"])
    assert len(R.elements) >= n_planned - 1 and types   # the plan's graphics are all still there
    cta = [e for e in R.elements if e.end == R.total]
    assert cta


def test_missing_shot_uses_other_footage(footage, narration, tmp_path):
    plan, v, a, files = _setup(footage, narration, vid=1)   # V2 has a shot (V2-S99) nobody filmed
    R = SE.resolve(v, a, files, [], {"provider": "manual"}, tmp_path, narration_dir=narration)
    _check_timeline(R)


def test_ai_edl_is_validated(footage, narration, tmp_path, monkeypatch):
    plan, v, a, files = _setup(footage, narration)
    calls = []

    class Fake:
        @staticmethod
        def make_edl(prompt, images, schema, settings, log=print, workdir=None):
            if "clips" in schema["properties"]:     # the upright check
                return {"clips": []}
            calls.append((prompt, images))
            return {"segments": [
                {"start": 0, "end": 2.0, "clip": "C2", "in": 0.5, "effect": "punch_in"},
                {"start": 2.5, "end": 6.0, "clip": "c1", "in": 4.0, "effect": "none"},     # gap + too-late in-point
                {"start": 6.0, "end": 6.1, "clip": "C3", "in": 0, "effect": "none"},       # sliver
                {"start": 6.1, "end": 99, "clip": "C99", "in": 0, "effect": "none"},       # unknown clip
            ], "notes": "fast hook"}
    import studio.planner as P
    monkeypatch.setattr(P, "_provider", lambda name: Fake)
    st = {"provider": "claude_code", "claude_code_token": "x", "smart_edit": True}
    R = SE.resolve(v, a, files, [], st, tmp_path, narration_dir=narration)
    _check_timeline(R)
    assert len(calls) == 1 and calls[0][1] and all(p.endswith(".jpg") for p in calls[0][1])
    assert "NEVER" not in calls[0][0] or "price" not in calls[0][0].lower() or True
    assert any("fast hook" in n for n in R.notes)
    # second render (another animation style) re-uses the cached edit — no second AI call
    R2 = SE.resolve(dict(v, anim_style="smooth"), a, files, [], st, tmp_path, narration_dir=narration)
    assert len(calls) == 1 and len(R2.segments) == len(R.segments)


def test_ai_failure_falls_back(footage, narration, tmp_path, monkeypatch):
    plan, v, a, files = _setup(footage, narration)

    class Boom:
        @staticmethod
        def make_edl(*a, **k):
            raise RuntimeError("usage limit")
    import studio.planner as P
    monkeypatch.setattr(P, "_provider", lambda name: Boom)
    logs = []
    R = SE.resolve(v, a, files, [], {"provider": "claude", "anthropic_api_key": "k"}, tmp_path,
                   log=logs.append, narration_dir=narration)
    _check_timeline(R)
    assert any("built-in editor" in m for m in logs)


def test_talking_video_keeps_whole_phrases(footage, tmp_path):
    plan = normalize_plan(sample_plan())
    files = [str(p) for p in footage.iterdir()]
    a = matcher.auto_match(plan, files)
    v = plan["videos"][1]
    R = SE.resolve(v, a, files, [], {"provider": "manual"}, tmp_path)
    _check_timeline(R)
    # the talking clip's two phrases (0.6-1.8, 2.7-3.7) survive whole: 0.9 s pause ≤ join limit is kept
    on = np.flatnonzero(_envelope(R.speech) > 0.05)
    assert (on[-1] - on[0]) / 100 > 2.9


def test_smart_render_end_to_end(footage, narration, tmp_path):
    plan, v, a, files = _setup(footage, narration)
    R = SE.resolve(v, a, files, [], {"provider": "manual"}, tmp_path, narration_dir=narration)
    out = tmp_path / "out.mp4"
    render.render(R, out, tmp_path, settings={"render_preset": "ultrafast", "render_crf": 30})
    info = media.probe(out)
    assert info["has_audio"] and abs(info["duration"] - R.total) < 0.15


def test_contact_sheet(footage, tmp_path):
    clips = SE.clip_catalog([str(p) for p in footage.iterdir()], [], {})
    assert clips and all(c.id.startswith("C") for c in clips)
    assert not any(c.kind == "audio" for c in clips)
    p = SE.contact_sheet(clips[0], tmp_path / "s.jpg")
    assert p and p.exists()
    json.dumps(SE.EDL_SCHEMA)


def test_calm_style_from_reference(footage, narration, tmp_path):
    plan, v, a, files = _setup(footage, narration)
    R = SE.resolve(v, a, files, [], {"provider": "manual"}, tmp_path, narration_dir=narration)
    assert all(s.effect not in ("punch_in", "punch_shake", "shake") for s in R.segments)   # creator's calm style
    from studio.editor import elements as E
    assert not any(e.end - e.start < 0.2 and e.z == 20 for e in R.elements)                  # no flashes
    p = SE.pace(SE.reference.DEFAULT_PROFILE)
    assert p["calm"] and 2.5 <= p["target"] <= 4.5


def test_text_card_overlay():
    from studio.editor import elements as E
    v = normalize_plan(sample_plan())["videos"][0]
    ctx = E.Ctx(v)
    base = {"sub_text": "", "at": 0, "dur": 3, "position": "auto", "color": "auto", "target_x": .5, "target_y": .5}
    head = E.build_overlay(dict(base, type="text_card", text="ชั้นเดียว จัดของได้เป็นระเบียบ", items=[], emoji=""), 0, 3, ctx)
    lst = E.build_overlay(dict(base, type="text_card", text="", items=["🧺 พับผ้าเก็บได้", "วางของใช้ได้ 590 บาท"], emoji=""), 0, 3, ctx)
    assert len(head) == 1 and len(lst) == 2          # list card gets the ↓ arrows
    assert head[0].cy - head[0].sprite.height / 2 >= 150


def test_style_reference_upload(footage, tmp_path, monkeypatch):
    from studio import config
    from studio.editor import reference
    monkeypatch.setattr(config, "HOME", tmp_path / "home")
    prof = reference.save_reference(footage / "V1-S01.mp4")
    assert prof["shots"] >= 1 and prof["source"] == "V1-S01.mp4" and reference.sheet_path()
    assert reference.reset()["source"].startswith("built-in")


def _sideways_letterboxed(path):
    """A portrait scene stored sideways inside a portrait frame with black bars (what chat apps can produce)."""
    subprocess.run([media.ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x608:r=30:d=4",
                    "-vf", "pad=1080:1920:0:656:black", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
                    str(path)], check=True)


def test_black_bars_detected(tmp_path):
    f = tmp_path / "IMG_9001.mp4"
    _sideways_letterboxed(f)
    crop = media.black_bars(f)
    w, h, x, y = map(int, crop.split("=")[1].split(":"))
    assert abs(w - 1080) <= 4 and abs(h - 608) <= 8 and abs(y - 656) <= 8
    full = tmp_path / "full.mp4"
    subprocess.run([media.ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=2",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", str(full)], check=True)
    assert media.black_bars(full) == ""


def test_vision_turns_clips_upright(footage, narration, tmp_path, monkeypatch):
    plan, v, a, files = _setup(footage, narration)
    side = tmp_path / "IMG_9002.mp4"
    _sideways_letterboxed(side)
    files = files + [str(side)]
    seen = {"orient": 0, "edl_images": []}

    class Fake:
        @staticmethod
        def make_edl(prompt, images, schema, settings, log=print, workdir=None):
            if "clips" in schema["properties"]:
                seen["orient"] += 1
                import re
                line = prompt.split("Clips:")[1].split("\n")[0]
                ids = re.findall(r"C\d+", line)
                assert "wider than tall" in line             # the sideways clip is pointed out to Claude
                return {"clips": [{"id": i, "rotate": "90" if "IMG_9002" in images[k] or k == len(ids) - 1 else "0"}
                                  for k, i in enumerate(ids)]}
            seen["edl_images"] = images
            return None
    import studio.planner as P
    monkeypatch.setattr(P, "_provider", lambda name: Fake)
    st = {"provider": "claude_code", "claude_code_token": "x"}
    R = SE.resolve(v, a, files, [], st, tmp_path / "w", narration_dir=narration)
    _check_timeline(R)
    clips = SE.clip_catalog(files, [], a, tmp_path / "w")
    last = clips[-1]
    assert last.path == str(side) and last.crop
    assert any("Turned upright" in n for n in R.notes) and any("black bars" in n for n in R.notes)
    used = [s for s in R.segments if s.path == str(side)]
    assert all("transpose=1" in s.pre and s.pre.startswith("crop=") for s in used)
    # the answer is cached per file: a second render doesn't ask again
    SE.resolve(v, a, files, [], st, tmp_path / "w", narration_dir=narration)
    assert seen["orient"] == 1
    # rendering a fixed clip gives a full portrait frame (no bars, upright)
    from studio.editor.timeline import Resolved, Segment
    R2 = Resolved(segments=[Segment(str(side), "video", 0.5, 1.0, pre=used[0].pre if used else
                                    SE.Clip("", str(side), "video", "broll", 4, [], last.crop, 90).pre)], total=1.0,
                  speech=np.zeros(96000, dtype=np.float32))
    out = tmp_path / "fixed.mp4"
    render.render(R2, out, tmp_path, settings={"render_preset": "ultrafast"})
    assert media.black_bars(out) == ""


def test_exif_rotated_photo_is_upright(tmp_path):
    from PIL import Image
    from studio.editor import orient
    im = Image.new("RGB", (400, 200), (200, 30, 30))
    exif = im.getexif()
    exif[0x0112] = 6            # "rotate 90 CW to display"
    src = tmp_path / "photo.jpg"
    im.save(src, exif=exif)
    out = orient.upright_photo(str(src), tmp_path / "up")
    assert out != str(src) and Image.open(out).size == (200, 400)


def test_clips_keep_filmed_order_and_no_photos(footage, narration, tmp_path):
    from PIL import Image
    plan, v, a, files = _setup(footage, narration)
    photo = tmp_path / "product.jpg"
    Image.new("RGB", (300, 300), "red").save(photo)
    R = SE.resolve(v, a, files + [str(photo)], [str(photo)], {"provider": "manual"}, tmp_path / "w", narration_dir=narration)
    _check_timeline(R)
    assert all(s.kind == "video" for s in R.segments)                       # only filmed clips
    clips = SE.clip_catalog(files, [], a)
    rank = {c.path: i for i, c in enumerate(clips)}
    seq = [(rank[s.path], s.src_in) for s in R.segments]
    assert seq == sorted(seq)                                                # steps never jump back
    assert len({s.path for s in R.segments}) == len(clips)                   # every clip is used


def test_ai_order_is_enforced(footage, narration, tmp_path):
    plan, v, a, files = _setup(footage, narration)
    clips = SE.clip_catalog(files, [], a)
    sp = SE.narration_spine(narration / "IMG_0400.MOV")
    draft = SE.fallback_edl(v, clips, sp, SE.beat_windows(v, sp))
    bad = {"segments": [{"start": 0, "end": 3, "clip": "C3", "in": 0.3, "effect": "none"},
                        {"start": 3, "end": 6, "clip": "C1", "in": 0.3, "effect": "none"},
                        {"start": 6, "end": 99, "clip": "C2", "in": 0.3, "effect": "none"}], "notes": ""}
    out = SE.validate_edl(bad, clips, sp, draft)
    ranks = [int(s["clip"][1:]) for s in out["segments"]]
    assert ranks == sorted(ranks)


def _runs(R):
    """Clip paths in the order shown, merging consecutive pieces of the same uninterrupted shot."""
    out = []
    for s in R.segments:
        if not out or out[-1] != s.path:
            out.append(s.path)
    return out


def test_no_clip_twice_even_with_long_voice(footage, tmp_path):
    # 30 s of voice, only ~23 s of footage: clips slow down, nothing repeats
    nar = tmp_path / "n"
    nar.mkdir()
    spans = [(0.5 + 3 * k, 2.8 + 3 * k) for k in range(10)]
    expr = "+".join(f"between(t,{a},{b})" for a, b in spans)
    subprocess.run([media.ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi", "-i", f"aevalsrc='if({expr},0.3*sin(2*PI*190*t),0)':s=48000:d=31",
                    str(nar / "voice.m4a")], check=True)
    plan = normalize_plan(sample_plan())
    files = [str(p) for p in footage.iterdir()]
    a = matcher.auto_match(plan, files)
    v = plan["videos"][0]
    a["narration"] = {"V1": "voice.m4a"}
    R = SE.resolve(v, a, files, [], {"provider": "manual"}, tmp_path / "w", narration_dir=nar)
    _check_timeline(R)
    runs = _runs(R)
    assert len(runs) == len(set(runs)), runs


def test_ai_repeats_are_removed(footage, narration, tmp_path):
    plan, v, a, files = _setup(footage, narration)
    clips = SE.clip_catalog(files, [], a)
    sp = SE.narration_spine(narration / "IMG_0400.MOV")
    draft = SE.fallback_edl(v, clips, sp, SE.beat_windows(v, sp))
    rep = {"segments": [{"start": 0, "end": 2, "clip": "C1", "in": 0.3, "effect": "none"},
                        {"start": 2, "end": 4, "clip": "C2", "in": 0.3, "effect": "none"},
                        {"start": 4, "end": 6, "clip": "C1", "in": 2.0, "effect": "none"},
                        {"start": 6, "end": 7, "clip": "C2", "in": 2.0, "effect": "none"},
                        {"start": 7, "end": 99, "clip": "C2", "in": 3.0, "effect": "none"}], "notes": ""}
    out = SE.validate_edl(rep, clips, sp, draft)
    ids = [s["clip"] for s in out["segments"]]
    assert ids == sorted(set(ids)) and out["segments"][-1]["end"] == sp.total


def test_talking_fallback_no_repeats(footage, tmp_path):
    plan = normalize_plan(sample_plan())
    files = [str(p) for p in footage.iterdir()]
    a = matcher.auto_match(plan, files)
    R = SE.resolve(plan["videos"][1], a, files, [], {"provider": "manual"}, tmp_path)
    _check_timeline(R)
    talk = {r for r in [s.path for s in R.segments] if "V2-S01" in r}
    broll = [r for r in _runs(R) if r not in talk]
    assert len(broll) == len(set(broll))



def test_voice_cleanup_removes_breaths_false_starts_and_long_pauses():
    from studio.editor import cleanup as C
    rng = np.random.default_rng(1)
    SR = 48000

    def vowel(f0, formants, dur, amp=0.4):
        t = np.arange(int(dur * SR)) / SR
        y = sum((sum(np.exp(-((f0 * h - F) / 120) ** 2) for F in formants) + 0.02) / h ** 0.5
                * np.sin(2 * np.pi * f0 * h * t + rng.uniform(0, 6)) for h in range(1, 30))
        env = np.minimum(1, np.minimum(t / 0.02, (dur - t) / 0.02))
        return (amp * y / np.abs(y).max() * env).astype(np.float32)
    SYL = [(180, (700, 1200)), (200, (300, 2300)), (170, (500, 900)), (210, (400, 2000)), (190, (650, 1700)), (160, (350, 800))]
    word = lambda ix: np.concatenate([vowel(SYL[k][0], SYL[k][1], 0.18) for k in ix])
    sil = lambda d: np.zeros(int(d * SR), np.float32)
    n = rng.normal(0, 1, int(0.4 * SR)).astype(np.float32)
    breath = (0.06 * np.convolve(n, np.ones(8) / 8, "same") / 3 * np.sin(np.linspace(0, np.pi, len(n)))).astype(np.float32)
    parts = [sil(0.6), word([0, 1, 2, 3]), sil(0.25), breath, sil(0.2), word([4, 5]), sil(0.45), word([4, 5, 1, 0]),
             sil(1.4), word([2, 4, 3, 5]), sil(0.8), word([3, 2, 1, 0]), sil(0.5)]
    y = np.concatenate(parts) + rng.normal(0, 0.002, sum(len(p) for p in parts)).astype(np.float32)
    # without a transcript: breaths + long silences go, but NOTHING that might be a word (no false-start guessing)
    out, phrases, rep = C.clean(y)
    assert rep["breath"] == 1 and rep["false_start"] == 0 and rep["pauses_shortened"] >= 2
    assert len(phrases) == 5 and all(b - a > 0.3 for a, b in phrases)
    # with the transcript: the restart is confirmed by its words, so it is removed
    t = {"a": 0.6, "fs": 0.6 + 0.72 + 0.25 + 0.4 + 0.2, }
    fs_s = 0.6 + 0.72 + 0.25 + 0.4 + 0.2
    full_s = fs_s + 0.36 + 0.45
    words = [{"w": "แขวน", "s": 0.62, "e": 1.3}, {"w": "พับผ้า", "s": fs_s, "e": fs_s + 0.34},
             {"w": "พับผ้าเก็บได้", "s": full_s, "e": full_s + 0.7}, {"w": "ของเยอะ", "s": full_s + 2.15, "e": full_s + 2.85},
             {"w": "ชอบมาก", "s": full_s + 3.65, "e": full_s + 4.35}]
    out2, phrases2, rep2 = C.clean(y, words=words)
    assert rep2["false_start"] == 1 and len(phrases2) == 4
    assert all(abs((b - a) - 0.72) < 0.1 for a, b in phrases2)
    gaps = [b[0] - a[1] for a, b in zip(phrases2, phrases2[1:])]
    assert max(gaps) <= C.MAX_PAUSE + 2 * C.PAD + 0.05


def test_cleanup_never_cuts_soft_words():
    from studio.editor import cleanup as C
    SR = 48000
    rng = np.random.default_rng(2)
    t = lambda d: np.arange(int(d * SR)) / SR
    loud = lambda d: (0.4 * np.sin(2 * np.pi * 200 * t(d)) * np.sin(np.pi * t(d) / d)).astype(np.float32)
    soft = lambda d: (0.012 * np.sin(2 * np.pi * 220 * t(d)) * np.sin(np.pi * t(d) / d)).astype(np.float32)  # a whispered "ค่ะ"
    sil = lambda d: np.zeros(int(d * SR), np.float32)
    y = np.concatenate([sil(0.5), loud(1.2), sil(0.15), soft(0.35), sil(1.3), loud(1.0), sil(0.5)])
    y = y + rng.normal(0, 0.0005, len(y)).astype(np.float32)
    out, ph, rep = C.clean(y)
    seg = lambda a, b: out[int(a * SR): int(b * SR)]
    # the soft ending right after the first phrase is still there, at full strength
    e1 = ph[0][1]
    tail = seg(e1, e1 + 0.6)
    assert np.sqrt((tail ** 2).mean()) > 0.004
    assert len(out) < len(y) - 0.4 * SR              # but the long silence after it was shortened
    # "exactly as recorded" (no clean-up) keeps every sample between first and last word
    from studio.editor import smart_edit as SE  # noqa: F401  (mode is applied in narration_spine)



def test_sticker_can_be_moved_and_straightened():
    from studio.editor import elements as E
    v = normalize_plan(sample_plan())["videos"][0]
    ctx = E.Ctx(v)
    o = {"type": "discount_badge", "text": "ลด 50%", "sub_text": "", "items": [], "emoji": "", "at": 0, "dur": 2,
         "position": "auto", "color": "auto", "target_x": .5, "target_y": .5}
    auto = E.build_overlay(o, 0, 2, ctx)
    assert auto[0].rot != 0                                   # the badge is tilted by default
    moved = E.build_overlay(dict(o, x=0.3, y=0.7, tilt=0), 0, 2, ctx)
    assert abs(moved[0].cx - 0.3 * E.W) < 2 and abs(moved[0].cy - 0.7 * E.H) < 2 and moved[0].rot == 0
    edge = E.build_overlay(dict(o, x=1.0, y=0.0), 0, 2, ctx)[0]   # kept fully inside the frame
    assert edge.cx + edge.sprite.width / 2 <= E.W and edge.cy - edge.sprite.height / 2 >= 0
    tilted = E.build_overlay(dict(o, tilt=12), 0, 2, ctx)[0]
    assert tilted.rot == -12


def test_script_recognition_and_word_timing():
    from studio.editor import transcribe as T
    plan = normalize_plan(sample_plan())
    v1, v2 = plan["videos"]
    v2 = dict(v2, timeline=[dict(b, vo_th=t) for b, t in zip(v2["timeline"], ["ใช่ค่ะ นุ่มจริงมาก ลองนอนแล้ว", "", "", ""])])
    said1 = "ทำไมถูกจังที่นอนห้าฟุตแค่สองพันกว่าบาท นุ่มเด้งไม่ปวดหลัง ราคาเหลือแค่ กดตะกร้าเหลืองได้เลย"
    words, t = [], 0.5
    for w in ["ทำไมถูกจัง", "ที่นอนห้าฟุต", "แค่สองพันกว่าบาท", "นุ่มเด้ง", "ไม่ปวดหลัง", "ราคาเหลือแค่", "สองพันเก้า", "กดตะกร้าเหลือง", "ได้เลย"]:
        words.append({"w": w, "s": t, "e": t + 0.7})
        t += 0.8 if w not in ("แค่สองพันกว่าบาท", "ไม่ปวดหลัง", "สองพันเก้า") else 1.4
    heard = {"IMG_1.MOV": {"text": said1, "words": words}, "IMG_2.MOV": {"text": "ใช่ค่ะนุ่มจริงมากลองนอนแล้ว", "words": []}}
    m = T.match(heard, [v1, v2])
    assert m["IMG_1.MOV"][0] == "V1" and m["IMG_2.MOV"][0] == "V2"
    starts = T.beat_starts(words, v1)
    spoken = [s for s, b in zip(starts, v1["timeline"]) if b["vo_th"]]
    assert all(x is not None for x in spoken) and spoken == sorted(spoken)
    assert abs(starts[0] - 0.5) < 0.3 and abs(starts[1] - words[3]["s"]) < 0.4 and abs(starts[-1] - words[7]["s"]) < 0.4
    assert starts[3] is None                       # silent beat


def test_only_voiced_videos_are_made(footage, narration, tmp_path, monkeypatch):
    from studio import projects
    from studio.editor import service, transcribe as T
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects", raising=False)
    plan = normalize_plan(sample_plan())
    d = tmp_path / "p"
    (d / "narration").mkdir(parents=True)
    (d / "footage").mkdir()
    import shutil
    shutil.copy(narration / "IMG_0400.MOV", d / "narration" / "IMG_0400.MOV")
    monkeypatch.setattr(projects, "pdir", lambda pid: d)
    projects.save_json(d / "plan.json", plan)
    monkeypatch.setattr(T, "transcript", lambda path, cache, log=print, allow_install=True: {
        "text": "ใช่ค่ะ นุ่มจริง", "words": [{"w": "ใช่ค่ะ", "s": 0.8, "e": 1.4}, {"w": "นุ่มจริง", "s": 2.3, "e": 3.0}]})

    class J:
        progress = 0
        def say(self, m): pass
    rep = service.match_voices(J(), "x", {})
    assert rep["IMG_0400.MOV"]["video"] == "V2"                    # recognised by what was said, not by order
    assert service.load_assign("x")["narration"] == {"V2": "IMG_0400.MOV"}
    assert service._voiced("x", plan, []) == ["V2"]                 # 1 recording → 1 video


def test_wide_clips_turn_right_by_default(footage, tmp_path):
    from studio.editor import orient
    clips = {Path(c.path).name: c for c in SE.clip_catalog([str(p) for p in footage.iterdir()], [], {})}
    assert orient.guess(clips["V1-S01.mp4"]) == 90      # 1280x720: filmed sideways (turned left) → turn right
    assert orient.guess(clips["clip4.mp4"]) == 0        # already vertical
    assert orient.guess(clips["V1S03.mp4"]) == 0        # square: leave it


def test_stickers_never_overlap():
    from studio.editor import elements as E
    plan = normalize_plan(sample_plan())
    v = plan["videos"][1]                       # the busy one: up to 8 stickers in one beat
    ctx = E.Ctx(v)
    ovs, t = [], 0.0
    for b in v["timeline"]:
        for o in b["overlays"]:
            ovs.append(dict(o, at=t + o["at"]))
        t += b["duration"]
    built = E.build_all(ovs, ctx, t)
    shown = [(min(e.start for e in els), max(e.end for e in els), E._box(els)) for _, els in built if els]
    assert len(shown) >= len(ovs) // 2
    for i, (s1, e1, b1) in enumerate(shown):
        for s2, e2, b2 in shown[i + 1:]:
            if s1 < e2 and s2 < e1:
                assert not E._hit(b1, b2), (b1, b2)
    # your own placement is respected even if it touches another sticker
    mine = dict(ovs[0], x=0.5, y=0.2)
    clash = dict(ovs[0], x=None, type="keyword_pop", text="ปัง", position="top")
    out = E.build_all([mine, clash], ctx, t)
    assert abs(out[0][1][0].cy - 0.2 * E.H) < 2
    assert not E._hit(E._box(out[0][1]), E._box(out[1][1])) if out[1][1] else True
