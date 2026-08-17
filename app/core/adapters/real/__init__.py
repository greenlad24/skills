"""Real (non-DRY_RUN) provider implementations.

Importing this package registers every real adapter with the registry via
``register_real(...)`` at import time. The registry imports it lazily — only when
``settings.DRY_RUN`` is false — so vendor SDKs (e.g. ``anthropic``) are never
imported during dry-run development or tests.

This is the REFERENCE pattern for adding a real provider:
  1. Create ``app/core/adapters/real/<vendor>_<capability>.py``.
  2. Implement the matching Protocol from ``app.core.adapters.base``.
  3. Call ``register_real("<capability>", "<provider_key>", <Factory>)`` at module
     top level.
  4. Import it here so registration runs.
  5. Declare the vendor SDK in ``requirements.txt``.

``anthropic_llm`` is the worked example — copy its shape for fal (videogen),
HeyGen (avatar), ElevenLabs (tts), Apify/Firecrawl (scraper), PostPeer (posting).
"""

from __future__ import annotations

# Importing each module runs its register_real(...) call. This is the single
# approved stack — LLM (Anthropic), Thai TTS (Google), video (LTX-2.5 on Modal),
# posting (TikTok Content Posting API).
from app.core.adapters.real import anthropic_llm  # noqa: F401
from app.core.adapters.real import ltx_modal  # noqa: F401  (serverless LTX-2.5 via Modal)
from app.core.adapters.real import google_tts  # noqa: F401  (near-free Thai TTS)
from app.core.adapters.real import tiktok_posting  # noqa: F401  (free TikTok posting)

__all__ = [
    "anthropic_llm",
    "ltx_modal",
    "google_tts",
    "tiktok_posting",
]
