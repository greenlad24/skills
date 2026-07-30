"""4C — AI-generated disclosure overlay.

TikTok Shop requires a **visible "AI-generated" disclosure in the first 3 seconds**.
The module's default (see ``captions.build_disclosure_ass`` + ``filtergraph``) bakes a
libass disclosure into ``final.mp4`` — Thai-correct and a single source of truth.

This file provides the *alternative* PNG-overlay mechanism from §4C (a pre-rendered
plate gated with ``enable='between(t,0,3)'``) for callers who need the label as an image
overlay rather than a subtitle. The PNG is rendered with PIL (lazy) so Thai glyphs stack
correctly; ``drawtext`` is deliberately NOT used.
"""

from __future__ import annotations

from .config import CONFIG, EditingConfig


def disclosure_overlay_filter(
    badge_input_label: str = "badge_png",
    base_label: str = "vraw",
    out_label: str = "vout",
    x: int = 48,
    y: int = 60,
    window_s: tuple[float, float] = (0.0, 3.0),
) -> str:
    """Filtergraph fragment overlaying a PNG plate for the disclosure window (§4C).

        [vraw][badge_png]overlay=48:60:enable='between(t,0,3)'[vout]
    """
    start, end = window_s
    return (
        f"[{base_label}][{badge_input_label}]"
        f"overlay={x}:{y}:enable='between(t,{start:g},{end:g})'[{out_label}]"
    )


def build_disclosure_png(
    out_path: str,
    cfg: EditingConfig = CONFIG,
    padding: int = 24,
) -> str:
    """Render the dual Thai+EN disclosure plate to a transparent PNG (PIL, lazy).

    Returns ``out_path``. Raises RuntimeError if PIL / the Thai font are unavailable —
    that is a build defect (§4E), surfaced with an actionable message.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont  # lazy optional dep
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Pillow is required for the PNG-overlay disclosure variant; either install "
            "it or use the default libass disclosure (disclosure.in_base via ASS)."
        ) from exc

    text = cfg.disclosure.text
    size = cfg.disclosure.size
    font = _load_thai_font(ImageFont, cfg, size)

    # Measure text
    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    img = Image.new("RGBA", (tw + 2 * padding, th + 2 * padding), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Semi-transparent plate + high-contrast white text.
    draw.rounded_rectangle(
        [(0, 0), (img.width - 1, img.height - 1)], radius=12, fill=(0, 0, 0, 160)
    )
    draw.text((padding - bbox[0], padding - bbox[1]), text, font=font,
              fill=(255, 255, 255, 255))
    img.save(out_path, "PNG")
    return out_path


def _load_thai_font(ImageFont, cfg: EditingConfig, size: int):
    import os

    candidates = [
        os.path.join(cfg.caption.fontsdir, "NotoSansThai-Bold.ttf"),
        os.path.join(cfg.caption.fontsdir, "NotoSansThai-Regular.ttf"),
        os.path.join(cfg.caption.fontsdir, "Sarabun-Bold.ttf"),
    ]
    for path in candidates:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001
            continue
    try:
        return ImageFont.truetype("NotoSansThai-Regular.ttf", size)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"No Thai font found in {cfg.caption.fontsdir} for the disclosure plate "
            f"(build defect, §4E)."
        ) from exc
