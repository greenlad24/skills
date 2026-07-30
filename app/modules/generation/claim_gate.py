"""Claim-safety gate (§3A.6) — fail-closed, defence in depth.

Three layers; any BLOCK (unauthorized) fails the whole script:

  1. Prompt-level prevention lives in ``scripting.py`` (the system prompt).
  2. Lexicon / regex screen (deterministic) — this module. A maintained Thai +
     English trigger lexicon runs over every ``thai_narration`` /
     ``on_screen_text_th``.
  3. LLM-judge classifier (semantic) — an independent LLM call catches paraphrase
     the regex misses. Optional/best-effort: it can only *add* BLOCKs, never
     downgrade a deterministic BLOCK (fail-closed).

It also calls the compliance module's authoritative gate
(``app.modules.compliance.service.classify_claims``) when available; that import
may not exist until the compliance agent ships — it is resolved lazily at runtime
and its absence never turns a BLOCK into an ALLOW.

Authorization inputs (the ONLY things that can turn a BLOCK into ALLOW):
  * ``approved_claims`` — merchant-verified, allowed verbatim (EFFICACY/HEALTH/WHITENING).
  * ``operator_verified_experience`` — allows FIRST_PERSON_EXPERIENCE.
  * SUPERLATIVE is ALWAYS blocked (OCPB unsubstantiated-superiority risk).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.adapters import registry
from app.core.adapters.base import ProviderResult
from app.modules.generation.constants import DEFAULT_LLM_MODEL, KIND_LLM

# --------------------------------------------------------------------------- #
# Categories (§3A.6)
# --------------------------------------------------------------------------- #
CAT_FIRST_PERSON = "FIRST_PERSON_EXPERIENCE"
CAT_EFFICACY = "EFFICACY"
CAT_HEALTH = "HEALTH"
CAT_WHITENING = "WHITENING"
CAT_SUPERLATIVE = "SUPERLATIVE"
CAT_OK = "OK"

VERDICT_ALLOW = "ALLOW"
VERDICT_BLOCK = "BLOCK"
VERDICT_REWRITE = "REWRITE"

# Categories whose block is lifted only by a verbatim approved claim.
_APPROVED_CLAIM_CATEGORIES = frozenset({CAT_EFFICACY, CAT_HEALTH, CAT_WHITENING})

# --------------------------------------------------------------------------- #
# Layer 2 lexicon — Thai + English trigger phrases (owned conceptually by §06;
# a defence-in-depth copy lives here so the gate never depends on a network call).
# --------------------------------------------------------------------------- #
LEXICON: dict[str, tuple[str, ...]] = {
    CAT_FIRST_PERSON: (
        "ฉันใช้แล้ว",
        "ใช้แล้วดี",
        "ใช้แล้วหน้าใส",
        "หน้าใสขึ้นเอง",
        "ผลลัพธ์ของฉัน",
        "เราใช้แล้ว",
        "i used it",
        "i tried it",
        "worked for me",
        "it worked for me",
        "changed my skin",
    ),
    CAT_EFFICACY: (
        "เห็นผล",
        "ได้ผล",
        "รักษา",
        "แก้ปัญหา",
        "หายขาด",
        "ลดเลือน",
        "works",
        "cures",
        "cure",
        "fixes",
        "clinically proven",
        "proven to",
        "reduces wrinkles",
    ),
    CAT_HEALTH: (
        "รักษาสิว",
        "ลดสิว",
        "หายสิว",
        "รักษาโรค",
        "therapeutic",
        "heals",
        "treats acne",
        "medical grade",
    ),
    CAT_WHITENING: (
        "ขาวขึ้น",
        "ผิวขาว",
        "ขาวใส",
        "หน้าขาว",
        "whitening",
        "whiter skin",
        "brightens skin",
        "skin whitening",
    ),
    CAT_SUPERLATIVE: (
        "ดีที่สุด",
        "อันดับ1",
        "อันดับ 1",
        "ที่สุดในไทย",
        "เบอร์1",
        "เบอร์ 1",
        "the best",
        "number one",
        "no.1",
        "no. 1",
        "#1",
    ),
}


def _authorized(category: str, span: str, *, approved_claims: list[str],
                operator_verified: bool) -> bool:
    """Fail-closed authorization: absence of proof == not allowed."""
    if category == CAT_SUPERLATIVE:
        return False  # never allowed
    if category == CAT_FIRST_PERSON:
        return bool(operator_verified)
    if category in _APPROVED_CLAIM_CATEGORIES:
        span_l = span.lower()
        return any(span_l in (c or "").lower() for c in approved_claims)
    return True


def lexicon_scan(
    scenes: list[dict[str, Any]],
    *,
    approved_claims: list[str],
    operator_verified: bool,
) -> list[dict[str, Any]]:
    """Deterministic layer-2 scan → list of findings."""
    findings: list[dict[str, Any]] = []
    for scene in scenes:
        scene_id = str(scene.get("scene_id", ""))
        haystacks = [
            scene.get("thai_narration", "") or "",
            scene.get("on_screen_text_th", "") or "",
        ]
        joined = "  ".join(haystacks)
        joined_l = joined.lower()
        for category, phrases in LEXICON.items():
            for phrase in phrases:
                if phrase in joined or phrase.lower() in joined_l:
                    allowed = _authorized(
                        category, phrase,
                        approved_claims=approved_claims,
                        operator_verified=operator_verified,
                    )
                    findings.append(
                        {
                            "scene_id": scene_id,
                            "span": phrase,
                            "category": category,
                            "verdict": VERDICT_ALLOW if allowed else VERDICT_BLOCK,
                        }
                    )
    return findings


def llm_judge_scan(
    scenes: list[dict[str, Any]],
    *,
    approved_claims: list[str],
    operator_verified: bool,
    idempotency_prefix: str,
) -> tuple[list[dict[str, Any]], ProviderResult | None]:
    """Layer-3 semantic classifier (best-effort).

    Makes one temperature-0 LLM call to catch paraphrase. The fake provider does
    not return structured verdicts, so this parses defensively and, when it can't
    extract a verdict, contributes nothing (the deterministic layer still governs
    — fail-closed is preserved because layer 2 can only be *added to*).

    Returns ``(findings, provider_result)`` so the caller can bill the call.
    """
    try:
        llm = registry.get_llm_provider()
    except Exception:  # noqa: BLE001 - never let the judge crash the gate
        return [], None

    lines = []
    for scene in scenes:
        lines.append(
            f"- scene {scene.get('scene_id')}: {scene.get('thai_narration', '')} "
            f"|| {scene.get('on_screen_text_th', '')}"
        )
    system = (
        "You are a Thai cosmetics advertising claim classifier. For each sentence, "
        "return the category in {EFFICACY, HEALTH, WHITENING, FIRST_PERSON_EXPERIENCE, "
        "SUPERLATIVE, OK} and a verdict in {ALLOW, BLOCK, REWRITE}. Temperature 0."
    )
    prompt = "Classify each line:\n" + "\n".join(lines)
    try:
        result = llm.complete(
            prompt=prompt,
            system=system,
            model=DEFAULT_LLM_MODEL,
            max_tokens=1024,
            idempotency_key=f"{idempotency_prefix}:claimjudge",
        )
    except Exception:  # noqa: BLE001
        return [], None

    findings: list[dict[str, Any]] = []
    data = result.data if result and result.ok else {}
    # Real providers return structured verdicts under data["findings"]; the fake
    # returns free text and yields none (deterministic layer covers it).
    for f in data.get("findings", []) or []:
        if not isinstance(f, dict):
            continue
        category = f.get("category")
        span = f.get("span", "")
        if category in {CAT_EFFICACY, CAT_HEALTH, CAT_WHITENING, CAT_FIRST_PERSON, CAT_SUPERLATIVE}:
            allowed = _authorized(
                category, span,
                approved_claims=approved_claims,
                operator_verified=operator_verified,
            )
            findings.append(
                {
                    "scene_id": str(f.get("scene_id", "")),
                    "span": span,
                    "category": category,
                    "verdict": VERDICT_ALLOW if allowed else VERDICT_BLOCK,
                }
            )
    return findings, result


def _compliance_gate(script: dict[str, Any]) -> dict[str, Any] | None:
    """Call the authoritative compliance gate if it exists (resolved at runtime).

    Signature: ``classify_claims(script: dict) -> {allowed: bool, flags: [...]}``.
    Its absence must never turn a BLOCK into an ALLOW (fail-closed).
    """
    try:
        from app.modules.compliance.service import classify_claims  # type: ignore
    except Exception:  # noqa: BLE001 - not shipped yet / import error
        return None
    try:
        out = classify_claims(script)
        if isinstance(out, dict):
            return out
    except Exception:  # noqa: BLE001
        return None
    return None


def run_claim_gate(
    script: dict[str, Any],
    *,
    approved_claims: list[str] | None = None,
    operator_verified_experience: bool = False,
    idempotency_prefix: str = "claimgate",
    use_llm_judge: bool = True,
    use_compliance: bool = True,
) -> tuple[dict[str, Any], list[ProviderResult]]:
    """Run the full fail-closed gate → ``(claim_audit, billable_results)``.

    ``claim_audit`` is the object persisted with the script (§3A.4): it always has
    ``passed`` / ``checked_at`` / ``findings``. ``passed`` is True iff there is no
    unauthorized BLOCK across all layers.
    """
    approved_claims = approved_claims or []
    scenes = script.get("scenes", []) or []
    billable: list[ProviderResult] = []

    findings = lexicon_scan(
        scenes,
        approved_claims=approved_claims,
        operator_verified=operator_verified_experience,
    )

    if use_llm_judge:
        judge_findings, judge_result = llm_judge_scan(
            scenes,
            approved_claims=approved_claims,
            operator_verified=operator_verified_experience,
            idempotency_prefix=idempotency_prefix,
        )
        findings.extend(judge_findings)
        if judge_result is not None:
            billable.append(judge_result)

    # Authoritative compliance module (if present) — can only *add* a block.
    compliance_out = _compliance_gate(script) if use_compliance else None
    compliance_blocked = False
    if compliance_out is not None and compliance_out.get("allowed") is False:
        compliance_blocked = True
        for flag in compliance_out.get("flags", []) or []:
            findings.append(
                {
                    "scene_id": str(flag.get("scene_id", "")) if isinstance(flag, dict) else "",
                    "span": (flag.get("span", "") if isinstance(flag, dict) else str(flag)),
                    "category": (flag.get("category", CAT_OK) if isinstance(flag, dict) else CAT_OK),
                    "verdict": VERDICT_BLOCK,
                }
            )

    has_block = any(f["verdict"] == VERDICT_BLOCK for f in findings)
    passed = (not has_block) and (not compliance_blocked)

    claim_audit = {
        "passed": passed,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "findings": findings,
    }
    return claim_audit, billable


def blocking_spans(claim_audit: dict[str, Any]) -> list[dict[str, Any]]:
    """The offending spans, fed back to the generator as negative constraints."""
    return [f for f in claim_audit.get("findings", []) if f.get("verdict") == VERDICT_BLOCK]
