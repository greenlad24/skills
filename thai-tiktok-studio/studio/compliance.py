"""Local claim check over every Thai text in a plan (no AI, instant)."""

from __future__ import annotations

import json

from .config import FRAMEWORKS_DIR


def _lists():
    data = json.loads((FRAMEWORKS_DIR / "compliance_th.json").read_text("utf-8"))
    return data.get("hard", []), data.get("soft", [])


def _texts(video: dict):
    yield "script", video.get("full_script_th", "")
    yield "post caption", video.get("post_caption_th", "")
    for i, b in enumerate(video.get("timeline", []), 1):
        yield f"beat {i} voice", b.get("vo_th", "")
        for o in b.get("overlays", []):
            yield f"beat {i} {o['type']}", " ".join([o.get("text", ""), o.get("sub_text", "")] + o.get("items", []))
    for s in video.get("shots", []):
        yield f"shot {s['id']} dialogue", s.get("dialogue_th", "")


STORE_WORDS = ("ห้าง", "หน้าร้าน", "ร้าน", "ข้างนอก", "ที่อื่น", "ราคาเต็ม", "ราคาปกติ", "ช็อป", "เคาน์เตอร์", "ซุปเปอร์")
SELLING_CUES = ("เหลือ", "แค่", "เพียง", "ในคลิป", "ในตะกร้า", "ตอนนี้", "ลด")


def _is_store_anchor(text: str, pos: int, where: str) -> bool:
    """A spoken amount is OK only when it's what a store charges (not the selling price)."""
    if "caption" in where or "post" in where or where.startswith("beat") and "voice" not in where:
        return False                      # on-screen text: never
    before = text[max(0, pos - 30):pos]
    near = text[max(0, pos - 12):pos]
    return any(w in before for w in STORE_WORDS) and not any(c in near for c in SELLING_CUES)


def check_plan(plan: dict) -> dict:
    """→ {video_id: [{level, word, where}]}"""
    from .plan_schema import PRICE_RE
    hard, soft = _lists()
    out = {}
    for v in plan.get("videos", []):
        found = []
        for where, text in _texts(v):
            for m in PRICE_RE.finditer(text or ""):   # owner's rule: only a store-price anchor may be spoken
                if not _is_store_anchor(text, m.start(), where):
                    found.append({"level": "hard", "word": f"price {m.group(0).strip()}", "where": where})
            for level, words in (("hard", hard), ("soft", soft)):
                for w in words:
                    if w and w in (text or ""):
                        found.append({"level": level, "word": w, "where": where})
        out[v["id"]] = found
    return out
