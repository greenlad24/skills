"""Tool 2 orchestration: project files → rendered MP4s (Claude plans the cuts when available)."""

from __future__ import annotations

import time
from pathlib import Path

from .. import projects
from . import matcher, media, render, smart_edit


SUBS = ("footage", "narration")


def footage_files(pid: str, sub: str = "footage") -> list:
    d = projects.pdir(pid) / sub
    d.mkdir(exist_ok=True)
    return sorted(str(p) for p in d.iterdir() if p.is_file() and not p.name.startswith("."))


def load_assign(pid: str) -> dict:
    a = projects.load_json(projects.pdir(pid) / "assign.json", {})
    for k, dflt in (("shots", {}), ("vo", {}), ("music", []), ("narration", {})):
        a.setdefault(k, dflt)
    return a


def refresh_assign(pid: str, plan: dict) -> dict:
    """Auto-match new files while keeping manual choices; drop links to deleted files."""
    d = projects.pdir(pid) / "footage"
    cur = load_assign(pid)
    names = {Path(f).name for f in footage_files(pid)}
    cur["shots"] = {k: v for k, v in cur.get("shots", {}).items() if v in names}
    cur["vo"] = {k: v for k, v in cur.get("vo", {}).items() if v in names}
    cur["music"] = [m for m in cur.get("music", []) if m in names]
    out = matcher.auto_match(plan, footage_files(pid), cur)
    out["narration"] = matcher.match_narration(plan, footage_files(pid, "narration"), cur.get("narration"))
    projects.save_json(projects.pdir(pid) / "assign.json", out)
    return out


def file_infos(pid: str, sub: str = "footage") -> list:
    out = []
    for f in footage_files(pid, sub):
        p = Path(f)
        k = media.kind(p)
        info = {"name": p.name, "kind": k, "size": p.stat().st_size, "duration": 0}
        if k in ("video", "audio"):
            try:
                info["duration"] = round(media.probe(p)["duration"], 2)
            except Exception:
                pass
        out.append(info)
    return out


def render_videos(job, pid: str, video_ids: list, settings: dict, draft: bool = False, versions: int = 1) -> dict:
    from .styles import STYLES
    d = projects.pdir(pid)
    plan = projects.load_json(d / "plan.json")
    if not plan:
        raise RuntimeError("This project has no plan yet.")
    assign = refresh_assign(pid, plan)
    vids = [v for v in plan["videos"] if not video_ids or v["id"] in video_ids]
    versions = max(1, min(5, int(versions or 1)))
    product_images = sorted(str(p) for p in (d / "product_images").glob("*") if media.kind(p) == "image")
    music_name = (assign.get("music") or [None])[0]
    music = d / "footage" / music_name if music_name else None
    st = dict(settings)
    if draft:
        st["render_preset"], st["render_crf"] = "ultrafast", 28
    jobs_list = []
    for v in vids:
        base_style = v.get("anim_style") if v.get("anim_style") in STYLES else STYLES[0]
        for k in range(versions):   # each extra version = next animation style + new random picks
            style = STYLES[(STYLES.index(base_style) + k) % len(STYLES)]
            jobs_list.append(dict(v, anim_style=style, variation=int(v.get("variation", 0)) + k))
    results = []
    for i, v in enumerate(jobs_list):
        base = i / len(jobs_list)
        label = f"{v['id']} ({v['anim_style']})"
        job.say(f"{label}: planning the edit…")
        R = smart_edit.resolve(v, assign, footage_files(pid), product_images, st, d / "work" / v["id"],
                               log=lambda m, label=label: job.say(f"{label}: {m}"), narration_dir=d / "narration")
        for n in R.notes:
            job.say(f"{label}: {n}")
        out = d / "renders" / f"{v['id']}_{v['anim_style']}{'_draft' if draft else ''}_{time.strftime('%H%M%S')}.mp4"
        job.say(f"{label}: rendering {R.total:.1f}s video…")

        def prog(p, base=base):
            job.progress = base + p / len(jobs_list)
        render.render(R, out, d / "work" / v["id"], music=music if music and music.exists() else None,
                      settings=st, progress=prog, log=job.say)
        job.say(f"{label}: done → {out.name}")
        results.append({"video": v["id"], "style": v["anim_style"], "file": out.name, "duration": R.total,
                        "missing": []})
    return {"renders": results}


def list_renders(pid: str) -> list:
    d = projects.pdir(pid) / "renders"
    return [{"name": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime}
            for p in sorted(d.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)]
