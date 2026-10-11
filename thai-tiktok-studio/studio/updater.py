"""Self-update for the Mac app: new versions published to GitHub install themselves.

Publishing = run `python mac/build_app.py` (bumps nothing; uses studio.__version__) and push.
That writes releases/ThaiTikTokStudio-mac.zip and releases/latest.json. The app checks
latest.json on launch and every 6 h; when it's newer, it downloads the zip, unpacks only the
app's code into ~/Library/Application Support/ThaiTikTokStudio/app-<version>, and points
`current.txt` at it. The launcher starts the newest valid version next time. Projects,
videos and settings live elsewhere and are never touched. A broken download is ignored.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import threading
import time
import zipfile
from pathlib import Path

import requests

from . import __version__

LATEST_URL = os.environ.get(
    "TTS_STUDIO_UPDATE_URL",
    "https://raw.githubusercontent.com/greenlad24/skills/claude/wizardly-thompson-w6jjr8/"
    "thai-tiktok-studio/releases/latest.json")
APP_PREFIX = "Thai TikTok Studio.app/Contents/Resources/app/"
CHECK_EVERY = 6 * 3600
STATE = {"current": __version__, "latest": "", "ready": "", "error": "", "checked": 0, "notes": ""}


def _support() -> Path:
    return Path(os.environ.get("TTS_STUDIO_SUPPORT",
                               Path.home() / "Library" / "Application Support" / "ThaiTikTokStudio"))


def vtuple(v: str) -> tuple:
    out = []
    for part in str(v).strip().split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out + [0] * (3 - len(out)))


def enabled() -> bool:
    """Only the packaged Mac app updates itself (source checkouts use git; servers use update.sh)."""
    return bool(os.environ.get("TTS_STUDIO_BUNDLE")) or os.environ.get("TTS_STUDIO_FORCE_UPDATER") == "1"


def check_and_download() -> dict:
    STATE["checked"] = time.time()
    try:
        r = requests.get(LATEST_URL, timeout=15, headers={"Cache-Control": "no-cache"})
        r.raise_for_status()
        info = r.json()
    except Exception as e:
        STATE["error"] = f"check failed: {e}"
        return STATE
    latest = str(info.get("version", ""))
    STATE["latest"], STATE["notes"] = latest, str(info.get("notes", ""))[:500]
    if not latest or vtuple(latest) <= vtuple(__version__):
        return STATE
    support = _support()
    target = support / f"app-{latest}"
    if (target / "studio" / "app.py").exists():
        _point_to(target)
        STATE["ready"] = latest
        return STATE
    try:
        z = requests.get(info["zip_url"], timeout=600)
        z.raise_for_status()
        tmp = support / f".app-{latest}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
            for name in zf.namelist():
                if not name.startswith(APP_PREFIX) or name.endswith("/"):
                    continue
                rel = name[len(APP_PREFIX):]
                if ".." in Path(rel).parts:
                    continue
                dest = tmp / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(name))
        ver_file = tmp / "VERSION"
        if not (tmp / "studio" / "app.py").exists() or not ver_file.exists() \
                or ver_file.read_text().strip() != latest:
            raise ValueError("downloaded update is incomplete")
        shutil.rmtree(target, ignore_errors=True)
        tmp.rename(target)
        _point_to(target)
        STATE["ready"], STATE["error"] = latest, ""
    except Exception as e:
        STATE["error"] = f"download failed: {e}"
    return STATE


def _point_to(target: Path) -> None:
    ptr = target.parent / "current.txt"
    tmp = ptr.with_suffix(".tmp")
    tmp.write_text(target.name)
    tmp.replace(ptr)


def start() -> None:
    if not enabled():
        return

    def loop():
        time.sleep(5)
        while True:
            check_and_download()
            time.sleep(CHECK_EVERY)
    threading.Thread(target=loop, daemon=True).start()


def restart() -> bool:
    """Relaunch the Mac app (the launcher picks the newest version) and quit this one."""
    bundle = os.environ.get("TTS_STUDIO_BUNDLE")
    if not bundle or sys.platform != "darwin":
        return False
    import subprocess
    subprocess.Popen(["/bin/bash", "-c", f'sleep 1; open -n "{bundle}"'])
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return True
