"""§6C.1 consent / likeness validity — the ``consent_valid()`` predicate.

Backs ELVIS Act tool-liability, Thai PDPA (biometric/voice = explicit consent), and
forward-compat with the NO FAKES Act (revocation + takedown). Fail closed: any missing
field or ambiguity -> invalid.

The predicate is duck-typed so it works with a SQLAlchemy ``ConsentRecord``, a plain
dict, or a lightweight test double, and with a ``job`` that exposes ``category`` and
``uses_cloned_voice`` (the core ``VideoJob`` has no ``category`` column, so callers pass
it via a context object/dict).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

REQUIRED_USAGE = "recorded_shoppable_video"
REQUIRED_TERRITORY = "TH"


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def consent_validity(job: Any, consent: Any, *, now: datetime | None = None
                     ) -> tuple[bool, list[str]]:
    """Return ``(is_valid, reasons)``. ``reasons`` lists every failed sub-predicate.

    All of the following must hold (§6C.1 / §6D CHK-8):
      * subject_is_operator and identity_verified
      * biometric_explicit_consent; if the job uses a cloned voice -> voice_licensed
      * not revoked
      * now within [term.start, term.end]
      * job.category in scope.categories AND "TH" in scope.territory
        AND "recorded_shoppable_video" in scope.usage
    """
    reasons: list[str] = []
    if consent is None:
        return False, ["no_consent_record"]

    now = now or datetime.now(timezone.utc)
    today = now.date()

    if not _get(consent, "subject_is_operator"):
        reasons.append("subject_is_operator_false")
    if not _get(consent, "identity_verified"):
        reasons.append("identity_verified_false")
    if not _get(consent, "biometric_explicit_consent"):
        reasons.append("biometric_explicit_consent_false")

    uses_voice = bool(_get(job, "uses_cloned_voice", True))  # default True = stricter
    if uses_voice and not _get(consent, "voice_licensed"):
        reasons.append("voice_licensed_false")

    if _get(consent, "revoked", False):
        reasons.append("consent_revoked")

    term = _get(consent, "term") or {}
    start = _parse_date(_get(term, "start"))
    end = _parse_date(_get(term, "end"))
    if start is None or end is None:
        reasons.append("term_missing")
    else:
        if today < start:
            reasons.append("term_not_started")
        if today > end:
            reasons.append("term_expired")

    scope = _get(consent, "scope") or {}
    categories = [str(c).lower() for c in (_get(scope, "categories") or [])]
    territory = [str(t).upper() for t in (_get(scope, "territory") or [])]
    usage = [str(u) for u in (_get(scope, "usage") or [])]

    category = _get(job, "category")
    if not category:
        reasons.append("job_category_unknown")  # fail safe
    elif str(category).lower() not in categories:
        reasons.append("category_out_of_scope")

    if REQUIRED_TERRITORY not in territory:
        reasons.append("territory_out_of_scope")
    if REQUIRED_USAGE not in usage:
        reasons.append("usage_out_of_scope")

    return (len(reasons) == 0), reasons


def consent_valid(job: Any, consent: Any, *, now: datetime | None = None) -> bool:
    """Boolean form of the §6C.1 predicate (fail closed)."""
    ok, _ = consent_validity(job, consent, now=now)
    return ok
