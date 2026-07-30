from __future__ import annotations

from sqlalchemy import select

from app.core.models import CostLedgerEntry, Product, SwipeSource, VideoJob
from app.core.state_machine import JobState
from app.modules.research.swipe import service
from app.modules.research.tasks import run_research


def _make_job(db, url="https://shop.myshopify.com/products/serum"):
    p = Product(source_url=url)
    db.add(p)
    db.flush()
    job = VideoJob(product_id=p.id, state=JobState.QUEUED)
    db.add(job)
    db.commit()
    return job


def test_research_run_advances_state_and_meters_cost(db):
    job = _make_job(db)
    out = run_research(str(job.id), session=db)
    assert out["ok"] is True
    db.refresh(job)
    assert job.state == JobState.SCRIPTING
    assert job.last_completed_stage == "research"
    # scrape cost metered into the ledger + accrued bumped
    ledger = list(db.scalars(select(CostLedgerEntry).where(CostLedgerEntry.video_job_id == job.id)))
    assert ledger and ledger[0].stage == "research"
    assert float(job.cost_accrued_usd) > 0


def test_research_run_links_warm_templates(db):
    # warm the library for the category the fake product resolves to ("misc")
    db.add(SwipeSource(type="account", handle="@x", niche="misc", enabled=True))
    db.commit()
    service.refresh_niche(db, "misc", top_k=5)

    job = _make_job(db)
    out = run_research(str(job.id), session=db)
    db.refresh(job)
    assert out["ok"] is True
    # at least one template linked for the resolved niche
    assert job.formula_template_id is not None or job.hook_template_id is not None


def test_research_run_fails_gracefully_without_url(db):
    p = Product(source_url="")
    db.add(p)
    db.flush()
    job = VideoJob(product_id=p.id, state=JobState.QUEUED)
    db.add(job)
    db.commit()
    out = run_research(str(job.id), session=db)
    assert out["ok"] is False
    db.refresh(job)
    assert job.state == JobState.FAILED
    assert job.failure_reason
