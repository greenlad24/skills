"""Shared enums, roles and tunables for the generation module (§03).

Kept in one place so the load-bearing decisions (hybrid role map, reroll budget,
QA threshold, cost estimates) are visible and testable rather than scattered.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Scene roles + asset types (§3A.4 schema enums)
# --------------------------------------------------------------------------- #
ROLE_HOOK = "HOOK"
ROLE_DEMO = "DEMO"
ROLE_PROOF = "PROOF"
ROLE_CTA = "CTA"
SCENE_ROLES = frozenset({ROLE_HOOK, ROLE_DEMO, ROLE_PROOF, ROLE_CTA})

ASSET_AVATAR = "AVATAR"
ASSET_BROLL = "BROLL"
ASSET_TYPES = frozenset({ASSET_AVATAR, ASSET_BROLL})

# FACELESS workflow: every scene is BROLL (generated product footage) with the Thai
# voiceover played over it — no talking-head avatar. The avatar lane in pipeline.py
# stays in the code but is never exercised because no scene is ASSET_AVATAR.
ALLOWED_ROLES_FOR_ASSET: dict[str, frozenset[str]] = {
    ASSET_AVATAR: frozenset(),                                  # dormant (faceless)
    ASSET_BROLL: frozenset({ROLE_HOOK, ROLE_DEMO, ROLE_PROOF, ROLE_CTA}),
}
# Reverse map: which asset type a role must use — all BROLL for faceless.
ASSET_FOR_ROLE: dict[str, str] = {
    ROLE_HOOK: ASSET_BROLL,
    ROLE_CTA: ASSET_BROLL,
    ROLE_DEMO: ASSET_BROLL,
    ROLE_PROOF: ASSET_BROLL,
}

# --------------------------------------------------------------------------- #
# MediaAsset roles (models.MediaAsset.role — free string, these are the values
# this module writes)
# --------------------------------------------------------------------------- #
MEDIA_HERO_IMAGE = "hero_image"
MEDIA_BROLL = "broll"
MEDIA_AVATAR_CLIP = "avatar_clip"
MEDIA_TTS_AUDIO = "tts_audio"      # per-avatar-scene lip-sync VO
MEDIA_VO_TRACK = "vo_track"        # the clean, full Thai VO track for §04 editing

# --------------------------------------------------------------------------- #
# GenAttempt / CostLedgerEntry `kind` values (§3D.7)
# --------------------------------------------------------------------------- #
KIND_AVATAR = "AVATAR"
KIND_HERO_IMAGE = "HERO_IMAGE"
KIND_I2V = "I2V"
KIND_TTS = "TTS"
KIND_LLM = "LLM"

# --------------------------------------------------------------------------- #
# Provider / render tunables
# --------------------------------------------------------------------------- #
ASPECT_VERTICAL = "9:16"

# Total finished-video length bounds (seconds). TikTok deliverables are capped at
# 30s per the operator; the script stage targets and validates against this.
MIN_TOTAL_DURATION_S = 8
MAX_TOTAL_DURATION_S = 30

# §3D.5 product-consistency QA gate
QA_SIMILARITY_THRESHOLD = 0.85
MAX_REROLLS = 3                     # per scene (§3D.5)
REROLL_BUDGET_RATE_LOW = 0.15       # expected 15–30% reroll rate
REROLL_BUDGET_RATE_HIGH = 0.30
REROLL_ALERT_RATE = 0.35            # provider regression signal

# §3D.7 per-video cost alert target (soft; budget guard is the hard stop)
COST_TARGET_USD = 3.00

# Pre-spend estimates used by the budget guard *before* a provider reveals its
# actual cost. Actuals from ProviderResult.cost_usd are always reconciled after.
ESTIMATED_COST_USD: dict[str, float] = {
    KIND_AVATAR: 0.35,
    KIND_HERO_IMAGE: 0.05,
    KIND_I2V: 2.50,
    KIND_TTS: 0.06,
    KIND_LLM: 0.02,
}

# §3A.5 default models (config can override the provider; these label the call)
DEFAULT_LLM_MODEL = "claude-sonnet-5"
DEFAULT_I2V_MODEL = "ltx-2.5"
DEFAULT_TTS_MODEL = "google-th-TH-Neural2"

# Poll fallback (§3D.4) — fakes complete immediately; a real LTX-on-Modal render can
# take minutes (cold start + generation), so the window must be generous. At the 5s
# cadence set in service.run_generation that's ~10 min per clip — the loop returns the
# instant a render reports ready, so this only bounds how long we wait, never the norm.
POLL_MAX_ATTEMPTS = 120
POLL_INTERVAL_SEC = 5.0

# Consent types (§3C.2)
CONSENT_AVATAR_LIKENESS = "avatar_likeness"
CONSENT_VOICE_CLONE = "voice_clone"
