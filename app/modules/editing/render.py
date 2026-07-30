"""Render execution — the real FFmpeg subprocess path + a DRY_RUN placeholder path.

The filtergraph/command *builders* live in ``filtergraph.py`` (pure). This module runs
them. In ``DRY_RUN`` it produces a tiny, valid-enough placeholder MP4 without invoking
any heavy processing, so the pipeline runs for free in CI / rehearsal (§1.6 contract).
"""

from __future__ import annotations

import hashlib
import shutil
import struct
import subprocess
from pathlib import Path

from .config import CONFIG, EditingConfig
from .filtergraph import build_burn_command, build_cut_command
from .types import EDL


class RenderError(RuntimeError):
    """Raised on any FFmpeg / probe failure (worker maps this to JobState.FAILED)."""


# --------------------------------------------------------------------------- #
# DRY_RUN placeholder MP4 (no ffmpeg, no heavy processing)
# --------------------------------------------------------------------------- #
def _box(box_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + box_type + payload


def write_placeholder_mp4(path: str) -> str:
    """Write a minimal, structurally-valid MP4 (ftyp + free) as a DRY_RUN placeholder.

    It is intentionally tiny (no real video track): enough that downstream code sees an
    ``.mp4`` with a proper ``ftyp`` brand and a ``moov``-before-``mdat``-style layout,
    without running any codec. Deterministic (identical bytes every run) for T-9.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    ftyp = _box(b"ftyp", b"isom" + struct.pack(">I", 0x200) + b"isomiso2mp41")
    # A short free box carrying a marker so the file is recognizably our placeholder.
    free = _box(b"free", b"AUTOUGC-TH DRY_RUN placeholder mp4")
    data = ftyp + free
    with open(path, "wb") as fh:
        fh.write(data)
    return path


# --------------------------------------------------------------------------- #
# Command execution
# --------------------------------------------------------------------------- #
def run_cmd(args: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    """Run a subprocess, raising ``RenderError`` with the stderr tail on non-zero exit."""
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError as exc:  # ffmpeg/ffprobe missing = build defect (§4E)
        raise RenderError(f"binary not found: {args[0]} ({exc})") from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderError(f"{args[0]} timed out after {timeout}s") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-2000:]
        raise RenderError(f"{args[0]} exited {proc.returncode}:\n{tail}")
    return proc


# --------------------------------------------------------------------------- #
# Public render entry points
# --------------------------------------------------------------------------- #
def ffmpeg_render_cut(
    edl: EDL,
    out_path: str,
    cfg: EditingConfig = CONFIG,
    disclosure_ass: str | None = None,
    dry_run: bool = False,
) -> str:
    """Render the cut (``output/final.mp4``): §4A.8. DRY_RUN -> placeholder."""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        return write_placeholder_mp4(out_path)
    args = build_cut_command(edl, out_path, cfg, disclosure_ass)
    run_cmd(args)
    return out_path


def ffmpeg_burn_ass(
    base_path: str,
    ass_path: str,
    out_path: str,
    cfg: EditingConfig = CONFIG,
    dry_run: bool = False,
) -> str:
    """Burn ``captions.ass`` over ``final.mp4`` (§4B.5). DRY_RUN -> copy base."""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        # No re-encode in DRY_RUN: the captioned variant is a copy of the placeholder.
        if Path(base_path).exists():
            shutil.copyfile(base_path, out_path)
        else:
            write_placeholder_mp4(out_path)
        return out_path
    args = build_burn_command(base_path, ass_path, out_path, cfg)
    run_cmd(args)
    return out_path


# --------------------------------------------------------------------------- #
# ffprobe helpers (acceptance T-1) + source integrity (§4D.4)
# --------------------------------------------------------------------------- #
def probe_source(path: str) -> None:
    """Fail fast on a missing/corrupt source clip (§4D.4). No-op if ffprobe absent."""
    if not Path(path).exists():
        raise RenderError(f"source clip missing: {path}")
    if Path(path).stat().st_size == 0:
        raise RenderError(f"source clip is empty: {path}")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
