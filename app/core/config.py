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
    # Folder for the Redis-free `filesystem://` broker (local no-Redis mode).
    CELERY_BROKER_DIR: str = ".broker"

    # --- Media storage ---
    MEDIA_ROOT: str = "/data/media"
    MEDIA_BUCKET: str = "autougc-media"
    MINIO_ENDPOINT: str = "http://minio:9000"
    MINIO_ROOT_USER: str = "minio"
    MINIO_ROOT_PASSWORD: str = "change-me"

    # --- Provider selection (the single approved stack) ---
    LLM_PROVIDER: str = "anthropic"
    SCRAPER_PROVIDER: str = "socialcrawl"
    TTS_PROVIDER: str = "google_tts"
    VIDEOGEN_PROVIDER: str = "ltx_modal"
    POSTING_PROVIDER: str = "tiktok"

    # --- External API keys (secrets) ---
    ANTHROPIC_API_KEY: str = ""
    APIFY_API_KEY: str = ""
    FIRECRAWL_API_KEY: str = ""

    # --- SocialCrawl (the approved product/image source) ---
    # Per-call HTTP API (not a residential-proxy actor), so it's fast + reliable for
    # Thai TikTok Shop. The by-URL endpoints are US-only, so we use keyword SEARCH in
    # the TH region and take the top match: it returns the product title, image URLs,
    # and THB price. 100 free credits, 1 credit/call.
    SOCIALCRAWL_API_KEY: str = ""
    SOCIALCRAWL_BASE: str = "https://www.socialcrawl.dev/v1"
    SOCIALCRAWL_REGION: str = "TH"  # ISO alpha-2, uppercase
    SOCIALCRAWL_EST_USD_PER_CALL: float = 0.008  # ledger estimate (~£15 / 2,500 calls)
    # TikTok/ByteImg CDN images embed a resize template (e.g. ...:400:400.webp).
    # We rewrite it to this size for a crisp hero reference; the original stays as a
    # fallback and the LTX hero step picks whichever actually fetches. 0 => no rewrite.
    SOCIALCRAWL_IMAGE_SIZE: int = 1080

    # --- Apify scraper (the approved product/image source) ---
    # TikTok Shop / short links can't be scraped by generic crawlers, so we run an
    # Apify actor that resolves the link and returns product text + image URLs.
    # Actors are addressed as "<username>~<actor-name>"; override if you fork one.
    #
    # Two TikTok modes, routed by URL:
    #   * Shop product/shop/category URL -> the TikTok SHOP actor (title, THB price,
    #     images, variants). webdatalabs is the reliable one and covers the TH market.
    #   * A plain video link (incl. vt.tiktok.com short links) -> the VIDEO actor,
    #     whose cover image is used as the product reference.
    APIFY_TIKTOK_SHOP_ACTOR: str = "webdatalabs~tiktok-shop-scraper"
    APIFY_TIKTOK_VIDEO_ACTOR: str = "clockworks~tiktok-scraper"
    APIFY_GENERIC_ACTOR: str = ""  # optional actor for non-TikTok URLs; blank => manual
    # Universal override: point the app at ANY Apify actor you tested manually,
    # without a code change. When APIFY_ACTOR is set it wins for every URL, and
    # APIFY_INPUT (a JSON template with {url} and {region}/{REGION} placeholders)
    # is sent as its input verbatim. Example:
    #   APIFY_ACTOR=some-user~their-tiktok-shop-scraper
    #   APIFY_INPUT={"productUrls":["{url}"],"proxyConfiguration":{"useApifyProxy":true,"apifyProxyCountry":"{REGION}"}}
    APIFY_ACTOR: str = ""
    APIFY_INPUT: str = ""
    APIFY_TIKTOK_REGION: str = "th"  # Thai storefront/proxy region (ISO alpha-2)
    # TikTok Shop via residential proxy is slow (1-4 min is normal); Apify's
    # run-sync endpoint allows up to 300s. Give it room before falling to manual.
    APIFY_SYNC_TIMEOUT_SECONDS: int = 270
    APIFY_EST_USD_PER_SCRAPE: float = 0.02  # ledger estimate; real spend = Apify credits

    # --- Legacy identities (dormant avatar lane; faceless jobs never use these) ---
    # Kept only so the avatar scene-lane code path stays importable. The approved
    # faceless workflow produces no ASSET_AVATAR scenes, so these stay empty.
    AVATAR_PROVIDER: str = "fake-avatar"
    HEYGEN_AVATAR_ID: str = ""
    ELEVENLABS_VOICE_ID: str = ""

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
    # Expected render seconds per clip, used to bill an estimate at SUBMIT time
    # (the pipeline records cost at submit; actual compute_seconds is returned at
    # poll for reconciliation). Measure once after deploy and tune. 0 => report free.
    MODAL_LTX_EST_SECONDS_PER_CLIP: float = 90.0
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
    # Set true by the in-app onboarding wizard when first-run setup is finished.
    ONBOARDED: bool = False

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


def reload_settings_from_dotenv() -> None:
    """Re-read the `.env` file into the live `settings` singleton, in place.

    Secrets entered in the web onboarding are written to `.env` and applied to the
    web process — but the Celery worker is a SEPARATE process that read its settings
    at startup and won't otherwise see keys added afterwards. Calling this before each
    task lets the worker pick up onboarding-saved keys with no restart. Only fields
    that exist on Settings are touched; unknown lines are ignored.
    """
    import os
    from pathlib import Path

    env_path = Path(os.environ.get("AUTOUGC_ENV_FILE", ".env"))
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        val = raw.strip().strip('"').strip("'")
        if not hasattr(settings, key):
            continue
        current = getattr(settings, key)
        try:
            if isinstance(current, bool):
                coerced: object = val.lower() in ("1", "true", "yes", "on")
            elif isinstance(current, int) and not isinstance(current, bool):
                coerced = int(val)
            elif isinstance(current, float):
                coerced = float(val)
            else:
                coerced = val
        except ValueError:
            continue
        setattr(settings, key, coerced)
        os.environ[key] = val
