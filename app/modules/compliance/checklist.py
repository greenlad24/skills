"""§6D pre-post checklist gate — the single deterministic go/no-go (CHK-1..11).

A VideoJob cannot leave ``AWAITING_APPROVAL`` (and can never publish) unless EVERY check
below is green. This is pure and deterministic: it runs on the final render manifest +
records. Even an approving human cannot bypass a red check (§6D, AC-6D-2).

``evaluate_checklist(evidence)`` is the pure core (fully testable with plain dicts).
``service.run_prepost_checklist(job_id)`` gathers ``evidence`` from the DB and calls it.
Any missing/ambiguous evidence -> that check is red (fail closed).
"""

from __future__ import annotations

from typing import Any

from app.modules.compliance import ruleset, verifiers
from app.modules.compliance.common import CheckResult, ClaimClass, Decision
from app.modules.compliance.consent import consent_validity

_SUBSTANTIATION_CLASSES = {
    ClaimClass.EFFICACY_HEALTH, ClaimClass.COMPARATIVE, ClaimClass.GUARANTEE,
}
_REMOVED = {"REMOVED_BY_EDIT", "removed", "edited_out"}
_BAD_RESOLUTIONS = {None, "", "unresolved", "override", "OVERRIDE"}


def _decisions(evidence: dict) -> list[dict[str, Any]]:
    env = evidence.get("envelope") or {}
    return list(env.get("claim_decisions") or [])


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #
def chk_1(evidence: dict) -> CheckResult:
    env = evidence.get("envelope") or {}
    disc = env.get("disclosure") or {}
    r = verifiers.tt_disc_1_label_first_3s(disc, evidence.get("manifest"))
    return CheckResult("CHK-1", "AI label present in first 3s", r.passed, r.detail)


def chk_2(evidence: dict) -> CheckResult:
    # Re-asserted at post time from the Post payload; fall back to envelope disclosure.
    post = evidence.get("post") or {}
    env = evidence.get("envelope") or {}
    disc = env.get("disclosure") or {}
    toggle = post.get("platform_toggle_set")
    if toggle is None:
        toggle = disc.get("platform_toggle_set", False)
    ok = bool(toggle)
    return CheckResult("CHK-2", "Platform disclosure toggle configured", ok,
                       f"platform_toggle_set={ok}")


def chk_3(evidence: dict) -> CheckResult:
    env = evidence.get("envelope") or {}
    r = verifiers.tt_disc_3_c2pa(env.get("disclosure") or {})
    return CheckResult("CHK-3", "C2PA provenance embedded", r.passed, r.detail)


def chk_4(evidence: dict) -> CheckResult:
    decisions = _decisions(evidence)
    unresolved = []
    for d in decisions:
        resolved = bool(d.get("resolved"))
        final = d.get("final_decision")
        res = d.get("resolution")
        if not resolved:
            unresolved.append(f"{d.get('segment_id')}:not-resolved")
        elif final == Decision.BLOCK and res in _BAD_RESOLUTIONS:
            unresolved.append(f"{d.get('segment_id')}:blocked-unresolved")
    ok = not unresolved
    return CheckResult("CHK-4", "No unresolved flagged claims", ok,
                       "ok" if ok else "; ".join(unresolved))


def chk_5(evidence: dict) -> CheckResult:
    bad = []
    for d in _decisions(evidence):
        if d.get("claim_class") in _SUBSTANTIATION_CLASSES and d.get("resolution") not in _REMOVED:
            # A claim that remains in the video must carry a substantiation ref.
            if not d.get("substantiation_ref"):
                bad.append(f"{d.get('segment_id')}:no-substantiation")
    ok = not bad
    return CheckResult("CHK-5", "Efficacy/comparative/guarantee substantiated", ok,
                       "ok" if ok else "; ".join(bad))


def chk_6(evidence: dict) -> CheckResult:
    bad = []
    for d in _decisions(evidence):
        if d.get("claim_class") == ClaimClass.EXPERIENTIAL and d.get("resolution") not in _REMOVED:
            if not (d.get("operator_affirmed") and d.get("actor_identity_ref")):
                bad.append(f"{d.get('segment_id')}:not-operator-verified")
    ok = not bad
    return CheckResult("CHK-6", "Experiential claims operator-verified", ok,
                       "ok" if ok else "; ".join(bad))


def chk_7(evidence: dict) -> CheckResult:
    env = evidence.get("envelope") or {}
    category = env.get("category")
    r = verifiers.tt_category_rules(category, evidence.get("manifest"))
    envelope_flag = env.get("category_rules_satisfied")
    ok = r.passed and (envelope_flag is not False)
    return CheckResult("CHK-7", "Category AI-imagery rules satisfied", ok, r.detail)


def chk_8(evidence: dict) -> CheckResult:
    job = evidence.get("job")
    consent = evidence.get("consent")
    ok, reasons = consent_validity(job, consent, now=evidence.get("now"))
    return CheckResult("CHK-8", "Consent valid & not revoked", ok,
                       "ok" if ok else f"consent_invalid: {', '.join(reasons)}")


def chk_9(evidence: dict) -> CheckResult:
    manifest = evidence.get("manifest") or {}
    job = evidence.get("job")
    consent = evidence.get("consent")
    form = verifiers.all_content_form(manifest, job, consent, now=evidence.get("now"))
    failed = [c.id for c in form if not c.passed]
    ok = not failed
    return CheckResult("CHK-9", "Content-form rules met (TT-FORM-1..5)", ok,
                       "ok" if ok else f"failed: {', '.join(failed)}")


def chk_10(evidence: dict) -> CheckResult:
    env = evidence.get("envelope") or {}
    classified = env.get("script_hash")
    rendered = evidence.get("render_script_hash")
    ok = bool(classified) and bool(rendered) and classified == rendered
    return CheckResult("CHK-10", "Script hash matches classified hash", ok,
                       f"classified={classified} rendered={rendered}")


def chk_11(evidence: dict) -> CheckResult:
    env = evidence.get("envelope") or {}
    version = env.get("ruleset_version") or evidence.get("ruleset_version")
    ok = ruleset.is_ruleset_active(version)
    return CheckResult("CHK-11", "Ruleset version current & not deprecated", ok,
                       f"ruleset_version={version} active={ok}")


_CHECKS = [chk_1, chk_2, chk_3, chk_4, chk_5, chk_6, chk_7, chk_8, chk_9, chk_10, chk_11]


def evaluate_checklist(evidence: dict) -> dict[str, Any]:
    """Run CHK-1..11. Returns ``{"passed": bool, "checks": [{id,name,passed,detail}]}``.

    ``passed`` is the AND of all rows (§6D aggregate). No human override of a red check.
    """
    checks: list[CheckResult] = []
    for fn in _CHECKS:
        try:
            checks.append(fn(evidence))
        except Exception as exc:  # any evaluation error -> fail closed
            checks.append(CheckResult(fn.__name__.upper(), fn.__name__, False,
                                      f"evaluation error (fail closed): {exc}"))
    passed = all(c.passed for c in checks)
    return {"passed": passed, "checks": [c.to_dict() for c in checks]}
