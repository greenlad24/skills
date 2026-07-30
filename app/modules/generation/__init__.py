"""AutoUGC-TH generation module (spec §03).

Turns a normalized product + chosen templates into a validated, claim-safe Thai
script (§3A), then renders it into scene-level media assets using the hybrid
avatar + product-b-roll strategy (§3B) reusing a one-time avatar/voice persona
(§3C) through the async fan-out generation pipeline (§3D).

Public seams (per docs/CONTRACTS.md):
  * ``router: APIRouter`` (prefix ``/api/generation``) — see ``router.py``.
  * Celery task ``generation.run`` — see ``tasks.py``.

Everything external goes through ``app.core.adapters.registry``; job state changes
only through ``app.core.state_machine.transition``; every billable call writes a
``CostLedgerEntry`` and respects the per-video budget.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
