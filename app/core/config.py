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

    # --- Free/self-hosted video (Wan via ComfyUI) ---
    # Set VIDEOGEN_PROVIDER=wan_comfyui and point this at a ComfyUI server:
    # a free Kaggle/Colab GPU (see notebooks/wan_comfyui_kaggle.ipynb) or a rented GPU.
    COMFYUI_URL: str = ""
    # ComfyUI "API-format" workflow JSON with placeholder tokens (see the sample).
    # Empty => the bundled sample template is used.
    COMFYUI_WORKFLOW_PATH: str = ""
    COMFYUI_FPS: int = 16
    COMFYUI_POLL_SECONDS: int = 5
    COMFYUI_TIMEOUT_SECONDS: int = 900

    # --- Serverless video (LTX-2.5 on Modal) — the cheap "no GPU to babysit" path ---
    # Set VIDEOGEN_PROVIDER=ltx_modal and point this at your deployed Modal web app
    # (see deploy/modal_ltx.py + `modal deploy`). Generation then scales to zero
    # between renders; ~$0/mo inside Modal's free credit, ~$6/mo beyond it.
    MODAL_LTX_URL: str = ""
    # Optional shared secret; must match the AUTOUGC_LTX_TOKEN in the Modal secret.
    MODAL_LTX_TOKEN: str = ""
    LTX_FPS: int = 24
    # $/GPU-second used to estimate real cost from Modal's returned compute time,
    # so the cost ledger is honest. Default ~A10G list rate. Set 0 to report free.
    MODAL_GPU_USD_PER_SEC: float = 0.000306
    # How long the adapter waits for a submit/poll HTTP call before erroring.
    MODAL_LTX_TIMEOUT_SECONDS: int = 300

    # --- Near-free Thai TTS (Google Cloud Text-to-Speech) ---
    # Set TTS_PROVIDER=google_tts. Free tier (1M chars Neural2 / 4M Standard) covers
    # ~90 videos/mo, so Thai narration is effectively $0.
    GOOGLE_TTS_API_KEY: str = ""
    GOOGLE_TTS_VOICE: str = "th-TH-Neural2-C"     # natural Thai; th-TH-Standard-A is cheaper
    GOOGLE_TTS_LANGUAGE: str = "th-TH"
    # $/million chars used only for ledger honesty; 0 = report free (inside free tier).
    GOOGLE_TTS_USD_PER_MILLION: float = 0.0
    # Fallback duration estimate (sec/char) when ffprobe isn't available.
    GOOGLE_TTS_SEC_PER_CHAR: float = 0.08

    # --- Free TikTok posting (official Content Posting API) ---
    # Set POSTING_PROVIDER=tiktok. No per-post fee; needs an OAuth user token.
    TIKTOK_ACCESS_TOKEN: str = ""
    TIKTOK_API_BASE: str = "https://open.tiktokapis.com"
    # "direct" = publish to profile (audited app, video.publish scope);
    # "inbox"  = upload to drafts, creator posts from the app (unaudited, video.upload).
    TIKTOK_POSTING_MODE: str = "direct"
    # Empty => auto-pick an allowed level from creator_info (direct mode).
    TIKTOK_PRIVACY_LEVEL: str = ""

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
