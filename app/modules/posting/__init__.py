"""Posting & winner-loop module (spec §05).

Owns everything downstream of a rendered final-captioned video:
  * the single human approval gate + posting to TikTok via the PostingProvider adapter,
  * the shop-product-tag manual reminder loop,
  * variant-batch generation with a near-duplicate suppression guard,
  * scheduled analytics ingestion + a scoring/attribution/reweight winner loop.

Plug-in contract (see app/modules/README.md):
  * router.py exposes `router: APIRouter` (prefix /api/posting),
  * tasks.py registers Celery tasks `posting.run` and `posting.ingest_analytics`.

Rules honoured: imports only from app.core.*; all external calls go through
`registry.get_posting_provider()`; job state is changed only via `transition()`.
"""

from __future__ import annotations

__all__ = ["router"]
