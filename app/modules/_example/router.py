"""Example module router — mounted automatically by app.main.load_modules().

The foundation looks for a module-level `router: APIRouter`. Give it a unique prefix.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.adapters import registry
from app.core.config import settings

router = APIRouter(prefix="/api/_example", tags=["_example"])


@router.get("/ping")
def ping() -> dict:
    """Trivial endpoint proving the module mounted."""
    return {"module": "_example", "ok": True, "dry_run": settings.DRY_RUN}


@router.get("/demo-scrape")
def demo_scrape(url: str = "https://shop.example/demo") -> dict:
    """Shows the correct pattern: reach external services via the adapter registry only.

    With DRY_RUN=true this returns deterministic fake data and spends $0.
    """
    scraper = registry.get_scraper_provider()
    result = scraper.scrape_product(url=url, idempotency_key=f"_example:{url}")
    return {"ok": result.ok, "cost_usd": result.cost_usd, "data": result.data}
