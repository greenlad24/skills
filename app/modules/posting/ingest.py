"""Scheduled analytics ingestion + template reweighting (spec §5B.4–§5B.7).

Runs daily per published post within a tracking window: pull engagement metrics
via the PostingProvider adapter (`fetch_metrics`), optionally fold in operator-
imported TikTok-Shop affiliate sales, write a time-series `PerformanceRecord`,
score it, and once per cycle reweight the Hook/Formula/Pacing templates.

HONESTY CONTRACT: engagement is pulled automatically and is always present; sales
(`orders`/`gmv`/`commission`) are best-effort and frequently a MANUAL CSV import,
so they may be null — the scorer falls back to an engagement-only branch and never
crashes on missing sales (spec §5B.4 / §5D "missing sales data").

Idempotency: at most one PerformanceRecord per (post, captured_at::date, source);
a same-day re-run UPSERTS rather than duplicating (spec §5B.5).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.core.adapters import registry
from app.core.models import (
    FormulaTemplate,
    HookTemplate,
    PacingTemplate,
    PerformanceRecord,
    Post,
    VideoJob,
)
from app.modules.posting import scoring
from app.modules.posting.service import ST_PUBLISHED

TRACKING_WINDOW_DAYS = 30  # daily to 14d then weekly out to 30d (spec §5B.5)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def posts_in_tracking_window(session, *, max_age_days: int = TRACKING_WINDOW_DAYS) -> list[Post]:
    """Published posts still inside the tracking window and not media-missing."""
    cutoff = _utcnow() - timedelta(days=max_age_days)
    stmt = select(Post).where(Post.status == ST_PUBLISHED)
    posts = list(session.execute(stmt).scalars().all())
    result: list[Post] = []
    for p in posts:
        posted = p.posted_at
        if posted is not None and posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        if posted is None or posted >= cutoff:
            result.append(p)
    return result


def _same_day_record(session, post_id, source: str, day: datetime) -> PerformanceRecord | None:
    """Find an existing record for (post, day, source) to upsert (idempotency)."""
    day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    stmt = (
        select(PerformanceRecord)
        .where(PerformanceRecord.post_id == post_id)
        .where(PerformanceRecord.source == source)
    )
    for rec in session.execute(stmt).scalars().all():
        cap = rec.captured_at
        if cap is None:
            continue
        if cap.tzinfo is None:
            cap = cap.replace(tzinfo=timezone.utc)
        if day_start <= cap < day_end:
            return rec
    return None


def ingest_post(session, post: Post, *, source: str = "tiktok_analytics") -> PerformanceRecord | None:
    """Fetch metrics for one post, upsert a scored PerformanceRecord.

    Returns the record, or None if the post has no external id yet. Missing sales
    data is tolerated (engagement-only score). A provider that flags the media as
    missing sets Post.status='MEDIA_MISSING' and is skipped from scoring upstream.
    """
    external_id = post.external_post_id or post.provider_post_id
    if not external_id:
        return None

    provider = registry.get_posting_provider()
    result = provider.fetch_metrics(external_post_id=external_id)
    if not result.ok:
        return None
    m = result.data or {}

    now = _utcnow()
    rec = _same_day_record(session, post.id, source, now)
    created = rec is None
    if rec is None:
        rec = PerformanceRecord(post_id=post.id, source=source)
        session.add(rec)

    rec.captured_at = now
    rec.views = int(m.get("views") or 0)
    rec.likes = int(m.get("likes") or 0)
    rec.comments = int(m.get("comments") or 0)
    rec.shares = int(m.get("shares") or 0)
    rec.favorites = int(m.get("favorites") or 0)
    rec.avg_watch_time_s = _f(m.get("avg_watch_time_s"))
    rec.full_video_watch_rate = _f(m.get("full_video_watch_rate"))
    rec.reach = _i(m.get("reach"))
    rec.profile_visits = _i(m.get("profile_visits"))

    # Optional operator-imported Shop affiliate sales (may be entirely absent).
    sales = _latest_affiliate_row(m)
    rec.product_clicks = _i(sales.get("product_clicks"))
    rec.orders = _i(sales.get("orders"))
    rec.gmv = _f(sales.get("gmv"))
    rec.commission = _f(sales.get("commission"))

    rec.score = scoring.compute_score(rec)

    # Denormalized latest-score cache on the Post (source of truth stays the record).
    post.latest_score = rec.score
    post.latest_metrics_at = now
    if rec.score is not None and rec.orders:
        rec.is_winner = rec.score >= 0.5

    session.flush()
    _ = created  # kept for clarity: created vs. upserted are handled identically
    return rec


def _latest_affiliate_row(metrics: dict[str, Any]) -> dict[str, Any]:
    """Sales fields the operator imported (e.g. via /import/affiliate-csv).

    In this build the affiliate numbers, when available, ride alongside the metrics
    payload; absent that they're all None and the scorer uses the engagement-only
    branch. A CSV-import endpoint can populate a dedicated table later without
    changing this contract.
    """
    return {
        "product_clicks": metrics.get("product_clicks"),
        "orders": metrics.get("orders"),
        "gmv": metrics.get("gmv"),
        "commission": metrics.get("commission"),
    }


def reweight_templates(session) -> int:
    """Attribute each post's latest score back to its Hook/Formula/Pacing templates
    and update their `operator_win_score` via floored EMA (spec §5B.7).

    Attribution is shared, not double-counted: a post's score updates the hook,
    formula and pacing weights INDEPENDENTLY. Returns the count of posts attributed.
    Runs once per ingest cycle.
    """
    posts = list(
        session.execute(
            select(Post).where(Post.latest_score.is_not(None))
        ).scalars().all()
    )
    attributed = 0
    for post in posts:
        job = session.get(VideoJob, post.video_job_id)
        if job is None:
            continue
        templates = [
            session.get(HookTemplate, job.hook_template_id) if job.hook_template_id else None,
            session.get(FormulaTemplate, job.formula_template_id) if job.formula_template_id else None,
            session.get(PacingTemplate, job.pacing_template_id) if job.pacing_template_id else None,
        ]
        agg = scoring.aggregate_post_score(float(post.latest_score))
        scoring.attribute_to_templates(templates, agg)
        attributed += 1
    session.commit()
    return attributed


def ingest_daily(session) -> dict[str, Any]:
    """Full daily cycle: ingest every in-window post, then reweight once."""
    posts = posts_in_tracking_window(session)
    ingested = 0
    for post in posts:
        try:
            rec = ingest_post(session, post)
        except Exception:  # noqa: BLE001 — one bad post must not sink the batch (§5D)
            continue
        if rec is not None:
            ingested += 1
    session.commit()
    attributed = reweight_templates(session)
    return {"posts": len(posts), "ingested": ingested, "attributed": attributed}


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
