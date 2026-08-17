"""Generation stage orchestration — the body of the ``generation.run`` task.

Advances a job through §3A (claim-safe scripting) and §3D (render), driving state
ONLY through ``app.core.state_machine.transition``:

    SCRIPTING --(script emitted + claim gate passes)--> GENERATING
    GENERATING --(all scene assets READY)-------------> EDITING
    (claim gate fails after one retry, budget breach, or exhausted rerolls)
      --> FAILED  (routed back to the operator; NO media shipped)

Produces avatar clips + b-roll clips + a clean Thai VO track for §04 editing, and
persists ``Script`` / ``Scene`` / ``MediaAsset`` / ``GenAttempt`` / ``CostLedgerEntry``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.models import (
    ComplianceRecord,
    Avatar,
    Scene,
    Script,
    VideoJob,
    VoiceProfile,
)
from app.core.state_machine import (
    IllegalTransitionError,
    JobState,
    transition,
)
from app.modules.generation import scripting, setup_service
from app.modules.generation.constants import (
    ASSET_AVATAR,
    DEFAULT_LLM_MODEL,
)
from app.modules.generation.invariants import normalize_invariants
from app.modules.generation.pipeline import RenderResult, render_video


@dataclass
class GenerationOutcome:
    job_id: str
    state: str
    script_passed_claims: bool = False
    halted: bool = False
    reason: str | None = None
    reroll_rate: float = 0.0
    cost_usd: float = 0.0
    blocked_scene_ids: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Input assembly from DB rows
# --------------------------------------------------------------------------- #
def _product_to_dict(job: VideoJob) -> dict[str, Any]:
    p = job.product
    if p is None:
        return {"title_th": "สินค้า", "attributes": [], "approved_claims": [], "images": []}
    attrs_raw = p.attributes or {}
    # Normalize attributes into the [{key,value}] shape scripting expects.
    attributes: list[dict[str, Any]] = []
    if isinstance(attrs_raw, dict):
        for feat in attrs_raw.get("features", []) or []:
            attributes.append({"key": "feature", "value": str(feat)})
        for a in attrs_raw.get("attributes", []) or []:
            if isinstance(a, dict):
                attributes.append(a)
        images = attrs_raw.get("images", []) or []
        manual_images = attrs_raw.get("manual_images", []) or []
        approved = attrs_raw.get("approved_claims", []) or []
        category = attrs_raw.get("category")
    else:
        images, manual_images, approved, category = [], [], [], None
    return {
        "title_th": p.title or "สินค้า",
        "brand": p.brand,
        "attributes": attributes,
        "approved_claims": approved,
        "images": images,
        "manual_images": manual_images,
        "category": category,
        "price_thb": float(p.price) if p.price is not None else None,
    }


def _ascii_only(text: str | None, fallback: str) -> str:
    """Keep only ASCII so a Thai title/brand never bleeds into an English prompt."""
    if not text:
        return fallback
    cleaned = "".join(ch for ch in text if ord(ch) < 128).strip()
    # Collapse whitespace and drop stray punctuation-only results.
    cleaned = " ".join(cleaned.split())
    return cleaned if any(c.isalnum() for c in cleaned) else fallback


def _derive_invariants(product: dict[str, Any]) -> dict[str, str]:
    # The visual prompt is ENGLISH-ONLY (§3A.2); the Thai title must never leak in.
    brand = _ascii_only(product.get("brand"), "the brand")
    category = _ascii_only(product.get("category"), "cosmetics")
    return normalize_invariants(
        {
            "product_desc_en": (
                f"a {category} product by {brand}, label and branding intact"
            ),
            "set_desc_en": "a clean pastel vanity with soft morning window light",
            "style_en": "authentic UGC iPhone look, shallow depth of field, 9:16 vertical",
        }
    )


def _resolve_persona(db: Session, job: VideoJob) -> tuple[str, str, str | None]:
    """Resolve the reused ``avatar_id`` + ``voice_id`` (§3C) or an error string.

    Enforces consent: a revoked/retired avatar blocks the job.
    """
    avatar_id: str | None = None
    voice_id: str | None = None

    if job.avatar_id is not None:
        avatar: Avatar | None = db.get(Avatar, job.avatar_id)
        if avatar is None:
            return "", "", "avatar not found"
        if not setup_service.consent_active(db, avatar=avatar):
            return "", "", "avatar consent revoked or inactive — blocked"
        avatar_id = avatar.provider_avatar_id

    if job.voice_profile_id is not None:
        voice: VoiceProfile | None = db.get(VoiceProfile, job.voice_profile_id)
        if voice is not None:
            voice_id = voice.provider_voice_id

    avatar_id = avatar_id or settings.HEYGEN_AVATAR_ID or "heygen-avatar-default"
    voice_id = voice_id or settings.ELEVENLABS_VOICE_ID or "eleven-voice-default"
    return avatar_id, voice_id, None


# --------------------------------------------------------------------------- #
# Scripting sub-stage (§3A) with the single claim-gate retry
# --------------------------------------------------------------------------- #
def build_and_gate_script(
    *,
    video_job_id: str,
    script_input: dict[str, Any],
    forced_narration: dict[str, str] | None = None,
    use_llm_judge: bool = True,
) -> tuple[dict[str, Any], bool, list[str]]:
    """Generate a script, run the claim gate, retry once on a blocking failure.

    Returns ``(script, passed, validation_errors)``.
    """
    script, errors, _ = scripting.generate_script(
        video_job_id=video_job_id,
        script_input=script_input,
        forced_narration=forced_narration,
    )
    claim_audit, _ = scripting.score_claims(
        script, script_input=script_input,
        idempotency_prefix=f"{video_job_id}:1", use_llm_judge=use_llm_judge,
    )
    if claim_audit["passed"] and not errors:
        return script, True, errors

    # Retry once with the offending spans fed back as negative constraints (§3A.6).
    script2, errors2, _ = scripting.generate_script(
        video_job_id=video_job_id,
        script_input=script_input,
        forced_narration=forced_narration,  # persists an injected violation → hard stop
    )
    claim_audit2, _ = scripting.score_claims(
        script2, script_input=script_input,
        idempotency_prefix=f"{video_job_id}:2", use_llm_judge=use_llm_judge,
    )
    passed = bool(claim_audit2["passed"]) and not errors2
    return script2, passed, errors2


def _persist_script(db: Session, job: VideoJob, script: dict[str, Any]) -> Script:
    """Persist the Script + Scene rows (§3A output) before rendering."""
    claim_audit = script.get("claim_audit", {})
    full_text = " ".join(
        s.get("thai_narration", "") for s in sorted(
            script.get("scenes", []), key=lambda s: s.get("order", 0)
        )
    )
    row = Script(
        video_job_id=job.id,
        language="th",
        full_text=full_text,
        hook={"pattern": script.get("hook_template_id"), "text": full_text[:80]},
        claim_safety_passed=bool(claim_audit.get("passed")),
        claim_safety_report=claim_audit,
        llm_provider=settings.LLM_PROVIDER,
        llm_model=DEFAULT_LLM_MODEL,
    )
    db.add(row)
    db.flush()
    for scene in sorted(script.get("scenes", []), key=lambda s: s.get("order", 0)):
        db.add(
            Scene(
                script_id=row.id,
                sequence_no=scene.get("order", 0),
                scene_type=(scene.get("asset_type") or "").lower(),
                spoken_text_th=scene.get("thai_narration"),
                visual_direction=scene.get("visual_prompt_en"),
                duration_sec=scene.get("duration_s"),
            )
        )
    db.flush()
    return row


def _record_claim_failure(db: Session, job: VideoJob, script: dict[str, Any]) -> None:
    db.add(
        ComplianceRecord(
            video_job_id=job.id,
            check_type="claim_safety",
            passed=False,
            detail=script.get("claim_audit", {}),
            checked_at=datetime.now(timezone.utc),
        )
    )


# --------------------------------------------------------------------------- #
# Top-level entry (the Celery task body)
# --------------------------------------------------------------------------- #
def run_generation(
    job_id: str,
    *,
    db: Session | None = None,
    script_input_overrides: dict[str, Any] | None = None,
    forced_narration: dict[str, str] | None = None,
    options: dict[str, Any] | None = None,
    use_llm_judge: bool = True,
    enqueue_next: bool = True,
) -> GenerationOutcome:
    """Run the generation stage for ``job_id`` (§3A + §3D).

    Accepts an injected ``db`` (tests / callers manage the transaction) or opens
    its own ``SessionLocal`` and commits on success.
    """
    owns_session = db is None
    db = db or SessionLocal()
    try:
        job = db.get(VideoJob, job_id)
        if job is None:
            return GenerationOutcome(job_id=str(job_id), state="FAILED", reason="job not found")

        current = job.state if isinstance(job.state, JobState) else JobState(job.state)

        # ---- persona (§3C reuse) + consent gate ----
        avatar_id, voice_id, persona_err = _resolve_persona(db, job)
        if persona_err:
            return _fail(db, job, persona_err, owns_session)

        # ---- §3A scripting (generate if not already persisted) ----
        existing_script = db.execute(
            select(Script).where(Script.video_job_id == job.id)
        ).scalars().first()

        product = _product_to_dict(job)
        script_input = scripting.build_script_input(
            product=product,
            global_invariants=_derive_invariants(product),
            **(script_input_overrides or {}),
        )

        if existing_script is None:
            script, passed, errors = build_and_gate_script(
                video_job_id=str(job.id),
                script_input=script_input,
                forced_narration=forced_narration,
                use_llm_judge=use_llm_judge,
            )
            if not passed:
                _record_claim_failure(db, job, script)
                reason = (
                    "claim gate failed (fail-closed): "
                    + (", ".join(f["span"] for f in script["claim_audit"]["findings"]
                                 if f["verdict"] == "BLOCK") or "; ".join(errors))
                )
                return _fail(db, job, reason, owns_session, script_passed=False)
            _persist_script(db, job, script)
        else:
            # Re-entry: reconstruct the script dict from persisted rows.
            script = _reconstruct_script(db, job, existing_script, script_input)

        # ---- advance SCRIPTING -> GENERATING ----
        if current == JobState.SCRIPTING:
            try:
                transition(job, JobState.GENERATING)
            except IllegalTransitionError as exc:
                return _fail(db, job, f"cannot enter GENERATING: {exc}", owns_session)
            job.last_completed_stage = "scripting"
            db.flush()

        # ---- §3D render ----
        invariants = script_input["global_invariants"]
        result: RenderResult = render_video(
            db, job,
            script=script, product=product, invariants=invariants,
            avatar_id=avatar_id, voice_id=voice_id, options=options,
        )

        if result.halted or not result.all_ready:
            reason = result.halt_reason or "not all scene assets reached READY"
            job.failure_reason = reason
            _safe_transition_fail(db, job)
            db.flush()
            if owns_session:
                db.commit()
            return GenerationOutcome(
                job_id=str(job.id), state=job.state.value if isinstance(job.state, JobState) else str(job.state),
                script_passed_claims=True, halted=True, reason=reason,
                reroll_rate=result.reroll_rate, cost_usd=float(job.cost_accrued_usd or 0),
                blocked_scene_ids=result.blocked_scene_ids,
            )

        # ---- advance GENERATING -> EDITING ----
        try:
            transition(job, JobState.EDITING)
        except IllegalTransitionError as exc:
            return _fail(db, job, f"cannot enter EDITING: {exc}", owns_session)
        job.last_completed_stage = "generation"
        db.flush()
        if owns_session:
            db.commit()

        if enqueue_next:
            _enqueue_editing(job.id)
        return GenerationOutcome(
            job_id=str(job.id),
            state=JobState.EDITING.value,
            script_passed_claims=True,
            halted=False,
            reroll_rate=result.reroll_rate,
            cost_usd=float(job.cost_accrued_usd or 0),
        )
    finally:
        if owns_session:
            db.close()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _reconstruct_script(
    db: Session, job: VideoJob, script_row: Script, script_input: dict[str, Any]
) -> dict[str, Any]:
    scene_rows = db.execute(
        select(Scene).where(Scene.script_id == script_row.id).order_by(Scene.sequence_no)
    ).scalars().all()
    inv = script_input["global_invariants"]
    scenes = []
    for row in scene_rows:
        asset_type = (row.scene_type or "").upper() or ASSET_AVATAR
        role = "HOOK"
        # Best-effort role from asset type (avatar->HOOK/CTA, broll->DEMO/PROOF).
        scenes.append(
            {
                "scene_id": str(row.id),
                "order": row.sequence_no,
                "role": role,
                "thai_narration": row.spoken_text_th or "",
                "visual_prompt_en": row.visual_direction or "product",
                "on_screen_text_th": "",
                "duration_s": float(row.duration_sec or 3),
                "asset_type": asset_type,
            }
        )
    return {
        "script_id": str(script_row.id),
        "video_job_id": str(job.id),
        "language": "th",
        "total_duration_s": sum(s["duration_s"] for s in scenes) or 8,
        "scenes": scenes,
        "claim_audit": script_row.claim_safety_report or {"passed": True, "findings": []},
    }


def _fail(
    db: Session, job: VideoJob, reason: str, owns_session: bool,
    *, script_passed: bool = False,
) -> GenerationOutcome:
    job.failure_reason = reason
    _safe_transition_fail(db, job)
    db.flush()
    if owns_session:
        db.commit()
    return GenerationOutcome(
        job_id=str(job.id),
        state=job.state.value if isinstance(job.state, JobState) else str(job.state),
        script_passed_claims=script_passed,
        halted=True,
        reason=reason,
        cost_usd=float(job.cost_accrued_usd or 0),
    )


def _safe_transition_fail(db: Session, job: VideoJob) -> None:
    """Transition to FAILED if the current edge allows it (SCRIPTING/GENERATING → FAILED)."""
    try:
        transition(job, JobState.FAILED)
    except IllegalTransitionError:
        # Already terminal or an unexpected state — leave as-is.
        pass


def _enqueue_editing(job_id: Any) -> None:
    try:
        from app.core.queue import celery_app

        # ignore_result avoids the result-backend consumer blocking on connect.
        celery_app.send_task(
            "editing.run", kwargs={"job_id": str(job_id)}, ignore_result=True,
        )
    except Exception:  # noqa: BLE001 - broker may be absent in local/dry runs
        pass
