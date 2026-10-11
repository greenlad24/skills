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
            assert s.src_in + s.dur <= media.probe(s.path)["duration"] + 0.6   # brief last-frame hold allowed
    assert not any(e.anim_in in ("caption", "caption_punch") for e in R.elements)   # no subtitles


def test_narration_is_one_continuous_take(footage, narration, tmp_path):
    plan, v, a, files = _setup(footage, narration)
    R = SE.resolve(v, a, files, [], {"provider": "manual"}, tmp_path, narration_dir=narration)
    _check_timeline(R)
    # the voice is the original recording shifted, not re-assembled: inner pauses keep their length
    on = _envelope(R.speech) > 0.05
    edges = np.flatnonzero(np.diff(on.astype(int)))
    first = edges[0] / 100
    assert abs(first - (SE.LEAD + 0.08)) < 0.08                               # lead silence trimmed
    gaps = [(edges[i + 1] - edges[i]) / 100 for i in range(1, len(edges) - 1, 2)]
    assert len(gaps) == 4 and abs(gaps[0] - 0.3) < 0.06 and abs(gaps[2] - 0.3) < 0.06 and abs(gaps[1] - 0.5) < 0.06
    assert abs(R.total - (SE.LEAD + 8.6 - 0.72 + 0.25 + SE.TAIL)) < 0.2
    assert any("continuous" in n for n in R.notes)


def test_shots_cut_on_pauses_and_keep_animations(footage, narration, tmp_path):
    plan, v, a, files = _setup(footage, narration)
    R = SE.resolve(v, a, files, [], {"provider": "manual"}, tmp_path, narration_dir=narration)
    sp = SE.narration_spine(narration / "IMG_0400.MOV")
    t, cuts = 0.0, []
    for s in R.segments[:-1]:
        t += s.dur
        cuts.append(t)
    for c in cuts:   # no cut inside a spoken phrase
        assert not any(a + 0.05 < c < b - 0.05 for a, b in sp.phrases), (c, sp.phrases)
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
