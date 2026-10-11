"""Upload FINAL rendered videos to Cloudinary (free plan) so PostPeer can fetch them.

Only finished MP4s from renders/ are uploaded — raw clips and narration never leave the
computer. Configure with the dashboard's "API environment variable":
    cloudinary://<api_key>:<api_secret>@<cloud_name>
Free plan: 25 credits/month (1 credit ≈ 1 GB storage or 1 GB bandwidth), videos ≤ 100 MB.
Docs: https://cloudinary.com/documentation/image_upload_api_reference
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

import requests

FOLDER = "thai-tiktok-studio"
MAX_BYTES = 100 * 1024 * 1024


class CloudinaryError(RuntimeError):
    pass


def parse_url(url: str) -> dict:
    m = re.match(r"^\s*cloudinary://([^:]+):([^@]+)@([\w-]+)\s*$", url or "")
    if not m:
        raise CloudinaryError("Paste the Cloudinary 'API environment variable' "
                              "(looks like cloudinary://123456:abcDEF@your-cloud).")
    return {"api_key": m.group(1), "api_secret": m.group(2), "cloud": m.group(3)}


def _sign(params: dict, secret: str) -> str:
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params) if params[k] not in (None, ""))
    return hashlib.sha1((to_sign + secret).encode()).hexdigest()


def upload_video(path: Path, cfg_url: str, public_id: str) -> dict:
    """→ {"url": https link, "public_id": id}. Re-uploading the same public_id overwrites it."""
    c = parse_url(cfg_url)
    if path.stat().st_size > MAX_BYTES:
        raise CloudinaryError(f"{path.name} is over 100 MB (Cloudinary free limit). Render with Quick draft "
                              "quality off and a lower export quality, or shorten the video.")
    params = {"folder": FOLDER, "public_id": public_id, "overwrite": "true", "timestamp": str(int(time.time()))}
    params["signature"] = _sign(params, c["api_secret"])
    params["api_key"] = c["api_key"]
    with open(path, "rb") as f:
        r = requests.post(f"https://api.cloudinary.com/v1_1/{c['cloud']}/video/upload", data=params,
                          files={"file": (path.name, f, "video/mp4")}, timeout=1800)
    data = r.json() if r.content else {}
    if r.status_code >= 400 or "secure_url" not in data:
        msg = (data.get("error") or {}).get("message") if isinstance(data.get("error"), dict) else str(data)[:200]
        raise CloudinaryError(f"Cloudinary upload failed ({r.status_code}): {msg}")
    return {"url": data["secure_url"], "public_id": data.get("public_id", f"{FOLDER}/{public_id}")}


def delete_video(cfg_url: str, public_id: str) -> None:
    c = parse_url(cfg_url)
    params = {"public_id": public_id, "timestamp": str(int(time.time()))}
    params["signature"] = _sign(params, c["api_secret"])
    params["api_key"] = c["api_key"]
    requests.post(f"https://api.cloudinary.com/v1_1/{c['cloud']}/video/destroy", data=params, timeout=60)


def check(cfg_url: str) -> dict:
    """Validate credentials with a signed ping (usage endpoint)."""
    c = parse_url(cfg_url)
    r = requests.get(f"https://api.cloudinary.com/v1_1/{c['cloud']}/usage", auth=(c["api_key"], c["api_secret"]),
                     timeout=30)
    if r.status_code >= 400:
        raise CloudinaryError("Cloudinary rejected these credentials.")
    d = r.json()
    cr = d.get("credits") or {}
    return {"cloud": c["cloud"], "plan": d.get("plan", ""), "credits_used": cr.get("usage"), "credits_limit": cr.get("limit")}
