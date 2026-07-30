"""Product adapter interface + error taxonomy (§2A.4).

Every per-platform adapter implements `fetch()` (raw platform payload) and
`normalize(raw)` (→ NormalizedProduct). The ACTUAL network call inside `fetch()` goes
through `app.core.adapters.registry.get_scraper_provider()` — the module never imports a
vendor SDK. Each adapter passes a `platform` hint so a real ScraperProvider can dispatch
to the right actor/endpoint (Apify / Rainforest / ScrapFly / Firecrawl); in DRY_RUN the
fake provider returns deterministic data and spends $0.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..schemas import NormalizedProduct, RawProduct


class AdapterError(Exception):
    """Recoverable: the router should try the Firecrawl fallback once."""


class HardBlockError(AdapterError):
    """CAPTCHA / auth wall / geo-block — fallback unlikely to help; go manual faster."""


@runtime_checkable
class ProductAdapter(Protocol):
    platform: str
    url: str

    def fetch(self) -> RawProduct:  # raw platform payload → dict
        ...

    def normalize(self, raw: RawProduct) -> NormalizedProduct:
        ...
