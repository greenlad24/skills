"""Canonical SQLAlchemy models — the single source of truth for entity/field names (§1.5).

Reconciliation of the README "cross-section integration notes" is applied here and
recorded in docs/CONTRACTS.md. Where §1's ER model and a later section disagreed on a
name, §1 is canonical and the later section's extra fields are ADDED (not renamed):

  * CostLedgerEntry  — §1 table `COST_LEDGER`; canonical Python class name is
    `CostLedgerEntry` (per README §6). Merges §3's per-call fields (scene_id, model,
    kind, attempt, is_reroll).
  * ConsentRecord    — §1 base fields kept (consenter_name, consent_type, document_key,
    consented_at); §3/§6 compliance fields added. §3's `subject_name` == canonical
    `consenter_name`.
  * Post             — §1 names canonical (posting_provider, external_post_id,
    ai_disclosure_set, product_tag_attached, posted_at); §5's posting/analytics fields
    added (provider_post_id, tiktok_*, visibility, disclose_*, shop_tag_status, ...).
  * PerformanceRecord— §1 names canonical (captured_at, views..shares, ctr, conversion,
    is_winner); §5's analytics fields added (source, favorites, watch metrics, orders...).
  * SwipeSource / SwipeVideo — new entities from §2, ratified here.
  * GenAttempt       — new entity from §3 (one row per generation call; UNIQUE
    idempotency_key + UNIQUE request_id back the no-double-charge rule).

Types are portable: a GUID type maps to native Postgres UUID and to CHAR(36) on SQLite;
generic JSON maps to JSONB-compatible JSON. This keeps the models importable and testable
on SQLite while remaining the Postgres schema of record.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CHAR,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.state_machine import JobState


# --------------------------------------------------------------------------- #
# Portable column types
# --------------------------------------------------------------------------- #
class GUID(TypeDecorator):
    """Platform-independent UUID: native UUID on Postgres, CHAR(36) elsewhere."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(GUID(), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """created_at / updated_at on every table (§1.5)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


# --------------------------------------------------------------------------- #
# Core pipeline entities
# --------------------------------------------------------------------------- #
class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = _pk()
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(Text)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(8))
    attributes: Mapped[dict | None] = mapped_column(JSON)   # specs, features, images[]
    raw_scrape: Mapped[dict | None] = mapped_column(JSON)   # provider payload
    scraper_provider: Mapped[str | None] = mapped_column(String(64))
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    jobs: Mapped[list["VideoJob"]] = relationship(back_populates="product")


class VideoJob(TimestampMixin, Base):
    __tablename__ = "video_jobs"

    id: Mapped[uuid.UUID] = _pk()
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id"))
    avatar_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("avatars.id"))
    voice_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("voice_profiles.id")
    )
    formula_template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("formula_templates.id")
    )
    hook_template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hook_templates.id")
    )
    pacing_template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pacing_templates.id")
    )

    state: Mapped[JobState] = mapped_column(
        SAEnum(JobState, name="job_state"), default=JobState.QUEUED, nullable=False
    )
    last_completed_stage: Mapped[str | None] = mapped_column(String(64))
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    cost_budget_usd: Mapped[float] = mapped_column(
        Numeric(10, 2), default=5.00, nullable=False
    )
    cost_accrued_usd: Mapped[float] = mapped_column(
        Numeric(10, 2), default=0.00, nullable=False
    )

    draft_asset_key: Mapped[str | None] = mapped_column(Text)   # MinIO key
    decision: Mapped[dict | None] = mapped_column(JSON)         # approve/reject + notes
    failure_reason: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    product: Mapped["Product"] = relationship(back_populates="jobs")
    avatar: Mapped["Avatar"] = relationship()
    voice_profile: Mapped["VoiceProfile"] = relationship()
    script: Mapped["Script"] = relationship(back_populates="video_job", uselist=False)
    media_assets: Mapped[list["MediaAsset"]] = relationship(back_populates="video_job")
    gen_attempts: Mapped[list["GenAttempt"]] = relationship(back_populates="video_job")
    post: Mapped["Post"] = relationship(back_populates="video_job", uselist=False)
    compliance_records: Mapped[list["ComplianceRecord"]] = relationship(
        back_populates="video_job"
    )
    cost_ledger_entries: Mapped[list["CostLedgerEntry"]] = relationship(
        back_populates="video_job"
    )


class Script(TimestampMixin, Base):
    __tablename__ = "scripts"

    id: Mapped[uuid.UUID] = _pk()
    video_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_jobs.id"), nullable=False
    )
    language: Mapped[str] = mapped_column(String(8), default="th")
    full_text: Mapped[str | None] = mapped_column(Text)
    hook: Mapped[dict | None] = mapped_column(JSON)   # opening line + type
    claim_safety_passed: Mapped[bool | None] = mapped_column(Boolean)
    claim_safety_report: Mapped[dict | None] = mapped_column(JSON)  # flagged phrases
    llm_provider: Mapped[str | None] = mapped_column(String(64))
    llm_model: Mapped[str | None] = mapped_column(String(128))

    video_job: Mapped["VideoJob"] = relationship(back_populates="script")
    scenes: Mapped[list["Scene"]] = relationship(back_populates="script")


class Scene(TimestampMixin, Base):
    __tablename__ = "scenes"

    id: Mapped[uuid.UUID] = _pk()
    script_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scripts.id"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_type: Mapped[str] = mapped_column(String(16))   # avatar | broll
    spoken_text_th: Mapped[str | None] = mapped_column(Text)
    visual_direction: Mapped[str | None] = mapped_column(Text)
    duration_sec: Mapped[float | None] = mapped_column(Numeric(8, 2))
    media_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id")
    )

    script: Mapped["Script"] = relationship(back_populates="scenes")


class MediaAsset(TimestampMixin, Base):
    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = _pk()
    video_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_jobs.id"), nullable=False
    )
    # hero_image | broll | avatar_clip | tts_audio | draft | final
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(Text)   # MinIO object key
    mime_type: Mapped[str | None] = mapped_column(String(128))
    provider: Mapped[str | None] = mapped_column(String(64))
    provider_job_id: Mapped[str | None] = mapped_column(String(255))  # for re-attach
    idempotency_key: Mapped[str | None] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|processing|ready|failed
    duration_sec: Mapped[float | None] = mapped_column(Numeric(8, 2))
    meta: Mapped[dict | None] = mapped_column(JSON)   # resolution, seed, prompt
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 4))

    video_job: Mapped["VideoJob"] = relationship(back_populates="media_assets")


# --------------------------------------------------------------------------- #
# Reused-forever identities + templates
# --------------------------------------------------------------------------- #
class Avatar(TimestampMixin, Base):
    __tablename__ = "avatars"

    id: Mapped[uuid.UUID] = _pk()
    label: Mapped[str | None] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(64), default="heygen")
    provider_avatar_id: Mapped[str | None] = mapped_column(String(255))  # reused forever
    status: Mapped[str] = mapped_column(String(16), default="active")    # active|retired

    consent_records: Mapped[list["ConsentRecord"]] = relationship(
        back_populates="avatar"
    )


class VoiceProfile(TimestampMixin, Base):
    __tablename__ = "voice_profiles"

    id: Mapped[uuid.UUID] = _pk()
    label: Mapped[str | None] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(64), default="elevenlabs")  # elevenlabs|botnoi
    provider_voice_id: Mapped[str | None] = mapped_column(String(255))       # reused forever
    language: Mapped[str] = mapped_column(String(8), default="th")
    model: Mapped[str | None] = mapped_column(String(128), default="multilingual_v2")


class FormulaTemplate(TimestampMixin, Base):
    __tablename__ = "formula_templates"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(255))
    structure: Mapped[dict | None] = mapped_column(JSON)   # beat-by-beat formula
    source: Mapped[str | None] = mapped_column(Text)       # mined tiktok id/url
    win_score: Mapped[float | None] = mapped_column(Numeric(8, 4))  # from feedback loop
    # §2 honesty contract: proxy vs. operator-real signal, always labelled.
    proxy_score: Mapped[float | None] = mapped_column(Float)
    operator_win_score: Mapped[float | None] = mapped_column(Float)
    signal_type: Mapped[str] = mapped_column(String(32), default="engagement_proxy")


class HookTemplate(TimestampMixin, Base):
    __tablename__ = "hook_templates"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(255))
    pattern_th: Mapped[str | None] = mapped_column(Text)
    hook_type: Mapped[str | None] = mapped_column(String(64))
    win_score: Mapped[float | None] = mapped_column(Numeric(8, 4))
    proxy_score: Mapped[float | None] = mapped_column(Float)
    operator_win_score: Mapped[float | None] = mapped_column(Float)
    signal_type: Mapped[str] = mapped_column(String(32), default="engagement_proxy")


class PacingTemplate(TimestampMixin, Base):
    __tablename__ = "pacing_templates"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(255))
    cut_profile: Mapped[dict | None] = mapped_column(JSON)   # cuts/sec, scene lengths
    avg_scene_sec: Mapped[float | None] = mapped_column(Numeric(8, 2))
    win_score: Mapped[float | None] = mapped_column(Numeric(8, 4))
    proxy_score: Mapped[float | None] = mapped_column(Float)
    operator_win_score: Mapped[float | None] = mapped_column(Float)
    signal_type: Mapped[str] = mapped_column(String(32), default="engagement_proxy")


# --------------------------------------------------------------------------- #
# Posting + performance
# --------------------------------------------------------------------------- #
class Post(TimestampMixin, Base):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = _pk()
    video_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_jobs.id"), nullable=False
    )
    # --- §1 canonical fields ---
    platform: Mapped[str] = mapped_column(String(32), default="tiktok")
    posting_provider: Mapped[str | None] = mapped_column(String(64))  # postpeer|ayrshare|blotato
    external_post_id: Mapped[str | None] = mapped_column(String(255))
    post_url: Mapped[str | None] = mapped_column(Text)
    ai_disclosure_set: Mapped[bool] = mapped_column(Boolean, default=False)
    product_tag_attached: Mapped[bool] = mapped_column(Boolean, default=False)  # manual step
    status: Mapped[str] = mapped_column(String(32), default="pending")  # published|failed|...
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- §5 extension fields (posting/analytics), aligned to §1 ---
    variant_group_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    account_ref: Mapped[str | None] = mapped_column(String(255))
    provider_post_id: Mapped[str | None] = mapped_column(String(255))
    tiktok_publish_id: Mapped[str | None] = mapped_column(String(255))
    tiktok_video_id: Mapped[str | None] = mapped_column(String(255))
    visibility: Mapped[str | None] = mapped_column(String(32))
    fail_reason: Mapped[str | None] = mapped_column(Text)
    disclose_commercial: Mapped[bool | None] = mapped_column(Boolean)
    disclose_your_brand: Mapped[bool | None] = mapped_column(Boolean)
    disclose_branded_content: Mapped[bool | None] = mapped_column(Boolean)
    is_ai_generated: Mapped[bool | None] = mapped_column(Boolean)
    shop_tag_status: Mapped[str | None] = mapped_column(String(16))  # PENDING|TAGGED|NA
    shop_tagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deep_link: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_score: Mapped[float | None] = mapped_column(Float)
    latest_metrics_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    video_job: Mapped["VideoJob"] = relationship(back_populates="post")
    performance_records: Mapped[list["PerformanceRecord"]] = relationship(
        back_populates="post"
    )


class PerformanceRecord(TimestampMixin, Base):
    __tablename__ = "performance_records"

    id: Mapped[uuid.UUID] = _pk()
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id"), nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # --- §1 canonical ---
    views: Mapped[int | None] = mapped_column(Integer)
    likes: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    shares: Mapped[int | None] = mapped_column(Integer)
    ctr: Mapped[float | None] = mapped_column(Numeric(8, 4))
    conversion: Mapped[float | None] = mapped_column(Numeric(8, 4))  # if available
    is_winner: Mapped[bool] = mapped_column(Boolean, default=False)  # feedback flag
    # --- §5 extension (analytics/commercial) ---
    source: Mapped[str | None] = mapped_column(String(64))  # tiktok_analytics|shop_csv|manual
    favorites: Mapped[int | None] = mapped_column(Integer)
    avg_watch_time_s: Mapped[float | None] = mapped_column(Float)
    full_video_watch_rate: Mapped[float | None] = mapped_column(Float)
    reach: Mapped[int | None] = mapped_column(Integer)
    profile_visits: Mapped[int | None] = mapped_column(Integer)
    product_clicks: Mapped[int | None] = mapped_column(Integer)
    orders: Mapped[int | None] = mapped_column(Integer)
    gmv: Mapped[float | None] = mapped_column(Numeric(14, 2))
    commission: Mapped[float | None] = mapped_column(Numeric(14, 2))
    score: Mapped[float | None] = mapped_column(Float)

    post: Mapped["Post"] = relationship(back_populates="performance_records")


# --------------------------------------------------------------------------- #
# Compliance + consent + cost
# --------------------------------------------------------------------------- #
class ComplianceRecord(TimestampMixin, Base):
    __tablename__ = "compliance_records"

    id: Mapped[uuid.UUID] = _pk()
    video_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_jobs.id"), nullable=False
    )
    check_type: Mapped[str] = mapped_column(String(32))  # ai_label|disclosure|claim_safety
    passed: Mapped[bool | None] = mapped_column(Boolean)
    detail: Mapped[dict | None] = mapped_column(JSON)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # §6 extension: append-only, hash-chained audit events.
    events: Mapped[dict | None] = mapped_column(JSON)
    prev_hash: Mapped[str | None] = mapped_column(String(128))
    ruleset_version: Mapped[str | None] = mapped_column(String(32))

    video_job: Mapped["VideoJob"] = relationship(back_populates="compliance_records")


class ConsentRecord(TimestampMixin, Base):
    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = _pk()
    avatar_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("avatars.id"), nullable=False
    )
    # --- §1 canonical (§3 `subject_name` == `consenter_name`) ---
    consenter_name: Mapped[str | None] = mapped_column(String(255))
    consent_type: Mapped[str | None] = mapped_column(String(64))  # avatar_likeness|voice_clone
    document_key: Mapped[str | None] = mapped_column(Text)        # signed doc in MinIO
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # --- §6 compliance-critical fields ---
    subject_is_operator: Mapped[bool | None] = mapped_column(Boolean)
    identity_verified: Mapped[bool | None] = mapped_column(Boolean)
    identity_verification_ref: Mapped[str | None] = mapped_column(String(255))
    biometric_explicit_consent: Mapped[bool | None] = mapped_column(Boolean)
    voice_licensed: Mapped[bool | None] = mapped_column(Boolean)
    scope: Mapped[dict | None] = mapped_column(JSON)
    term: Mapped[dict | None] = mapped_column(JSON)
    revocable: Mapped[bool] = mapped_column(Boolean, default=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    takedown_contact: Mapped[str | None] = mapped_column(String(255))
    source_clip_sha256: Mapped[str | None] = mapped_column(String(128))
    signature_ref: Mapped[str | None] = mapped_column(String(255))
    ruleset_version: Mapped[str | None] = mapped_column(String(32))

    avatar: Mapped["Avatar"] = relationship(back_populates="consent_records")


class CostLedgerEntry(TimestampMixin, Base):
    """§1 table `COST_LEDGER`; canonical class name `CostLedgerEntry` (append-only)."""

    __tablename__ = "cost_ledger"

    id: Mapped[uuid.UUID] = _pk()
    video_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_jobs.id"), nullable=False
    )
    # --- §1 canonical ---
    stage: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(64))
    line_item: Mapped[str | None] = mapped_column(String(128))
    amount_usd: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    usage: Mapped[dict | None] = mapped_column(JSON)   # tokens, seconds, credits
    incurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # --- §3 extension (per generation call) ---
    scene_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenes.id"))
    model: Mapped[str | None] = mapped_column(String(128))
    kind: Mapped[str | None] = mapped_column(String(32))  # AVATAR|HERO_IMAGE|I2V|...
    attempt: Mapped[int | None] = mapped_column(Integer)
    is_reroll: Mapped[bool] = mapped_column(Boolean, default=False)

    video_job: Mapped["VideoJob"] = relationship(back_populates="cost_ledger_entries")


# --------------------------------------------------------------------------- #
# Generation attempts (§3) — one row per external generation call
# --------------------------------------------------------------------------- #
class GenAttempt(TimestampMixin, Base):
    __tablename__ = "gen_attempts"

    id: Mapped[uuid.UUID] = _pk()
    video_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_jobs.id"), nullable=False
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenes.id"))
    media_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id")
    )
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    kind: Mapped[str | None] = mapped_column(String(32))  # AVATAR|HERO_IMAGE|I2V
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    seed: Mapped[int | None] = mapped_column(Integer)
    # Provider request handles + local guards (UNIQUE => no double-charge on retry).
    request_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    status_url: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|processing|ready|failed
    is_reroll: Mapped[bool] = mapped_column(Boolean, default=False)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 4))
    error: Mapped[str | None] = mapped_column(Text)

    video_job: Mapped["VideoJob"] = relationship(back_populates="gen_attempts")


# --------------------------------------------------------------------------- #
# Swipe / market mining (§2)
# --------------------------------------------------------------------------- #
class SwipeSource(TimestampMixin, Base):
    __tablename__ = "swipe_sources"

    id: Mapped[uuid.UUID] = _pk()
    type: Mapped[str] = mapped_column(String(16))   # account | hashtag | keyword
    handle: Mapped[str | None] = mapped_column(String(255))
    niche: Mapped[str | None] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    added_by: Mapped[str] = mapped_column(String(32), default="seed")  # seed|operator|auto_discovered

    videos: Mapped[list["SwipeVideo"]] = relationship(back_populates="source")


class SwipeVideo(TimestampMixin, Base):
    __tablename__ = "swipe_videos"

    id: Mapped[uuid.UUID] = _pk()
    tiktok_id: Mapped[str] = mapped_column(String(64), unique=True)  # de-dupe key
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("swipe_sources.id")
    )
    niche: Mapped[str | None] = mapped_column(String(128))
    author_handle: Mapped[str | None] = mapped_column(String(255))
    author_gender: Mapped[str | None] = mapped_column(String(16))  # inferred
    url: Mapped[str | None] = mapped_column(Text)
    local_video_path: Mapped[str | None] = mapped_column(Text)  # yt-dlp output
    duration_s: Mapped[float | None] = mapped_column(Float)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    views: Mapped[int | None] = mapped_column(Integer)
    likes: Mapped[int | None] = mapped_column(Integer)
    shares: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    saves: Mapped[int | None] = mapped_column(Integer)
    proxy_score: Mapped[float | None] = mapped_column(Float)
    operator_win_score: Mapped[float | None] = mapped_column(Float)  # null until §5
    # transcript_id / scene_data_id reference §2 entities owned by the research module;
    # kept as opaque IDs here so core stays importable without those tables.
    transcript_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    scene_data_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    processed_stages: Mapped[dict | None] = mapped_column(JSON)  # idempotent-rerun bitmap
    signal_type: Mapped[str] = mapped_column(String(32), default="engagement_proxy")

    source: Mapped["SwipeSource"] = relationship(back_populates="videos")


# Convenience export: every model class (used by tests / tooling).
ALL_MODELS = [
    Product,
    VideoJob,
    Script,
    Scene,
    MediaAsset,
    Avatar,
    VoiceProfile,
    FormulaTemplate,
    HookTemplate,
    PacingTemplate,
    Post,
    PerformanceRecord,
    ComplianceRecord,
    ConsentRecord,
    CostLedgerEntry,
    GenAttempt,
    SwipeSource,
    SwipeVideo,
]
