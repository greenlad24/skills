from __future__ import annotations

from sqlalchemy import select

from app.core.models import HookTemplate, SwipeSource, SwipeVideo
from app.modules.research.swipe import service


def _seed_source(db, niche="beauty.skincare"):
    src = SwipeSource(type="account", handle="@nimpara_", niche=niche, enabled=True)
    db.add(src)
    db.commit()
    return src


def test_refresh_creates_templates_and_processes_new(db):
    _seed_source(db)
    report = service.refresh_niche(db, "beauty.skincare", top_k=5)
    assert report.new_videos >= 1
    assert report.videos_processed == report.new_videos
    assert report.templates_created >= 1
    assert report.budget_hit is None
    # every mined video carries the proxy marker
    for v in db.scalars(select(SwipeVideo)):
        assert v.signal_type == "engagement_proxy"


def test_refresh_throttles_second_run(db):
    _seed_source(db)
    service.refresh_niche(db, "beauty.skincare", top_k=5)
    # second run within the refresh window: source is throttled, nothing re-scraped
    report2 = service.refresh_niche(db, "beauty.skincare", top_k=5)
    assert report2.sources_scraped == 0
    assert report2.videos_processed == 0


def test_process_video_idempotent(db):
    from app.modules.research.models import Transcript

    _seed_source(db)
    service.refresh_niche(db, "beauty.skincare", top_k=5)
    video = db.scalars(select(SwipeVideo)).first()
    before_stages = dict(video.processed_stages)
    before_transcripts = len(list(db.scalars(select(Transcript))))

    # re-running without force must skip every completed stage (§2B.9)
    service.process_video(db, video)
    db.commit()

    assert dict(video.processed_stages) == before_stages
    assert len(list(db.scalars(select(Transcript)))) == before_transcripts


def test_get_templates_blends_operator_win_score(db):
    _seed_source(db)
    service.refresh_niche(db, "beauty.skincare", top_k=5)
    hooks = service.get_templates(db, "beauty.skincare", "hook", limit=10)
    assert hooks
    # pre-05 operator_win_score is null; ranking uses proxy only
    assert all(h.operator_win_score is None for h in hooks)

    # simulate §05 populating a real-sales signal on the lowest-proxy hook
    target = min(hooks, key=lambda h: h.proxy_score or 0)
    target.operator_win_score = 999.0
    db.commit()
    ranked = service.get_templates(db, "beauty.skincare", "hook", limit=10, operator_blend=0.9)
    assert ranked[0].id == target.id  # operator signal now dominates


def test_decay_reduces_stale_proxy(db):
    _seed_source(db)
    service.refresh_niche(db, "beauty.skincare", top_k=5)
    hook = db.scalars(select(HookTemplate)).first()
    before = float(hook.proxy_score or 0)
    # a second refresh with force triggers another decay pass
    service.refresh_niche(db, "beauty.skincare", top_k=5, force=True)
    db.refresh(hook)
    assert float(hook.proxy_score or 0) <= before
