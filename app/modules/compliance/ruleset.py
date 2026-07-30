"""Versioned rule tables — *config as data, not code* (§6.0 principle 5).

Every compliance decision pins ``RULESET_VERSION`` so it is reproducible years later.
The canonical values are embedded here as Python data (so the module is importable and
testable with zero extra deps); ``data/ruleset_2026_07.yaml`` mirrors them for
counsel-review workflows and is loaded as an override when PyYAML is available.

⚠️ NOT LEGAL ADVICE. The claim taxonomy, disclosure copy, category rules, and the
jurisdiction map below are engineering encodings of researched facts and MUST be reviewed
by qualified US/EU/Thai counsel before production launch. Where counsel and this file
disagree, counsel wins — encode their determination here and bump ``RULESET_VERSION``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.modules.compliance.common import ClaimClass, Decision

RULESET_VERSION = "2026.07.0"
CLASSIFIER_PROMPT_VERSION = "cc-2026.07.0"

# Ruleset versions the engine still accepts (CHK-11). Anything else -> deprecated -> BLOCK.
ACTIVE_RULESET_VERSIONS = frozenset({"2026.07.0"})


# --------------------------------------------------------------------------- #
# §6B.3 Stage-1 deterministic lexicon (Thai + English), high-recall pre-filter.
# Each entry: (rule_id, claim_class, [surface terms]). A hit forces the segment
# into the given class and can never be dropped to ALLOW without a source.
# --------------------------------------------------------------------------- #
LEXICON: list[dict[str, Any]] = [
    # --- Thai FDA / whitening / anti-aging / cure (EFFICACY_HEALTH) ---
    {
        "rule": "TH_WHITENING",
        "class": ClaimClass.EFFICACY_HEALTH,
        "terms": ["ขาวใส", "ผิวขาว", "ขาวขึ้น", "กระจ่างใส", "ฝ้า", "กระ", "หน้าใส"],
    },
    {
        "rule": "TH_ANTIAGING",
        "class": ClaimClass.EFFICACY_HEALTH,
        "terms": ["ลดริ้วรอย", "อ่อนกว่าวัย", "ย้อนวัย", "ริ้วรอย"],
    },
    {
        "rule": "TH_CURE_TREAT",
        "class": ClaimClass.EFFICACY_HEALTH,
        "terms": ["รักษา", "หายขาด", "หาย", "บำบัด", "รักษาสิว"],
    },
    {
        "rule": "TH_WEIGHTLOSS",
        "class": ClaimClass.EFFICACY_HEALTH,
        "terms": ["ลดน้ำหนัก", "ลดพุง", "เผาผลาญ", "ผอมเพรียว"],
    },
    {
        "rule": "EN_EFFICACY_HEALTH",
        "class": ClaimClass.EFFICACY_HEALTH,
        "terms": [
            "whiten", "whitening", "anti-aging", "anti aging", "cure", "cures",
            "treats", "treat", "heal", "clears acne", "clear acne", "acne-free",
            "weight loss", "lose weight", "brighten", "brightens", "fade dark spots",
            "reduce wrinkles", "removes wrinkles",
        ],
    },
    # --- Comparative / superlative ---
    {
        "rule": "TH_SUPERLATIVE",
        "class": ClaimClass.COMPARATIVE,
        "terms": ["ดีที่สุด", "อันดับ 1", "อันดับหนึ่ง", "เบอร์ 1", "ที่สุดในไทย"],
    },
    {
        "rule": "EN_SUPERLATIVE",
        "class": ClaimClass.COMPARATIVE,
        "terms": ["best", "#1", "number one", "no.1", "the only", "unbeatable", "top-rated"],
    },
    # --- Guarantee / financial / safety ---
    {
        "rule": "TH_GUARANTEE",
        "class": ClaimClass.GUARANTEE,
        "terms": ["รับประกัน", "การันตี", "คืนเงิน", "ปลอดภัย 100"],
    },
    {
        "rule": "EN_GUARANTEE",
        "class": ClaimClass.GUARANTEE,
        "terms": [
            "guarantee", "guaranteed", "money-back", "money back", "100% safe",
            "100 percent safe", "risk-free", "no side effects",
        ],
    },
    # --- First-person experiential markers ---
    {
        "rule": "TH_EXPERIENTIAL_FIRST_PERSON",
        "class": ClaimClass.EXPERIENTIAL,
        "terms": ["ฉันใช้", "ผมใช้", "หลังจากใช้", "พอใช้แล้ว", "ใช้เองแล้ว", "ผิวฉัน", "ของฉัน"],
    },
    {
        "rule": "EN_EXPERIENTIAL_FIRST_PERSON",
        "class": ClaimClass.EXPERIENTIAL,
        "terms": [
            "i use", "i used", "i've used", "i have used", "it worked for me",
            "my skin", "for me it", "i tried", "after using it my", "changed my life",
        ],
    },
]


# --------------------------------------------------------------------------- #
# §6A.3 category-restricted AI imagery. Unknown/unmapped -> restricted (fail safe).
# --------------------------------------------------------------------------- #
CATEGORY_RULES: dict[str, dict[str, Any]] = {
    "beauty": {
        "id": "TT-CAT-1",
        "restricted": True,
        "embellishment_profile": "none",
        "ban": ["before_after", "skin_smoothing", "result_imagery"],
        "efficacy_hard_block": True,
    },
    "cosmetics": {
        "id": "TT-CAT-1",
        "restricted": True,
        "embellishment_profile": "none",
        "ban": ["before_after", "skin_smoothing", "result_imagery"],
        "efficacy_hard_block": True,
    },
    "supplements": {
        "id": "TT-CAT-2",
        "restricted": True,
        "embellishment_profile": "none",
        "ban": ["physiological_effect_imagery"],
        "efficacy_hard_block": True,
    },
    "health": {
        "id": "TT-CAT-2",
        "restricted": True,
        "embellishment_profile": "none",
        "ban": ["physiological_effect_imagery"],
        "efficacy_hard_block": True,
    },
    "baby": {
        "id": "TT-CAT-3",
        "restricted": True,
        "embellishment_profile": "none",
        "ban": ["safety_outcome_imagery"],
        "efficacy_hard_block": True,
    },
    "maternity": {
        "id": "TT-CAT-3",
        "restricted": True,
        "embellishment_profile": "none",
        "ban": ["safety_outcome_imagery"],
        "efficacy_hard_block": True,
    },
    "electronics": {
        "id": "TT-CAT-4",
        "restricted": True,
        "embellishment_profile": "none",
        "ban": ["exaggerated_performance", "spec_exaggeration"],
        "efficacy_hard_block": False,
    },
    # A general/unrestricted bucket still requires a KNOWN category to pass CHK-7.
    "general": {
        "id": "TT-CAT-0",
        "restricted": False,
        "embellishment_profile": "conservative",
        "ban": [],
        "efficacy_hard_block": False,
    },
}


# --------------------------------------------------------------------------- #
# §6A.2 / §6C.2 disclosure copy (versioned string set; counsel-reviewed wording).
# --------------------------------------------------------------------------- #
DISCLOSURE_COPY = {
    "medium_th": "เนื้อหาที่สร้างด้วย AI",
    "medium_en": "AI-generated",
    "endorser_th": "ผู้นำเสนอเป็นอวาตาร์ AI",
    "endorser_en": "Presenter is an AI avatar",
    "min_first_seconds": 3.0,
    "min_height_frac": 0.04,
    "min_contrast_ratio": 4.5,
}


# --------------------------------------------------------------------------- #
# §6E jurisdiction -> control map (data, not code).
# --------------------------------------------------------------------------- #
JURISDICTION_MAP: list[dict[str, Any]] = [
    {
        "regime": "TikTok Shop policy (2026)",
        "obligation": "Real-env, motion, face+product, >=3s dynamic; AI-voice ban is "
        "livestream-only; disclosure required; category limits.",
        "controls": ["TT-FORM-1..5", "TT-DISC-1..3", "TT-CAT-1..4",
                     "CHK-1", "CHK-2", "CHK-3", "CHK-7", "CHK-9"],
    },
    {
        "regime": "US FTC — Testimonials/Reviews Rule (2024), Endorsement Guides",
        "obligation": "No fake/unsubstantiated testimonials (~$51,744/violation); clear "
        "AI/endorser disclosure.",
        "controls": ["6B", "CHK-4", "CHK-5", "CHK-6", "dual-disclosure-6C.2"],
    },
    {
        "regime": "EU AI Act — Art. 50 (from 2 Aug 2026)",
        "obligation": "Transparency: mark AI-generated content & synthetic media.",
        "controls": ["TT-DISC-1", "endorser-disclosure-6C.2", "TT-DISC-3",
                     "CHK-1", "CHK-3"],
    },
    {
        "regime": "Thai OCPB (Consumer Protection)",
        "obligation": "Ban false/exaggerated ads; visible AI label.",
        "controls": ["6B", "TT-DISC-1", "CHK-1", "CHK-4", "CHK-5"],
    },
    {
        "regime": "Thai FDA (cosmetics/food/health advertising)",
        "obligation": "No unapproved efficacy/whitening/anti-aging/health claims.",
        "controls": ["6B-EFFICACY_HEALTH-hard-block", "TT-CAT-1", "TT-CAT-2",
                     "TT-CAT-3", "CHK-5"],
    },
    {
        "regime": "Thai PDPA",
        "obligation": "Biometric & voice data -> explicit consent.",
        "controls": ["ConsentRecord.biometric_explicit_consent",
                     "ConsentRecord.voice_licensed", "consent_valid()", "CHK-8"],
    },
    {
        "regime": "ELVIS Act (voice/likeness)",
        "obligation": "Tool liability for unauthorized voice/likeness.",
        "controls": ["subject_is_operator", "identity_verified", "TT-FORM-5"],
    },
    {
        "regime": "NO FAKES Act (forward-compat)",
        "obligation": "Consent verification + takedown/revocation.",
        "controls": ["revocation-path-6C.1", "takedown-endpoint",
                     "retro-flag-published-posts"],
    },
]


# --------------------------------------------------------------------------- #
# Decision routing table (§6B.3 Stage 3). Maps a reconciled decision to a
# resolution requirement. Kept as data so counsel can retune without code edits.
# --------------------------------------------------------------------------- #
RESOLUTION_ROUTING = {
    Decision.ALLOW: "auto_pass_with_source_log",
    Decision.NEEDS_SUBSTANTIATION: "approved_claims_library_with_substantiation_ref",
    Decision.NEEDS_OPERATOR_VERIFICATION: "operator_identity_bound_affirmation",
    Decision.BLOCK: "hard_block_edit_and_rerun_only",
}


# --------------------------------------------------------------------------- #
# Optional YAML override loader (config-as-data). Silently no-ops without PyYAML
# so the module stays importable/testable with only stdlib.
# --------------------------------------------------------------------------- #
_DATA_DIR = Path(__file__).resolve().parent / "data"


def load_yaml_overrides() -> dict[str, Any]:
    """Load ``data/ruleset_<version>.yaml`` if present + PyYAML installed, else {}."""
    try:
        import yaml  # type: ignore
    except Exception:
        return {}
    path = _DATA_DIR / "ruleset_2026_07.yaml"
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def category_rule(category: str | None) -> dict[str, Any]:
    """Return the category rule; unknown/None -> a synthesized restricted rule."""
    if category and category.lower() in CATEGORY_RULES:
        return CATEGORY_RULES[category.lower()]
    # Fail safe: unknown/unmapped category is treated as restricted & unknown.
    return {
        "id": "TT-CAT-UNKNOWN",
        "restricted": True,
        "known": False,
        "embellishment_profile": "none",
        "ban": ["*"],
        "efficacy_hard_block": True,
    }


def is_ruleset_active(version: str | None) -> bool:
    return bool(version) and version in ACTIVE_RULESET_VERSIONS
