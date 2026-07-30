"""RESEARCH module (spec 02) — Product Research (2A) + Swipe Engine (2B).

Owns ONLY app/modules/research/. Imports only from app.core.*. Every external call
goes through app.core.adapters.registry so DRY_RUN stays $0. Job state changes only via
app.core.state_machine.transition().

Public seams (discovered by the foundation):
  * router.py  → `router: APIRouter` mounted at /api/research
  * tasks.py   → Celery task `research.run` (+ nightly `research.refresh`)
"""

from __future__ import annotations

__all__ = ["MODULE_NAME"]

MODULE_NAME = "research"
