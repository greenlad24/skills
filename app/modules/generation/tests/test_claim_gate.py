"""§3A.6 claim-safety gate — fail-closed tests."""

from __future__ import annotations

import uuid

from app.modules.generation import claim_gate


def _script(narrations):
    scenes = []
    for i, text in enumerate(narrations):
        scenes.append(
            {
                "scene_id": str(uuid.uuid4()),
                "order": i,
                "role": "HOOK" if i % 2 == 0 else "CTA",
                "thai_narration": text,
                "on_screen_text_th": "",
                "asset_type": "AVATAR",
            }
        )
    return {"scenes": scenes}


def test_efficacy_claim_blocked_when_not_approved():
    audit, _ = claim_gate.run_claim_gate(
        _script(["ครีมนี้เห็นผลใน 7 วัน"]),
        approved_claims=[],
        operator_verified_experience=False,
        use_llm_judge=False, use_compliance=False,
    )
    assert audit["passed"] is False
    assert any(f["category"] == "EFFICACY" and f["verdict"] == "BLOCK"
               for f in audit["findings"])


def test_whitening_claim_blocked():
    audit, _ = claim_gate.run_claim_gate(
        _script(["ใช้แล้วผิวขาวขึ้น"]),
        approved_claims=[], use_llm_judge=False, use_compliance=False,
    )
    assert audit["passed"] is False
    assert any(f["category"] == "WHITENING" for f in audit["findings"])


def test_first_person_blocked_without_operator_flag():
    audit, _ = claim_gate.run_claim_gate(
        _script(["ฉันใช้แล้วดีมาก"]),
        approved_claims=[], operator_verified_experience=False, use_llm_judge=False, use_compliance=False,
    )
    assert audit["passed"] is False


def test_first_person_allowed_when_operator_verified():
    audit, _ = claim_gate.run_claim_gate(
        _script(["ฉันใช้แล้วดีมาก"]),
        approved_claims=[], operator_verified_experience=True, use_llm_judge=False, use_compliance=False,
    )
    # First-person now authorized → the only finding is ALLOW, so it passes.
    assert audit["passed"] is True


def test_approved_claim_verbatim_allowed():
    audit, _ = claim_gate.run_claim_gate(
        _script(["สินค้าเห็นผลจริง"]),
        approved_claims=["เห็นผล"],  # merchant-verified, allowed verbatim
        use_llm_judge=False, use_compliance=False,
    )
    assert audit["passed"] is True


def test_superlative_always_blocked_even_if_in_approved_claims():
    audit, _ = claim_gate.run_claim_gate(
        _script(["ดีที่สุดในไทย"]),
        approved_claims=["ดีที่สุด"],  # cannot authorize a superlative
        use_llm_judge=False, use_compliance=False,
    )
    assert audit["passed"] is False
    assert any(f["category"] == "SUPERLATIVE" for f in audit["findings"])


def test_clean_attribute_only_script_passes():
    audit, _ = claim_gate.run_claim_gate(
        _script(["เนื้อแมตต์ กลิ่นวานิลลา 30ml"]),
        approved_claims=[], use_llm_judge=False, use_compliance=False,
    )
    assert audit["passed"] is True
    assert audit["findings"] == []


def test_blocking_spans_helper():
    audit, _ = claim_gate.run_claim_gate(
        _script(["ครีมรักษาสิว หายขาด"]), approved_claims=[], use_llm_judge=False, use_compliance=False,
    )
    spans = claim_gate.blocking_spans(audit)
    assert spans and all(s["verdict"] == "BLOCK" for s in spans)
