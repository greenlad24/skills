"""VOX FastAPI application — routes, static hosting, and hand-rolled SSE.

This is the process entrypoint: ``uvicorn server.app:app`` (or ``python -m
server.app``) serves the hologram front-end from ``web/`` and the JSON/stream API
defined in ``API.md``. Design rules honored here:

- Never crash on startup because a local dependency (Ollama / Piper / whisper) is
  missing — capabilities are probed lazily and reported via ``GET /api/config``.
- The LLM is contacted only per request, streaming tokens back as SSE that we
  build by hand (no sse-starlette) with ``StreamingResponse``.
- Only fastapi, uvicorn[standard], httpx, python-multipart + stdlib are used.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, llm, personality, stt, tts, web

app = FastAPI(title="VOX — Local Hologram Librarian", version="1.0.0")

# CORS: open to localhost for dev convenience (single-user local app). Allowing a
# regex keeps any localhost/127.0.0.1 port working without an allow-list.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request models ---------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []
    # v2: opt in/out of the web/sources layer for this turn. ``None`` = use the
    # server's default (``web_ready``). Ignored entirely when ``VOX_WEB=0``.
    web: Optional[bool] = None


class TTSRequest(BaseModel):
    text: str


class SearchRequest(BaseModel):
    query: str
    count: Optional[int] = 4


class FetchRequest(BaseModel):
    url: Optional[str] = None


# --- Helpers ----------------------------------------------------------------
def _current_date() -> str:
    """Human-readable current date for the persona. Honors VOX_DATE if set so the
    'patron's world' date is deterministic; otherwise uses the system clock."""
    override = os.environ.get("VOX_DATE")
    if override and override.strip():
        return override.strip()
    return datetime.now().strftime("%A, %d %B %Y")


def _sse(event: Dict[str, object]) -> str:
    """Encode one dict as a single SSE ``data:`` frame (UTF-8, newline-safe)."""
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


def _sanitize_history(history: List[ChatMessage]) -> List[Dict[str, str]]:
    """Keep only well-formed user/assistant turns; drop any injected system rows
    (the backend owns the persona)."""
    clean: List[Dict[str, str]] = []
    for item in history:
        role = item.role
        if role in ("user", "assistant") and item.content:
            clean.append({"role": role, "content": item.content})
    return clean


# Words that mark a factual/knowledge question worth consulting the library for.
_WH_WORDS = {
    "who", "what", "when", "where", "why", "how", "which", "whose", "whom",
    "is", "are", "was", "were", "does", "do", "did", "can", "could", "will",
    "tell", "explain", "define", "describe", "list", "name", "compare",
}
# Short social openers that should NOT trigger a web search.
_GREETINGS = {
    "hi", "hello", "hey", "yo", "sup", "hiya", "howdy", "greetings", "hola",
    "thanks", "thank", "thx", "ta", "cheers", "bye", "goodbye", "ok", "okay",
    "cool", "nice", "great", "yes", "no", "yep", "nope", "please",
}


def _looks_like_knowledge_query(message: str) -> bool:
    """Heuristic: is this turn worth pulling live sources for?

    True when the message is >= 4 words, OR contains "?", OR opens with / uses a
    wh-word — but greetings and very short one-liners are skipped so a friendly
    "hello" never fires a web search.
    """
    text = (message or "").strip()
    if not text:
        return False
    words = re.findall(r"[a-z0-9']+", text.lower())
    if len(words) < 2:
        return False
    if words[0] in _GREETINGS and len(words) <= 3:
        return False
    if "?" in text:
        return True
    if any(w in _WH_WORDS for w in words):
        return True
    return len(words) >= 4


# --- API: capabilities ------------------------------------------------------
@app.get("/api/config")
async def get_config() -> JSONResponse:
    """Report runtime capabilities so the frontend can adapt/degrade."""
    return JSONResponse(
        {
            "model": config.llm_model(),
            "llm_ready": await llm.probe_ready(),
            "tts_ready": config.tts_ready(),
            "stt_ready": config.stt_ready(),
            # web_ready = feature enabled AND the internet is (best-effort)
            # reachable. The reachability probe is short-timeout, briefly cached,
            # and only runs here at request time — never at import/startup.
            "web_ready": config.web_enabled() and await web.reachable(),
            "voice": config.voice_name(),
            "portrait_url": config.portrait_url(),
            "portrait_present": config.portrait_present(),
            "face_box": config.face_box(),
            "name": personality.VOX_NAME,
        }
    )


# --- API: chat (SSE) --------------------------------------------------------
# Total wall-clock budget for the web/sources phase of a single chat turn. If
# search + top-result fetch can't finish inside this, we silently skip panels and
# let Vox answer from local knowledge — the web must never stall the reply.
_WEB_SEARCH_BUDGET = 7.0
_WEB_FETCH_BUDGET = 9.0


async def _web_phase(message: str):
    """Run the search + top-result fetch for a turn.

    Returns ``(panels, grounding)`` where ``panels`` is a list of SSE-ready panel
    dicts (source cards first, then one reader card) and ``grounding`` is a
    context string to inject before the user's turn (or ``None``). Never raises —
    any failure yields ``([], None)`` so the chat proceeds regardless.
    """
    panels: List[Dict[str, object]] = []
    grounding: Optional[str] = None
    try:
        results = await asyncio.wait_for(
            web.search(message, count=4), timeout=_WEB_SEARCH_BUDGET
        )
    except Exception:  # noqa: BLE001 — slow/failed search => no panels
        results = []

    if not results:
        return panels, grounding

    for i, r in enumerate(results):
        panel: Dict[str, object] = {
            "id": "p{}".format(i + 1),
            "kind": "source",
            "title": r.get("title"),
            "url": r.get("url"),
            "snippet": r.get("snippet"),
            "source": r.get("source"),
        }
        if r.get("image"):
            panel["image"] = r["image"]
        panels.append(panel)

    # Fetch just the single top result for an expanded "reader" card.
    try:
        reader = await asyncio.wait_for(
            web.fetch(results[0]["url"]), timeout=_WEB_FETCH_BUDGET
        )
        if reader and not reader.get("error"):
            reader_panel: Dict[str, object] = {
                "id": "reader1",
                "kind": "reader",
                "title": reader.get("title") or results[0].get("title"),
                "url": reader.get("url") or results[0].get("url"),
                "text": reader.get("text"),
                "images": reader.get("images") or [],
                "source": reader.get("source") or results[0].get("source"),
            }
            if reader.get("image"):
                reader_panel["image"] = reader["image"]
            panels.append(reader_panel)
    except Exception:  # noqa: BLE001 — reader is optional; skip on any failure
        pass

    # Ground the spoken answer on the snippets, in-character and URL-free.
    lines = []
    for i, r in enumerate(results):
        title = (r.get("title") or "").strip()
        snippet = (r.get("snippet") or "").strip()
        lines.append("[{}] {} — {}".format(i + 1, title, snippet))
    grounding = (
        "Relevant sources (cite naturally, do not list raw URLs or invent "
        "details):\n" + "\n".join(lines)
    )
    return panels, grounding


@app.post("/api/chat")
async def post_chat(req: ChatRequest) -> StreamingResponse:
    """Stream Vox's reply as Server-Sent Events.

    Builds ``[system persona] + history + [optional grounding] + [user message]``
    and relays the LLM's token deltas as ``{"type":"token"}`` frames, closing with
    ``{"type":"done"}`` (or ``{"type":"error"}`` on failure).

    v2: when the web layer is enabled + reachable (or explicitly requested) and
    the turn looks like a knowledge query, it first performs a live search, emits
    ``panel`` frames (source cards + one reader card), and grounds the answer on
    the results. Any web failure is swallowed so the chat response is never broken.
    """
    system_prompt = personality.build_system_prompt(
        current_date=_current_date(),
        has_face=config.portrait_present(),
    )
    history = _sanitize_history(req.history)

    # Resolve whether to consult the web for this turn.
    web_on = config.web_enabled()
    if req.web is None:
        default_web = (await web.reachable()) if web_on else False
    else:
        default_web = bool(req.web)
    do_web = (
        web_on
        and default_web
        and _looks_like_knowledge_query(req.message)
    )

    async def event_stream():
        # --- Web/sources phase (panels + grounding) — never breaks the chat. ---
        grounding: Optional[str] = None
        if do_web:
            try:
                panels, grounding = await _web_phase(req.message)
                for panel in panels:
                    yield _sse({"type": "panel", "panel": panel})
            except Exception:  # noqa: BLE001 — belt-and-suspenders; answer anyway
                grounding = None

        # --- Assemble the LLM conversation. ---
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]
        messages.extend(history)
        if grounding:
            messages.append({"role": "system", "content": grounding})
        messages.append({"role": "user", "content": req.message})

        # --- Stream tokens (unchanged graceful-LLM-down behavior). ---
        parts: List[str] = []
        try:
            async for token in llm.stream_chat(messages):
                parts.append(token)
                yield _sse({"type": "token", "text": token})
            yield _sse({"type": "done", "text": "".join(parts)})
        except Exception as exc:  # noqa: BLE001 — surface any failure to the client
            yield _sse({"type": "error", "message": str(exc)})

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # disable proxy buffering if one is present
    }
    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=headers
    )


# --- API: text-to-speech ----------------------------------------------------
@app.post("/api/tts")
async def post_tts(req: TTSRequest):
    """Synthesize ``text`` to a WAV via Piper. 503 if TTS is unavailable."""
    try:
        audio = await tts.synthesize(req.text)
    except tts.TTSUnavailable:
        return JSONResponse({"error": "tts_unavailable"}, status_code=503)
    return StreamingResponse(iter([audio]), media_type="audio/wav")


# --- API: speech-to-text (optional) -----------------------------------------
@app.post("/api/stt")
async def post_stt(audio: UploadFile = File(...)):
    """Transcribe an uploaded audio blob via whisper.cpp. 503 if unavailable."""
    try:
        data = await audio.read()
        text = await stt.transcribe(data)
    except stt.STTUnavailable:
        return JSONResponse({"error": "stt_unavailable"}, status_code=503)
    return JSONResponse({"text": text})


# --- API: web search (v2) ---------------------------------------------------
@app.post("/api/search")
async def post_search(req: SearchRequest):
    """Dependency-free web search. 503 if the web feature is disabled."""
    if not config.web_enabled():
        return JSONResponse({"error": "web_unavailable"}, status_code=503)
    count = req.count if isinstance(req.count, int) and req.count > 0 else 4
    results = await web.search(req.query, count=count)
    return JSONResponse({"results": results})


# --- API: page fetch / reader (v2) ------------------------------------------
@app.post("/api/fetch")
async def post_fetch(req: FetchRequest):
    """Fetch + clean a page into a reader payload. 503 if disabled, 400 if the
    URL is missing or not http(s)."""
    if not config.web_enabled():
        return JSONResponse({"error": "web_unavailable"}, status_code=503)
    url = (req.url or "").strip()
    if not url or not re.match(r"^https?://", url, re.IGNORECASE):
        return JSONResponse({"error": "invalid_url"}, status_code=400)
    data = await web.fetch(url)
    return JSONResponse(data)


# --- Static hosting ---------------------------------------------------------
# Mount the front-end LAST so explicit /api routes win. Guarded so a not-yet-
# created web/ dir (built by the frontend agent) never crashes startup.
if config.WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(config.WEB_DIR), html=True), name="web")
else:  # pragma: no cover - dev fallback before the front-end exists
    @app.get("/")
    async def _no_web() -> JSONResponse:
        return JSONResponse(
            {"name": personality.VOX_NAME, "detail": "web/ not built yet"},
            status_code=200,
        )


def main() -> None:
    """Run the app with uvicorn, honoring VOX_PORT."""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=config.port())


if __name__ == "__main__":
    main()
