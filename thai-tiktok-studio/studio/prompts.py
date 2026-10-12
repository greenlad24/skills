"""Prompt builders. The frameworks are injected verbatim so behaviour is editable
by changing the markdown files in frameworks/ — no code changes needed."""

from __future__ import annotations

import json

from .config import FRAMEWORKS_DIR
from .plan_schema import PLAN_SCHEMA, RESEARCH


def _read(name: str) -> str:
    return (FRAMEWORKS_DIR / name).read_text("utf-8")


def framework_text() -> str:
    from .inspiration import EXAMPLES_PATH  # user's own imported dataset (optional)
    out = _read("script_framework.md") + "\n\n" + _read("motion_framework.md")
    if EXAMPLES_PATH.exists():
        out += "\n\n" + EXAMPLES_PATH.read_text("utf-8")
    return out


EDITOR_RULES = """
# How the automatic editor reads your plan (follow exactly)
- Each video has `shots` (the FILMING list for the creator) and a `timeline` (the EDIT: ordered beats).
- Shot ids: "V<video>-S<two digits>", e.g. V1-S01. The creator names files by these ids.
- Every beat uses one shot's footage; a long shot may be reused by several beats with different `trim`.
- audio_mode:
  - "talking": the creator speaks on camera. Shots with dialogue have audio "sync", and the beat's `vo_th`
    must equal what is said in that clip. The editor trims silences automatically; beat duration ≈ speech length.
    B-roll beats inside a talking video use mute shots (vo_th "").
  - "voiceover": all footage is B-roll (audio "mute"); the creator records ALL the `vo_th` lines of the video
    in ONE take in their own voice, in order, with a short pause between lines. Write vo_th as natural spoken
    Thai that is easy to read aloud. Beat duration ≈ time to speak vo_th (≈ 7 Thai syllables/second);
    silent beats still need a duration.
  - "music_only": no speech; captions/overlays carry the message (ASMR, satisfying). Use on-screen text heavily.
- `captions` = vo_th split into readable chunks IN ORDER that together contain the whole vo_th
  (≤18 Thai characters each, break only between words). Mark 0–2 keyword `highlight`s per chunk (prices, numbers, benefits).
- Overlay `at`/`dur` are in seconds relative to the beat start. Text must be SHORT (hook ≤ 8 words, labels ≤ 4 words).
- Do not plan any sound effects (the editor has none); leave `sfx` out.
- PRICES: never say or show the actual selling price ("เหลือแค่ 2,990", "ในคลิปนี้ 1,990"). In SPOKEN lines
  (vo_th / dialogue_th / full_script_th) you MAY state what it costs in a store/mall as an anchor
  ("ที่ห้างราคาเป็นหมื่น", "หน้าร้านขาย 4,000 กว่าบาท"), followed by "แต่เจอตัวนี้ในราคาพิเศษ ที่หาจากที่ไหนไม่ได้เลย"
  and "ตอนนี้มีราคาพิเศษ / กดดูราคาพิเศษในตะกร้า". Captions, overlays and post_caption_th contain NO amounts at all. Show value with words instead ("คุ้มมาก", "ลดแรง", "โปรดีมาก") or a discount_badge like "ลด 50%".
- GRAPHICS STYLE = the creator's proven style (see "The creator's own proven style" in the motion framework):
  beat 1 starts a `text_card` headline (dur ~6-9 s, may span beats); from the middle a `text_card` with `items`
  (3-5 emoji-first lines, last line = who it's for) lasting to the very end (it shows ↓ arrows to the basket).
  At most 1 other graphic per video. Camera `effect` "none" on video beats (slow_zoom on product photos).
  Only fast formats (reply_to_comment, comparisons, lists) may use hook_title / cta_basket / punch_in instead.
- The editor shows NO subtitles; `captions` are still filled in (used for the script export), but put any
  must-read words in the text_card.
- Beat durations must add up to ≈ target_length_sec.
- Shot lists in Thai: concrete, filmable at home with a phone, 9:16 vertical; say what to film, how, and how long.
  Always include at least one wide "real home/context" shot and several close-ups. Record each shot 2–3 s longer than needed.
- NEVER plan product photos or downloaded images: every shot is a video clip the creator films themself
  (do not use shot_size "product_photo"). Number the shots in the order they should be FILMED = the order of the
  steps in the video; the editor keeps the clips in recording order.
"""


def system_prompt(n_videos: int) -> str:
    return (
        "You are a top Thai TikTok Shop affiliate strategist, scriptwriter and video editor. "
        "You write native, natural Thai (spoken style, ภาษาพูด) that sounds like a real Thai creator, "
        "never translated or ad-like. You follow the evidence-based framework below exactly.\n\n"
        + framework_text()
        + "\n\n"
        + EDITOR_RULES
        + f"\n\nProduce exactly {n_videos} videos with {n_videos} different formats and hook types, "
        "ranked by predicted virality (rank 1 = best). All Thai-facing fields in Thai; *_en fields in English."
    )


def describe_inputs(gathered: dict) -> str:
    page = gathered.get("page") or {}
    parts = [f"USER INPUT: {gathered.get('input_text') or '(screenshot only)'}"]
    if gathered.get("url"):
        parts.append(f"PRODUCT URL: {gathered['url']}")
    if page.get("ok"):
        parts.append(
            "SCRAPED PAGE:\n" + json.dumps(
                {k: page.get(k) for k in ("final_url", "title", "description", "price", "currency", "rating")},
                ensure_ascii=False, indent=1) + "\nPAGE TEXT (truncated): " + (page.get("text") or "")[:2500]
        )
    if gathered.get("search_results"):
        parts.append("WEB SEARCH RESULTS:\n" + "\n".join(
            f"- {r['title']} | {r['url']} | {r['snippet']}" for r in gathered["search_results"]))
    if gathered.get("user_images"):
        parts.append(f"The user attached {len(gathered['user_images'])} screenshot(s) of the product (see images).")
    if gathered.get("notes"):
        parts.append("EXTRA NOTES FROM THE USER: " + gathered["notes"])
    return "\n\n".join(parts)


def research_prompt(gathered: dict) -> str:
    return (
        describe_inputs(gathered)
        + "\n\nTASK — RESEARCH (use web search, several queries, Thai and English):\n"
        "1. Identify the exact product (brand, model, variants) and its facts: features, specs, materials, "
        "current price in THB on TikTok Shop / Shopee / Lazada and the usual/original price, ratings, units sold.\n"
        "2. Customer pain points, desires, objections and real review quotes (Thai reviews, Pantip, Shopee/Lazada reviews).\n"
        "3. What is working RIGHT NOW on Thai TikTok for this product and niche: hooks, formats, angles competitors "
        "use, top creators, trends, sounds. Search e.g. '<product> tiktok', '<category> รีวิว tiktok', "
        "'<category> ป้ายยา'.\n"
        "4. Compliance risks for this category (อย. registration/claims, TikTok Shop TH rules).\n"
        "Finish with a concise research dossier (facts only, with source URLs). Do not write scripts yet."
    )


def plan_prompt(gathered: dict, dossier: str, n_videos: int) -> str:
    return (
        describe_inputs(gathered)
        + "\n\nRESEARCH DOSSIER:\n" + (dossier or "(none — rely on the inputs above)")
        + f"\n\nTASK — Create the full plan: the research summary and {n_videos} complete videos "
        "(filming shot list + exact edit timeline), following the framework and editor rules. "
        "Score each with the rubric, rank them, and make sure every claim is compliant."
    )


def manual_prompt(gathered: dict, n_videos: int) -> str:
    """One self-contained prompt to paste into ChatGPT / Claude chat (free)."""
    return (
        system_prompt(n_videos)
        + "\n\n---\n\n"
        + research_prompt(gathered).replace("Do not write scripts yet.", "")
        + "\n\nThen, using that research:\n"
        + plan_prompt(gathered, "(use the research you just did)", n_videos).split("TASK —", 1)[-1]
        + "\n\nOUTPUT FORMAT: reply with ONE JSON object only (no markdown fences, no commentary) that matches "
        "this JSON Schema exactly (every property is required; use \"\", [] or 0 when not applicable):\n"
        + json.dumps(PLAN_SCHEMA, ensure_ascii=False)
    )


def research_schema_keys() -> list:
    return list(RESEARCH["properties"])
