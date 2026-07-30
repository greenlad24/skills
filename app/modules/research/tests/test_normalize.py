from __future__ import annotations

from app.modules.research.product import normalize as nz
from app.modules.research.schemas import NormalizedProduct


def test_category_fast_path():
    assert nz.category_fast_path("Vitamin C Serum", [], None) == "beauty.skincare"
    assert nz.category_fast_path("เครื่องปั่นน้ำผลไม้", [], None) == "home.kitchen"
    assert nz.category_fast_path("mystery gizmo", [], None) is None


def test_tier_within_category_and_cues():
    # ฿1500 lipstick (beauty.makeup band 250/700) → premium
    tier, band = nz.derive_tier(1500, "beauty.makeup", "lipstick", [])
    assert tier == "premium"
    # ฿1500 blender (home.kitchen band 800/3000) → mid
    tier2, _ = nz.derive_tier(1500, "home.kitchen", "blender", [])
    assert tier2 == "mid"
    # cue nudges down
    tier3, _ = nz.derive_tier(1500, "beauty.makeup", "lipstick ราคาส่ง", [])
    assert tier3 == "mid"
    assert band  # audit label present


def test_voice_gender_cascade():
    # explicit target wins
    g, c = nz.derive_voice_gender("men's grooming kit", [], {}, "beauty.skincare", None)
    assert g == "male" and c >= 0.9
    # category prior when no explicit
    g2, _ = nz.derive_voice_gender("hydrating serum", [], {}, "beauty.skincare", None)
    assert g2 == "female"
    # swipe evidence overrides prior when confident
    g3, c3 = nz.derive_voice_gender(
        "hydrating serum", [], {}, "beauty.skincare", {"male": 8, "female": 1}
    )
    assert g3 == "male" and c3 > 0.6
    # neutral fallback
    g4, _ = nz.derive_voice_gender("mystery", [], {}, "supplements", None)
    assert g4 == "neutral"


def test_too_sparse():
    assert nz.too_sparse(NormalizedProduct(title=None, images=["/x.jpg"])) is True
    assert nz.too_sparse(NormalizedProduct(title="ok", images=[])) is True
    assert nz.too_sparse(NormalizedProduct(title="ok", images=["/x.jpg"])) is False


def test_enrich_fills_fields():
    n = NormalizedProduct(title="Vitamin C Serum", price=250.0, images=["/x.jpg"])
    nz.enrich(n)
    assert n.category == "beauty.skincare"
    assert n.tier in ("budget", "mid", "premium")
    assert n.voice_gender in ("female", "male", "neutral")
