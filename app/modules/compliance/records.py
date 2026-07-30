"""§6C.3 ComplianceRecord — immutable, hash-chained audit log + per-claim decisions.

The audit trail is the product's core legal defense (§6.0 principle 3): append-only
events, no update/delete of prior events, each event forming a tamper-evident hash chain
``{ts, actor, type, payload_hash, prev_hash}``.

This module is storage-agnostic:
  * ``ComplianceLedger`` is a pure in-memory builder/validator of the event chain and the
    §6C.3 record envelope (works in tests with zero DB).
  * ``persist_envelope`` / ``load_envelope`` map the envelope onto the core
    ``ComplianceRecord`` SQLAlchemy row (``detail`` JSON + ``events`` JSON + ``prev_hash``).
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.modules.compliance import ruleset
from app.modules.compliance.common import canonical_hash

GENESIS_HASH = "sha256:" + "0" * 64


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class ClaimDecision:
    """One flagged-segment decision recorded into the ComplianceRecord (§6C.3)."""

    segment_id: str
    text_hash: str
    claim_class: str
    final_decision: str
    resolved: bool = False
    resolution: str | None = None            # OPERATOR_VERIFIED | SUBSTANTIATED | REMOVED_BY_EDIT | unresolved
    substantiation_ref: str | None = None
    operator_affirmed: bool = False
    actor: str | None = None
    actor_identity_ref: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ComplianceLedger:
    """Append-only, hash-chained event log for one VideoJob's ComplianceRecord."""

    def __init__(
        self,
        video_job_id: str,
        *,
        script_hash: str | None = None,
        consent_ref: str | None = None,
        category: str | None = None,
    ) -> None:
        self.video_job_id = str(video_job_id)
        self.ruleset_version = ruleset.RULESET_VERSION
        self.classifier_prompt_version = ruleset.CLASSIFIER_PROMPT_VERSION
        self.script_hash = script_hash
        self.consent_ref = consent_ref
        self.consent_valid_at_decision: bool | None = None
        self.category = category
        self.category_rules_satisfied: bool | None = None
        self.disclosure: dict[str, Any] = {
            "label_baked_first_3s": False,
            "label_render_evidence": None,
            "platform_toggle_set": False,
            "c2pa_embedded": False,
        }
        self.claim_decisions: list[dict[str, Any]] = []
        self.checklist_result: dict[str, Any] | None = None
        self.events: list[dict[str, Any]] = []
        self.sealed_at: str | None = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.append_event("created", actor="system", payload={"video_job_id": self.video_job_id})

    # --- append-only event chain -------------------------------------------- #
    def append_event(self, event_type: str, *, actor: str | None,
                     payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Append a tamper-evident event. Never mutates or removes prior events."""
        if self.sealed_at is not None:
            raise RecordSealedError("ComplianceRecord is sealed; no further events allowed.")
        prev_hash = self.events[-1]["event_hash"] if self.events else GENESIS_HASH
        payload = payload or {}
        payload_hash = canonical_hash(payload)
        ts = datetime.now(timezone.utc).isoformat()
        core = {
            "ts": ts,
            "actor": actor,
            "type": event_type,
            "payload": payload,
            "payload_hash": payload_hash,
            "prev_hash": prev_hash,
        }
        core["event_hash"] = _hash(
            f"{prev_hash}|{ts}|{actor}|{event_type}|{payload_hash}"
        )
        self.events.append(core)
        return core

    def add_claim_decision(self, decision: ClaimDecision, *, actor: str | None = None) -> None:
        self.claim_decisions.append(decision.to_dict())
        self.append_event(
            "claim_decision", actor=actor or decision.actor,
            payload={"segment_id": decision.segment_id,
                     "final_decision": decision.final_decision,
                     "resolution": decision.resolution},
        )

    def set_disclosure(self, **kwargs: Any) -> None:
        self.disclosure.update({k: v for k, v in kwargs.items() if k in self.disclosure})
        self.append_event("disclosure_updated", actor="system", payload=dict(kwargs))

    def set_consent(self, ref: str | None, valid: bool) -> None:
        self.consent_ref = ref
        self.consent_valid_at_decision = valid
        self.append_event("consent_evaluated", actor="system",
                           payload={"consent_ref": ref, "valid": valid})

    def set_category_result(self, satisfied: bool) -> None:
        self.category_rules_satisfied = satisfied
        self.append_event("category_evaluated", actor="system",
                           payload={"satisfied": satisfied})

    # --- verification / integrity ------------------------------------------- #
    def verify_chain(self) -> bool:
        """Recompute the hash chain; True iff untampered (§6C.3, AC-6D-3)."""
        prev = GENESIS_HASH
        for ev in self.events:
            if ev.get("prev_hash") != prev:
                return False
            expected = _hash(
                f"{ev['prev_hash']}|{ev['ts']}|{ev['actor']}|{ev['type']}|{ev['payload_hash']}"
            )
            if ev.get("event_hash") != expected:
                return False
            if canonical_hash(ev.get("payload", {})) != ev.get("payload_hash"):
                return False
            prev = ev["event_hash"]
        return True

    def seal(self, checklist_result: dict[str, Any]) -> None:
        """Seal on a passing checklist; the record is frozen thereafter (§6D)."""
        self.checklist_result = checklist_result
        # sealing event must be appended BEFORE marking sealed_at.
        self.append_event("sealed", actor="system",
                          payload={"passed": bool(checklist_result.get("passed"))})
        self.sealed_at = datetime.now(timezone.utc).isoformat()

    # --- envelope (§6C.3 shape) --------------------------------------------- #
    def envelope(self) -> dict[str, Any]:
        return {
            "video_job_id": self.video_job_id,
            "ruleset_version": self.ruleset_version,
            "classifier_prompt_version": self.classifier_prompt_version,
            "script_hash": self.script_hash,
            "consent_ref": self.consent_ref,
            "consent_valid_at_decision": self.consent_valid_at_decision,
            "disclosure": self.disclosure,
            "category": self.category,
            "category_rules_satisfied": self.category_rules_satisfied,
            "claim_decisions": self.claim_decisions,
            "checklist_result": self.checklist_result,
            "events": self.events,
            "created_at": self.created_at,
            "sealed_at": self.sealed_at,
        }

    @classmethod
    def from_envelope(cls, env: dict[str, Any]) -> "ComplianceLedger":
        led = cls(
            env.get("video_job_id", ""),
            script_hash=env.get("script_hash"),
            consent_ref=env.get("consent_ref"),
            category=env.get("category"),
        )
        # Replace the auto-created genesis event with the persisted chain verbatim.
        led.events = list(env.get("events", []))
        led.ruleset_version = env.get("ruleset_version", led.ruleset_version)
        led.classifier_prompt_version = env.get(
            "classifier_prompt_version", led.classifier_prompt_version)
        led.consent_valid_at_decision = env.get("consent_valid_at_decision")
        led.disclosure = env.get("disclosure", led.disclosure)
        led.category_rules_satisfied = env.get("category_rules_satisfied")
        led.claim_decisions = list(env.get("claim_decisions", []))
        led.checklist_result = env.get("checklist_result")
        led.created_at = env.get("created_at", led.created_at)
        led.sealed_at = env.get("sealed_at")
        return led


class RecordSealedError(Exception):
    """Raised on any attempt to mutate a sealed (frozen) ComplianceRecord."""


# --------------------------------------------------------------------------- #
# Persistence bridge onto the core ComplianceRecord SQLAlchemy row.
# --------------------------------------------------------------------------- #
def persist_envelope(db, video_job_id, ledger: ComplianceLedger, *, check_type: str = "envelope"):
    """Write the ledger envelope onto a ComplianceRecord row (append a new row).

    We append a new immutable row rather than updating in place, preserving history.
    Returns the created ComplianceRecord (not committed — caller commits).
    """
    from app.core.models import ComplianceRecord  # local import: only app.core.*

    env = ledger.envelope()
    row = ComplianceRecord(
        video_job_id=video_job_id,
        check_type=check_type,
        passed=bool((ledger.checklist_result or {}).get("passed")) if ledger.checklist_result else None,
        detail=env,
        checked_at=datetime.now(timezone.utc),
        events=env["events"],
        prev_hash=env["events"][-1]["event_hash"] if env["events"] else GENESIS_HASH,
        ruleset_version=ledger.ruleset_version,
    )
    db.add(row)
    return row


def load_latest_envelope(db, video_job_id) -> dict[str, Any] | None:
    """Load the most recent envelope ComplianceRecord.detail for a job, or None."""
    from sqlalchemy import select

    from app.core.models import ComplianceRecord

    try:
        rows = db.execute(
            select(ComplianceRecord)
            .where(ComplianceRecord.video_job_id == video_job_id)
            .order_by(ComplianceRecord.created_at.desc())
        ).scalars().all()
    except Exception:
        return None
    for row in rows:
        detail = row.detail
        if isinstance(detail, dict) and "claim_decisions" in detail:
            return detail
    return None
