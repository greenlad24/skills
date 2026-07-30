"""Sourcing top videos + engagement-proxy ranking (§2B.1).

Videos are mined via the core ScraperProvider (`mine_top_videos`) — the same registry
seam used everywhere, so DRY_RUN returns the deterministic fake dataset for $0. Ranking
is a pure function (`score_videos`) over the returned metrics; EVERY output carries
`signal_type="engagement_proxy"` — public engagement is a proxy, never proof of sales.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import log1p

from app.core.adapters import registry

from .. import config
from ..schemas import ScoredVideo


def recency_decay(posted_at: datetime | None, *, now: datetime | None = None) -> float:
    """Halve weight roughly every PROXY_RECENCY_HALFLIFE_DAYS."""
    if posted_at is None:
        return 1.0
    now = now or datetime.now(timezone.utc)
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)
    age_days = max((now - posted_at).total_seconds() / 86400.0, 0.0)
    return 0.5 ** (age_days / config.PROXY_RECENCY_HALFLIFE_DAYS)


def proxy_score(v: dict, *, now: datetime | None = None) -> float:
    """§2B.1 engagement proxy. Prefers engagement RATE when views are known (avoids
    over-rewarding mega-viral flukes), else falls back to log-scaled raw counts."""
    w = config.PROXY_WEIGHTS
    views = float(v.get("views") or 0)
    likes = float(v.get("likes") or 0)
    shares = float(v.get("shares") or 0)
    comments = float(v.get("comments") or 0)
    saves = float(v.get("saves") or 0)

    if views > 0:
        # rate-based core, scaled by log(views) so reach still matters a little
        rate = (
            w["likes"] * (likes / views)
            + w["shares"] * (shares / views)
            + w["comments"] * (comments / views)
            + w["saves"] * (saves / views)
        )
        base = rate * log1p(views)
    else:
        base = (
            w["views"] * log1p(views)
            + w["likes"] * log1p(likes)
            + w["shares"] * log1p(shares)
            + w["comments"] * log1p(comments)
            + w["saves"] * log1p(saves)
        )

    posted = v.get("posted_at")
    if isinstance(posted, str):
        try:
            posted = datetime.fromisoformat(posted.replace("Z", "+00:00"))
        except ValueError:
            posted = None
    return round(base * recency_decay(posted, now=now), 6)


def _passes_filters(v: dict) -> bool:
    """§2B.1 ingest filters: Thai, UGC duration band, has audio."""
    lang = v.get("language")
    if lang and lang != config.SWIPE_LANGUAGE:
        return False
    dur = v.get("duration_s")
    if dur is not None and not (config.SWIPE_MIN_DURATION_S <= float(dur) <= config.SWIPE_MAX_DURATION_S):
        return False
    if v.get("has_audio") is False:
        return False
    if v.get("is_slideshow") is True or v.get("is_duet") is True:
        return False
    return True


def score_videos(videos: list[dict], *, now: datetime | None = None) -> list[ScoredVideo]:
    """Filter, score, de-dupe by tiktok_id, and return sorted-desc by proxy_score."""
    seen: set[str] = set()
    scored: list[ScoredVideo] = []
    for v in videos:
        if not _passes_filters(v):
            continue
        tid = str(v.get("tiktok_id") or v.get("id") or "")
        if not tid or tid in seen:
            continue
        seen.add(tid)
        posted = v.get("posted_at")
        if isinstance(posted, str):
            try:
                posted = datetime.fromisoformat(posted.replace("Z", "+00:00"))
            except ValueError:
                posted = None
        scored.append(
            ScoredVideo(
                tiktok_id=tid,
                url=v.get("url") or "",
                author_handle=v.get("author_handle") or v.get("author"),
                author_gender=v.get("author_gender"),
                duration_s=v.get("duration_s"),
                posted_at=posted if isinstance(posted, datetime) else None,
                views=int(v.get("views") or 0),
                likes=int(v.get("likes") or 0),
                shares=int(v.get("shares") or 0),
                comments=int(v.get("comments") or 0),
                saves=int(v.get("saves") or 0),
                proxy_score=proxy_score(v, now=now),
            )
        )
    scored.sort(key=lambda s: s.proxy_score, reverse=True)
    return scored


def mine_source(
    query: str, market: str, limit: int, *, idempotency_key: str
) -> tuple[list[ScoredVideo], float]:
    """Mine one source via the ScraperProvider; return (top-K scored, cost_usd)."""
    provider = registry.get_scraper_provider()
    res = provider.mine_top_videos(
        query=query, market=market, limit=limit, idempotency_key=idempotency_key
    )
    if not res.ok:
        return [], res.cost_usd
    videos = list((res.data or {}).get("videos") or [])
    return score_videos(videos)[:limit], res.cost_usd
