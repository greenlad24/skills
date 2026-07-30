"""§3D.5 QA gate + §3D.7 cost/budget tests."""

from __future__ import annotations

from app.modules.generation import cost, qa
from app.modules.generation.constants import KIND_I2V


# --------------------------------------------------------------------------- #
# QA gate
# --------------------------------------------------------------------------- #
def test_qa_accepts_above_threshold():
    result = qa.evaluate({"image_key": "hero"}, {"qa_similarity": 0.92}, threshold=0.85)
    assert result.accepted is True
    assert result.similarity == 0.92


def test_qa_rejects_below_threshold():
    result = qa.evaluate({"image_key": "hero"}, {"qa_similarity": 0.60}, threshold=0.85)
    assert result.accepted is False
    assert "similarity" in result.reason


def test_qa_rejects_on_checklist_failure():
    clip = {"qa_similarity": 0.99, "checklist": {"label_stable": False}}
    result = qa.evaluate({}, clip, threshold=0.85)
    assert result.accepted is False
    assert "label_stable" in result.checklist_failures


def test_default_dry_run_similarity_passes():
    # Fake clips are conditioned on the hero → deterministic default clears 0.85.
    result = qa.evaluate({"image_key": "hero-x"}, {"video_key": "broll-x"}, threshold=0.85)
    assert result.accepted is True


def test_reroll_rate():
    assert qa.reroll_rate(1, 4) == 0.25
    assert qa.reroll_rate(0, 0) == 0.0


# --------------------------------------------------------------------------- #
# Cost + budget guard
# --------------------------------------------------------------------------- #
def test_record_bumps_accrued(db):
    from app.core.models import CostLedgerEntry
    from app.modules.generation.tests.conftest import make_job

    from app.core.models import Product

    p = Product(source_url="u")
    db.add(p)
    db.flush()
    job = make_job(db, p, budget=5.0)
    cost.record(db, job, kind=KIND_I2V, provider="fal", model="kling", amount_usd=2.28)
    db.flush()
    assert float(job.cost_accrued_usd) == 2.28
    assert db.query(CostLedgerEntry).count() == 1


def test_budget_guard_blocks_over_budget(db):
    from app.core.models import Product
    from app.modules.generation.tests.conftest import make_job

    p = Product(source_url="u")
    db.add(p)
    db.flush()
    job = make_job(db, p, budget=2.0)  # cannot afford a $2.50 i2v estimate
    assert cost.can_afford(job, KIND_I2V) is False
    try:
        cost.guard(job, KIND_I2V)
        assert False, "expected BudgetExceededError"
    except cost.BudgetExceededError:
        pass
