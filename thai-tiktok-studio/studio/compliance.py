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


def check_plan(plan: dict) -> dict:
    """→ {video_id: [{level, word, where}]}"""
    hard, soft = _lists()
    out = {}
    for v in plan.get("videos", []):
        found = []
        for where, text in _texts(v):
            for level, words in (("hard", hard), ("soft", soft)):
                for w in words:
                    if w and w in (text or ""):
                        found.append({"level": level, "word": w, "where": where})
        out[v["id"]] = found
    return out
