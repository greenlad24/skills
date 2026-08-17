"""Onboarding endpoints (/api/setup/*) — the first-run setup wizard backend.

Mounted automatically by app.main.load_modules(). Drives the frontend SetupWizard:
report status → save keys → live-test each provider → mark complete.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.modules.onboarding import service

router = APIRouter(prefix="/api/setup", tags=["setup"])


class SaveBody(BaseModel):
    values: dict[str, str]


@router.get("/status")
def status() -> dict:
    """{complete, steps:{keys,video,tiktok}, dry_run} — powers the wizard gate."""
    return service.compute_status()


@router.post("/save")
def save(body: SaveBody) -> dict:
    """Persist whitelisted keys to .env and the running process."""
    return service.save(body.values)


@router.post("/test/{provider}")
def test(provider: str) -> dict:
    """Live-test one provider (llm | tts | video | tiktok) with saved credentials."""
    return service.test_provider(provider)


@router.post("/complete")
def complete() -> dict:
    """Mark first-run setup finished (persists ONBOARDED=true)."""
    return service.mark_complete()
