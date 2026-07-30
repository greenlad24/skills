from __future__ import annotations

from app.modules.research.swipe import extraction, guardrail, templates
from app.modules.research.swipe.mediatools import StubSceneDetector


def _transcripts(n=3):
    out = []
    for i in range(n):
        tr, _ = extraction.extract_transcript(f"https://tt/{i}", f"vid{i}", 28.0)
        out.append(tr)
    return out


def test_extract_formula_schema_and_support():
    trs = _transcripts(3)
    f = templates.extract_formula(trs, "beauty.skincare", [1.0, 2.0, 3.0], ["a", "b", "c"])
    assert f is not None
    assert f["support_count"] == 3
    assert f["signal_type"] == "engagement_proxy"
    assert f["structure"]["beats"]
    assert f["proxy_score"] == 2.0
    # under min support → None
    assert templates.extract_formula(trs[:1], "x", [1.0], ["a"], min_support=2) is None


def test_extract_hook_abstract_and_niche_scoped():
    tr = _transcripts(1)[0]
    h = templates.extract_hook(tr, "beauty.skincare", 5.0, "vidX")
    assert h["signal_type"] == "engagement_proxy"
    assert h["name"].startswith("beauty.skincare:")
    assert "{" in h["pattern_th"]  # abstract slot pattern, not a copied line
    # pattern must not reproduce a source span
    corpus = [tr.merged_text]
    assert guardrail.assert_template_clean([h["pattern_th"]], corpus) == []


def test_extract_pacing_shapes():
    scenes = StubSceneDetector().detect("v.mp4")
    tr = _transcripts(1)[0]
    p = templates.extract_pacing("vid1", scenes, tr, "beauty.skincare", 4.0, "vid1")
    t = p["template"]
    sa = p["scene_analysis"]
    assert t["signal_type"] == "engagement_proxy"
    assert sa["shot_count"] == len(scenes)
    assert sa["beat_map"] and t["cut_profile"]["shots_per_10s"] > 0
