import importlib
import json
from datetime import datetime, timedelta

import pytest
from fixtures import sample_plan


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TTS_STUDIO_HOME", str(tmp_path / "home"))
    import studio.config as config
    importlib.reload(config)
    import studio.projects as projects
    importlib.reload(projects)
    import studio.scheduler as scheduler
    importlib.reload(scheduler)
    made = []
    for name in ("ที่นอน", "ครีม"):
        pid = projects.new_project(name)["id"]
        d = projects.pdir(pid)
        plan = sample_plan()
        plan["videos"][0]["post_caption_th"] = "ที่นอนนุ่มมาก ราคาแค่ 2,990 บาท"
        plan["videos"][0]["hashtags"] = ["ที่นอน", "#นายหน้า", "solomon"]
        (d / "plan.json").write_text(json.dumps(plan, ensure_ascii=False))
        for f in ("V1_bouncy_100000.mp4", "V1_punchy_100001.mp4", "V2_smooth_100002.mp4", "V1_bouncy_draft_100003.mp4"):
            (d / "renders" / f).write_bytes(b"\x00" * 100)
        made.append(pid)
    return scheduler, projects, made


def test_finished_videos_skip_drafts(env):
    scheduler, _, made = env
    vids = scheduler.finished_videos()
    assert len(vids) == 6 and not any("draft" in v["render"] for v in vids)


def test_auto_schedule_best_slots_alternating(env):
    scheduler, _, made = env
    start = datetime(2026, 10, 12, 9, 0, tzinfo=scheduler.BKK)       # a Monday morning
    posts = scheduler.auto_schedule(per_day=1, start=start)
    assert len(posts) == 6
    times = [p["at"] for p in posts]
    assert times[0] == "2026-10-12T20:00" and times[1] == "2026-10-13T20:00"   # Mon/Tue 20:00
    assert all(t.endswith(("20:00", "20:30", "19:00")) for t in times)        # slot #1 of each day
    assert posts[0]["project_id"] != posts[1]["project_id"]                   # products alternate
    # the A/B version of the same video waits ≥ 2 days
    by = {}
    for p in posts:
        by.setdefault((p["project_id"], p["video_id"]), []).append(scheduler._parse(p["at"]))
    for ts in by.values():
        ts.sort()
        assert all((b.date() - a.date()).days >= 2 for a, b in zip(ts, ts[1:]))
    assert scheduler.auto_schedule(per_day=1, start=start) == []              # nothing left to add


def test_two_per_day_spacing(env):
    scheduler, _, _ = env
    posts = scheduler.auto_schedule(per_day=2, start=datetime(2026, 10, 12, 9, 0, tzinfo=scheduler.BKK))
    ts = sorted(scheduler._parse(p["at"]) for p in posts)
    assert all((b - a) >= timedelta(hours=3) for a, b in zip(ts, ts[1:]))
    assert ts[0].strftime("%H:%M") == "12:15"


def test_caption_has_no_price_and_good_tags(env):
    scheduler, _, _ = env
    p = scheduler.auto_schedule(per_day=1, start=datetime(2026, 10, 12, 9, 0, tzinfo=scheduler.BKK))[0]
    assert "2,990" not in p["caption"] and "บาท" not in p["caption"]
    assert "ตะกร้า" in p["caption"]                                          # one clear CTA
    assert 3 <= len(p["hashtags"]) <= 5 and "#นายหน้า" not in p["hashtags"]
    assert p["hashtags"][0] == "#ที่นอน"


def test_tick_hands_posts_to_postpeer(env, monkeypatch):
    scheduler, _, _ = env
    calls = []
    monkeypatch.setattr(scheduler.cloudinary_host, "upload_video",
                        lambda path, cfg, pid: {"url": f"https://res.cloudinary.com/x/{pid}.mp4", "public_id": pid})
    monkeypatch.setattr(scheduler.postpeer, "create_post",
                        lambda key, acct, text, url, when, tz, mode: calls.append((acct, text, url, when, tz, mode))
                        or {"id": f"pp{len(calls)}", "url": ""})
    monkeypatch.setattr(scheduler.postpeer, "scheduled", lambda key: [{"id": "pp2"}])
    st = {"postpeer_key": "k", "postpeer_account_id": "tt_1", "postpeer_mode": "inbox",
          "cloudinary_url": "cloudinary://a:b@c"}
    start = scheduler.now_bkk() + timedelta(hours=1)
    posts = scheduler.auto_schedule(per_day=1, start=start)
    scheduler.tick(st)
    assert len(calls) == len(posts)                                           # permanent links → all queued
    acct, text, url, when, tz, mode = calls[0]
    assert acct == "tt_1" and tz == "Asia/Bangkok" and mode == "inbox" and url.startswith("https://res.cloudinary")
    assert "#" in text and when == posts[0]["at"]
    data = scheduler.load()["posts"]
    assert all(p["status"] == "queued" for p in data)
    # time passes: pp1 left PostPeer's queue → posted; pp2 still waiting
    for p in data:
        scheduler._update(p["id"], at=scheduler._fmt(scheduler.now_bkk() - timedelta(hours=2)))
    scheduler.tick(st)
    st_by_pp = {p["postpeer_id"]: p["status"] for p in scheduler.load()["posts"]}
    assert st_by_pp["pp1"] == "posted" and st_by_pp["pp2"] == "queued"


def test_litterbox_only_hands_over_within_48h(env, monkeypatch):
    scheduler, _, _ = env
    sent = []
    monkeypatch.setattr(scheduler.media_host, "upload_litterbox", lambda path: "https://litter.catbox.moe/x.mp4")
    monkeypatch.setattr(scheduler.postpeer, "create_post", lambda *a: sent.append(a) or {"id": "p", "url": ""})
    scheduler.auto_schedule(per_day=1, start=scheduler.now_bkk() + timedelta(hours=1))
    scheduler.tick({"postpeer_key": "k", "postpeer_account_id": "tt"})
    soon = [p for p in scheduler.load()["posts"] if scheduler._parse(p["at"]) - scheduler.now_bkk() <= timedelta(hours=48)]
    assert len(sent) == len(soon) < 6


def test_edit_requeues_and_strips_price(env, monkeypatch):
    scheduler, _, _ = env
    cancelled = []
    monkeypatch.setattr(scheduler.postpeer, "cancel", lambda key, pid: cancelled.append(pid))
    p = scheduler.auto_schedule(per_day=1, start=datetime(2026, 10, 12, 9, 0, tzinfo=scheduler.BKK))[0]
    scheduler._update(p["id"], status="queued", postpeer_id="pp9")
    q = scheduler.edit(p["id"], at="2026-10-20T12:15", caption="นุ่มมาก แค่ 990 บาท", settings={"postpeer_key": "k"})
    assert cancelled == ["pp9"] and q["status"] == "planned" and q["at"] == "2026-10-20T12:15"
    assert "990" not in q["caption"]


def test_missed_posts_and_cloudinary_cleanup(env, monkeypatch):
    scheduler, _, _ = env
    deleted = []
    monkeypatch.setattr(scheduler.cloudinary_host, "delete_video", lambda cfg, pid: deleted.append(pid))
    posts = scheduler.auto_schedule(per_day=1, start=datetime(2026, 10, 12, 9, 0, tzinfo=scheduler.BKK))
    old = scheduler._fmt(scheduler.now_bkk() - timedelta(days=9))
    scheduler._update(posts[0]["id"], at=old)                              # planned but long overdue
    scheduler._update(posts[1]["id"], at=old, status="posted", cloudinary_id="c1")
    scheduler.tick({"postpeer_key": "k", "postpeer_account_id": "tt", "cloudinary_url": "cloudinary://a:b@c"})
    s = {p["id"]: p for p in scheduler.load()["posts"]}
    assert s[posts[0]["id"]]["status"] == "missed" and deleted == ["c1"] and s[posts[1]["id"]]["cloudinary_id"] == ""


def test_cloudinary_signature():
    from studio import cloudinary_host
    # Cloudinary docs example: sha1("eager=w_400,h_300,c_pad|w_260,h_200,c_crop&public_id=sample_image&timestamp=1315060510abcd")
    sig = cloudinary_host._sign({"timestamp": "1315060510", "public_id": "sample_image",
                                 "eager": "w_400,h_300,c_pad|w_260,h_200,c_crop"}, "abcd")
    assert sig == "bfd09f95f331f558cbd1320e67aa8d488770583e"
    c = cloudinary_host.parse_url("cloudinary://123:abc@my-cloud")
    assert c == {"api_key": "123", "api_secret": "abc", "cloud": "my-cloud"}
    with pytest.raises(cloudinary_host.CloudinaryError):
        cloudinary_host.parse_url("nonsense")


def test_deleting_product_cancels_its_posts(env, monkeypatch):
    scheduler, projects, made = env
    cancelled = []
    monkeypatch.setattr(scheduler.postpeer, "cancel", lambda key, pid: cancelled.append(pid))
    posts = scheduler.auto_schedule(per_day=1, start=datetime(2026, 10, 12, 9, 0, tzinfo=scheduler.BKK))
    mine = [p for p in posts if p["project_id"] == made[0]]
    scheduler._update(mine[0]["id"], status="queued", postpeer_id="pp1")
    assert scheduler.cancel_project(made[0], {"postpeer_key": "k"}) == len(mine)
    st = {p["id"]: p["status"] for p in scheduler.load()["posts"]}
    assert all(st[p["id"]] == "cancelled" for p in mine) and cancelled == ["pp1"]
    assert all(st[p["id"]] == "planned" for p in posts if p["project_id"] != made[0])
