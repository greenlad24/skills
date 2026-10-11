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


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", **kw)
