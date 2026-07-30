"""Pydantic v2 schemas for API I/O (§7A.10 REST/WS contract).

These are the request/response shapes the FastAPI layer and every module router speak.
They intentionally mirror the canonical models but stay decoupled (API surface != DB rows).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.state_machine import JobState


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
class JobCreate(BaseModel):
    """POST /api/jobs body."""

    product_url: str
    seed_set: str | None = None
    avatar_id: uuid.UUID | None = None
    duration_s: int | None = None


class JobCreateResponse(BaseModel):
    job_id: uuid.UUID
    state: JobState = JobState.QUEUED


class ComplianceItem(BaseModel):
    id: str
    label: str
    pass_: bool = Field(alias="pass")
    reason: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class ComplianceSummary(BaseModel):
    items: list[ComplianceItem] = Field(default_factory=list)
    all_green: bool = False


class PostSummary(BaseModel):
    tiktok_url: str | None = None
    deep_link: str | None = None
    tagged: bool = False


class JobSummary(BaseModel):
    """Row shape for GET /api/jobs (dashboard table)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    state: JobState
    product: str | None = None
    progress: int = 0
    cost: float = 0.0
    created_at: datetime | None = None
    video_url: str | None = None


class Job(BaseModel):
    """Full job for GET /api/jobs/{id}."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    state: JobState
    product: str | None = None
    progress: int = 0
    cost: float = 0.0
    created_at: datetime | None = None
    video_url: str | None = None
    script: str | None = None
    flagged_claims: list[dict[str, Any]] = Field(default_factory=list)
    compliance: ComplianceSummary = Field(default_factory=ComplianceSummary)
    caption: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    post: PostSummary | None = None


class JobListResponse(BaseModel):
    jobs: list[JobSummary] = Field(default_factory=list)
    cursor: str | None = None


class CaptionUpdate(BaseModel):
    """PATCH /api/jobs/{id}/caption."""

    caption: str | None = None
    hashtags: list[str] | None = None


class RerollRequest(BaseModel):
    """POST /api/jobs/{id}/reroll."""

    stage: Literal["script", "voice", "broll", "recut"]
    note: str | None = None


class DecisionResponse(BaseModel):
    """Generic state-change response for approve/reject/retry/reroll."""

    state: JobState
    from_stage: str | None = None


class TaggedResponse(BaseModel):
    tagged: bool = True


class OkResponse(BaseModel):
    ok: bool = True


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
class ProviderHealth(BaseModel):
    provider: str
    kind: str
    mode: Literal["fake", "real"]
    ok: bool = True


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    dry_run: bool = True
    version: str
    db: Literal["ok", "unavailable"] = "ok"
    providers: list[ProviderHealth] = Field(default_factory=list)
    modules_loaded: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# WebSocket event envelopes (§7A.10) — documented shapes for module workers.
# --------------------------------------------------------------------------- #
class WSStateEvent(BaseModel):
    type: Literal["state"] = "state"
    job_id: uuid.UUID
    ts: datetime
    state: JobState
    prev: JobState | None = None


class WSProgressEvent(BaseModel):
    type: Literal["progress"] = "progress"
    job_id: uuid.UUID
    ts: datetime
    stage: str
    pct: int
    cost: float


class WSArtifactEvent(BaseModel):
    type: Literal["artifact"] = "artifact"
    job_id: uuid.UUID
    ts: datetime
    kind: Literal["script", "first_frame", "hook", "product_facts"]
    ref: str


class WSCostEvent(BaseModel):
    type: Literal["cost"] = "cost"
    job_id: uuid.UUID
    ts: datetime
    job: float
    day: float
    guard: Literal["OK", "WARN", "STOP"]


class WSErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    job_id: uuid.UUID
    ts: datetime
    stage: str
    message: str
    retryable: bool = False


class WSPostedEvent(BaseModel):
    type: Literal["posted"] = "posted"
    job_id: uuid.UUID
    ts: datetime
    tiktok_url: str
    deep_link: str | None = None
