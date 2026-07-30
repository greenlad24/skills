"""Cost ledger + per-video budget guard (§3D.7, CONTRACTS §3).

Every billable adapter call writes a ``CostLedgerEntry`` in the SAME transaction
that bumps ``VideoJob.cost_accrued_usd``. The budget guard is checked *before*
spending; exceeding the per-video ceiling halts to the operator gate instead of
auto-spending (§3D.10 cost guard).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.models import CostLedgerEntry, VideoJob
from app.modules.generation.constants import (
    COST_TARGET_USD,
    ESTIMATED_COST_USD,
)


class BudgetExceededError(Exception):
    """Raised when a spend would push the job past its per-video budget."""

    def __init__(self, accrued: float, estimate: float, budget: float) -> None:
        self.accrued = accrued
        self.estimate = estimate
        self.budget = budget
        super().__init__(
            f"budget guard: accrued ${accrued:.4f} + est ${estimate:.4f} "
            f"> budget ${budget:.2f}"
        )


def estimate_cost(kind: str) -> float:
    return float(ESTIMATED_COST_USD.get(kind, 0.0))


def remaining_budget(job: VideoJob) -> float:
    return float(job.cost_budget_usd or 0) - float(job.cost_accrued_usd or 0)


def can_afford(job: VideoJob, kind: str) -> bool:
    """True if the estimated cost of ``kind`` fits the remaining budget."""
    return estimate_cost(kind) <= remaining_budget(job) + 1e-9


def guard(job: VideoJob, kind: str) -> None:
    """Raise ``BudgetExceededError`` if ``kind`` cannot be afforded."""
    if not can_afford(job, kind):
        raise BudgetExceededError(
            float(job.cost_accrued_usd or 0), estimate_cost(kind),
            float(job.cost_budget_usd or 0),
        )


def record(
    db: Session,
    job: VideoJob,
    *,
    kind: str,
    provider: str | None,
    model: str | None,
    amount_usd: float,
    stage: str = "generation",
    scene_id=None,
    attempt: int | None = None,
    is_reroll: bool = False,
    usage: dict | None = None,
    line_item: str | None = None,
) -> CostLedgerEntry:
    """Append a ``CostLedgerEntry`` and bump ``job.cost_accrued_usd`` atomically.

    The caller owns the surrounding transaction/commit; this only adds to the
    session and mutates the in-memory job so the two stay consistent.
    """
    entry = CostLedgerEntry(
        video_job_id=job.id,
        stage=stage,
        provider=provider,
        line_item=line_item or kind,
        amount_usd=amount_usd,
        usage=usage or {},
        incurred_at=datetime.now(timezone.utc),
        scene_id=scene_id,
        model=model,
        kind=kind,
        attempt=attempt,
        is_reroll=is_reroll,
    )
    db.add(entry)
    job.cost_accrued_usd = float(job.cost_accrued_usd or 0) + float(amount_usd or 0)
    return entry


def over_target(job: VideoJob) -> bool:
    """Soft alert: job trending above the ~$3/video target (§3D.7)."""
    return float(job.cost_accrued_usd or 0) > COST_TARGET_USD
