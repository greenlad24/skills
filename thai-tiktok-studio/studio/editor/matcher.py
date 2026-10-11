"""Match dropped files to shots WITHOUT needing special filenames.

1. Files are put in recording order (capture time from the file's metadata, else the
   file's date, else natural filename order like IMG_0012 < IMG_0103).
2. Each video is classified as "talk" (has speech) or "broll"; photos as "photo".
3. Clips are aligned to the shot list in order (V1-S01, V1-S02, … V2-S01 …) with a
   small dynamic-programming alignment, so a missing shot or an extra take doesn't
   shift everything after it, and talking clips prefer talking shots. When a shot was
   filmed more than once in a row, the LAST take is used (it's usually the keeper).
4. Audio files are classified as voice-over (speech with pauses) or music.

Filenames that DO contain a shot id (V1-S01) or "V1-VO" are still honoured, and any
manual choice made in the app is kept.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

from . import media

ID_RE = re.compile(r"(?<![a-z0-9])v\s*(\d{1,2})\s*[-_. ]?\s*s\s*(\d{1,3})(?![0-9])", re.I)
VO_RE = re.compile(r"(?<![a-z0-9])v\s*(\d{1,2})\s*[-_. ]?\s*(vo|voice|เสียง)", re.I)

SKIP_SHOT = 1.0    # leave a shot without footage
SKIP_FILE = 0.9    # treat a clip as an extra take / unused
MATCH = {("talk", "talk"): 0.0, ("broll", "broll"): 0.0, ("photo", "photo"): 0.0,
         ("talk", "broll"): 0.8, ("broll", "talk"): 1.3, ("photo", "broll"): 0.7,
         ("photo", "talk"): 1.6, ("broll", "photo"): 0.5, ("talk", "photo"): 1.0}


def id_from_name(name: str) -> str:
    m = ID_RE.search(Path(name).stem)
    return f"V{int(m.group(1))}-S{int(m.group(2)):02d}" if m else ""


def vo_video_from_name(name: str) -> str:
    m = VO_RE.search(Path(name).stem)
    return f"V{int(m.group(1))}" if m else ""


def _natural(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def order_key(path) -> tuple:
    p = Path(path)
    t = None
    try:
        t = media.capture_time(p)
    except Exception:
        pass
    if t is None:
        t = p.stat().st_mtime if p.exists() else 0
    return (t, _natural(p.name))


@functools.lru_cache(maxsize=1024)
def _classify(path: str, mtime: float) -> str:
    p = Path(path)
    k = media.kind(p)
    if k == "image":
        return "photo"
    if k == "audio":
        info = media.probe(p)
        isl = media.speech_islands(p, min_silence=0.35)
        dur = info["duration"] or 1
        silence = 1 - sum(e - s for s, e in isl) / dur
        # speech has many short pauses; music is mostly continuous
        return "voice" if len(isl) >= 2 and silence >= 0.08 else "music"
    if k != "video":
        return "other"
    info = media.probe(p)
    if not info["has_audio"] or info["duration"] <= 0:
        return "broll"
    isl = media.speech_islands(p)
    speech = sum(e - s for s, e in isl) / info["duration"]
    return "talk" if speech >= 0.35 and any(e - s >= 0.6 for s, e in isl) else "broll"


def classify(path) -> str:
    p = Path(path)
    return _classify(str(p), p.stat().st_mtime)


def shot_type(shot: dict) -> str:
    if shot.get("shot_size") == "product_photo":
        return "photo"
    if shot.get("audio") == "sync" or shot.get("shot_size") == "selfie_talking":
        return "talk"
    return "broll"


def align(files: list, shots: list) -> dict:
    """Order-preserving alignment of typed files to typed shots → {shot_id: file}."""
    n, m = len(files), len(shots)
    INF = float("inf")
    cost = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            c = cost[i][j]
            if c == INF:
                continue
            if i < n and j < m:
                # tie-breaks: among equal retakes the LAST take wins; otherwise fill earlier shots first
                v = c + MATCH.get((files[i][1], shots[j][1]), 1.5) - 1e-6 * i + 1e-7 * j
                if v < cost[i + 1][j + 1]:
                    cost[i + 1][j + 1], back[i + 1][j + 1] = v, (i, j, "match")
            if i < n and c + SKIP_FILE < cost[i + 1][j]:
                cost[i + 1][j], back[i + 1][j] = c + SKIP_FILE, (i, j, "file")
            if j < m and c + SKIP_SHOT < cost[i][j + 1]:
                cost[i][j + 1], back[i][j + 1] = c + SKIP_SHOT, (i, j, "shot")
    out, i, j = {}, n, m
    while back[i][j]:
        pi, pj, kind = back[i][j]
        if kind == "match":
            out[shots[pj][0]] = files[pi][0]
        i, j = pi, pj
    return out


def match_narration(plan: dict, files: list, existing: dict | None = None) -> dict:
    """Narration uploads → videos, in recording order. Voice-over videos first, then the rest."""
    cur = dict(existing or {})
    names = {Path(f).name for f in files}
    cur = {k: v for k, v in cur.items() if v in names}
    free = [Path(f).name for f in sorted(files, key=order_key) if Path(f).name not in cur.values()]
    vids = [v["id"] for v in plan["videos"] if v.get("audio_mode") == "voiceover"]
    vids += [v["id"] for v in plan["videos"] if v["id"] not in vids]
    for vid in vids:
        if vid not in cur and free:
            cur[vid] = free.pop(0)
    return cur


def auto_match(plan: dict, files: list, existing: dict | None = None) -> dict:
    """→ {"shots": {shot_id: filename}, "vo": {video_id: filename}, "music": [...], "unmatched": [...]}"""
    existing = existing or {}
    shots_map = dict(existing.get("shots", {}))
    vo_map = dict(existing.get("vo", {}))
    music = list(existing.get("music", []))
    all_shots = [(s["id"], shot_type(s)) for v in plan["videos"] for s in v["shots"]]
    shot_ids = {s for s, _ in all_shots}
    used = set(shots_map.values()) | set(vo_map.values()) | set(music)

    files = sorted(files, key=order_key)
    loose_media, voices = [], []
    for f in files:
        name = Path(f).name
        if name in used:
            continue
        k = media.kind(Path(f))
        if k == "audio":
            vo = vo_video_from_name(name)
            if vo and vo not in vo_map:
                vo_map[vo] = name
                used.add(name)
            elif classify(f) == "voice":
                voices.append(name)
            else:
                music.append(name)
                used.add(name)
            continue
        if k not in ("video", "image"):
            continue
        sid = id_from_name(name)
        if sid in shot_ids and sid not in shots_map:
            shots_map[sid] = name
            used.add(name)
        else:
            loose_media.append(f)

    # voice-overs → voice-over videos, in recording order
    vo_videos = [v["id"] for v in plan["videos"] if v.get("audio_mode") == "voiceover" and v["id"] not in vo_map]
    for vid, name in zip(vo_videos, voices):
        vo_map[vid] = name
        used.add(name)

    free_shots = [(s, t) for s, t in all_shots if s not in shots_map]
    typed = [(Path(f).name, classify(f)) for f in loose_media]
    for sid, name in align(typed, free_shots).items():
        shots_map[sid] = name
        used.add(name)
    unmatched = [Path(f).name for f in files if Path(f).name not in used]
    return {"shots": shots_map, "vo": vo_map, "music": music, "unmatched": unmatched}
