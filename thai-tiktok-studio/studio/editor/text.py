"""Thai text → RGBA sprites (Pillow + libraqm shaping so tone marks sit correctly)."""

from __future__ import annotations

import functools
import os
import re
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

from ..config import FONTS_DIR

FONT_FILES = {
    ("kanit", "black"): "Kanit-Black.ttf", ("kanit", "xbold"): "Kanit-ExtraBold.ttf",
    ("kanit", "bold"): "Kanit-Bold.ttf", ("kanit", "medium"): "Kanit-Medium.ttf",
    ("prompt", "black"): "Prompt-ExtraBold.ttf", ("prompt", "xbold"): "Prompt-ExtraBold.ttf",
    ("prompt", "bold"): "Prompt-Bold.ttf", ("prompt", "medium"): "Prompt-Bold.ttf",
    ("mitr", "any"): "Mitr-SemiBold.ttf", ("chakra", "any"): "ChakraPetch-Bold.ttf",
    ("mali", "any"): "Mali-Bold.ttf", ("itim", "any"): "Itim-Regular.ttf",
}
EMOJI_FONTS = [
    ("/System/Library/Fonts/Apple Color Emoji.ttc", 160),
    ("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 109),
    ("/usr/share/fonts/noto/NotoColorEmoji.ttf", 109),
]
LAYOUT = ImageFont.Layout.RAQM if features.check("raqm") else ImageFont.Layout.BASIC

# Emoji / pictographs are drawn with the emoji font, never with the Thai font.
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF⬀-⯿️‍←-⇿⌀-⏿]+"
)
COMBINING = set(range(0x0E34, 0x0E3B)) | {0x0E31} | set(range(0x0E47, 0x0E4F))


def strip_emoji(s: str) -> str:
    return re.sub(r"\s{2,}", " ", EMOJI_RE.sub("", s or "")).strip()


def first_emoji(s: str) -> str:
    m = EMOJI_RE.search(s or "")
    return m.group(0) if m else ""


@functools.lru_cache(maxsize=256)
def font(family: str, weight: str, size: int) -> ImageFont.FreeTypeFont:
    fname = FONT_FILES.get((family, weight)) or FONT_FILES.get((family, "any")) or FONT_FILES[("kanit", "bold")]
    path = FONTS_DIR / fname
    if not path.exists():  # macOS system fallbacks
        for p in ("/System/Library/Fonts/Supplemental/Sukhumvit Set.ttc", "/System/Library/Fonts/Thonburi.ttc"):
            if os.path.exists(p):
                path = Path(p)
                break
    return ImageFont.truetype(str(path), size=size, layout_engine=LAYOUT)


@functools.lru_cache(maxsize=64)
def _emoji_font():
    for path, size in EMOJI_FONTS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size), size
            except OSError:
                continue
    return None, 0


def emoji_sprite(emoji: str, size: int) -> Image.Image | None:
    f, native = _emoji_font()
    if not f or not emoji:
        return None
    img = Image.new("RGBA", (native * 3, native * 2), (0, 0, 0, 0))
    try:
        ImageDraw.Draw(img).text((native // 4, native // 4), emoji, font=f, embedded_color=True)
    except Exception:
        return None
    bbox = img.getbbox()
    if not bbox:
        return None
    img = img.crop(bbox)
    scale = size / max(img.height, 1)
    return img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)


def safe_splits(text: str, subs: list) -> list:
    """Split text into [(chunk, highlighted)] runs; never start a run with a combining mark."""
    marks = [False] * len(text)
    for h in subs:
        if not h:
            continue
        start = 0
        while True:
            i = text.find(h, start)
            if i < 0:
                break
            j = i + len(h)
            while j < len(text) and ord(text[j]) in COMBINING:  # keep marks with their base
                j += 1
            for k in range(i, j):
                marks[k] = True
            start = j
    runs = []
    for ch, m in zip(text, marks):
        if runs and runs[-1][1] == m:
            runs[-1][0] += ch
        elif runs and ord(ch) in COMBINING:
            runs[-1][0] += ch
        else:
            runs.append([ch, m])
    return [(r[0], r[1]) for r in runs]


def wrap(text: str, fnt, max_w: int, max_lines: int = 2) -> list:
    """Wrap on spaces (Thai uses spaces between phrases). Returns lines or [] if it can't fit."""
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if fnt.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines or any(fnt.getlength(l) > max_w for l in lines):
        return []
    return lines


def fit_lines(text, family, weight, size, max_w, max_lines=2, min_size=40):
    """Largest font size (≤ size) whose wrapped lines fit inside max_w."""
    s = size
    while s >= min_size:
        f = font(family, weight, s)
        lines = wrap(text, f, max_w, max_lines)
        if lines:
            return f, lines
        s -= 4
    f = font(family, weight, min_size)
    return f, [text]


def text_block(
    text: str,
    family: str = "kanit",
    weight: str = "xbold",
    size: int = 80,
    max_w: int = 840,
    max_lines: int = 2,
    fill=(255, 255, 255, 255),
    stroke=(0, 0, 0, 255),
    stroke_w: int | None = None,
    highlight: list | None = None,
    hl_fill=(255, 230, 0, 255),
    align: str = "center",
    shadow: bool = True,
    line_gap: float = -0.18,
) -> Image.Image:
    """Multi-line stroked text with optional highlighted substrings, tightly cropped."""
    text = unicodedata.normalize("NFC", strip_emoji(text))
    if not text:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    f, lines = fit_lines(text, family, weight, size, max_w, max_lines)
    sw = stroke_w if stroke_w is not None else (max(3, int(f.size * 0.10)) if stroke else 0)
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * (1 + line_gap))
    widths = [int(f.getlength(l)) for l in lines]
    pad = sw + 12
    W = max(widths) + pad * 2
    H = lh * len(lines) + pad * 2 + desc // 2
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        x = pad if align == "left" else pad + (max(widths) - widths[i]) // 2
        y = pad + i * lh
        for chunk, hl in safe_splits(line, highlight or []):
            col = hl_fill if hl else fill
            d.text((x, y), chunk, font=f, fill=col, stroke_width=sw, stroke_fill=stroke if sw else None)
            x += int(f.getlength(chunk))
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        alpha = img.getchannel("A").point(lambda a: int(a * 0.45))
        sh.putalpha(alpha)
        sh = sh.filter(ImageFilter.GaussianBlur(6))
        out = Image.new("RGBA", (W + 8, H + 10), (0, 0, 0, 0))
        out.alpha_composite(sh, (4, 8))
        out.alpha_composite(img, (0, 0))
        img = out
    bb = img.getbbox()
    return img.crop(bb) if bb else img


def rounded_box(size, radius, fill, outline=None, width=0) -> Image.Image:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=fill,
                                          outline=outline, width=width)
    return img


def boxed(content: Image.Image, fill, pad_x=34, pad_y=18, radius=26, outline=None, width=0,
          shadow=True) -> Image.Image:
    W, H = content.width + pad_x * 2, content.height + pad_y * 2
    box = rounded_box((W, H), radius, fill, outline, width)
    box.alpha_composite(content, (pad_x, pad_y))
    if not shadow:
        return box
    out = Image.new("RGBA", (W + 16, H + 20), (0, 0, 0, 0))
    sh = rounded_box((W, H), radius, (0, 0, 0, 110)).filter(ImageFilter.GaussianBlur(7))
    out.alpha_composite(sh, (8, 14))
    out.alpha_composite(box, (4, 2))
    return out


def hstack(images: list, gap: int = 12, valign: str = "center") -> Image.Image:
    images = [i for i in images if i is not None]
    if not images:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    W = sum(i.width for i in images) + gap * (len(images) - 1)
    H = max(i.height for i in images)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x = 0
    for i in images:
        y = (H - i.height) // 2 if valign == "center" else 0
        out.alpha_composite(i, (x, y))
        x += i.width + gap
    return out


def vstack(images: list, gap: int = 10, align: str = "center") -> Image.Image:
    images = [i for i in images if i is not None]
    if not images:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    W = max(i.width for i in images)
    H = sum(i.height for i in images) + gap * (len(images) - 1)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    y = 0
    for i in images:
        x = (W - i.width) // 2 if align == "center" else 0
        out.alpha_composite(i, (x, y))
        y += i.height + gap
    return out
