"""UI strings for the server-rendered pages (login, phone upload).

They come from the same dictionaries as the web app (studio/web/lang/<lang>.json),
so there is one place to translate. Only UI chrome is translated, never user content.
"""

from __future__ import annotations

import json
from functools import lru_cache

from . import config

LANGS = ("th", "en")


@lru_cache(maxsize=None)
def _dict(lang: str) -> dict:
    return json.loads((config.WEB_DIR / "lang" / f"{lang}.json").read_text("utf-8"))


def texts(lang: str, prefix: str = "") -> dict:
    """All strings for `lang` whose key starts with `prefix` (prefix removed)."""
    d = _dict(lang if lang in LANGS else "th")
    return {k[len(prefix):]: v for k, v in d.items() if k.startswith(prefix)}


def pick_lang(*candidates) -> str:
    """First supported language among the candidates (query param, cookie, setting…), else Thai."""
    for c in candidates:
        if c in LANGS:
            return c
    return "th"
