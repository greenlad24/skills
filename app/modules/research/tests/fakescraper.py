"""A configurable fake ScraperProvider for product-adapter tests (no network)."""

from __future__ import annotations

from app.core.adapters.base import ProviderResult


class ConfigurableScraper:
    def __init__(self, *, data=None, ok=True, error=None, cost=0.005):
        self._data = data if data is not None else {}
        self._ok = ok
        self._error = error
        self._cost = cost

    def scrape_product(self, *, url: str, idempotency_key: str) -> ProviderResult:
        return ProviderResult(
            ok=self._ok, data=dict(self._data), cost_usd=self._cost, error=self._error,
            usage={"requests": 1},
        )

    def mine_top_videos(self, *, query, market, limit, idempotency_key) -> ProviderResult:
        return ProviderResult(ok=True, data={"videos": []}, cost_usd=0.0, usage={})
