"""Clean up your recorded voice-over: no awkward pauses, breaths, clicks or false starts.

Only whole sounds BETWEEN words are touched — every spoken word stays exactly as recorded,
so the voice never sounds chopped:

- long pauses are shortened to a natural beat (MAX_PAUSE), short ones are left alone;
- breaths (soft, noisy, un-voiced sounds between phrases) are removed;
- clicks / bumps (very short sharp sounds) are removed;
- false starts: when you start a phrase, stop and say it again, the first attempt is
  removed (the later take is kept), detected by comparing the sound of the two starts.

Joins get short crossfades so there are no clicks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SR = 48000
HOP = 0.01                # 10 ms analysis frames
MAX_PAUSE = 0.42          # longest pause kept between phrases
MIN_KEEP_PAUSE = 0.16     # pauses shorter than this are never touched
PAD = 0.05                # air kept around each phrase so consonants aren't clipped
FADE = 0.012


@dataclass
class Island:
    s: float
    e: float
    kind: str = "speech"  # speech | breath | click | false_start


def _frames(y: np.ndarray, win: int, hop: int) -> np.ndarray:
    n = max(1, 1 + (len(y) - win) // hop)
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    return y[np.minimum(idx, len(y) - 1)]


def features(y: np.ndarray):
    """Per 10 ms: loudness (dB), voicing (pitch strength 0-1), spectral flatness (0 tonal … 1 noise)."""
    hop, win = int(SR * HOP), int(SR * 0.03)
    fr = _frames(y, win, hop) * np.hanning(win)[None, :]
    rms = np.sqrt((fr ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    spec = np.abs(np.fft.rfft(fr, axis=1)) + 1e-9
    band = spec[:, int(80 * win / SR): int(5000 * win / SR)]
    flat = np.exp(np.log(band).mean(axis=1)) / band.mean(axis=1)
    # voicing: normalised autocorrelation peak in the 75-400 Hz pitch range
    ac = np.fft.irfft(spec ** 2, axis=1)[:, : int(SR / 75) + 1]
    lo, hi = int(SR / 400), int(SR / 75)
    voiced = (ac[:, lo:hi].max(axis=1) / (ac[:, 0] + 1e-9)).clip(0, 1)
    return db, voiced, flat, spec


def islands(db: np.ndarray, min_gap: float = 0.12) -> list:
    """Sound regions using an adaptive threshold (works for quiet and loud phone recordings)."""
    floor = np.percentile(db, 10)
    peak = np.percentile(db, 95)
    thr = max(floor + 10, peak - 32)
    on = db > thr
    out, i, n = [], 0, len(on)
    while i < n:
        if on[i]:
            j = i
            while j < n and on[j]:
                j += 1
            out.append([i * HOP, j * HOP])
            i = j
        else:
            i += 1
    merged = []
    for s, e in out:
        if merged and s - merged[-1][1] < min_gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [Island(s, e) for s, e in merged]


def _mfcc(spec: np.ndarray, nb: int = 26, nc: int = 13) -> np.ndarray:
    """Speech fingerprint per frame (MFCC 1-12, normalised over the whole recording)."""
    n = spec.shape[1]
    hz = np.linspace(0, SR / 2, n)
    mel = lambda f: 2595 * np.log10(1 + f / 700)
    hzp = 700 * (10 ** (np.linspace(mel(60), mel(7000), nb + 2) / 2595) - 1)
    fb = np.zeros((nb, n))
    for i in range(nb):
        lo, c, hi = hzp[i], hzp[i + 1], hzp[i + 2]
        fb[i] = np.clip(np.minimum((hz - lo) / (c - lo), (hi - hz) / (hi - c)), 0, None)
    lm = np.log(spec ** 2 @ fb.T + 1e-10)
    dct = np.cos(np.pi / nb * (np.arange(nb)[None, :] + 0.5) * np.arange(nc)[:, None])
    cc = (lm @ dct.T)[:, 1:]
    return (cc - cc.mean(axis=0)) / (cc.std(axis=0) + 1e-6)


def _dtw(a: np.ndarray, b: np.ndarray) -> float:
    """Average frame distance along the best alignment (lower = more alike)."""
    n, m = len(a), len(b)
    d = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).mean(axis=2))
    acc = np.full((n + 1, m + 1), np.inf)
    acc[0, 0] = 0
    for i in range(1, n + 1):
        for j in range(max(1, i - 25), min(m, i + 25) + 1):
            acc[i, j] = d[i - 1, j - 1] + min(acc[i - 1, j], acc[i, j - 1], acc[i - 1, j - 1])
    return float(acc[n, m] / (n + m))


def classify(y: np.ndarray, isl: list, feats) -> list:
    db, voiced, flat, spec = feats
    f = lambda t: int(round(t / HOP))
    speech_db = np.median([db[f(i.s):f(i.e)].mean() for i in isl if i.e - i.s > 0.3] or [db.max()])
    for n, i in enumerate(isl):
        a, b = f(i.s), max(f(i.s) + 1, f(i.e))
        dur = i.e - i.s
        alone = (n == 0 or i.s - isl[n - 1].e >= 0.25) and (n == len(isl) - 1 or isl[n + 1].s - i.e >= 0.25)
        if dur < 0.09 and alone and voiced[a:b].max() < 0.3:      # short un-voiced bang on its own, not a syllable
            i.kind = "click"
        elif (dur < 0.9 and np.median(voiced[a:b]) < 0.35 and np.median(flat[a:b]) > 0.18
              and db[a:b].mean() < speech_db - 4):
            i.kind = "breath"
    mel = _mfcc(spec)
    sp = [i for i in isl if i.kind == "speech"]

    def start(i, L):
        return mel[f(i.s): f(i.s) + L]
    for k, (x, nxt) in enumerate(zip(sp, sp[1:])):
        gap, dur = nxt.s - x.e, x.e - x.s
        if dur > 2.2 or gap > 1.6 or dur < 0.15 or dur > (nxt.e - nxt.s) + 0.3:
            continue
        L = f(min(dur, 1.2))
        A = start(x, L)
        if len(A) < 8:
            continue
        d_next = _dtw(A, start(nxt, L))
        # how different does this attempt sound from your OTHER phrases? (relative, so it works for any voice/mic)
        others = [o for j, o in enumerate(sp) if j not in (k, k + 1) and o.e - o.s >= dur * 0.8][:8]
        if len(others) < 2:
            continue
        base = float(np.median([_dtw(A, start(o, L)) for o in others]))
        if d_next < 0.7 * base:       # measured on real Thai narration: repeats ≈0.4-0.55, normal ≈0.9-1.0
            x.kind = "false_start"     # the first attempt sounds like the start of the next phrase
    return isl


def clean(y: np.ndarray, max_pause: float = MAX_PAUSE):
    """→ (cleaned audio, [(t0, t1)] phrases in the cleaned audio, report dict)."""
    if y is None or len(y) < SR * 0.3:
        return y, [], {}
    feats = features(y)
    isl = classify(y, islands(feats[0]), feats)
    keep = [i for i in isl if i.kind == "speech"]
    report = {k: sum(1 for i in isl if i.kind == k) for k in ("breath", "click", "false_start")}
    if not keep:
        return y, [], report
    parts, phrases, t = [], [], 0.0
    fade = int(SR * FADE)
    ramp = np.linspace(0, 1, fade, dtype=np.float32)
    shortened, prev_b = 0, None
    for i in keep:
        a = max(0, int((i.s - PAD) * SR))
        b = min(len(y), int((i.e + PAD) * SR))
        if prev_b is not None:
            a = max(a, prev_b)                     # never play the same sound twice
            orig = (a - prev_b) / SR
            gap = orig if orig <= MIN_KEEP_PAUSE else min(orig, max_pause)
            shortened += orig > gap + 0.01
            parts.append(np.zeros(int(gap * SR), dtype=np.float32))
            t += int(gap * SR) / SR
        seg = y[a:b].astype(np.float32).copy()
        if len(seg) > 2 * fade:
            seg[:fade] *= ramp
            seg[-fade:] *= ramp[::-1]
        phrases.append((t + (i.s - a / SR), t + (i.e - a / SR)))
        parts.append(seg)
        t += len(seg) / SR
        prev_b = b
    report["pauses_shortened"] = shortened
    return np.concatenate(parts), phrases, report
