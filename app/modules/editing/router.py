"""Editing module router — mounted at ``/api/editing`` by ``app.main.load_modules()``.

Read/QA + trigger surface for the editing stage. State changes go only through
``transition()`` (in the worker); these endpoints inspect config/plan and (re)enqueue the
``editing.run`` task. Heavy render deps are imported lazily inside handlers.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.models import VideoJob
from app.core.queue import celery_app
from app.core.state_machine import JobState

from .config import CONFIG

router = APIRouter(prefix="/api/editing", tags=["editing"])


@router.get("/health")
def editing_health() -> dict:
    """Prove the module mounted + surface the render/caption config (§4E)."""
    return {
        "module": "editing",
        "ok": True,
        "dry_run": settings.DRY_RUN,
        "resolution": f"{CONFIG.render.width}x{CONFIG.render.height}",
        "fps": CONFIG.render.fps,
        "captions_renderer": CONFIG.caption.renderer,
        "font": CONFIG.caption.font,
        "disclosure_in_base": CONFIG.disclosure.in_base,
        "max_avg_cut_ms": CONFIG.pacing.max_avg_cut_ms,
    }


@router.get("/config")
def editing_config() -> dict:
    """Full effective editing configuration (§4E)."""
    return {
        "render": asdict(CONFIG.render),
        "caption": asdict(CONFIG.caption),
        "disclosure": {**asdict(CONFIG.disclosure),
                       "window_s": list(CONFIG.disclosure.window_s)},
        "pacing": asdict(CONFIG.pacing),
    }


@router.get("/jobs/{job_id}/plan")
def job_plan(job_id: str) -> dict:
    """Compute + return the render plan (EDL) for a job without rendering (QA / preview)."""
    from .worker import resolve_job_spec
    from .edl import build_edl

    db: Session = SessionLocal()
    try:
        job = db.get(VideoJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        try:
            spec = resolve_job_spec(db, job)
            edl = build_edl(spec)
        except Exception as exc:  # noqa: BLE001 — planning errors are 422, not 500
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "job_id": str(job.id),
            "shot_count": edl.shot_count,
            "avg_cut_ms": round(edl.avg_cut_ms(), 1),
            "bpm": edl.bpm,
            "total_duration_s": round(edl.total_duration_s(), 3),
            "hook_first": edl.shots[0].is_hook if edl.shots else False,
            "shots": edl.as_dict()["shots"],
        }
    finally:
        db.close()


@router.post("/jobs/{job_id}/render")
def trigger_render(job_id: str) -> dict:
    """(Re)enqueue ``editing.run`` for a job currently in EDITING (manual QA trigger)."""
    db: Session = SessionLocal()
    try:
        job = db.get(VideoJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        state = job.state if isinstance(job.state, JobState) else JobState(job.state)
        if state != JobState.EDITING:
            raise HTTPException(
                status_code=409,
                detail=f"job must be EDITING to render, is {state.value}",
            )
    finally:
        db.close()
    try:
        celery_app.send_task("editing.run", kwargs={"job_id": str(job_id)})
    except Exception:  # noqa: BLE001 — broker may be absent in local/skeleton runs
        pass
    return {"ok": True, "job_id": str(job_id), "enqueued": "editing.run"}
