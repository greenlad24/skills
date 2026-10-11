"""Give PostPeer a public link to a rendered video.

- Hosted website: our own secret link (https://your-site/pub/<token>/<file>) — permanent.
- Mac app: Litterbox (litterbox.catbox.moe) — free, no account, links last 72 h, ≤ 1 GB.
  The scheduler therefore hands posts to PostPeer at most 48 h before their time.
"""

from __future__ import annotations

from pathlib import Path

import requests

LITTERBOX = "https://litterbox.catbox.moe/resources/internals/api.php"
LITTERBOX_HOURS = 72


def upload_litterbox(path: Path) -> str:
    with open(path, "rb") as f:
        r = requests.post(LITTERBOX, data={"reqtype": "fileupload", "time": f"{LITTERBOX_HOURS}h"},
                          files={"fileToUpload": (path.name, f, "video/mp4")}, timeout=900)
    url = (r.text or "").strip()
    if r.status_code >= 400 or not url.startswith("http"):
        raise RuntimeError(f"Video upload failed ({r.status_code}): {url[:200]}")
    return url
