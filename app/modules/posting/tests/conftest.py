"""Shared test fixtures for the posting module.

Runs entirely against the core's SQLite fallback engine with $0 fake providers
(DRY_RUN defaults True), so there is zero network and zero spend. Each test gets a
fresh Session; rows use fresh UUIDs so runs don't collide.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.db import SessionLocal, init_db
from app.core.models import (
    FormulaTemplate,
    HookTemplate,
    PacingTemplate,
    Product,
    VideoJob,
)
from app.core.state_machine import JobState


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    init_db()
    yield


@pytest.fixture
def session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def product(session):
    p = Product(source_url=f"https://shop.example/{uuid.uuid4()}")
    session.add(p)
    session.flush()
    return p


def make_hook(session, name: str, pattern: str, score: float | None = None) -> HookTemplate:
    h = HookTemplate(
        name=name, pattern_th=pattern, hook_type="curiosity", operator_win_score=score
    )
    session.add(h)
    session.flush()
    return h


def make_job(
    session,
    product,
    *,
    state: JobState = JobState.AWAITING_APPROVAL,
    draft_key: str | None = "media/final_captioned.mp4",
    hook=None,
    formula=None,
    pacing=None,
) -> VideoJob:
    job = VideoJob(
        product_id=product.id,
        state=state,
        draft_asset_key=draft_key,
        hook_template_id=hook.id if hook else None,
        formula_template_id=formula.id if formula else None,
        pacing_template_id=pacing.id if pacing else None,
    )
    session.add(job)
    session.flush()
    return job


@pytest.fixture
def green_compliance(monkeypatch):
    """Force the compliance hard gate to all-green (the real module may not exist yet)."""
    from app.modules.posting import compliance_gate

    monkeypatch.setattr(
        compliance_gate,
        "run_prepost_checklist",
        lambda job_id: {
            "passed": True,
            "checks": [{"id": "ai_label", "label": "AI label", "pass": True}],
        },
    )
    return True
