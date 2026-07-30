from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.research.swipe import sourcing


def _v(tid, views, likes, **kw):
    d = {"tiktok_id": tid, "url": f"https://tt/{tid}", "views": views, "likes": likes,
         "language": "th", "duration_s": 20.0, "has_audio": True}
    d.update(kw)
    return d


def test_ranking_stable_and_all_proxy():
    now = datetime(2026, 7, 1, tzinfo=timezone.utc)
    posted = (now - timedelta(days=1)).isoformat()
    videos = [
        _v("a", 10000, 500, posted_at=posted),
        _v("b", 10000, 2000, posted_at=posted),   # higher like-rate → should rank first
        _v("c", 10000, 100, posted_at=posted),
        _v("a", 10000, 500, posted_at=posted),     # dup id → dropped
    ]
    scored = sourcing.score_videos(videos, now=now)
    ids = [s.tiktok_id for s in scored]
    assert ids == ["b", "a", "c"]
    assert all(s.signal_type == "engagement_proxy" for s in scored)
    assert scored[0].proxy_score >= scored[1].proxy_score >= scored[2].proxy_score


def test_filters_language_and_duration():
    videos = [
        _v("th_ok", 1000, 100),
        _v("en", 1000, 100, language="en"),
        _v("too_short", 1000, 100, duration_s=3.0),
        _v("too_long", 1000, 100, duration_s=200.0),
        _v("no_audio", 1000, 100, has_audio=False),
    ]
    scored = sourcing.score_videos(videos)
    assert [s.tiktok_id for s in scored] == ["th_ok"]


def test_recency_decay_monotonic():
    now = datetime(2026, 7, 1, tzinfo=timezone.utc)
    fresh = sourcing.recency_decay(now - timedelta(days=1), now=now)
    old = sourcing.recency_decay(now - timedelta(days=90), now=now)
    assert fresh > old > 0


def test_mine_source_dry_run_uses_fake():
    top, cost = sourcing.mine_source("@x", "TH", 5, idempotency_key="t")
    assert len(top) >= 1
    assert all(s.signal_type == "engagement_proxy" for s in top)
    assert cost >= 0
