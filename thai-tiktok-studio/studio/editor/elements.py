"""Overlay element library — each plan overlay `type` → animated Elements.

Specs follow frameworks/motion_framework.md (ranked research). Safe box for text:
x 60–900, y 150–1400 on a 1080x1920 frame (TikTok UI covers the right rail + bottom).
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

from . import text as T
from ..plan_schema import strip_overlay_prices
from . import styles
from .anim import IN_DUR, Element

W, H = 1080, 1920
SAFE_CX = 480          # centre of the safe box (right rail is covered by TikTok buttons)
MAX_W = 820
CAPTION_Y = 1215

POS = {
    "top": (SAFE_CX, 330), "upper": (SAFE_CX, 560), "center": (SAFE_CX, 880), "lower": (SAFE_CX, 1040),
    "bottom": (SAFE_CX, 1320), "top_left": (270, 330), "top_right": (700, 330),
    "center_left": (290, 880), "center_right": (690, 880), "lower_left": (290, 1040),
    "lower_right": (690, 1040),
}

THEMES = {
    "sale_red_yellow": {"primary": (230, 0, 18), "accent": (255, 224, 0), "ink": (17, 17, 17), "good": (34, 197, 94), "hl": (255, 255, 255)},
    "hot_orange_gold": {"primary": (255, 106, 0), "accent": (255, 199, 0), "ink": (17, 17, 17), "good": (34, 197, 94), "hl": (255, 255, 255)},
    "trust_green": {"primary": (22, 163, 74), "accent": (255, 224, 0), "ink": (15, 23, 42), "good": (34, 197, 94), "hl": (255, 255, 255)},
    "beauty_pink": {"primary": (255, 95, 162), "accent": (255, 240, 246), "ink": (60, 20, 40), "good": (255, 95, 162), "hl": (255, 255, 255)},
    "clean_black_white": {"primary": (17, 17, 17), "accent": (255, 255, 255), "ink": (17, 17, 17), "good": (34, 197, 94), "hl": (255, 255, 255)},
}
NAMED = {
    "yellow": (255, 224, 0), "red": (230, 0, 18), "white": (255, 255, 255), "black": (17, 17, 17),
    "pink": (255, 95, 162), "green": (34, 197, 94), "orange": (255, 106, 0), "blue": (37, 99, 235),
}


WHITE = (255, 255, 255, 255)


def rgba(c, a=255):
    return (c[0], c[1], c[2], a)


def ink_for(bg) -> tuple:
    lum = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
    return (17, 17, 17) if lum > 150 else (255, 255, 255)


class Ctx:
    def __init__(self, video: dict):
        self.style = video.get("anim_style") or "bouncy"
        self.rng = styles.rng_for(video)
        self.theme = THEMES.get(video.get("theme"), THEMES["sale_red_yellow"])
        self.family = video.get("font", "kanit")
        self.caption_style = video.get("caption_style", "stroke_white")

    def color(self, name: str, default_key: str = "primary"):
        if name and name != "auto" and name in NAMED:
            return NAMED[name]
        return self.theme[default_key]


def _pos(o: dict, default: str):
    p = o.get("position") or "auto"
    if p == "target":
        return (o["target_x"] * W, o["target_y"] * H)
    return POS.get(p, POS[default])


def _clamp_center(cx, cy, img, left=60, right=900, top=150, bottom=1400):
    hw, hh = img.width / 2, img.height / 2
    cx = min(max(cx, left + hw), max(left + hw, right - hw))
    cy = min(max(cy, top + hh), max(top + hh, bottom - hh))
    return cx, cy


def _el(sprite, cx, cy, start, end, clamp=True, **kw) -> Element:
    if clamp and sprite is not None:
        cx, cy = _clamp_center(cx, cy, sprite)
    return Element(start=start, end=end, cx=cx, cy=cy, sprite=sprite, **kw)


# --------------------------------------------------------------------------- shapes
def starburst(r: int, points: int, fill, outline=None) -> Image.Image:
    img = Image.new("RGBA", (2 * r + 8, 2 * r + 8), (0, 0, 0, 0))
    pts = []
    for i in range(points * 2):
        ang = math.pi * i / points - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.82
        pts.append((r + 4 + rr * math.cos(ang), r + 4 + rr * math.sin(ang)))
    d = ImageDraw.Draw(img)
    d.polygon(pts, fill=fill, outline=outline)
    if outline:
        d.line(pts + [pts[0]], fill=outline, width=6, joint="curve")
    return img


def star(r: int, fill) -> Image.Image:
    img = Image.new("RGBA", (2 * r + 6, 2 * r + 6), (0, 0, 0, 0))
    pts = []
    for i in range(10):
        ang = math.pi * i / 5 - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((r + 3 + rr * math.cos(ang), r + 3 + rr * math.sin(ang)))
    ImageDraw.Draw(img).polygon(pts, fill=fill, outline=(120, 80, 0, 255))
    return img


def check_icon(size: int, bg=(34, 197, 94)) -> Image.Image:
    img = T.rounded_box((size, size), size // 4, rgba(bg))
    d = ImageDraw.Draw(img)
    s = size
    d.line([(s * 0.24, s * 0.52), (s * 0.43, s * 0.70), (s * 0.77, s * 0.30)], fill=(255, 255, 255, 255),
           width=max(4, s // 8), joint="curve")
    return img


def arrow_sprite(length: int = 230, color=(255, 224, 0)) -> Image.Image:
    """Arrow pointing RIGHT (rotate for other directions); yellow with black outline."""
    w, h = length + 20, 120
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    shaft = [(10, h / 2 - 18), (length - 70, h / 2 - 18), (length - 70, h / 2 - 50), (length + 8, h / 2),
             (length - 70, h / 2 + 50), (length - 70, h / 2 + 18), (10, h / 2 + 18)]
    d.polygon(shaft, fill=rgba(color))
    d.line(shaft + [shaft[0]], fill=(0, 0, 0, 255), width=7, joint="curve")
    return img


def _title(text, ctx, size=88, weight="black", max_w=MAX_W, fill=(255, 255, 255, 255), stroke=(0, 0, 0, 255),
           hl=None, max_lines=2, family=None, stroke_w=None, shadow=True):
    return T.text_block(text, family=family or ctx.family, weight=weight, size=size, max_w=max_w,
                        max_lines=max_lines, fill=fill, stroke=stroke, stroke_w=stroke_w, highlight=hl,
                        hl_fill=rgba(ctx.theme["hl"]), shadow=shadow)


# --------------------------------------------------------------------------- builders
def hook_title(o, s, e, ctx):
    if o["color"] in ("auto", "white", "black", "yellow"):
        bg, ink = (0, 0, 0, 165), WHITE
    else:
        c = ctx.color(o["color"])
        bg, ink = rgba(c), rgba(ink_for(c))
    t = _title(o["text"], ctx, size=92, max_w=760, fill=ink, stroke=None, stroke_w=0, shadow=False)
    spr = T.boxed(t, bg, pad_x=36, pad_y=14, radius=28)
    cx, cy = _pos(o, "top")
    return [_el(spr, cx, cy, s, e, anim_in="pop", in_dur=0.32, rot=-2, z=5)]


def keyword_pop(o, s, e, ctx):
    spr = _title(o["text"], ctx, size=150, max_w=840, fill=WHITE, stroke=(0, 0, 0, 255), stroke_w=12)
    emo = T.emoji_sprite(o["emoji"], 150) if o["emoji"] else None
    if emo:
        spr = T.hstack([spr, emo], gap=10)
    cx, cy = _pos(o, "center")
    return [_el(spr, cx, cy, s, e, anim_in="stamp", in_dur=0.22, z=6)]


def discount_badge(o, s, e, ctx):
    bg = ctx.color(o["color"], "primary")
    t = _title(o["text"], ctx, size=70, weight="black", max_w=260, fill=WHITE,
               stroke=(0, 0, 0, 255), stroke_w=5, shadow=False, max_lines=2)
    r = max(t.width, t.height) // 2 + 36
    b = starburst(r, 16, rgba(bg), outline=(255, 255, 255, 255))
    b.alpha_composite(t, ((b.width - t.width) // 2, (b.height - t.height) // 2))
    cx, cy = _pos(o, "top_right")
    return [_el(b, cx, cy, s, e, anim_in="stamp", in_dur=0.22, rot=-10, loop="pulse", z=7)]


def cta_basket(o, s, e, ctx):
    bg = ctx.color(o["color"], "primary")
    label = T.strip_emoji(o["text"]) or "กดตะกร้าเลย"
    t = _title(label, ctx, size=70, weight="black", max_w=560, fill=rgba(ink_for(bg)), stroke=None, stroke_w=0,
               shadow=False, max_lines=1)
    emo = T.emoji_sprite(o["emoji"] or "🛒", 74)
    pill = T.boxed(T.hstack([t, emo], gap=14), rgba(bg), pad_x=40, pad_y=16, radius=60,
                   outline=(255, 255, 255, 255), width=6)
    els = [_el(pill, 400, 1352, s, e, clamp=False, anim_in="pop", in_dur=0.3, loop="pulse", z=8)]
    # arrow pointing at the TikTok product anchor (bottom-left, just above the username)
    arr = arrow_sprite(200, ctx.theme["accent"]).rotate(-125, resample=Image.BICUBIC, expand=True)
    els.append(Element(start=s + 0.15, end=e, cx=160, cy=1490, sprite=arr, anim_in="pop", in_dur=0.25,
                       loop="bob", bob_dir=(-0.57, 0.82), z=8))
    return els


def arrow(o, s, e, ctx):
    tx, ty = o["target_x"] * W, o["target_y"] * H
    # come from the side with more room, pointing at the target
    fx = tx - 230 if tx > W / 2 else tx + 230
    fy = ty - 170
    ang = math.degrees(math.atan2(ty - fy, tx - fx))
    spr = arrow_sprite(220, ctx.color(o["color"], "accent")).rotate(-ang, resample=Image.BICUBIC, expand=True)
    L = 130  # place centre back from the tip
    ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    return [Element(start=s, end=e, cx=tx - ux * L, cy=ty - uy * L, sprite=spr, anim_in="pop", in_dur=0.25,
                    loop="bob", bob_dir=(ux, uy), z=6)]


def circle_highlight(o, s, e, ctx):
    tx, ty = o["target_x"] * W, o["target_y"] * H
    col = rgba(ctx.color(o["color"], "primary"))
    rx, ry = 170, 130

    def draw(lt):
        p = min(1.0, lt / 0.35)
        img = Image.new("RGBA", (rx * 2 + 30, ry * 2 + 30), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.arc([15, 15, 15 + rx * 2, 15 + ry * 2], start=-100, end=-100 + 380 * p, fill=col, width=13)
        return img
    return [Element(start=s, end=e, cx=tx, cy=ty, draw=draw, anim_in="none", in_dur=0.0, z=6)]


def checklist(o, s, e, ctx):
    items = o["items"] or ([o["text"]] if o["text"] else [])
    cx, cy = _pos(o, "center_left")
    rows = []
    for it in items[:5]:
        t = _title(it, ctx, size=58, weight="bold", max_w=600, fill=(255, 255, 255, 255), stroke=None, stroke_w=0,
                   shadow=False, max_lines=1)
        row = T.boxed(T.hstack([check_icon(64, ctx.theme["good"]), t], gap=16), (0, 0, 0, 150), pad_x=18,
                      pad_y=10, radius=20, shadow=False)
        rows.append(row)
    if not rows:
        return []
    gap = 16
    total_h = sum(r.height for r in rows) + gap * (len(rows) - 1)
    max_w = max(r.width for r in rows)
    left = max(60, min(cx - max_w / 2, 900 - max_w))
    y = max(150, min(cy - total_h / 2, 1400 - total_h))
    els = []
    stagger = min(0.5, max(0.25, (e - s - 0.6) / max(1, len(rows))))
    for i, r in enumerate(rows):
        els.append(Element(start=s + i * stagger, end=e, cx=left + r.width / 2, cy=y + r.height / 2, sprite=r,
                           anim_in="slide_left", in_dur=0.25, z=5))
        y += r.height + gap
    return els


def label(o, s, e, ctx, default_pos="top_left"):
    txt = T.strip_emoji(o["text"])
    if o["type"] == "before_after_labels" and o["color"] == "auto":
        bg = (120, 120, 120) if "ก่อน" in txt or "before" in txt.lower() else ctx.theme["good"]
    else:
        bg = ctx.color(o["color"], "primary")
    t = _title(txt, ctx, size=76, weight="black", max_w=520, fill=rgba(ink_for(bg)), stroke=None, stroke_w=0,
               shadow=False, max_lines=1)
    spr = T.boxed(t, rgba(bg), pad_x=30, pad_y=10, radius=22)
    cx, cy = _pos(o, default_pos)
    return [_el(spr, cx, cy, s, e, anim_in="pop", in_dur=0.28, z=5)]


def trust_badges(o, s, e, ctx):
    items = o["items"] or [o["text"]]
    pills = []
    for it in [i for i in items if i][:4]:
        t = _title(it, ctx, size=48, weight="bold", max_w=420, fill=(255, 255, 255, 255), stroke=None, stroke_w=0,
                   shadow=False, max_lines=1)
        pills.append(T.boxed(T.hstack([check_icon(46, (255, 255, 255)), t], gap=10), rgba(ctx.color(o["color"], "good")),
                             pad_x=18, pad_y=8, radius=40, shadow=False))
    if not pills:
        return []
    cx, cy = _pos(o, "upper")
    stack = T.vstack(pills, gap=12)
    cx, cy = _clamp_center(cx, cy, stack)
    els, y = [], cy - stack.height / 2
    for i, p in enumerate(pills):
        els.append(Element(start=s + i * 0.18, end=e, cx=cx, cy=y + p.height / 2, sprite=p, anim_in="pop",
                           in_dur=0.25, z=5))
        y += p.height + 12
    return els


def stars_rating(o, s, e, ctx):
    cx, cy = _pos(o, "upper")
    els = []
    st = star(46, (255, 199, 0, 255))
    total_w = 5 * st.width + 4 * 8
    x0 = cx - total_w / 2
    x0 = max(60, min(x0, 900 - total_w))
    for i in range(5):
        els.append(Element(start=s + i * 0.09, end=e, cx=x0 + st.width / 2 + i * (st.width + 8), cy=cy, sprite=st,
                           anim_in="pop", in_dur=0.22, z=6))
    lines = [x for x in (T.strip_emoji(o["text"]), T.strip_emoji(o["sub_text"])) if x]
    if lines:
        t = _title("  ".join(lines), ctx, size=62, weight="black", max_w=780, fill=(255, 255, 255, 255),
                   stroke=(0, 0, 0, 255), stroke_w=6, max_lines=1)
        els.append(_el(t, cx, cy + 105, s + 0.45, e, anim_in="pop", in_dur=0.25, z=6))
    return els


def comment_reply(o, s, e, ctx):
    user = o["sub_text"] or "@ลูกค้า"
    if not user.startswith("@"):
        user = "@" + user
    head = T.text_block(f"ตอบกลับความคิดเห็นของ {user}", family="kanit", weight="medium", size=36, max_w=640,
                        max_lines=1, fill=(110, 110, 110, 255), stroke=None, stroke_w=0, shadow=False)
    body = T.text_block(o["text"], family="kanit", weight="bold", size=54, max_w=640, max_lines=3,
                        fill=(17, 17, 17, 255), stroke=None, stroke_w=0, shadow=False, align="left")
    avatar = Image.new("RGBA", (72, 72), (0, 0, 0, 0))
    ImageDraw.Draw(avatar).ellipse([0, 0, 71, 71], fill=(254, 44, 85, 255))
    col = T.vstack([head, body], gap=4, align="left")
    card = T.boxed(T.hstack([avatar, col], gap=16), (255, 255, 255, 255), pad_x=24, pad_y=18, radius=26)
    cx, cy = _pos(o, "upper")
    return [_el(card, cx, cy, s, e, anim_in="pop", in_dur=0.3, z=7)]


def emoji_sticker(o, s, e, ctx):
    spr = T.emoji_sprite(o["emoji"] or T.first_emoji(o["text"]) or "🔥", 210)
    if spr is None:
        return []
    cx, cy = _pos(o, "center_right")
    return [_el(spr, cx, cy, s, e, anim_in="pop", in_dur=0.3, loop="wiggle", z=6)]


def spec_card(o, s, e, ctx):
    rows = []
    if o["text"]:
        rows.append(_title(o["text"], ctx, size=58, weight="black", max_w=640, fill=WHITE,
                           stroke=None, stroke_w=0, shadow=False, max_lines=1))
    for it in o["items"][:6]:
        rows.append(T.text_block(it, family=ctx.family, weight="bold", size=46, max_w=640, max_lines=1,
                                 fill=(255, 255, 255, 255), stroke=None, stroke_w=0, shadow=False, align="left"))
    if not rows:
        return []
    card = T.boxed(T.vstack(rows, gap=8, align="left"), (0, 0, 0, 175), pad_x=30, pad_y=20, radius=24)
    cx, cy = _pos(o, "center_left")
    return [_el(card, cx, cy, s, e, anim_in="slide_left", in_dur=0.28, z=5)]


def number_badge(o, s, e, ctx):
    num = T.strip_emoji(o["text"])[:3] or "1"
    r = 70
    circ = Image.new("RGBA", (r * 2 + 8, r * 2 + 8), (0, 0, 0, 0))
    ImageDraw.Draw(circ).ellipse([4, 4, r * 2 + 4, r * 2 + 4], fill=rgba(ctx.theme["primary"]),
                                 outline=(255, 255, 255, 255), width=6)
    n = T.text_block(num, family="kanit", weight="black", size=100, max_w=200, max_lines=1, fill=WHITE,
                     stroke=None, stroke_w=0, shadow=False)
    circ.alpha_composite(n, ((circ.width - n.width) // 2, (circ.height - n.height) // 2))
    parts = [circ]
    if o["sub_text"]:
        parts.append(T.boxed(_title(o["sub_text"], ctx, size=60, weight="black", max_w=560, fill=(255, 255, 255, 255),
                                    stroke=None, stroke_w=0, shadow=False, max_lines=1), (0, 0, 0, 170),
                             pad_x=22, pad_y=8, radius=18, shadow=False))
    spr = T.hstack(parts, gap=14)
    cx, cy = _pos(o, "top_left")
    return [_el(spr, cx, cy, s, e, anim_in="slide_right", in_dur=0.28, z=6)]


def urgency_banner(o, s, e, ctx):
    bg = ctx.color(o["color"], "primary")
    t = _title(o["text"], ctx, size=68, weight="black", max_w=780, fill=WHITE if ink_for(bg)[0] > 128 else rgba(ink_for(bg)),
               stroke=None, stroke_w=0, shadow=False, max_lines=1)
    spr = T.boxed(t, rgba(bg), pad_x=34, pad_y=12, radius=10, outline=(255, 255, 255, 255), width=5)
    cx, cy = _pos(o, "upper")
    return [_el(spr, cx, cy, s, e, anim_in="slide_down", in_dur=0.25, loop="pulse", z=6)]


def vs_split(o, s, e, ctx):
    els = []
    left = dict(o, text=o["text"] or "A", position="top_left", color="blue")
    right = dict(o, text=o["sub_text"] or "B", position="top_right", color="red")
    els += label(left, s, e, ctx)
    els += label(right, s, e, ctx)
    r = 62
    c = Image.new("RGBA", (r * 2 + 8, r * 2 + 8), (0, 0, 0, 0))
    ImageDraw.Draw(c).ellipse([4, 4, 2 * r + 4, 2 * r + 4], fill=(17, 17, 17, 255), outline=(255, 255, 255, 255), width=6)
    vs = T.text_block("VS", family="kanit", weight="black", size=70, max_w=200, max_lines=1, fill=WHITE,
                      stroke=None, stroke_w=0, shadow=False)
    c.alpha_composite(vs, ((c.width - vs.width) // 2, (c.height - vs.height) // 2))
    els.append(_el(c, SAFE_CX, 330, s + 0.15, e, anim_in="stamp", in_dur=0.22, z=7))
    return els


def reaction_text(o, s, e, ctx):
    spr = T.text_block(o["text"], family="mali", weight="any", size=96, max_w=700, max_lines=2, fill=WHITE,
                       stroke=(0, 0, 0, 255), stroke_w=9)
    emo = T.emoji_sprite(o["emoji"], 96) if o["emoji"] else None
    if emo:
        spr = T.hstack([spr, emo], gap=8)
    cx, cy = _pos(o, "upper")
    return [_el(spr, cx, cy, s, e, anim_in="pop", in_dur=0.3, rot=-5, loop="wiggle", loop_amp=0.6, z=6)]


def speech_bubble(o, s, e, ctx):
    t = T.text_block(o["text"], family=ctx.family, weight="bold", size=56, max_w=600, max_lines=3,
                     fill=(17, 17, 17, 255), stroke=None, stroke_w=0, shadow=False)
    pad = 34
    bw, bh = t.width + pad * 2, t.height + pad * 2
    img = Image.new("RGBA", (bw + 10, bh + 50), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 4, bw, bh], radius=44, fill=(255, 255, 255, 255), outline=(17, 17, 17, 255), width=5)
    d.polygon([(bw * 0.25, bh - 2), (bw * 0.18, bh + 44), (bw * 0.40, bh - 2)], fill=(255, 255, 255, 255))
    d.line([(bw * 0.25, bh), (bw * 0.18, bh + 44), (bw * 0.40, bh)], fill=(17, 17, 17, 255), width=5)
    img.alpha_composite(t, (pad + 4, pad + 4))
    cx, cy = _pos(o, "upper")
    return [_el(img, cx, cy, s, e, anim_in="pop", in_dur=0.3, z=6)]


def lower_third(o, s, e, ctx):
    bg = ctx.color(o["color"], "primary")
    main = _title(o["text"], ctx, size=64, weight="black", max_w=700, fill=rgba(ink_for(bg)), stroke=None,
                  stroke_w=0, shadow=False, max_lines=1)
    parts = [main]
    if o["sub_text"]:
        parts.append(T.text_block(o["sub_text"], family=ctx.family, weight="medium", size=40, max_w=700,
                                  max_lines=1, fill=rgba(ink_for(bg)), stroke=None, stroke_w=0, shadow=False))
    spr = T.boxed(T.vstack(parts, gap=2, align="left"), rgba(bg), pad_x=30, pad_y=12, radius=14)
    cx, cy = _pos(o, "lower_left")
    return [_el(spr, cx, cy, s, e, anim_in="slide_right", in_dur=0.3, z=5)]


BUILDERS = {
    "hook_title": hook_title, "keyword_pop": keyword_pop,
    "discount_badge": discount_badge, "cta_basket": cta_basket, "arrow": arrow,
    "circle_highlight": circle_highlight, "checklist": checklist, "label": label,
    "trust_badges": trust_badges, "stars_rating": stars_rating, "comment_reply": comment_reply,
    "emoji_sticker": emoji_sticker, "spec_card": spec_card, "number_badge": number_badge,
    "urgency_banner": urgency_banner, "before_after_labels": label, "vs_split": vs_split,
    "reaction_text": reaction_text, "speech_bubble": speech_bubble, "lower_third": lower_third,
}


def build_overlay(o: dict, start: float, end: float, ctx: Ctx) -> list:
    fn = BUILDERS.get(o["type"])
    if not fn or end - start < 0.1:
        return []
    o = strip_overlay_prices(o)  # never show prices in graphics
    if o is None:
        return []
    try:
        return styles.apply(fn(o, start, end, ctx), o["type"], ctx.style, ctx.rng)
    except Exception:  # one bad overlay must never kill a render
        return []


# --------------------------------------------------------------------------- captions & globals
def caption(text: str, highlight: list, start: float, end: float, ctx: Ctx) -> Element | None:
    style = {"stroke_yellow": "stroke_white", "box_yellow": "box_black"}.get(ctx.caption_style, ctx.caption_style)
    hl = rgba(ctx.theme["hl"])
    if style == "box_black":
        t = T.text_block(text, family=ctx.family, weight="bold", size=70, max_w=760, max_lines=2,
                         fill=(255, 255, 255, 255), stroke=None, stroke_w=0, highlight=highlight, hl_fill=hl,
                         shadow=False)
        spr = T.boxed(t, (0, 0, 0, 185), pad_x=24, pad_y=8, radius=18, shadow=False)
    else:
        spr = T.text_block(text, family=ctx.family, weight="xbold", size=78, max_w=800, max_lines=2,
                           fill=WHITE, stroke=(0, 0, 0, 255), highlight=highlight, hl_fill=hl)
    if spr.width <= 2:
        return None
    cx, cy = _clamp_center(SAFE_CX, CAPTION_Y, spr)
    anim = styles.caption_anim(ctx.style)
    return Element(start=start, end=end, cx=cx, cy=cy, sprite=spr, anim_in=anim, in_dur=IN_DUR.get(anim, 0.14),
                   out="none", z=4)


def flash(at: float) -> Element:
    white = Image.new("RGBA", (W, H), (255, 255, 255, 255))

    def draw(lt):
        a = max(0.0, 0.9 * (1 - lt / 0.13))
        img = white.copy()
        img.putalpha(int(255 * a))
        return img
    return Element(start=at, end=at + 0.13, cx=W / 2, cy=H / 2, draw=draw, anim_in="none", in_dur=0.0, out="none", z=20)


def progress_bar(total: float, color) -> Element:
    def draw(lt):
        img = Image.new("RGBA", (W, 10), (255, 255, 255, 70))
        ImageDraw.Draw(img).rectangle([0, 0, int(W * min(1, lt / total)), 9], fill=rgba(color))
        return img
    return Element(start=0, end=total, cx=W / 2, cy=150, draw=draw, anim_in="none", in_dur=0.0, out="none", z=1)


def missing_card(shot: dict, start: float, end: float) -> Element:
    lines = [f"📷 ยังไม่มีไฟล์ {shot.get('id', '')}", shot.get("what_to_film_th", "")[:80]]
    t = T.vstack([
        T.text_block(lines[0], size=64, max_w=820, max_lines=1, fill=WHITE),
        T.text_block(lines[1], size=44, weight="medium", max_w=820, max_lines=3) if lines[1] else None,
    ], gap=10)
    return Element(start=start, end=end, cx=W / 2, cy=760, sprite=t, anim_in="none", in_dur=0, out="none", z=0)
