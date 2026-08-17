"""§3B/§3D render pipeline integration tests (all $0, fake providers)."""

from __future__ import annotations

import uuid

from app.core.models import CostLedgerEntry, MediaAsset
from app.core.state_machine import JobState
from app.modules.generation import pipeline, scripting
from app.modules.generation.constants import (
    KIND_HERO_IMAGE,
    KIND_I2V,
    MEDIA_HERO_IMAGE,
)
from app.modules.generation.tests.conftest import make_job

PRODUCT = {
    "title_th": "ลิปเซรั่ม",
    "brand": "XYZ",
    "attributes": [{"key": "finish", "value": "แมตต์"}],
    "approved_claims": [],
    "images": [{"url": "file:///media/p1.jpg", "is_primary": True}],
}
INV = scripting.build_script_input(product=PRODUCT)["global_invariants"]


def _script():
    si = scripting.build_script_input(product=PRODUCT)
    script, errors, _ = scripting.generate_script(video_job_id=str(uuid.uuid4()), script_input=si)
    assert errors == []
    return script


def _render(db, product, *, options=None):
    job = make_job(db, product, state=JobState.GENERATING, budget=50.0)
    script = _script()
    result = pipeline.render_video(
        db, job, script=script, product=PRODUCT, invariants=INV,
        avatar_id="heygen-xyz", voice_id="eleven-xyz",
        options={**(options or {}), "poll_sleep": 0.0},
    )
    return job, script, result


def test_faceless_all_scenes_broll(db, product):
    # Faceless: no avatar lane; every scene is generated b-roll across all roles.
    _, _, result = _render(db, product)
    assert result.avatar_assets == []
    for a in result.broll_assets:
        assert (a.meta or {}).get("role") in {"HOOK", "DEMO", "PROOF", "CTA"}
    assert result.hero_asset is not None
    assert result.vo_track_asset is not None
    assert result.all_ready is True


def test_hero_image_reused_across_broll_scenes(db, product):
    db_job, _, result = _render(db, product)
    heroes = db.query(MediaAsset).filter(
        MediaAsset.video_job_id == db_job.id, MediaAsset.role == MEDIA_HERO_IMAGE
    ).all()
    assert len(heroes) == 1  # one locked hero, reused (§3D.2)
    hero_costs = db.query(CostLedgerEntry).filter(
        CostLedgerEntry.video_job_id == db_job.id, CostLedgerEntry.kind == KIND_HERO_IMAGE
    ).count()
    assert hero_costs == 1


def test_reroll_on_low_similarity_then_accept(db, product):
    # First i2v attempt on the DEMO scene (order 1) fails QA, reroll succeeds.
    job, _, result = _render(db, product, options={"qa_similarities": {"1": [0.50, 0.95]}})
    assert result.reroll_count >= 1
    assert result.all_ready is True
    assert 0.0 < result.reroll_rate <= 1.0


def test_reroll_cap_routes_to_operator_gate(db, product):
    # Every attempt on the DEMO scene fails QA → exhaust rerolls → halt.
    job, _, result = _render(db, product, options={"qa_similarities": {"1": [0.1, 0.1, 0.1, 0.1, 0.1]}})
    assert result.halted is True
    assert result.blocked_scene_ids
    assert result.all_ready is False


def test_duplicate_finalize_is_idempotent(db, product):
    job = make_job(db, product, state=JobState.GENERATING, budget=50.0)
    script = _script()
    broll_scene = next(s for s in script["scenes"] if s["asset_type"] == "BROLL")
    hero = pipeline.generate_hero_image(db, job, product=PRODUCT, invariants=INV)

    clip, attempt = pipeline._submit_i2v(
        db, job, broll_scene, hero, attempt_n=1, model="kling", is_reroll=False,
    )
    provider = pipeline.registry.get_video_gen_provider()
    poll = provider.poll(provider_job_id=attempt.request_id)
    # Webhook + poll both land on the same finaliser.
    pipeline._finalize_media(clip, attempt, poll)
    pipeline._finalize_media(clip, attempt, poll)

    ready = db.query(MediaAsset).filter(
        MediaAsset.video_job_id == job.id, MediaAsset.idempotency_key == clip.idempotency_key
    ).all()
    assert len(ready) == 1 and ready[0].status == "ready"
    i2v_costs = db.query(CostLedgerEntry).filter(
        CostLedgerEntry.video_job_id == job.id, CostLedgerEntry.kind == KIND_I2V
    ).count()
    assert i2v_costs == 1  # billed once despite duplicate delivery


def test_resubmit_same_key_does_not_double_charge(db, product):
    job = make_job(db, product, state=JobState.GENERATING, budget=50.0)
    script = _script()
    broll_scene = next(s for s in script["scenes"] if s["asset_type"] == "BROLL")
    hero = pipeline.generate_hero_image(db, job, product=PRODUCT, invariants=INV)

    pipeline._submit_i2v(db, job, broll_scene, hero, attempt_n=1, model="kling", is_reroll=False)
    pipeline._submit_i2v(db, job, broll_scene, hero, attempt_n=1, model="kling", is_reroll=False)
    i2v_costs = db.query(CostLedgerEntry).filter(
        CostLedgerEntry.video_job_id == job.id, CostLedgerEntry.kind == KIND_I2V
    ).count()
    assert i2v_costs == 1
