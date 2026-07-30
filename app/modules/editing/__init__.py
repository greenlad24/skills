"""EDITING & CAPTIONS module (spec §04).

Consumes the artifacts produced by the Generation module — avatar talking-head clips,
product B-roll clips, one *clean Thai VO* track, a chosen `PacingTemplate`, and an
optional music bed — and stitches them into a single TikTok-Shop-compliant Thai
vertical short (9:16, 1080x1920, 30 fps): ``output/final.mp4`` and
``output/final_captioned.mp4``.

Public surface (per docs/CONTRACTS.md §4):
  * ``router`` (in ``router.py``) — APIRouter mounted at ``/api/editing``.
  * Celery task ``editing.run`` (in ``tasks.py``) — the render worker (§4D).

Everything runs locally; there are NO cloud media APIs and therefore no billable
adapter calls / cost-ledger entries in this module. Heavy dependencies (librosa,
moviepy, whisperx, pythainlp, auto-editor, ffmpeg) are imported lazily so the pure
planning/builder functions — and the DRY_RUN path — import and test with zero infra.
"""

from __future__ import annotations

__all__ = ["__doc__"]
