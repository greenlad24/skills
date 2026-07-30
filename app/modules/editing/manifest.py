"""4D.2 — deterministic re-render manifest.

Captures every non-source input to the filtergraph (EDL frame boundaries, beat times,
ramp factors, mix levels, ASS path, font, FFmpeg version, and a hash of each source
asset) so re-running from the manifest with unchanged sources reproduces the render.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, is_dataclass
from pathlib import Path

from .config import EditingConfig
from .render import sha256_file
from .types import EDL, AlignResult


def ffmpeg_version() -> str:
    try:
        out = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, check=False
        )
        return (out.stdout or "").splitlines()[0] if out.stdout else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def _config_dict(cfg: EditingConfig) -> dict:
    def _d(x):
        return asdict(x) if is_dataclass(x) else x
    return {
        "render": _d(cfg.render),
        "caption": _d(cfg.caption),
        "disclosure": {**_d(cfg.disclosure), "window_s": list(cfg.disclosure.window_s)},
        "pacing": _d(cfg.pacing),
    }


def build_manifest(
    edl: EDL,
    align: AlignResult,
    cfg: EditingConfig,
    ass_path: str,
    hash_sources: bool = True,
) -> dict:
    source_hashes: dict[str, str] = {}
    if hash_sources:
        for shot in edl.shots:
            p = shot.source_path
            if p and Path(p).exists() and p not in source_hashes:
                try:
                    source_hashes[p] = sha256_file(p)
                except OSError:
                    source_hashes[p] = "unreadable"
    return {
        "job_id": edl.job_id,
        "ffmpeg_version": ffmpeg_version(),
        "config": _config_dict(cfg),
        "edl": edl.as_dict(),
        "align_meta": align.meta,
        "align_degraded": align.degraded,
        "ass_path": ass_path,
        "font": cfg.caption.font,
        "source_hashes": source_hashes,
    }


def write_manifest(path: str, manifest: dict) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=True)
    return path


def read_manifest(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
