"""AutoUGC-TH COMPLIANCE module (spec §06).

The fail-safe compliance & legal guardrails engine. Exposes:

* ``service.classify_claims(script)``      — the claim-safety scan (§6B).
* ``service.run_prepost_checklist(job_id)``— the deterministic pre-post gate (§6D).
* ``router: APIRouter`` (prefix ``/api/compliance``).
* Celery tasks ``compliance.classify`` / ``compliance.checklist`` (``tasks.py``).

Design principles (§6.0): fail closed on any ambiguity; deterministic gate with a
probabilistic (LLM) assist that can only *raise* flags, never grant a pass; every
decision is logged into an append-only, hash-chained ``ComplianceRecord``; rule tables
are versioned data (``ruleset.py`` / ``data/``).

NOT LEGAL ADVICE — see README.md.
"""

from app.modules.compliance.service import (  # noqa: F401
    classify_claims,
    run_prepost_checklist,
)

__all__ = ["classify_claims", "run_prepost_checklist"]
