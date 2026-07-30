"""§6F.1 claim-gate tests — the classifier fails closed on experiential/health claims
and can never auto-ALLOW a risky class."""

from __future__ import annotations

from app.modules.compliance.common import Action, ClaimClass
from app.modules.compliance.service import classify_claims


def _flags_by_type(result: dict) -> dict[str, dict]:
    return {f["type"]: f for f in result["flags"]}


def test_thai_whitening_efficacy_is_blocked():
    # AC-6B-1: Thai whitening/efficacy -> EFFICACY_HEALTH, action BLOCK, not allowed.
    result = classify_claims({"full_text": "หลังจากใช้ผิวขาวขึ้น"})
    assert result["allowed"] is False
    flags = _flags_by_type(result)
    assert ClaimClass.EFFICACY_HEALTH in flags
    assert flags[ClaimClass.EFFICACY_HEALTH]["action"] == Action.BLOCK


def test_english_efficacy_is_blocked():
    result = classify_claims({"full_text": "This cream whitens skin in 7 days."})
    assert result["allowed"] is False
    assert any(f["action"] == Action.BLOCK for f in result["flags"])


def test_experiential_first_person_routes_not_allowed():
    # AC-6B-2: first-person experiential -> ROUTE (operator verification), not allowed.
    result = classify_claims({"full_text": "I use this every day and my skin cleared."})
    assert result["allowed"] is False
    flags = _flags_by_type(result)
    assert ClaimClass.EXPERIENTIAL in flags
    assert flags[ClaimClass.EXPERIENTIAL]["action"] == Action.ROUTE


def test_comparative_and_guarantee_blocked():
    result = classify_claims({"segments": [
        "The best whitening cream in Thailand.",
        "Money-back guaranteed results.",
    ]})
    assert result["allowed"] is False
    actions = {f["action"] for f in result["flags"]}
    assert Action.BLOCK in actions
    # No risky claim may be ALLOW.
    for f in result["flags"]:
        if f["type"] in ClaimClass.NEVER_AUTO_ALLOW:
            assert f["action"] != Action.ALLOW


def test_neutral_script_allowed():
    result = classify_claims({"full_text": "สวัสดีค่ะ วันนี้มารีวิวสินค้า"})
    assert result["allowed"] is True
    assert result["flags"] == []


def test_efficacy_never_auto_allowed_property():
    # AC-6B-7: over a batch of risky inputs, none is ever ALLOW.
    risky = [
        "รักษาสิวให้หายขาด",           # cure/treat
        "ลดริ้วรอย อ่อนกว่าวัย",       # anti-aging
        "อันดับ 1 ในไทย",              # comparative
        "รับประกันผล 100%",            # guarantee
        "whitening serum brightens skin",
        "I tried it and it worked for me",
    ]
    for text in risky:
        result = classify_claims({"full_text": text})
        assert result["allowed"] is False, text
        for f in result["flags"]:
            if f["type"] in ClaimClass.NEVER_AUTO_ALLOW:
                assert f["action"] != Action.ALLOW, (text, f)


def test_substantiated_efficacy_can_pass():
    # AC-6B-3: efficacy matched to approved-claims WITH substantiation_ref -> passes.
    script = {
        "full_text": "ครีมนี้ช่วยลดริ้วรอย",
        "approved_claims": [
            {"text": "ครีมนี้ช่วยลดริ้วรอย", "substantiation_ref": "sub_123"},
        ],
    }
    result = classify_claims(script)
    # With a substantiation ref the claim is resolvable to ALLOW.
    assert result["allowed"] is True


def test_efficacy_without_ref_blocks():
    script = {
        "full_text": "ครีมนี้ช่วยลดริ้วรอย",
        "approved_claims": [{"text": "ครีมนี้ช่วยลดริ้วรอย"}],  # no substantiation_ref
    }
    result = classify_claims(script)
    assert result["allowed"] is False
