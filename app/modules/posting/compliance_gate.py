"""Pre-post compliance gate wrapper (hard gate — spec §5A / CONTRACTS §5).

The compliance module owns the checklist:

    from app.modules.compliance.service import run_prepost_checklist
    run_prepost_checklist(job_id) -> {"passed": bool, "checks": [...]}

Posting MUST refuse to publish unless the checklist is all-green (no override in
v1). The import is resolved at RUNTIME so this module can be built and tested
before the compliance module lands (CONTRACTS: "fine if compliance finishes after
you"). If the compliance module is not importable we FAIL CLOSED — treat the gate
as not-green — because publishing without a verifiable compliance pass would break
the hard-gate guarantee. Tests inject a green result by monkeypatching
`run_prepost_checklist` on this module.
"""

from __future__ import annotations

from typing import Any


def run_prepost_checklist(job_id: str) -> dict[str, Any]:
    """Call the compliance module's checklist, resolving the import lazily.

    Returns the checklist dict {"passed": bool, "checks": [...]}. If the compliance
    module is unavailable, returns a fail-closed result with an explanatory check
    rather than raising, so the caller can surface a clear reason.
    """
    try:
        from app.modules.compliance.service import (  # noqa: PLC0415 (runtime import by design)
            run_prepost_checklist as _impl,
        )
    except Exception as exc:  # noqa: BLE001 — ImportError or any load failure -> fail closed
        return {
            "passed": False,
            "checks": [
                {
                    "id": "compliance_module",
                    "label": "Compliance module available",
                    "pass": False,
                    "reason": f"compliance checklist unavailable: {exc}",
                }
            ],
        }
    return _impl(job_id)


def evaluate_gate(job_id: str) -> tuple[bool, dict[str, Any]]:
    """Return (all_green, checklist). `all_green` is True only when the checklist
    reports passed AND no individual check failed."""
    checklist = run_prepost_checklist(job_id)
    passed = bool(checklist.get("passed"))
    checks = checklist.get("checks") or []
    all_checks_ok = all(_check_passed(c) for c in checks) if checks else passed
    return (passed and all_checks_ok), checklist


def _check_passed(check: Any) -> bool:
    if isinstance(check, dict):
        # accept either "pass" (API shape) or "passed"
        if "pass" in check:
            return bool(check["pass"])
        return bool(check.get("passed", True))
    return bool(getattr(check, "passed", getattr(check, "pass_", True)))
