"""Keep every clip upright — the file's own rotation data first, then Claude's eyes.

1. Photos: the EXIF "orientation" tag is applied (phones store many photos sideways and
   only mark them as rotated); an upright copy is used for both the AI and the render.
2. Videos: ffmpeg already applies the rotation recorded by the phone.
3. Vision check: some clips have no (or wrong) rotation data — e.g. the phone was held
   upside down. Claude looks at 3 frames of every clip exactly as they will be rendered and
   says how far each must be turned to be upright. The answer is cached per file, so each
   clip is only checked once.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageOps

ROTATIONS = (0, 90, 180, 270)

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["clips"],
    "properties": {"clips": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["id", "rotate"],
        "properties": {
            "id": {"type": "string"},
            "rotate": {"type": "string", "enum": ["0", "90", "180", "270"],
                       "description": "Degrees CLOCKWISE to turn this clip so it is upright."},
        }}}},
}


def file_key(path: str) -> str:
    p = Path(path)
    st = p.stat()
    return hashlib.sha1(f"{p.name}|{st.st_size}|{st.st_mtime}".encode()).hexdigest()[:16]


def upright_photo(path: str, out_dir: Path) -> str:
    """Apply EXIF orientation; returns the original path when nothing needs turning."""
    try:
        im = Image.open(path)
        if im.getexif().get(0x0112, 1) in (None, 1):
            return path
        fixed = ImageOps.exif_transpose(im).convert("RGB")
    except Exception:
        return path
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{Path(path).stem}_{file_key(path)}.jpg"
    if not out.exists():
        fixed.save(out, quality=94)
    return str(out)


def turn_image(src: Path, degrees: int, out: Path) -> Path:
    """Clockwise turn of a frames sheet, so the editor AI sees the corrected clip."""
    Image.open(src).rotate(-degrees, expand=True).save(out, quality=82)
    return out


def ffmpeg_filter(degrees: int) -> str:
    return {90: "transpose=1", 180: "hflip,vflip", 270: "transpose=2"}.get(int(degrees) % 360, "")


PROMPT = """You check phone footage before it is edited into a vertical TikTok video.
Each image shows frames from ONE clip or photo, labelled with its id in the top-left corner
(ignore the label's own orientation — judge the PICTURE).
For every clip decide how many degrees CLOCKWISE it must be turned so the scene is upright the way a
person would see it: people's heads up, floors and tables at the bottom, furniture standing, text readable.
Answer "0" when it is already upright. Only answer 90/180/270 when the picture is clearly sideways or
upside down (a close-up with no clear up/down is "0").
Clips: {ids}
Reply with ONE JSON object: {{"clips":[{{"id":"C1","rotate":"0"}}, ...]}}"""


def check(clips: list, sheets: dict, settings: dict, cache_file: Path, log) -> dict:
    """→ {clip_id: degrees}. Uses the cache; asks Claude only about clips not seen before."""
    cache = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text("utf-8"))
        except ValueError:
            cache = {}
    out, todo = {}, []
    for c in clips:
        k = file_key(c.path)
        if k in cache:
            out[c.id] = int(cache[k])
        elif c.id in sheets:
            todo.append(c)
    if todo:
        from ..planner import _provider
        mod = _provider(settings.get("provider", "claude_code"))
        log(f"Claude is checking {len(todo)} clip(s) are the right way up…")
        got = mod.make_edl(PROMPT.format(ids=", ".join(c.id for c in todo)),
                           [sheets[c.id] for c in todo], SCHEMA, settings, log=log,
                           workdir=cache_file.parent)
        ans = {str(x.get("id", "")).strip().upper(): x.get("rotate") for x in (got or {}).get("clips", [])}
        for c in todo:
            try:
                deg = int(ans.get(c.id, 0)) % 360
            except (TypeError, ValueError):
                deg = 0
            deg = deg if deg in ROTATIONS else 0
            out[c.id] = cache[file_key(c.path)] = deg
            if deg:
                log(f"{Path(c.path).name} was {'upside down' if deg == 180 else 'sideways'} — turned it upright.")
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache, indent=1), "utf-8")
    return out
