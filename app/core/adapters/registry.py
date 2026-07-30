"""Provider registry / factory — selects real vs fake implementations (§1.6).

Selection rule:
  * If `settings.DRY_RUN` is true → always return the deterministic Fake ($0, no network).
  * Otherwise → return the concrete real implementation registered for the configured
    `*_PROVIDER` env var.

Real vendor adapters (HeyGenAvatarProvider, FalVideoGenProvider, ...) are the only place
vendor SDKs get imported. In this P0 foundation none are implemented yet; a module/vendor
agent registers one with `register_real(...)`. Requesting a real provider that has not been
registered raises a clear error instead of silently doing nothing.

Business logic calls `get_*_provider()` and never constructs providers directly.
"""

from __future__ import annotations

from typing import Any, Callable

from app.core.adapters.base import (
    AvatarProvider,
    LLMProvider,
    PostingProvider,
    ScraperProvider,
    TTSProvider,
    VideoGenProvider,
)
from app.core.adapters.fakes import FAKE_PROVIDERS
from app.core.config import settings

# Registry of REAL implementations: {capability: {provider_key: factory}}.
# Populated by vendor adapter modules at import time via `register_real`.
_REAL_REGISTRY: dict[str, dict[str, Callable[[], Any]]] = {
    "llm": {},
    "scraper": {},
    "tts": {},
    "avatar": {},
    "videogen": {},
    "posting": {},
}


def register_real(capability: str, provider_key: str, factory: Callable[[], Any]) -> None:
    """Register a real provider factory for a capability + provider_key.

    e.g. register_real("videogen", "fal", FalVideoGenProvider)
    """
    if capability not in _REAL_REGISTRY:
        raise ValueError(f"Unknown capability {capability!r}")
    _REAL_REGISTRY[capability][provider_key] = factory


def _resolve(capability: str, provider_key: str) -> Any:
    """Return an instance of the fake (DRY_RUN) or the registered real provider."""
    if settings.DRY_RUN:
        return FAKE_PROVIDERS[capability]()

    factories = _REAL_REGISTRY.get(capability, {})
    factory = factories.get(provider_key)
    if factory is None:
        raise NotImplementedError(
            f"No real {capability} provider registered for "
            f"{capability.upper()}_PROVIDER={provider_key!r}. "
            f"Either set DRY_RUN=true, or register one via "
            f"adapters.registry.register_real({capability!r}, {provider_key!r}, <Factory>)."
        )
    return factory()


# --------------------------------------------------------------------------- #
# Typed accessors (business logic imports these).
# --------------------------------------------------------------------------- #
def get_llm_provider() -> LLMProvider:
    return _resolve("llm", settings.LLM_PROVIDER)


def get_scraper_provider() -> ScraperProvider:
    return _resolve("scraper", settings.SCRAPER_PROVIDER)


def get_tts_provider() -> TTSProvider:
    return _resolve("tts", settings.TTS_PROVIDER)


def get_avatar_provider() -> AvatarProvider:
    return _resolve("avatar", settings.AVATAR_PROVIDER)


def get_video_gen_provider() -> VideoGenProvider:
    return _resolve("videogen", settings.VIDEOGEN_PROVIDER)


def get_posting_provider() -> PostingProvider:
    return _resolve("posting", settings.POSTING_PROVIDER)
