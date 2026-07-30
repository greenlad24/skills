"""Compliance Celery tasks — autodiscovered by app.core.queue.

Namespaced task names so they don't collide across modules:
  * ``compliance.classify``  — run the §6B claim gate on a job's script, persist results.
  * ``compliance.checklist`` — run the §6D pre-post gate for a job, persist the result.

These are advisory hooks the script/editor stages call between SCRIPTING and rendering;
they never drive job state directly (the core approve endpoint reads the checklist).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.queue import celery_app


@celery_app.task(name="compliance.classify")
def classify_task(job_id: str, script: dict | None = None) -> dict[str, Any]:
    """Classify a script (passed inline or loaded from the job's Script row) and persist
    the claim-safety report + a ComplianceRecord envelope with per-claim decisions."""
    from app.core.db import SessionLocal
    from app.core.models import Script, VideoJob
    from app.modules.compliance.records import ClaimDecision, ComplianceLedger, persist_envelope
    from app.modules.compliance.service import classify_claims

    db = SessionLocal()
    try:
        job = db.get(VideoJob, job_id)
        if job is None:
            return {"ok": False, "error": "job not found"}

        if script is None and job.script is not None:
            script = {"full_text": job.script.full_text, "language": job.script.language}
        report = classify_claims(script or {})

        # Persist onto the Script row (claim_safety_passed / _report).
        if job.script is not None:
            job.script.claim_safety_passed = bool(report.get("allowed"))
            job.script.claim_safety_report = report

        # Build an append-only ComplianceRecord envelope with per-claim decisions.
        ledger = ComplianceLedger(
            str(job_id), script_hash=report.get("script_hash"),
            category=(script or {}).get("category"),
        )
        for flag in report.get("flags", []):
            from app.modules.compliance.common import sha256_hex
            ledger.add_claim_decision(ClaimDecision(
                segment_id=flag.get("segment_id", "seg"),
                text_hash=sha256_hex(flag.get("claim") or ""),
                claim_class=flag.get("type", "NEUTRAL"),
                final_decision=flag.get("decision", "BLOCK"),
                resolved=False,
                resolution="unresolved",
            ))
        persist_envelope(db, job.id, ledger)
        db.commit()
        return {"ok": True, "allowed": report.get("allowed"),
                "flags": len(report.get("flags", [])),
                "script_hash": report.get("script_hash")}
    finally:
        db.close()


@celery_app.task(name="compliance.checklist")
def checklist_task(job_id: str) -> dict[str, Any]:
    """Run the §6D pre-post checklist for a job and persist the aggregate result."""
    from app.core.db import SessionLocal
    from app.core.models import ComplianceRecord, VideoJob
    from app.modules.compliance.service import run_prepost_checklist

    db = SessionLocal()
    try:
        job = db.get(VideoJob, job_id)
        if job is None:
            return {"ok": False, "error": "job not found"}
        result = run_prepost_checklist(job_id)
        db.add(ComplianceRecord(
            video_job_id=job.id,
            check_type="checklist",
            passed=bool(result.get("passed")),
            detail=result,
            checked_at=datetime.now(timezone.utc),
        ))
        db.commit()
        return {"ok": True, "passed": result.get("passed")}
    finally:
        db.close()
