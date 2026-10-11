"""Your editing style, learned from a reference video you posted and liked.

The built-in profile comes from the creator's own best edit (a 22 s home-organiser video):
7 calm shots, smooth handheld camera moves, no zoom punches / shakes / flashes, one small
text card at the top (headline first, then a feature list with emojis and ↓ arrows).

Uploading another reference video in Settings replaces it: we measure its cut rhythm and
save a frames sheet, and Claude copies that pacing and look when it plans each edit.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from PIL import Image

from .. import config
from . import media

DEFAULT_PROFILE = {
    "source": "built-in (your posted closet-rack video)",
    "duration": 21.9,
    "shots": 7,
    "avg_shot": 3.1,
    "min_shot": 1.3,
    "max_shot": 6.3,
    "calm": True,
    "notes": [
        "Hook: the product moves toward the lens in the first second, then the creator is seen with it.",
        "Shots are held 2.5-6 s; one quick 1-2 s insert between longer shots. No zoom punches, shakes or flashes — "
        "only the smooth handheld camera movement already in the clips.",
        "Text: ONE small card at the top (red text, white outline, no box). A short headline for the first ~8 s, "
        "then a feature list (an emoji per line, last line 'who is it for', ↓ arrows to the basket) until the end.",
        "Shows the product in a real home: empty product → product in use full of things → close details.",
        "Ends on the creator presenting the product in its place.",
    ],
}


def style_dir() -> Path:
    d = config.HOME / "style"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load() -> dict:
    p = style_dir() / "profile.json"
    if p.exists():
        try:
            prof = dict(DEFAULT_PROFILE, **json.loads(p.read_text("utf-8")))
            return prof
        except (OSError, ValueError):
            pass
    return dict(DEFAULT_PROFILE)


def sheet_path() -> Path | None:
    p = style_dir() / "reference_frames.jpg"
    return p if p.exists() else None


def cuts(path) -> list:
    """Hard cuts (seconds) by scene change."""
    p = subprocess.run([media.ffmpeg_exe(), "-hide_banner", "-i", str(path), "-an", "-vf",
                        "select='gt(scene,0.3)',metadata=print", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace")
    return [float(x) for x in re.findall(r"pts_time:([\d.]+)", p.stderr)]


def frames_sheet(path, out: Path, n: int = 12) -> Path | None:
    dur = media.probe(path)["duration"] or 1
    tiles = []
    for k in range(n):
        t = dur * (k + 0.5) / n
        p = subprocess.run([media.ffmpeg_exe(), "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
                            "-vf", "scale=180:-2", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        if p.returncode == 0 and p.stdout:
            import io
            tiles.append(Image.open(io.BytesIO(p.stdout)).convert("RGB"))
    if not tiles:
        return None
    cols = 6
    w, h = tiles[0].size
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), (0, 0, 0))
    for i, im in enumerate(tiles):
        sheet.paste(im.resize((w, h)), ((i % cols) * w, (i // cols) * h))
    sheet.save(out, quality=85)
    return out


def analyze(path) -> dict:
    info = media.probe(path)
    dur = info["duration"]
    c = [x for x in cuts(path) if 0.3 < x < dur - 0.3]
    bounds = [0.0] + c + [dur]
    shots = [b - a for a, b in zip(bounds, bounds[1:])]
    return {
        "source": Path(path).name,
        "duration": round(dur, 1),
        "shots": len(shots),
        "avg_shot": round(sum(shots) / len(shots), 2),
        "min_shot": round(min(shots), 2),
        "max_shot": round(max(shots), 2),
        "calm": sum(shots) / len(shots) >= 2.2,
        "notes": [f"Cut points in the reference: {', '.join(f'{x:.1f}s' for x in c) or 'one continuous shot'}."],
    }


def save_reference(path: Path) -> dict:
    prof = analyze(path)
    frames_sheet(path, style_dir() / "reference_frames.jpg")
    (style_dir() / "profile.json").write_text(json.dumps(prof, ensure_ascii=False, indent=1), "utf-8")
    return load()


def reset() -> dict:
    for name in ("profile.json", "reference_frames.jpg"):
        (style_dir() / name).unlink(missing_ok=True)
    return load()


def describe(prof: dict) -> str:
    lines = [f"Reference: {prof['source']} — {prof['duration']} s, {prof['shots']} shots "
             f"(average {prof['avg_shot']} s, shortest {prof['min_shot']} s, longest {prof['max_shot']} s)."]
    lines += [f"- {n}" for n in prof.get("notes", [])]
    if not prof.get("calm"):
        lines.append("- This reference is fast-paced: short shots, punch-ins allowed on emphasis.")
    return "\n".join(lines)
