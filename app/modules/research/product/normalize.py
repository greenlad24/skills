"""Tier / category / voice_gender derivation (§2A.5 / §2A.6).

Deterministic, fixture-stable heuristics with a cheap-LLM fallback for category only.
All functions are pure (no I/O) except `classify_category`, which may call the LLM
provider via the registry when the keyword fast-path misses.
"""

from __future__ import annotations

from typing import Any

from .. import config
from ..schemas import NormalizedProduct

# --------------------------------------------------------------------------- #
# Category
# --------------------------------------------------------------------------- #
def category_fast_path(title: str | None, bullets: list[str], breadcrumb: str | None) -> str | None:
    """Keyword-map fast path — avoids an LLM call when the platform text is obvious."""
    hay = " ".join(
        [title or "", " ".join(bullets or []), breadcrumb or ""]
    ).lower()
    for kw, cat in config.CATEGORY_KEYWORDS.items():
        if kw.lower() in hay:
            return cat
    return None


def classify_category(
    title: str | None,
    bullets: list[str],
    breadcrumb: str | None = None,
    *,
    llm=None,
    idempotency_key: str = "research:category",
) -> str:
    """Return a dotted category from the fixed taxonomy.

    Tries the keyword fast-path first; on a miss, a cheap constrained LLM classification.
    In DRY_RUN the fake LLM won't emit a valid enum, so we fall back to 'misc' — still
    deterministic and schema-valid.
    """
    hit = category_fast_path(title, bullets, breadcrumb)
    if hit:
        return hit

    try:
        if llm is None:
            from app.core.adapters import registry

            llm = registry.get_llm_provider()
        enum_str = ", ".join(config.CATEGORY_TAXONOMY)
        prompt = (
            "Classify this product into EXACTLY ONE category from the list.\n"
            f"Categories: {enum_str}\n"
            f"Title: {title}\nBullets: {bullets}\nBreadcrumb: {breadcrumb}\n"
            "Answer with only the category string."
        )
        res = llm.complete(
            prompt=prompt,
            system="You are a strict product taxonomy classifier.",
            model=config.LLM_CLASSIFY_MODEL,
            max_tokens=16,
            idempotency_key=idempotency_key,
        )
        text = (res.data or {}).get("text", "") if res and res.ok else ""
        for cat in config.CATEGORY_TAXONOMY:
            if cat in text:
                return cat
    except Exception:  # noqa: BLE001 — never let classification hard-fail research
        pass
    return "misc"


# --------------------------------------------------------------------------- #
# Tier
# --------------------------------------------------------------------------- #
def derive_tier(
    price: float | None,
    category: str | None,
    title: str | None = None,
    bullets: list[str] | None = None,
) -> tuple[str, str]:
    """Return (tier, price_band_used). Price bucketed *within category*, nudged by cues.

    price_band_used records the (budget_max, mid_max) band applied, for auditability.
    """
    band = config.TIER_PRICE_BANDS_THB.get(category or "", config.TIER_BAND_DEFAULT)
    budget_max, mid_max = band
    band_label = f"{category or 'default'}:{budget_max}/{mid_max}"

    if price is None:
        base = "mid"  # unknown price → neutral middle
    elif price <= budget_max:
        base = "budget"
    elif price <= mid_max:
        base = "mid"
    else:
        base = "premium"

    hay = " ".join([title or "", " ".join(bullets or [])]).lower()
    order = ["budget", "mid", "premium"]
    idx = order.index(base)
    if any(cue.lower() in hay for cue in config.TIER_CUES_UP):
        idx = min(idx + 1, 2)
    if any(cue.lower() in hay for cue in config.TIER_CUES_DOWN):
        idx = max(idx - 1, 0)
    return order[idx], band_label


# --------------------------------------------------------------------------- #
# voice_gender (§2A.6 heuristic cascade, first hit wins)
# --------------------------------------------------------------------------- #
def derive_voice_gender(
    title: str | None,
    bullets: list[str] | None,
    attributes: dict[str, Any] | None,
    category: str | None,
    swipe_gender_evidence: dict[str, int] | None = None,
) -> tuple[str, float]:
    """Return (voice_gender, confidence). Suggestion only — human gate may override.

    Cascade: (1) explicit gender-target cue, (2) category prior, (3) swipe-library
    creator-gender evidence overrides the prior when confident, (4) neutral fallback.
    """
    hay = " ".join(
        [title or "", " ".join(bullets or []), " ".join(str(v) for v in (attributes or {}).values())]
    ).lower()

    # 1. Explicit target.
    if any(cue.lower() in hay for cue in config.GENDER_CUES_MALE):
        return "male", 0.9
    if any(cue.lower() in hay for cue in config.GENDER_CUES_FEMALE):
        return "female", 0.9

    prior = config.CATEGORY_GENDER_PRIOR.get(category or "", "neutral")

    # 3. Swipe evidence can OVERRIDE the soft prior when confident.
    if swipe_gender_evidence:
        total = sum(swipe_gender_evidence.values())
        if total >= 3:
            dominant = max(swipe_gender_evidence, key=lambda k: swipe_gender_evidence[k])
            frac = swipe_gender_evidence[dominant] / total
            if frac >= 0.6 and dominant in ("female", "male"):
                return dominant, round(0.6 + 0.4 * frac, 3)

    # 2. Category prior (soft).
    if prior in ("female", "male"):
        return prior, 0.55
    return "neutral", 0.4


# --------------------------------------------------------------------------- #
# Sparsity gate (§2A.7)
# --------------------------------------------------------------------------- #
def too_sparse(norm: NormalizedProduct) -> bool:
    """True ⇔ no title OR no usable image (post-download). Text-only or image-only
    both trigger a targeted manual top-up rather than a full restart."""
    if not (norm.title and norm.title.strip()):
        return True
    if not norm.images:
        return True
    return False


def enrich(
    norm: NormalizedProduct,
    *,
    swipe_gender_evidence: dict[str, int] | None = None,
    llm=None,
) -> NormalizedProduct:
    """Fill category / tier / voice_gender on an otherwise-populated NormalizedProduct."""
    if not norm.category:
        norm.category = classify_category(norm.title, norm.bullets, llm=llm)
    tier, band = derive_tier(norm.price, norm.category, norm.title, norm.bullets)
    norm.tier = tier
    norm.price_band_used = band
    vg, conf = derive_voice_gender(
        norm.title, norm.bullets, norm.attributes, norm.category, swipe_gender_evidence
    )
    norm.voice_gender = vg
    norm.voice_gender_confidence = conf
    return norm
