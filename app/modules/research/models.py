"""Research-owned tables: `Transcript` and `SceneAnalysis` (§2B.2 / §2B.5).

CONTRACTS.md §1: `SwipeVideo.transcript_id` / `scene_data_id` are opaque IDs; the
`Transcript` / `SceneAnalysis` tables themselves are owned by THIS module, not core.
They inherit the core declarative `Base` so they share one metadata/engine, but core's
`init_db()` only creates the core tables — this module creates its own via
`create_research_tables()` (called from tasks bootstrap and tests).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, engine
from app.core.models import GUID, JSON, TimestampMixin


def _pk() -> Mapped[uuid.UUID]:
    from sqlalchemy.orm import mapped_column as _mc

    return _mc(GUID(), primary_key=True, default=uuid.uuid4)


class Transcript(TimestampMixin, Base):
    """Merged VO ⊕ OSD timed transcript for one SwipeVideo (§2B.2 merge output)."""

    __tablename__ = "research_transcripts"

    id: Mapped[uuid.UUID] = _pk()
    swipe_video_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), index=True)
    tiktok_id: Mapped[str | None] = mapped_column(String(64), index=True)
    language: Mapped[str] = mapped_column(String(8), default="th")
    # segments: [{t_start,t_end,source:"vo"|"osd",text,bbox?}]
    segments: Mapped[list | None] = mapped_column(JSON)
    vo_text: Mapped[str | None] = mapped_column(Text)
    osd_text: Mapped[str | None] = mapped_column(Text)
    merged_text: Mapped[str | None] = mapped_column(Text)
    tokens: Mapped[list | None] = mapped_column(JSON)   # PyThaiNLP word tokens


class SceneAnalysis(TimestampMixin, Base):
    """PySceneDetect output + beat map for one SwipeVideo (§2B.5)."""

    __tablename__ = "research_scene_analyses"

    id: Mapped[uuid.UUID] = _pk()
    swipe_video_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), index=True)
    tiktok_id: Mapped[str | None] = mapped_column(String(64), index=True)
    total_duration_s: Mapped[float | None] = mapped_column(Float)
    shot_count: Mapped[int | None] = mapped_column(Integer)
    avg_shot_len_s: Mapped[float | None] = mapped_column(Float)
    # cut_rhythm: [{idx,start,end,dur}]
    cut_rhythm: Mapped[list | None] = mapped_column(JSON)
    # beat_map: [{beat,t:[start,end]}]
    beat_map: Mapped[list | None] = mapped_column(JSON)
    hook_end_s: Mapped[float | None] = mapped_column(Float)
    cta_start_s: Mapped[float | None] = mapped_column(Float)
    shots_per_10s: Mapped[float | None] = mapped_column(Float)


RESEARCH_MODELS = [Transcript, SceneAnalysis]


def create_research_tables() -> None:
    """Create this module's tables (idempotent). Core's init_db() doesn't know them."""
    Base.metadata.create_all(bind=engine, tables=[m.__table__ for m in RESEARCH_MODELS])
