"""Provider-agnostic external-service adapter layer (§1.6).

The ONLY place vendor SDKs may be imported. Business logic depends solely on the
Protocol interfaces in `base.py`; concrete implementations are selected by
`registry.py` from settings, and swapped to deterministic `fakes.py` when DRY_RUN.
"""

from app.core.adapters.base import (  # noqa: F401
    AvatarProvider,
    LLMProvider,
    PostingProvider,
    ProviderResult,
    ScraperProvider,
    TTSProvider,
    VideoGenProvider,
)
