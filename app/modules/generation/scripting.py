"""Claim-safe Thai scripting (§3A).

Produces a STRUCTURED, schema-valid bilingual script: Thai narration/on-screen
text + English visual prompts, with global invariants pinned in code (§3A.3) and
the hybrid role map enforced (§3B). The claim-safety gate (§3A.6) runs *after*
the script is emitted and *before* it can be marked approved-for-gen.

LLM strategy (§3A.5): the primary path is a single tool-call (``emit_script``)
to Claude whose ``input_schema`` is the §3A.4 schema. When the provider returns
schema-valid JSON we use it; otherwise (e.g. the DRY_RUN fake, which returns free
text) we fall back to a deterministic, claim-safe synthesiser built from product
*attributes* + verbatim ``approved_claims`` only — which is inherently safe.

The system prompt (layer-1 prevention) is assembled from the spec template so it
is exercised in real mode; the deterministic fallback keeps DRY_RUN free and
tests hermetic.
"""

from __future__ import annotations

import json
import math
import uuid
from typing import Any

from app.core.adapters import registry
from app.core.adapters.base import ProviderResult
from app.modules.generation import claim_gate
from app.modules.generation.constants import (
    ASSET_FOR_ROLE,
    DEFAULT_LLM_MODEL,
    MAX_TOTAL_DURATION_S,
    MIN_TOTAL_DURATION_S,
    ROLE_CTA,
    ROLE_DEMO,
    ROLE_HOOK,
    ROLE_PROOF,
)
from app.modules.generation.invariants import (
    compose_visual_prompt,
    normalize_invariants,
)
from app.modules.generation.schema import validate_script

# A safe default four-beat plan when no FormulaTemplate is supplied.
DEFAULT_SCENE_PLAN: list[dict[str, Any]] = [
    {"role": ROLE_HOOK, "target_s": 3, "asset_type": ASSET_FOR_ROLE[ROLE_HOOK]},
    {"role": ROLE_DEMO, "target_s": 8, "asset_type": ASSET_FOR_ROLE[ROLE_DEMO]},
    {"role": ROLE_PROOF, "target_s": 6, "asset_type": ASSET_FOR_ROLE[ROLE_PROOF]},
    {"role": ROLE_CTA, "target_s": 4, "asset_type": ASSET_FOR_ROLE[ROLE_CTA]},
]

# Deterministic, claim-safe Thai narration templates by role. They reference only
# describable product facts (attributes) — never efficacy/health/whitening/etc.
_ROLE_NARRATION_TH: dict[str, str] = {
    ROLE_HOOK: "{hook} มาดูตัวนี้กันนะ",
    ROLE_DEMO: "เนื้อสัมผัสดูดีมากเลยอ่ะ {fact}",
    ROLE_PROOF: "รายละเอียดชัด ๆ ให้ดูเลย {fact}",
    ROLE_CTA: "ถ้าสนใจกดตะกร้าเลยนะ",
}
_ROLE_ONSCREEN_TH: dict[str, str] = {
    ROLE_HOOK: "{hook}",
    ROLE_DEMO: "{fact}",
    ROLE_PROOF: "{fact}",
    ROLE_CTA: "กดตะกร้า",
}
# English action clauses (the LLM emits only this; invariants get pinned around it).
_ROLE_ACTION_EN: dict[str, str] = {
    ROLE_HOOK: "creator talking to camera, chest-up framing, warm and friendly",
    ROLE_DEMO: "slow product rotation, texture and applicator in focus, single hero unit",
    ROLE_PROOF: "macro detail of the product label and finish, clean product-only frame",
    ROLE_CTA: "creator talking to camera, chest-up framing, inviting gesture",
}


def build_script_input(
    *,
    product: dict[str, Any],
    formula_template: dict[str, Any] | None = None,
    hook_template: dict[str, Any] | None = None,
    operator_flags: dict[str, Any] | None = None,
    global_invariants: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the §3A.1 scripting input with safe defaults."""
    formula_template = formula_template or {}
    scene_plan = formula_template.get("scene_plan") or DEFAULT_SCENE_PLAN
    return {
        "product": product or {},
        "formula_template": {
            "id": formula_template.get("id"),
            "scene_plan": scene_plan,
        },
        "hook_template": hook_template or {"id": None, "pattern_th": "POV: เธอเพิ่งเจอ"},
        "operator_flags": operator_flags
        or {"operator_verified_experience": False, "register": "tiktok_casual"},
        "global_invariants": normalize_invariants(global_invariants),
    }


def build_system_prompt(script_input: dict[str, Any]) -> str:
    """Assemble the §3A.6 system prompt (layer-1 claim prevention)."""
    product = script_input["product"]
    attributes = product.get("attributes", []) or []
    approved = product.get("approved_claims", []) or []
    flags = script_input["operator_flags"]
    plan = script_input["formula_template"]["scene_plan"]
    hook = script_input["hook_template"]
    return (
        "You are a Thai UGC short-video scriptwriter for TikTok Shop.\n"
        "OUTPUT: call the tool `emit_script` with schema-valid JSON. Never write prose.\n\n"
        "LANGUAGE RULES (hard):\n"
        "- thai_narration + on_screen_text_th: natural, colloquial spoken Thai "
        f"(register: {flags.get('register', 'tiktok_casual')}). Short un-rushed sentences.\n"
        "- visual_prompt_en: ENGLISH ONLY, scene-specific ACTION clause only.\n\n"
        "STRUCTURE (from formula_template):\n"
        f"{json.dumps(plan, ensure_ascii=False)}\n"
        "- AVATAR scenes = HOOK or CTA only, talking head, NO product in hand.\n"
        "- BROLL scenes  = DEMO or PROOF only, product-focused, no avatar.\n\n"
        "DURATION (hard):\n"
        f"- total_duration_s (sum of every scene duration_s) MUST be between "
        f"{MIN_TOTAL_DURATION_S} and {MAX_TOTAL_DURATION_S} seconds — never longer "
        f"than {MAX_TOTAL_DURATION_S}s. Write narration short enough to fit.\n\n"
        "CLAIM RULES (hard — you will be audited and rejected):\n"
        f"- Use ONLY these product attributes: {json.dumps(attributes, ensure_ascii=False)}\n"
        f"- Use ONLY these approved claims verbatim: {json.dumps(approved, ensure_ascii=False)}\n"
        "- FORBIDDEN unless explicitly permitted: efficacy, health, whitening, "
        "superlatives, first-person experience.\n"
        f"- operator_verified_experience = {flags.get('operator_verified_experience', False)}\n"
        f"Hook to open with: {hook.get('pattern_th', '')}\n"
    )


def _thai_safe(text: str) -> str:
    """Strip Latin marketing words (>=4 letters) so a fact is safe in a Thai field.

    Short unit tokens ("30ml", "ml") survive; English marketing words are removed.
    """
    import re

    cleaned = re.sub(r"[A-Za-z]{4,}", "", text or "")
    return " ".join(cleaned.split()).strip()


def _fact_phrases(product: dict[str, Any]) -> list[str]:
    """Claim-safe, Thai-field-safe describable facts (attributes + approved claims).

    Attributes are describable product facts (allowed by §3A.6). English attribute
    values are sanitized so they never inject Latin marketing copy into Thai
    narration/on-screen text (the two-language rule, §3A.2).
    """
    raw: list[str] = []
    for attr in product.get("attributes", []) or []:
        if isinstance(attr, dict):
            val = str(attr.get("value", "")).strip()
            if val:
                raw.append(val)
        elif attr:
            raw.append(str(attr))
    for claim in product.get("approved_claims", []) or []:
        if claim:
            raw.append(str(claim))

    facts: list[str] = []
    for f in raw:
        safe = _thai_safe(f)
        # Keep only facts that carry Thai text or a numeric/unit token (no bare Latin).
        if safe and any(ch >= "฀" and ch <= "๿" for ch in safe):
            facts.append(safe)
        elif safe and any(ch.isdigit() for ch in safe):
            facts.append(safe)
    return facts or ["ดีไซน์สวยงาม"]


def _synthesize_script(
    *,
    video_job_id: str,
    script_input: dict[str, Any],
    forced_narration: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Deterministic, claim-safe structured script from the plan + product facts.

    ``forced_narration`` (keyed by scene order as str) lets tests/negative-retry
    inject specific narration to exercise the claim gate.
    """
    product = script_input["product"]
    invariants = script_input["global_invariants"]
    hook = script_input["hook_template"].get("pattern_th", "มาดูกันนะ")
    facts = _fact_phrases(product)
    forced_narration = forced_narration or {}

    scenes: list[dict[str, Any]] = []
    total = 0.0
    for i, beat in enumerate(script_input["formula_template"]["scene_plan"]):
        role = beat["role"]
        asset_type = beat.get("asset_type") or ASSET_FOR_ROLE.get(role)
        fact = facts[i % len(facts)]
        dur = float(beat.get("target_s", 4))
        dur = max(1.5, min(15.0, dur))
        total += dur

        narration = forced_narration.get(str(i))
        if narration is None:
            narration = _ROLE_NARRATION_TH[role].format(hook=hook, fact=fact).strip()
        narration = narration[:180]

        on_screen = _ROLE_ONSCREEN_TH[role].format(hook=hook, fact=fact).strip()[:80]
        action_en = _ROLE_ACTION_EN[role]
        visual_prompt_en = compose_visual_prompt(invariants, action_en)

        scenes.append(
            {
                "scene_id": str(uuid.uuid4()),
                "order": i,
                "role": role,
                "thai_narration": narration,
                "visual_prompt_en": visual_prompt_en,
                "on_screen_text_th": on_screen,
                "duration_s": dur,
                "asset_type": asset_type,
                # DEMO/PROOF are the product-centric beats (faceless: all b-roll).
                "product_focus": role in (ROLE_DEMO, ROLE_PROOF),
            }
        )

    # Clamp total into [MIN, MAX] seconds by nudging durations if the plan was extreme.
    total = sum(s["duration_s"] for s in scenes)
    if total < MIN_TOTAL_DURATION_S and scenes:
        pad = (MIN_TOTAL_DURATION_S - total) / len(scenes)
        for s in scenes:
            s["duration_s"] = round(min(15.0, s["duration_s"] + pad), 2)
        total = sum(s["duration_s"] for s in scenes)
    if total > MAX_TOTAL_DURATION_S and scenes:
        # Scale every scene down proportionally so the finished video stays within
        # the TikTok cap (never below 1.5s/scene, matching the per-beat floor above).
        factor = MAX_TOTAL_DURATION_S / total
        for s in scenes:
            s["duration_s"] = round(max(1.5, s["duration_s"] * factor), 2)
        total = sum(s["duration_s"] for s in scenes)

    return {
        "script_id": str(uuid.uuid4()),
        "video_job_id": str(video_job_id),
        "language": "th",
        "formula_template_id": str(script_input["formula_template"].get("id") or ""),
        "hook_template_id": str(script_input["hook_template"].get("id") or ""),
        "total_duration_s": round(total, 2),
        "scenes": scenes,
        # claim_audit is filled by run_claim_gate; placeholder keeps schema shape.
        "claim_audit": {"passed": False, "checked_at": "", "findings": []},
    }


def _parse_llm_script(result: ProviderResult) -> dict[str, Any] | None:
    """Extract a schema-valid script from a real provider's emit_script tool call."""
    if not result or not result.ok:
        return None
    data = result.data or {}
    candidate = data.get("script") or data.get("emit_script")
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except (ValueError, TypeError):
            return None
    if isinstance(candidate, dict) and "scenes" in candidate:
        return candidate
    return None


def generate_script(
    *,
    video_job_id: str,
    script_input: dict[str, Any],
    forced_narration: dict[str, str] | None = None,
    call_llm: bool = True,
) -> tuple[dict[str, Any], list[str], list[ProviderResult]]:
    """Generate + validate a structured script (§3A) WITHOUT the claim gate.

    Returns ``(script, validation_errors, billable_results)``. The claim gate is
    run separately by ``score_claims`` so the two-attempt retry loop lives in the
    service layer.
    """
    billable: list[ProviderResult] = []
    system = build_system_prompt(script_input)

    llm_script: dict[str, Any] | None = None
    if call_llm:
        try:
            llm = registry.get_llm_provider()
            result = llm.complete(
                prompt="Write the TikTok Shop script now via emit_script.",
                system=system,
                model=DEFAULT_LLM_MODEL,
                max_tokens=2048,
                idempotency_key=f"{video_job_id}:script:1",
            )
            billable.append(result)
            llm_script = _parse_llm_script(result)
        except Exception:  # noqa: BLE001 - fall back to deterministic synth
            llm_script = None

    if llm_script is not None and not forced_narration:
        script = llm_script
        script["video_job_id"] = str(video_job_id)
        script.setdefault("language", "th")
        script.setdefault(
            "claim_audit", {"passed": False, "checked_at": "", "findings": []}
        )
    else:
        script = _synthesize_script(
            video_job_id=video_job_id,
            script_input=script_input,
            forced_narration=forced_narration,
        )

    errors = validate_script(script)
    return script, errors, billable


def score_claims(
    script: dict[str, Any],
    *,
    script_input: dict[str, Any],
    idempotency_prefix: str,
    use_llm_judge: bool = True,
) -> tuple[dict[str, Any], list[ProviderResult]]:
    """Run the §3A.6 gate and attach ``claim_audit`` to the script in place."""
    product = script_input["product"]
    flags = script_input["operator_flags"]
    claim_audit, billable = claim_gate.run_claim_gate(
        script,
        approved_claims=product.get("approved_claims", []) or [],
        operator_verified_experience=bool(flags.get("operator_verified_experience")),
        idempotency_prefix=idempotency_prefix,
        use_llm_judge=use_llm_judge,
    )
    script["claim_audit"] = claim_audit
    return claim_audit, billable


def duration_seconds(scene: dict[str, Any]) -> int:
    """Whole-second duration for provider calls (§3D.9 ``ceil(scene.duration_s)``)."""
    return max(1, int(math.ceil(float(scene.get("duration_s", 1.5)))))
