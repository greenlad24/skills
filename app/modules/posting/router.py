"""Posting module HTTP surface (spec §5A / §7A.10). Prefix: /api/posting.

Mounted automatically by app.main.load_modules(). Provides the approval gate
(approve / reject / reroll), the manual shop-tag mark endpoint, a variant-batch
generation trigger, an analytics-ingest trigger, and a small analytics read.

The gate render itself (inline video, caption editor, username+avatar confirmation
panel) is the frontend's job; these endpoints are the actions behind it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Post, VideoJob
from app.modules.posting import ingest as ingest_mod
from app.modules.posting import service, variants
from app.modules.posting.schemas import (
    ApproveRequest,
    DecisionResponse,
    IngestResponse,
    PostView,
    RejectRequest,
    RerollRequest,
    TaggedResponse,
    VariantBatchRequest,
    VariantBatchResponse,
)

router = APIRouter(prefix="/api/posting", tags=["posting"])


@router.get("/health")
def posting_health() -> dict:
    """Prove the module mounted."""
    return {"module": "posting", "ok": True}


# --------------------------------------------------------------------------- #
# 5A — the approval gate (human-only edges out of AWAITING_APPROVAL)
# --------------------------------------------------------------------------- #
@router.post("/jobs/{job_id}/approve", response_model=DecisionResponse)
def approve(
    job_id: str, body: ApproveRequest, db: Session = Depends(get_db)
) -> DecisionResponse:
    """Approve & Post/Schedule → compliance hard gate → POSTING (enqueues posting.run).

    Returns 409 if the compliance checklist is not all-green (no override in v1) or
    if the job is not AWAITING_APPROVAL; 422 on a disclosure/visibility conflict.
    """
    try:
        out = service.approve(db, job_id, body.model_dump())
    except service.ComplianceNotGreenError as exc:
        raise HTTPException(status_code=409, detail={
            "error": "compliance_not_green", "compliance": exc.checklist,
        }) from exc
    except service.PostingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return DecisionResponse(state=out["state"], compliance=out.get("compliance"))


@router.post("/jobs/{job_id}/reject", response_model=DecisionResponse)
def reject(
    job_id: str, body: RejectRequest, db: Session = Depends(get_db)
) -> DecisionResponse:
    """Reject at the gate → terminal REJECTED (discard)."""
    try:
        out = service.reject(db, job_id, body.note)
    except service.PostingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return DecisionResponse(state=out["state"])


@router.post("/jobs/{job_id}/reroll", response_model=DecisionResponse)
def reroll(
    job_id: str, body: RerollRequest, db: Session = Depends(get_db)
) -> DecisionResponse:
    """Request re-roll → back to EDITING (cheap re-cut loop)."""
    try:
        out = service.reroll(db, job_id, body.stage, body.note)
    except service.PostingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return DecisionResponse(state=out["state"], from_stage=out.get("from_stage"))


@router.post("/jobs/{job_id}/tagged", response_model=TaggedResponse)
def mark_tagged(job_id: str, db: Session = Depends(get_db)) -> TaggedResponse:
    """Mark the MANUAL TikTok-Shop product tag done (spec §5A.5 #3).

    The product/affiliate tag cannot be attached via any API — this only records
    that the operator tapped it in the TikTok app and lifts the dashboard reminder.
    """
    try:
        out = service.mark_tagged(db, job_id)
    except service.PostingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return TaggedResponse(tagged=out["tagged"], shop_tag_status=out["shop_tag_status"])


@router.get("/jobs/{job_id}/post", response_model=PostView)
def get_post(job_id: str, db: Session = Depends(get_db)) -> PostView:
    """Read the Post for a job (incl. shop-tag reminder state + latest score)."""
    job = db.get(VideoJob, job_id)
    if job is None or job.post is None:
        raise HTTPException(status_code=404, detail="no post for this job")
    p = job.post
    return PostView(
        id=p.id, status=p.status, post_url=p.post_url, deep_link=p.deep_link,
        shop_tag_status=p.shop_tag_status,
        product_tag_attached=bool(p.product_tag_attached),
        latest_score=p.latest_score,
    )


# --------------------------------------------------------------------------- #
# 5B — winner loop triggers + analytics read
# --------------------------------------------------------------------------- #
@router.post("/variants", response_model=VariantBatchResponse)
def create_variant_batch(
    body: VariantBatchRequest, db: Session = Depends(get_db)
) -> VariantBatchResponse:
    """Generate a differentiated N-variant batch for a product (spec §5B.1/§5B.2)."""
    out = variants.generate_variant_batch(
        str(body.product_id), body.n, hook_selector=body.hook_selector, session=db
    )
    return VariantBatchResponse(**out)


@router.post("/ingest", response_model=IngestResponse)
def trigger_ingest(db: Session = Depends(get_db)) -> IngestResponse:
    """Run the analytics-ingest cycle now (the scheduled task does this daily)."""
    out = ingest_mod.ingest_daily(db)
    return IngestResponse(**out)


@router.get("/analytics/posts", response_model=list[PostView])
def list_scored_posts(db: Session = Depends(get_db)) -> list[PostView]:
    """Dashboard analytics: posts with their latest score + shop-tag flag.

    Untagged published posts are surfaced here so the dashboard can visually flag
    them (they are excluded from 'shoppable' analytics until tagged — spec §5A.5 #3).
    """
    posts = list(db.execute(select(Post)).scalars().all())
    return [
        PostView(
            id=p.id, status=p.status, post_url=p.post_url, deep_link=p.deep_link,
            shop_tag_status=p.shop_tag_status,
            product_tag_attached=bool(p.product_tag_attached),
            latest_score=p.latest_score,
        )
        for p in posts
    ]
