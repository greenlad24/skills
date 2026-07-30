"""Generation Celery tasks — autodiscovered by ``app.core.queue``.

``generation.run`` is the task name the core jobs pipeline enqueues for the
generation stage (docs/CONTRACTS.md §4). It advances GENERATING → (next),
producing avatar clips + b-roll clips + a clean Thai VO track for the editing
module. It opens its own DB session and drives state only via ``transition()``.
"""

from __future__ import annotations

from app.core.queue import celery_app
from app.modules.generation import service


@celery_app.task(name="generation.run", bind=True, max_retries=3)
def run(self, job_id: str, **kwargs) -> dict:
    """Run the generation stage for ``job_id`` (§3A scripting + §3D render)."""
    outcome = service.run_generation(job_id, options=kwargs.get("options"))
    return {
        "job_id": outcome.job_id,
        "state": outcome.state,
        "script_passed_claims": outcome.script_passed_claims,
        "halted": outcome.halted,
        "reason": outcome.reason,
        "reroll_rate": outcome.reroll_rate,
        "cost_usd": outcome.cost_usd,
        "blocked_scene_ids": outcome.blocked_scene_ids,
    }
