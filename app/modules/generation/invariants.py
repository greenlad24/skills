"""Global-invariant pinning (§3A.3).

Every ``visual_prompt_en`` is composed *in code* (never left to the LLM) so the
same product/set/style description reaches every scene's image + video model —
the single biggest lever on cross-scene product consistency. The LLM emits only
the scene-specific ACTION clause; we concatenate the pinned invariants around it.
"""

from __future__ import annotations

from typing import Any

DEFAULT_INVARIANTS: dict[str, str] = {
    "product_desc_en": "the product, shown clearly with its label and branding intact",
    "set_desc_en": "a clean, softly-lit tabletop set",
    "style_en": "authentic UGC iPhone look, shallow depth of field, 9:16 vertical",
}


def normalize_invariants(raw: dict[str, Any] | None) -> dict[str, str]:
    """Fill any missing invariant with a safe default so pinning always succeeds."""
    raw = raw or {}
    return {
        "product_desc_en": str(raw.get("product_desc_en") or DEFAULT_INVARIANTS["product_desc_en"]).strip(),
        "set_desc_en": str(raw.get("set_desc_en") or DEFAULT_INVARIANTS["set_desc_en"]).strip(),
        "style_en": str(raw.get("style_en") or DEFAULT_INVARIANTS["style_en"]).strip(),
    }


def compose_visual_prompt(invariants: dict[str, str], action_clause_en: str) -> str:
    """Compose the pinned ``visual_prompt_en`` (§3A.3 exact template).

    ``{product_desc_en}. {action}. Setting: {set_desc_en}. Style: {style_en}.``
    """
    inv = normalize_invariants(invariants)
    action = (action_clause_en or "product presented naturally").strip().rstrip(".")
    return (
        f"{inv['product_desc_en']}. {action}. "
        f"Setting: {inv['set_desc_en']}. Style: {inv['style_en']}."
    )


def compose_hero_prompt(invariants: dict[str, str], hero_action_en: str) -> str:
    """Compose the locked hero-image prompt (§3D.2)."""
    inv = normalize_invariants(invariants)
    action = (hero_action_en or "product hero, bottle standing").strip().rstrip(".")
    return (
        f"{inv['product_desc_en']}. Product hero on {inv['set_desc_en']}. "
        f"{action}. Style: {inv['style_en']}. "
        f"Preserve label text, color, and proportions exactly."
    )


def invariants_present(visual_prompt_en: str, invariants: dict[str, str]) -> bool:
    """True iff every invariant appears verbatim in the composed prompt (§3D.11 test)."""
    inv = normalize_invariants(invariants)
    return all(part in (visual_prompt_en or "") for part in inv.values())
