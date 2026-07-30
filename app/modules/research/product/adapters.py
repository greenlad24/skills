"""Per-platform product adapters (§2A.2).

Each adapter classifies raw payloads from ONE platform and maps them into the normalized
schema. The network call in `fetch()` is delegated to the ScraperProvider from the core
registry (the only place a vendor SDK may live); a `platform` hint is passed so a real
provider can pick the right actor/endpoint (Apify TikTok Shop, Rainforest, ScrapFly,
Shopify .json, Firecrawl). In DRY_RUN the fake provider answers deterministically → $0.

Adapters raise `AdapterError` (recoverable → Firecrawl fallback) or `HardBlockError`
(CAPTCHA/geo/auth wall → skip to manual faster).
"""

from __future__ import annotations

import re
from typing import Any

from app.core.adapters import registry

from .. import config
from ..schemas import NormalizedProduct, RawProduct
from .base import AdapterError, HardBlockError

# Markers that indicate a hard block rather than a recoverable scrape miss.
_HARD_BLOCK_MARKERS = (
    "captcha", "are you a robot", "access denied", "verify you are human",
    "unusual traffic", "geo", "451", "login to continue",
)


def _scrape(url: str, platform: str, idempotency_key: str) -> RawProduct:
    """Call the ScraperProvider and surface block/empty conditions as adapter errors."""
    provider = registry.get_scraper_provider()
    res = provider.scrape_product(url=url, idempotency_key=idempotency_key)
    if not res.ok:
        err = (res.error or "").lower()
        if any(m in err for m in _HARD_BLOCK_MARKERS):
            raise HardBlockError(res.error or "hard block")
        raise AdapterError(res.error or "scrape failed")
    data = dict(res.data or {})
    if not data:
        raise AdapterError("empty dataset")
    # carry the simulated cost so the caller can meter it
    data["_cost_usd"] = res.cost_usd
    data["_platform"] = platform
    return data


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _first_str(*vals: Any) -> str | None:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


class _BaseAdapter:
    platform = "generic"

    def __init__(self, url: str) -> None:
        self.url = url

    def fetch(self) -> RawProduct:
        return _scrape(self.url, self.platform, f"research:{self.platform}:{self.url}")

    # Shared field extraction; platform subclasses override where payloads differ.
    def normalize(self, raw: RawProduct) -> NormalizedProduct:
        attrs = raw.get("attributes") or {}
        images = list(attrs.get("images") or raw.get("images") or [])
        bullets = list(attrs.get("features") or raw.get("bullets") or [])
        return NormalizedProduct(
            title=_first_str(raw.get("title"), attrs.get("title")),
            bullets=bullets,
            description=_first_str(raw.get("description"), raw.get("body_html")),
            source_images=images,
            price=_to_float(raw.get("price")),
            currency=_first_str(raw.get("currency")) or config.DEFAULT_CURRENCY,
            attributes={k: v for k, v in attrs.items() if k not in ("images", "features")},
            category=_first_str(raw.get("category"), attrs.get("category")),
            source_url=self.url,
            source_platform=self.platform,
            raw_payload=raw,
            cost_usd=float(raw.get("_cost_usd") or 0.0),
        )


class TikTokShopAdapter(_BaseAdapter):
    """Apify TikTok Shop actor via ScraperProvider (residential proxy, fragile)."""

    platform = "tiktok_shop"


class AmazonAdapter(_BaseAdapter):
    """Rainforest API (type=product) via ScraperProvider — NOT Amazon PA-API."""

    platform = "amazon"

    def normalize(self, raw: RawProduct) -> NormalizedProduct:
        norm = super().normalize(raw)
        # Rainforest nests the product; a real provider flattens it, but tolerate both.
        prod = raw.get("product") if isinstance(raw.get("product"), dict) else None
        if prod:
            norm.title = norm.title or _first_str(prod.get("title"))
            norm.price = norm.price or _to_float((prod.get("buybox_winner") or {}).get("price", {}).get("value"))
            norm.source_images = norm.source_images or [
                i.get("link") for i in (prod.get("images") or []) if i.get("link")
            ]
        return norm


class AliExpressAdapter(_BaseAdapter):
    """Apify AliExpress actor OR ScrapFly (asp=true, render_js, country=th)."""

    platform = "aliexpress"


class ShopifyAdapter(_BaseAdapter):
    """Native product JSON: {product:{title, body_html, variants[], images[]}}."""

    platform = "shopify"

    def normalize(self, raw: RawProduct) -> NormalizedProduct:
        product = raw.get("product") if isinstance(raw.get("product"), dict) else raw
        images = [
            img.get("src")
            for img in (product.get("images") or [])
            if isinstance(img, dict) and img.get("src")
        ] or list(raw.get("images") or [])
        variants = product.get("variants") or []
        price = _to_float(variants[0].get("price")) if variants and isinstance(variants[0], dict) else _to_float(product.get("price"))
        return NormalizedProduct(
            title=_first_str(product.get("title"), raw.get("title")),
            bullets=[],
            description=_first_str(product.get("body_html"), raw.get("description")),
            source_images=images,
            price=price,
            currency=_first_str(raw.get("currency"), product.get("currency")) or config.DEFAULT_CURRENCY,
            attributes={"vendor": product.get("vendor"), "product_type": product.get("product_type")},
            category=_first_str(product.get("product_type")),
            source_url=self.url,
            source_platform=self.platform,
            raw_payload=raw,
            cost_usd=float(raw.get("_cost_usd") or 0.0),
        )


class FirecrawlAdapter(_BaseAdapter):
    """Generic fallback (§2A.2). Firecrawl /scrape → markdown + structured json.

    Terminal fallback — if this is still too sparse the router goes to manual upload.
    """

    platform = "firecrawl"


ADAPTERS: dict[str, type[_BaseAdapter]] = {
    "tiktok_shop": TikTokShopAdapter,
    "amazon": AmazonAdapter,
    "aliexpress": AliExpressAdapter,
    "shopify": ShopifyAdapter,
    "firecrawl": FirecrawlAdapter,
}

# Host-pattern → adapter name (§2A.1). Shopify is detected, not host-matched.
ADAPTER_TABLE = [
    (re.compile(r"(^|\.)tiktok\.com$"), "tiktok_shop"),
    (re.compile(r"(^|\.)amazon\."), "amazon"),
    (re.compile(r"(^|\.)aliexpress\."), "aliexpress"),
]
