"""Internal dataclasses / typed shapes for the research pipeline.

These are module-internal (not the public API schemas — those stay in
`app.core.schemas`). `NormalizedProduct` is the §2A.3 normalized shape every product
adapter maps into; the swipe dataclasses back §2B.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

# Raw platform payload is just an untyped dict returned by the ScraperProvider.
RawProduct = dict[str, Any]

ScrapeStatus = Literal["ok", "degraded", "manual"]
Tier = Literal["budget", "mid", "premium"]
VoiceGender = Literal["female", "male", "neutral"]


@dataclass
class DownloadedImage:
    local_path: str
    source_url: str
    width: int
    height: int
    fmt: str
    phash: str


@dataclass
class NormalizedProduct:
    """§2A.3 normalized product schema. All adapters map into this."""

    title: str | None = None
    bullets: list[str] = field(default_factory=list)
    description: str | None = None
    images: list[str] = field(default_factory=list)          # LOCAL paths post-download
    source_images: list[str] = field(default_factory=list)   # original remote URLs
    price: float | None = None
    currency: str = "THB"
    attributes: dict[str, Any] = field(default_factory=dict)
    category: str | None = None
    tier: Tier | None = None
    voice_gender: VoiceGender | None = None
    voice_gender_confidence: float = 0.0
    source_url: str | None = None
    source_platform: str | None = None
    scrape_status: ScrapeStatus = "ok"
    scraped_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # audit: price percentile band used, raw payload, cost
    price_band_used: str | None = None
    raw_payload: RawProduct = field(default_factory=dict)
    cost_usd: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "bullets": self.bullets,
            "description": self.description,
            "images": self.images,
            "source_images": self.source_images,
            "price": self.price,
            "currency": self.currency,
            "attributes": self.attributes,
            "category": self.category,
            "tier": self.tier,
            "voice_gender": self.voice_gender,
            "voice_gender_confidence": self.voice_gender_confidence,
            "source_url": self.source_url,
            "source_platform": self.source_platform,
            "scrape_status": self.scrape_status,
            "scraped_at": self.scraped_at,
            "price_band_used": self.price_band_used,
        }


@dataclass
class ScoredVideo:
    """A mined SwipeVideo candidate with its computed engagement proxy score."""

    tiktok_id: str
    url: str
    author_handle: str | None = None
    author_gender: str | None = None
    duration_s: float | None = None
    posted_at: datetime | None = None
    views: int = 0
    likes: int = 0
    shares: int = 0
    comments: int = 0
    saves: int = 0
    proxy_score: float = 0.0
    signal_type: str = "engagement_proxy"


@dataclass
class RefreshReport:
    """Emitted by the nightly swipe refresh (§2B.10)."""

    niche: str
    sources_scraped: int = 0
    videos_seen: int = 0
    new_videos: int = 0
    videos_processed: int = 0
    templates_created: int = 0
    templates_updated: int = 0
    spend_usd: float = 0.0
    budget_hit: str | None = None          # which cap halted the run, if any
    failures: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()
