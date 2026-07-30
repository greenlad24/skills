"""Domain router (§2A.1): classify a product URL's host → platform adapter, with a
Shopify `.json` probe and Firecrawl as the universal fallback.

$0 guarantee: the Shopify probe is a real HTTP request, so it is SKIPPED in DRY_RUN
(and whenever real ML/network is disabled) — detection then falls back to a host
heuristic (`*.myshopify.com` or an explicit hint), keeping CI network-free.
"""

from __future__ import annotations

from urllib.parse import urlparse

from app.core.config import settings

from .adapters import ADAPTER_TABLE, ADAPTERS, FirecrawlAdapter, ShopifyAdapter, _BaseAdapter


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def is_shopify(url: str, *, probe: bool = True) -> bool:
    """Cheap Shopify detection. Host heuristic always; a `.json` probe only when
    `probe` and not DRY_RUN (most Shopify stores use custom domains, so host-matching
    alone misses them — but we must not spend/network in dry-runs)."""
    host = _host(url)
    if host.endswith(".myshopify.com"):
        return True
    if not probe or settings.DRY_RUN:
        return False
    try:  # real path only
        import httpx

        probe_url = url.split("?")[0].rstrip("/") + ".json"
        with httpx.Client(timeout=8.0, follow_redirects=True) as c:
            resp = c.get(probe_url)
            if resp.status_code == 200 and "product" in resp.json():
                return True
    except Exception:  # noqa: BLE001 — probe failure just means "not shopify / unknown"
        return False
    return False


def route(url: str, *, probe_shopify: bool = True) -> _BaseAdapter:
    """Return the adapter instance for `url` (§2A.1 dispatch order)."""
    if is_shopify(url, probe=probe_shopify):
        return ShopifyAdapter(url)
    host = _host(url)
    for pattern, name in ADAPTER_TABLE:
        if pattern.search(host):
            return ADAPTERS[name](url)
    return FirecrawlAdapter(url)
