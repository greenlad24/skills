"""Read/upsert the app's `.env` and reflect changes into the live settings object.

The onboarding wizard writes secrets here. Two effects per save:
  1. Persist to `.env` (so a restart keeps the value) — upsert, preserving comments
     and any keys we don't manage.
  2. Update `os.environ` + the cached `settings` singleton in-process, so a provider
     "Test" right after saving sees the new value WITHOUT a restart.

Only a whitelisted set of keys may be written (no arbitrary env injection).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from app.core.config import settings

# Keys the wizard is allowed to write. Anything else is ignored.
ALLOWED_KEYS: frozenset[str] = frozenset({
    # LLM
    "LLM_PROVIDER", "ANTHROPIC_API_KEY",
    # Thai TTS (Google)
    "TTS_PROVIDER", "GOOGLE_TTS_API_KEY", "GOOGLE_TTS_VOICE", "GOOGLE_TTS_LANGUAGE",
    # Video (LTX-2.5 on Modal)
    "VIDEOGEN_PROVIDER", "MODAL_LTX_URL", "MODAL_LTX_TOKEN", "LTX_FPS",
    # TikTok posting
    "POSTING_PROVIDER", "TIKTOK_ACCESS_TOKEN", "TIKTOK_POSTING_MODE", "TIKTOK_PRIVACY_LEVEL",
    # Research scraping (optional)
    "SCRAPER_PROVIDER", "APIFY_API_KEY", "FIRECRAWL_API_KEY",
    # Run mode / markers
    "DRY_RUN", "ONBOARDED",
})

_LINE_RE = re.compile(r"^\s*([A-Z0-9_]+)\s*=")


def env_path() -> Path:
    """Path to the .env we manage (override with AUTOUGC_ENV_FILE for tests)."""
    return Path(os.environ.get("AUTOUGC_ENV_FILE", ".env"))


def _coerce(current: object, value: str) -> object:
    """Coerce a string to match the type of the existing settings field."""
    if isinstance(current, bool):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(current, int):
        try:
            return int(value)
        except ValueError:
            return current
    if isinstance(current, float):
        try:
            return float(value)
        except ValueError:
            return current
    return value


def apply_live(updates: dict[str, str]) -> None:
    """Reflect updates into os.environ and the cached settings singleton."""
    for key, value in updates.items():
        os.environ[key] = value
        if hasattr(settings, key):
            setattr(settings, key, _coerce(getattr(settings, key), value))


def upsert_env(updates: dict[str, str]) -> None:
    """Write updates into `.env`, replacing existing keys and appending new ones."""
    path = env_path()
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    out: list[str] = []
    for line in existing:
        m = _LINE_RE.match(line)
        if m and m.group(1) in updates:
            key = m.group(1)
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def save(values: dict[str, str]) -> dict[str, list[str]]:
    """Persist + apply whitelisted keys. Returns which were saved vs. ignored."""
    # Strip CR/LF so a pasted multi-line value can't corrupt the .env format.
    updates = {
        k: str(v).replace("\r", "").replace("\n", "").strip()
        for k, v in values.items() if k in ALLOWED_KEYS
    }
    ignored = [k for k in values if k not in ALLOWED_KEYS]
    if updates:
        upsert_env(updates)
        apply_live(updates)
    return {"saved": sorted(updates), "ignored": sorted(ignored)}
