"""Auto-post to TikTok via the official Content Posting API — the free `PostingProvider` (§1.6).

The Content Posting API has no per-post fee; the only cost is passing TikTok's app
review once to unlock direct publishing. Set:

    POSTING_PROVIDER=tiktok
    TIKTOK_ACCESS_TOKEN=<OAuth user token>   # video.publish (direct) or video.upload (draft) scope

Two modes (TIKTOK_POSTING_MODE):
  * "direct"  — publishes straight to the profile (needs an audited app + video.publish).
  * "inbox"   — uploads to the creator's TikTok drafts; they tap "post" in the app
                (works with an UNAUDITED app + video.upload — good for early testing).

AI disclosure: `ai_disclosure=True` sets the post's `is_aigc` flag, satisfying
TikTok's AI-generated-content labeling requirement (important — undisclosed AI
caught by detection is penalized harder; disclosed AI stays monetization-eligible).

Flow (FILE_UPLOAD): query creator_info → publish init (get publish_id + upload_url)
→ PUT the mp4 bytes → return publish_id as external_post_id. TikTok finishes
processing asynchronously; poll status with the same publish_id.

Note: TikTok's public API does not schedule posts, so `schedule_at` is recorded but
not honored here (post now); and post analytics live behind a different scope
(Display/Research API), so `fetch_metrics` returns a clear not-supported result
rather than fabricating numbers.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from app.core.adapters.base import ProviderResult
from app.core.adapters.registry import register_real
from app.core.config import settings

_UPLOAD_CHUNK = 64 * 1024 * 1024   # 64MB; short clips are one chunk


class TikTokPostingProvider:
    """Free `PostingProvider` backed by the official TikTok Content Posting API."""

    provider_name = "tiktok-content-posting"

    def __init__(self) -> None:
        if not settings.TIKTOK_ACCESS_TOKEN:
            raise RuntimeError(
                "TIKTOK_ACCESS_TOKEN is not set. Complete TikTok OAuth to obtain a user "
                "access token, or set DRY_RUN=true for the fake provider."
            )
        self._token = settings.TIKTOK_ACCESS_TOKEN
        self._base = settings.TIKTOK_API_BASE.rstrip("/")
        self._mode = (settings.TIKTOK_POSTING_MODE or "direct").lower()
        self._privacy = settings.TIKTOK_PRIVACY_LEVEL

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    # -- PostingProvider ----------------------------------------------------- #

    def publish(
        self, *, video_key: str, caption: str, platform: str, ai_disclosure: bool,
        schedule_at: str | None, idempotency_key: str,
    ) -> ProviderResult:
        try:
            video_bytes = self._read_bytes(video_key)
        except OSError as exc:
            return ProviderResult(ok=False, error=f"tiktok: cannot read video: {exc}")

        try:
            with httpx.Client(base_url=self._base, timeout=120, headers=self._headers) as c:
                privacy = self._privacy or self._first_allowed_privacy(c)
                publish_id, upload_url = self._init(c, caption, ai_disclosure, privacy, len(video_bytes))
                self._upload(upload_url, video_bytes)
        except httpx.HTTPError as exc:
            return ProviderResult(ok=False, error=f"tiktok publish http error: {exc}")
        except (KeyError, ValueError) as exc:
            return ProviderResult(ok=False, error=f"tiktok publish bad response: {exc}")

        return ProviderResult(
            ok=True,
            data={
                "external_post_id": publish_id,
                "post_url": None,                 # assigned by TikTok after processing
                "ai_disclosure_set": bool(ai_disclosure),
                "platform": platform or "tiktok",
                "mode": self._mode,
                "schedule_ignored": schedule_at,  # API doesn't schedule; recorded for transparency
            },
            cost_usd=0.0,                         # official API has no per-post fee
            usage={},
            provider_job_id=publish_id,
        )

    def fetch_metrics(self, *, external_post_id: str) -> ProviderResult:
        # Content Posting API can report publish STATUS but not view/like analytics;
        # metrics need the Display API / Research API (different scopes). Report the
        # processing status rather than inventing engagement numbers.
        try:
            with httpx.Client(base_url=self._base, timeout=30, headers=self._headers) as c:
                r = c.post("/v2/post/publish/status/fetch/",
                           json={"publish_id": external_post_id})
                r.raise_for_status()
                status = (r.json().get("data") or {}).get("status")
        except httpx.HTTPError as exc:
            return ProviderResult(ok=False, error=f"tiktok status error: {exc}")

        return ProviderResult(
            ok=False,
            data={"publish_status": status},
            error="tiktok Content Posting API does not expose engagement metrics; "
                  "use the Display/Research API scope for views/likes.",
        )

    # -- helpers ------------------------------------------------------------- #

    def _init(self, c: httpx.Client, caption: str, ai_disclosure: bool, privacy: str,
              size: int) -> tuple[str, str]:
        source_info = {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": min(size, _UPLOAD_CHUNK),
            "total_chunk_count": 1,
        }
        if self._mode == "inbox":
            # Draft upload: no post_info allowed; creator posts from the app.
            path = "/v2/post/publish/inbox/video/init/"
            body: dict = {"source_info": source_info}
        else:
            path = "/v2/post/publish/video/init/"
            body = {
                "post_info": {
                    "title": caption[:2200],
                    "privacy_level": privacy,
                    "disable_comment": False,
                    "disable_duet": False,
                    "disable_stitch": False,
                    "brand_content_toggle": False,
                    "brand_organic_toggle": False,
                    # AI-generated-content disclosure flag.
                    "is_aigc": bool(ai_disclosure),
                },
                "source_info": source_info,
            }
        r = c.post(path, json=body)
        r.raise_for_status()
        data = r.json()["data"]
        return data["publish_id"], data["upload_url"]

    def _upload(self, upload_url: str, video_bytes: bytes) -> None:
        size = len(video_bytes)
        headers = {
            "Content-Type": "video/mp4",
            "Content-Length": str(size),
            "Content-Range": f"bytes 0-{size - 1}/{size}",
        }
        with httpx.Client(timeout=300) as c:
            r = c.put(upload_url, content=video_bytes, headers=headers)
            r.raise_for_status()

    def _first_allowed_privacy(self, c: httpx.Client) -> str:
        """Query creator_info for an allowed privacy level (required before direct post)."""
        if self._mode == "inbox":
            return "SELF_ONLY"   # unused for inbox, but a safe default
        try:
            r = c.post("/v2/post/publish/creator_info/query/")
            r.raise_for_status()
            options = (r.json().get("data") or {}).get("privacy_level_options") or []
        except (httpx.HTTPError, ValueError):
            options = []
        for pref in ("PUBLIC_TO_EVERYONE", "FOLLOWER_OF_CREATOR", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"):
            if pref in options:
                return pref
        return options[0] if options else "SELF_ONLY"

    def _read_bytes(self, video_key: str) -> bytes:
        if video_key.startswith(("http://", "https://")):
            with httpx.Client(timeout=120) as c:
                r = c.get(video_key); r.raise_for_status(); return r.content
        p = Path(video_key)
        if not p.is_absolute():
            p = Path(settings.MEDIA_ROOT) / video_key
        return p.read_bytes()


# Selected when POSTING_PROVIDER=tiktok and DRY_RUN=false.
register_real("posting", "tiktok", TikTokPostingProvider)
