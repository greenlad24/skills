"""§3C one-time avatar/voice setup tests — idempotency + consent."""

from __future__ import annotations

import pytest

from app.core.models import Avatar, ConsentRecord, VoiceProfile
from app.modules.generation import setup_service


def test_setup_creates_persona_with_consent(db):
    result = setup_service.setup_persona(
        db,
        operator_label="op",
        consenter_name="Jane",
        source_clip_key="minio://clip.mp4",
        sample_audio_key="minio://voice.wav",
    )
    assert result.created is True
    assert result.avatar.provider_avatar_id
    assert result.voice_profile.provider_voice_id
    assert result.consent_record.consent_type == "avatar_likeness"
    # No avatar without a stored ConsentRecord.
    assert db.query(ConsentRecord).count() >= 1


def test_setup_is_idempotent(db):
    a = setup_service.setup_persona(
        db, operator_label="op", consenter_name="Jane",
        source_clip_key="minio://clip.mp4", sample_audio_key="minio://voice.wav",
    )
    db.flush()
    b = setup_service.setup_persona(
        db, operator_label="op", consenter_name="Jane",
        source_clip_key="minio://clip.mp4", sample_audio_key="minio://voice.wav",
    )
    assert b.created is False
    assert b.avatar.id == a.avatar.id
    assert b.voice_profile.id == a.voice_profile.id
    # Exactly one persona created despite two setup calls.
    assert db.query(Avatar).count() == 1
    assert db.query(VoiceProfile).count() == 1


def test_consent_required(db):
    with pytest.raises(setup_service.ConsentRequiredError):
        setup_service.setup_persona(
            db, operator_label="op", consenter_name="",
            source_clip_key="", sample_audio_key="minio://voice.wav",
        )


def test_revoke_consent_blocks_avatar(db):
    result = setup_service.setup_persona(
        db, operator_label="op", consenter_name="Jane",
        source_clip_key="minio://clip.mp4", sample_audio_key="minio://voice.wav",
    )
    db.flush()
    assert setup_service.consent_active(db, avatar=result.avatar) is True
    setup_service.revoke_consent(db, avatar=result.avatar)
    db.flush()
    assert setup_service.consent_active(db, avatar=result.avatar) is False
