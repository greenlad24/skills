"""Unit tests for the Apify scraper adapter's pure logic (no network)."""

from __future__ import annotations

from app.core.adapters.real import apify


def test_url_classification():
    # Shop product/shop URLs -> Shop actor.
    assert apify._is_tiktok_shop("https://shop.tiktok.com/th/view/product/123")
    assert apify._is_tiktok_shop("https://www.tiktok.com/shop/pdp/456")
    assert apify._is_tiktok_shop("https://www.tiktok.com/view/product/789")
    # Plain video + short links are NOT shop URLs (routed to the video actor).
    assert not apify._is_tiktok_shop("https://vt.tiktok.com/ZS9kHcG8fAE3k/")
    assert not apify._is_tiktok_shop("https://www.tiktok.com/@user/video/123")
    # But they ARE tiktok.
    assert apify._is_tiktok("https://vt.tiktok.com/ZS9kHcG8fAE3k/")
    assert not apify._is_tiktok("https://shop.example/p/1")


def test_harvest_images_walks_nested_payloads():
    item = {
        "videoMeta": {"coverUrl": "https://cdn/cover.jpg"},
        "images": ["https://cdn/1.png", "not-a-url", "https://cdn/2.webp"],
        "product": {"displayImage": "https://cdn/hero.jpeg"},
    }
    out: list[str] = []
    apify._harvest_images(item, out)
    assert "https://cdn/cover.jpg" in out
    assert "https://cdn/1.png" in out
    assert "https://cdn/2.webp" in out
    assert "https://cdn/hero.jpeg" in out
    assert "not-a-url" not in out


def test_looks_like_image():
    assert apify._looks_like_image("https://cdn.example/a/b/photo.jpg")
    assert apify._looks_like_image("https://cdn.example/dynamic-cover/x")
    assert not apify._looks_like_image("https://cdn.example/page.html")
    assert not apify._looks_like_image("just text")
