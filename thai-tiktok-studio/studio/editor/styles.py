"""Animation style packs — the same plan can be rendered with different motion.

Each video gets one pack (bouncy, punchy, smooth, playful, minimal). Within a pack, the
exact entrance for each graphic is picked with a seeded random generator, so every
render "variation" looks different but is reproducible.
"""

from __future__ import annotations

import random

from .anim import IN_DUR

STYLES = ["bouncy", "punchy", "smooth", "playful", "minimal"]

PACKS = {
    "bouncy":  {"title": ["pop", "drop"], "emph": ["pop", "stamp"], "list": ["slide_left", "pop"],
                "sticker": "wiggle", "caption": "caption", "out": "pop_out"},
    "punchy":  {"title": ["stamp", "zoom_out"], "emph": ["stamp", "caption_punch"], "list": ["slide_left", "slide_right"],
                "sticker": "pulse", "caption": "caption_punch", "out": "fade"},
    "smooth":  {"title": ["fade_up", "wipe"], "emph": ["zoom_out", "fade_up"], "list": ["fade_up", "slide_left"],
                "sticker": "float", "caption": "fade_up", "out": "fade"},
    "playful": {"title": ["swing", "drop"], "emph": ["spin_in", "swing"], "list": ["drop", "pop"],
                "sticker": "wiggle", "caption": "caption", "out": "pop_out"},
    "minimal": {"title": ["fade", "fade_up"], "emph": ["fade_up", "fade"], "list": ["fade", "fade_up"],
                "sticker": "breathe", "caption": "fade", "out": "fade"},
}

ROLE = {
    "hook_title": "title", "label": "title", "before_after_labels": "title", "lower_third": "title",
    "comment_reply": "title", "speech_bubble": "title", "spec_card": "title", "urgency_banner": "title",
    "number_badge": "title", "vs_split": "title",
    "keyword_pop": "emph", "discount_badge": "emph", "reaction_text": "emph",
    "checklist": "list", "trust_badges": "list", "stars_rating": "list",
    "emoji_sticker": "sticker",
    # arrow / cta_basket keep their own purpose-built motion
}


def rng_for(video: dict) -> random.Random:
    return random.Random(f"{video.get('id', '')}:{video.get('anim_style', '')}:{video.get('variation', 0)}")


def apply(els: list, overlay_type: str, style: str, rng: random.Random) -> list:
    pack = PACKS.get(style)
    role = ROLE.get(overlay_type)
    if not pack or not role or not els:
        return els
    if role == "sticker":
        anim = rng.choice(["pop", "drop", "spin_in", "swing"])
    else:
        anim = rng.choice(pack[role])
    for el in els:
        if el.draw is not None or el.anim_in == "none":
            continue
        el.anim_in, el.in_dur = anim, IN_DUR.get(anim, 0.3)
        el.out = pack["out"] if el.out != "none" else "none"
        if role == "sticker" or (role == "emph" and el.loop):
            el.loop = pack["sticker"]
    return els


def caption_anim(style: str) -> str:
    return PACKS.get(style, PACKS["bouncy"])["caption"]
