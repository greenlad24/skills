from __future__ import annotations

from app.modules.research.product.domain_router import is_shopify, route


def test_routes_each_platform():
    assert route("https://www.tiktok.com/@x/video/1").platform == "tiktok_shop"
    assert route("https://vt.tiktok.com/ZS123/").platform == "tiktok_shop"
    assert route("https://www.amazon.co.th/dp/B0ABC").platform == "amazon"
    assert route("https://th.aliexpress.com/item/1005.html").platform == "aliexpress"
    assert route("https://random-store.example/p/thing").platform == "firecrawl"


def test_shopify_detected_on_myshopify_host():
    assert route("https://cool.myshopify.com/products/serum").platform == "shopify"


def test_shopify_probe_skipped_in_dry_run():
    # custom domain, no myshopify host → probe would be needed, but DRY_RUN skips network
    assert is_shopify("https://customdomain.example/products/x") is False
