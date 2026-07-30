"""4B — Thai text discipline: word segmentation, ZWSP break hints, combining-mark guards.

Thai has NO spaces between words: you cannot split on whitespace, and a naive boundary
can land between a base char and its combining tone/vowel mark. This module is pure
(PyThaiNLP is imported lazily and degrades to a no-split fallback) so the guards are
unit-testable with zero heavy deps.
"""

from __future__ import annotations

ZWSP = "​"  # U+200B ZERO WIDTH SPACE — where libass may line-break

# Combining code points that must NEVER start a word/line (§4B.3):
#   U+0E31 (mai han-akat), U+0E34–U+0E3A (upper/lower vowels + phinthu),
#   U+0E47–U+0E4E (tone marks + thanthakhat + nikhahit family).
COMBINING: set[int] = set(range(0x0E34, 0x0E3B)) | {0x0E31} | set(range(0x0E47, 0x0E4F))

# Tone marks specifically (verification target, §4B.5 / T-3).
TONE_MARKS: set[int] = set(range(0x0E48, 0x0E4C))


def _newmm(text: str, custom_dict=None) -> list[str]:
    """PyThaiNLP ``newmm`` word tokenizer; falls back to a single token if absent.

    ``custom_dict`` is an optional PyThaiNLP ``Trie`` of brand/product terms so OOV
    names are not split mid-word (§4B.3 OOV guard).
    """
    try:
        from pythainlp.tokenize import word_tokenize  # lazy heavy dep

        return word_tokenize(
            text, engine="newmm", keep_whitespace=False, custom_dict=custom_dict
        )
    except Exception:  # noqa: BLE001 — no PyThaiNLP: don't split (safe, never mid-word)
        return [text] if text else []


def thai_words(text: str, custom_dict=None) -> list[str]:
    """Tokenize Thai text into words, then merge any boundary that would orphan a
    combining mark (tone/vowel) onto the *previous* word."""
    words = _newmm(text, custom_dict)
    return _merge_orphan_marks(words)


def _merge_orphan_marks(words: list[str]) -> list[str]:
    """If a token begins with a combining code point, glue it to the previous token."""
    out: list[str] = []
    for w in words:
        if out and w and ord(w[0]) in COMBINING:
            out[-1] = out[-1] + w
        else:
            out.append(w)
    return out


def with_break_hints(text: str, custom_dict=None) -> str:
    """Insert ZWSP at PyThaiNLP word boundaries so libass wraps between words (§4B.5)."""
    return ZWSP.join(thai_words(text, custom_dict))


def safe_boundaries(text: str, cuts: list[int]) -> list[int]:
    """Drop any character-offset boundary that falls immediately before a combining
    code point (§4B.3) — such a cut would split a base char from its mark."""
    return [c for c in cuts if not (0 <= c < len(text) and ord(text[c]) in COMBINING)]


def build_brand_trie(terms: list[str]):
    """Build a PyThaiNLP ``Trie`` custom dictionary from Script-module brand terms.

    Returns ``None`` if PyThaiNLP is unavailable (callers treat that as "no custom dict").
    """
    if not terms:
        return None
    try:
        from pythainlp.util import Trie  # lazy

        return Trie(terms)
    except Exception:  # noqa: BLE001
        return None


def has_orphan_mark_break(text_with_zwsp: str) -> bool:
    """QA (T-5): True if any ZWSP is immediately followed by a combining mark."""
    for i, ch in enumerate(text_with_zwsp):
        if ch == ZWSP and i + 1 < len(text_with_zwsp):
            if ord(text_with_zwsp[i + 1]) in COMBINING:
                return True
    return False
