from __future__ import annotations

import app.core.adapters.registry as registry
from app.modules.research.product import service
from .conftest import make_png
from .fakescraper import ConfigurableScraper


def _patch_scraper(monkeypatch, scraper):
    monkeypatch.setattr(registry, "get_scraper_provider", lambda: scraper)


def _png_fetcher(url):
    # salt with the full URL so distinct URLs yield distinct bytes (no false dedupe)
    return make_png(800, 600, salt=url.encode()), "image/png"


def test_ok_path_downloads_images(monkeypatch, tmp_path):
    raw = {
        "product": {
            "title": "Bright Serum",
            "body_html": "great serum",
            "variants": [{"price": "250.00"}],
            "images": [{"src": "https://cdn/a.png"}, {"src": "https://cdn/b.png"}],
        }
    }
    _patch_scraper(monkeypatch, ConfigurableScraper(data=raw, cost=0.006))
    res = service.research_product(
        "https://shop.myshopify.com/products/serum", "jobOK",
        image_fetcher=_png_fetcher, media_root=str(tmp_path), probe_shopify=False,
    )
    p = res.product
    assert p.scrape_status == "ok"
    assert p.title == "Bright Serum"
    assert res.images_downloaded == 2
    assert p.tier and p.voice_gender
    assert res.cost_usd == 0.006


def test_degraded_when_images_unusable(monkeypatch, tmp_path):
    raw = {"title": "No Pics Product", "attributes": {"images": ["https://cdn/x.png"]}}

    def bad_fetch(url):
        raise RuntimeError("expired signed url")

    _patch_scraper(monkeypatch, ConfigurableScraper(data=raw))
    res = service.research_product(
        "https://random.example/p/1", "jobDEG", image_fetcher=bad_fetch,
        media_root=str(tmp_path),
    )
    assert res.product.scrape_status == "degraded"
    assert res.needs_manual_images is True


def test_hard_block_then_manual(monkeypatch, tmp_path):
    # scraper returns a CAPTCHA marker error → HardBlockError → firecrawl (also fails) → manual
    blocked = ConfigurableScraper(ok=False, error="captcha challenge presented")
    _patch_scraper(monkeypatch, blocked)
    res = service.research_product(
        "https://www.tiktok.com/@x/video/1", "jobHB", media_root=str(tmp_path),
    )
    assert res.product.scrape_status == "manual"
    assert res.needs_manual_images is True


def test_empty_dataset_degrades(monkeypatch, tmp_path):
    _patch_scraper(monkeypatch, ConfigurableScraper(data={}))
    res = service.research_product(
        "https://random.example/p/2", "jobEMPTY", media_root=str(tmp_path),
    )
    # empty → AdapterError → firecrawl (also empty) → None → manual
    assert res.product.scrape_status == "manual"
