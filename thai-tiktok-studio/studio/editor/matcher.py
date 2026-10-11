"""Match dropped files to shot ids: by filename first, then by recording order."""

from __future__ import annotations

import re
from pathlib import Path

from . import media

ID_RE = re.compile(r"(?<![a-z0-9])v\s*(\d{1,2})\s*[-_. ]?\s*s\s*(\d{1,3})(?![0-9])", re.I)
VO_RE = re.compile(r"(?<![a-z0-9])v\s*(\d{1,2})\s*[-_. ]?\s*(vo|voice|เสียง)", re.I)


def id_from_name(name: str) -> str:
    m = ID_RE.search(Path(name).stem)
    return f"V{int(m.group(1))}-S{int(m.group(2)):02d}" if m else ""


def vo_video_from_name(name: str) -> str:
    m = VO_RE.search(Path(name).stem)
    return f"V{int(m.group(1))}" if m else ""


def auto_match(plan: dict, files: list, existing: dict | None = None) -> dict:
    """→ {"shots": {shot_id: filename}, "vo": {video_id: filename}, "music": [filenames], "unmatched": [...]}

    Manual assignments in `existing` are kept. Files without a shot id in their name are
    assigned to still-empty shots in filming order (sorted by file modified time), which
    matches how people usually record the shot list top to bottom.
    """
    existing = existing or {}
    shots_map = dict(existing.get("shots", {}))
    vo_map = dict(existing.get("vo", {}))
    music = list(existing.get("music", []))
    all_shots = [s["id"] for v in plan["videos"] for s in v["shots"]]
    used = set(shots_map.values()) | set(vo_map.values()) | set(music)
    loose = []
    for f in files:
        name = Path(f).name
        if name in used:
            continue
        k = media.kind(Path(f))
        vo = vo_video_from_name(name)
        if k == "audio":
            if vo:
                vo_map.setdefault(vo, name)
            else:
                music.append(name)
            used.add(name)
            continue
        if k not in ("video", "image"):
            continue
        sid = id_from_name(name)
        if sid and sid in all_shots and sid not in shots_map:
            shots_map[sid] = name
            used.add(name)
        else:
            loose.append(f)
    loose.sort(key=lambda f: (Path(f).stat().st_mtime if Path(f).exists() else 0, Path(f).name))
    empty = [s for s in all_shots if s not in shots_map]
    for f, sid in zip(loose, empty):
        shots_map[sid] = Path(f).name
        used.add(Path(f).name)
    unmatched = [Path(f).name for f in files if Path(f).name not in used]
    return {"shots": shots_map, "vo": vo_map, "music": music, "unmatched": unmatched}
