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


def make_url(cloud: str, api_key: str, api_secret: str) -> str:
    """The three boxes in the app → one cloudinary:// address (what we store)."""
    cloud, api_key, api_secret = (str(x or "").strip().strip('"\'') for x in (cloud, api_key, api_secret))
    return f"cloudinary://{api_key}:{api_secret}@{cloud}"


def parse_url(url: str) -> dict:
    """Accepts the dashboard's 'API environment variable' however it was copied
    (with or without CLOUDINARY_URL=, quotes, spaces)."""
    u = (url or "").strip().strip('"\'')
    u = re.sub(r"^(export\s+)?CLOUDINARY_URL\s*=\s*", "", u, flags=re.I).strip().strip('"\'')
    m = re.match(r"^cloudinary://([^:\s]+):([^@\s]+)@([\w.-]+)/?$", u)
    if not m:
        raise CloudinaryError("That Cloudinary address doesn't look right. Fill in Cloud name, API key and "
                              "API secret from the Cloudinary dashboard (Settings → API Keys).")
    key, secret, cloud = m.group(1), m.group(2), m.group(3)
    if "*" in secret or "<" in secret or "your_api_secret" in secret.lower():
        raise CloudinaryError("The API secret was copied while hidden (******). In Cloudinary click the eye 👁 "
                              "next to the secret to show it, then copy it again.")
    if not key.isdigit():
        raise CloudinaryError("The API key should be only numbers — check you copied the API key (not the secret).")
    return {"api_key": key, "api_secret": secret, "cloud": cloud}


def explain(status: int, msg: str) -> str:
    low = (msg or "").lower()
    if "signature" in low:
        return "Cloudinary says the API secret is wrong. Copy it again (click the eye 👁 first so it isn't hidden)."
    if "api_key" in low or "api key" in low:
        return "Cloudinary doesn't know this API key. Copy the API key again from Settings → API Keys."
    if "cloud_name" in low or "cloud name" in low or status == 404:
        return "Cloudinary doesn't know this Cloud name. Copy it from the top of the Cloudinary dashboard."
    if "file size" in low or "too large" in low:
        return "The video is too big for Cloudinary's free plan (100 MB)."
    if status == 420 or "rate limit" in low:
        return "Cloudinary's free plan limit was reached for now — try again in an hour."
    return f"Cloudinary upload failed ({status}): {msg[:200]}"


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
    try:
        with open(path, "rb") as f:
            r = requests.post(f"https://api.cloudinary.com/v1_1/{c['cloud']}/video/upload", data=params,
                              files={"file": (path.name, f, "video/mp4")}, timeout=1800)
    except requests.RequestException as e:
        raise CloudinaryError(f"Can't reach Cloudinary — check the internet connection. ({str(e)[:120]})") from e
    try:
        data = r.json() if r.content else {}
    except ValueError:
        data = {"error": {"message": r.text[:200]}}
    if r.status_code >= 400 or "secure_url" not in data:
        msg = (data.get("error") or {}).get("message") if isinstance(data.get("error"), dict) else str(data)[:200]
        raise CloudinaryError(explain(r.status_code, msg or ""))
    return {"url": data["secure_url"], "public_id": data.get("public_id", f"{FOLDER}/{public_id}")}


def delete_video(cfg_url: str, public_id: str) -> None:
    c = parse_url(cfg_url)
    params = {"public_id": public_id, "timestamp": str(int(time.time()))}
    params["signature"] = _sign(params, c["api_secret"])
    params["api_key"] = c["api_key"]
    requests.post(f"https://api.cloudinary.com/v1_1/{c['cloud']}/video/destroy", data=params, timeout=60)


def check(cfg_url: str, work_dir: Path | None = None) -> dict:
    """Real test: upload a 1-second video exactly like a post would, then delete it."""
    import subprocess
    import tempfile
    from .editor.media import ffmpeg_exe
    c = parse_url(cfg_url)
    tmp = Path(work_dir or tempfile.mkdtemp()) / "cloudinary_test.mp4"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0xe11d48:s=180x320:d=1",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", str(tmp)], check=True)
    try:
        res = upload_video(tmp, cfg_url, "connection-test")
    finally:
        tmp.unlink(missing_ok=True)
    try:
        delete_video(cfg_url, res["public_id"])
    except Exception:
        pass
    return {"cloud": c["cloud"], "url": res["url"]}
