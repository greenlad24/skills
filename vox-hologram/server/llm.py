"""OpenAI-compatible streaming chat client for VOX.

Talks to whatever local backend exposes an OpenAI-style ``/v1`` API — Ollama
(``http://localhost:11434/v1``) or llama.cpp's ``llama-server``
(``http://localhost:8080/v1``). Connections are lazy and per-request: nothing
here runs at import or startup, so a missing / stopped LLM server never crashes
VOX — it simply surfaces as an error event on the SSE stream for that turn.

The public surface is:
- ``stream_chat(messages)``  async generator yielding token text as it arrives.
- ``probe_ready()``          best-effort, short-timeout readiness check.
"""

from __future__ import annotations

import json
from typing import AsyncIterator, Dict, List

import httpx

from . import config

# A request-scoped client is created per call; these bound how long we wait.
# Connect is short (the server is local); read has no hard cap because token
# streams can be long, but an initial-response timeout guards a dead backend.
_CONNECT_TIMEOUT = 5.0
_STREAM_TIMEOUT = httpx.Timeout(connect=_CONNECT_TIMEOUT, read=None, write=30.0, pool=30.0)


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {config.llm_api_key()}",
        "Content-Type": "application/json",
    }


async def stream_chat(messages: List[Dict[str, str]]) -> AsyncIterator[str]:
    """Stream assistant token text for the given chat ``messages``.

    ``messages`` is a full OpenAI-style list (system + history + latest user).
    Yields the incremental ``choices[0].delta.content`` strings as they arrive.
    Raises on transport/HTTP errors so the caller can emit an SSE error event.
    """
    payload = {
        "model": config.llm_model(),
        "messages": messages,
        "stream": True,
    }
    url = config.llm_base_url() + "/chat/completions"

    async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT) as client:
        async with client.stream("POST", url, headers=_headers(), json=payload) as response:
            response.raise_for_status()
            # OpenAI-compatible servers stream Server-Sent Events: lines like
            # ``data: {json}`` terminated by a ``data: [DONE]`` sentinel.
            async for raw_line in response.aiter_lines():
                if not raw_line:
                    continue
                line = raw_line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    # Ignore keep-alives / malformed fragments rather than abort.
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                text = delta.get("content")
                if text:
                    yield text


async def probe_ready(timeout: float = 1.5) -> bool:
    """Best-effort check that the LLM backend is reachable.

    Does a quick ``GET /models``. Never raises: returns True on a 2xx, and — to
    avoid a false 'offline' banner when the endpoint merely differs — returns
    True when uncertain, False only on a clear connection failure.
    """
    url = config.llm_base_url() + "/models"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=_headers())
        if response.status_code < 500:
            return True
        return True  # server answered (even an error) => it's up
    except (httpx.ConnectError, httpx.ConnectTimeout):
        return False
    except httpx.HTTPError:
        # Ambiguous (read timeout, protocol quirk): don't block the UI.
        return True
