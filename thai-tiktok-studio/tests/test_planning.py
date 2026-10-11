import json

from fixtures import sample_plan

from studio import compliance, exports, prompts, scrape
from studio.plan_schema import PLAN_SCHEMA, canon_shot_id, normalize_plan, plan_problems


def test_canon_shot_id_variants():
    for raw in ("V1-S01", "v1s1", "V1_S1", "v1 - s01", "clip V1-S1 take2"):
        assert canon_shot_id(raw) == "V1-S01"
    assert canon_shot_id("V12-S3") == "V12-S03"


def test_normalize_fills_and_clamps():
    raw = {"videos": [{"id": "video 3", "shots": [{"id": "v3 s1", "shot_size": "weird"}],
                       "timeline": [{"shot_id": "nope", "duration": 99, "speed": 9, "effect": "explode",
                                     "captions": ["ก", {"text": "ข", "highlight": ["zz"]}],
                                     "overlays": [{"type": "hook_title", "text": "x", "at": -3}, {"type": "bogus"}],
                                     "sfx": [{"type": "pop", "at": 1}, {"type": "laser"}]}]}]}
    plan = normalize_plan(raw)
    v = plan["videos"][0]
    assert v["id"] == "V3" and v["shots"][0]["id"] == "V3-S01" and v["shots"][0]["shot_size"] == "medium"
    b = v["timeline"][0]
    assert b["shot_id"] == "V3-S01"            # unknown shot → first shot
    assert b["duration"] == 15 and b["speed"] == 2.0 and b["effect"] == "none"
    assert [c["text"] for c in b["captions"]] == ["ก", "ข"] and b["captions"][1]["highlight"] == []
    assert len(b["overlays"]) == 1 and b["overlays"][0]["at"] == 0
    assert [s["type"] for s in b["sfx"]] == ["pop"]
    assert set(plan["research"]) >= {"product_name", "sources"}


def test_sample_plan_normalizes_and_ranks():
    plan = normalize_plan(sample_plan())
    assert [v["id"] for v in plan["videos"]] == ["V1", "V2"]
    assert plan["videos"][0]["score"]["total"] > 0
    assert isinstance(plan_problems(plan), list)


def test_schema_is_strict_everywhere():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(PLAN_SCHEMA)


def test_compliance_flags_hard_claims():
    plan = normalize_plan(sample_plan())
    plan["videos"][0]["timeline"][0]["vo_th"] = "รักษาสิวหายขาด 100%"
    flags = compliance.check_plan(plan)["V1"]
    words = {f["word"] for f in flags if f["level"] == "hard"}
    assert {"รักษา", "หายขาด", "100%"} <= words


def test_prompts_embed_framework_and_schema():
    g = {"input_text": "ที่นอน", "url": "", "page": {}, "search_results": [], "user_images": []}
    sp = prompts.system_prompt(5)
    assert "price_shock" in sp and "cta_basket" in sp and "Produce exactly 5 videos" in sp
    mp = prompts.manual_prompt(g, 5)
    assert json.dumps(PLAN_SCHEMA, ensure_ascii=False)[:200] in mp


def test_exports(tmp_path):
    plan = normalize_plan(sample_plan())
    exports.write_all(tmp_path, plan, {"name": "x"})
    html = (tmp_path / "filming_pack.html").read_text("utf-8")
    assert "V1-S01" in html and "แพ็กถ่ายทำ" in html
    assert "V2" in (tmp_path / "scripts.txt").read_text("utf-8")


def test_scrape_parses_meta_and_jsonld(monkeypatch):
    html = """<html><head><title>T</title><meta property="og:title" content="ที่นอน Solomon">
    <meta property="og:image" content="/img/a.jpg">
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Solomon",
     "offers":{"price":"2990","priceCurrency":"THB"},"aggregateRating":{"ratingValue":"4.9","reviewCount":"120"}}</script>
    </head><body>นุ่มเด้ง ไม่ปวดหลัง</body></html>"""

    class R:
        status_code = 200
        url = "https://shop.example.com/p/1"
        headers = {"content-type": "text/html"}
        text = html

    monkeypatch.setattr(scrape, "_get", lambda url, timeout=15: R())
    info = scrape.scrape_url("https://shop.example.com/p/1")
    assert info["ok"] and info["title"] == "ที่นอน Solomon" and info["price"] == "2990"
    assert info["currency"] == "THB" and info["rating"].startswith("4.9")
    assert info["images"] == ["https://shop.example.com/img/a.jpg"]
    assert scrape.find_url("ดูอันนี้ https://x.co/a?b=1, ค่ะ") == "https://x.co/a?b=1"


def test_inspiration_csv_to_examples():
    from studio import inspiration
    csv_text = ("Link,Trasnscription,Caption,Plays,Video Duration,อะไรทำให้ฉันชอบวิดีโอนี้,เกิดอะไรขึ้นบนหน้าจอ?\n"
                "a,ทนนอนปวดหลังมาหลายปี,cap,\"13,200,000\",35 seconds,ราคาชัด,Wide shot~close up\n"
                "b,English only,cap,999999999,10 seconds,,\n"
                "c,ทำไมถูกจัง,cap,4600000,47 seconds,จริงใจ,wide shot\n")
    md, n = inspiration.build_examples(csv_text)
    assert n == 2
    assert md.index("13,200,000") < md.index("4,600,000") and "ราคาชัด" in md and "English only" not in md


def test_prices_never_reach_graphics():
    from studio.plan_schema import normalize_overlay, strip_prices
    base = {"sub_text": "", "items": [], "emoji": "", "at": 0, "dur": 2, "position": "auto", "color": "auto",
            "target_x": 0.5, "target_y": 0.5}
    assert normalize_overlay({**base, "type": "price_tag", "text": "199"}) is None
    assert normalize_overlay({**base, "type": "keyword_pop", "text": "฿2,990"}) is None
    o = normalize_overlay({**base, "type": "hook_title", "text": "ในห้างเป็นหมื่น แต่ในคลิปนี้เหลือ 2,990 บาท"})
    assert "2,990" not in o["text"] and o["text"].startswith("ในห้างเป็นหมื่น")
    o = normalize_overlay({**base, "type": "checklist", "text": "", "items": ["นุ่มเด้ง", "ราคา 990", "ส่งฟรี"]})
    assert o["items"] == ["นุ่มเด้ง", "ส่งฟรี"]
    assert normalize_overlay({**base, "type": "discount_badge", "text": "ลด 50%"})["text"] == "ลด 50%"
    assert strip_prices("ขายแล้ว 10k+") == "ขายแล้ว 10k+" and strip_prices("1,290.-") == ""
