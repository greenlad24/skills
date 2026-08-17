"""Apify product scraper — the real `ScraperProvider` (§2A.2).

Generic crawlers (Firecrawl) can't get past TikTok's bot wall, and TikTok Shop
short links (`vt.tiktok.com/...`) redirect through JS, so the product photo the
image-to-video step needs never comes back. Apify runs purpose-built actors that
resolve the link server-side (residential proxies) and return the product text
*and* image URLs.

Wiring:

    SCRAPER_PROVIDER=apify
    APIFY_API_KEY=<your Apify token>
    # optional overrides:
    APIFY_TIKTOK_SHOP_ACTOR=webdatalabs~tiktok-shop-scraper    # product/shop URLs (TH)
    APIFY_TIKTOK_VIDEO_ACTOR=clockworks~tiktok-scraper         # plain video links
    APIFY_TIKTOK_REGION=th                                     # Thai storefront/proxy
    APIFY_GENERIC_ACTOR=<username~actor for non-TikTok URLs>   # blank => manual

Cost: Apify bills prepaid platform credits (free tier ~$5/mo), which easily covers
~90 scrapes/month. We record a small per-scrape ESTIMATE on the ledger
(`APIFY_EST_USD_PER_SCRAPE`); real out-of-pocket stays inside the free credit.

Output contract: `scrape_product` returns `data` shaped for the research
`_BaseAdapter.normalize` — top-level `title`, `description`, `price`, `currency`,
`images` (list of remote URL strings), `attributes`, `category`. The mapping is
deliberately defensive because actor payloads vary field-by-field.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.adapters.base import ProviderResult
from app.core.adapters.registry import register_real
from app.core.config import settings

_APIFY_BASE = "https://api.apify.com/v2"

# Keys that commonly carry an image URL across TikTok/e-commerce actor payloads.
_IMAGE_KEYS = (
    "coverUrl", "originalCoverUrl", "dynamicCover", "cover", "originalCover",
    "displayImage", "imageUrl", "image", "thumbnail", "thumbnailUrl", "src", "url",
)
# Containers that hold nested image objects/urls.
_IMAGE_CONTAINERS = ("videoMeta", "video", "product", "covers", "images", "imageList", "media")


def _is_tiktok(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return "tiktok" in host


def _is_tiktok_shop(url: str) -> bool:
    """A TikTok Shop product/shop/category URL (needs the Shop actor, not the video one).

    Short links (vt.tiktok.com) are opaque until resolved, so they are treated as
    videos here; a real Shop *product* URL exposes /product|/view/product|/shop or
    the shop.tiktok.com host.
    """
    u = url.lower()
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("shop.tiktok.") or host.endswith(".shop.tiktok.com"):
        return True
    return any(m in u for m in ("/product/", "/view/product", "tiktok.com/shop", "/shop/"))


def _looks_like_image(value: str) -> bool:
    v = value.lower()
    return v.startswith(("http://", "https://")) and (
        any(ext in v for ext in (".jpg", ".jpeg", ".png", ".webp", ".heic"))
        or "image" in v
        or "cover" in v
        or "/img" in v
    )


def _harvest_images(node: Any, out: list[str], depth: int = 0) -> None:
    """Walk a dataset item collecting plausible image URLs (bounded recursion)."""
    if depth > 4 or len(out) >= 6:
        return
    if isinstance(node, str):
        if _looks_like_image(node) and node not in out:
            out.append(node)
        return
    if isinstance(node, list):
        for item in node:
            _harvest_images(item, out, depth + 1)
        return
    if isinstance(node, dict):
        for key in _IMAGE_KEYS:
            val = node.get(key)
            if isinstance(val, str) and val.startswith("http") and val not in out:
                out.append(val)
        for key in _IMAGE_CONTAINERS:
            if key in node:
                _harvest_images(node[key], out, depth + 1)


def _render_input(template: str, url: str, region: str) -> dict[str, Any]:
    """Render an APIFY_INPUT JSON template, substituting {url}/{region}/{REGION}.

    Falls back to a minimal `{"startUrls":[{"url": url}]}` if the template is blank
    or not valid JSON, so a typo never hard-fails the scrape.
    """
    if not template.strip():
        return {"startUrls": [{"url": url}]}
    filled = (
        template.replace("{url}", url)
        .replace("{region}", region)
        .replace("{REGION}", region.upper())
    )
    try:
        parsed = json.loads(filled)
        return parsed if isinstance(parsed, dict) else {"startUrls": [{"url": url}]}
    except ValueError:
        return {"startUrls": [{"url": url}]}


def _first_str(*vals: Any) -> str | None:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("฿", "").strip())
    except (ValueError, TypeError):
        return None


class ApifyScraperProvider:
    """`ScraperProvider` backed by Apify actors (TikTok-first, generic optional)."""

    provider_name = "apify"

    def __init__(self) -> None:
        if not settings.APIFY_API_KEY:
            raise RuntimeError(
                "APIFY_API_KEY is not set. Add your Apify token in setup, or set "
                "DRY_RUN=true for the fake scraper."
            )
        self._token = settings.APIFY_API_KEY
        self._timeout = max(30, int(settings.APIFY_SYNC_TIMEOUT_SECONDS))
        self._est_cost = float(settings.APIFY_EST_USD_PER_SCRAPE)

    # -- ScraperProvider ----------------------------------------------------- #

    def scrape_product(self, *, url: str, idempotency_key: str) -> ProviderResult:
        region = (settings.APIFY_TIKTOK_REGION or "th").lower()

        # Universal override: any manually-tested actor + input, no code change.
        if settings.APIFY_ACTOR:
            actor = settings.APIFY_ACTOR
            run_input = _render_input(settings.APIFY_INPUT, url, region)
            items = self._run_actor(actor, run_input)
            return self._items_to_result(items, url, actor)

        if _is_tiktok_shop(url):
            # Real TikTok Shop product/shop URL -> the reliable Shop actor (TH market).
            # The Thai storefront is selected by routing through a Thai RESIDENTIAL
            # proxy (apifyProxyCountry), NOT a country field.
            actor = settings.APIFY_TIKTOK_SHOP_ACTOR
            run_input = {
                "mode": "product",
                "productUrls": [url],
                "maxResults": 1,
                "proxyConfiguration": {
                    "useApifyProxy": True,
                    "apifyProxyGroups": ["RESIDENTIAL"],
                    "apifyProxyCountry": region.upper(),  # e.g. "TH"
                },
            }
        elif _is_tiktok(url):
            # A plain video link (incl. vt.tiktok.com short links) -> video actor;
            # its cover image serves as the product reference.
            actor = settings.APIFY_TIKTOK_VIDEO_ACTOR
            run_input = {
                "postURLs": [url],
                "resultsPerPage": 1,
                "shouldDownloadCovers": False,
                "shouldDownloadVideos": False,
                "shouldDownloadSubtitles": False,
            }
        else:
            actor = settings.APIFY_GENERIC_ACTOR
            if not actor:
                return ProviderResult(
                    ok=False,
                    error="apify has no generic actor configured for this URL; set "
                    "APIFY_GENERIC_ACTOR or supply a product image URL manually.",
                )
            run_input = {"startUrls": [{"url": url}], "country": region}

        items = self._run_actor(actor, run_input)
        return self._items_to_result(items, url, actor)

    def _items_to_result(
        self, items: list[Any] | ProviderResult, url: str, actor: str
    ) -> ProviderResult:
        """Map an Apify dataset (defensively, field names vary) into a scrape result."""
        if isinstance(items, ProviderResult):  # error passthrough
            return items
        if not items:
            return ProviderResult(ok=False, error="apify returned an empty dataset")

        item = items[0] if isinstance(items[0], dict) else {}
        images: list[str] = []
        _harvest_images(item, images)

        title = _first_str(
            item.get("title"),
            item.get("name"),
            item.get("productName"),
            (item.get("text") or "")[:90] if item.get("text") else None,
        )
        description = _first_str(
            item.get("description"), item.get("text"), item.get("desc"),
            item.get("caption"),
        )
        data = {
            "source_url": url,
            "title": title,
            "description": description,
            "price": _to_float(item.get("price") or item.get("priceValue")),
            "currency": _first_str(item.get("currency")) or "THB",
            "images": images,
            "attributes": {
                "images": images,
                "author": (item.get("authorMeta") or {}).get("name")
                if isinstance(item.get("authorMeta"), dict) else item.get("author"),
                "hashtags": [
                    h.get("name") if isinstance(h, dict) else h
                    for h in (item.get("hashtags") or [])
                ][:12],
            },
            "category": _first_str(item.get("category")),
        }
        return ProviderResult(
            ok=True, data=data, cost_usd=self._est_cost,
            usage={"actor": actor, "items": len(items), "images": len(images)},
        )

    def mine_top_videos(
        self, *, query: str, market: str, limit: int, idempotency_key: str
    ) -> ProviderResult:
        actor = settings.APIFY_TIKTOK_VIDEO_ACTOR
        run_input = {
            "searchQueries": [query],
            "resultsPerPage": max(1, min(int(limit), 30)),
            "shouldDownloadCovers": False,
            "shouldDownloadVideos": False,
        }
        items = self._run_actor(actor, run_input)
        if isinstance(items, ProviderResult):
            return items
        videos = []
        for i, it in enumerate(items[: max(1, int(limit))]):
            if not isinstance(it, dict):
                continue
            meta = it.get("videoMeta") if isinstance(it.get("videoMeta"), dict) else {}
            videos.append(
                {
                    "tiktok_id": _first_str(it.get("id"), str(i)),
                    "url": _first_str(it.get("webVideoUrl"), it.get("url")) or "",
                    "views": it.get("playCount") or it.get("views") or 0,
                    "signal_type": "engagement_proxy",
                    "cover": meta.get("coverUrl"),
                }
            )
        return ProviderResult(
            ok=True, data={"videos": videos}, cost_usd=self._est_cost,
            usage={"actor": actor, "videos": len(videos)},
        )

    # -- helpers ------------------------------------------------------------- #

    def _run_actor(self, actor: str, run_input: dict[str, Any]) -> list[Any] | ProviderResult:
        """Run an actor synchronously and return its dataset items (or an error result)."""
        endpoint = f"{_APIFY_BASE}/acts/{actor}/run-sync-get-dataset-items"
        params = {"token": self._token, "timeout": str(self._timeout)}
        try:
            with httpx.Client(timeout=self._timeout + 15) as c:
                r = c.post(endpoint, params=params, json=run_input)
                r.raise_for_status()
                body = r.json()
        except httpx.HTTPStatusError as exc:
            return ProviderResult(
                ok=False, error=f"apify actor {actor} HTTP {exc.response.status_code}"
            )
        except httpx.HTTPError as exc:
            return ProviderResult(ok=False, error=f"apify actor {actor} error: {exc}")
        except ValueError as exc:
            return ProviderResult(ok=False, error=f"apify bad response: {exc}")
        if not isinstance(body, list):
            return ProviderResult(ok=False, error="apify response was not a dataset array")
        return body


# Selected when SCRAPER_PROVIDER=apify and DRY_RUN=false.
register_real("scraper", "apify", ApifyScraperProvider)
