"""P0 smoke test: the foundation imports, the state machine guards illegal transitions,
and every Fake adapter instantiates and returns a deterministic $0 ProviderResult.

Runs entirely in DRY_RUN with SQLite — no Docker, no network, no spend.
"""

from __future__ import annotations

import os

# Force the $0 dry-run path + SQLite fallback before importing app config.
os.environ.setdefault("DRY_RUN", "true")
os.environ.setdefault("DATABASE_URL", "")

import pytest

from app.core.adapters.base import ProviderResult
from app.core.adapters.fakes import FAKE_PROVIDERS
from app.core.adapters import registry
from app.core.state_machine import (
    ALLOWED_TRANSITIONS,
    IllegalTransitionError,
    JobState,
    can_transition,
    transition,
)


class _JobStub:
    """Minimal stand-in with a mutable .state (the state machine only needs that)."""

    def __init__(self, state: JobState) -> None:
        self.state = state


def test_app_imports():
    """The FastAPI app and its routes import cleanly, and the example module mounts."""
    from app.main import app, LOADED_MODULES

    # Use the OpenAPI schema — the stable public view of mounted paths across
    # Starlette versions (some wrap included routers so app.routes has no .path).
    paths = set(app.openapi()["paths"].keys())
    assert "/health" in paths
    assert "/api/jobs" in paths
    assert "/api/jobs/{job_id}" in paths
    assert "/api/jobs/{job_id}/approve" in paths
    assert "/api/jobs/{job_id}/reroll" in paths
    # The dynamic loader mounted the example stub module's route.
    assert "/api/_example/ping" in paths
    # The dynamic loader mounted the example stub module.
    assert "_example" in LOADED_MODULES


def test_state_machine_rejects_illegal_transition():
    """QUEUED -> POSTED is not a legal edge and must raise."""
    job = _JobStub(JobState.QUEUED)
    assert not can_transition(JobState.QUEUED, JobState.POSTED)
    with pytest.raises(IllegalTransitionError):
        transition(job, JobState.POSTED)
    # Job state is unchanged after a rejected transition.
    assert job.state is JobState.QUEUED


def test_state_machine_allows_legal_transition():
    job = _JobStub(JobState.QUEUED)
    transition(job, JobState.RESEARCHING)
    assert job.state is JobState.RESEARCHING


def test_gate_requires_human():
    """Only a human decision may leave AWAITING_APPROVAL (durable-pause semantics)."""
    job = _JobStub(JobState.AWAITING_APPROVAL)
    # POSTING is a legal target, but not without by_human=True.
    with pytest.raises(IllegalTransitionError):
        transition(job, JobState.POSTING, by_human=False)
    transition(job, JobState.POSTING, by_human=True)
    assert job.state is JobState.POSTING


def test_all_states_present_in_transition_map():
    """Every JobState is a key in the transitions map (no dangling states)."""
    for state in JobState:
        assert state in ALLOWED_TRANSITIONS


def test_every_fake_adapter_instantiates_and_returns_result():
    """Instantiate every Fake and call one representative method; all $0, deterministic."""
    # LLM
    llm = FAKE_PROVIDERS["llm"]()
    r = llm.complete(prompt="hi", system=None, model="m", max_tokens=10, idempotency_key="k")
    assert isinstance(r, ProviderResult) and r.ok and r.cost_usd >= 0

    # Scraper
    scr = FAKE_PROVIDERS["scraper"]()
    assert scr.scrape_product(url="u", idempotency_key="k").ok
    assert scr.mine_top_videos(query="q", market="TH", limit=3, idempotency_key="k").ok

    # TTS
    tts = FAKE_PROVIDERS["tts"]()
    assert tts.synthesize(text="สวัสดี", voice_id="v", language="th", model="m", idempotency_key="k").ok

    # Avatar (submit + poll)
    av = FAKE_PROVIDERS["avatar"]()
    sub = av.submit_talking_head(avatar_id="a", audio_key="ak", script_text="s", aspect="9:16", idempotency_key="k")
    assert sub.ok and sub.provider_job_id
    assert av.poll(provider_job_id=sub.provider_job_id).ok

    # VideoGen (hero + i2v + poll)
    vg = FAKE_PROVIDERS["videogen"]()
    assert vg.generate_hero_image(prompt="p", refs=[], idempotency_key="k").ok
    i2v = vg.submit_image_to_video(image_key="i", prompt="p", model="kling", seconds=5, aspect="9:16", idempotency_key="k")
    assert i2v.ok and i2v.provider_job_id
    assert vg.poll(provider_job_id=i2v.provider_job_id).ok

    # Posting (publish + metrics)
    post = FAKE_PROVIDERS["posting"]()
    pub = post.publish(video_key="vk", caption="c", platform="tiktok", ai_disclosure=True, schedule_at=None, idempotency_key="k")
    assert pub.ok and pub.data["ai_disclosure_set"] is True
    assert post.fetch_metrics(external_post_id="pid").ok


def test_fakes_are_deterministic():
    """Same inputs -> identical fake output (idempotency requirement)."""
    a = FAKE_PROVIDERS["scraper"]().scrape_product(url="u", idempotency_key="same")
    b = FAKE_PROVIDERS["scraper"]().scrape_product(url="u", idempotency_key="same")
    assert a.data == b.data


def test_registry_returns_fakes_in_dry_run():
    """With DRY_RUN=true the registry hands back Fake instances for every capability."""
    assert registry.get_llm_provider().__class__.__name__.startswith("Fake")
    assert registry.get_scraper_provider().__class__.__name__.startswith("Fake")
    assert registry.get_tts_provider().__class__.__name__.startswith("Fake")
    assert registry.get_avatar_provider().__class__.__name__.startswith("Fake")
    assert registry.get_video_gen_provider().__class__.__name__.startswith("Fake")
    assert registry.get_posting_provider().__class__.__name__.startswith("Fake")


def test_models_and_db_create():
    """All canonical models register on the metadata and create on SQLite."""
    from app.core.db import Base, engine, init_db
    from app.core.models import ALL_MODELS

    init_db()
    table_names = set(Base.metadata.tables.keys())
    # 18 canonical entities.
    assert len(ALL_MODELS) == 18
    for expected in [
        "products", "video_jobs", "scripts", "scenes", "media_assets", "avatars",
        "voice_profiles", "formula_templates", "hook_templates", "pacing_templates",
        "posts", "performance_records", "compliance_records", "consent_records",
        "cost_ledger", "gen_attempts", "swipe_sources", "swipe_videos",
    ]:
        assert expected in table_names
