"""Project folders on disk: ~/ThaiTikTokStudio/projects/<id>/."""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from .config import PROJECTS_DIR, ensure_dirs


def slugify(text: str) -> str:
    s = re.sub(r"https?://\S+", "", text or "").strip()
    s = re.sub(r"[^\w฀-๿]+", "-", s).strip("-")[:40]
    return s or "product"


def new_project(name: str) -> dict:
    ensure_dirs()
    pid = time.strftime("%Y%m%d-%H%M%S") + "-" + slugify(name)
    d = PROJECTS_DIR / pid
    for sub in ("inputs", "footage", "renders", "product_images", "work"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    meta = {"id": pid, "name": name[:120] or "Product", "created": time.time(), "status": "new"}
    save_json(d / "project.json", meta)
    return meta


def pdir(pid: str) -> Path:
    if not re.fullmatch(r"[\w฀-๿.-]+", pid or ""):
        raise ValueError("bad project id")
    d = PROJECTS_DIR / pid
    if not d.is_dir():
        raise FileNotFoundError(pid)
    return d


def save_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(path)


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return default


def meta(pid: str) -> dict:
    return load_json(pdir(pid) / "project.json", {})


def update_meta(pid: str, **kw) -> dict:
    m = meta(pid)
    m.update(kw)
    save_json(pdir(pid) / "project.json", m)
    return m


def list_projects() -> list:
    ensure_dirs()
    out = []
    for d in sorted(PROJECTS_DIR.iterdir(), reverse=True):
        m = load_json(d / "project.json")
        if m:
            m["has_plan"] = (d / "plan.json").exists()
            out.append(m)
    return out


def delete_project(pid: str) -> None:
    shutil.rmtree(pdir(pid))
