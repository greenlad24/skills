"""Posting module Celery tasks — autodiscovered by app.core.queue.

  * `posting.run`               — post one approved job (enqueued by the approve gate;
                                   this is the task name the core jobs router enqueues).
  * `posting.ingest_analytics`  — scheduled daily analytics ingestion + reweight.

Tasks own their own DB session (SessionLocal) — the FastAPI `get_db` dependency is
request-scoped and not available inside a worker.
"""

from __future__ import annotations

from typing import Any

from app.core.db import SessionLocal
from app.core.queue import celery_app
from app.modules.posting import ingest as ingest_mod
from app.modules.posting import service


@celery_app.task(name="posting.run")
def run(job_id: str) -> dict[str, Any]:
    """Post an APPROVED job (spec §5A.3). Refuses unless human-approved AND the
    compliance checklist is all-green; drives POSTING→POSTED on success, POSTING→
    FAILED otherwise."""
    session = SessionLocal()
    try:
        return service.run_posting(session, job_id)
    finally:
        session.close()


@celery_app.task(name="posting.ingest_analytics")
def ingest_analytics() -> dict[str, Any]:
    """Daily analytics ingestion + template reweight (spec §5B.5). Idempotent:
    same-day re-runs upsert PerformanceRecords rather than duplicating."""
    session = SessionLocal()
    try:
        return ingest_mod.ingest_daily(session)
    finally:
        session.close()


# Register the daily schedule on the shared Celery app without editing core.
# cron 03:00 UTC (spec §5B.5). Merges into any existing beat_schedule so we don't
# clobber another module's entries.
try:  # pragma: no cover - depends on celery beat config being mutable
    from celery.schedules import crontab

    _schedule = dict(getattr(celery_app.conf, "beat_schedule", None) or {})
    _schedule["posting-ingest-analytics-daily"] = {
        "task": "posting.ingest_analytics",
        "schedule": crontab(hour=3, minute=0),
    }
    celery_app.conf.beat_schedule = _schedule
except Exception:  # noqa: BLE001 — beat not always configured; scheduling is best-effort
    pass
