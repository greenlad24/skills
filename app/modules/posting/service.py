"""Approval gate + posting service (spec §5A).

This is the business logic behind the module's endpoints and the `posting.run`
Celery task. It:

  * evaluates the human approval decision (approve / reject / reroll) and moves the
    job out of AWAITING_APPROVAL via `transition(..., by_human=True)` ONLY;
  * on approve, enforces the compliance hard gate (all-green) and enqueues posting;
  * builds a compliant PostRequest plan (AI-disclosure toggles, visibility,
    branded-content/SELF_ONLY conflict rule), forcing `is_ai_generated=True`;
  * posts through `registry.get_posting_provider()` (never a vendor SDK directly),
    polls to a terminal state, and persists a `Post`;
  * sets the manual TikTok-Shop product-tag reminder (`shop_tag_status=PENDING`,
    `product_tag_attached=False`, deep link) and lets the operator mark it tagged.

HONEST CONSTRAINTS documented inline below:
  1. OAuth + 2–4 week audit reality (public posting gated on an audited client).
  2. TikTok's mandated pre-post confirmation UX (username+avatar) IS the approval
     gate — there is no second confirmation screen.
  3. The TikTok-Shop product tag / affiliate anchor is NOT in any public API — it
     stays a MANUAL in-app tap; we can only remind + deep-link.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.adapters import registry
from app.core.config import settings
from app.core.models import Post, VideoJob
from app.core.state_machine import (
    IllegalTransitionError,
    JobState,
    transition,
)
from app.modules.posting import compliance_gate

# TikTok visibility vocabulary (spec §5A.2 PostVisibility).
VIS_PUBLIC = "PUBLIC_TO_EVERYONE"
VIS_FRIENDS = "MUTUAL_FOLLOW_FRIENDS"
VIS_PRIVATE = "SELF_ONLY"

# Post status vocabulary (spec §5B.3).
ST_PENDING = "PENDING"
ST_PROCESSING = "PROCESSING"
ST_PUBLISHED = "PUBLISHED"
ST_FAILED = "FAILED"
ST_DRAFT_FALLBACK = "DRAFT_FALLBACK"

# Manual shop-tag status vocabulary (spec §5A.5 #3).
TAG_PENDING = "PENDING"
TAG_TAGGED = "TAGGED"
TAG_NA = "NA"

# Unaudited daily cap (spec §5A.5 #1 / §5D).
UNAUDITED_MAX_POSTS_PER_DAY = 5


class PostingError(Exception):
    """Raised for gate/validation failures the router maps to 4xx."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class ComplianceNotGreenError(PostingError):
    def __init__(self, checklist: dict[str, Any]) -> None:
        super().__init__("compliance checklist is not all-green", status_code=409)
        self.checklist = checklist


# --------------------------------------------------------------------------- #
# Post plan (disclosure mapping + validation) — spec §5A.4
# --------------------------------------------------------------------------- #
@dataclass
class PostPlan:
    account_ref: str
    video_key: str
    caption: str
    hashtags: list[str] = field(default_factory=list)
    visibility: str = VIS_PRIVATE
    disclose_commercial: bool = True         # default ON for shop/UGC content
    disclose_your_brand: bool = True         # promoting the operator's own shop
    disclose_branded_content: bool = False   # only true for a paid partnership
    is_ai_generated: bool = True             # forced True — all AutoUGC output is AI
    schedule_at: str | None = None
    idempotency_key: str = ""

    def full_caption(self) -> str:
        """Merge normalized hashtags into the caption (adapter posts one string)."""
        tags = " ".join(
            f"#{h.lstrip('#')}" for h in (self.hashtags or []) if h.strip()
        )
        base = (self.caption or "").rstrip()
        merged = f"{base}\n\n{tags}".strip() if tags else base
        # TikTok caps the caption (incl. hashtags) at 2200 chars.
        return merged[:2200]

    @property
    def ai_disclosure_master(self) -> bool:
        """The single boolean the core PostingProvider.publish() accepts. We keep the
        full disclosure snapshot on the Post row; the adapter contract only exposes a
        master flag, so we OR the commercial + AIGC signals (both default ON here)."""
        return bool(self.disclose_commercial or self.is_ai_generated)


def build_post_plan(job: VideoJob, decision: dict[str, Any]) -> PostPlan:
    """Assemble the plan from the approved job + the operator's gate decision.

    `decision` carries the operator's edited caption/hashtags and disclosure choices
    captured at the gate (the gate IS TikTok's mandated username/avatar confirmation
    — honest constraint #2). `is_ai_generated` is forced True and cannot be toggled
    off (spec §5A.4 rule) — all AutoUGC output is synthetic.
    """
    account_ref = decision.get("account_ref") or settings.POSTING_PROVIDER + ":default"
    # HONEST CONSTRAINT #1 — OAuth + 2–4 week audit: until the wrapper vendor confirms
    # an audited client, public posting is not legal; an unaudited client may only post
    # SELF_ONLY, capped at 5/user/day. `audited` here is the operator's written
    # confirmation from the vendor (default False = private, the safe legal default).
    audited = bool(decision.get("audited", False))
    requested_vis = decision.get("visibility")
    if requested_vis in (VIS_PUBLIC, VIS_FRIENDS) and not audited:
        # Fall back to private rather than silently attempting an illegal public post.
        visibility = VIS_PRIVATE
    else:
        visibility = requested_vis or (VIS_PUBLIC if audited else VIS_PRIVATE)

    plan = PostPlan(
        account_ref=account_ref,
        video_key=job.draft_asset_key or "",
        caption=decision.get("caption") or "",
        hashtags=list(decision.get("hashtags") or []),
        visibility=visibility,
        disclose_commercial=bool(decision.get("disclose_commercial", True)),
        disclose_your_brand=bool(decision.get("disclose_your_brand", True)),
        disclose_branded_content=bool(decision.get("disclose_branded_content", False)),
        is_ai_generated=True,  # forced — non-editable
        schedule_at=decision.get("schedule_at"),
        idempotency_key=f"{job.id}:{account_ref}",
    )
    validate_plan(plan)
    return plan


def validate_plan(plan: PostPlan) -> None:
    """Enforce disclosure/visibility rules before submit (spec §5A.4 / §5D)."""
    if not plan.video_key:
        raise PostingError("no rendered video to post (draft_asset_key is empty)")
    # Branded content cannot be private — TikTok rejects private branded content.
    if plan.disclose_branded_content and plan.visibility == VIS_PRIVATE:
        raise PostingError(
            "branded-content posts cannot be SELF_ONLY; choose a public/friends "
            "visibility or disable branded-content disclosure",
            status_code=422,
        )
    if not plan.is_ai_generated:
        # Defensive: the builder forces True, but never let a caller flip it off.
        raise PostingError("is_ai_generated must be True for AutoUGC output", status_code=422)


# --------------------------------------------------------------------------- #
# Approval-gate decisions (human-only edges out of AWAITING_APPROVAL) — §5A.1
# --------------------------------------------------------------------------- #
def approve(session, job_id: str, decision: dict[str, Any]) -> dict[str, Any]:
    """Operator APPROVE → compliance hard gate → POSTING, then enqueue posting.run.

    Raises ComplianceNotGreenError (409) if the pre-post checklist is not all-green
    — no override in v1 (CONTRACTS §5). The gate render (username+avatar) satisfies
    TikTok's mandated pre-post confirmation UX; this approve call is that confirmation.
    """
    job = _get_job(session, job_id)
    _require_state(job, JobState.AWAITING_APPROVAL)

    all_green, checklist = compliance_gate.evaluate_gate(str(job_id))
    if not all_green:
        raise ComplianceNotGreenError(checklist)

    # Validate the disclosure/visibility combination up front so the operator gets a
    # clear gate error instead of a late task failure.
    build_post_plan(job, decision)

    try:
        transition(job, JobState.POSTING, by_human=True)
    except IllegalTransitionError as exc:
        raise PostingError(str(exc), status_code=409) from exc

    job.approved_at = datetime.now(timezone.utc)
    job.decision = {
        **(job.decision or {}),
        "decision": "approve",
        "caption": decision.get("caption"),
        "hashtags": decision.get("hashtags"),
        "disclose_your_brand": decision.get("disclose_your_brand", True),
        "disclose_branded_content": decision.get("disclose_branded_content", False),
        "disclose_commercial": decision.get("disclose_commercial", True),
        "visibility": decision.get("visibility"),
        "audited": decision.get("audited", False),
        "account_ref": decision.get("account_ref"),
        "schedule_at": decision.get("schedule_at"),
        "approved_at": job.approved_at.isoformat(),
    }
    session.commit()

    _enqueue("posting.run", {"job_id": str(job.id)})
    return {"state": JobState.POSTING.value, "compliance": checklist}


def reject(session, job_id: str, note: str | None = None) -> dict[str, Any]:
    """Operator REJECT (discard) → terminal REJECTED."""
    job = _get_job(session, job_id)
    _require_state(job, JobState.AWAITING_APPROVAL)
    try:
        transition(job, JobState.REJECTED, by_human=True)
    except IllegalTransitionError as exc:
        raise PostingError(str(exc), status_code=409) from exc
    job.decision = {**(job.decision or {}), "decision": "reject", "note": note}
    session.commit()
    return {"state": JobState.REJECTED.value}


def reroll(session, job_id: str, stage: str, note: str | None = None) -> dict[str, Any]:
    """Operator REQUEST RE-ROLL → back to EDITING (cheap re-cut loop, no full regen)."""
    job = _get_job(session, job_id)
    from_state = _state_of(job)
    _require_state(job, JobState.AWAITING_APPROVAL)
    try:
        transition(job, JobState.EDITING, by_human=True)
    except IllegalTransitionError as exc:
        raise PostingError(str(exc), status_code=409) from exc
    job.decision = {
        **(job.decision or {}),
        "decision": "reroll",
        "stage": stage,
        "note": note,
    }
    session.commit()
    _enqueue("editing.run", {"job_id": str(job.id), "reroll": stage})
    return {"state": JobState.EDITING.value, "from_stage": from_state.value}


def mark_tagged(session, job_id: str) -> dict[str, Any]:
    """Operator marks the manual TikTok-Shop product tag done (spec §5A.5 #3).

    The product/affiliate tag CANNOT be attached programmatically — it is a manual
    in-app tap. We only record that the operator did it, and lift the reminder.
    """
    job = _get_job(session, job_id)
    post = _get_post(session, job)
    if post is None:
        raise PostingError("no post exists for this job yet", status_code=409)
    post.product_tag_attached = True
    post.shop_tag_status = TAG_TAGGED
    post.shop_tagged_at = datetime.now(timezone.utc)
    session.commit()
    return {"tagged": True, "shop_tag_status": TAG_TAGGED}


# --------------------------------------------------------------------------- #
# Posting (the posting.run task body) — spec §5A.3 / §5A.7
# --------------------------------------------------------------------------- #
def run_posting(session, job_id: str) -> dict[str, Any]:
    """Post an APPROVED job. Called by the `posting.run` Celery task.

    Preconditions enforced here (defence in depth — the gate also enforces them):
      * the job is in POSTING (i.e. an operator approve already happened), and
      * `job.approved_at` is set (evidence the human gate was crossed), and
      * the compliance checklist is all-green.
    If any precondition fails we refuse to post and drive POSTING→FAILED.
    """
    job = _get_job(session, job_id)

    # AWAITING_APPROVAL→POSTING must have already happened via a human decision.
    if _state_of(job) is not JobState.POSTING or job.approved_at is None:
        return _fail(session, job, "posting refused: job was not human-approved")

    # HARD GATE (backstop): refuse unless compliance is all-green — no override (v1).
    all_green, checklist = compliance_gate.evaluate_gate(str(job_id))
    if not all_green:
        return _fail(
            session, job, "posting refused: compliance checklist not all-green",
            extra={"compliance": checklist},
        )

    plan = build_post_plan(job, job.decision or {})
    provider = registry.get_posting_provider()

    # Create the Post row BEFORE calling the provider so a worker crash mid-submit
    # can re-attach rather than double-post (idempotency_key + local uniqueness).
    post = _get_or_create_post(session, job, plan)
    post.status = ST_PENDING
    session.commit()

    result = provider.publish(
        video_key=plan.video_key,
        caption=plan.full_caption(),
        platform=job.post.platform if job.post else "tiktok",
        ai_disclosure=plan.ai_disclosure_master,
        schedule_at=plan.schedule_at,
        idempotency_key=plan.idempotency_key,
    )

    if not result.ok:
        return _fail(session, job, result.error or "provider publish failed",
                     post=post, extra={"provider_error": result.error})

    # Status: the core PostingProvider contract (publish + fetch_metrics) has no
    # separate poll method — publish returns the (near-)terminal result directly.
    # The Fake returns a live post_url immediately. `_poll_until_published` here
    # interprets that result; a real async wrapper would loop provider.poll() with
    # backoff (10s,20s,40s… capped 5min, max ~30min — spec §5A.7). Documented so the
    # collapse of submit+poll into publish() is explicit, not accidental.
    status_data = _poll_until_published(result.data)

    _apply_published(post, plan, status_data, provider_post_id=result.provider_job_id)
    session.commit()

    # POSTING → POSTED (published; awaiting the manual product tag).
    try:
        transition(job, JobState.POSTED)
    except IllegalTransitionError:
        pass
    session.commit()

    return {
        "state": JobState.POSTED.value,
        "post_id": str(post.id),
        "post_url": post.post_url,
        "deep_link": post.deep_link,
        # Manual shop-tag reminder (spec §5A.5 #3) — the operator must open the post
        # in-app and add the product/affiliate tag; it is NOT possible via API.
        "shop_tag_reminder": _shop_tag_reminder(post),
    }


def _poll_until_published(publish_data: dict[str, Any]) -> dict[str, Any]:
    """Interpret the publish result as a terminal status.

    With the core adapter, publish() is effectively submit+poll collapsed: if a
    post_url / external_post_id is present we treat it as PUBLISHED. A real async
    provider would instead loop poll() with capped exponential backoff until
    PUBLISHED or FAILED (spec §5A.7); the interface for that lives in the vendor
    adapter, not this module.
    """
    url = publish_data.get("post_url")
    external_id = publish_data.get("external_post_id")
    if url or external_id:
        return {
            "status": ST_PUBLISHED,
            "post_url": url,
            "external_post_id": external_id,
            "deep_link": publish_data.get("deep_link"),
            "tiktok_video_id": _extract_video_id(url) if url else None,
        }
    return {"status": ST_PROCESSING}


def _apply_published(
    post: Post, plan: PostPlan, status_data: dict[str, Any], *, provider_post_id: str | None
) -> None:
    now = datetime.now(timezone.utc)
    post.posting_provider = settings.POSTING_PROVIDER
    post.provider_post_id = provider_post_id or status_data.get("external_post_id")
    post.external_post_id = status_data.get("external_post_id") or provider_post_id
    post.tiktok_video_id = status_data.get("tiktok_video_id")
    post.post_url = status_data.get("post_url")
    post.deep_link = status_data.get("deep_link") or _fallback_deep_link(post.post_url)
    post.status = status_data.get("status", ST_PUBLISHED)
    post.visibility = plan.visibility
    post.ai_disclosure_set = True
    post.is_ai_generated = True
    post.disclose_commercial = plan.disclose_commercial
    post.disclose_your_brand = plan.disclose_your_brand
    post.disclose_branded_content = plan.disclose_branded_content
    post.account_ref = plan.account_ref
    if post.status == ST_PUBLISHED:
        post.posted_at = now
        # Manual product tag — pending until the operator taps it in the TikTok app.
        post.product_tag_attached = False
        post.shop_tag_status = TAG_PENDING


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _get_or_create_post(session, job: VideoJob, plan: PostPlan) -> Post:
    existing = _get_post(session, job)
    if existing is not None:
        return existing
    vgid = (job.decision or {}).get("variant_group_id")
    post = Post(
        video_job_id=job.id,
        platform="tiktok",
        posting_provider=settings.POSTING_PROVIDER,
        account_ref=plan.account_ref,
        visibility=plan.visibility,
        status=ST_PENDING,
        ai_disclosure_set=True,
        is_ai_generated=True,
        disclose_commercial=plan.disclose_commercial,
        disclose_your_brand=plan.disclose_your_brand,
        disclose_branded_content=plan.disclose_branded_content,
        product_tag_attached=False,
        shop_tag_status=TAG_PENDING,
        variant_group_id=_as_uuid(vgid),
    )
    session.add(post)
    session.flush()
    return post


def _shop_tag_reminder(post: Post) -> dict[str, Any]:
    return {
        "message": (
            "Open this post in the TikTok app and add the TikTok-Shop product / "
            "affiliate tag — it cannot be attached automatically."
        ),
        "post_url": post.post_url,
        "deep_link": post.deep_link,
        "shop_tag_status": post.shop_tag_status,
        "product_tag_attached": post.product_tag_attached,
    }


def _fail(
    session, job: VideoJob, reason: str, *, post: Post | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if post is not None:
        post.status = ST_FAILED
        post.fail_reason = reason
    job.failure_reason = reason
    try:
        transition(job, JobState.FAILED)
    except IllegalTransitionError:
        pass
    session.commit()
    out = {"state": _state_of(job).value, "error": reason}
    if extra:
        out.update(extra)
    return out


def _get_job(session, job_id: str) -> VideoJob:
    job = session.get(VideoJob, _as_uuid(job_id) or job_id)
    if job is None:
        raise PostingError("job not found", status_code=404)
    return job


def _get_post(session, job: VideoJob) -> Post | None:
    return job.post


def _require_state(job: VideoJob, state: JobState) -> None:
    if _state_of(job) is not state:
        raise PostingError(
            f"job is {_state_of(job).value}, expected {state.value}", status_code=409
        )


def _state_of(job: VideoJob) -> JobState:
    s = job.state
    return s if isinstance(s, JobState) else JobState(s)


def _enqueue(task_name: str, kwargs: dict[str, Any]) -> None:
    from app.core.queue import celery_app

    try:
        celery_app.send_task(task_name, kwargs=kwargs)
    except Exception:  # noqa: BLE001 — broker may be absent in local/skeleton runs
        pass


def _as_uuid(value: Any):
    import uuid

    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


def _extract_video_id(url: str | None) -> str | None:
    if not url:
        return None
    # canonical tiktok.com/@user/video/<id>
    marker = "/video/"
    if marker in url:
        return url.rsplit(marker, 1)[-1].split("?")[0] or None
    return None


def _fallback_deep_link(url: str | None) -> str | None:
    vid = _extract_video_id(url)
    return f"snssdk1233://aweme/detail/{vid}" if vid else None
