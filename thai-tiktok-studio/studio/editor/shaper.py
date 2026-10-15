"""Correct Thai text drawing when Pillow can't shape it (usual on a Mac).

Pillow only places Thai vowel and tone marks correctly when its "raqm" layout works, which
needs the FriBiDi library — present on Linux, usually missing on a Mac. Without it, stacked
marks (ที่, น้ำ, ติ๊ก) are dropped or land in the wrong place. This module shapes the text with
HarfBuzz (the engine browsers use) and draws the glyphs with FreeType, fill + outline, so the
stickers look exactly like they're meant to on every computer.

Needs the small `uharfbuzz` and `freetype-py` packages; installed in the background the first
time they're missing (see ensure()). Until then Pillow's own drawing is used.
"""

from __future__ import annotations

import functools
import importlib
import importlib.util
import subprocess
import sys
import threading

from PIL import Image

_INSTALLING = threading.Lock()
_USE = threading.RLock()          # FreeType/HarfBuzz objects must never be used by two threads at once


def _marker():
    from .. import config
    return config.HOME / "thai_shaper_in_use"


def _off_flag():
    from .. import config
    return config.HOME / "thai_shaper_off"


def startup_check() -> None:
    """Called at app start: if the app died while drawing text last time, never use the shaper again."""
    m = _marker()
    if m.exists():
        try:
            _off_flag().write_text("crashed while drawing Thai text")
            m.unlink()
        except OSError:
            pass


def available() -> bool:
    if _off_flag().exists():
        return False
    return importlib.util.find_spec("uharfbuzz") is not None and importlib.util.find_spec("freetype") is not None


class _guard:
    """One drawing at a time + a crash marker around native code."""
    def __enter__(self):
        _USE.acquire()
        try:
            _marker().touch()
        except OSError:
            pass

    def __exit__(self, *a):
        try:
            _marker().unlink()
        except OSError:
            pass
        _USE.release()


def ensure(background: bool = True) -> None:
    """Install the shaping packages once (they're small wheels for every Mac)."""
    if available():
        return
    if not _INSTALLING.acquire(blocking=False):
        if not background:            # someone else is installing: wait for it to finish
            with _INSTALLING:
                pass
        return

    def run():
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--prefer-binary", "uharfbuzz", "freetype-py"],
                           capture_output=True, timeout=600)
            importlib.invalidate_caches()
        finally:
            _INSTALLING.release()
    threading.Thread(target=run, daemon=True).start() if background else run()


@functools.lru_cache(maxsize=32)
def _faces(path: str, size: int):
    import freetype
    import uharfbuzz as hb
    data = open(path, "rb").read()
    hb_font = hb.Font(hb.Face(hb.Blob(data)))
    hb_font.scale = (size * 64, size * 64)
    ft = freetype.Face(path)
    ft.set_char_size(size * 64)
    return hb_font, ft


def _shape(path: str, size: int, text: str):
    import uharfbuzz as hb
    hb_font, _ = _faces(path, size)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hb_font, buf, {"kern": True, "liga": True})
    return buf.glyph_infos, buf.glyph_positions


def length(path: str, size: int, text: str) -> float:
    with _guard():
        _, pos = _shape(path, size, text)
        return sum(p.x_advance for p in pos) / 64.0


def draw(img: Image.Image, xy, text: str, path: str, size: int, ascent: int, fill, stroke=None, stroke_w: int = 0):
    """Draw text onto an RGBA image at xy (top-left like Pillow's d.text), baseline = y + ascent."""
    with _guard():
        _draw(img, xy, text, path, size, ascent, fill, stroke, stroke_w)


def _draw(img, xy, text, path, size, ascent, fill, stroke, stroke_w):
    import freetype
    infos, pos = _shape(path, size, text)
    _, ft = _faces(path, size)
    x = xy[0] * 64.0
    base_y = xy[1] + ascent
    layers = []                                    # (order, mask image, left, top, colour) — copied out of FreeType at once

    def grab(bg, order, col, gx, gy):
        bm = bg.bitmap
        if bm.width and bm.rows:
            mask = Image.frombytes("L", (bm.width, bm.rows), bytes(bm.buffer), "raw", "L", bm.pitch)
            layers.append((order, mask, gx + bg.left, gy - bg.top, col))

    for info, p in zip(infos, pos):
        gx = (x + p.x_offset) / 64.0
        gy = base_y - p.y_offset / 64.0
        ft.load_glyph(info.codepoint, freetype.FT_LOAD_DEFAULT | freetype.FT_LOAD_NO_BITMAP)
        if stroke is not None and stroke_w > 0:
            g = ft.glyph.get_glyph()
            st = freetype.Stroker()
            st.set(int(stroke_w * 64), freetype.FT_STROKER_LINECAP_ROUND, freetype.FT_STROKER_LINEJOIN_ROUND, 0)
            g.stroke(st, True)
            grab(g.to_bitmap(freetype.FT_RENDER_MODE_NORMAL, freetype.Vector(0, 0), True), 0, stroke, gx, gy)
        g2 = ft.glyph.get_glyph()
        grab(g2.to_bitmap(freetype.FT_RENDER_MODE_NORMAL, freetype.Vector(0, 0), True), 1, fill, gx, gy)
        x += p.x_advance
    for _, mask, left, top, col in sorted(layers, key=lambda l: l[0]):   # all outlines first, then fills
        col = tuple(col) + ((255,) if len(col) == 3 else ())
        a = mask.point(lambda v, k=col[3]: v * k // 255)
        tile = Image.new("RGBA", mask.size, col[:3] + (0,))
        tile.putalpha(a)
        _paste(img, tile, int(round(left)), int(round(top)))


def _paste(img: Image.Image, tile: Image.Image, x: int, y: int) -> None:
    """alpha_composite that tolerates glyphs hanging off the edge."""
    sx, sy = max(0, -x), max(0, -y)
    w, h = min(tile.width - sx, img.width - max(0, x)), min(tile.height - sy, img.height - max(0, y))
    if w <= 0 or h <= 0:
        return
    if sx or sy or w < tile.width or h < tile.height:
        tile = tile.crop((sx, sy, sx + w, sy + h))
    img.alpha_composite(tile, (max(0, x), max(0, y)))
