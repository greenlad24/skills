"""Unit tests for the SocialCrawl scraper mapping (no network)."""

from __future__ import annotations

from app.core.adapters.real import socialcrawl
from app.core.config import settings

# A trimmed real search item (SocialCrawl /tiktokshop/search, region=TH).
_ITEM = {
    "product_id": "1732795882465887718",
    "title": "LIPBUSYCARE LITE BALANCE, ชาผักผลไม้ 11-in-1",
    "image": {
        "url_list": [
            "https://p16-oec-sg.ibyteimg.com/tos/f3931612.webp?a=1",
            "https://p19-oec-sg.ibyteimg.com/tos/f3931612.webp?a=1",
        ]
    },
    "product_price_info": {
        "sale_price_decimal": "28.99",
        "origin_price_decimal": "199.00",
        "discount_format": "85%",
        "currency_symbol": "฿",
        "currency_name": "",
    },
    "rate_info": {"score": 4.6},
    "sold_info": {"sold_count": 81008},
    "seller_info": {"shop_name": "LIPBUSYCARE TH"},
    "seo_url": {"canonical_url": "https://www.tiktok.com/shop/pdp/1732795882465887718"},
}


def _body(items):
    return {"success": True, "data": {"items": items}, "credits_used": 1}


def test_helpers():
    assert socialcrawl._to_float("28.99") == 28.99
    assert socialcrawl._to_float("฿199.00") == 199.00
    assert socialcrawl._currency_of({"currency_symbol": "฿"}) == "THB"
    imgs = socialcrawl._images_of(_ITEM)
    assert imgs == [
        "https://p16-oec-sg.ibyteimg.com/tos/f3931612.webp?a=1",
        "https://p19-oec-sg.ibyteimg.com/tos/f3931612.webp?a=1",
    ]


def test_scrape_product_maps_search_item(monkeypatch):
    monkeypatch.setattr(settings, "SOCIALCRAWL_API_KEY", "k", raising=False)
    prov = socialcrawl.SocialCrawlScraperProvider()
    monkeypatch.setattr(prov, "_search", lambda q: _body([_ITEM]))

    res = prov.scrape_product(url="LIPBUSYCARE ชาผักผลไม้", idempotency_key="t")
    assert res.ok
    assert res.data["title"].startswith("LIPBUSYCARE")
    assert res.data["price"] == 28.99
    assert res.data["currency"] == "THB"
    assert len(res.data["images"]) == 2
    assert res.data["attributes"]["brand"] == "LIPBUSYCARE TH"
    assert res.data["attributes"]["product_id"] == "1732795882465887718"
    assert res.data["source_url"].endswith("1732795882465887718")
    assert res.cost_usd > 0


def test_scrape_product_prefers_exact_id_match(monkeypatch):
    monkeypatch.setattr(settings, "SOCIALCRAWL_API_KEY", "k", raising=False)
    prov = socialcrawl.SocialCrawlScraperProvider()
    other = {**_ITEM, "product_id": "9999999999999999", "title": "wrong one"}
    monkeypatch.setattr(prov, "_search", lambda q: _body([other, _ITEM]))
    # Seed carries the product id -> pick the matching item, not the top one.
    res = prov.scrape_product(
        url="https://www.tiktok.com/view/product/1732795882465887718", idempotency_key="t"
    )
    assert res.ok
    assert res.data["attributes"]["product_id"] == "1732795882465887718"


def test_empty_search_returns_not_ok(monkeypatch):
    monkeypatch.setattr(settings, "SOCIALCRAWL_API_KEY", "k", raising=False)
    prov = socialcrawl.SocialCrawlScraperProvider()
    monkeypatch.setattr(prov, "_search", lambda q: _body([]))
    res = prov.scrape_product(url="nonexistent", idempotency_key="t")
    assert not res.ok
