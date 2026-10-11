"""Tool 2 orchestration: project files → rendered MP4s (no AI calls)."""

from __future__ import annotations

import time
from pathlib import Path

from .. import projects
from . import matcher, media, render, timeline


def footage_files(pid: str) -> list:
    d = projects.pdir(pid) / "footage"
    return sorted(str(p) for p in d.iterdir() if p.is_file() and not p.name.startswith("."))


def load_assign(pid: str) -> dict:
    return projects.load_json(projects.pdir(pid) / "assign.json", {"shots": {}, "vo": {}, "music": []})


def refresh_assign(pid: str, plan: dict) -> dict:
    """Auto-match new files while keeping manual choices; drop links to deleted files."""
    d = projects.pdir(pid) / "footage"
    cur = load_assign(pid)
    names = {Path(f).name for f in footage_files(pid)}
    cur["shots"] = {k: v for k, v in cur.get("shots", {}).items() if v in names}
    cur["vo"] = {k: v for k, v in cur.get("vo", {}).items() if v in names}
    cur["music"] = [m for m in cur.get("music", []) if m in names]
    out = matcher.auto_match(plan, footage_files(pid), cur)
    projects.save_json(projects.pdir(pid) / "assign.json", out)
    return out


def file_infos(pid: str) -> list:
    out = []
    for f in footage_files(pid):
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


def render_videos(job, pid: str, video_ids: list, settings: dict, draft: bool = False) -> dict:
    d = projects.pdir(pid)
    plan = projects.load_json(d / "plan.json")
    if not plan:
        raise RuntimeError("This project has no plan yet.")
    assign = refresh_assign(pid, plan)
    vids = [v for v in plan["videos"] if not video_ids or v["id"] in video_ids]
    product_images = sorted(str(p) for p in (d / "product_images").glob("*") if media.kind(p) == "image")
    music_name = (assign.get("music") or [None])[0]
    music = d / "footage" / music_name if music_name else None
    st = dict(settings)
    if draft:
        st["render_preset"], st["render_crf"] = "ultrafast", 28
    results = []
    for i, v in enumerate(vids):
        base = i / len(vids)
        job.say(f"{v['id']}: planning cuts…")
        R = timeline.resolve(v, assign, d / "footage", product_images, st, d / "work" / v["id"], log=job.say)
        for n in R.notes:
            job.say(f"{v['id']}: {n}")
        if R.missing:
            job.say(f"{v['id']}: missing footage for {', '.join(sorted(set(R.missing)))} (placeholder cards used)")
        out = d / "renders" / f"{v['id']}{'_draft' if draft else ''}_{time.strftime('%H%M%S')}.mp4"
        job.say(f"{v['id']}: rendering {R.total:.1f}s video…")

        def prog(p, base=base):
            job.progress = base + p / len(vids)
        render.render(R, out, d / "work" / v["id"], music=music if music and music.exists() else None,
                      settings=st, progress=prog, log=job.say)
        job.say(f"{v['id']}: done → {out.name}")
        results.append({"video": v["id"], "file": out.name, "duration": R.total, "missing": R.missing})
    return {"renders": results}


def list_renders(pid: str) -> list:
    d = projects.pdir(pid) / "renders"
    return [{"name": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime}
            for p in sorted(d.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)]
