"""The edit plan: the single contract between Tool 1 (planner) and Tool 2 (editor).

Tool 1 asks an LLM ONCE to fill this schema. Tool 2 renders it deterministically —
no AI calls — so editing is free and repeatable. Everything the editor needs (cut
points, durations, captions, motion graphics, sound effects) lives in the plan.
"""

from __future__ import annotations

import copy
import re

# ---------------------------------------------------------------------------
# Vocabularies (kept in sync with frameworks/*.json and editor/elements.py)
# ---------------------------------------------------------------------------
FORMATS = [
    "problem_solution", "price_shock", "demo_proof", "unboxing_first_impression",
    "before_after", "storytime_pov", "comparison", "reasons_list",
    "reply_to_comment", "must_have_life_hack", "honest_review", "asmr_satisfying",
]
AUDIO_MODES = ["voiceover", "talking", "music_only"]
SHOT_SIZES = [
    "extreme_close_up", "close_up", "medium", "wide", "extreme_wide",
    "pov_hands", "overhead", "selfie_talking", "screen_record", "product_photo",
]
BEAT_ROLES = ["hook", "problem", "demo", "proof", "feature", "price", "offer", "cta", "other"]
TRIMS = ["start", "middle", "end"]
EFFECTS = ["none", "punch_in", "shake", "flash", "slow_zoom", "punch_shake"]
OVERLAY_TYPES = [
    "hook_title", "keyword_pop", "price_tag", "discount_badge", "cta_basket",
    "arrow", "circle_highlight", "checklist", "label", "trust_badges",
    "stars_rating", "comment_reply", "emoji_sticker", "spec_card", "number_badge",
    "urgency_banner", "before_after_labels", "vs_split", "reaction_text",
    "speech_bubble", "lower_third",
]
POSITIONS = [
    "top", "upper", "center", "lower", "bottom",
    "top_left", "top_right", "center_left", "center_right", "lower_left", "lower_right",
    "target",
]
COLORS = ["auto", "yellow", "red", "white", "black", "pink", "green", "orange", "blue"]
SFX = ["pop", "whoosh", "ding", "cash", "click", "boom", "sparkle", "tick", "shutter", "riser", "boing"]
CAPTION_STYLES = ["stroke_white", "box_black", "box_yellow", "stroke_yellow"]
FONTS = ["kanit", "prompt", "mitr", "chakra", "mali", "itim"]
THEMES = ["sale_red_yellow", "hot_orange_gold", "trust_green", "beauty_pink", "clean_black_white"]
MUSIC_MOODS = ["upbeat", "chill", "dramatic", "cute", "none"]


def _s(desc: str = "") -> dict:
    return {"type": "string", "description": desc} if desc else {"type": "string"}


def _enum(vals, desc: str = "") -> dict:
    d = {"type": "string", "enum": list(vals)}
    if desc:
        d["description"] = desc
    return d


def _num(desc: str = "") -> dict:
    return {"type": "number", "description": desc} if desc else {"type": "number"}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _arr(items: dict, desc: str = "") -> dict:
    d = {"type": "array", "items": items}
    if desc:
        d["description"] = desc
    return d


OVERLAY = _obj({
    "type": _enum(OVERLAY_TYPES),
    "text": _s("Main Thai text (short!). For price_tag: the NEW price digits only e.g. '199'."),
    "sub_text": _s("Secondary text: old price for price_tag, @username for comment_reply, '' if unused."),
    "items": _arr(_s(), "List items for checklist/trust_badges/spec_card ('label: value'), else []."),
    "emoji": _s("One emoji for emoji_sticker/reaction_text/cta, else ''."),
    "at": _num("Seconds after the beat starts when it appears."),
    "dur": _num("Seconds it stays on screen."),
    "position": _enum(POSITIONS),
    "color": _enum(COLORS),
    "target_x": _num("0-1 horizontal point an arrow/circle points at (0.5 if unused)."),
    "target_y": _num("0-1 vertical point an arrow/circle points at (0.5 if unused)."),
})

CAPTION = _obj({
    "text": _s("One caption chunk: max ~18 Thai characters, a natural phrase, never split a word."),
    "highlight": _arr(_s(), "Exact substrings of text to color as keywords (0-2)."),
})

SFX_CUE = _obj({"type": _enum(SFX), "at": _num("Seconds after beat start.")})

BEAT = _obj({
    "shot_id": _s("Which shot's footage to use, e.g. 'V1-S02'. Shots may be reused."),
    "role": _enum(BEAT_ROLES),
    "duration": _num("Target seconds on screen (0.6-8). In talking mode the clip's speech length wins."),
    "trim": _enum(TRIMS, "Which part of the clip to use when it is longer than needed."),
    "speed": _num("Playback speed 0.5-2.0 (1 = normal)."),
    "effect": _enum(EFFECTS, "Camera effect at the start of this beat."),
    "vo_th": _s("Exactly what is SPOKEN during this beat in Thai (voice-over or on-camera line). '' if silent."),
    "captions": _arr(CAPTION, "vo_th split into on-screen chunks in order (empty if silent)."),
    "overlays": _arr(OVERLAY),
    "sfx": _arr(SFX_CUE),
})

SHOT = _obj({
    "id": _s("'V<n>-S<nn>' e.g. 'V1-S01'."),
    "shot_size": _enum(SHOT_SIZES),
    "what_to_film_th": _s("Thai: exactly what to film (subject, action, props)."),
    "how_to_film_th": _s("Thai: angle, camera movement, lighting, framing tips."),
    "dialogue_th": _s("Thai line spoken on camera in this shot ('' for B-roll)."),
    "min_seconds": _num("Minimum seconds to record (record extra)."),
    "audio": _enum(["sync", "mute"], "'sync' keeps the clip's own sound (talking), 'mute' for B-roll."),
})

SCORE = _obj({
    "hook_strength": _num("1-10"),
    "pain_or_desire": _num("1-10"),
    "proof_demo": _num("1-10"),
    "offer_clarity": _num("1-10"),
    "trend_fit": _num("1-10"),
    "filmability": _num("1-10"),
    "compliance_safety": _num("1-10"),
    "total": _num("Average of the above x10 (0-100)."),
})

VIDEO = _obj({
    "id": _s("'V1'..'V5'"),
    "rank": _num("1 = most likely to go viral."),
    "title_th": _s("Internal Thai title."),
    "format": _enum(FORMATS),
    "hook_type": _s("Hook archetype used (curiosity, pain, price, social proof...)."),
    "angle_en": _s("One-line English summary of the angle, for the owner."),
    "why_it_works_en": _s("2-3 sentences in English referencing the research/framework."),
    "audio_mode": _enum(AUDIO_MODES),
    "target_length_sec": _num(),
    "font": _enum(FONTS),
    "theme": _enum(THEMES),
    "caption_style": _enum(CAPTION_STYLES),
    "music_mood": _enum(MUSIC_MOODS),
    "progress_bar": {"type": "boolean"},
    "full_script_th": _s("The complete Thai script as one readable block (what is said, in order)."),
    "post_caption_th": _s("TikTok post caption in Thai with a soft CTA."),
    "hashtags": _arr(_s()),
    "score": SCORE,
    "shots": _arr(SHOT),
    "timeline": _arr(BEAT),
})

RESEARCH = _obj({
    "product_name": _s(), "brand": _s(), "category": _s(),
    "price_thb": _s("Current/typical price in THB, '' if unknown."),
    "original_price_thb": _s("Pre-discount price if any, else ''."),
    "key_features": _arr(_s()), "pain_points": _arr(_s()), "target_audience": _s(),
    "objections": _arr(_s()), "proof_points": _arr(_s()),
    "niche_trends": _arr(_s(), "What is currently working for this niche on Thai TikTok."),
    "competitor_hooks": _arr(_s(), "Real hooks/angles competitors use."),
    "compliance_notes": _arr(_s(), "Claims to avoid for this category (อย./TikTok Shop rules)."),
    "sources": _arr(_s(), "URLs used."),
})

PLAN_SCHEMA = _obj({
    "research": RESEARCH,
    "videos": _arr(VIDEO),
})


# ---------------------------------------------------------------------------
# Normalization: make any LLM output safe for the renderer.
# ---------------------------------------------------------------------------
def _clamp(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    return max(lo, min(hi, v))


def _pick(v, allowed, default):
    return v if v in allowed else default


def _str(v) -> str:
    return v.strip() if isinstance(v, str) else ("" if v is None else str(v))


def _strs(v) -> list:
    return [_str(x) for x in v if _str(x)] if isinstance(v, list) else []


SHOT_ID_RE = re.compile(r"V(\d+)\s*[-_ ]?\s*S(\d+)", re.I)


def canon_shot_id(s: str) -> str:
    m = SHOT_ID_RE.search(s or "")
    return f"V{int(m.group(1))}-S{int(m.group(2)):02d}" if m else _str(s)


def normalize_overlay(o: dict) -> dict | None:
    if not isinstance(o, dict) or o.get("type") not in OVERLAY_TYPES:
        return None
    return {
        "type": o["type"],
        "text": _str(o.get("text")),
        "sub_text": _str(o.get("sub_text")),
        "items": _strs(o.get("items"))[:6],
        "emoji": _str(o.get("emoji")),
        "at": _clamp(o.get("at"), 0, 30, 0.0),
        "dur": _clamp(o.get("dur"), 0.3, 60, 2.0),
        "position": _pick(o.get("position"), POSITIONS, "auto"),
        "color": _pick(o.get("color"), COLORS, "auto"),
        "target_x": _clamp(o.get("target_x"), 0, 1, 0.5),
        "target_y": _clamp(o.get("target_y"), 0, 1, 0.5),
    }


def normalize_beat(b: dict, vid: str) -> dict:
    caps = []
    for c in b.get("captions") or []:
        if isinstance(c, str):
            c = {"text": c, "highlight": []}
        if isinstance(c, dict) and _str(c.get("text")):
            t = _str(c["text"])
            caps.append({"text": t, "highlight": [h for h in _strs(c.get("highlight")) if h in t][:3]})
    return {
        "shot_id": canon_shot_id(_str(b.get("shot_id"))),
        "role": _pick(b.get("role"), BEAT_ROLES, "other"),
        "duration": _clamp(b.get("duration"), 0.4, 15, 2.5),
        "trim": _pick(b.get("trim"), TRIMS, "start"),
        "speed": _clamp(b.get("speed"), 0.5, 2.0, 1.0),
        "effect": _pick(b.get("effect"), EFFECTS, "none"),
        "vo_th": _str(b.get("vo_th")),
        "captions": caps,
        "overlays": [x for x in (normalize_overlay(o) for o in b.get("overlays") or []) if x],
        "sfx": [
            {"type": s["type"], "at": _clamp(s.get("at"), 0, 30, 0.0)}
            for s in (b.get("sfx") or []) if isinstance(s, dict) and s.get("type") in SFX
        ],
    }


def normalize_video(v: dict, idx: int) -> dict:
    vid = _str(v.get("id")) or f"V{idx + 1}"
    m = re.search(r"\d+", vid)
    vid = f"V{int(m.group(0))}" if m else f"V{idx + 1}"
    shots = []
    seen = set()
    for s in v.get("shots") or []:
        if not isinstance(s, dict):
            continue
        sid = canon_shot_id(_str(s.get("id")))
        if not SHOT_ID_RE.fullmatch(sid.replace("-", "")) and not SHOT_ID_RE.search(sid):
            sid = f"{vid}-S{len(shots) + 1:02d}"
        if sid in seen:
            continue
        seen.add(sid)
        shots.append({
            "id": sid,
            "shot_size": _pick(s.get("shot_size"), SHOT_SIZES, "medium"),
            "what_to_film_th": _str(s.get("what_to_film_th")),
            "how_to_film_th": _str(s.get("how_to_film_th")),
            "dialogue_th": _str(s.get("dialogue_th")),
            "min_seconds": _clamp(s.get("min_seconds"), 1, 60, 4),
            "audio": _pick(s.get("audio"), ["sync", "mute"], "mute"),
        })
    timeline = [normalize_beat(b, vid) for b in (v.get("timeline") or []) if isinstance(b, dict)]
    shot_ids = {s["id"] for s in shots}
    for b in timeline:  # a beat pointing at an unknown shot → nearest valid shot
        if b["shot_id"] not in shot_ids and shots:
            b["shot_id"] = shots[0]["id"]
    sc = v.get("score") if isinstance(v.get("score"), dict) else {}
    keys = ["hook_strength", "pain_or_desire", "proof_demo", "offer_clarity", "trend_fit",
            "filmability", "compliance_safety"]
    score = {k: _clamp(sc.get(k), 0, 10, 5) for k in keys}
    score["total"] = round(sum(score[k] for k in keys) / len(keys) * 10, 1)
    return {
        "id": vid,
        "rank": int(_clamp(v.get("rank"), 1, 99, idx + 1)),
        "title_th": _str(v.get("title_th")) or vid,
        "format": _pick(v.get("format"), FORMATS, "problem_solution"),
        "hook_type": _str(v.get("hook_type")),
        "angle_en": _str(v.get("angle_en")),
        "why_it_works_en": _str(v.get("why_it_works_en")),
        "audio_mode": _pick(v.get("audio_mode"), AUDIO_MODES, "voiceover"),
        "target_length_sec": _clamp(v.get("target_length_sec"), 8, 120, 30),
        "font": _pick(v.get("font"), FONTS, "kanit"),
        "theme": _pick(v.get("theme"), THEMES, "sale_red_yellow"),
        "caption_style": _pick(v.get("caption_style"), CAPTION_STYLES, "stroke_white"),
        "music_mood": _pick(v.get("music_mood"), MUSIC_MOODS, "upbeat"),
        "progress_bar": bool(v.get("progress_bar", False)),
        "full_script_th": _str(v.get("full_script_th")),
        "post_caption_th": _str(v.get("post_caption_th")),
        "hashtags": [h if h.startswith("#") else "#" + h for h in _strs(v.get("hashtags"))][:12],
        "score": score,
        "shots": shots,
        "timeline": timeline,
    }


def normalize_plan(plan: dict) -> dict:
    """Return a renderer-safe copy of an LLM plan (never raises on bad fields)."""
    if not isinstance(plan, dict):
        raise ValueError("Plan must be a JSON object")
    plan = copy.deepcopy(plan)
    r = plan.get("research") if isinstance(plan.get("research"), dict) else {}
    research = {}
    for k, spec in RESEARCH["properties"].items():
        research[k] = _strs(r.get(k)) if spec["type"] == "array" else _str(r.get(k))
    videos = [normalize_video(v, i) for i, v in enumerate(plan.get("videos") or []) if isinstance(v, dict)]
    if not videos:
        raise ValueError("Plan has no videos")
    # unique ids
    used = set()
    for i, v in enumerate(videos):
        if v["id"] in used:
            v["id"] = f"V{i + 1}"
        used.add(v["id"])
    videos.sort(key=lambda v: (v["rank"], -v["score"]["total"]))
    return {"research": research, "videos": videos}


def plan_problems(plan: dict) -> list:
    """Human-readable warnings about a normalized plan (shown in the UI)."""
    out = []
    for v in plan.get("videos", []):
        if not v["timeline"]:
            out.append(f"{v['id']}: timeline is empty")
        if not v["shots"]:
            out.append(f"{v['id']}: no shots")
        total = sum(b["duration"] for b in v["timeline"])
        if total and abs(total - v["target_length_sec"]) > max(8, v["target_length_sec"] * 0.5):
            out.append(f"{v['id']}: beats add up to {total:.0f}s vs target {v['target_length_sec']:.0f}s")
    return out
