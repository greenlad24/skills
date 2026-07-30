"""End-to-end pipeline smoke test in DRY_RUN ($0, no network, no real providers).

Drives a job through the real stage tasks in order — research -> generation ->
editing -> [approval] -> posting — via the Celery task registry (``.apply()`` runs
each task eagerly in-process). This is the living check that the modules integrate:
the state machine advances, artifacts are produced, and the compliance-gated
approval->post path works, all against the deterministic fake providers.

Requires DRY_RUN (the default). If a stage's optional heavy ML deps are missing in
the environment, that stage is expected to still run via its DRY_RUN/stub path.
"""

from __future__ import annotations

import pytest

from app.core.config import settings

pytestmark = pytest.mark.skipif(
    not settings.DRY_RUN, reason="integration test runs only in DRY_RUN ($0, no network)"
)


@pytest.fixture(scope="module")
def app_ready():
    """Import the app, register module tasks, point Celery at an in-memory broker
    (so ``send_task`` in the API endpoints returns instantly instead of hanging on
    Redis), and ensure all tables exist."""
    import importlib

    from app.main import app  # noqa: F401  (triggers module loader)
    from app.core.db import Base, engine
    from app.core.queue import celery_app

    # In-memory broker/backend: send_task() calls inside the endpoints publish to a
    # queue no worker consumes (no cascade) and return immediately (no Redis hang).
    celery_app.conf.broker_url = "memory://"
    celery_app.conf.result_backend = "cache+memory://"
    celery_app.conf.broker_connection_retry_on_startup = False
    celery_app.conf.broker_transport_options = {"max_retries": 0}

    # Import each module's tasks so @celery_app.task registers them by name, and
    # each module's models so their tables register on the shared Base.
    for m in ("research", "generation", "editing", "posting", "compliance"):
        for sub in ("models", "tasks"):
            try:
                importlib.import_module(f"app.modules.{m}.{sub}")
            except Exception:
                pass
    importlib.import_module("app.core.models")

    Base.metadata.create_all(bind=engine)
    return app


def _run_stage(task_name: str, job_id: str):
    """Run one pipeline stage synchronously in-process (direct call, no broker)."""
    from app.core.queue import celery_app

    task = celery_app.tasks[task_name]  # KeyError if the module's tasks weren't imported
    return task(job_id=job_id)  # calling a task object runs it locally, raising on error


def _create_job(product_url: str, *, budget_usd: float = 50.0) -> str:
    """Insert a Product + QUEUED VideoJob directly, with a budget generous enough
    that the DRY_RUN fake per-clip costs (~$2.28 each) don't trip the generation
    budget guard — that guard has its own unit test in the generation module."""
    from app.core.db import SessionLocal
    from app.core.models import Product, VideoJob
    from app.core.state_machine import JobState

    db = SessionLocal()
    try:
        product = Product(source_url=product_url)
        db.add(product)
        db.flush()
        job = VideoJob(product_id=product.id, state=JobState.QUEUED, cost_budget_usd=budget_usd)
        db.add(job)
        db.commit()
        return str(job.id)
    finally:
        db.close()


def _setup_persona():
    from app.core.db import SessionLocal
    from app.modules.generation import setup_service

    db = SessionLocal()
    try:
        setup_service.setup_persona(
            db,
            operator_label="nimpara",
            consenter_name="Nimpara (operator)",
            source_clip_key="dryrun/source_clip.mp4",
            sample_audio_key="dryrun/voice_sample.mp3",
        )
        db.commit()
    finally:
        db.close()


def _drive_to_gate(app) -> str:
    """Setup persona, create a job, and run the automated stages up to the gate.
    Returns the job id, now in AWAITING_APPROVAL."""
    _setup_persona()
    job_id = _create_job("https://shop.example.com/p/silicone-ice-tray")
    _run_stage("research.run", job_id)
    _run_stage("generation.run", job_id)
    _run_stage("editing.run", job_id)
    return job_id


def test_url_to_awaiting_approval(app_ready):
    """The fully-automated portion: URL in -> post-ready captioned video at the gate."""
    from fastapi.testclient import TestClient
    from app.core.db import SessionLocal
    from app.core.models import MediaAsset

    client = TestClient(app_ready)

    # API smoke: the public create endpoint accepts a product URL.
    resp = client.post("/api/jobs", json={"product_url": "https://shop.example.com/p/silicone-ice-tray"})
    assert resp.status_code == 201, resp.text

    # Drive the pipeline to the gate on a realistic-budget job.
    job_id = _drive_to_gate(app_ready)

    # The job should now be paused at the single human gate, with artifacts.
    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["state"] == "AWAITING_APPROVAL", status
    assert status.get("script"), "expected a generated Thai script on the job"

    db = SessionLocal()
    try:
        assets = db.query(MediaAsset).filter(MediaAsset.video_job_id == job_id).all()
        assert assets, "expected at least one rendered MediaAsset (final video)"
    finally:
        db.close()


def test_approve_and_post(app_ready):
    """The approval -> compliance gate -> posting leg produces a Post (or a clean,
    non-crashing compliance block)."""
    from fastapi.testclient import TestClient
    from app.core.db import SessionLocal
    from app.core.models import VideoJob, Post

    client = TestClient(app_ready)

    # Reuse the pipeline to reach the gate.
    job_id = _drive_to_gate(app_ready)

    # Approve via the core gate endpoint -> moves to POSTING.
    resp = client.post(f"/api/jobs/{job_id}/approve")
    assert resp.status_code in (200, 409), resp.text

    if resp.status_code == 200:
        _run_stage("posting.run", job_id)

    db = SessionLocal()
    try:
        job = db.get(VideoJob, job_id)
        state = job.state.value if hasattr(job.state, "value") else job.state
        # Either it posted, or the compliance gate cleanly halted it — never a crash.
        assert state in {"POSTED", "POSTING", "FAILED"}, state
        if state == "POSTED":
            post = db.query(Post).filter(Post.video_job_id == job_id).first()
            assert post is not None, "POSTED job should have a Post record"
    finally:
        db.close()
