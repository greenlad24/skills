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


def _context(pid: str):
    d = projects.pdir(pid)
    plan = projects.load_json(d / "plan.json")
    if not plan:
        raise RuntimeError("This project has no plan yet.")
    assign = refresh_assign(pid, plan)
    product_images = sorted(str(p) for p in (d / "product_images").glob("*") if media.kind(p) == "image")
    music_name = (assign.get("music") or [None])[0]
    music = d / "footage" / music_name if music_name else None
    return d, plan, assign, product_images, (music if music and music.exists() else None)


def _variants(plan: dict, video_ids: list, versions: int) -> list:
    from .styles import STYLES
    vids = [v for v in plan["videos"] if not video_ids or v["id"] in video_ids]
    versions = max(1, min(5, int(versions or 1)))
    out = []
    for v in vids:
        base_style = v.get("anim_style") if v.get("anim_style") in STYLES else STYLES[0]
        for k in range(versions):   # each extra version = next animation style + new random picks
            style = STYLES[(STYLES.index(base_style) + k) % len(STYLES)]
            out.append(dict(v, anim_style=style, variation=int(v.get("variation", 0)) + k))
    return out


def _build(pid, v, settings, say, edl=None):
    d, plan, assign, product_images, music = _context(pid)
    R = smart_edit.resolve(v, assign, footage_files(pid), product_images, settings, d / "work" / v["id"],
                           log=say, narration_dir=d / "narration", edl_override=edl)
    return d, R, music


def _draft(settings: dict) -> dict:
    st = dict(settings)
    st["render_preset"], st["render_crf"] = "ultrafast", 30
    return st


def render_videos(job, pid: str, video_ids: list, settings: dict, draft: bool = False, versions: int = 1) -> dict:
    """Plan + render in one go (no review)."""
    _, plan, *_ = _context(pid)
    items = _variants(plan, video_ids, versions)
    st = _draft(settings) if draft else dict(settings)
    results = []
    for i, v in enumerate(items):
        label = f"{v['id']} ({v['anim_style']})"
        job.say(f"{label}: planning the edit…")
        d, R, music = _build(pid, v, st, lambda m, label=label: job.say(f"{label}: {m}"))
        for n in R.notes:
            job.say(f"{label}: {n}")
        out = d / "renders" / f"{v['id']}_{v['anim_style']}{'_draft' if draft else ''}_{time.strftime('%H%M%S')}.mp4"
        results.append(_render(job, R, out, d / "work" / v["id"], music, st, i, len(items), label))
    return {"renders": results}


def _render(job, R, out, work, music, st, i, n, label):
    job.say(f"{label}: rendering {R.total:.1f}s video…")
    out.parent.mkdir(parents=True, exist_ok=True)

    def prog(p):
        job.progress = (i + p) / n
    render.render(R, out, work, music=music, settings=st, progress=prog, log=job.say)
    job.say(f"{label}: done → {out.name}")
    return {"file": out.name, "duration": R.total}


# --------------------------------------------------------------------------- review step
EDIT_FIELDS = ("text", "sub_text", "items", "emoji", "hidden", "x", "y", "tilt")


def edits_dir(pid: str) -> Path:
    d = projects.pdir(pid) / "edits"
    d.mkdir(exist_ok=True)
    return d


def _edit_key(v: dict) -> str:
    return f"{v['id']}_{v['anim_style']}_{int(v.get('variation', 0))}"


def prepare_edits(job, pid: str, video_ids: list, settings: dict, versions: int = 1) -> dict:
    """Batch: plan every video and make a quick preview of each, for the review screen."""
    _, plan, *_ = _context(pid)
    items = _variants(plan, video_ids, versions)
    ed = edits_dir(pid)
    for f in ed.glob("*"):          # a new batch replaces the previous review
        if f.is_dir():
            import shutil
            shutil.rmtree(f, ignore_errors=True)
        else:
            f.unlink()
    st = _draft(settings)
    keys = []
    for i, v in enumerate(items):
        key = _edit_key(v)
        label = f"{v['id']} ({v['anim_style']})"
        job.say(f"{label}: planning the edit…")
        d, R, music = _build(pid, v, settings, lambda m, label=label: job.say(f"{label}: {m}"))
        for n in R.notes:
            job.say(f"{label}: {n}")
        rec = {"key": key, "video": v["id"], "anim_style": v["anim_style"], "variation": int(v.get("variation", 0)),
               "title": v.get("title_th", ""), "rank": v.get("rank", i + 1), "duration": R.total,
               "edl": R.edl, "notes": R.notes, "preview": f"{key}.mp4", "preview_stale": False, "rendered": ""}
        projects.save_json(ed / f"{key}.json", rec)
        job.say(f"{label}: making the preview…")
        _render(job, R, ed / f"{key}.mp4", d / "work" / v["id"], music, st, i, len(items), label)
        keys.append(key)
    return {"edits": keys}


def _sticker_view(o: dict, i: int, home: list | None = None) -> dict:
    hx, hy, hw, hh, hr = (home or [0.5, 0.3, 0.5, 0.08, 0.0])
    return {"i": i, "type": o["type"], "text": o.get("text", ""), "sub_text": o.get("sub_text", ""),
            "items": o.get("items", []), "emoji": o.get("emoji", ""), "at": o.get("at", 0), "dur": o.get("dur", 0),
            "hidden": bool(o.get("hidden")),
            "x": o.get("x") if o.get("x") is not None else hx, "y": o.get("y") if o.get("y") is not None else hy,
            "w": hw, "h": hh, "tilt": o.get("tilt") if o.get("tilt") is not None else hr,
            "moved": o.get("x") is not None}


def _homes(pid: str, rec: dict) -> list:
    """Where each sticker sits by default (x, y, w, h as 0-1 of the frame, tilt) — the start point for dragging."""
    from . import elements as E
    _, plan, *_ = _context(pid)
    try:
        ctx = E.Ctx(_video_for(plan, rec))
    except ValueError:
        return []
    out = []
    for o in (rec.get("edl") or {}).get("overlays", []):
        base = {k: v for k, v in o.items() if k not in ("x", "y", "tilt")}
        els = E.build_overlay(base, 0.0, max(0.5, o.get("dur", 2)), ctx)
        main = next((e for e in els if e.sprite is not None), None)
        if main is None:
            out.append([0.5, 0.3, 0.3, 0.06, 0.0])
            continue
        out.append([round(main.cx / E.W, 4), round(main.cy / E.H, 4), round(main.sprite.width / E.W, 4),
                    round(main.sprite.height / E.H, 4), round(-main.rot, 1)])
    return out


def list_edits(pid: str) -> list:
    out = []
    for f in sorted(edits_dir(pid).glob("*.json")):
        rec = projects.load_json(f, {})
        if not rec:
            continue
        if len(rec.get("homes") or []) != len((rec.get("edl") or {}).get("overlays", [])):
            try:
                rec["homes"] = _homes(pid, rec)
                projects.save_json(f, rec)
            except Exception:
                rec["homes"] = []
        homes = rec.get("homes") or []
        pv = edits_dir(pid) / rec.get("preview", "")
        out.append({k: rec.get(k) for k in ("key", "video", "anim_style", "variation", "title", "rank", "duration",
                                              "notes", "preview_stale", "rendered")}
                   | {"preview": f"edits/{rec['preview']}" if pv.is_file() else "",
                      "preview_v": int(pv.stat().st_mtime) if pv.is_file() else 0,
                      "stickers": [_sticker_view(o, i, homes[i] if i < len(homes) else None)
                                   for i, o in enumerate((rec.get("edl") or {}).get("overlays", []))]})
    return sorted(out, key=lambda r: (r["rank"] or 0, r["key"]))


def _load_edit(pid: str, key: str) -> tuple:
    if not key.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Unknown video.")
    f = edits_dir(pid) / f"{key}.json"
    rec = projects.load_json(f, {})
    if not rec:
        raise ValueError("This video is no longer in the review — prepare the videos again.")
    return f, rec


def update_edit(pid: str, key: str, stickers: list) -> dict:
    """Change sticker text / emoji / list items or remove a sticker. Timing and animation stay the same."""
    from ..plan_schema import strip_overlay_prices
    f, rec = _load_edit(pid, key)
    ovs = rec["edl"]["overlays"]
    for chg in stickers or []:
        try:
            i = int(chg.get("i"))
        except (TypeError, ValueError):
            continue
        if not 0 <= i < len(ovs):
            continue
        o = dict(ovs[i])
        for k in EDIT_FIELDS:
            if k not in chg:
                continue
            v = chg[k]
            if k == "items":
                v = [str(x).strip()[:60] for x in (v if isinstance(v, list) else str(v).splitlines()) if str(x).strip()][:6]
            elif k == "hidden":
                v = bool(v)
            elif k in ("x", "y", "tilt"):      # None = back to the automatic place / angle
                try:
                    v = None if v is None else float(v)
                except (TypeError, ValueError):
                    continue
                if v is not None:
                    v = max(-45.0, min(45.0, v)) if k == "tilt" else max(0.0, min(1.0, v))
            else:
                v = str(v).strip()[:120]
            o[k] = v
        cleaned = strip_overlay_prices(dict(o))     # prices never appear, edited or not
        ovs[i] = dict(o, **{k: cleaned[k] for k in ("text", "sub_text", "items")}) if cleaned else dict(o, hidden=True)
    rec["preview_stale"] = True
    projects.save_json(f, rec)
    return next(e for e in list_edits(pid) if e["key"] == key)


def edit_frame(pid: str, key: str, t: float) -> Path:
    """A still of the preview at time t (for placing a sticker by dragging)."""
    import subprocess
    _, rec = _load_edit(pid, key)
    src = edits_dir(pid) / rec.get("preview", "")
    if not src.is_file():
        raise ValueError("No preview yet.")
    out = edits_dir(pid) / "frames" / f"{key}_{int(t * 10)}_{int(src.stat().st_mtime)}.jpg"
    if not out.exists():
        out.parent.mkdir(exist_ok=True)
        subprocess.run([media.ffmpeg_exe(), "-v", "error", "-y", "-ss", f"{max(0.0, t):.2f}", "-i", str(src),
                        "-frames:v", "1", "-vf", "scale=360:-2", str(out)], capture_output=True)
    if not out.exists():
        raise ValueError("Couldn't read the preview.")
    return out


def _video_for(plan: dict, rec: dict) -> dict:
    v = next((x for x in plan["videos"] if x["id"] == rec["video"]), None)
    if v is None:
        raise ValueError("That video is no longer in the plan.")
    return dict(v, anim_style=rec["anim_style"], variation=rec["variation"])


def preview_edit(job, pid: str, key: str, settings: dict) -> dict:
    f, rec = _load_edit(pid, key)
    _, plan, *_ = _context(pid)
    v = _video_for(plan, rec)
    d, R, music = _build(pid, v, settings, job.say, edl=rec["edl"])
    _render(job, R, edits_dir(pid) / rec["preview"], d / "work" / v["id"], music, _draft(settings), 0, 1, key)
    rec["preview_stale"] = False
    projects.save_json(f, rec)
    return {"edit": key}


def render_final(job, pid: str, keys: list, settings: dict) -> dict:
    """Full-quality render of the reviewed edits, exactly as approved (no new planning)."""
    _, plan, *_ = _context(pid)
    keys = keys or [e["key"] for e in list_edits(pid)]
    results = []
    for i, key in enumerate(keys):
        f, rec = _load_edit(pid, key)
        v = _video_for(plan, rec)
        label = f"{v['id']} ({v['anim_style']})"
        d, R, music = _build(pid, v, settings, lambda m, label=label: job.say(f"{label}: {m}"), edl=rec["edl"])
        out = d / "renders" / f"{v['id']}_{v['anim_style']}_{time.strftime('%H%M%S')}.mp4"
        results.append(_render(job, R, out, d / "work" / v["id"], music, settings, i, len(keys), label))
        rec["rendered"] = out.name
        projects.save_json(f, rec)
    return {"renders": results}


def delete_renders(pid: str, names: list) -> dict:
    """Delete finished videos (and cancel any post of them that hasn't gone out yet)."""
    from .. import scheduler
    d = projects.pdir(pid) / "renders"
    gone = []
    for n in names or []:
        p = (d / Path(str(n)).name)
        if p.suffix.lower() == ".mp4" and p.is_file():
            p.unlink()
            gone.append(p.name)
    if gone and hasattr(scheduler, "forget_renders"):
        scheduler.forget_renders(pid, gone)
    return {"deleted": gone}


def list_renders(pid: str) -> list:
    d = projects.pdir(pid) / "renders"
    return [{"name": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime}
            for p in sorted(d.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)]
