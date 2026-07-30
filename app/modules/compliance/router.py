"""Compliance module router — mounted at /api/compliance by app.main.load_modules().

Read-only / advisory endpoints plus the takedown (revocation) path (§6C.1). The hard
publish gate itself is enforced by the core approve endpoint reading this module's
checklist; these endpoints expose the classifier, the checklist, and the audit surface.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.modules.compliance import ruleset
from app.modules.compliance.consent import consent_validity
from app.modules.compliance.service import classify_claims, run_prepost_checklist

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


@router.get("/health")
def health() -> dict:
    return {
        "module": "compliance",
        "ok": True,
        "dry_run": settings.DRY_RUN,
        "ruleset_version": ruleset.RULESET_VERSION,
        "classifier_prompt_version": ruleset.CLASSIFIER_PROMPT_VERSION,
        "not_legal_advice": True,
    }


@router.get("/ruleset")
def get_ruleset() -> dict:
    """Expose the versioned rule tables (config-as-data, §6.0/§6E)."""
    return {
        "ruleset_version": ruleset.RULESET_VERSION,
        "classifier_prompt_version": ruleset.CLASSIFIER_PROMPT_VERSION,
        "category_rules": ruleset.CATEGORY_RULES,
        "disclosure_copy": ruleset.DISCLOSURE_COPY,
        "jurisdiction_map": ruleset.JURISDICTION_MAP,
    }


@router.post("/classify")
def classify(script: dict = Body(...)) -> dict:
    """Run the §6B claim-safety scan on a script dict. Fail-closed."""
    return classify_claims(script)


@router.get("/checklist/{job_id}")
def checklist(job_id: str) -> dict:
    """Run the §6D pre-post checklist for a job. passed=false unless all-green."""
    return run_prepost_checklist(job_id)


@router.get("/consent/{avatar_id}/validity")
def consent_check(
    avatar_id: str,
    category: str | None = None,
    uses_cloned_voice: bool = True,
    db: Session = Depends(get_db),
) -> dict:
    """Evaluate consent_valid() for the newest ConsentRecord of an avatar."""
    from app.core.models import ConsentRecord

    rows = db.execute(
        select(ConsentRecord)
        .where(ConsentRecord.avatar_id == avatar_id)
        .order_by(ConsentRecord.created_at.desc())
    ).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="no consent record for avatar")
    consent = next((c for c in rows if not c.revoked), rows[0])

    class _Ctx:
        pass

    ctx = _Ctx()
    ctx.category = category
    ctx.uses_cloned_voice = uses_cloned_voice
    ok, reasons = consent_validity(ctx, consent)
    return {"valid": ok, "reasons": reasons, "consent_id": str(consent.id)}


@router.post("/consent/{consent_id}/revoke")
def revoke_consent(
    consent_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db),
) -> dict:
    """§6C.1 revocation/takedown path. Marks the consent revoked, flags referencing
    Posts for takedown/review, and records the revocation. Immediately invalidates all
    future jobs (``consent_valid()`` reads ``revoked``)."""
    from app.core.models import ConsentRecord, Post, VideoJob

    consent = db.get(ConsentRecord, consent_id)
    if consent is None:
        raise HTTPException(status_code=404, detail="consent record not found")

    consent.revoked = True
    consent.revoked_at = datetime.now(timezone.utc)

    # Flag existing Posts on jobs using this avatar for takedown/review.
    flagged: list[str] = []
    job_ids = db.execute(
        select(VideoJob.id).where(VideoJob.avatar_id == consent.avatar_id)
    ).scalars().all()
    if job_ids:
        posts = db.execute(
            select(Post).where(Post.video_job_id.in_(job_ids))
        ).scalars().all()
        for p in posts:
            p.shop_tag_status = "TAKEDOWN_REVIEW"
            flagged.append(str(p.id))

    db.commit()
    return {
        "revoked": True,
        "consent_id": str(consent.id),
        "revoked_at": consent.revoked_at.isoformat(),
        "posts_flagged_for_takedown": flagged,
        "reason": body.get("reason"),
    }
