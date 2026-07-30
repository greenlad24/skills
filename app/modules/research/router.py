"""Research module HTTP surface — mounted at /api/research by app.main.load_modules().

Covers the research-owned slices of the Setup / Library API (§7A.10):
  * swipe-source management (seed/operator lists),
  * swipe-library template reads,
  * an on-demand product-research preview and a swipe-refresh trigger.

Everything honors DRY_RUN (fake providers, $0) and drives no job state directly.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.models import SwipeSource, SwipeVideo
from app.core.queue import celery_app

from .models import create_research_tables
from .product.service import research_product
from .swipe.service import get_templates

router = APIRouter(prefix="/api/research", tags=["research"])


# --------------------------------------------------------------------------- #
# Schemas (module-local API I/O)
# --------------------------------------------------------------------------- #
class SourceCreate(BaseModel):
    type: Literal["account", "hashtag", "keyword"]
    handle: str
    niche: str
    enabled: bool = True
    added_by: Literal["seed", "operator", "auto_discovered"] = "operator"


class SourceOut(BaseModel):
    id: uuid.UUID
    type: str | None = None
    handle: str | None = None
    niche: str | None = None
    enabled: bool = True
    added_by: str | None = None

    model_config = {"from_attributes": True}


class SourceToggle(BaseModel):
    enabled: bool


class ProductPreviewRequest(BaseModel):
    url: str
    job_id: str | None = None


class TemplateOut(BaseModel):
    id: uuid.UUID
    name: str | None = None
    proxy_score: float | None = None
    operator_win_score: float | None = None
    signal_type: str = "engagement_proxy"

    model_config = {"from_attributes": True}


# --------------------------------------------------------------------------- #
# Health / ping
# --------------------------------------------------------------------------- #
@router.get("/ping")
def ping() -> dict:
    return {"module": "research", "ok": True, "dry_run": settings.DRY_RUN}


# --------------------------------------------------------------------------- #
# Setup: swipe sources
# --------------------------------------------------------------------------- #
@router.get("/sources", response_model=list[SourceOut])
def list_sources(niche: str | None = None, db: Session = Depends(get_db)) -> list[SwipeSource]:
    stmt = select(SwipeSource)
    if niche:
        stmt = stmt.where(SwipeSource.niche == niche)
    return list(db.scalars(stmt))


@router.post("/sources", response_model=SourceOut, status_code=201)
def create_source(body: SourceCreate, db: Session = Depends(get_db)) -> SwipeSource:
    src = SwipeSource(
        type=body.type, handle=body.handle, niche=body.niche,
        enabled=body.enabled, added_by=body.added_by,
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    return src


@router.patch("/sources/{source_id}", response_model=SourceOut)
def toggle_source(source_id: str, body: SourceToggle, db: Session = Depends(get_db)) -> SwipeSource:
    src = db.get(SwipeSource, source_id)
    if src is None:
        raise HTTPException(status_code=404, detail="source not found")
    src.enabled = body.enabled
    db.commit()
    db.refresh(src)
    return src


# --------------------------------------------------------------------------- #
# Library: swipe templates + videos
# --------------------------------------------------------------------------- #
@router.get("/templates", response_model=list[TemplateOut])
def templates(
    niche: str,
    kind: Literal["formula", "hook", "pacing"] = "formula",
    limit: int = 10,
    db: Session = Depends(get_db),
) -> list:
    create_research_tables()
    return get_templates(db, niche, kind, limit=limit)


@router.get("/swipe-videos")
def swipe_videos(niche: str | None = None, limit: int = 50, db: Session = Depends(get_db)) -> dict:
    stmt = select(SwipeVideo)
    if niche:
        stmt = stmt.where(SwipeVideo.niche == niche)
    rows = list(db.scalars(stmt.limit(limit)))
    return {
        "videos": [
            {
                "id": str(v.id), "tiktok_id": v.tiktok_id, "niche": v.niche,
                "author_handle": v.author_handle, "proxy_score": v.proxy_score,
                "operator_win_score": v.operator_win_score,
                "signal_type": v.signal_type,  # always engagement_proxy until §05
                "processed_stages": v.processed_stages,
            }
            for v in rows
        ]
    }


# --------------------------------------------------------------------------- #
# On-demand actions
# --------------------------------------------------------------------------- #
@router.post("/product-preview")
def product_preview(body: ProductPreviewRequest) -> dict:
    """Run product research for a URL WITHOUT creating a job (dashboard preview)."""
    res = research_product(body.url, body.job_id or "preview")
    p = res.product
    return {
        "product": p.as_dict(),
        "images_downloaded": res.images_downloaded,
        "needs_manual_images": res.needs_manual_images,
        "scrape_status": p.scrape_status,
    }


@router.post("/refresh")
def refresh(niche: str | None = None, top_k: int | None = None) -> dict:
    """Trigger a swipe-library refresh (nightly job's manual 'refresh now')."""
    try:
        celery_app.send_task("research.refresh", kwargs={"niche": niche, "top_k": top_k})
        enqueued = True
    except Exception:  # noqa: BLE001
        enqueued = False
    return {"enqueued": enqueued, "niche": niche}
