"""Immediate, validated image download for products (§2A.3).

Design for testability + $0 dry-runs:
  * The byte-fetcher is injectable (`fetcher` arg). The default real fetcher uses httpx;
    tests inject a fake that returns in-memory PNG/JPEG bytes — no network.
  * Validation uses a pure-Python magic-byte + header sniffer (`sniff_image`) so it needs
    neither Pillow nor network. When Pillow IS installed the real path additionally runs
    `Image.verify()` and produces a 1080-wide normalized copy.
  * De-dupe uses perceptual hash (imagehash.phash) when available, else falls back to a
    content SHA-256 (exact-dup drop). Both drop repeated hero shots deterministically.
"""

from __future__ import annotations

import hashlib
import os
import struct
from dataclasses import dataclass
from typing import Callable

from .. import config
from ..schemas import DownloadedImage

# A fetcher takes a URL and returns (bytes, content_type) or raises.
Fetcher = Callable[[str], "tuple[bytes, str]"]


# --------------------------------------------------------------------------- #
# Pure-Python image sniffing (no Pillow)
# --------------------------------------------------------------------------- #
@dataclass
class SniffResult:
    fmt: str
    width: int
    height: int


def sniff_image(data: bytes) -> SniffResult | None:
    """Detect PNG/JPEG/GIF/WEBP and read intrinsic width/height from the header.

    Returns None if the bytes are not a recognizable image (e.g. an HTML error page
    served as `.jpg`) — this is how we reject non-images per §2A.3.
    """
    if len(data) < 12:
        return None

    # PNG: 8-byte sig, IHDR width/height at bytes 16..24 (big-endian).
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        if len(data) < 24:
            return None
        try:
            w, h = struct.unpack(">II", data[16:24])
            return SniffResult("png", int(w), int(h))
        except struct.error:
            return None

    # GIF: 'GIF87a'/'GIF89a', width/height little-endian at bytes 6..10.
    if data[:6] in (b"GIF87a", b"GIF89a"):
        w, h = struct.unpack("<HH", data[6:10])
        return SniffResult("gif", int(w), int(h))

    # WEBP (VP8/VP8L/VP8X) inside RIFF container.
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        try:
            chunk = data[12:16]
            if chunk == b"VP8X":
                w = 1 + int.from_bytes(data[24:27], "little")
                h = 1 + int.from_bytes(data[27:30], "little")
                return SniffResult("webp", w, h)
            if chunk == b"VP8 ":
                w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
                h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
                return SniffResult("webp", int(w), int(h))
        except (struct.error, IndexError):
            return None
        return SniffResult("webp", 0, 0)

    # JPEG: scan the marker segments for a Start-Of-Frame (SOFn) with dimensions.
    if data[:2] == b"\xff\xd8":
        i = 2
        n = len(data)
        while i + 9 < n:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            # SOF0..SOF3, SOF5..SOF7, SOF9..SOF11, SOF13..SOF15 carry dimensions.
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                          0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return SniffResult("jpeg", int(w), int(h))
            # Skip this segment using its length field.
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg_len
        return None

    return None


def _content_phash(data: bytes) -> str:
    """Perceptual hash if imagehash+Pillow present, else content SHA-256 (exact-dup)."""
    try:  # real path
        import io

        import imagehash  # type: ignore
        from PIL import Image  # type: ignore

        with Image.open(io.BytesIO(data)) as im:
            return str(imagehash.phash(im))
    except Exception:  # noqa: BLE001 — deps absent or decode error → content hash
        return "sha:" + hashlib.sha256(data).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Real byte fetcher (only used outside DRY_RUN / when URLs exist)
# --------------------------------------------------------------------------- #
def _httpx_fetcher(url: str) -> tuple[bytes, str]:
    import httpx  # lazy — real path only

    with httpx.Client(timeout=config.IMAGE_DOWNLOAD_TIMEOUT_S, follow_redirects=True) as c:
        resp = c.get(url)
        resp.raise_for_status()
        return resp.content, resp.headers.get("content-type", "")


# --------------------------------------------------------------------------- #
# Downloader
# --------------------------------------------------------------------------- #
def download_images(
    source_urls: list[str],
    job_id: str,
    *,
    fetcher: Fetcher | None = None,
    media_root: str | None = None,
    min_short_side: int | None = None,
) -> list[DownloadedImage]:
    """Download, validate, de-dupe product images to {media_root}/products/{job_id}/.

    Returns the accepted `DownloadedImage`s (empty list if none were usable). Never
    raises on a single bad URL — bad images are skipped so the pipeline degrades.
    """
    fetcher = fetcher or _httpx_fetcher
    media_root = media_root or config.MEDIA_ROOT
    min_short_side = (
        config.MIN_IMAGE_SHORT_SIDE if min_short_side is None else min_short_side
    )
    out_dir = os.path.join(media_root, config.PRODUCT_IMAGE_DIR, str(job_id))

    accepted: list[DownloadedImage] = []
    seen_hashes: set[str] = set()

    for idx, url in enumerate(source_urls):
        data = _fetch_with_retry(fetcher, url, config.IMAGE_DOWNLOAD_RETRIES)
        if data is None:
            continue
        sniff = sniff_image(data)
        if sniff is None:  # HTML-as-image / corrupt → reject (§2A.3)
            continue
        if sniff.width and sniff.height:
            if min(sniff.width, sniff.height) < min_short_side:  # icon/badge → drop
                continue
        phash = _content_phash(data)
        if phash in seen_hashes:  # repeated hero shot → de-dupe
            continue
        seen_hashes.add(phash)

        os.makedirs(out_dir, exist_ok=True)
        fname = f"img_{idx:02d}.{sniff.fmt if sniff.fmt != 'jpeg' else 'jpg'}"
        local_path = os.path.join(out_dir, fname)
        try:
            with open(local_path, "wb") as fh:
                fh.write(data)
        except OSError:
            continue
        accepted.append(
            DownloadedImage(
                local_path=local_path,
                source_url=url,
                width=sniff.width,
                height=sniff.height,
                fmt=sniff.fmt,
                phash=phash,
            )
        )
    return accepted


def _fetch_with_retry(fetcher: Fetcher, url: str, retries: int) -> bytes | None:
    attempt = 0
    while attempt <= retries:
        try:
            data, ctype = fetcher(url)
            # Content-type sanity (an HTML error page won't sniff as an image anyway).
            if ctype and "image" not in ctype.lower() and ctype.lower().startswith("text"):
                return None
            return data
        except Exception:  # noqa: BLE001 — network/HTTP error → backoff+retry
            attempt += 1
    return None
