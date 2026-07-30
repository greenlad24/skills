"""Unit tests for the reference Anthropic LLM adapter (no network).

We inject a fake ``anthropic`` module into ``sys.modules`` so the adapter can be
exercised without the real SDK installed and without any API call.
"""

from __future__ import annotations

import sys
import types

import pytest

from app.core.adapters.real import anthropic_llm as mod
from app.core.config import settings


# --- pure-function tests (no SDK needed) ------------------------------------ #

def test_price_lookup_by_prefix():
    assert mod._price_for("claude-opus-5") == (5.0, 25.0)
    assert mod._price_for("claude-haiku-4-5") == (1.0, 5.0)
    assert mod._price_for("claude-haiku-4-5-20251001") == (1.0, 5.0)  # dated id
    assert mod._price_for("some-unknown-model") == mod._DEFAULT_PRICE


def test_cost_math():
    # 1M input @ $5 + 1M output @ $25 = $30
    assert mod._cost_usd("claude-opus-5", 1_000_000, 1_000_000) == pytest.approx(30.0)
    assert mod._cost_usd("claude-haiku-4-5", 500_000, 200_000) == pytest.approx(0.5 + 1.0)


# --- adapter behavior with a faked SDK -------------------------------------- #

def _install_fake_anthropic(monkeypatch, *, message=None, raise_status=None):
    """Build a minimal fake ``anthropic`` module and install it.

    ``raise_status`` = (status_code, message) makes ``create`` raise the fake's OWN
    ``APIStatusError`` — so it matches the ``except`` clause inside the adapter,
    which references ``self._anthropic.APIStatusError`` from this same fake module.
    """

    class APIError(Exception):
        pass

    class APIStatusError(APIError):
        def __init__(self, status_code, message):
            super().__init__(message)
            self.status_code = status_code
            self.message = message

    class _Messages:
        def create(self, **kwargs):
            if raise_status is not None:
                raise APIStatusError(*raise_status)
            return message

    class Anthropic:
        def __init__(self, *args, **kwargs):
            self.messages = _Messages()

    fake = types.ModuleType("anthropic")
    fake.Anthropic = Anthropic
    fake.APIError = APIError
    fake.APIStatusError = APIStatusError
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test-key", raising=False)
    return fake


def _fake_message(text, *, stop_reason="end_turn", in_tok=100, out_tok=50):
    text_block = types.SimpleNamespace(type="text", text=text)
    usage = types.SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok)
    return types.SimpleNamespace(
        content=[text_block], usage=usage, stop_reason=stop_reason,
        model="claude-opus-5", id="msg_123",
    )


def test_complete_success(monkeypatch):
    _install_fake_anthropic(monkeypatch, message=_fake_message("สวัสดีค่ะ"))
    provider = mod.AnthropicLLMProvider()
    result = provider.complete(
        prompt="write a Thai hook", system="you are a copywriter",
        model="claude-opus-5", max_tokens=1024, idempotency_key="k1",
    )
    assert result.ok is True
    assert result.data["text"] == "สวัสดีค่ะ"
    assert result.usage == {"input_tokens": 100, "output_tokens": 50}
    # 100 in @ $5/M + 50 out @ $25/M
    assert result.cost_usd == pytest.approx(100 / 1e6 * 5 + 50 / 1e6 * 25)
    assert result.provider_job_id == "msg_123"


def test_complete_refusal_is_failure(monkeypatch):
    _install_fake_anthropic(monkeypatch, message=_fake_message("", stop_reason="refusal"))
    provider = mod.AnthropicLLMProvider()
    result = provider.complete(
        prompt="do something disallowed", system=None,
        model="claude-opus-5", max_tokens=256, idempotency_key="k2",
    )
    assert result.ok is False
    assert "refusal" in (result.error or "")


def test_complete_api_error_is_failure(monkeypatch):
    _install_fake_anthropic(monkeypatch, raise_status=(429, "rate limited"))
    provider = mod.AnthropicLLMProvider()
    result = provider.complete(
        prompt="hi", system=None, model="claude-opus-5",
        max_tokens=256, idempotency_key="k3",
    )
    assert result.ok is False
    assert "429" in (result.error or "")


def test_missing_api_key_raises(monkeypatch):
    _install_fake_anthropic(monkeypatch, message=_fake_message("x"))
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "", raising=False)
    with pytest.raises(RuntimeError):
        mod.AnthropicLLMProvider()
