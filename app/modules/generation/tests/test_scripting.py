"""§3A scripting tests — schema validity, two-language rule, invariant pinning."""

from __future__ import annotations

import uuid

from app.modules.generation import scripting
from app.modules.generation.invariants import invariants_present
from app.modules.generation.schema import contains_thai, validate_script

PRODUCT = {
    "title_th": "ลิปเซรั่ม",
    "brand": "XYZ",
    "attributes": [
        {"key": "volume_ml", "value": "30"},
        {"key": "finish", "value": "แมตต์"},
    ],
    "approved_claims": [],
    "images": [{"url": "file:///media/p1.jpg", "is_primary": True}],
    "category": "cosmetics/lip",
    "price_thb": 259,
}


def _input(**over):
    return scripting.build_script_input(product=PRODUCT, **over)


def test_generated_script_is_schema_valid():
    script, errors, _ = scripting.generate_script(
        video_job_id=str(uuid.uuid4()), script_input=_input(),
    )
    assert errors == []
    assert validate_script(script) == []


def test_generated_script_is_claim_safe():
    si = _input()
    script, _, _ = scripting.generate_script(video_job_id=str(uuid.uuid4()), script_input=si)
    audit, _ = scripting.score_claims(script, script_input=si, idempotency_prefix="t")
    assert audit["passed"] is True


def test_two_language_rule_enforced():
    script, _, _ = scripting.generate_script(
        video_job_id=str(uuid.uuid4()), script_input=_input(),
    )
    for scene in script["scenes"]:
        # Visual prompts are English-only; narration/on-screen are Thai.
        assert not contains_thai(scene["visual_prompt_en"])
        assert contains_thai(scene["thai_narration"]) or scene["thai_narration"] == ""


def test_global_invariants_pinned_in_every_visual_prompt():
    si = _input()
    script, _, _ = scripting.generate_script(video_job_id=str(uuid.uuid4()), script_input=si)
    inv = si["global_invariants"]
    for scene in script["scenes"]:
        assert invariants_present(scene["visual_prompt_en"], inv)


def test_faceless_all_broll():
    # Faceless workflow: every scene is BROLL (generated product footage), no avatar.
    script, _, _ = scripting.generate_script(
        video_job_id=str(uuid.uuid4()), script_input=_input(),
    )
    assert script["scenes"], "expected scenes"
    for scene in script["scenes"]:
        assert scene["asset_type"] == "BROLL"


def test_forced_bad_narration_fails_gate():
    si = _input()
    script, _, _ = scripting.generate_script(
        video_job_id=str(uuid.uuid4()), script_input=si,
        forced_narration={"0": "ครีมนี้ขาวขึ้นชัวร์ ดีที่สุด"},
    )
    audit, _ = scripting.score_claims(script, script_input=si, idempotency_prefix="t")
    assert audit["passed"] is False
