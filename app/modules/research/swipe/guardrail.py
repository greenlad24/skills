"""IP / legal guardrail (§2B.8), enforced in code.

Two independent protections:
  * `similarity_gate` — before a generated script is finalized (§03), check its Thai
    copy against the source `Transcript` corpus of the templates used. Any span with
    ≥ VERBATIM_NGRAM_N-gram overlap, or a sentence with cosine ≥ VERBATIM_MAX_COSINE, is
    flagged so the caller regenerates that span. Protects against copying COMPETITORS.
  * `is_self_duplicate` — reject a new script too similar (token Jaccard) to the
    operator's own last M scripts. Protects against SELF-duplication (TikTok suppresses
    unoriginal content). These are separate concerns.

Also `assert_template_clean` guards extraction output: a template must never contain a
full source sentence.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from math import sqrt

from .. import config
from .thai import word_tokenize


def _ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def ngram_overlap(a: str, b: str, n: int = config.VERBATIM_NGRAM_N) -> set[tuple[str, ...]]:
    """Return the set of shared n-grams between two texts (Thai-tokenized)."""
    return _ngrams(word_tokenize(a), n) & _ngrams(word_tokenize(b), n)


def _cosine(a: str, b: str) -> float:
    ta, tb = word_tokenize(a), word_tokenize(b)
    if not ta or not tb:
        return 0.0
    ca, cb = Counter(ta), Counter(tb)
    dot = sum(ca[t] * cb[t] for t in ca.keys() & cb.keys())
    na = sqrt(sum(v * v for v in ca.values()))
    nb = sqrt(sum(v * v for v in cb.values()))
    return dot / (na * nb) if na and nb else 0.0


def jaccard(a: str, b: str) -> float:
    sa, sb = set(word_tokenize(a)), set(word_tokenize(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


@dataclass
class GateResult:
    passed: bool
    offending_spans: list[str] = field(default_factory=list)
    max_cosine: float = 0.0
    details: dict = field(default_factory=dict)


def _split_sentences(text: str) -> list[str]:
    # Thai UGC rarely uses full stops; split on newlines and common separators.
    parts: list[str] = []
    for chunk in text.replace("।", "\n").splitlines():
        for sub in chunk.split("  "):
            s = sub.strip()
            if s:
                parts.append(s)
    return parts or ([text.strip()] if text.strip() else [])


def similarity_gate(
    generated: str,
    source_corpus: list[str],
    *,
    n: int = config.VERBATIM_NGRAM_N,
    max_cosine: float = config.VERBATIM_MAX_COSINE,
) -> GateResult:
    """Flag near-verbatim reuse of any source transcript. `passed=False` ⇒ regenerate the
    offending spans (§03 must not finalize until this passes)."""
    offending: list[str] = []
    worst_cos = 0.0
    gen_sentences = _split_sentences(generated)

    for src in source_corpus:
        # n-gram verbatim overlap anywhere in the generated copy
        if ngram_overlap(generated, src, n):
            for sent in gen_sentences:
                if ngram_overlap(sent, src, n) and sent not in offending:
                    offending.append(sent)
        # sentence-level cosine
        for sent in gen_sentences:
            c = _cosine(sent, src)
            worst_cos = max(worst_cos, c)
            if c >= max_cosine and sent not in offending:
                offending.append(sent)

    return GateResult(
        passed=not offending,
        offending_spans=offending,
        max_cosine=round(worst_cos, 4),
        details={"n": n, "max_cosine_threshold": max_cosine, "sources": len(source_corpus)},
    )


def is_self_duplicate(
    new_script: str,
    recent_scripts: list[str],
    *,
    threshold: float = config.SELF_DUP_JACCARD_MAX,
    window: int = config.SELF_DUP_HISTORY,
) -> bool:
    """True if the new script is too similar (token Jaccard) to the operator's last M."""
    for prev in recent_scripts[-window:]:
        if jaccard(new_script, prev) >= threshold:
            return True
    return False


def assert_template_clean(template_texts: list[str], source_corpus: list[str], *, n: int = config.VERBATIM_NGRAM_N) -> list[str]:
    """Return any template strings that reproduce a source span (should be empty).

    Used to assert extraction output stores abstracted patterns, not copied sentences.
    """
    dirty: list[str] = []
    for t in template_texts:
        for src in source_corpus:
            if ngram_overlap(t, src, n):
                dirty.append(t)
                break
    return dirty
