"""Editing module Celery tasks — autodiscovered by ``app.core.queue``.

Owns ``editing.run`` (the task name the core jobs router enqueues for the editing stage,
see docs/CONTRACTS.md §4). Delegates to the render worker in ``worker.py``.
"""

from __future__ import annotations

from app.core.queue import celery_app


@celery_app.task(name="editing.run", bind=True)
def editing_run(self, job_id: str, reroll: str | None = None) -> dict:
    """Render a VideoJob into final.mp4 + final_captioned.mp4 and advance to the gate.

    ``reroll`` (optional) carries the operator's re-cut stage note when the job re-enters
    EDITING from the approval gate (§API /reroll). The worker re-renders deterministically
    from stored inputs regardless (§4D.2).
    """
    # Imported lazily so importing this task module (Celery autodiscovery) never drags in
    # the heavy render/align dependency tree.
    from .worker import run

    return run(job_id, reroll=reroll)
