"""SocialCrawl product scraper — the approved `ScraperProvider` (§2A.2).

Why this and not a residential-proxy actor: SocialCrawl is a per-call HTTP API, so
it's fast and reliable for Thai TikTok Shop where proxy-based actors stall. Its
by-URL product endpoint is US-only, so for Thailand we use keyword SEARCH in the TH
region and take the top match — proven to return the exact product (the operator's
product title as the query resolves to the right product id at rank 0), with the
product's image URLs and THB price.

Wiring:

    SCRAPER_PROVIDER=socialcrawl
    SOCIALCRAWL_API_KEY=<your key>          # 100 free credits, 1 credit/call
    SOCIALCRAWL_REGION=TH

Contract: `scrape_product(url=...)` receives the operator's search seed (the Thai
product title / keyword) as `url` and returns `data` shaped for the research
`_BaseAdapter.normalize` — top-level `title`, `description`, `price`, `currency`,
`images` (remote URL strings), `attributes`, `category`.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.core.adapters.base import ProviderResult
from app.core.adapters.registry import register_real
from app.core.config import settings

# A TikTok Shop product id is a long run of digits (e.g. in /product/<id> or /pdp/<id>).
_PRODUCT_ID_RE = re.compile(r"(\d{15,})")

# ByteImg/TikTok CDN resize template, e.g. "~tplv-aphluv4xwc-crop-webp:400:400.webp".
# The ":W:H" is a rendition size we can raise for a higher-resolution image.
_TPLV_SIZE_RE = re.compile(r"(~tplv-[^:/?]+):\d+:\d+(\.\w+)")


def _hires_url(url: str, size: int) -> str | None:
    """Rewrite a ByteImg resize template to `size`×`size`; None if it doesn't apply."""
    if size <= 0 or not isinstance(url, str):
        return None
    new = _TPLV_SIZE_RE.sub(rf"\g<1>:{size}:{size}\g<2>", url, count=1)
    return new if new != url else None


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


def _images_of(item: dict[str, Any], hires_size: int = 0) -> list[str]:
    """Collect product image URLs, high-resolution variant first (original as fallback).

    For each CDN URL we prepend a higher-res rendition (rewritten resize template) so
    the hero reference is crisp; the original stays right after it so the LTX hero step
    can fall back if a hi-res variant is ever rejected.
    """
    out: list[str] = []

    def _add(u: str) -> None:
        if not (isinstance(u, str) and u.startswith("http")):
            return
        hi = _hires_url(u, hires_size)
        for cand in (hi, u):
            if cand and cand not in out:
                out.append(cand)

    img = item.get("image")
    if isinstance(img, dict):
        for u in img.get("url_list") or []:
            _add(u)
    # Some items carry multiple images under `images`.
    for extra in item.get("images") or []:
        if isinstance(extra, dict):
            for u in extra.get("url_list") or []:
                _add(u)
        elif isinstance(extra, str):
            _add(extra)
    return out


def _currency_of(price_info: dict[str, Any]) -> str:
    sym = _first_str(price_info.get("currency_symbol"))
    name = _first_str(price_info.get("currency_name"))
    if name:
        return name.upper()
    return {"฿": "THB", "$": "USD", "£": "GBP", "€": "EUR"}.get(sym or "", "THB")


class SocialCrawlScraperProvider:
    """`ScraperProvider` backed by SocialCrawl's TikTok Shop search (TH region)."""

    provider_name = "socialcrawl"

    def __init__(self) -> None:
        if not settings.SOCIALCRAWL_API_KEY:
            raise RuntimeError(
                "SOCIALCRAWL_API_KEY is not set. Add your SocialCrawl key in setup, or "
                "set DRY_RUN=true for the fake scraper."
            )
        self._base = settings.SOCIALCRAWL_BASE.rstrip("/")
        self._region = (settings.SOCIALCRAWL_REGION or "TH").upper()
        self._headers = {"x-api-key": settings.SOCIALCRAWL_API_KEY}
        self._est_per_credit = float(settings.SOCIALCRAWL_EST_USD_PER_CALL)
        self._image_size = int(settings.SOCIALCRAWL_IMAGE_SIZE)

    # -- ScraperProvider ----------------------------------------------------- #

    def scrape_product(self, *, url: str, idempotency_key: str) -> ProviderResult:
        """`url` is the operator's search seed (Thai product title / keyword)."""
        query = (url or "").strip()
        if not query:
            return ProviderResult(ok=False, error="socialcrawl needs a product title/keyword to search")

        body = self._search(query)
        if isinstance(body, ProviderResult):  # error passthrough
            return body
        items = (((body.get("data") or {}).get("items")) or [])
        if not items:
            return ProviderResult(ok=False, error="socialcrawl search returned no products")

        # If the seed carries a product id, prefer that exact item; else take the top hit.
        want_id = None
        m = _PRODUCT_ID_RE.search(query)
        if m:
            want_id = m.group(1)
        item = None
        if want_id:
            item = next((it for it in items if str(it.get("product_id")) == want_id), None)
        if item is None:
            item = items[0]

        price_info = item.get("product_price_info") or {}
        images = _images_of(item, hires_size=self._image_size)
        rate = item.get("rate_info") or {}
        seller = item.get("seller_info") or {}
        seo = item.get("seo_url") or {}

        data = {
            "source_url": _first_str(seo.get("canonical_url")) or query,
            "title": _first_str(item.get("title")),
            "description": _first_str(item.get("product_description")),
            "price": _to_float(price_info.get("sale_price_decimal") or price_info.get("single_product_price_decimal")),
            "currency": _currency_of(price_info),
            "images": images,
            "attributes": {
                "images": images,
                "brand": _first_str(seller.get("shop_name")),
                "vendor": _first_str(seller.get("shop_name")),
                "product_id": _first_str(str(item.get("product_id"))),
                "original_price": _to_float(price_info.get("origin_price_decimal")),
                "discount": _first_str(price_info.get("discount_format")),
                "rating": rate.get("score"),
                "sold_count": (item.get("sold_info") or {}).get("sold_count"),
            },
            "category": None,
        }
        credits = int(body.get("credits_used") or 1)
        return ProviderResult(
            ok=True, data=data, cost_usd=round(credits * self._est_per_credit, 6),
            usage={"credits": credits, "images": len(images),
                   "matched_id": bool(want_id and item.get("product_id") and str(item.get("product_id")) == want_id)},
        )

    def mine_top_videos(
        self, *, query: str, market: str, limit: int, idempotency_key: str
    ) -> ProviderResult:
        """Best-effort trend signal: top TH products for a query, ranked by sold_count."""
        body = self._search(query)
        if isinstance(body, ProviderResult):
            return body
        items = (((body.get("data") or {}).get("items")) or [])
        items = sorted(
            items, key=lambda it: (it.get("sold_info") or {}).get("sold_count") or 0, reverse=True
        )[: max(1, int(limit))]
        vids = []
        for it in items:
            seo = it.get("seo_url") or {}
            vids.append({
                "tiktok_id": _first_str(str(it.get("product_id"))) or "",
                "url": _first_str(seo.get("canonical_url")) or "",
                "views": (it.get("sold_info") or {}).get("sold_count") or 0,
                "signal_type": "sold_count_proxy",
            })
        credits = int(body.get("credits_used") or 1)
        return ProviderResult(
            ok=True, data={"videos": vids}, cost_usd=round(credits * self._est_per_credit, 6),
            usage={"credits": credits, "videos": len(vids)},
        )

    # -- helpers ------------------------------------------------------------- #

    def _search(self, query: str) -> dict[str, Any] | ProviderResult:
        params = {"region": self._region, "page": 1, "query": query}
        try:
            with httpx.Client(timeout=60) as c:
                r = c.get(f"{self._base}/tiktokshop/search", params=params, headers=self._headers)
                r.raise_for_status()
                body = r.json()
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            hint = " (check SOCIALCRAWL_API_KEY)" if code in (401, 403) else ""
            return ProviderResult(ok=False, error=f"socialcrawl HTTP {code}{hint}")
        except httpx.HTTPError as exc:
            return ProviderResult(ok=False, error=f"socialcrawl request error: {exc}")
        except ValueError as exc:
            return ProviderResult(ok=False, error=f"socialcrawl bad response: {exc}")
        if not isinstance(body, dict) or not body.get("success", True):
            return ProviderResult(ok=False, error="socialcrawl returned an error envelope")
        return body


# Selected when SCRAPER_PROVIDER=socialcrawl and DRY_RUN=false.
register_real("scraper", "socialcrawl", SocialCrawlScraperProvider)
