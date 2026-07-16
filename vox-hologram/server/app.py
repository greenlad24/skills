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

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, llm, personality, stt, tts

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


class TTSRequest(BaseModel):
    text: str


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
            "voice": config.voice_name(),
            "portrait_url": config.portrait_url(),
            "portrait_present": config.portrait_present(),
            "name": personality.VOX_NAME,
        }
    )


# --- API: chat (SSE) --------------------------------------------------------
@app.post("/api/chat")
async def post_chat(req: ChatRequest) -> StreamingResponse:
    """Stream Vox's reply as Server-Sent Events.

    Builds ``[system persona] + history + [user message]`` and relays the LLM's
    token deltas as ``{"type":"token"}`` frames, closing with ``{"type":"done"}``
    (or ``{"type":"error"}`` on failure).
    """
    system_prompt = personality.build_system_prompt(
        current_date=_current_date(),
        has_face=config.portrait_present(),
    )
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(_sanitize_history(req.history))
    messages.append({"role": "user", "content": req.message})

    async def event_stream():
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
