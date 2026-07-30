"""§6F.3 consent predicate + §6C.3 hash-chain audit tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.compliance.consent import consent_valid, consent_validity
from app.modules.compliance.records import ClaimDecision, ComplianceLedger, RecordSealedError


def _consent(**over):
    now = datetime.now(timezone.utc)
    base = {
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
    base.update(over)
    return base


def _job(**over):
    j = {"category": "beauty", "uses_cloned_voice": True}
    j.update(over)
    return j


def test_valid_consent_passes():
    assert consent_valid(_job(), _consent()) is True


def test_missing_consent_fails_closed():
    ok, reasons = consent_validity(_job(), None)
    assert ok is False and "no_consent_record" in reasons


def test_category_out_of_scope_blocks():
    assert consent_valid(_job(category="electronics"), _consent()) is False


def test_unknown_category_blocks():
    ok, reasons = consent_validity(_job(category=None), _consent())
    assert ok is False and "job_category_unknown" in reasons


def test_expired_term_blocks():
    now = datetime.now(timezone.utc)
    c = _consent(term={"start": (now - timedelta(days=400)).date().isoformat(),
                       "end": (now - timedelta(days=10)).date().isoformat()})
    ok, reasons = consent_validity(_job(), c)
    assert ok is False and "term_expired" in reasons


def test_not_operator_blocks():
    assert consent_valid(_job(), _consent(subject_is_operator=False)) is False


def test_cloned_voice_requires_license():
    ok, reasons = consent_validity(_job(uses_cloned_voice=True),
                                   _consent(voice_licensed=False))
    assert ok is False and "voice_licensed_false" in reasons


def test_revoked_blocks():
    assert consent_valid(_job(), _consent(revoked=True)) is False


def test_territory_must_be_th():
    c = _consent(scope={"categories": ["beauty"], "territory": ["US"],
                        "usage": ["recorded_shoppable_video"]})
    assert consent_valid(_job(), c) is False


# --- hash-chain audit --- #
def test_hash_chain_verifies_and_detects_tamper():
    led = ComplianceLedger("job_1", script_hash="sha256:abc")
    led.add_claim_decision(ClaimDecision(
        segment_id="seg_000", text_hash="sha256:x", claim_class="EFFICACY_HEALTH",
        final_decision="BLOCK", resolved=True, resolution="REMOVED_BY_EDIT"))
    led.set_disclosure(label_baked_first_3s=True, c2pa_embedded=True)
    assert led.verify_chain() is True

    # Tamper with a prior event's payload -> chain must fail.
    led.events[1]["payload"]["final_decision"] = "ALLOW"
    assert led.verify_chain() is False


def test_sealed_record_is_immutable():
    led = ComplianceLedger("job_2")
    led.seal({"passed": True, "checks": []})
    assert led.sealed_at is not None
    try:
        led.append_event("tamper", actor="attacker")
    except RecordSealedError:
        pass
    else:  # pragma: no cover
        raise AssertionError("sealed record accepted a new event")


def test_envelope_roundtrip_preserves_chain():
    led = ComplianceLedger("job_3", script_hash="sha256:zzz")
    led.set_consent("cns_1", True)
    env = led.envelope()
    restored = ComplianceLedger.from_envelope(env)
    assert restored.verify_chain() is True
    assert restored.script_hash == "sha256:zzz"
