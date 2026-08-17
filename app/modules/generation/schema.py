"""Script JSON schema (§3A.4) + validation.

The schema is the one from the spec verbatim (structure + the ``if/then`` blocks
that encode the load-bearing hybrid rule at the schema level). Because
``jsonschema`` is an optional dependency, ``validate_script`` runs a deterministic
built-in validator that enforces every load-bearing rule and, when ``jsonschema``
*is* installed, additionally runs the formal draft-2020-12 validation.

Load-bearing rules enforced here (§3A.2, §3A.4, §3B):
  * AVATAR scene => role in {HOOK, CTA}; BROLL scene => role in {DEMO, PROOF}.
  * ``visual_prompt_en`` contains no Thai; ``thai_narration`` /
    ``on_screen_text_th`` contain no Latin marketing copy.
  * total_duration_s / per-scene bounds; enum membership; required keys.
"""

from __future__ import annotations

import re
from typing import Any

from app.modules.generation.constants import (
    ALLOWED_ROLES_FOR_ASSET,
    ASSET_TYPES,
    MAX_TOTAL_DURATION_S,
    MIN_TOTAL_DURATION_S,
    SCENE_ROLES,
)

# --------------------------------------------------------------------------- #
# The schema (spec §3A.4, verbatim structure)
# --------------------------------------------------------------------------- #
SCRIPT_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "autougc.th/script.schema.json",
    "title": "Script",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "script_id",
        "video_job_id",
        "language",
        "total_duration_s",
        "scenes",
        "claim_audit",
    ],
    "properties": {
        "script_id": {"type": "string"},
        "video_job_id": {"type": "string"},
        "language": {"const": "th"},
        "formula_template_id": {"type": "string"},
        "hook_template_id": {"type": "string"},
        "total_duration_s": {
            "type": "number",
            "minimum": MIN_TOTAL_DURATION_S,
            "maximum": MAX_TOTAL_DURATION_S,
        },
        "scenes": {
            "type": "array",
            "minItems": 2,
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "scene_id",
                    "order",
                    "role",
                    "thai_narration",
                    "visual_prompt_en",
                    "on_screen_text_th",
                    "duration_s",
                    "asset_type",
                ],
                "properties": {
                    "scene_id": {"type": "string"},
                    "order": {"type": "integer", "minimum": 0},
                    "role": {"enum": ["HOOK", "DEMO", "PROOF", "CTA"]},
                    "thai_narration": {"type": "string", "minLength": 0, "maxLength": 180},
                    "visual_prompt_en": {"type": "string", "minLength": 10, "maxLength": 900},
                    "on_screen_text_th": {"type": "string", "maxLength": 80},
                    "duration_s": {"type": "number", "minimum": 1.5, "maximum": 15},
                    "asset_type": {"enum": ["AVATAR", "BROLL"]},
                    "product_focus": {"type": "boolean", "default": False},
                },
                "allOf": [
                    {
                        "if": {"properties": {"asset_type": {"const": "AVATAR"}}},
                        "then": {"properties": {"role": {"enum": ["HOOK", "CTA"]}}},
                    },
                    {
                        "if": {"properties": {"asset_type": {"const": "BROLL"}}},
                        "then": {"properties": {"role": {"enum": ["DEMO", "PROOF"]}}},
                    },
                ],
            },
        },
        "claim_audit": {
            "type": "object",
            "additionalProperties": False,
            "required": ["passed", "checked_at", "findings"],
            "properties": {
                "passed": {"type": "boolean"},
                "checked_at": {"type": "string"},
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["scene_id", "span", "category", "verdict"],
                        "properties": {
                            "scene_id": {"type": "string"},
                            "span": {"type": "string"},
                            "category": {
                                "enum": [
                                    "EFFICACY",
                                    "HEALTH",
                                    "WHITENING",
                                    "FIRST_PERSON_EXPERIENCE",
                                    "SUPERLATIVE",
                                    "OK",
                                ]
                            },
                            "verdict": {"enum": ["ALLOW", "BLOCK", "REWRITE"]},
                        },
                    },
                },
            },
        },
    },
}

# Thai unicode block.
_THAI_RE = re.compile(r"[฀-๿]")
# A "Latin word" = a run of >= 4 ASCII letters (allows unit tokens like "ml", "30ml").
_LATIN_WORD_RE = re.compile(r"[A-Za-z]{4,}")


def contains_thai(text: str) -> bool:
    return bool(_THAI_RE.search(text or ""))


def has_latin_marketing_copy(text: str) -> bool:
    """True if a Thai field carries a Latin marketing word (>=4 letters)."""
    return bool(_LATIN_WORD_RE.search(text or ""))


class ScriptValidationError(Exception):
    """Raised (or collected) when a script violates §3A.4 / the hybrid rule."""


def validate_script(script: dict[str, Any]) -> list[str]:
    """Return a list of validation error strings (empty list == valid).

    Enforces every load-bearing rule deterministically; if ``jsonschema`` is
    installed it *also* runs the formal schema and appends any structural errors.
    """
    errors: list[str] = []

    # --- top-level required keys ---
    for key in SCRIPT_JSON_SCHEMA["required"]:
        if key not in script:
            errors.append(f"missing required key: {key!r}")
    if script.get("language") != "th":
        errors.append("language must be 'th'")

    total = script.get("total_duration_s")
    if not isinstance(total, (int, float)) or not (
        MIN_TOTAL_DURATION_S <= total <= MAX_TOTAL_DURATION_S
    ):
        errors.append(
            f"total_duration_s must be a number in "
            f"[{MIN_TOTAL_DURATION_S}, {MAX_TOTAL_DURATION_S}]"
        )

    scenes = script.get("scenes")
    if not isinstance(scenes, list) or not (2 <= len(scenes) <= 8):
        errors.append("scenes must be an array of 2..8 items")
        scenes = scenes if isinstance(scenes, list) else []

    orders_seen: set[int] = set()
    for i, scene in enumerate(scenes):
        where = f"scenes[{i}]"
        if not isinstance(scene, dict):
            errors.append(f"{where}: not an object")
            continue
        required = [
            "scene_id",
            "order",
            "role",
            "thai_narration",
            "visual_prompt_en",
            "on_screen_text_th",
            "duration_s",
            "asset_type",
        ]
        for key in required:
            if key not in scene:
                errors.append(f"{where}: missing {key!r}")

        role = scene.get("role")
        asset_type = scene.get("asset_type")
        if role not in SCENE_ROLES:
            errors.append(f"{where}: role {role!r} not in {sorted(SCENE_ROLES)}")
        if asset_type not in ASSET_TYPES:
            errors.append(f"{where}: asset_type {asset_type!r} not in {sorted(ASSET_TYPES)}")

        # THE load-bearing hybrid rule (§3B / decision #3):
        if asset_type in ALLOWED_ROLES_FOR_ASSET and role not in ALLOWED_ROLES_FOR_ASSET[asset_type]:
            errors.append(
                f"{where}: hybrid-rule violation — {asset_type} scene cannot carry "
                f"role {role!r} (allowed: {sorted(ALLOWED_ROLES_FOR_ASSET[asset_type])})"
            )

        order = scene.get("order")
        if not isinstance(order, int) or order < 0:
            errors.append(f"{where}: order must be a non-negative integer")
        elif order in orders_seen:
            errors.append(f"{where}: duplicate order {order}")
        else:
            orders_seen.add(order)

        dur = scene.get("duration_s")
        if not isinstance(dur, (int, float)) or not (1.5 <= dur <= 15):
            errors.append(f"{where}: duration_s must be a number in [1.5, 15]")

        # Two-language rule (§3A.2) — enforced, not left to the LLM.
        vpe = scene.get("visual_prompt_en", "")
        if not isinstance(vpe, str) or len(vpe) < 10:
            errors.append(f"{where}: visual_prompt_en must be a string >= 10 chars")
        elif contains_thai(vpe):
            errors.append(f"{where}: visual_prompt_en must be English-only (found Thai)")

        for field in ("thai_narration", "on_screen_text_th"):
            val = scene.get(field, "")
            if has_latin_marketing_copy(val):
                errors.append(f"{where}: {field} must not contain Latin marketing copy")

    # --- claim_audit shape ---
    ca = script.get("claim_audit")
    if not isinstance(ca, dict):
        errors.append("claim_audit must be an object")
    else:
        for key in ("passed", "checked_at", "findings"):
            if key not in ca:
                errors.append(f"claim_audit: missing {key!r}")
        if not isinstance(ca.get("findings", []), list):
            errors.append("claim_audit.findings must be an array")

    # --- optional formal jsonschema pass (defence in depth) ---
    try:  # pragma: no cover - only when jsonschema installed
        import jsonschema  # type: ignore

        validator = jsonschema.Draft202012Validator(SCRIPT_JSON_SCHEMA)
        for err in validator.iter_errors(script):
            errors.append(f"jsonschema: {err.message}")
    except ImportError:
        pass

    # De-duplicate while preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            deduped.append(e)
    return deduped
