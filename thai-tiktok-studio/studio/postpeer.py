"""PostPeer client — publishes / schedules TikTok posts for us.

API (from postpeer.dev docs): base https://api.postpeer.dev/v1, header `x-access-key`.
  GET    /connect/tiktok            → OAuth URL to connect a TikTok account
  GET    /connect/integrations      → connected accounts (id = accountId)
  POST   /posts                     → create (publishNow or scheduledFor + timezone)
  GET    /posts/scheduled           → queued posts
  DELETE /posts/scheduled/{id}      → cancel a queued post
TikTok options go in platformSpecificData; `draft: true` sends the video to the
creator's TikTok inbox (finish there + add the product basket) and needs no audit.
Responses are parsed tolerantly because field names aren't fully documented.
"""

from __future__ import annotations

import json
import time

import requests

BASE = "https://api.postpeer.dev/v1"
TIMEOUT = 60


class PostPeerError(RuntimeError):
    pass


def _log(method: str, path: str, body, status: int, data) -> None:
    """~/ThaiTikTokStudio/logs/postpeer.log — what we sent and what PostPeer answered (never the key)."""
    try:
        from . import config
        d = config.HOME / "logs"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "postpeer.log"
        if f.exists() and f.stat().st_size > 2_000_000:
            f.write_text("")
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "req": f"{method} {path}", "body": body,
                                 "status": status, "reply": data}, ensure_ascii=False)[:4000] + "\n")
    except Exception:
        pass


def _h(key: str) -> dict:
    return {"x-access-key": key, "Content-Type": "application/json", "Accept": "application/json"}


def _call(method: str, path: str, key: str, **kw) -> dict:
    if not key:
        raise PostPeerError("Add your PostPeer API key first (PostPeer dashboard → Access Keys).")
    try:
        r = requests.request(method, BASE + path, headers=_h(key), timeout=TIMEOUT, **kw)
    except requests.RequestException as e:
        raise PostPeerError(f"Can't reach PostPeer: {e}") from e
    try:
        data = r.json() if r.content else {}
    except ValueError:
        data = {"raw": r.text[:500]}
    _log(method, path, kw.get("json"), r.status_code, data)
    if r.status_code >= 400:
        msg = ""
        if isinstance(data, dict):
            err = data.get("error")
            msg = (err.get("message") if isinstance(err, dict) else err) or data.get("message") or ""
            extra = data.get("details") or data.get("errors") or (err.get("details") if isinstance(err, dict) else None)
            if extra:                       # validation errors: which field PostPeer didn't like
                msg = f"{msg} — {json.dumps(extra, ensure_ascii=False)[:300]}"
        if r.status_code in (401, 403):
            msg = "PostPeer rejected the API key. " + str(msg or "")
        elif r.status_code == 402 or "credit" in str(msg).lower():
            msg = "PostPeer plan limit reached (out of credits). " + str(msg or "")
        raise PostPeerError(f"PostPeer {r.status_code}: {msg or str(data)[:300]}")
    return data if isinstance(data, dict) else {"data": data}


def _items(data: dict) -> list:
    for k in ("data", "integrations", "accounts", "posts", "items", "results"):
        v = data.get(k)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            for k2 in ("integrations", "accounts", "posts", "items"):
                if isinstance(v.get(k2), list):
                    return v[k2]
    return []


def connect_url(key: str, platform: str = "tiktok") -> str:
    d = _call("GET", f"/connect/{platform}", key)
    for c in (d, d.get("data") if isinstance(d.get("data"), dict) else {}):
        for k in ("url", "authUrl", "authorizationUrl", "auth_url"):
            if c.get(k):
                return c[k]
    raise PostPeerError("PostPeer didn't return a connect link.")


def accounts(key: str) -> list:
    out = []
    for a in _items(_call("GET", "/connect/integrations", key)):
        if not isinstance(a, dict):
            continue
        plat = str(a.get("platform") or a.get("provider") or a.get("type") or "").lower()
        out.append({"id": a.get("id") or a.get("accountId") or a.get("integrationId"),
                    "platform": plat,
                    "name": a.get("username") or a.get("name") or a.get("displayName") or a.get("handle") or ""})
    return [a for a in out if a["id"]]


def rfc3339(when_local: str, tz: str = "Asia/Bangkok") -> str:
    """'2026-10-14T20:00' (local) → '2026-10-14T20:00:00+07:00' — PostPeer needs a full date-time with offset."""
    from datetime import datetime, timedelta, timezone as _tz
    dt = datetime.strptime(when_local[:16], "%Y-%m-%dT%H:%M")
    try:
        from zoneinfo import ZoneInfo
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    except Exception:                      # no tz database: Bangkok is UTC+7 all year
        dt = dt.replace(tzinfo=_tz(timedelta(hours=7)))
    return dt.isoformat(timespec="seconds")


def create_post(key: str, account_id: str, caption: str, video_url: str, when_local: str | None,
                timezone: str = "Asia/Bangkok", mode: str = "inbox") -> dict:
    """mode 'inbox' = draft to TikTok inbox (add basket, tap post) · 'direct' = publish publicly."""
    psd = {"draft": True} if mode == "inbox" else {"draft": False, "privacyLevel": "PUBLIC_TO_EVERYONE"}
    body = {
        "content": caption,
        "platforms": [{"platform": "tiktok", "accountId": account_id, "platformSpecificData": psd}],
        "mediaItems": [{"type": "video", "url": video_url}],
    }
    if when_local:
        body.update({"scheduledFor": rfc3339(when_local, timezone), "timezone": timezone})
    else:
        body["publishNow"] = True
    try:
        d = _call("POST", "/posts", key, json=body)
    except PostPeerError as e:
        if mode == "inbox" or "privacy" not in str(e).lower():
            raise
        # TikTok only allows "only me" until PostPeer's app is approved for this account
        psd["privacyLevel"] = "SELF_ONLY"
        d = _call("POST", "/posts", key, json=body)
    inner = d.get("data") if isinstance(d.get("data"), dict) else d
    post_id = inner.get("postId") or inner.get("id") or d.get("postId") or d.get("id")
    if not post_id:
        raise PostPeerError(f"PostPeer accepted the request but returned no post id: {str(d)[:200]}")
    url = ""
    for p in inner.get("platforms") or []:
        if isinstance(p, dict) and p.get("platformPostUrl"):
            url = p["platformPostUrl"]
    return {"id": str(post_id), "url": url, "scheduled_utc": inner.get("scheduledFor") or ""}


def scheduled(key: str) -> list:
    return [p for p in _items(_call("GET", "/posts/scheduled", key)) if isinstance(p, dict)]


def cancel(key: str, post_id: str) -> None:
    _call("DELETE", f"/posts/scheduled/{post_id}", key)
