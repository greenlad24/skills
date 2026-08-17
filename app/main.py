"""FastAPI application: health, the core jobs router, and the dynamic module loader.

The module loader is the plug-in seam: on startup it imports every
`app/modules/<name>/router.py` and, if that module exposes `router: APIRouter`,
includes it — so module agents add endpoints WITHOUT editing this file.
"""

from __future__ import annotations

import importlib
import pkgutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.core.adapters import registry
from app.core.config import settings
from app.core.db import get_db
from app.core.models import Product, VideoJob
from app.core.queue import celery_app
from app.core.schemas import (
    DecisionResponse,
    HealthResponse,
    Job,
    JobCreate,
    JobCreateResponse,
    ProviderHealth,
    RerollRequest,
)
from app.core.state_machine import (
    IllegalTransitionError,
    JobState,
    transition,
)

app = FastAPI(
    title="AutoUGC-TH",
    version=__version__,
    description="Local single-operator TikTok-Shop UGC video factory (P0 foundation).",
)

# Tracks which module packages were successfully mounted (surfaced on /health).
LOADED_MODULES: list[str] = []


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
@app.get("/health", response_model=HealthResponse, tags=["system"])
def health(db: Session = Depends(get_db)) -> HealthResponse:
    """Liveness + provider/DB/module readiness (§1.7 first-run health dashboard)."""
    mode = "fake" if settings.DRY_RUN else "real"
    providers = [
        ProviderHealth(provider=settings.LLM_PROVIDER, kind="llm", mode=mode),
        ProviderHealth(provider=settings.SCRAPER_PROVIDER, kind="scraper", mode=mode),
        ProviderHealth(provider=settings.TTS_PROVIDER, kind="tts", mode=mode),
        ProviderHealth(provider=settings.VIDEOGEN_PROVIDER, kind="videogen", mode=mode),
        ProviderHealth(provider=settings.POSTING_PROVIDER, kind="posting", mode=mode),
    ]

    db_status = "ok"
    try:
        db.execute(select(VideoJob.id).limit(1))
    except Exception:  # noqa: BLE001 — health must never raise
        db_status = "unavailable"

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        dry_run=settings.DRY_RUN,
        version=__version__,
        db=db_status,
        providers=providers,
        modules_loaded=list(LOADED_MODULES),
    )


# --------------------------------------------------------------------------- #
# Core jobs router (skeleton — the pipeline stages live in modules)
# --------------------------------------------------------------------------- #
jobs_router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _to_job_schema(job: VideoJob) -> Job:
    product_title = job.product.title if job.product else None
    return Job(
        id=job.id,
        state=job.state if isinstance(job.state, JobState) else JobState(job.state),
        product=product_title,
        cost=float(job.cost_accrued_usd or 0),
        created_at=job.created_at,
        video_url=None,
        script=job.script.full_text if job.script else None,
        caption=None,
        hashtags=[],
    )


@jobs_router.post("", response_model=JobCreateResponse, status_code=201)
def create_job(body: JobCreate, db: Session = Depends(get_db)) -> JobCreateResponse:
    """Create a video job from a product URL and enqueue the research stage."""
    product = Product(source_url=body.product_url)
    db.add(product)
    db.flush()  # assign product.id

    job = VideoJob(
        product_id=product.id,
        avatar_id=body.avatar_id,
        state=JobState.QUEUED,
        cost_budget_usd=settings.PER_VIDEO_COST_BUDGET_USD,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Enqueue the first pipeline stage. The research module registers `research.run`;
    # if it isn't loaded yet, sending is a no-op broker publish (skeleton behavior).
    try:
        celery_app.send_task("research.run", kwargs={"job_id": str(job.id)})
    except Exception:  # noqa: BLE001 — broker may be absent in local/skeleton runs
        pass

    return JobCreateResponse(job_id=job.id, state=JobState.QUEUED)


@jobs_router.get("/{job_id}", response_model=Job)
def get_job(job_id: str, db: Session = Depends(get_db)) -> Job:
    """Full job status incl. artifacts/script (dashboard + approval screen)."""
    job = db.get(VideoJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _to_job_schema(job)


@jobs_router.post("/{job_id}/approve", response_model=DecisionResponse)
def approve_job(job_id: str, db: Session = Depends(get_db)) -> DecisionResponse:
    """The human gate → POSTING.

    NOTE: the compliance module enforces the all-green hard gate before this succeeds;
    in this skeleton the transition itself is validated by the state machine (a job must
    be AWAITING_APPROVAL). Returns 409 on an illegal transition.
    """
    job = db.get(VideoJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    try:
        transition(job, JobState.POSTING, by_human=True)
    except IllegalTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    job.approved_at = datetime.now(timezone.utc)
    job.decision = {"decision": "approve"}
    db.commit()

    try:
        celery_app.send_task("posting.run", kwargs={"job_id": str(job.id)})
    except Exception:  # noqa: BLE001
        pass
    return DecisionResponse(state=JobState.POSTING)


@jobs_router.post("/{job_id}/reroll", response_model=DecisionResponse)
def reroll_job(
    job_id: str, body: RerollRequest, db: Session = Depends(get_db)
) -> DecisionResponse:
    """Operator REJECT + re-cut notes → back to EDITING (cheap loop, no regen)."""
    job = db.get(VideoJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    from_state = job.state if isinstance(job.state, JobState) else JobState(job.state)
    try:
        transition(job, JobState.EDITING, by_human=True)
    except IllegalTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    job.decision = {"decision": "reroll", "stage": body.stage, "note": body.note}
    db.commit()

    try:
        celery_app.send_task("editing.run", kwargs={"job_id": str(job.id), "reroll": body.stage})
    except Exception:  # noqa: BLE001
        pass
    return DecisionResponse(state=JobState.EDITING, from_stage=from_state.value)


app.include_router(jobs_router)


# --------------------------------------------------------------------------- #
# Dynamic module loader
# --------------------------------------------------------------------------- #
def load_modules(target_app: FastAPI) -> list[str]:
    """Import every app/modules/<name>/router.py and include its `router` if present.

    This is the plug-in contract: a module agent creates `app/modules/<name>/router.py`
    exposing `router: APIRouter`, and it is mounted here automatically. Underscore-
    prefixed packages (e.g. `_example`) are included so stubs mount too. A module that
    fails to import is skipped (logged to stdout) rather than crashing the whole app.
    """
    loaded: list[str] = []
    modules_dir = Path(__file__).resolve().parent / "modules"
    if not modules_dir.is_dir():
        return loaded

    for finder in pkgutil.iter_modules([str(modules_dir)]):
        name = finder.name
        if name.startswith("__"):
            continue
        router_mod_path = f"app.modules.{name}.router"
        try:
            mod = importlib.import_module(router_mod_path)
        except ModuleNotFoundError:
            # Module has no router.py — that's allowed.
            continue
        except Exception as exc:  # noqa: BLE001 — one bad module must not sink the app
            print(f"[module-loader] failed to import {router_mod_path}: {exc}")
            continue

        router = getattr(mod, "router", None)
        if router is None:
            print(f"[module-loader] {router_mod_path} has no `router` — skipping")
            continue
        target_app.include_router(router)
        loaded.append(name)
        print(f"[module-loader] mounted module {name!r}")

    return loaded


# Load modules at import time so uvicorn picks them up on boot.
LOADED_MODULES.extend(load_modules(app))


# --------------------------------------------------------------------------- #
# Frontend (single-origin): serve the built React app so no Node is needed to run.
# Registered LAST so /health, /api/*, and every module router take precedence.
# --------------------------------------------------------------------------- #
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if (_FRONTEND_DIST / "index.html").is_file():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    _assets = _FRONTEND_DIST / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        """Serve a built static file if it exists, else index.html (SPA routing)."""
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file() and candidate.is_relative_to(_FRONTEND_DIST):
            return FileResponse(str(candidate))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
