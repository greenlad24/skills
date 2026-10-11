"""Claude provider (official Anthropic Python SDK)."""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path

import anthropic

from . import prompts
from .plan_schema import PLAN_SCHEMA

MAX_CONTINUATIONS = 6


def _client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key or None, timeout=900.0, max_retries=3)


def _image_blocks(paths: list) -> list:
    blocks = []
    for p in paths[:6]:
        path = Path(p)
        mt = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        if mt not in ("image/jpeg", "image/png", "image/gif", "image/webp") or not path.exists():
            continue
        if path.stat().st_size > 4_500_000:
            continue
        data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
        blocks.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}})
    return blocks


def _text(msg) -> str:
    return "".join(b.text for b in msg.content if b.type == "text")


def _check(msg) -> None:
    if msg.stop_reason == "refusal":
        cat = getattr(getattr(msg, "stop_details", None), "category", None)
        raise RuntimeError(f"Claude declined this request (category: {cat}). Try rephrasing the product input.")


def research(gathered: dict, settings: dict, log=print) -> str:
    """Web-search research pass → plain-text dossier."""
    client = _client(settings.get("anthropic_api_key", ""))
    content = _image_blocks(gathered.get("user_images", []) + gathered.get("product_images", [])[:2])
    content.append({"type": "text", "text": prompts.research_prompt(gathered)})
    messages = [{"role": "user", "content": content}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 12}]
    msg = None
    for i in range(MAX_CONTINUATIONS):
        log("Researching on the web with Claude…" if i == 0 else "Research continuing…")
        with client.beta.messages.stream(
            model=settings["claude_model"],
            max_tokens=32000,
            output_config={"effort": "medium"},
            tools=tools,
            messages=messages,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            msg = stream.get_final_message()
        _check(msg)
        if msg.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": msg.content}]
    return _text(msg) if msg else ""


def make_plan(gathered: dict, dossier: str, settings: dict, log=print) -> dict:
    n = int(settings.get("videos_per_product", 5))
    try:
        return _make_plan(gathered, dossier, settings, n, log, structured=True)
    except anthropic.BadRequestError as e:
        # If the API rejects the (large) JSON schema, ask for JSON in the prompt instead.
        if "schema" not in str(e).lower() and "output_config" not in str(e).lower():
            raise
        log("Structured output unavailable — retrying with JSON instructions…")
        return _make_plan(gathered, dossier, settings, n, log, structured=False)


def _make_plan(gathered, dossier, settings, n, log, structured: bool) -> dict:
    client = _client(settings.get("anthropic_api_key", ""))
    content = _image_blocks(gathered.get("user_images", []))
    text = prompts.plan_prompt(gathered, dossier, n)
    output_config = {"effort": settings.get("claude_effort", "high")}
    if structured:
        output_config["format"] = {"type": "json_schema", "schema": PLAN_SCHEMA}
    else:
        text += ("\n\nReply with ONE JSON object only (no markdown fences) matching this JSON Schema; "
                 "every property is required:\n" + json.dumps(PLAN_SCHEMA, ensure_ascii=False))
    content.append({"type": "text", "text": text})
    log(f"Writing {n} scripts, shot lists and edit plans with Claude…")
    with client.beta.messages.stream(
        model=settings["claude_model"],
        max_tokens=64000,
        system=[{"type": "text", "text": prompts.system_prompt(n), "cache_control": {"type": "ephemeral"}}],
        output_config=output_config,
        messages=[{"role": "user", "content": content}],
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    ) as stream:
        msg = stream.get_final_message()
    _check(msg)
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("The plan was cut off (too long). Try fewer videos per product in Settings.")
    out = _text(msg)
    if not structured:
        out = out[out.find("{"): out.rfind("}") + 1]
    return json.loads(out)


def explain_error(e: Exception) -> str:
    if isinstance(e, anthropic.AuthenticationError):
        return "Claude API key is invalid — check Settings."
    if isinstance(e, anthropic.PermissionDeniedError):
        return "This API key can't use that model or feature."
    if isinstance(e, anthropic.NotFoundError):
        return "Model not found — check the model name in Settings."
    if isinstance(e, anthropic.RateLimitError):
        return "Claude rate limit hit — wait a minute and try again."
    if isinstance(e, anthropic.APIStatusError):
        return f"Claude API error {e.status_code}: {e.message}"
    if isinstance(e, anthropic.APIConnectionError):
        return "Can't reach Claude — check the internet connection."
    return str(e)


def make_edl(prompt: str, images: list, schema: dict, settings: dict, log=print, workdir=None) -> dict:
    """Video editor pass: clip contact sheets + voice timing in, cut list (JSON) out."""
    client = _client(settings.get("anthropic_api_key", ""))
    content = []
    for p in images[:20]:
        content += [{"type": "text", "text": f"Frames image {Path(p).name}:"}] + _image_blocks([p])
    content.append({"type": "text", "text": prompt})
    with client.beta.messages.stream(
        model=settings["claude_model"],
        max_tokens=16000,
        output_config={"effort": settings.get("claude_effort", "high"),
                       "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": content}],
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    ) as stream:
        msg = stream.get_final_message()
    _check(msg)
    return json.loads(_text(msg))
