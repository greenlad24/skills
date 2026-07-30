"""§3A.4 schema + §3B hybrid-rule validation tests."""

from __future__ import annotations

import uuid

from app.modules.generation.invariants import compose_visual_prompt
from app.modules.generation.schema import (
    contains_thai,
    has_latin_marketing_copy,
    validate_script,
)

INV = {
    "product_desc_en": "a 30ml frosted-glass lip serum bottle with a gold cap",
    "set_desc_en": "clean pastel-pink vanity",
    "style_en": "authentic UGC iPhone look, 9:16 vertical",
}


def _scene(role, asset_type, order=0, narration="สวัสดีจ้า มาดูกันนะ"):
    return {
        "scene_id": str(uuid.uuid4()),
        "order": order,
        "role": role,
        "thai_narration": narration,
        "visual_prompt_en": compose_visual_prompt(INV, "creator talking to camera"),
        "on_screen_text_th": "โปรโมชั่น",
        "duration_s": 3.0,
        "asset_type": asset_type,
    }


def _script(scenes):
    return {
        "script_id": str(uuid.uuid4()),
        "video_job_id": str(uuid.uuid4()),
        "language": "th",
        "total_duration_s": sum(s["duration_s"] for s in scenes),
        "scenes": scenes,
        "claim_audit": {"passed": True, "checked_at": "2026-01-01T00:00:00Z", "findings": []},
    }


def test_valid_script_passes():
    scenes = [
        _scene("HOOK", "AVATAR", 0),
        _scene("DEMO", "BROLL", 1),
        _scene("PROOF", "BROLL", 2),
        _scene("CTA", "AVATAR", 3),
    ]
    assert validate_script(_script(scenes)) == []


def test_avatar_demo_combo_rejected():
    # AVATAR must be HOOK/CTA — an AVATAR+DEMO scene is a hybrid-rule violation.
    scenes = [_scene("DEMO", "AVATAR", 0), _scene("CTA", "AVATAR", 1)]
    errors = validate_script(_script(scenes))
    assert any("hybrid-rule violation" in e for e in errors)


def test_broll_hook_combo_rejected():
    scenes = [_scene("HOOK", "BROLL", 0), _scene("CTA", "AVATAR", 1)]
    errors = validate_script(_script(scenes))
    assert any("hybrid-rule violation" in e for e in errors)


def test_visual_prompt_must_be_english_only():
    bad = _scene("DEMO", "BROLL", 0)
    bad["visual_prompt_en"] = "โชว์สินค้า close up of the bottle please please"
    other = _scene("PROOF", "BROLL", 1)
    errors = validate_script(_script([bad, other]))
    assert any("English-only" in e for e in errors)


def test_thai_field_rejects_latin_marketing_copy():
    bad = _scene("HOOK", "AVATAR", 0)
    bad["thai_narration"] = "amazing product ที่สุด"
    other = _scene("CTA", "AVATAR", 1)
    errors = validate_script(_script([bad, other]))
    assert any("Latin marketing copy" in e for e in errors)


def test_too_few_scenes_rejected():
    errors = validate_script(_script([_scene("HOOK", "AVATAR", 0)]))
    assert any("2..8" in e for e in errors)


def test_language_helpers():
    assert contains_thai("สวัสดี")
    assert not contains_thai("hello world")
    assert has_latin_marketing_copy("amazing")
    assert not has_latin_marketing_copy("30ml")  # short unit token allowed
