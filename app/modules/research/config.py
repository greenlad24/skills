"""Module-local knobs for the research pipeline (thresholds, weights, taxonomy).

These are tuning constants, not secrets — secrets/provider selection live in
`app.core.config.settings`. Kept here so the rest of the module reads one place.
`USE_REAL_ML` gates the heavy Whisper/OCR/scene-detect/yt-dlp code paths; when it is
False (the default, and always in DRY_RUN) the stub media tools are used — no model
downloads, no network, $0.
"""

from __future__ import annotations

from app.core.config import settings

# --------------------------------------------------------------------------- #
# Media / storage layout
# --------------------------------------------------------------------------- #
MEDIA_ROOT = settings.MEDIA_ROOT
PRODUCT_IMAGE_DIR = "products"          # → {MEDIA_ROOT}/products/{job_id}/
SWIPE_VIDEO_DIR = "swipe"               # → {MEDIA_ROOT}/swipe/{tiktok_id}/


def use_real_ml() -> bool:
    """Heavy ML (Whisper/OCR/PySceneDetect/yt-dlp) runs only when explicitly enabled
    AND we're not in DRY_RUN. Default: stubbed. Guarded so CI never blocks on model
    downloads."""
    return (not settings.DRY_RUN) and bool(getattr(settings, "RESEARCH_USE_REAL_ML", False))


# --------------------------------------------------------------------------- #
# 2A — Product research
# --------------------------------------------------------------------------- #
DEFAULT_CURRENCY = "THB"

# Minimum short-side pixels for a downloaded image to be kept (drop icons/badges).
MIN_IMAGE_SHORT_SIDE = 300
NORMALIZED_IMAGE_WIDTH = 1080
IMAGE_DOWNLOAD_CONCURRENCY = 4
IMAGE_DOWNLOAD_TIMEOUT_S = 15
IMAGE_DOWNLOAD_RETRIES = 2

# Fixed dotted product taxonomy (category selects the swipe-library niche).
CATEGORY_TAXONOMY = [
    "beauty.skincare",
    "beauty.makeup",
    "beauty.haircare",
    "fashion.apparel",
    "fashion.accessories",
    "home.kitchen",
    "home.living",
    "electronics.accessories",
    "electronics.gadgets",
    "supplements",
    "mom_baby",
    "pet",
    "food_beverage",
    "misc",
]

# Keyword fast-path for category classification (avoid an LLM call when obvious).
# Maps a lowercased keyword (Thai or English) → dotted category.
CATEGORY_KEYWORDS = {
    "serum": "beauty.skincare",
    "moisturizer": "beauty.skincare",
    "sunscreen": "beauty.skincare",
    "กันแดด": "beauty.skincare",
    "เซรั่ม": "beauty.skincare",
    "ครีม": "beauty.skincare",
    "lipstick": "beauty.makeup",
    "ลิป": "beauty.makeup",
    "foundation": "beauty.makeup",
    "shampoo": "beauty.haircare",
    "แชมพู": "beauty.haircare",
    "dress": "fashion.apparel",
    "เสื้อ": "fashion.apparel",
    "กางเกง": "fashion.apparel",
    "blender": "home.kitchen",
    "เครื่องปั่น": "home.kitchen",
    "earbuds": "electronics.accessories",
    "หูฟัง": "electronics.accessories",
    "charger": "electronics.accessories",
    "vitamin": "supplements",
    "วิตามิน": "supplements",
    "collagen": "supplements",
    "คอลลาเจน": "supplements",
    "diaper": "mom_baby",
    "ผ้าอ้อม": "mom_baby",
}

# Tier thresholds as price percentile *within category* (see §2A.5). Because a full
# category price distribution isn't available at single-product time, we approximate
# with per-category absolute price bands (THB) tuned to be overridden by the language
# cue nudges below.
TIER_PRICE_BANDS_THB = {
    # category: (budget_max, mid_max)  — above mid_max => premium
    "beauty.skincare": (300, 900),
    "beauty.makeup": (250, 700),
    "beauty.haircare": (250, 700),
    "fashion.apparel": (400, 1200),
    "fashion.accessories": (300, 1000),
    "home.kitchen": (800, 3000),
    "home.living": (700, 2500),
    "electronics.accessories": (500, 1500),
    "electronics.gadgets": (1500, 6000),
    "supplements": (400, 1200),
    "mom_baby": (300, 1000),
    "pet": (300, 1000),
    "food_beverage": (200, 700),
    "misc": (400, 1500),
}
TIER_BAND_DEFAULT = (400, 1500)

# Language cues that nudge tier up / down.
TIER_CUES_UP = ["ของแท้", "พรีเมียม", "luxury", "premium", "hi-end", "hi end", "แท้100"]
TIER_CUES_DOWN = ["ราคาส่ง", "ถูก", "ราคาถูก", "wholesale", "cheap", "โปรโมชั่น"]

# voice_gender category prior (soft; §2A.6 signal 2). Overridden by swipe evidence.
CATEGORY_GENDER_PRIOR = {
    "beauty.skincare": "female",
    "beauty.makeup": "female",
    "beauty.haircare": "female",
    "mom_baby": "female",
    "supplements": "neutral",
    "electronics.gadgets": "male",
    "electronics.accessories": "male",
}

# Explicit gender-target cues (§2A.6 signal 1).
GENDER_CUES_MALE = ["for men", "men's", "mens", "สำหรับผู้ชาย", "ผู้ชาย", "grooming"]
GENDER_CUES_FEMALE = ["for women", "women's", "สำหรับผู้หญิง", "ผู้หญิง"]

# _too_sparse: a product is too sparse if it has no title OR no usable image.
PRODUCT_CACHE_TTL_DAYS = 7

# --------------------------------------------------------------------------- #
# 2B — Swipe engine
# --------------------------------------------------------------------------- #
# proxy_score weights (§2B.1).
PROXY_WEIGHTS = {
    "views": 0.20,
    "likes": 0.35,
    "shares": 0.20,
    "comments": 0.15,
    "saves": 0.10,
}
PROXY_RECENCY_HALFLIFE_DAYS = 45.0

# Ingest filters (§2B.1).
SWIPE_MIN_DURATION_S = 8.0
SWIPE_MAX_DURATION_S = 90.0
SWIPE_LANGUAGE = "th"

DEFAULT_TOP_K = 30
MIN_SUPPORT = 2                 # a formula/hook needs ≥ this many source videos

# Nightly refresh budget caps (§2B.10) — halt & report when hit.
REFRESH_BUDGET = {
    "apify_runs": 20,
    "downloads": 60,
    "ocr_frames": 4000,
    "llm_calls": 40,
    "usd": 3.0,
}
SOURCE_REFRESH_WINDOW_HOURS = 20   # skip re-scraping a source scraped within window

# OCR sampling.
OCR_SAMPLE_FPS = 2.0

# --------------------------------------------------------------------------- #
# 2B.8 — IP guardrail
# --------------------------------------------------------------------------- #
VERBATIM_NGRAM_N = 7               # ≥7-gram overlap against source ⇒ block/regenerate
VERBATIM_MAX_COSINE = 0.86        # sentence-level token cosine ceiling
SELF_DUP_JACCARD_MAX = 0.72       # reject new script too similar to operator's last M
SELF_DUP_HISTORY = 5              # M: rolling window of recent operator scripts

# LLM models used for cheap classification / extraction.
LLM_CLASSIFY_MODEL = "claude-haiku-4-5"
LLM_EXTRACT_MODEL = "claude-sonnet-5"
