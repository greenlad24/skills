"""§6B claim-safety classifier — hybrid: deterministic rules -> LLM judge -> reconcile.

Pipeline (§6B.3):

  Stage 1  deterministic Thai+English lexicon pre-filter (high recall, cheap).
  Stage 2  LLM judge via ``registry.get_llm_provider()`` (temperature 0, strict JSON).
  Stage 3  most-restrictive reconciliation of Stage 1 ∪ Stage 2.

Invariants (enforced here, tested in ``tests/``):
  * The classifier can only ever move a segment toward BLOCK / NEEDS_*; it can NEVER
    auto-ALLOW an EXPERIENTIAL / EFFICACY_HEALTH / COMPARATIVE / GUARANTEE claim.
  * Any LLM failure (timeout / malformed JSON / model error) -> affected segments keep
    their deterministic (already fail-closed) decision; the LLM can never grant a pass.
  * Temperature 0 is requested in the system prompt: the fixed ``LLMProvider.complete``
    Protocol has no temperature parameter, so determinism is the adapter's contract.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.adapters import registry
from app.core.config import settings
from app.modules.compliance import ruleset
from app.modules.compliance.common import (
    ClaimClass,
    Decision,
    SegmentResult,
    most_restrictive,
    sha256_hex,
)

# The judge model label; the real LLM adapter maps this to a concrete vendor model.
# Determinism (temp 0) is requested via the system prompt (see note in module docstring).
DEFAULT_JUDGE_MODEL = getattr(settings, "COMPLIANCE_JUDGE_MODEL", "claude-sonnet-4")

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


# --------------------------------------------------------------------------- #
# Segment extraction — accept the several script shapes other modules produce.
# --------------------------------------------------------------------------- #
def extract_segments(script: dict | str | None) -> list[tuple[str, str]]:
    """Return ``[(segment_id, text), ...]`` from a script dict/str.

    Accepts: ``{"segments": [{"id","text"}|str]}``, ``{"scenes":[{"spoken_text_th"}]}``,
    ``{"full_text": "..."}``, ``{"text": "..."}``, or a bare string.
    """
    if script is None:
        return []
    if isinstance(script, str):
        return _split_text(script)

    segs = script.get("segments")
    if isinstance(segs, list) and segs:
        out: list[tuple[str, str]] = []
        for i, seg in enumerate(segs):
            if isinstance(seg, str):
                out.append((f"seg_{i:03d}", seg))
            elif isinstance(seg, dict):
                sid = str(seg.get("id") or seg.get("segment_id") or f"seg_{i:03d}")
                txt = str(seg.get("text") or seg.get("spoken_text_th") or "")
                if txt.strip():
                    out.append((sid, txt))
        if out:
            return out

    scenes = script.get("scenes")
    if isinstance(scenes, list) and scenes:
        out = []
        for i, sc in enumerate(scenes):
            if isinstance(sc, dict):
                txt = str(sc.get("spoken_text_th") or sc.get("text") or "")
                if txt.strip():
                    sid = str(sc.get("id") or sc.get("sequence_no") or f"seg_{i:03d}")
                    out.append((f"seg_{i:03d}" if sid.isdigit() else sid, txt))
        if out:
            return out

    for key in ("full_text", "text", "spoken_text_th"):
        val = script.get(key)
        if isinstance(val, str) and val.strip():
            return _split_text(val)
    return []


def _split_text(text: str) -> list[tuple[str, str]]:
    parts = re.split(r"[\n\.।。!?]+|(?<=[฀-๿])\s{2,}", text)
    segs = [p.strip() for p in parts if p and p.strip()]
    if not segs:
        segs = [text.strip()] if text.strip() else []
    return [(f"seg_{i:03d}", s) for i, s in enumerate(segs)]


def script_hash(segments: list[tuple[str, str]]) -> str:
    """Bind decisions to the exact script (+ ruleset/prompt versions) (§6C.3, CHK-10)."""
    joined = "␟".join(t for _, t in segments)
    return sha256_hex(
        f"{ruleset.RULESET_VERSION}|{ruleset.CLASSIFIER_PROMPT_VERSION}|{joined}"
    )


# --------------------------------------------------------------------------- #
# Stage 1 — deterministic lexicon.
# --------------------------------------------------------------------------- #
def _default_decision_for_class(claim_class: str) -> str:
    if claim_class == ClaimClass.EFFICACY_HEALTH:
        return Decision.NEEDS_SUBSTANTIATION
    if claim_class in (ClaimClass.COMPARATIVE, ClaimClass.GUARANTEE):
        return Decision.NEEDS_SUBSTANTIATION
    if claim_class == ClaimClass.EXPERIENTIAL:
        return Decision.NEEDS_OPERATOR_VERIFICATION
    if claim_class == ClaimClass.ATTRIBUTE:
        return Decision.ALLOW
    return Decision.ALLOW  # NEUTRAL


def stage1_rules(segment_id: str, text: str) -> SegmentResult:
    """Deterministic high-recall pass. Never returns a *risky* class as ALLOW."""
    lowered = text.lower()
    matched: list[str] = []
    hit_classes: list[str] = []
    is_first_person = False

    for entry in ruleset.LEXICON:
        for term in entry["terms"]:
            t = term.lower()
            # ASCII terms match on word boundaries; Thai/non-ascii on substring.
            if t.isascii():
                # Leading word-boundary + prefix match: "whiten" also catches
                # "whitens"/"whitening" (fail-closed over-inclusive is acceptable).
                if re.search(r"(?<![a-z0-9])" + re.escape(t), lowered):
                    matched.append(entry["rule"])
                    hit_classes.append(entry["class"])
                    break
            elif term in text:
                matched.append(entry["rule"])
                hit_classes.append(entry["class"])
                break

    if not hit_classes:
        return SegmentResult(
            segment_id=segment_id, text=text, claim_class=ClaimClass.NEUTRAL,
            decision=Decision.ALLOW, risk="LOW",
            rationale="No high-risk lexicon hit (Stage 1).",
        )

    # Choose the highest-risk class among hits (efficacy > guarantee > comparative >
    # experiential), and mark first-person if an experiential marker fired.
    priority = [
        ClaimClass.EFFICACY_HEALTH, ClaimClass.GUARANTEE,
        ClaimClass.COMPARATIVE, ClaimClass.EXPERIENTIAL,
    ]
    is_first_person = ClaimClass.EXPERIENTIAL in hit_classes
    claim_class = next((c for c in priority if c in hit_classes), hit_classes[0])
    decision = _default_decision_for_class(claim_class)
    return SegmentResult(
        segment_id=segment_id, text=text, claim_class=claim_class,
        is_first_person=is_first_person, risk="HIGH", decision=decision,
        matched_rules=sorted(set(matched)),
        rationale=f"Stage-1 lexicon hit: {', '.join(sorted(set(matched)))}.",
    )


# --------------------------------------------------------------------------- #
# Stage 2 — LLM judge (strict JSON, temp 0). Returns per-segment decisions or None.
# --------------------------------------------------------------------------- #
CLASSIFIER_SYSTEM_PROMPT = """\
You are a compliance claim classifier for Thai-market shoppable video scripts.
You classify each segment; you NEVER approve risky claims. Operate deterministically
(temperature 0). Output STRICT JSON only — an array of segment objects, no prose.

Classes: EXPERIENTIAL, EFFICACY_HEALTH, COMPARATIVE, GUARANTEE, ATTRIBUTE, NEUTRAL.
Decision rules (MANDATORY):
- EFFICACY_HEALTH, COMPARATIVE, GUARANTEE -> NEEDS_SUBSTANTIATION (never ALLOW).
- EXPERIENTIAL (is_first_person=true)     -> NEEDS_OPERATOR_VERIFICATION.
- ATTRIBUTE -> ALLOW only if a plain verifiable product fact; else NEEDS_SUBSTANTIATION.
- Any uncertainty -> choose the more restrictive decision.
- Never output ALLOW for EFFICACY_HEALTH/COMPARATIVE/GUARANTEE/EXPERIENTIAL.
Each object: {segment_id, class, is_first_person, risk, decision, matched_rules, rationale}.
"""


def _sanitize_llm_decision(claim_class: str, decision: str) -> str:
    """Belt-and-suspenders: never let the LLM ALLOW a never-auto-allow class."""
    if claim_class in ClaimClass.NEVER_AUTO_ALLOW and decision == Decision.ALLOW:
        if claim_class == ClaimClass.EXPERIENTIAL:
            return Decision.NEEDS_OPERATOR_VERIFICATION
        return Decision.NEEDS_SUBSTANTIATION
    if decision not in (
        Decision.ALLOW, Decision.NEEDS_OPERATOR_VERIFICATION,
        Decision.NEEDS_SUBSTANTIATION, Decision.BLOCK,
    ):
        return Decision.BLOCK  # unknown -> fail closed
    return decision


def stage2_llm(
    segments: list[tuple[str, str]],
    *,
    category: str | None,
    approved_claims: list[dict[str, Any]] | None,
    shash: str,
) -> dict[str, dict[str, Any]] | None:
    """Call the LLM judge. Returns ``{segment_id: {class, decision, ...}}`` or None on
    any failure (timeout / malformed JSON / model error) — fail-closed by the caller.
    """
    if not segments:
        return {}
    payload = {
        "category": category,
        "approved_claims_library": approved_claims or [],
        "script_segments": [{"segment_id": sid, "text": txt} for sid, txt in segments],
    }
    prompt = (
        "temperature: 0\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\nReturn ONLY the JSON array."
    )
    try:
        provider = registry.get_llm_provider()
        result = provider.complete(
            prompt=prompt,
            system=CLASSIFIER_SYSTEM_PROMPT,
            model=DEFAULT_JUDGE_MODEL,
            max_tokens=2048,
            idempotency_key=f"compliance:claim_classifier:{shash}",
        )
    except Exception:
        return None
    if not getattr(result, "ok", False):
        return None

    text = (result.data or {}).get("text", "")
    parsed = _parse_json_array(text)
    if parsed is None:
        return None

    out: dict[str, dict[str, Any]] = {}
    for obj in parsed:
        if not isinstance(obj, dict):
            return None  # malformed -> fail closed
        sid = str(obj.get("segment_id", ""))
        if not sid:
            continue
        claim_class = obj.get("class", ClaimClass.NEUTRAL)
        if claim_class not in ClaimClass.ALL:
            claim_class = ClaimClass.NEUTRAL
        decision = _sanitize_llm_decision(
            claim_class, obj.get("decision", Decision.BLOCK)
        )
        out[sid] = {
            "class": claim_class,
            "decision": decision,
            "is_first_person": bool(obj.get("is_first_person", False)),
            "risk": obj.get("risk", "MEDIUM"),
            "matched_rules": list(obj.get("matched_rules", []) or []),
            "rationale": obj.get("rationale", "LLM judge."),
        }
    return out


def _parse_json_array(text: str) -> list | None:
    if not text:
        return None
    text = text.strip()
    # Tolerate ```json fences.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text).rstrip("`").strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, list) else None


# --------------------------------------------------------------------------- #
# Stage 3 — most-restrictive reconciliation + substantiation matching.
# --------------------------------------------------------------------------- #
def _approved_ref_for(text: str, approved_claims: list[dict[str, Any]] | None) -> str | None:
    """Return a substantiation_ref if this claim maps to an approved-claims entry that
    carries a non-empty ``substantiation_ref`` (§6B.3). Else None (=> stays blocked)."""
    if not approved_claims:
        return None
    norm = " ".join(text.lower().split())
    for entry in approved_claims:
        if not isinstance(entry, dict):
            continue
        claim_text = " ".join(str(entry.get("text", "")).lower().split())
        ref = entry.get("substantiation_ref")
        if claim_text and ref and (claim_text in norm or norm in claim_text):
            return str(ref)
    return None


def classify_script(
    script: dict | str | None,
    *,
    category: str | None = None,
    approved_claims: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the full hybrid classifier over a script.

    Returns::

        {
          "script_hash": "sha256:...",
          "ruleset_version": "...",
          "classifier_prompt_version": "...",
          "llm_ok": bool,
          "segments": [SegmentResult-as-dict, ...],
        }
    """
    segments = extract_segments(script)
    shash = script_hash(segments)

    # Stage 1 (deterministic) for every segment.
    stage1: dict[str, SegmentResult] = {
        sid: stage1_rules(sid, txt) for sid, txt in segments
    }

    # Stage 2 (LLM) — may be None on failure.
    llm = stage2_llm(
        segments, category=category, approved_claims=approved_claims, shash=shash
    )
    llm_ok = llm is not None

    results: list[SegmentResult] = []
    for sid, txt in segments:
        s1 = stage1[sid]
        decision = s1.decision
        claim_class = s1.claim_class
        rationale = s1.rationale
        matched = list(s1.matched_rules)
        is_fp = s1.is_first_person
        risk = s1.risk

        if llm_ok and sid in llm:
            l = llm[sid]
            # Most-restrictive reconciliation.
            decision = most_restrictive(decision, l["decision"])
            # Escalate class to the more specific/risky one if LLM found risk.
            if l["class"] in ClaimClass.NEVER_AUTO_ALLOW:
                claim_class = l["class"]
            elif claim_class == ClaimClass.NEUTRAL:
                claim_class = l["class"]
            is_fp = is_fp or l["is_first_person"]
            matched = sorted(set(matched) | set(l["matched_rules"]))
            if l["rationale"]:
                rationale = f"{rationale} | LLM: {l['rationale']}"
            risk = "HIGH" if decision == Decision.BLOCK else risk
        elif not llm_ok and claim_class != ClaimClass.NEUTRAL:
            # LLM failed AND Stage 1 already flagged risk -> fail closed harder.
            rationale += " | LLM judge unavailable (fail-closed)."

        # Substantiation resolution for NEEDS_SUBSTANTIATION.
        if decision == Decision.NEEDS_SUBSTANTIATION:
            ref = _approved_ref_for(txt, approved_claims)
            if ref:
                decision = Decision.ALLOW
                matched = sorted(set(matched) | {"APPROVED_CLAIMS_LIBRARY"})
                rationale += f" | Substantiated via approved-claims ref {ref}."
            # else: remains NEEDS_SUBSTANTIATION -> action BLOCK (fail closed).

        # Final safety net: never emit ALLOW for a never-auto-allow class w/o a source.
        if (
            claim_class in ClaimClass.NEVER_AUTO_ALLOW
            and decision == Decision.ALLOW
            and "APPROVED_CLAIMS_LIBRARY" not in matched
            and not (claim_class == ClaimClass.EXPERIENTIAL)
        ):
            decision = Decision.NEEDS_SUBSTANTIATION

        results.append(
            SegmentResult(
                segment_id=sid, text=txt, claim_class=claim_class,
                is_first_person=is_fp, risk=risk, decision=decision,
                matched_rules=matched, rationale=rationale.strip(" |"),
            )
        )

    return {
        "script_hash": shash,
        "ruleset_version": ruleset.RULESET_VERSION,
        "classifier_prompt_version": ruleset.CLASSIFIER_PROMPT_VERSION,
        "llm_ok": llm_ok,
        "segments": [r.__dict__ | {"action": r.action} for r in results],
        "_results": results,  # in-process handle; not JSON-serialized by callers
    }
