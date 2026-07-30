"""Typed application settings loaded from the environment / `.env`.

Single source of truth for configuration and secrets (§1.7). Adapters and stages
read keys ONLY from this `settings` object — never from `os.environ` directly and
never hard-coded. `DRY_RUN` and the per-video cost budget are first-class here.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core infra ---
    POSTGRES_DB: str = "autougc"
    POSTGRES_USER: str = "autougc"
    POSTGRES_PASSWORD: str = "change-me"
    # Empty => SQLite fallback (see db.py resolved_database_url). Postgres is the prod default.
    DATABASE_URL: str = ""

    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"

    # --- Media storage ---
    MEDIA_ROOT: str = "/data/media"
    MEDIA_BUCKET: str = "autougc-media"
    MINIO_ENDPOINT: str = "http://minio:9000"
    MINIO_ROOT_USER: str = "minio"
    MINIO_ROOT_PASSWORD: str = "change-me"

    # --- Provider selection (registry keys) ---
    LLM_PROVIDER: str = "anthropic"
    SCRAPER_PROVIDER: str = "apify"
    AVATAR_PROVIDER: str = "heygen"
    TTS_PROVIDER: str = "elevenlabs"
    VIDEOGEN_PROVIDER: str = "fal"
    POSTING_PROVIDER: str = "postpeer"

    # --- External API keys (secrets) ---
    ANTHROPIC_API_KEY: str = ""
    HEYGEN_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""
    FAL_API_KEY: str = ""
    APIFY_API_KEY: str = ""
    FIRECRAWL_API_KEY: str = ""
    RAINFOREST_API_KEY: str = ""
    POSTPEER_API_KEY: str = ""

    # --- Reused-forever identities ---
    HEYGEN_AVATAR_ID: str = ""
    ELEVENLABS_VOICE_ID: str = ""

    # --- Guards & run mode ---
    DRY_RUN: bool = True
    PER_VIDEO_COST_BUDGET_USD: float = 5.00

    # --- Auth ---
    APP_PASSWORD: str = ""

    @property
    def resolved_database_url(self) -> str:
        """The DB URL to actually connect with.

        Uses DATABASE_URL when set (Postgres in Docker); otherwise falls back to a
        local SQLite file so tests and no-Docker dev work with zero infra.
        """
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return "sqlite:///./autougc_local.sqlite3"

    @property
    def is_sqlite(self) -> bool:
        return self.resolved_database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    """Cached singleton accessor (import this, not the class)."""
    return Settings()


# Convenience module-level singleton.
settings = get_settings()
