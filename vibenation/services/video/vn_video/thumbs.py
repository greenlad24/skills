"""YouTube thumbnails from real show frames (no AI image editing: faces are never changed).

What makes a live-music thumbnail get clicked, and what this does about it:
  1. one real moment — score candidate frames on face size, sharpness and exposure; pick the best
  2. tight crop — 16:9 around the main performer, face in the upper third, readable at phone size
  3. depth — subject bright and crisp, background quieter (vignette + slight desaturation away from faces)
  4. the approved warm finish (R604): brown-black shadows, olive mids, golden highlights, cream tops, fine grain
  5. YouTube spec — 1280x720 JPEG < 2 MB; nothing placed bottom-right (YouTube's duration/LIVE badge)

CLI (for testing):  python -m vn_video.thumbs out.jpg frame1.jpg [frame2.jpg ...]
"""

from __future__ import annotations

import io
import os
import sys
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

W, H = 1280, 720
MAX_BYTES = 2_000_000  # YouTube's thumbnail limit
MODEL = os.path.join(os.path.dirname(__file__), '..', 'models', 'face_detection_yunet_2023mar.onnx')

# R604 finish, measured from the approved reference (mean colour per brightness band, 0..1).
# Shadows sit on a lifted warm brown-black (~RGB 34,27,17) instead of pure black; tops roll off to cream.
TINT = [  # (luma, chroma offset to blend toward)
    (0.10, np.array([+0.030, +0.004, -0.034])),   # shadows: brown-black
    (0.33, np.array([+0.035, +0.025, -0.060])),   # mids: olive
    (0.60, np.array([+0.070, +0.010, -0.080])),   # highs: golden
    (0.85, np.array([+0.030, +0.005, -0.035])),   # tops: cream
]
TINT_STRENGTH = 0.45  # partial: skin keeps its own colour inside the grade (never an orange filter)


@dataclass
class Face:
    x: float
    y: float
    w: float
    h: float
    score: float


def _luma(a: np.ndarray) -> np.ndarray:
    return a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722


def faces(img: np.ndarray) -> list[Face]:
    """Faces in an RGB uint8 frame, biggest first."""
    h, w = img.shape[:2]
    det = cv2.FaceDetectorYN.create(os.path.abspath(MODEL), '', (w, h), score_threshold=0.75)
    _, found = det.detect(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    out = [Face(*map(float, f[:4]), float(f[14])) for f in (found if found is not None else [])]
    return sorted(out, key=lambda f: f.w * f.h, reverse=True)


def score(img: np.ndarray, fs: list[Face]) -> float:
    """Higher = better thumbnail moment. A frame without a clear face scores 0."""
    if not fs:
        return 0.0
    f = fs[0]
    h, w = img.shape[:2]
    x0, y0 = max(0, int(f.x)), max(0, int(f.y))
    crop = img[y0:int(f.y + f.h), x0:int(f.x + f.w)]
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    sharp = min(1.0, cv2.Laplacian(gray, cv2.CV_64F).var() / 300)   # motion blur kills it
    expo = 1 - min(1.0, abs(gray.mean() / 255 - 0.45) * 2.2)         # face neither black nor blown
    size = min(1.0, (f.h / h) / 0.22)                                # face big enough to read on a phone
    return f.score * (0.40 * sharp + 0.25 * expo + 0.35 * size)


def crop_box(img_w: int, img_h: int, fs: list[Face]) -> tuple[int, int, int, int]:
    """16:9 box: main face ~20% of the height (room for hands + instrument), eyes on the upper third, on the side with more room.
    Never crops below 50% of the frame width, so a 1080p source still makes a sharp 1280x720."""
    f = fs[0]
    cw = min(img_w, max(img_w * 0.5, f.h / 0.20 * 16 / 9))
    ch = cw * 9 / 16
    if ch > img_h:
        ch, cw = img_h, img_h * 16 / 9
    cx_face, eyes_y = f.x + f.w / 2, f.y + f.h * 0.4
    # Performer on a third, looking into the open side; keep other faces in when they fit.
    third = cw / 3 if cx_face > img_w / 2 else cw * 2 / 3
    x0 = cx_face - (cw - third if cx_face > img_w / 2 else third)
    others = [g for g in fs[1:] if g.h > f.h * 0.6]
    if others:
        lo = min([f.x] + [g.x for g in others]) - f.w * 0.5
        hi = max([f.x + f.w] + [g.x + g.w for g in others]) + f.w * 0.5
        if hi - lo <= cw:
            x0 = min(max(x0, hi - cw), lo)
    y0 = eyes_y - ch / 3
    x0 = min(max(0, x0), img_w - cw)
    y0 = min(max(0, y0), img_h - ch)
    return int(x0), int(y0), int(x0 + cw), int(y0 + ch)


def grade(a: np.ndarray, seed: int = 0) -> np.ndarray:
    """R604 finish on float RGB 0..1."""
    L = _luma(a)
    # Tone: lift the floor to warm brown-black, soft S in the mids, gentle highlight roll-off.
    s = np.clip(L, 0, 1)
    curve = s + 0.35 * s * (1 - s) * (s - 0.35)                         # S: punch for phone-size viewing
    curve = np.where(curve > 0.88, 0.88 + (curve - 0.88) * 0.6, curve)  # roll-off: no clipped skin
    Ln = 0.035 + curve * (0.975 - 0.035)                                # slight warm lift, not faded
    chroma = (a - L[..., None]) * 1.0
    out = Ln[..., None] + chroma
    # Split tone by brightness band.
    lumas = np.array([t[0] for t in TINT])
    tints = np.stack([t[1] for t in TINT])
    tint = np.stack([np.interp(Ln, lumas, tints[:, c]) for c in range(3)], -1)
    out = out + tint * TINT_STRENGTH
    # Fine grain (luma only, so it reads as film, not colour noise).
    g = np.random.default_rng(seed).normal(0, 0.012, L.shape)
    return np.clip(out + g[..., None], 0, 1)


def depth(a: np.ndarray, fs: list[Face], box: tuple[int, int, int, int]) -> np.ndarray:
    """Quieter background: darken + desaturate away from the performers (no fake blur)."""
    h, w = a.shape[:2]
    x0, y0, x1, y1 = box
    sx, sy = w / (x1 - x0), h / (y1 - y0)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    keep = np.zeros((h, w), np.float32)
    for f in fs[:3]:
        cx, cy = (f.x + f.w / 2 - x0) * sx, (f.y + f.h * 1.2 - y0) * sy  # face + upper body
        rx, ry = f.w * sx * 2.2, f.h * sy * 3.0
        keep = np.maximum(keep, np.exp(-(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)))
    vign = 1 - 0.35 * (((xx / w - 0.5) * 2) ** 2 + ((yy / h - 0.5) * 2) ** 2) / 2
    k = np.clip(0.62 + 0.38 * keep, 0, 1) * np.clip(vign, 0.6, 1) ** (1 - keep)
    L = _luma(a)[..., None]
    sat = 0.75 + 0.25 * keep[..., None]
    return np.clip((L + (a - L) * sat) * k[..., None], 0, 1)


def make(frames: list[np.ndarray]) -> tuple[bytes, dict]:
    """Best of the candidate RGB frames -> (JPEG bytes, info)."""
    scored = []
    for i, img in enumerate(frames):
        fs = faces(img)
        scored.append((score(img, fs), i, fs))
    best, i, fs = max(scored, key=lambda t: t[0])
    if best == 0:
        raise ValueError('No frame shows a clear face. Try again during a song, with a camera on the singer.')
    img = frames[i]
    box = crop_box(img.shape[1], img.shape[0], fs)
    crop = np.asarray(Image.fromarray(img).crop(box).resize((W, H), Image.LANCZOS)).astype(np.float32) / 255
    out = grade(depth(crop, fs, box), seed=i)
    pil = Image.fromarray((out * 255 + 0.5).astype(np.uint8))
    for q in (92, 88, 84, 80, 75):
        buf = io.BytesIO()
        pil.save(buf, 'JPEG', quality=q, optimize=True, progressive=True)
        if buf.tell() < MAX_BYTES:
            break
    return buf.getvalue(), {'frame': i, 'score': round(best, 3), 'faces': len(fs), 'crop': box, 'bytes': buf.tell()}


if __name__ == '__main__':
    out, *paths = sys.argv[1:]
    data, info = make([np.asarray(Image.open(p).convert('RGB')) for p in paths])
    open(out, 'wb').write(data)
    print(info)
