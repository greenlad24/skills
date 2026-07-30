"""Public service API — the two functions other modules import (per CONTRACTS.md).

    classify_claims(script: dict) -> dict
    run_prepost_checklist(job_id) -> dict

Both fail CLOSED. ``classify_claims`` never auto-ALLOWs an experiential / efficacy /
health / comparative / guarantee claim; ``run_prepost_checklist`` returns passed=false
unless every §6D check is green (no human override of a red check).
"""

from __future__ import annotations

from typing import Any

from app.modules.compliance import checklist as _checklist
from app.modules.compliance import classifier as _classifier
from app.modules.compliance.common import Action


# --------------------------------------------------------------------------- #
# 1) Claim-safety scan (§6B).
# --------------------------------------------------------------------------- #
def classify_claims(script: dict) -> dict:
    """Scan a generated script and return the claim-safety verdict.

    Returns::

        {
          "allowed": bool,                       # True iff EVERY flag is action=ALLOW
          "flags": [ {claim, type, action, reason, ...} ],
          "script_hash": "sha256:...",
          "ruleset_version": "...",
          "classifier_prompt_version": "...",
        }

    ``action`` ∈ {"BLOCK","ROUTE","ALLOW"}. Fail closed: experiential claims ->
    ROUTE (operator verification); efficacy/health/comparative/guarantee -> BLOCK unless
    resolved via the merchant approved-claims library elsewhere. Any classifier failure
    keeps the deterministic (already fail-closed) decision — never an auto-pass.
    """
    category: str | None = None
    approved: list[dict[str, Any]] | None = None
    if isinstance(script, dict):
        category = script.get("category") or (script.get("meta") or {}).get("category")
        approved = (
            script.get("approved_claims")
            or script.get("approved_claims_library")
            or None
        )

    try:
        report = _classifier.classify_script(
            script, category=category, approved_claims=approved
        )
    except Exception as exc:
        # Total failure -> fail closed: nothing allowed.
        return {
            "allowed": False,
            "flags": [{
                "claim": None, "type": "CLASSIFIER_ERROR", "action": Action.BLOCK,
                "reason": f"Classifier error (fail closed): {exc}",
            }],
            "script_hash": None,
        }

    results = report.get("_results", [])
    # A flag per non-neutral segment (attribute-with-source surfaces as ALLOW, logged).
    flags: list[dict[str, Any]] = []
    for r in results:
        if r.claim_class == "NEUTRAL" and r.action == Action.ALLOW:
            continue  # plain neutral text — nothing to flag
        flags.append(r.to_flag())

    allowed = all(f["action"] == Action.ALLOW for f in flags)
    return {
        "allowed": allowed,
        "flags": flags,
        "script_hash": report.get("script_hash"),
        "ruleset_version": report.get("ruleset_version"),
        "classifier_prompt_version": report.get("classifier_prompt_version"),
        "llm_ok": report.get("llm_ok"),
    }


# --------------------------------------------------------------------------- #
# 2) Pre-post checklist gate (§6D).
# --------------------------------------------------------------------------- #
def run_prepost_checklist(job_id) -> dict:
    """Deterministic §6D gate for a job. Returns ``{"passed": bool, "checks": [...]}``.

    Gathers evidence from the DB (ComplianceRecord envelope, ConsentRecord, Post) and
    evaluates CHK-1..11. Missing evidence or DB errors -> checks fail closed.
    """
    evidence = gather_evidence(job_id)
    return _checklist.evaluate_checklist(evidence)


def evaluate_checklist(evidence: dict) -> dict:
    """Pure re-export of the checklist evaluator (testable with plain dicts)."""
    return _checklist.evaluate_checklist(evidence)


# --------------------------------------------------------------------------- #
# Evidence gathering (DB -> evidence dict for the checklist).
# --------------------------------------------------------------------------- #
def gather_evidence(job_id) -> dict[str, Any]:
    """Best-effort evidence assembly from core models. Fail-closed on any error."""
    from app.core.db import SessionLocal
    from app.modules.compliance.records import load_latest_envelope

    evidence: dict[str, Any] = {"job": None, "consent": None, "envelope": None}
    db = None
    try:
        db = SessionLocal()
        from sqlalchemy import select

        from app.core.models import ConsentRecord, Post, VideoJob

        job = db.get(VideoJob, job_id)
        if job is None:
            return evidence  # unknown job -> everything fails closed

        envelope = load_latest_envelope(db, job_id) or {}
        evidence["envelope"] = envelope

        # Category / cloned-voice live on the envelope (VideoJob has no category column).
        category = envelope.get("category")
        uses_voice = envelope.get("uses_cloned_voice")
        if uses_voice is None:
            uses_voice = bool(job.voice_profile_id)
        evidence["job"] = _JobCtx(category=category, uses_cloned_voice=uses_voice)

        # Consent: newest non-revoked record for the job's avatar.
        consent = None
        if job.avatar_id is not None:
            rows = db.execute(
                select(ConsentRecord)
                .where(ConsentRecord.avatar_id == job.avatar_id)
                .order_by(ConsentRecord.created_at.desc())
            ).scalars().all()
            consent = next((c for c in rows if not c.revoked), rows[0] if rows else None)
        evidence["consent"] = consent

        # Post payload for the CHK-2 re-assertion at post time.
        post = db.execute(
            select(Post).where(Post.video_job_id == job_id)
        ).scalars().first()
        if post is not None:
            evidence["post"] = {
                "platform_toggle_set": bool(post.ai_disclosure_set),
            }

        # Rendered script hash for CHK-10 (draft asset meta if present; else envelope).
        evidence["render_script_hash"] = envelope.get("render_script_hash") or envelope.get("script_hash")
        evidence["ruleset_version"] = envelope.get("ruleset_version")
    except Exception:
        # Any DB failure -> return what we have; missing pieces fail closed downstream.
        return evidence
    finally:
        if db is not None:
            db.close()
    return evidence


class _JobCtx:
    """Lightweight duck-typed job context for consent_valid / verifiers."""

    def __init__(self, *, category: str | None, uses_cloned_voice: bool) -> None:
        self.category = category
        self.uses_cloned_voice = uses_cloned_voice
