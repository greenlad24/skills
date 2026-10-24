"""Per-camera picture adjustment (exposure, gamma, contrast, saturation) on the I420 frames.

The phones lock exposure when they start streaming, so a camera that metered on a bright
lamp stays dark all night. A look brightens it here instead: two lookup tables (one for the
luma plane, one for both chroma planes), a few ms per 1080p frame. Looks are kept per camera
name, so they survive a phone re-joining with a new number.
"""
from __future__ import annotations

import json
import logging
import os

import numpy as np

log = logging.getLogger('vn_video.looks')

FILE = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'cam_looks.json')
DEFAULT = {'ev': 0.0, 'gamma': 1.0, 'contrast': 1.0, 'saturation': 1.0}
LIMITS = {'ev': (-2.0, 3.0), 'gamma': (0.5, 2.5), 'contrast': (0.5, 1.8), 'saturation': (0.0, 2.0)}


def _tables(look: dict) -> tuple[np.ndarray, np.ndarray]:
    x = (np.arange(256, dtype=np.float32) - 16) / 219          # video-range luma -> 0..1
    x = np.clip(x, 0, None) * (2.0 ** look['ev'])               # exposure
    x = x / (1 + 0.25 * np.maximum(x - 0.75, 0) ** 2)           # soft shoulder: highlights roll off, no hard clip
    x = np.clip(x, 0, 1) ** (1 / look['gamma'])                 # lift the mids
    x = np.clip(0.5 + (x - 0.5) * look['contrast'], 0, 1)       # contrast around mid-grey
    y = np.round(16 + x * 219).astype(np.uint8)
    c = np.arange(256, dtype=np.float32) - 128
    uv = np.clip(np.round(128 + c * look['saturation']), 16, 240).astype(np.uint8)
    return y, uv


class Looks:
    def __init__(self):
        self.by_name: dict[str, dict] = {}
        self._cache: dict[str, tuple] = {}
        try:
            with open(FILE) as fh:
                self.by_name = {k: {**DEFAULT, **v} for k, v in json.load(fh).items()}
        except (OSError, ValueError):
            pass

    def set(self, name: str, **vals) -> dict:
        look = {**DEFAULT, **self.by_name.get(name, {})}
        for k, v in vals.items():
            if k in LIMITS and v is not None:
                lo, hi = LIMITS[k]
                look[k] = max(lo, min(hi, float(v)))
        if look == DEFAULT:
            self.by_name.pop(name, None)
        else:
            self.by_name[name] = look
        self._cache.pop(name, None)
        try:
            os.makedirs(os.path.dirname(FILE), exist_ok=True)
            with open(FILE, 'w') as fh:
                json.dump(self.by_name, fh, indent=1)
        except OSError as e:
            log.warning('could not save camera looks: %s', e)
        log.info('look for %s: %s', name, look)
        return look

    def apply(self, name: str | None, data: bytes, offsets, sizes) -> bytes:
        """data: a tight I420 frame; offsets/sizes: (y, u, v) plane offsets and byte sizes."""
        look = self.by_name.get(name or '')
        if not look:
            return data
        t = self._cache.get(name)
        if t is None:
            t = self._cache[name] = _tables(look)
        ylut, uvlut = t
        a = np.frombuffer(data, dtype=np.uint8).copy()
        oy, ou, ov = offsets
        sy, su, sv = sizes
        a[oy:oy + sy] = ylut[a[oy:oy + sy]]
        a[ou:ou + su] = uvlut[a[ou:ou + su]]
        a[ov:ov + sv] = uvlut[a[ov:ov + sv]]
        return a.tobytes()
