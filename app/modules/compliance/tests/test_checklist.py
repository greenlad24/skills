"""§6F.4 checklist-gate tests — the gate blocks when any single check is red, and a
human cannot override a red check (there is no override path in evaluate_checklist)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.compliance import ruleset
from app.modules.compliance.checklist import evaluate_checklist
from app.modules.compliance.common import ClaimClass, Decision


def _valid_consent():
    now = datetime.now(timezone.utc)
    return {
        "subject_is_operator": True,
        "identity_verified": True,
        "biometric_explicit_consent": True,
        "voice_licensed": True,
        "revoked": False,
        "term": {"start": (now - timedelta(days=10)).date().isoformat(),
                 "end": (now + timedelta(days=300)).date().isoformat()},
        "scope": {"categories": ["beauty"], "territory": ["TH"],
                  "usage": ["recorded_shoppable_video"]},
    }


def _all_green_evidence():
    shash = "sha256:deadbeef"
    return {
        "job": {"category": "beauty", "uses_cloned_voice": True},
        "consent": _valid_consent(),
        "render_script_hash": shash,
        "ruleset_version": ruleset.RULESET_VERSION,
        "manifest": {
            "real_environment_score": 0.9, "camera_motion_score": 0.5,
            "face_product_cooccurrence_s": 2.0, "duration_s": 12.0,
            "frame_entropy": 0.6, "looped": False, "ai_embellished": False,
            "embellishment_profile": "none",
        },
        "post": {"platform_toggle_set": True},
        "envelope": {
            "script_hash": shash,
            "ruleset_version": ruleset.RULESET_VERSION,
            "category": "beauty",
            "category_rules_satisfied": True,
            "disclosure": {
                "label_baked_first_3s": True, "platform_toggle_set": True,
                "c2pa_embedded": True, "label_from_s": 0.0, "label_to_s": 3.0,
            },
            "claim_decisions": [
                {"segment_id": "seg_000", "claim_class": ClaimClass.EXPERIENTIAL,
                 "final_decision": Decision.NEEDS_OPERATOR_VERIFICATION,
                 "resolved": True, "resolution": "OPERATOR_VERIFIED",
                 "operator_affirmed": True, "actor_identity_ref": "kyc_1"},
                {"segment_id": "seg_001", "claim_class": ClaimClass.EFFICACY_HEALTH,
                 "final_decision": Decision.NEEDS_SUBSTANTIATION,
                 "resolved": True, "resolution": "SUBSTANTIATED",
                 "substantiation_ref": "sub_9"},
            ],
        },
    }


def test_all_green_passes():
    result = evaluate_checklist(_all_green_evidence())
    reds = [c for c in result["checks"] if not c["passed"]]
    assert result["passed"] is True, reds


def test_missing_disclosure_label_blocks():
    ev = _all_green_evidence()
    ev["envelope"]["disclosure"]["label_baked_first_3s"] = False
    result = evaluate_checklist(ev)
    assert result["passed"] is False
    chk1 = next(c for c in result["checks"] if c["id"] == "CHK-1")
    assert chk1["passed"] is False


def test_platform_toggle_off_blocks():
    ev = _all_green_evidence()
    ev["post"]["platform_toggle_set"] = False
    ev["envelope"]["disclosure"]["platform_toggle_set"] = False
    assert evaluate_checklist(ev)["passed"] is False


def test_unresolved_claim_blocks():
    ev = _all_green_evidence()
    ev["envelope"]["claim_decisions"][0]["resolved"] = False
    result = evaluate_checklist(ev)
    assert result["passed"] is False
    chk4 = next(c for c in result["checks"] if c["id"] == "CHK-4")
    assert chk4["passed"] is False


def test_experiential_not_operator_verified_blocks():
    ev = _all_green_evidence()
    ev["envelope"]["claim_decisions"][0]["operator_affirmed"] = False
    assert evaluate_checklist(ev)["passed"] is False


def test_efficacy_without_substantiation_blocks():
    ev = _all_green_evidence()
    ev["envelope"]["claim_decisions"][1]["substantiation_ref"] = None
    assert evaluate_checklist(ev)["passed"] is False


def test_revoked_consent_blocks():
    ev = _all_green_evidence()
    ev["consent"]["revoked"] = True
    result = evaluate_checklist(ev)
    assert result["passed"] is False
    chk8 = next(c for c in result["checks"] if c["id"] == "CHK-8")
    assert chk8["passed"] is False


def test_unknown_category_blocks():
    ev = _all_green_evidence()
    ev["job"]["category"] = "weapons"
    ev["envelope"]["category"] = "weapons"
    result = evaluate_checklist(ev)
    assert result["passed"] is False  # unknown category -> restricted (fail safe)


def test_script_hash_mismatch_blocks():
    ev = _all_green_evidence()
    ev["render_script_hash"] = "sha256:changed"
    result = evaluate_checklist(ev)
    assert result["passed"] is False
    chk10 = next(c for c in result["checks"] if c["id"] == "CHK-10")
    assert chk10["passed"] is False


def test_deprecated_ruleset_blocks():
    ev = _all_green_evidence()
    ev["envelope"]["ruleset_version"] = "1999.01.0"
    ev["ruleset_version"] = "1999.01.0"
    assert evaluate_checklist(ev)["passed"] is False


def test_empty_evidence_fails_closed():
    result = evaluate_checklist({})
    assert result["passed"] is False
    assert all(len(result["checks"]) == 11 for _ in [0])
