"""Tool 3 — TikTok post scheduler: best-time calendar, auto captions, PostPeer publishing.

The schedule lives in ~/ThaiTikTokStudio/schedule.json. A background worker hands each
post to PostPeer (as a TikTok inbox draft by default, so you can add the product basket),
uploading the video to a public link first. All times are Bangkok time (UTC+7, no DST).
"""

from __future__ import annotations

import json
import random
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import cloudinary_host, config, media_host, postpeer, projects
from .plan_schema import PRICE_RE, strip_caption_price

BKK = timezone(timedelta(hours=7))
TZ_NAME = "Asia/Bangkok"
STORE = lambda: config.HOME / "schedule.json"  # noqa: E731  (HOME can change in tests)
_LOCK = threading.RLock()

# Best Thai posting slots (Bangkok time) per weekday, best first. Mon=0 … Sun=6.
# Evidence (frameworks/posting_times.md): Thai TikTok Shop buying peaks 19:30–22:30 and
# lunch 12:00–13:30; 20:00 is the core slot; Tue–Thu strongest; weekends start earlier.
SLOTS = {
    0: ["20:00", "12:15", "18:30"],
    1: ["20:00", "12:15", "18:30"],
    2: ["20:00", "12:15", "21:00"],
    3: ["20:00", "12:15", "07:30"],
    4: ["20:30", "12:15", "18:30"],
    5: ["19:00", "10:00", "13:00"],
    6: ["20:00", "10:00", "13:00"],
}
MIN_GAP_H = 3
SUBMIT_AHEAD_H_LOCAL = 48      # Litterbox links last 72 h → hand over at most 48 h early
MISSED_AFTER_MIN = 30

BASE_TAGS = ["#tiktokshop", "#ป้ายยา", "#ของดีบอกต่อ"]
NEVER_TAGS = {"#นายหน้า", "#นายหน้าtiktokshop", "#นายหน้าติ๊กต็อก"}   # reach affiliates, not buyers
CTAS = ["👉 กดตะกร้าดูราคาพิเศษได้เลย", "🛒 จิ้มตะกร้าเหลืองดูโปรตอนนี้", "ใครสนใจกดตะกร้าเลยนะ 🧺",
        "เก็บคลิปไว้ก่อน แล้วกดตะกร้าดูราคาพิเศษ ✨"]
OPENERS = ["{hook}", "{hook} 😳", "ใครกำลังหา{cat}อยู่ ต้องดูคลิปนี้ 👀", "รีวิวจริง ใช้จริง {name} ✨",
           "ของมันต้องมี! {name} 🔥"]


def now_bkk() -> datetime:
    return datetime.now(BKK)


def _fmt(dt: datetime) -> str:
    return dt.astimezone(BKK).strftime("%Y-%m-%dT%H:%M")


def _parse(s: str) -> datetime:
    return datetime.strptime(s[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=BKK)


# ------------------------------------------------------------------ store
def load() -> dict:
    with _LOCK:
        try:
            data = json.loads(STORE().read_text("utf-8"))
        except (OSError, ValueError):
            data = {}
        data.setdefault("posts", [])
        return data


def save(data: dict) -> None:
    with _LOCK:
        STORE().parent.mkdir(parents=True, exist_ok=True)
        tmp = STORE().with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(STORE())


def _update(post_id: str, **kw) -> dict | None:
    with _LOCK:
        data = load()
        for p in data["posts"]:
            if p["id"] == post_id:
                p.update(kw, updated=time.time())
                save(data)
                return p
    return None


# ------------------------------------------------------------------ captions (free, instant)
def _clean(text: str) -> str:
    text = strip_caption_price(text or "")
    text = PRICE_RE.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _tags(video: dict, research: dict, limit: int = 5) -> list:
    out = []
    for t in (video.get("hashtags") or [])[:3] + BASE_TAGS:
        t = "#" + re.sub(r"[\s#]+", "", str(t).lstrip("#"))
        if (len(t) > 1 and t.lower() not in [x.lower() for x in out] and not PRICE_RE.search(t)
                and t.lower() not in NEVER_TAGS):
            out.append(t)
    return out[:limit]


def make_caption(video: dict, research: dict, variant: int = 0) -> dict:
    """→ {"caption", "hashtags"} — hook first, no prices, one clear CTA, 3–5 hashtags."""
    hook = ""
    for b in video.get("timeline", []):
        for o in b.get("overlays", []):
            if o.get("type") == "hook_title" and o.get("text"):
                hook = o["text"]
                break
        if hook:
            break
    name = research.get("product_name") or video.get("title_th") or ""
    cat = research.get("category") or "ของดี"
    if variant == 0 and video.get("post_caption_th"):
        body = _clean(video["post_caption_th"])
    else:
        rnd = random.Random(f"{video.get('id')}:{variant}")
        opener = rnd.choice(OPENERS if hook else OPENERS[2:]).format(hook=hook, name=name, cat=cat)
        body = _clean(opener)
    if "ตะกร้า" not in body:
        body = (body + "\n" + CTAS[variant % len(CTAS)]).strip()
    return {"caption": body[:1800], "hashtags": _tags(video, research)}


def full_text(post: dict) -> str:
    return (post.get("caption", "").strip() + "\n\n" + " ".join(post.get("hashtags", []))).strip()


# ------------------------------------------------------------------ what can be posted
RENDER_RE = re.compile(r"^(V\d+)(?:_([a-z]+))?(_draft)?_\d{6}\.mp4$")


def finished_videos() -> list:
    """Every non-draft render across products, newest first per (product, video, style)."""
    out = []
    for m in projects.list_projects():
        pid = m["id"]
        d = projects.pdir(pid)
        plan = projects.load_json(d / "plan.json")
        if not plan:
            continue
        vids = {v["id"]: v for v in plan["videos"]}
        seen = set()
        for f in sorted((d / "renders").glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
            mm = RENDER_RE.match(f.name)
            if not mm or mm.group(3) or mm.group(1) not in vids:
                continue
            key = (mm.group(1), mm.group(2) or "")
            if key in seen:
                continue
            seen.add(key)
            v = vids[mm.group(1)]
            out.append({"project_id": pid, "project_name": m.get("name", ""), "video_id": v["id"],
                        "style": mm.group(2) or "", "render": f.name, "rank": v.get("rank", 9),
                        "score": v.get("score", {}).get("total", 0), "title": v.get("title_th", "")})
    return out


# ------------------------------------------------------------------ calendar
def _slots_from(start: datetime, per_day: int):
    day = start.date()
    while True:
        for hm in sorted(SLOTS[day.weekday()][:per_day]):
            h, m = map(int, hm.split(":"))
            dt = datetime(day.year, day.month, day.day, h, m, tzinfo=BKK)
            if dt >= start:
                yield dt
        day += timedelta(days=1)


def auto_schedule(per_day: int = 1, start: datetime | None = None) -> list:
    """Put every finished, not-yet-scheduled video into the next best slots.

    Order: best-ranked videos first, alternating between products so the same product
    isn't posted back to back; one extra version (A/B) of a video waits ≥ 2 days.
    """
    per_day = max(1, min(3, int(per_day)))
    start = start or (now_bkk() + timedelta(hours=1))
    with _LOCK:
        data = load()
        active = [p for p in data["posts"] if p["status"] not in ("cancelled",)]
        taken_renders = {(p["project_id"], p["render"]) for p in active}
        busy = [_parse(p["at"]) for p in active if p["status"] in ("planned", "queued")]
        todo = [v for v in finished_videos() if (v["project_id"], v["render"]) not in taken_renders]
        # round-robin by product, best rank first
        by_proj: dict = {}
        for v in sorted(todo, key=lambda v: (v["rank"], -v["score"], v["style"])):
            by_proj.setdefault(v["project_id"], []).append(v)
        queue = []
        while any(by_proj.values()):
            for pid in list(by_proj):
                if by_proj[pid]:
                    queue.append(by_proj[pid].pop(0))
        created = []
        slots = _slots_from(start, per_day)
        last_video_day: dict = {}
        for v in queue:
            for dt in slots:
                if any(abs((dt - b).total_seconds()) < MIN_GAP_H * 3600 for b in busy):
                    continue
                k = (v["project_id"], v["video_id"])
                if k in last_video_day and (dt.date() - last_video_day[k]).days < 2:
                    # A/B version of the same video: keep looking (don't burn the slot for others)
                    later = dt
                    dt = None
                    for dt2 in _slots_from(later, per_day):
                        if (dt2.date() - last_video_day[k]).days >= 2 and not any(
                                abs((dt2 - b).total_seconds()) < MIN_GAP_H * 3600 for b in busy):
                            dt = dt2
                            break
                    if dt is None:
                        continue
                    slots = _slots_from(start, per_day)   # restart scanning for the next video
                busy.append(dt)
                last_video_day[k] = dt.date()
                post = new_post(v, dt)
                data["posts"].append(post)
                created.append(post)
                break
        save(data)
    return created


def new_post(v: dict, dt: datetime) -> dict:
    plan = projects.load_json(projects.pdir(v["project_id"]) / "plan.json") or {"videos": [], "research": {}}
    video = next((x for x in plan["videos"] if x["id"] == v["video_id"]), {})
    cap = make_caption(video, plan.get("research", {}))
    return {"id": secrets.token_hex(6), "project_id": v["project_id"], "project_name": v.get("project_name", ""),
            "video_id": v["video_id"], "style": v.get("style", ""), "render": v["render"], "title": v.get("title", ""),
            "at": _fmt(dt), "caption": cap["caption"], "hashtags": cap["hashtags"], "status": "planned",
            "postpeer_id": "", "post_url": "", "media_url": "", "media_uploaded": 0, "error": "",
            "pub_token": secrets.token_urlsafe(18), "updated": time.time()}


# ------------------------------------------------------------------ publishing via PostPeer
def _render_path(p: dict) -> Path:
    return projects.pdir(p["project_id"]) / "renders" / p["render"]


def _media_url(p: dict, settings: dict) -> str:
    """Public link for the FINAL video only: own website > Cloudinary > Litterbox (72 h)."""
    base = (settings.get("public_base_url") or "").rstrip("/")
    if base:                                     # hosted website: our own permanent link
        return f"{base}/pub/{p['pub_token']}/{p['render']}"
    if settings.get("cloudinary_url"):
        if p.get("media_url") and p.get("cloudinary_id"):
            return p["media_url"]
        res = cloudinary_host.upload_video(_render_path(p), settings["cloudinary_url"],
                                           f"post-{p['id']}")
        _update(p["id"], media_url=res["url"], cloudinary_id=res["public_id"], media_uploaded=time.time())
        return res["url"]
    if p.get("media_url") and time.time() - p.get("media_uploaded", 0) < 60 * 3600:
        return p["media_url"]
    url = media_host.upload_litterbox(_render_path(p))
    _update(p["id"], media_url=url, media_uploaded=time.time())
    return url


def submit(post_id: str, settings: dict, now_: bool = False) -> dict:
    """Hand one post to PostPeer (scheduled, or immediately with now_=True)."""
    data = load()
    p = next((x for x in data["posts"] if x["id"] == post_id), None)
    if not p:
        raise ValueError("Post not found")
    if not _render_path(p).exists():
        raise ValueError("The video file was deleted — render it again or remove this post.")
    key, acct = settings.get("postpeer_key", ""), settings.get("postpeer_account_id", "")
    if not acct:
        raise postpeer.PostPeerError("Connect your TikTok account in PostPeer settings first.")
    when = None if now_ or _parse(p["at"]) <= now_bkk() + timedelta(minutes=2) else p["at"]
    url = _media_url(p, settings)
    res = postpeer.create_post(key, acct, full_text(p), url, when, TZ_NAME, settings.get("postpeer_mode", "inbox"))
    return _update(p["id"], status="queued" if when else "posted", postpeer_id=res["id"], post_url=res["url"],
                   error="")


def cancel(post_id: str, settings: dict) -> dict | None:
    p = next((x for x in load()["posts"] if x["id"] == post_id), None)
    if p and p.get("postpeer_id") and p["status"] == "queued":
        postpeer.cancel(settings.get("postpeer_key", ""), p["postpeer_id"])
    return _update(post_id, status="cancelled")


def edit(post_id: str, at: str | None = None, caption: str | None = None, hashtags: list | None = None,
         settings: dict | None = None) -> dict | None:
    """Change time/caption. A post already queued at PostPeer is cancelled there and re-queued."""
    p = next((x for x in load()["posts"] if x["id"] == post_id), None)
    if not p:
        return None
    if p["status"] == "posted":
        raise ValueError("Already posted — it can't be edited here.")
    if p["status"] == "queued" and settings:
        postpeer.cancel(settings.get("postpeer_key", ""), p["postpeer_id"])
    upd = {"status": "planned", "postpeer_id": "", "error": ""}
    if at:
        _parse(at)
        upd["at"] = at[:16]
    if caption is not None:
        upd["caption"] = _clean(caption)[:1800] if PRICE_RE.search(caption) else caption.strip()[:1800]
    if hashtags is not None:
        upd["hashtags"] = [t for t in (("#" + str(h).lstrip("#")).strip() for h in hashtags) if len(t) > 1][:10]
    return _update(post_id, **upd)


def tick(settings: dict) -> None:
    """One worker pass: hand due posts to PostPeer; mark long-overdue ones as missed."""
    if not settings.get("postpeer_key") or not settings.get("postpeer_account_id"):
        return
    hosted = bool(settings.get("public_base_url") or settings.get("cloudinary_url"))   # permanent links
    now = now_bkk()
    due = [p for p in load()["posts"] if p["status"] == "queued" and _parse(p["at"]) < now - timedelta(minutes=15)]
    if due:   # queued posts whose time has passed and are no longer in PostPeer's queue → published
        try:
            waiting = {str(x.get("id") or x.get("postId")) for x in postpeer.scheduled(settings["postpeer_key"])}
            for p in due:
                if p["postpeer_id"] not in waiting:
                    _update(p["id"], status="posted")
        except Exception:
            pass
    for p in load()["posts"]:
        if p["status"] == "posted" and p.get("cloudinary_id") and settings.get("cloudinary_url") \
                and _parse(p["at"]) < now - timedelta(days=7):
            try:   # free-plan housekeeping: remove the copy a week after it was posted
                cloudinary_host.delete_video(settings["cloudinary_url"], p["cloudinary_id"])
                _update(p["id"], cloudinary_id="", media_url="")
            except Exception:
                pass
            continue
        if p["status"] != "planned":
            continue
        at = _parse(p["at"])
        if at < now - timedelta(minutes=MISSED_AFTER_MIN):
            _update(p["id"], status="missed", error="The app was closed at post time — press “Post now”.")
            continue
        if hosted or at - now <= timedelta(hours=SUBMIT_AHEAD_H_LOCAL):
            try:
                submit(p["id"], settings)
            except Exception as e:          # keep going; show the reason on the post
                _update(p["id"], error=str(e)[:300])


_worker_started = False


def start_worker(get_settings) -> None:
    global _worker_started
    if _worker_started:
        return
    _worker_started = True

    def loop():
        while True:
            try:
                tick(get_settings())
            except Exception:
                pass
            time.sleep(60)
    threading.Thread(target=loop, daemon=True).start()
