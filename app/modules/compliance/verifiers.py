"""§6A TikTok Shop policy verifiers (content-form, disclosure, category).

Two kinds of check:
  * **Code-checkable** now — consent (TT-FORM-5), disclosure toggle/manifest flags
    (TT-DISC-1..3), category rules (TT-CAT-*).
  * **Media-analysis** (real-environment, camera motion, face+product co-occurrence,
    >=3s dynamic) — these need frame analysis we don't run here. They sit behind the
    ``MediaAnalyzer`` interface. In ``DRY_RUN`` a deterministic stub PASSES; in real mode
    with no analyzer registered the check FAILS CLOSED (never a silent pass).

Each verifier returns a ``CheckResult``; the checklist (§6D) consumes them.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.core.config import settings
from app.modules.compliance import ruleset
from app.modules.compliance.common import CheckResult
from app.modules.compliance.consent import consent_validity

MOTION_SCORE_FLOOR = 0.15          # optical-flow motion score threshold (TT-FORM-2)
FRAME_ENTROPY_FLOOR = 0.10         # inter-frame delta entropy floor (TT-FORM-4)
MIN_DYNAMIC_SECONDS = 3.0          # TT-FORM-4 duration gate
FACE_PRODUCT_MIN_SECONDS = 1.0     # TT-FORM-3 co-occurrence


# --------------------------------------------------------------------------- #
# Media-analysis interface (stubbed; real impl registers later).
# --------------------------------------------------------------------------- #
@runtime_checkable
class MediaAnalyzer(Protocol):
    """Frame-level analysis of a rendered video. Inputs come from the render manifest."""

    def real_environment_score(self, manifest: dict) -> float: ...
    def camera_motion_score(self, manifest: dict) -> float: ...
    def face_product_cooccurrence_seconds(self, manifest: dict) -> float: ...
    def dynamic_stats(self, manifest: dict) -> dict: ...  # {duration_s, entropy, looped}
    def label_ocr_first_seconds(self, manifest: dict) -> dict: ...  # {present, from_s, to_s}


class DryRunMediaAnalyzer:
    """Deterministic passing stub for DRY_RUN / rehearsal (zero real analysis)."""

    provider_name = "dry-run-media-analyzer"

    def real_environment_score(self, manifest: dict) -> float:
        return float(manifest.get("real_environment_score", 0.9))

    def camera_motion_score(self, manifest: dict) -> float:
        return float(manifest.get("camera_motion_score", 0.5))

    def face_product_cooccurrence_seconds(self, manifest: dict) -> float:
        return float(manifest.get("face_product_cooccurrence_s", 2.0))

    def dynamic_stats(self, manifest: dict) -> dict:
        return {
            "duration_s": float(manifest.get("duration_s", 12.0)),
            "entropy": float(manifest.get("frame_entropy", 0.6)),
            "looped": bool(manifest.get("looped", False)),
        }

    def label_ocr_first_seconds(self, manifest: dict) -> dict:
        disc = manifest.get("disclosure", {})
        return {
            "present": bool(disc.get("label_baked_first_3s", True)),
            "from_s": float(disc.get("label_from_s", 0.0)),
            "to_s": float(disc.get("label_to_s", 3.0)),
        }


_MEDIA_ANALYZER: MediaAnalyzer | None = None


def register_media_analyzer(analyzer: MediaAnalyzer) -> None:
    """Register a real frame-analysis implementation (editor/vision module)."""
    global _MEDIA_ANALYZER
    _MEDIA_ANALYZER = analyzer


def get_media_analyzer() -> MediaAnalyzer | None:
    """DRY_RUN -> passing stub; real mode -> registered analyzer or None (fail closed)."""
    if _MEDIA_ANALYZER is not None:
        return _MEDIA_ANALYZER
    if settings.DRY_RUN:
        return DryRunMediaAnalyzer()
    return None


def _no_analyzer(check_id: str, name: str) -> CheckResult:
    return CheckResult(
        id=check_id, name=name, passed=False,
        detail="No media analyzer registered and DRY_RUN=false — fail closed.",
    )


# --------------------------------------------------------------------------- #
# §6A.1 content-form verifiers (TT-FORM-1..5).
# --------------------------------------------------------------------------- #
def tt_form_1_real_environment(manifest: dict) -> CheckResult:
    az = get_media_analyzer()
    if az is None:
        return _no_analyzer("TT-FORM-1", "Real-environment look")
    score = az.real_environment_score(manifest)
    void_bg = bool(manifest.get("void_background", False))
    ok = score >= 0.5 and not void_bg
    return CheckResult("TT-FORM-1", "Real-environment look", ok,
                       f"env_score={score:.2f} void_bg={void_bg}")


def tt_form_2_camera_motion(manifest: dict) -> CheckResult:
    az = get_media_analyzer()
    if az is None:
        return _no_analyzer("TT-FORM-2", "Camera movement present")
    score = az.camera_motion_score(manifest)
    ok = score >= MOTION_SCORE_FLOOR
    return CheckResult("TT-FORM-2", "Camera movement present", ok,
                       f"motion_score={score:.2f} floor={MOTION_SCORE_FLOOR}")


def tt_form_3_face_product(manifest: dict) -> CheckResult:
    az = get_media_analyzer()
    if az is None:
        return _no_analyzer("TT-FORM-3", "Face shown with product")
    secs = az.face_product_cooccurrence_seconds(manifest)
    ok = secs >= FACE_PRODUCT_MIN_SECONDS
    return CheckResult("TT-FORM-3", "Face shown with product", ok,
                       f"cooccurrence_s={secs:.2f} min={FACE_PRODUCT_MIN_SECONDS}")


def tt_form_4_dynamic(manifest: dict) -> CheckResult:
    az = get_media_analyzer()
    if az is None:
        return _no_analyzer("TT-FORM-4", ">=3s dynamic content")
    stats = az.dynamic_stats(manifest)
    ok = (
        stats.get("duration_s", 0.0) >= MIN_DYNAMIC_SECONDS
        and stats.get("entropy", 0.0) >= FRAME_ENTROPY_FLOOR
        and not stats.get("looped", True)
    )
    return CheckResult("TT-FORM-4", ">=3s dynamic content", ok,
                       f"duration={stats.get('duration_s')} entropy={stats.get('entropy')} "
                       f"looped={stats.get('looped')}")


def tt_form_5_consented_avatar(job: Any, consent: Any, *, now=None) -> CheckResult:
    """Avatar must be the consented, identity-verified operator (uses consent_valid)."""
    ok, reasons = consent_validity(job, consent, now=now)
    return CheckResult("TT-FORM-5", "Consented identity-verified avatar", ok,
                       "ok" if ok else f"consent_invalid: {', '.join(reasons)}")


def all_content_form(manifest: dict, job: Any, consent: Any, *, now=None) -> list[CheckResult]:
    return [
        tt_form_1_real_environment(manifest),
        tt_form_2_camera_motion(manifest),
        tt_form_3_face_product(manifest),
        tt_form_4_dynamic(manifest),
        tt_form_5_consented_avatar(job, consent, now=now),
    ]


# --------------------------------------------------------------------------- #
# §6A.2 disclosure verifiers (TT-DISC-1..3).
# --------------------------------------------------------------------------- #
def tt_disc_1_label_first_3s(disclosure: dict, manifest: dict | None = None) -> CheckResult:
    """Baked AI label present spanning 0.0 -> >=3.0s (render manifest + OCR spot-check)."""
    baked = bool(disclosure.get("label_baked_first_3s", False))
    ok = baked
    detail = f"label_baked_first_3s={baked}"
    if manifest is not None:
        az = get_media_analyzer()
        if az is None:
            return _no_analyzer("TT-DISC-1", "AI label baked in first 3s")
        ocr = az.label_ocr_first_seconds(manifest)
        covers = ocr.get("present") and ocr.get("from_s", 99) <= 0.0 and ocr.get("to_s", 0) >= 3.0
        ok = baked and bool(covers)
        detail += f" ocr={ocr}"
    return CheckResult("TT-DISC-1", "AI label baked in first 3s", ok, detail)


def tt_disc_2_platform_toggle(disclosure: dict) -> CheckResult:
    ok = bool(disclosure.get("platform_toggle_set", False))
    return CheckResult("TT-DISC-2", "Platform AIGC disclosure toggle set", ok,
                       f"platform_toggle_set={ok}")


def tt_disc_3_c2pa(disclosure: dict) -> CheckResult:
    ok = bool(disclosure.get("c2pa_embedded", False))
    return CheckResult("TT-DISC-3", "C2PA provenance embedded", ok,
                       f"c2pa_embedded={ok}")


# --------------------------------------------------------------------------- #
# §6A.3 category verifier (TT-CAT-*).
# --------------------------------------------------------------------------- #
def tt_category_rules(category: str | None, manifest: dict | None = None) -> CheckResult:
    """Known category + AI imagery non-embellishing. Unknown/unmapped -> fail (restricted)."""
    rule = ruleset.category_rule(category)
    known = rule.get("known", True) and rule.get("id") != "TT-CAT-UNKNOWN"
    if not known:
        return CheckResult("TT-CAT", "Category AI-imagery rules", False,
                           f"category={category!r} unknown/unmapped -> restricted (fail safe)")
    manifest = manifest or {}
    embellished = bool(manifest.get("ai_embellished", False))
    profile_ok = manifest.get("embellishment_profile", "none") == rule.get("embellishment_profile")
    ok = (not embellished) and (profile_ok or not rule.get("restricted", True))
    return CheckResult("TT-CAT", "Category AI-imagery rules", ok,
                       f"category={category} rule={rule.get('id')} embellished={embellished}")
