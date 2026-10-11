"""Your own voice-over: split one recorded take into per-beat lines at natural pauses.

You read a video's whole script in one go. We find the phrases (speech between pauses),
then cut the recording into one chunk per spoken beat at the pause closest to where
that line should end (by text length). Each chunk is placed exactly at its beat, so
picture, captions and voice never drift apart. Long pauses inside a line are tightened.
"""

from __future__ import annotations

import numpy as np

from . import audio_io, media

SR = audio_io.SR
MAX_PAUSE = 0.22   # longer pauses inside a line are shortened to this
EDGE = 0.06        # breathing room kept before/after speech


def _phrases(path) -> list:
    isl = media.speech_islands(path, min_silence=0.18, noise_db=-35)
    if not isl:
        info = media.probe(path)
        return [(0.0, info["duration"])]
    merged = [list(isl[0])]
    for s, e in isl[1:]:
        if s - merged[-1][1] < 0.12:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged if e - s > 0.08]


def _choose_cuts(phrases: list, weights: list) -> list:
    """Indices of phrase gaps to cut at (len = beats-1), monotonic, nearest to text targets."""
    k = len(weights)
    if k <= 1:
        return []
    speech = [e - s for s, e in phrases]
    total = sum(speech) or 1.0
    cum, acc = [], 0.0
    for d in speech[:-1]:          # cumulative speech time at each gap
        acc += d
        cum.append(acc / total)
    wt = sum(weights) or 1
    targets, a = [], 0.0
    for w in weights[:-1]:
        a += w
        targets.append(a / wt)
    if len(cum) < k - 1:           # fewer pauses than lines → caller falls back
        return []
    cuts, lo = [], 0
    for i, t in enumerate(targets):
        hi = len(cum) - (len(targets) - i - 1)   # leave gaps for the remaining cuts
        best = min(range(lo, hi), key=lambda g: abs(cum[g] - t))
        cuts.append(best)
        lo = best + 1
    return cuts


def _render_chunk(y: np.ndarray, phrases: list) -> np.ndarray:
    parts = []
    for n, (s, e) in enumerate(phrases):
        a = max(0, int((s - EDGE) * SR))
        b = min(len(y), int((e + EDGE) * SR))
        parts.append(y[a:b])
        if n < len(phrases) - 1:
            gap = min(MAX_PAUSE, phrases[n + 1][0] - e)
            parts.append(np.zeros(max(0, int(gap * SR)), dtype=np.float32))
    return np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)


def split_recording(path, weights: list) -> list | None:
    """→ one float32 array per spoken beat, or None if the file can't be read."""
    y = audio_io.decode(path)
    if y is None or not len(y):
        return None
    peak = float(np.max(np.abs(y))) or 1.0
    y = (y / peak * 0.89).astype(np.float32)        # normalise loudness of phone recordings
    phrases = _phrases(path)
    cuts = _choose_cuts(phrases, weights)
    if len(weights) > 1 and not cuts:
        # not enough pauses: cut proportionally by time (rare — e.g. one breathless take)
        s0, e0 = phrases[0][0], phrases[-1][1]
        wt = sum(weights) or 1
        bounds, a = [s0], s0
        for w in weights:
            a += (e0 - s0) * w / wt
            bounds.append(a)
        return [_render_chunk(y, [(bounds[i], bounds[i + 1])]) for i in range(len(weights))]
    groups, start = [], 0
    for c in cuts + [len(phrases) - 1]:
        groups.append(phrases[start:c + 1])
        start = c + 1
    return [_render_chunk(y, g) for g in groups]
