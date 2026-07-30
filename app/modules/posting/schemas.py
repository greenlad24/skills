"""Pydantic request/response schemas for the posting module endpoints (§5A / §7A.10).

These are the module's own API surface under /api/posting; they complement (not
replace) the core job schemas in app.core.schemas.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class ApproveRequest(BaseModel):
    """POST /api/posting/jobs/{id}/approve — the approval gate.

    The gate render (username + avatar) IS TikTok's mandated pre-post confirmation;
    submitting this body is the operator's confirmation. Caption/hashtags are the
    final edited values; disclosure flags are the exact state shown at the gate.
    `is_ai_generated` is intentionally absent — it is always True and non-editable.
    """

    caption: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    disclose_commercial: bool = True
    disclose_your_brand: bool = True
    disclose_branded_content: bool = False
    visibility: str | None = None          # PUBLIC_TO_EVERYONE | SELF_ONLY | ...
    audited: bool = False                  # operator's written vendor audit confirmation
    account_ref: str | None = None
    schedule_at: str | None = None         # RFC3339 UTC; None = post now


class RejectRequest(BaseModel):
    note: str | None = None


class RerollRequest(BaseModel):
    stage: str = "recut"
    note: str | None = None


class DecisionResponse(BaseModel):
    state: str
    from_stage: str | None = None
    compliance: dict[str, Any] | None = None


class TaggedResponse(BaseModel):
    tagged: bool = True
    shop_tag_status: str = "TAGGED"


class VariantBatchRequest(BaseModel):
    product_id: uuid.UUID
    n: int = 4
    hook_selector: str | None = None       # softmax | thompson | ucb1


class VariantBatchResponse(BaseModel):
    variant_group_id: str
    job_ids: list[str] = Field(default_factory=list)
    manifests: list[dict[str, Any]] = Field(default_factory=list)
    blocked: list[dict[str, Any]] = Field(default_factory=list)


class IngestResponse(BaseModel):
    posts: int = 0
    ingested: int = 0
    attributed: int = 0


class PostView(BaseModel):
    id: uuid.UUID
    status: str | None = None
    post_url: str | None = None
    deep_link: str | None = None
    shop_tag_status: str | None = None
    product_tag_attached: bool = False
    latest_score: float | None = None
