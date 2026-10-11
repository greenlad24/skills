"""Paths and user settings (stored outside the repo so updates never wipe them)."""

from __future__ import annotations

import json
import os
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PKG_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
FRAMEWORKS_DIR = PKG_DIR / "frameworks"
WEB_DIR = PKG_DIR / "web"

HOME = Path(os.environ.get("TTS_STUDIO_HOME", Path.home() / "ThaiTikTokStudio"))
PROJECTS_DIR = HOME / "projects"
SETTINGS_PATH = HOME / "settings.json"

DEFAULTS = {
    # "claude_code" = your Claude subscription via `claude setup-token` (default)
    # "claude" = Anthropic API key · "openai" = ChatGPT API key · "manual" = free copy/paste into a chat app
    "provider": "claude_code",
    "claude_code_token": "",
    "claude_code_path": "",
    "anthropic_api_key": "",
    "claude_model": "claude-opus-5-5",
    "claude_effort": "high",
    "openai_api_key": "",
    "openai_model": "gpt-5",
    "videos_per_product": 5,
    "onboarded": False,         # Thai welcome guide shown once
    "language": "th",           # UI language: "th" or "en" (the 🌐 switcher at the top of every screen)
    # Tool 3 — scheduler (PostPeer publishes to TikTok; Cloudinary hosts the final videos)
    "postpeer_key": "",
    "postpeer_account_id": "",
    "postpeer_account_name": "",
    "postpeer_mode": "inbox",   # "inbox" = TikTok inbox draft (add product basket, tap post) · "direct" = auto-publish
    "posts_per_day": 1,
    "cloudinary_url": "",
    "public_base_url": "",      # set automatically when hosted as a website
    # Editor
    "voice_source": "mine",     # "mine" = your recorded voice-over · "tts" = macOS Thai voice
    "tts_voice": "Kanya",       # macOS Thai voice (System Settings → Accessibility → Spoken Content)
    "tts_rate": 185,            # words-per-minute for `say`
    "smart_edit": True,         # Claude watches your clips and plans the cuts (built-in editor if off/unavailable)
    "subtitles": False,         # no subtitles — only the plan's animations
    "render_preset": "veryfast",
    "render_crf": 20,
    "music_volume": 0.14,
}


def ensure_dirs() -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    ensure_dirs()
    data = dict(DEFAULTS)
    if SETTINGS_PATH.exists():
        try:
            data.update(json.loads(SETTINGS_PATH.read_text("utf-8")))
        except (OSError, ValueError):
            pass
    # Environment variables win (handy for testing / power users).
    if os.environ.get("ANTHROPIC_API_KEY") and not data.get("anthropic_api_key"):
        data["anthropic_api_key"] = os.environ["ANTHROPIC_API_KEY"]
    if os.environ.get("OPENAI_API_KEY") and not data.get("openai_api_key"):
        data["openai_api_key"] = os.environ["OPENAI_API_KEY"]
    if os.environ.get("TTS_STUDIO_PUBLIC_URL"):          # hosted website: permanent video links
        data["public_base_url"] = os.environ["TTS_STUDIO_PUBLIC_URL"].rstrip("/")
    return data


def save_settings(update: dict) -> dict:
    data = load_settings()
    for k, v in update.items():
        if k in DEFAULTS:
            data[k] = v
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    try:
        os.chmod(SETTINGS_PATH, 0o600)  # API keys live here
    except OSError:
        pass
    return data


def public_settings(data: dict) -> dict:
    """Settings safe to send to the browser (keys masked)."""
    out = dict(data)
    for k in ("anthropic_api_key", "openai_api_key", "claude_code_token", "postpeer_key", "cloudinary_url"):
        v = out.get(k) or ""
        out[k] = ("•" * 8 + v[-4:]) if v else ""
    return out
