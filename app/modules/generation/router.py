"""Generation module HTTP surface (prefix ``/api/generation``).

Owns:
  * §3C one-time avatar/voice setup (idempotent).
  * §3A script preview / claim-gate dry-run.
  * generation status + asset listing for a job.

Mounted automatically by ``app.main.load_modules()``. All external calls go
through the adapter registry, so with ``DRY_RUN=true`` every endpoint is free.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.models import MediaAsset, VideoJob
from app.modules.generation import scripting, service, setup_service
from app.modules.generation.constants import MAX_REROLLS, QA_SIMILARITY_THRESHOLD

router = APIRouter(prefix="/api/generation", tags=["generation"])


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class SetupRequest(BaseModel):
    operator_label: str = Field(..., description="Idempotency key for the persona")
    consenter_name: str
    source_clip_key: str = Field(..., description="MinIO key of the consent talking clip")
    sample_audio_key: str = Field(..., description="MinIO key of the Thai voice sample")
    consent_scope: dict[str, Any] | None = None
    source_clip_sha256: str | None = None
    voice_provider: str | None = None


class PersonaResponse(BaseModel):
    created: bool
    avatar_id: uuid.UUID
    provider_avatar_id: str | None
    voice_profile_id: uuid.UUID
    provider_voice_id: str | None
    consent_record_id: uuid.UUID


class ScriptPreviewRequest(BaseModel):
    product: dict[str, Any] | None = None
    formula_template: dict[str, Any] | None = None
    hook_template: dict[str, Any] | None = None
    operator_flags: dict[str, Any] | None = None
    global_invariants: dict[str, Any] | None = None


class ScriptPreviewResponse(BaseModel):
    script: dict[str, Any]
    valid: bool
    validation_errors: list[str]
    claim_passed: bool


class GenerationInfoResponse(BaseModel):
    dry_run: bool
    max_rerolls: int
    qa_threshold: float
    per_video_budget_usd: float


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.get("/health", response_model=GenerationInfoResponse)
def health() -> GenerationInfoResponse:
    """Module readiness + the load-bearing tunables (§3D)."""
    return GenerationInfoResponse(
        dry_run=settings.DRY_RUN,
        max_rerolls=MAX_REROLLS,
        qa_threshold=QA_SIMILARITY_THRESHOLD,
        per_video_budget_usd=settings.PER_VIDEO_COST_BUDGET_USD,
    )


@router.post("/setup", response_model=PersonaResponse, status_code=201)
def setup_persona(body: SetupRequest, db: Session = Depends(get_db)) -> PersonaResponse:
    """One-time avatar/voice/consent setup (§3C). Idempotent per ``operator_label``."""
    try:
        result = setup_service.setup_persona(
            db,
            operator_label=body.operator_label,
            consenter_name=body.consenter_name,
            source_clip_key=body.source_clip_key,
            sample_audio_key=body.sample_audio_key,
            consent_scope=body.consent_scope,
            source_clip_sha256=body.source_clip_sha256,
            voice_provider=body.voice_provider,
        )
    except setup_service.ConsentRequiredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return PersonaResponse(
        created=result.created,
        avatar_id=result.avatar.id,
        provider_avatar_id=result.avatar.provider_avatar_id,
        voice_profile_id=result.voice_profile.id,
        provider_voice_id=result.voice_profile.provider_voice_id,
        consent_record_id=result.consent_record.id,
    )


@router.get("/setup/{operator_label}", response_model=PersonaResponse)
def get_persona(operator_label: str, db: Session = Depends(get_db)) -> PersonaResponse:
    """Return the existing persona for an operator label (404 if none)."""
    avatar = setup_service.find_active_persona(db, label=operator_label)
    if avatar is None:
        raise HTTPException(status_code=404, detail="no persona for that operator")
    from app.core.models import ConsentRecord, VoiceProfile

    voice = db.execute(
        select(VoiceProfile).where(VoiceProfile.label == operator_label)
        .order_by(VoiceProfile.created_at.desc())
    ).scalars().first()
    consent = db.execute(
        select(ConsentRecord).where(ConsentRecord.avatar_id == avatar.id)
        .order_by(ConsentRecord.created_at.desc())
    ).scalars().first()
    if voice is None or consent is None:
        raise HTTPException(status_code=404, detail="persona incomplete")
    return PersonaResponse(
        created=False,
        avatar_id=avatar.id,
        provider_avatar_id=avatar.provider_avatar_id,
        voice_profile_id=voice.id,
        provider_voice_id=voice.provider_voice_id,
        consent_record_id=consent.id,
    )


@router.post("/jobs/{job_id}/script/preview", response_model=ScriptPreviewResponse)
def preview_script(
    job_id: str, body: ScriptPreviewRequest, db: Session = Depends(get_db)
) -> ScriptPreviewResponse:
    """Generate + claim-gate a script WITHOUT persisting or rendering (§3A dry-run)."""
    job = db.get(VideoJob, job_id)
    if job is None and body.product is None:
        raise HTTPException(status_code=404, detail="job not found and no product supplied")

    product = body.product or (service._product_to_dict(job) if job else {})
    script_input = scripting.build_script_input(
        product=product,
        formula_template=body.formula_template,
        hook_template=body.hook_template,
        operator_flags=body.operator_flags,
        global_invariants=body.global_invariants or (
            service._derive_invariants(product) if product else None
        ),
    )
    script, errors, _ = scripting.generate_script(
        video_job_id=str(job_id), script_input=script_input,
    )
    claim_audit, _ = scripting.score_claims(
        script, script_input=script_input, idempotency_prefix=f"{job_id}:preview",
    )
    return ScriptPreviewResponse(
        script=script,
        valid=not errors,
        validation_errors=errors,
        claim_passed=bool(claim_audit["passed"]),
    )


class AssetOut(BaseModel):
    id: uuid.UUID
    role: str
    status: str
    storage_key: str | None = None
    mime_type: str | None = None
    duration_sec: float | None = None
    cost_usd: float | None = None


@router.get("/jobs/{job_id}/assets", response_model=list[AssetOut])
def list_assets(job_id: str, db: Session = Depends(get_db)) -> list[AssetOut]:
    """List the media assets produced for a job (avatar clips, b-roll, hero, VO)."""
    job = db.get(VideoJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    assets = db.execute(
        select(MediaAsset).where(MediaAsset.video_job_id == job.id)
        .order_by(MediaAsset.created_at)
    ).scalars().all()
    return [
        AssetOut(
            id=a.id, role=a.role, status=a.status, storage_key=a.storage_key,
            mime_type=a.mime_type,
            duration_sec=float(a.duration_sec) if a.duration_sec is not None else None,
            cost_usd=float(a.cost_usd) if a.cost_usd is not None else None,
        )
        for a in assets
    ]
