"""Decode any audio to mono float32 @48 kHz via ffmpeg, and write WAVs."""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

from .media import ffmpeg_exe

SR = 48000


def decode(path, start: float = 0.0, dur: float | None = None, channels: int = 1) -> np.ndarray | None:
    cmd = [ffmpeg_exe(), "-v", "error"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path)]
    if dur:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-vn", "-ac", str(channels), "-ar", str(SR), "-f", "f32le", "-"]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0 or not p.stdout:
        return None
    y = np.frombuffer(p.stdout, dtype=np.float32)
    return y.reshape(-1, channels) if channels > 1 else y


def write_wav(path: Path, y: np.ndarray) -> None:
    y = np.clip(y, -1, 1)
    if y.ndim == 1:
        y = np.stack([y, y], axis=1)
    pcm = (y * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
