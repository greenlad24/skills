"""Runtime configuration and capability detection for VOX.

Everything the backend needs to know is resolved from environment variables here,
with sensible defaults for the two supported local LLM backends (Ollama and
llama.cpp). Nothing in this module makes a blocking network call at import time —
capability probing is best-effort and cheap so the server always starts, even if
Ollama / Piper / whisper are absent. The frontend reads the resulting flags from
``GET /api/config`` and degrades gracefully.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# --- Paths -----------------------------------------------------------------
# All paths are resolved relative to THIS file so the server can be launched
# from any working directory (``uvicorn server.app:app`` from the repo root, or
# ``python -m server.app`` from anywhere).
SERVER_DIR = Path(__file__).resolve().parent
REPO_DIR = SERVER_DIR.parent          # .../vox-hologram
WEB_DIR = REPO_DIR / "web"            # static front-end (owned by frontend agent)
ASSETS_DIR = WEB_DIR / "assets"

# Portrait may be supplied by the user in any common web image format.
PORTRAIT_CANDIDATES = ("portrait.png", "portrait.jpg", "portrait.jpeg", "portrait.webp")


def _env(name: str, default: str) -> str:
    """Read an env var, treating empty/whitespace as unset."""
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value


# --- Server ----------------------------------------------------------------
def port() -> int:
    """TCP port for uvicorn (VOX_PORT, default 8008)."""
    try:
        return int(_env("VOX_PORT", "8008"))
    except ValueError:
        return 8008


# --- LLM (OpenAI-compatible endpoint: Ollama or llama.cpp) ------------------
def llm_base_url() -> str:
    """Base URL of the OpenAI-compatible LLM API (must include the /v1 suffix)."""
    return _env("VOX_LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")


def llm_model() -> str:
    """Model tag to request from the LLM backend."""
    return _env("VOX_LLM_MODEL", "llama3.2:3b")


def llm_api_key() -> str:
    """API key sent as a Bearer token. Local backends ignore it; a placeholder
    keeps the OpenAI-compatible clients happy."""
    return _env("VOX_LLM_API_KEY", "ollama")


# --- TTS (Piper) -----------------------------------------------------------
def piper_bin() -> str:
    """Name or path of the Piper executable."""
    return _env("VOX_PIPER_BIN", "piper")


def piper_voice() -> Path:
    """Path to the Piper voice model (.onnx)."""
    default = REPO_DIR / "voices" / "en_US-amy-medium.onnx"
    return Path(_env("VOX_PIPER_VOICE", str(default)))


def voice_name() -> str:
    """Human-facing voice name: the voice file's basename without extension."""
    return piper_voice().stem


# --- STT (whisper.cpp) -----------------------------------------------------
def whisper_bin() -> str:
    """Name or path of the whisper.cpp executable."""
    return _env("VOX_WHISPER_BIN", "whisper-cli")


def whisper_model() -> Path:
    """Path to the whisper.cpp GGML model."""
    default = REPO_DIR / "models" / "ggml-base.en.bin"
    return Path(_env("VOX_WHISPER_MODEL", str(default)))


# --- Web layer (v2: optional live sources / holographic panels) -------------
# The web feature is the ONLY part of VOX that reaches the public internet, and
# it is entirely optional. ``VOX_WEB=0`` (or "false"/"no"/"off") disables it
# outright — search/fetch endpoints return 503 and /api/chat emits no panels.
_DEFAULT_FACE_BOX = [0.36, 0.05, 0.28, 0.17]


def web_enabled() -> bool:
    """Whether the optional web/sources feature is turned on (``VOX_WEB``).

    Actual internet *reachability* is a separate, best-effort check made in
    ``web.reachable()`` at request time — this flag is only the on/off switch and
    never touches the network, so it is safe to call anywhere (including startup).
    """
    return _env("VOX_WEB", "1").strip().lower() not in ("0", "false", "no", "off")


def face_box() -> list:
    """Normalized ``[x, y, w, h]`` head box within the (possibly full-body)
    portrait, from ``VOX_FACE_BOX``. Robust to malformed input: anything that
    isn't exactly four numbers falls back to the default, and every component is
    clamped to ``0..1``."""
    raw = _env("VOX_FACE_BOX", "0.36,0.05,0.28,0.17")
    try:
        parts = [float(p) for p in raw.replace(" ", "").split(",") if p != ""]
    except (ValueError, AttributeError):
        return list(_DEFAULT_FACE_BOX)
    if len(parts) != 4:
        return list(_DEFAULT_FACE_BOX)
    return [min(1.0, max(0.0, p)) for p in parts]


# --- Capability detection ---------------------------------------------------
def _resolvable(binary: str) -> bool:
    """True if ``binary`` is an existing file path or found on PATH."""
    if not binary:
        return False
    if os.path.sep in binary or (os.path.altsep and os.path.altsep in binary):
        return Path(binary).is_file()
    return shutil.which(binary) is not None


def tts_ready() -> bool:
    """TTS is available when the Piper binary resolves AND the voice file exists."""
    return _resolvable(piper_bin()) and piper_voice().is_file()


def stt_ready() -> bool:
    """STT is available when the whisper binary resolves AND the model exists."""
    return _resolvable(whisper_bin()) and whisper_model().is_file()


def find_portrait() -> Path | None:
    """Return the first present portrait asset, or None."""
    for name in PORTRAIT_CANDIDATES:
        candidate = ASSETS_DIR / name
        if candidate.is_file():
            return candidate
    return None


def portrait_present() -> bool:
    """True if the user has dropped a portrait into web/assets/."""
    return find_portrait() is not None


def portrait_url() -> str:
    """Public URL for the portrait (a present file's real name, else the .png
    default the frontend expects — the frontend falls back to a placeholder when
    ``portrait_present`` is False)."""
    found = find_portrait()
    if found is not None:
        return "/assets/" + found.name
    return "/assets/portrait.png"
