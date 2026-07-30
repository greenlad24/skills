"""End-to-end generation-stage tests (§3A + §3D) via service.run_generation."""

from __future__ import annotations

from app.core.models import MediaAsset, Script
from app.core.state_machine import JobState
from app.modules.generation import service
from app.modules.generation.tests.conftest import make_job


def test_happy_path_scripting_to_editing(db, product, persona):
    job = make_job(
        db, product, state=JobState.SCRIPTING, budget=50.0,
        avatar=persona.avatar, voice=persona.voice_profile,
    )
    outcome = service.run_generation(job.id, db=db, options={"poll_sleep": 0.0}, enqueue_next=False)

    assert outcome.state == JobState.EDITING.value
    assert outcome.script_passed_claims is True
    assert outcome.halted is False
    # Script persisted + scene assets produced.
    assert db.query(Script).filter(Script.video_job_id == job.id).count() == 1
    assets = db.query(MediaAsset).filter(MediaAsset.video_job_id == job.id).all()
    roles = {a.role for a in assets}
    assert "avatar_clip" in roles
    assert "broll" in roles
    assert "hero_image" in roles
    assert "vo_track" in roles  # clean Thai VO track handed to editing
    assert job.last_completed_stage == "generation"
    assert outcome.cost_usd > 0


def test_claim_failure_routes_to_failed_no_media(db, product, persona):
    job = make_job(
        db, product, state=JobState.SCRIPTING, budget=50.0,
        avatar=persona.avatar, voice=persona.voice_profile,
    )
    # Inject an unauthorized whitening + superlative claim; persists across retry.
    outcome = service.run_generation(
        job.id, db=db,
        forced_narration={"0": "ครีมนี้ผิวขาวขึ้น ดีที่สุดในไทย"},
        options={"poll_sleep": 0.0}, enqueue_next=False,
    )
    assert outcome.state == JobState.FAILED.value
    assert outcome.script_passed_claims is False
    # Fail-closed: NO media generated for a script that fails the gate.
    assert db.query(MediaAsset).filter(MediaAsset.video_job_id == job.id).count() == 0


def test_budget_breach_halts_to_operator_gate(db, product, persona):
    # A tiny budget cannot fund the render → halt (FAILED), never assembly.
    job = make_job(
        db, product, state=JobState.SCRIPTING, budget=0.05,
        avatar=persona.avatar, voice=persona.voice_profile,
    )
    outcome = service.run_generation(job.id, db=db, options={"poll_sleep": 0.0}, enqueue_next=False)
    assert outcome.halted is True
    assert outcome.state == JobState.FAILED.value


def test_avatar_voice_reused_across_two_jobs(db, product, persona):
    # Two jobs, same persona → no new Avatar/VoiceProfile created (§3C reuse).
    from app.core.models import Avatar, VoiceProfile

    before_avatars = db.query(Avatar).count()
    before_voices = db.query(VoiceProfile).count()

    for _ in range(2):
        job = make_job(
            db, product, state=JobState.SCRIPTING, budget=50.0,
            avatar=persona.avatar, voice=persona.voice_profile,
        )
        outcome = service.run_generation(job.id, db=db, options={"poll_sleep": 0.0}, enqueue_next=False)
        assert outcome.state == JobState.EDITING.value

    assert db.query(Avatar).count() == before_avatars
    assert db.query(VoiceProfile).count() == before_voices


def test_revoked_consent_blocks_job(db, product, persona):
    from app.modules.generation import setup_service

    setup_service.revoke_consent(db, avatar=persona.avatar)
    db.flush()
    job = make_job(
        db, product, state=JobState.SCRIPTING, budget=50.0,
        avatar=persona.avatar, voice=persona.voice_profile,
    )
    outcome = service.run_generation(job.id, db=db, options={"poll_sleep": 0.0}, enqueue_next=False)
    assert outcome.state == JobState.FAILED.value
    assert "consent" in (outcome.reason or "").lower()
