"""One-time avatar/voice persona setup (§3C).

A wizard run ONCE per operator/brand persona (not per video). It stores a
``ConsentRecord`` (required before any avatar is created), creates the operator's
HeyGen digital twin (``avatar_id``) and a Thai voice clone (``voice_id``), and
persists them on ``Avatar`` / ``VoiceProfile``. Every subsequent video reuses the
same IDs — a major cost + consistency lever.

Idempotency: calling setup again for the same operator label returns the existing
persona instead of re-creating it (setup once, reuse forever).

Provider note: the core ``AvatarProvider`` / ``TTSProvider`` Protocols expose the
*per-video* methods (``submit_talking_head`` / ``synthesize``), not persona
*creation* (``create_avatar`` / ``create_voice``). Where a real provider adds
those creation methods we call them by duck-typing; otherwise we fall back to the
configured ``HEYGEN_AVATAR_ID`` / ``ELEVENLABS_VOICE_ID`` or a deterministic
dry-run id. Consent is ALWAYS required first — no avatar without a ConsentRecord.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.adapters import registry
from app.core.config import settings
from app.core.models import Avatar, ConsentRecord, VoiceProfile
from app.modules.generation.constants import (
    CONSENT_AVATAR_LIKENESS,
    CONSENT_VOICE_CLONE,
)


class ConsentRequiredError(Exception):
    """Raised when persona setup is attempted without operator consent."""


@dataclass
class PersonaSetupResult:
    avatar: Avatar
    voice_profile: VoiceProfile
    consent_record: ConsentRecord
    created: bool  # False when an existing persona was reused (idempotent hit)


def _deterministic_id(prefix: str, *parts: str) -> str:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{h}"


def _provision_avatar_id(source_clip_key: str, consent_ref: str) -> str:
    """Create (or resolve) a reusable provider ``avatar_id`` (§3C.3)."""
    provider = registry.get_avatar_provider()
    creator = getattr(provider, "create_avatar", None)
    if callable(creator):
        try:
            result = creator(source_video=source_clip_key, consent_ref=consent_ref)
            avatar_id = getattr(result, "data", {}).get("avatar_id") or getattr(
                result, "provider_job_id", None
            )
            if avatar_id:
                return str(avatar_id)
        except Exception:  # noqa: BLE001 - fall back below
            pass
    if settings.HEYGEN_AVATAR_ID:
        return settings.HEYGEN_AVATAR_ID
    return _deterministic_id("heygen-avatar", source_clip_key, consent_ref)


def _provision_voice_id(sample_audio_key: str) -> str:
    """Create (or resolve) a reusable Thai voice-clone ``voice_id`` (§3C.3)."""
    provider = registry.get_tts_provider()
    creator = getattr(provider, "create_voice", None)
    if callable(creator):
        try:
            result = creator(sample_audio=sample_audio_key, language="th")
            voice_id = getattr(result, "data", {}).get("voice_id")
            if voice_id:
                return str(voice_id)
        except Exception:  # noqa: BLE001
            pass
    if settings.ELEVENLABS_VOICE_ID:
        return settings.ELEVENLABS_VOICE_ID
    return _deterministic_id("eleven-voice", sample_audio_key)


def find_active_persona(db: Session, *, label: str) -> Avatar | None:
    """Return an existing active Avatar for ``label`` (idempotency key)."""
    stmt = (
        select(Avatar)
        .where(Avatar.label == label)
        .where(Avatar.status == "active")
        .order_by(Avatar.created_at.desc())
    )
    return db.execute(stmt).scalars().first()


def setup_persona(
    db: Session,
    *,
    operator_label: str,
    consenter_name: str,
    source_clip_key: str,
    sample_audio_key: str,
    consent_scope: dict[str, Any] | None = None,
    source_clip_sha256: str | None = None,
    voice_provider: str | None = None,
    avatar_provider: str = "heygen",
    subject_is_operator: bool = True,
) -> PersonaSetupResult:
    """Create (or reuse) the operator persona — idempotent per ``operator_label``.

    Order (§3C.1): store ConsentRecord → create avatar → create voice → upsert
    Avatar/VoiceProfile linked to the ConsentRecord.
    """
    existing = find_active_persona(db, label=operator_label)
    if existing is not None:
        voice = db.execute(
            select(VoiceProfile)
            .where(VoiceProfile.label == operator_label)
            .order_by(VoiceProfile.created_at.desc())
        ).scalars().first()
        consent = db.execute(
            select(ConsentRecord)
            .where(ConsentRecord.avatar_id == existing.id)
            .order_by(ConsentRecord.created_at.desc())
        ).scalars().first()
        if voice is not None and consent is not None:
            return PersonaSetupResult(existing, voice, consent, created=False)

    if not consenter_name or not source_clip_key:
        raise ConsentRequiredError(
            "consenter_name and a source clip are required before creating an avatar"
        )

    now = datetime.now(timezone.utc)
    clip_hash = source_clip_sha256 or hashlib.sha256(source_clip_key.encode()).hexdigest()

    # 1) Avatar row (created first so ConsentRecord.avatar_id FK is satisfiable),
    #    then the provider avatar_id is provisioned and stored on it.
    avatar = Avatar(
        label=operator_label,
        provider=avatar_provider,
        status="active",
    )
    db.add(avatar)
    db.flush()  # assign avatar.id for the consent FK

    # 2) ConsentRecord — REQUIRED before the avatar is usable (§3C.2).
    consent = ConsentRecord(
        avatar_id=avatar.id,
        consenter_name=consenter_name,
        consent_type=CONSENT_AVATAR_LIKENESS,
        consented_at=now,
        subject_is_operator=subject_is_operator,
        biometric_explicit_consent=True,
        voice_licensed=True,
        scope=consent_scope or {"use": "AI likeness for AutoUGC-TH marketing"},
        revocable=True,
        revoked=False,
        source_clip_sha256=clip_hash,
    )
    db.add(consent)
    db.flush()

    # 3) Provision reusable IDs (consent now exists → allowed).
    avatar.provider_avatar_id = _provision_avatar_id(source_clip_key, str(consent.id))
    voice_id = _provision_voice_id(sample_audio_key)

    voice = VoiceProfile(
        label=operator_label,
        provider=voice_provider or "elevenlabs",
        provider_voice_id=voice_id,
        language="th",
        model="eleven_multilingual_v2",
    )
    db.add(voice)
    db.flush()

    # A second consent line for the voice clone (audit completeness).
    voice_consent = ConsentRecord(
        avatar_id=avatar.id,
        consenter_name=consenter_name,
        consent_type=CONSENT_VOICE_CLONE,
        consented_at=now,
        subject_is_operator=subject_is_operator,
        voice_licensed=True,
        scope=consent_scope or {"use": "AI voice clone for AutoUGC-TH marketing"},
        revocable=True,
        revoked=False,
        source_clip_sha256=hashlib.sha256(sample_audio_key.encode()).hexdigest(),
    )
    db.add(voice_consent)

    return PersonaSetupResult(avatar, voice, consent, created=True)


def revoke_consent(db: Session, *, avatar: Avatar) -> None:
    """Revoke consent → disable the avatar so future jobs referencing it are blocked."""
    now = datetime.now(timezone.utc)
    avatar.status = "retired"
    consents = db.execute(
        select(ConsentRecord).where(ConsentRecord.avatar_id == avatar.id)
    ).scalars().all()
    for c in consents:
        c.revoked = True
        c.revoked_at = now


def consent_active(db: Session, *, avatar: Avatar) -> bool:
    """True iff the avatar is active and has at least one non-revoked consent."""
    if avatar.status != "active":
        return False
    consents = db.execute(
        select(ConsentRecord).where(ConsentRecord.avatar_id == avatar.id)
    ).scalars().all()
    likeness = [c for c in consents if c.consent_type == CONSENT_AVATAR_LIKENESS]
    return any(not c.revoked for c in likeness) if likeness else False
