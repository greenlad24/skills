"""Shared vocabulary + tiny value types for the compliance engine.

Kept dependency-free (only stdlib) so every other compliance submodule can import it
without creating cycles. The canonical rule *data* lives in ``ruleset.py``; this file
only holds the enums/constants and the small dataclasses passed between stages.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


# --------------------------------------------------------------------------- #
# Claim taxonomy (§6B.1) — string constants (JSON/DB friendly).
# --------------------------------------------------------------------------- #
class ClaimClass:
    EXPERIENTIAL = "EXPERIENTIAL"
    EFFICACY_HEALTH = "EFFICACY_HEALTH"
    COMPARATIVE = "COMPARATIVE"
    GUARANTEE = "GUARANTEE"
    ATTRIBUTE = "ATTRIBUTE"
    NEUTRAL = "NEUTRAL"

    ALL = {EXPERIENTIAL, EFFICACY_HEALTH, COMPARATIVE, GUARANTEE, ATTRIBUTE, NEUTRAL}
    # Classes the classifier may NEVER auto-ALLOW (§6B.1 rule of construction).
    NEVER_AUTO_ALLOW = {EXPERIENTIAL, EFFICACY_HEALTH, COMPARATIVE, GUARANTEE}


# --------------------------------------------------------------------------- #
# Per-segment decisions (§6B.2 schema) — ordered by restrictiveness.
# --------------------------------------------------------------------------- #
class Decision:
    ALLOW = "ALLOW"
    NEEDS_OPERATOR_VERIFICATION = "NEEDS_OPERATOR_VERIFICATION"
    NEEDS_SUBSTANTIATION = "NEEDS_SUBSTANTIATION"
    BLOCK = "BLOCK"


# Higher ordinal == more restrictive. Used by "most-restrictive" reconciliation.
_DECISION_RANK = {
    Decision.ALLOW: 0,
    Decision.NEEDS_OPERATOR_VERIFICATION: 1,
    Decision.NEEDS_SUBSTANTIATION: 2,
    Decision.BLOCK: 3,
}


# --------------------------------------------------------------------------- #
# Public action verbs used by the service-level classify_claims() contract.
# --------------------------------------------------------------------------- #
class Action:
    ALLOW = "ALLOW"    # auto-pass (attribute w/ source, or neutral)
    ROUTE = "ROUTE"    # cannot pass as-is; route to operator / substantiation
    BLOCK = "BLOCK"    # hard block; only resolvable by editing the script


# Fail-closed mapping decision -> externally-reported action.
# NEEDS_SUBSTANTIATION (efficacy/health/comparative/guarantee) surfaces as BLOCK:
# it is BLOCK-unless a merchant approved-claims entry + substantiation ref exists,
# and that resolution happens in the records/checklist layer, never in the scan.
_DECISION_TO_ACTION = {
    Decision.ALLOW: Action.ALLOW,
    Decision.NEEDS_OPERATOR_VERIFICATION: Action.ROUTE,
    Decision.NEEDS_SUBSTANTIATION: Action.BLOCK,
    Decision.BLOCK: Action.BLOCK,
}


def decision_rank(decision: str) -> int:
    """Restrictiveness ordinal; unknown decisions are treated as most restrictive."""
    return _DECISION_RANK.get(decision, _DECISION_RANK[Decision.BLOCK])


def most_restrictive(*decisions: str) -> str:
    """Return the most restrictive of the given decisions (fail-closed default BLOCK)."""
    if not decisions:
        return Decision.BLOCK
    return max(decisions, key=decision_rank)


def decision_to_action(decision: str) -> str:
    """Fail-closed: unknown decisions map to BLOCK."""
    return _DECISION_TO_ACTION.get(decision, Action.BLOCK)


# --------------------------------------------------------------------------- #
# Value types
# --------------------------------------------------------------------------- #
@dataclass
class SegmentResult:
    """One classified script segment across all classifier stages."""

    segment_id: str
    text: str
    claim_class: str = ClaimClass.NEUTRAL
    is_first_person: bool = False
    risk: str = "LOW"
    decision: str = Decision.ALLOW
    matched_rules: list[str] = field(default_factory=list)
    rationale: str = ""

    @property
    def action(self) -> str:
        return decision_to_action(self.decision)

    def to_flag(self) -> dict[str, Any]:
        """The public flag shape returned by service.classify_claims()."""
        return {
            "segment_id": self.segment_id,
            "claim": self.text,
            "type": self.claim_class,
            "action": self.action,
            "decision": self.decision,
            "is_first_person": self.is_first_person,
            "risk": self.risk,
            "matched_rules": list(self.matched_rules),
            "reason": self.rationale,
        }


@dataclass
class CheckResult:
    """One row of a checklist / verifier evaluation."""

    id: str
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Hashing helpers (bind decisions to exact text/script; back the audit chain).
# --------------------------------------------------------------------------- #
def sha256_hex(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_hash(payload: Any) -> str:
    """Stable hash of an arbitrary JSON-able payload (sorted keys)."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return sha256_hex(blob)
