"""ffmpeg discovery + media probing (parses `ffmpeg -i`, so no ffprobe is needed)."""

from __future__ import annotations

import functools
import re
import shutil
import subprocess
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".3gp", ".hevc"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".aiff", ".aif", ".ogg", ".flac"}


@functools.lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg  # bundled static build — works on macOS 10.9+ Intel
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe:
            return exe
    except Exception:
        pass
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    raise RuntimeError("ffmpeg not found. Re-run the installer (start.command).")


def kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    return "other"


@functools.lru_cache(maxsize=512)
def _probe_cached(path: str, mtime: float) -> dict:
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path], capture_output=True, text=True,
                       errors="replace")
    err = p.stderr
    info = {"duration": 0.0, "has_video": False, "has_audio": False, "width": 0, "height": 0, "fps": 30.0}
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        info["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    for line in err.splitlines():
        if "Stream #" in line and "Video:" in line and "attached pic" not in line and not info["has_video"]:
            info["has_video"] = True
            sm = re.search(r"\b(\d{2,5})x(\d{2,5})\b", line)
            if sm:
                info["width"], info["height"] = int(sm.group(1)), int(sm.group(2))
            fm = re.search(r"([\d.]+)\s*fps", line)
            if fm:
                info["fps"] = float(fm.group(1))
        if "Stream #" in line and "Audio:" in line:
            info["has_audio"] = True
    rot = re.search(r"rotation of (-?\d+(?:\.\d+)?)", err) or re.search(r"rotate\s*:\s*(-?\d+)", err)
    if rot and abs(float(rot.group(1))) % 180 == 90:
        info["width"], info["height"] = info["height"], info["width"]
    return info


def probe(path) -> dict:
    p = Path(path)
    return dict(_probe_cached(str(p), p.stat().st_mtime))


_TIME_RE = re.compile(r"(com\.apple\.quicktime\.creationdate|creation_time)\s*:\s*(\S+)")


@functools.lru_cache(maxsize=512)
def _capture_cached(path: str, mtime: float):
    from datetime import datetime
    p = Path(path)
    stamp = None
    if kind(p) == "image":
        try:
            from PIL import Image
            exif = Image.open(p).getexif()
            raw = exif.get_ifd(0x8769).get(36867) or exif.get(306)  # DateTimeOriginal / DateTime
            if raw:
                stamp = datetime.strptime(str(raw)[:19], "%Y:%m:%d %H:%M:%S").timestamp()
        except Exception:
            pass
    else:
        err = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path], capture_output=True, text=True,
                             errors="replace").stderr
        found = {k: v for k, v in _TIME_RE.findall(err)}
        raw = found.get("com.apple.quicktime.creationdate") or found.get("creation_time")
        m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.\d+)?(Z|[+-]\d\d:?\d\d)?", raw or "")
        if m:
            tz = (m.group(2) or "Z").replace("Z", "+00:00")
            if len(tz) == 5:  # +0700 → +07:00
                tz = tz[:3] + ":" + tz[3:]
            try:
                stamp = datetime.fromisoformat(m.group(1) + tz).timestamp()
            except ValueError:
                pass
    if stamp and stamp < 946684800:  # before 2000 → camera clock not set
        stamp = None
    return stamp


def capture_time(path):
    """When the clip/photo was actually recorded (metadata), or None."""
    p = Path(path)
    return _capture_cached(str(p), p.stat().st_mtime)


def speech_islands(path, min_silence: float = 0.4, noise_db: int = -32) -> list:
    """[(start, end)] of non-silent audio. Used to trim talking clips and remove pauses."""
    info = probe(path)
    if not info["has_audio"] or info["duration"] <= 0:
        return []
    p = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-nostats", "-i", str(path), "-vn",
         "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True, errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", p.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", p.stderr)]
    dur = info["duration"]
    silences = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else dur
        silences.append((max(0.0, s), min(dur, e)))
    islands, cur = [], 0.0
    for s, e in silences:
        if s - cur > 0.12:
            islands.append((cur, s))
        cur = e
    if dur - cur > 0.12:
        islands.append((cur, dur))
    return islands


@functools.lru_cache(maxsize=512)
def _bars_cached(path: str, mtime: float) -> str:
    info = probe(path)
    w, h = info["width"], info["height"]
    if not w or not h:
        return ""
    image = kind(Path(path)) == "image"
    starts = [None] if image else [info["duration"] * k for k in (0.15, 0.5, 0.85)]
    best = None
    for t in starts:
        cmd = [ffmpeg_exe(), "-hide_banner", "-nostats"]
        if t is not None:
            cmd += ["-ss", f"{t:.2f}"]
        cmd += ["-i", path, "-frames:v", "1" if image else "12", "-vf", "cropdetect=limit=24:round=2:reset=0",
                "-an", "-f", "null", "-"]
        found = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", subprocess.run(
            cmd, capture_output=True, text=True, errors="replace").stderr)
        if not found:
            return ""        # can't tell → never crop
        cw, ch, cx, cy = map(int, found[-1])
        if best is None or cw * ch > best[0] * best[1]:
            best = (cw, ch, cx, cy)   # the largest picture seen: a dark frame must not crop real footage
    cw, ch, cx, cy = best
    if cw < w * 0.2 or ch < h * 0.2 or (cw > w * 0.94 and ch > h * 0.94):
        return ""
    return f"crop={cw}:{ch}:{cx}:{cy}"


def black_bars(path) -> str:
    """'crop=w:h:x:y' when the picture has black bars baked in (e.g. a sideways video re-saved by a chat app), else ''."""
    p = Path(path)
    try:
        return _bars_cached(str(p), p.stat().st_mtime)
    except Exception:
        return ""


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", **kw)
