"""Anthropic LLM provider — the REFERENCE real adapter (§1.6).

Implements ``LLMProvider`` against the official ``anthropic`` SDK. Used by the
research (formula/hook extraction), generation (Thai scripting) and compliance
(claim-safety classifier) modules via ``registry.get_llm_provider()``.

Why this is the reference: it shows the full shape every real adapter must have —
conform to the core Protocol exactly, read the API key from ``settings`` (never
``os.environ``), translate the vendor response into a uniform ``ProviderResult``
with ``cost_usd`` + ``usage`` so the cost ledger is populated, and fail into
``ProviderResult(ok=False, error=...)`` instead of raising, so a stage records a
clean failure rather than crashing the worker.

Copy this file's structure for the other vendors (fal / HeyGen / ElevenLabs /
Apify / PostPeer). Only the SDK calls in ``complete`` change.

Notes on the Anthropic API (current models — Opus 5 / 4.8, Sonnet 5, Haiku 4.5):
  * ``temperature`` / ``top_p`` / ``top_k`` are rejected (400) on Opus 5 / 4.8 /
    Sonnet 5 — this adapter never sends them. Callers that need determinism
    (the claim classifier) instruct it in the prompt/system text instead.
  * ``budget_tokens`` thinking config is removed on those models — not sent.
  * ``max_tokens`` above ~16k must stream or the SDK raises a timeout guard, so
    this adapter streams when ``max_tokens`` is large.
"""

from __future__ import annotations

from app.core.adapters.base import ProviderResult
from app.core.adapters.registry import register_real
from app.core.config import settings

# Published API prices per 1M tokens (input, output), USD. Used to populate the
# cost ledger. Matched by longest-prefix so dated IDs resolve too. Unknown models
# fall back to Opus-tier pricing (a safe over-estimate for budgeting).
_PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
_DEFAULT_PRICE = (5.0, 25.0)
# Default model when a caller passes an empty model string. Capable + safe;
# cost-sensitive callers pass a cheaper model (e.g. claude-haiku-4-5) explicitly.
_DEFAULT_MODEL = "claude-opus-5"
# Above this max_tokens the non-streaming SDK call risks an HTTP-timeout guard.
_STREAM_THRESHOLD = 16000


def _price_for(model: str) -> tuple[float, float]:
    for prefix, price in _PRICE_PER_MTOK.items():
        if model.startswith(prefix):
            return price
    return _DEFAULT_PRICE


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = _price_for(model)
    return (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate


class AnthropicLLMProvider:
    """Real ``LLMProvider`` backed by the Anthropic Messages API."""

    def __init__(self) -> None:
        # Imported here (not at module top) so a missing/uninstalled SDK only
        # surfaces when a real call is actually made, never during DRY_RUN import.
        import anthropic

        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set — required for the real LLM provider. "
                "Set it in .env, or run with DRY_RUN=true for the fake provider."
            )
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def complete(
        self,
        *,
        prompt: str,
        system: str | None,
        model: str,
        max_tokens: int,
        idempotency_key: str,
    ) -> ProviderResult:
        model = model or _DEFAULT_MODEL
        # Idempotency-Key is a harmless extra header if the endpoint ignores it,
        # and dedups retried submissions if it doesn't.
        extra_headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        if extra_headers:
            kwargs["extra_headers"] = extra_headers

        try:
            if max_tokens > _STREAM_THRESHOLD:
                # Stream to avoid the SDK's long-request timeout guard, then
                # collect the final accumulated message.
                with self._client.messages.stream(**kwargs) as stream:
                    message = stream.get_final_message()
            else:
                message = self._client.messages.create(**kwargs)
        except self._anthropic.APIStatusError as exc:  # 4xx/5xx with a response
            return ProviderResult(ok=False, error=f"anthropic {exc.status_code}: {exc.message}")
        except self._anthropic.APIError as exc:  # connection / timeout / etc.
            return ProviderResult(ok=False, error=f"anthropic error: {exc}")

        # A safety refusal returns HTTP 200 with stop_reason "refusal" and
        # (usually) empty content — surface it as a typed failure, not text.
        if getattr(message, "stop_reason", None) == "refusal":
            return ProviderResult(
                ok=False,
                error="anthropic refusal",
                usage={
                    "input_tokens": message.usage.input_tokens,
                    "output_tokens": message.usage.output_tokens,
                },
            )

        text = "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )
        in_tok = message.usage.input_tokens
        out_tok = message.usage.output_tokens
        return ProviderResult(
            ok=True,
            data={"text": text, "stop_reason": message.stop_reason, "model": message.model},
            cost_usd=_cost_usd(model, in_tok, out_tok),
            usage={"input_tokens": in_tok, "output_tokens": out_tok},
            provider_job_id=getattr(message, "id", None),
        )


# Register under LLM_PROVIDER="anthropic" (the config default). Selected by the
# registry only when DRY_RUN is false.
register_real("llm", "anthropic", AnthropicLLMProvider)
