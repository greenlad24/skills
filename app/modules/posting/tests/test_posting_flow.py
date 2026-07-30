"""Posting flow tests using the fake provider — no network, no spend (spec §5A / §5E)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.core.state_machine import JobState
from app.modules.posting import ingest as ingest_mod
from app.modules.posting import service
from app.modules.posting.tests.conftest import make_hook, make_job


# --------------------------------------------------------------------------- #
# Plan building / disclosure rules (§5A.4)
# --------------------------------------------------------------------------- #
def test_is_ai_generated_always_true():
    job = SimpleNamespace(id=uuid.uuid4(), draft_asset_key="k")
    plan = service.build_post_plan(job, {"caption": "hi", "hashtags": ["a"]})
    assert plan.is_ai_generated is True
    assert plan.ai_disclosure_master is True


def test_branded_content_self_only_rejected():
    job = SimpleNamespace(id=uuid.uuid4(), draft_asset_key="k")
    with pytest.raises(service.PostingError) as ei:
        service.build_post_plan(
            job,
            {"disclose_branded_content": True, "visibility": service.VIS_PRIVATE},
        )
    assert ei.value.status_code == 422


def test_unaudited_public_downgrades_to_private():
    job = SimpleNamespace(id=uuid.uuid4(), draft_asset_key="k")
    plan = service.build_post_plan(
        job, {"visibility": service.VIS_PUBLIC, "audited": False}
    )
    assert plan.visibility == service.VIS_PRIVATE  # honest constraint #1


def test_audited_public_allowed():
    job = SimpleNamespace(id=uuid.uuid4(), draft_asset_key="k")
    plan = service.build_post_plan(
        job, {"visibility": service.VIS_PUBLIC, "audited": True}
    )
    assert plan.visibility == service.VIS_PUBLIC


def test_full_caption_merges_hashtags_and_caps_length():
    plan = service.PostPlan(
        account_ref="a", video_key="k", caption="buy this", hashtags=["deal", "#sale"]
    )
    cap = plan.full_caption()
    assert "#deal" in cap and "#sale" in cap
    assert len(cap) <= 2200


# --------------------------------------------------------------------------- #
# Approval gate (§5A.1) — compliance hard gate + human-only transition
# --------------------------------------------------------------------------- #
def test_approve_blocks_when_compliance_not_green(session, product, monkeypatch):
    from app.modules.posting import compliance_gate

    monkeypatch.setattr(
        compliance_gate, "run_prepost_checklist",
        lambda job_id: {"passed": False, "checks": [{"id": "x", "pass": False}]},
    )
    job = make_job(session, product)
    with pytest.raises(service.ComplianceNotGreenError):
        service.approve(session, str(job.id), {"caption": "hi"})
    # job never left the gate
    session.refresh(job)
    assert JobState(job.state) is JobState.AWAITING_APPROVAL


def test_approve_requires_awaiting_approval(session, product, green_compliance):
    job = make_job(session, product, state=JobState.POSTED)
    with pytest.raises(service.PostingError) as ei:
        service.approve(session, str(job.id), {"caption": "hi"})
    assert ei.value.status_code == 409


def test_run_posting_refuses_unapproved_job(session, product, green_compliance):
    # A job sitting in POSTING but never human-approved (approved_at is None).
    job = make_job(session, product, state=JobState.POSTING)
    out = service.run_posting(session, str(job.id))
    assert out["state"] == JobState.FAILED.value
    assert "not human-approved" in out["error"]


# --------------------------------------------------------------------------- #
# Happy path: approve -> post via fake provider -> shop-tag reminder -> tagged
# --------------------------------------------------------------------------- #
def test_happy_path_publish_and_tag(session, product, green_compliance):
    hook = make_hook(session, "h", "unique opening line for the win", 0.5)
    job = make_job(session, product, hook=hook)

    approve_out = service.approve(session, str(job.id), {
        "caption": "great product", "hashtags": ["fyp"],
        "disclose_your_brand": True,
    })
    assert approve_out["state"] == JobState.POSTING.value

    post_out = service.run_posting(session, str(job.id))
    assert post_out["state"] == JobState.POSTED.value
    assert post_out["post_url"]
    # shop-tag reminder present, tag still PENDING (manual step)
    reminder = post_out["shop_tag_reminder"]
    assert reminder["shop_tag_status"] == service.TAG_PENDING
    assert reminder["product_tag_attached"] is False
    assert reminder["deep_link"]

    session.refresh(job)
    post = job.post
    assert post.status == service.ST_PUBLISHED
    assert post.tiktok_video_id
    assert post.posted_at is not None
    assert post.ai_disclosure_set is True
    assert post.is_ai_generated is True

    # operator marks the manual product tag done
    tagged = service.mark_tagged(session, str(job.id))
    assert tagged["tagged"] is True
    session.refresh(post)
    assert post.product_tag_attached is True
    assert post.shop_tag_status == service.TAG_TAGGED


# --------------------------------------------------------------------------- #
# End-to-end winner loop: approve -> post -> ingest -> reweight (§5E)
# --------------------------------------------------------------------------- #
def test_ingest_reweights_template_weight(session, product, green_compliance):
    hook = make_hook(session, "h2", "another unique opening hook line", 0.5)
    before = hook.operator_win_score
    job = make_job(session, product, hook=hook)

    service.approve(session, str(job.id), {"caption": "c", "hashtags": ["x"]})
    service.run_posting(session, str(job.id))

    result = ingest_mod.ingest_daily(session)
    assert result["ingested"] >= 1
    assert result["attributed"] >= 1

    session.refresh(hook)
    # a PerformanceRecord was scored and attributed back to the hook's weight
    assert hook.operator_win_score is not None
    assert hook.operator_win_score != before

    post = job.post
    assert post.latest_score is not None

    # idempotent same-day re-run does not duplicate the day's record
    from app.core.models import PerformanceRecord
    from sqlalchemy import select

    n1 = len(session.execute(
        select(PerformanceRecord).where(PerformanceRecord.post_id == post.id)
    ).scalars().all())
    ingest_mod.ingest_daily(session)
    n2 = len(session.execute(
        select(PerformanceRecord).where(PerformanceRecord.post_id == post.id)
    ).scalars().all())
    assert n2 == n1  # upsert, not duplicate
