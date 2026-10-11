"""Thai voice-over: macOS `say` (free, offline, voice 'Kanya'). Falls back to silence."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import numpy as np

from . import audio_io


def available(voice: str = "Kanya") -> bool:
    if not shutil.which("say"):
        return False
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return any(line.split()[0] == voice for line in out.splitlines() if line.strip())


def estimate_seconds(text: str) -> float:
    """Rough Thai speech duration when no TTS engine exists (≈ 11 Thai chars/sec)."""
    thai = len(re.sub(r"[ัิ-ฺ็-๎\s]", "", text or ""))
    return max(0.6, thai / 11.0 + 0.2)


def synth(text: str, out_wav: Path, voice: str = "Kanya", rate: int = 185) -> np.ndarray | None:
    """→ mono float32 @48k, or None if TTS is unavailable."""
    if not text.strip() or not shutil.which("say"):
        return None
    aiff = out_wav.with_suffix(".aiff")
    try:
        subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", str(aiff), text], check=True,
                       capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    y = audio_io.decode(aiff)
    if y is None:
        return None
    # trim leading/trailing near-silence so beats stay tight
    idx = np.where(np.abs(y) > 0.01)[0]
    if len(idx):
        y = y[max(0, idx[0] - 800): idx[-1] + 2400]
    return y
