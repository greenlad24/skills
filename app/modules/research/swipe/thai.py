"""Thai word segmentation helper (§2B.2 step 5).

Thai has no spaces between words. The real path uses PyThaiNLP `word_tokenize(engine=
"newmm")`; when PyThaiNLP is absent (CI / DRY_RUN) a deterministic fallback tokenizer
splits on whitespace and Thai/non-Thai script boundaries. Downstream code treats the
returned token list as authoritative either way.
"""

from __future__ import annotations

import re

_THAI = re.compile(r"[฀-๿]+")
_NON_THAI_WORD = re.compile(r"[A-Za-z0-9]+")


def _fallback_tokenize(text: str) -> list[str]:
    """Whitespace + script-boundary split. Groups Thai runs and latin/number runs.

    Not linguistically perfect, but deterministic and dependency-free — enough for
    n-gram similarity, dedup, and prompt cleanliness in the stub path.
    """
    tokens: list[str] = []
    for chunk in text.split():
        pos = 0
        while pos < len(chunk):
            m_thai = _THAI.match(chunk, pos)
            m_other = _NON_THAI_WORD.match(chunk, pos)
            if m_thai:
                # Split long Thai runs into ~3-char pseudo-syllable tokens for stable
                # n-gram behavior without a dictionary.
                run = m_thai.group(0)
                tokens.extend(run[i : i + 3] for i in range(0, len(run), 3))
                pos = m_thai.end()
            elif m_other:
                tokens.append(m_other.group(0))
                pos = m_other.end()
            else:
                pos += 1  # skip punctuation/symbols
    return [t for t in tokens if t]


def word_tokenize(text: str) -> list[str]:
    if not text:
        return []
    try:  # real path
        from pythainlp.tokenize import word_tokenize as _wt  # type: ignore

        return [t for t in _wt(text, engine="newmm") if t.strip()]
    except Exception:  # noqa: BLE001 — dep absent → deterministic fallback
        return _fallback_tokenize(text)
