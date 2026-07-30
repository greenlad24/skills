"""Test fixtures — an isolated in-memory SQLite DB + job/product/persona factories.

Every provider is the deterministic Fake (DRY_RUN defaults true), so the whole
suite runs offline for $0. Service functions take an injected ``db`` so tests
never touch the app's file DB or the module loader.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.models import Avatar, Product, VideoJob, VoiceProfile
from app.core.state_machine import JobState


@pytest.fixture()
def db():
    """A fresh in-memory SQLite session with all tables created."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=True, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def product(db):
    p = Product(
        source_url="https://shop.example/lip-serum",
        title="ลิปเซรั่ม",
        brand="XYZ",
        price=259,
        currency="THB",
        attributes={
            "features": ["30ml", "matte finish", "vanilla scent"],
            "attributes": [
                {"key": "volume_ml", "value": "30"},
                {"key": "finish", "value": "matte"},
            ],
            "images": [{"asset_id": "a1", "url": "file:///media/p1.jpg", "is_primary": True}],
            "approved_claims": [],
            "category": "cosmetics/lip",
        },
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def persona(db):
    """A ready-to-use avatar + voice with active consent."""
    from app.modules.generation import setup_service

    result = setup_service.setup_persona(
        db,
        operator_label="operator-1",
        consenter_name="Jane Operator",
        source_clip_key="minio://consent/clip.mp4",
        sample_audio_key="minio://consent/voice.wav",
    )
    db.flush()
    return result


def make_job(db, product, *, state=JobState.SCRIPTING, budget=20.0,
             avatar=None, voice=None) -> VideoJob:
    job = VideoJob(
        id=uuid.uuid4(),
        product_id=product.id,
        state=state,
        cost_budget_usd=budget,
        cost_accrued_usd=0,
        avatar_id=avatar.id if avatar else None,
        voice_profile_id=voice.id if voice else None,
    )
    db.add(job)
    db.flush()
    return job
