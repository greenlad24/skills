"""Celery tasks for the research module.

  * `research.run`   — the pipeline stage the core enqueues on job creation. Runs product
                       research + pulls swipe templates, persists rows, advances the job
                       RESEARCHING → SCRIPTING (or → FAILED). Idempotent-ish and $0 in
                       DRY_RUN.
  * `research.refresh` — nightly swipe-library refresh per niche (§2B.10).

State changes go ONLY through `app.core.state_machine.transition()`; every billable call
is metered into the cost ledger in the same transaction that bumps the job's accrued cost.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.core.adapters.base import ProviderResult
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.models import CostLedgerEntry, Product, SwipeSource, VideoJob
from app.core.queue import celery_app
from app.core.state_machine import IllegalTransitionError, JobState, transition

from .models import create_research_tables
from .product.service import research_product
from .swipe.service import get_templates, refresh_niche

STAGE = "research"


# --------------------------------------------------------------------------- #
# Cost ledger helper (§ CONTRACTS 3)
# --------------------------------------------------------------------------- #
def _charge(db, job: VideoJob, *, provider: str, line_item: str, amount: float, usage: dict) -> str:
    """Write a CostLedgerEntry and bump VideoJob.cost_accrued_usd in one transaction.
    Returns the budget guard verdict (OK|WARN|STOP)."""
    db.add(CostLedgerEntry(
        video_job_id=job.id, stage=STAGE, provider=provider, line_item=line_item,
        amount_usd=amount, usage=usage, incurred_at=datetime.now(timezone.utc),
    ))
    job.cost_accrued_usd = float(job.cost_accrued_usd or 0) + float(amount)
    budget = float(job.cost_budget_usd or settings.PER_VIDEO_COST_BUDGET_USD)
    accrued = float(job.cost_accrued_usd)
    if accrued >= budget:
        return "STOP"
    if accrued >= 0.8 * budget:
        return "WARN"
    return "OK"


def _swipe_gender_evidence(db, niche: str) -> dict:
    """Aggregate creator-gender counts from mined SwipeVideos for §2A.6 signal 3."""
    from app.core.models import SwipeVideo

    counts: dict[str, int] = {}
    for g in db.scalars(select(SwipeVideo.author_gender).where(SwipeVideo.niche == niche)):
        if g in ("female", "male"):
            counts[g] = counts.get(g, 0) + 1
    return counts


# --------------------------------------------------------------------------- #
# research.run
# --------------------------------------------------------------------------- #
def run_research(job_id: str, *, session=None) -> dict:
    """Core logic for the `research.run` task (importable for tests without Celery)."""
    create_research_tables()
    own_session = session is None
    db = session or SessionLocal()
    try:
        job = db.get(VideoJob, job_id)
        if job is None:
            return {"ok": False, "error": "job not found", "job_id": str(job_id)}

        # QUEUED → RESEARCHING
        try:
            transition(job, JobState.RESEARCHING)
        except IllegalTransitionError:
            # Allow re-entry if already RESEARCHING (idempotent retry); else re-raise.
            cur = job.state if isinstance(job.state, JobState) else JobState(job.state)
            if cur is not JobState.RESEARCHING:
                raise
        db.commit()

        product_row = db.get(Product, job.product_id) if job.product_id else None
        url = product_row.source_url if product_row else None
        if not url:
            transition(job, JobState.FAILED)
            job.failure_reason = "no product source_url"
            db.commit()
            return {"ok": False, "error": "no source_url", "job_id": str(job_id)}

        # --- 2A product research (scraper failure must not hard-fail) ---
        result = research_product(url, str(job.id))
        norm = result.product
        if result.cost_usd:
            _charge(db, job, provider=norm.source_platform or "scraper",
                    line_item="scrape_product", amount=result.cost_usd,
                    usage={"requests": 1})

        # Persist onto the canonical Product row.
        product_row.title = norm.title
        product_row.brand = (norm.attributes or {}).get("brand") or (norm.attributes or {}).get("vendor")
        product_row.price = norm.price
        product_row.currency = norm.currency
        # normalized extras live in Product.attributes JSON (images/category/tier/voice_gender...)
        product_row.attributes = norm.as_dict()
        product_row.raw_scrape = {"raw": norm.raw_payload, "platform": norm.source_platform}
        product_row.scraper_provider = norm.source_platform
        product_row.scraped_at = datetime.now(timezone.utc)

        # --- pull relevant swipe templates for this product's category ---
        niche = norm.category or "misc"
        linked = {"formula": None, "hook": None, "pacing": None}
        try:
            create_research_tables()
            for kind in ("formula", "hook", "pacing"):
                rows = get_templates(db, niche, kind, limit=1)  # type: ignore[arg-type]
                if rows:
                    linked[kind] = str(rows[0].id)
            if linked["formula"]:
                job.formula_template_id = _uuid(linked["formula"])
            if linked["hook"]:
                job.hook_template_id = _uuid(linked["hook"])
            if linked["pacing"]:
                job.pacing_template_id = _uuid(linked["pacing"])
        except Exception:  # noqa: BLE001 — warm library is optional; research still completes
            pass

        job.last_completed_stage = STAGE

        # RESEARCHING → SCRIPTING
        transition(job, JobState.SCRIPTING)
        db.commit()

        # enqueue next stage best-effort (broker may be absent locally)
        try:
            celery_app.send_task("scripting.run", kwargs={"job_id": str(job.id)})
        except Exception:  # noqa: BLE001
            pass

        return {
            "ok": True, "job_id": str(job.id), "state": job.state.value if isinstance(job.state, JobState) else job.state,
            "scrape_status": norm.scrape_status, "category": niche,
            "tier": norm.tier, "voice_gender": norm.voice_gender,
            "images": len(norm.images), "needs_manual_images": result.needs_manual_images,
            "cost_accrued_usd": float(job.cost_accrued_usd or 0),
            "templates_linked": linked,
        }
    except Exception as exc:  # noqa: BLE001 — mark FAILED and surface
        try:
            job = db.get(VideoJob, job_id)
            if job is not None:
                cur = job.state if isinstance(job.state, JobState) else JobState(job.state)
                if cur is JobState.RESEARCHING:
                    transition(job, JobState.FAILED)
                    job.failure_reason = f"research: {exc}"
                    db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        return {"ok": False, "error": str(exc), "job_id": str(job_id)}
    finally:
        if own_session:
            db.close()


def _uuid(v):
    import uuid as _u

    return v if isinstance(v, _u.UUID) else _u.UUID(str(v))


@celery_app.task(name="research.run")
def research_run(job_id: str) -> dict:
    return run_research(job_id)


# --------------------------------------------------------------------------- #
# research.refresh (nightly swipe library)
# --------------------------------------------------------------------------- #
def run_refresh(niche: str | None = None, top_k: int = None, *, session=None) -> dict:  # type: ignore[assignment]
    from . import config as cfg

    create_research_tables()
    own_session = session is None
    db = session or SessionLocal()
    top_k = top_k or cfg.DEFAULT_TOP_K
    try:
        if niche:
            niches = [niche]
        else:
            niches = list({
                n for (n,) in db.execute(
                    select(SwipeSource.niche).where(SwipeSource.enabled.is_(True))
                ) if n
            })
        reports = {n: refresh_niche(db, n, top_k).as_dict() for n in niches}
        return {"ok": True, "reports": reports}
    finally:
        if own_session:
            db.close()


@celery_app.task(name="research.refresh")
def research_refresh(niche: str | None = None, top_k: int | None = None) -> dict:
    return run_refresh(niche, top_k)
