"""Stream graphics drawn with Pillow: the slate (Starting soon / Break / Thanks for watching)
and the band-view title strip. Layout follows designs/vibenation-canvas/Break.dc.html
(1280x720 reference) and the vertical band view in apps/web/src/screens/Show.tsx.

Everything returns tightly packed RGBA bytes of exactly the requested size.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).resolve().parent.parent / 'fonts'

BG = (0x14, 0x0B, 0x08)
TEXT = (0xF5, 0xEE, 0xE6)
META = (0xE9, 0xDC, 0xCD)
GOLD = (0xFF, 0xC3, 0x71)
SUB = (0xFF, 0xE3, 0xBF)

MODES = {
    'Starting soon': dict(pill='STARTING SOON', headline='The show starts in', foot='Grab a drink — the band is tuning up', time=True),
    'Break': dict(pill='SHORT BREAK', headline='We’ll be back in', foot='Grab a drink — set two starts soon', time=True),
    'Thanks for watching': dict(pill='THAT’S A WRAP', headline='Thanks for watching', foot='See you next week', time=False),
}


@dataclass
class Info:
    """Band/show settings used on the graphics (user settings in the web app)."""
    show_name: str = '[Band Name] · live cover band session'
    channel: str = 'Music Live Love'
    song: str = ''
    colors: tuple[str, str, str] = ('#FF5E62', '#FF9966', '#FFC371')
    now_playing: str = ''          # break playlist track, optional
    foot: dict[str, str] = field(default_factory=dict)  # per-mode footer override

    def key(self):
        return (self.show_name, self.channel, self.song, self.colors, self.now_playing, tuple(sorted(self.foot.items())))


@functools.lru_cache(maxsize=64)
def font(name: str, size: int, weight: int) -> ImageFont.FreeTypeFont:
    path = FONTS / {'sora': 'sora.ttf', 'dm': 'dmsans.ttf', 'mono': 'jetbrainsmono.ttf'}[name]
    try:
        f = ImageFont.truetype(str(path), max(6, size))
        try:
            axes = f.get_variation_axes()
            f.set_variation_by_axes([weight if 'eight' in str(a.get('name', '')) else a.get('default', 14) for a in axes])
        except Exception:  # noqa: BLE001 - static font or no variation support
            pass
        return f
    except OSError:
        return ImageFont.load_default(size)


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def text_w(f: ImageFont.FreeTypeFont, s: str, track: float = 0.0) -> float:
    if not track:
        return f.getlength(s)
    return sum(f.getlength(c) for c in s) + track * f.size * max(0, len(s) - 1)


def draw_text(d: ImageDraw.ImageDraw, x: float, y: float, s: str, f, fill, track: float = 0.0, anchor_top=True):
    """Draw with optional letter-spacing (em). (x, y) = left, top of the line box."""
    asc, _ = f.getmetrics()
    if not track:
        d.text((x, y + asc), s, font=f, fill=fill, anchor='ls')
        return
    for c in s:
        d.text((x, y + asc), c, font=f, fill=fill, anchor='ls')
        x += f.getlength(c) + track * f.size


def wrap(f, s: str, max_w: float) -> list[str]:
    words, lines, cur = s.split(), [], ''
    for w in words:
        t = f'{cur} {w}'.strip()
        if f.getlength(t) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


@functools.lru_cache(maxsize=8)
def _background(w: int, h: int, colors: tuple[str, str, str], s: float) -> Image.Image:
    """Radial glow (70% 90% at 50% 115%: c3 0, c2 30%, c1 52%, transparent 78%, opacity .9) + rings."""
    c1, c2, c3 = (np.array(hex_rgb(c), dtype=np.float32) for c in colors)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = np.sqrt(((xx - w * 0.5) / (0.7 * w)) ** 2 + ((yy - h * 1.15) / (0.9 * h)) ** 2)
    t = t[..., None]
    col = np.where(t < 0.30, c3 + (c2 - c3) * (t / 0.30),
                   np.where(t < 0.52, c2 + (c1 - c2) * ((t - 0.30) / 0.22), c1))
    a = np.clip(np.where(t < 0.52, 1.0, 1.0 - (t - 0.52) / 0.26), 0, 1) * 0.9
    bg = np.array(BG, dtype=np.float32)
    out = bg + (col - bg) * a
    img = Image.fromarray(out.clip(0, 255).astype(np.uint8), 'RGB').convert('RGBA')
    # Two thin rings rising from the bottom centre.
    ring = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ring)
    cy = h - 50 * s
    for r, alpha in ((380 * s, 0.35), (280 * s, 0.25)):
        d.ellipse((w / 2 - r, cy - r, w / 2 + r, cy + r), outline=GOLD + (int(255 * alpha),), width=max(1, round(2 * s)))
    return Image.alpha_composite(img, ring)


def render_slate(mode: str, w: int, h: int, remaining_s: float | None, info: Info) -> bytes:
    m = MODES.get(mode, MODES['Break'])
    vertical = h > w
    s = w / 760 if vertical else w / 1280
    img = _background(w, h, info.colors, s).copy()
    d = ImageDraw.Draw(img)

    # Centre column.
    y = (h * 0.24) if vertical else 120 * s
    gap = 18 * s
    pf = font('sora', round(15 * s), 600)
    pill_txt = m['pill']
    tw = text_w(pf, pill_txt, 0.12)
    dot, pad_x, pad_y = 8 * s, 16 * s, 8 * s
    pw = pad_x * 2 + dot + 12 * s + tw
    ph = pad_y * 2 + pf.size * 1.25
    px = (w - pw) / 2
    glass = Image.new('RGBA', img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glass).rounded_rectangle((px, y, px + pw, y + ph), radius=ph / 2, fill=(42, 22, 16, 178), outline=(245, 238, 230, 46), width=max(1, round(s)))
    img.alpha_composite(glass)
    d.ellipse((px + pad_x, y + ph / 2 - dot / 2, px + pad_x + dot, y + ph / 2 + dot / 2), fill=GOLD)
    draw_text(d, px + pad_x + dot + 12 * s, y + (ph - pf.size * 1.25) / 2 + 0.12 * pf.size, pill_txt, pf, TEXT, 0.12)
    y += ph + gap

    hf = font('sora', round(54 * s), 600)
    for line in wrap(hf, m['headline'], w - 64 * s):
        draw_text(d, (w - hf.getlength(line)) / 2, y, line, hf, TEXT)
        y += hf.size * 1.15
    y += gap

    if m['time']:
        rem = max(0, int(round(remaining_s or 0)))
        t = f'{rem // 60:02d}:{rem % 60:02d}'
        tf = font('mono', round(168 * s), 700)
        draw_text(d, (w - text_w(tf, t, -0.04)) / 2, y, t, tf, TEXT, -0.04)
        y += tf.size * 1.0 + gap
    else:
        sf = font('sora', round(40 * s), 700)
        for line in wrap(sf, f'Subscribe to {info.channel} for the next show', min(900 * s, w - 64 * s)):
            draw_text(d, (w - sf.getlength(line)) / 2, y, line, sf, SUB)
            y += sf.size * 1.2
        y += gap
    bf = font('sora', round(22 * s), 400)
    for line in wrap(bf, info.show_name, w - 64 * s):
        draw_text(d, (w - bf.getlength(line)) / 2, y + 8 * s, line, bf, META)
        y += bf.size * 1.3

    # Footer: now playing (left) and the mode line (right; centred on vertical).
    foot = info.foot.get(mode) or m['foot']
    ff = font('sora', round(16 * s), 400)
    fy = h - 40 * s - ff.size * 1.3
    if vertical:
        draw_text(d, (w - ff.getlength(foot)) / 2, fy, foot, ff, META)
        fy -= 70 * s
    else:
        draw_text(d, w - 48 * s - ff.getlength(foot), fy, foot, ff, META)
    if info.now_playing:
        lf = font('sora', round(13 * s), 600)
        nf = font('sora', round(18 * s), 600)
        block_y = fy - 6 * s if not vertical else fy
        x0 = 48 * s if not vertical else (w - max(text_w(lf, 'NOW PLAYING', 0.1), nf.getlength(info.now_playing))) / 2
        draw_text(d, x0, block_y - lf.size * 1.2, 'NOW PLAYING', lf, META, 0.1)
        draw_text(d, x0, block_y + 2 * s, info.now_playing, nf, TEXT)
    img.putalpha(255)
    return img.tobytes()


def render_strip(w: int, h: int, info: Info) -> bytes:
    """Band-view title strip: 'LIVE · <CHANNEL>' + song title, bottom aligned."""
    top, bot = np.array((0x16, 0x0C, 0x08), np.float32), np.array((0x0B, 0x06, 0x04), np.float32)
    g = (top + (bot - top) * np.linspace(0, 1, h, dtype=np.float32)[:, None])[:, None, :].repeat(w, 1)
    img = Image.fromarray(g.astype(np.uint8), 'RGB').convert('RGBA')
    d = ImageDraw.Draw(img)
    s = w / 224  # Show.tsx preview is 224 px wide
    pad = 10 * s
    lf = font('dm', round(9 * s), 800)
    sf = font('sora', round(13 * s), 800)
    lines = wrap(sf, info.song, w - 2 * pad)[:2] if info.song else []
    y = h - 8 * s - len(lines) * sf.size * 1.15
    for i, line in enumerate(lines):
        draw_text(d, pad, y + i * sf.size * 1.15, line, sf, TEXT)
    draw_text(d, pad, y - 2 * s - lf.size * 1.3, f'LIVE · {info.channel.upper()}', lf, GOLD, 0.12)
    img.putalpha(255)
    return img.tobytes()


def blank(w: int, h: int) -> bytes:
    return bytes(w * h * 4)
