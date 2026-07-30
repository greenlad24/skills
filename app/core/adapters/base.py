"""Abstract provider interfaces + the uniform ProviderResult (§1.6).

Every external provider sits behind one of these Protocols. Common patterns:
  * async submit/poll for long jobs; every billable method takes an `idempotency_key`.
  * every method returns a `ProviderResult` carrying `cost_usd` + `usage` so the cost
    ledger is populated uniformly.

Method signatures here are the CONTRACT module agents implement against — do not change
them without updating docs/CONTRACTS.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ProviderResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0
    usage: dict[str, Any] = field(default_factory=dict)  # tokens / seconds / credits
    provider_job_id: str | None = None                   # set for async jobs
    error: str | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """Research synthesis, formula/hook extraction, Thai scripting, claim-safety gate."""

    def complete(
        self,
        *,
        prompt: str,
        system: str | None,
        model: str,
        max_tokens: int,
        idempotency_key: str,
    ) -> ProviderResult: ...


@runtime_checkable
class ScraperProvider(Protocol):
    def scrape_product(self, *, url: str, idempotency_key: str) -> ProviderResult: ...

    def mine_top_videos(
        self, *, query: str, market: str, limit: int, idempotency_key: str
    ) -> ProviderResult: ...


@runtime_checkable
class TTSProvider(Protocol):
    def synthesize(
        self,
        *,
        text: str,
        voice_id: str,
        language: str,
        model: str,
        idempotency_key: str,
    ) -> ProviderResult: ...
    # returns audio object key + duration in data


@runtime_checkable
class AvatarProvider(Protocol):
    def submit_talking_head(
        self,
        *,
        avatar_id: str,
        audio_key: str,
        script_text: str,
        aspect: str,
        idempotency_key: str,
    ) -> ProviderResult: ...

    def poll(self, *, provider_job_id: str) -> ProviderResult: ...


@runtime_checkable
class VideoGenProvider(Protocol):
    def generate_hero_image(
        self, *, prompt: str, refs: list[str], idempotency_key: str
    ) -> ProviderResult: ...

    def submit_image_to_video(
        self,
        *,
        image_key: str,
        prompt: str,
        model: str,
        seconds: float,
        aspect: str,
        idempotency_key: str,
    ) -> ProviderResult: ...

    def poll(self, *, provider_job_id: str) -> ProviderResult: ...


@runtime_checkable
class PostingProvider(Protocol):
    def publish(
        self,
        *,
        video_key: str,
        caption: str,
        platform: str,
        ai_disclosure: bool,
        schedule_at: str | None,
        idempotency_key: str,
    ) -> ProviderResult: ...

    def fetch_metrics(self, *, external_post_id: str) -> ProviderResult: ...
    # fetch_metrics powers the winner-detection feedback loop.
