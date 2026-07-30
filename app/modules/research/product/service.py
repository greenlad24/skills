"""Product-research orchestration (§2A.4/§2A.7): route → fetch → normalize → fallback →
download images → enrich → graceful degradation.

A scraper failure must NEVER hard-fail the job — it degrades to `degraded` or `manual`.
`research_product` is pure orchestration over injectable seams (image fetcher, llm,
swipe gender evidence) so it is fully unit-testable under DRY_RUN with no network.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config
from ..schemas import NormalizedProduct
from . import normalize as norm_mod
from .adapters import FirecrawlAdapter
from .base import AdapterError, HardBlockError
from .domain_router import route
from .images import download_images


@dataclass
class ProductResearchResult:
    product: NormalizedProduct
    images_downloaded: int
    needs_manual_images: bool
    cost_usd: float


def _try_firecrawl(url: str) -> NormalizedProduct | None:
    """One quick Firecrawl shot; None if even that fails."""
    try:
        fc = FirecrawlAdapter(url)
        return fc.normalize(fc.fetch())
    except (AdapterError, Exception):  # noqa: BLE001
        return None


def research_product(
    url: str,
    job_id: str,
    *,
    image_fetcher=None,
    media_root: str | None = None,
    llm=None,
    swipe_gender_evidence: dict[str, int] | None = None,
    probe_shopify: bool = True,
) -> ProductResearchResult:
    adapter = route(url, probe_shopify=probe_shopify)

    norm: NormalizedProduct | None
    try:
        norm = adapter.normalize(adapter.fetch())
    except HardBlockError:
        # CAPTCHA/geo/auth — one Firecrawl shot, then manual (don't hang).
        norm = _try_firecrawl(url)
    except AdapterError:
        norm = _try_firecrawl(url)
    except Exception:  # noqa: BLE001 — unexpected adapter bug must not crash research
        norm = _try_firecrawl(url)

    # Total failure → manual upload flow.
    if norm is None:
        manual = NormalizedProduct(
            source_url=url, source_platform=adapter.platform, scrape_status="manual"
        )
        return ProductResearchResult(manual, 0, needs_manual_images=True, cost_usd=0.0)

    cost = norm.cost_usd

    # Immediate, validated image download (§2A.3).
    downloaded = []
    if norm.source_images:
        downloaded = download_images(
            norm.source_images,
            job_id,
            fetcher=image_fetcher,
            media_root=media_root,
        )
    norm.images = [d.local_path for d in downloaded]

    # Enrich category/tier/voice_gender (§2A.5/§2A.6).
    norm_mod.enrich(norm, swipe_gender_evidence=swipe_gender_evidence, llm=llm)

    # Graceful degradation (§2A.7).
    needs_manual_images = False
    if not (norm.title and norm.title.strip()):
        # No title even after fallback → manual top-up (text is load-bearing).
        norm.scrape_status = "manual"
        needs_manual_images = not norm.images
    elif not norm.images:
        # Scraped fine but images unusable → degraded; approval gate can supply images.
        norm.scrape_status = "degraded"
        needs_manual_images = True
    else:
        norm.scrape_status = "ok"

    return ProductResearchResult(
        product=norm,
        images_downloaded=len(downloaded),
        needs_manual_images=needs_manual_images,
        cost_usd=cost,
    )
