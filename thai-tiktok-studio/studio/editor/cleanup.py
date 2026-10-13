"""Clean up your recorded voice-over without ever cutting a word.

What is removed:
- breaths and chuckles between phrases (soft, noisy, un-voiced sounds),
- clicks / bumps (very short sharp sounds on their own),
- false starts — ONLY when the transcript confirms you said the same words again,
- the silent middle of an over-long pause (the pause is shortened to MAX_PAUSE).

What is never removed: anything the transcript heard as a word, and any sound inside a pause —
only true silence is trimmed. `keep_all` mode (Settings) leaves the recording exactly as recorded.
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


def _overlaps_word(i: "Island", words: list) -> bool:
    return any(w["s"] < i.e + 0.04 and w["e"] > i.s - 0.04 for w in words)


def _text_in(i: "Island", words: list) -> str:
    from .transcribe import norm
    return norm("".join(w["w"] for w in words if w["s"] < i.e and w["e"] > i.s))


def classify(y: np.ndarray, isl: list, feats, words: list | None = None) -> list:
    db, voiced, flat, spec = feats
    f = lambda t: int(round(t / HOP))
    speech_db = np.median([db[f(i.s):f(i.e)].mean() for i in isl if i.e - i.s > 0.3] or [db.max()])
    for n, i in enumerate(isl):
        if words and _overlaps_word(i, words):
            continue                        # the transcript heard a word here: it stays, always
        a, b = f(i.s), max(f(i.s) + 1, f(i.e))
        dur = i.e - i.s
        alone = (n == 0 or i.s - isl[n - 1].e >= 0.25) and (n == len(isl) - 1 or isl[n + 1].s - i.e >= 0.25)
        if dur < 0.09 and alone and voiced[a:b].max() < 0.3:      # short un-voiced bang on its own, not a syllable
            i.kind = "click"
        elif (dur < 0.8 and np.median(voiced[a:b]) < 0.3 and np.median(flat[a:b]) > 0.2
              and db[a:b].mean() < speech_db - 6):
            i.kind = "breath"              # breath / chuckle: soft, noisy, no pitch
    if not words:
        return isl                         # no transcript → never guess at false starts
    from .transcribe import norm
    sp = [i for i in isl if i.kind == "speech"]
    for x, nxt in zip(sp, sp[1:]):
        if nxt.s - x.e > 1.6 or x.e - x.s > 2.5:
            continue
        a_txt, b_txt = _text_in(x, words), _text_in(nxt, words)
        # a false start: what you said first is just the beginning of what you said next
        if len(a_txt) >= 3 and len(b_txt) > len(a_txt) and b_txt.startswith(a_txt[: max(3, int(len(a_txt) * 0.8))]):
            x.kind = "false_start"
    return isl


def clean(y: np.ndarray, max_pause: float = MAX_PAUSE, words: list | None = None):
    """→ (cleaned audio, [(t0, t1)] phrases in the cleaned audio, report dict incl. "map")."""
    if y is None or len(y) < SR * 0.3:
        return y, [], {}
    words = words or []
    feats = features(y)
    db = feats[0]
    isl = classify(y, islands(db), feats, words)
    report = {k: sum(1 for i in isl if i.kind == k) for k in ("breath", "click", "false_start")}
    keep = [i for i in isl if i.kind == "speech"]
    if not keep:
        return y, [], report
    y = y.astype(np.float32).copy()
    fade = int(SR * FADE)
    for i in isl:                                  # mute breaths / clicks / confirmed false starts
        if i.kind == "speech":
            continue
        a, b = max(0, int((i.s - 0.02) * SR)), min(len(y), int((i.e + 0.02) * SR))
        env = np.zeros(b - a, dtype=np.float32)
        k = min(fade, (b - a) // 2)
        if k > 1:
            env[:k] = np.linspace(1, 0, k)
            env[-k:] = np.linspace(0, 1, k)
        y[a:b] *= env
    # sound anywhere (lower threshold than speech): never cut into it
    floor = np.percentile(db, 10)
    quiet = db < floor + 6
    for i in isl:
        if i.kind != "speech":                     # the muted bits count as silence now
            quiet[int(i.s / HOP): int(i.e / HOP) + 1] = True
    gone = [i for i in isl if i.kind == "false_start"]
    for w in words:                                # every word the transcript heard is protected…
        if any(w["s"] >= i.s - 0.05 and w["e"] <= i.e + 0.05 for i in gone):
            continue                               # …except the words of a confirmed restart
        quiet[max(0, int((w["s"] - 0.03) / HOP)): int((w["e"] + 0.03) / HOP) + 1] = False
    cuts = []                                      # [(a, b)] seconds of pure silence to drop
    for gi, (x, nxt) in enumerate(zip(keep, keep[1:])):
        g0, g1 = x.e + PAD, nxt.s - PAD
        if g1 - g0 <= max_pause:
            continue
        run_s = None
        for fi in range(int(g0 / HOP), int(g1 / HOP) + 1):    # longest silent stretch inside this pause
            q = fi < len(quiet) and quiet[fi]
            if q and run_s is None:
                run_s = fi
            if (not q or fi == int(g1 / HOP)) and run_s is not None:
                end = fi if not q else fi + 1
                cuts.append((run_s * HOP, end * HOP, gi, g1 - g0))
                run_s = None
    drop, shortened = [], 0
    by_gap = {}
    for a, b, gi, glen in cuts:
        by_gap.setdefault(gi, (glen, []))[1].append((a, b))
    for glen, runs in by_gap.values():
        excess, did = glen - max_pause, False
        for a, b in sorted(runs, key=lambda r: r[0] - r[1]):      # longest silent stretches first
            take = min(excess, (b - a) - 0.06)
            if take > 0.03:
                mid = (a + b) / 2
                drop.append((mid - take / 2, mid + take / 2))
                excess -= take
                did = True
            if excess <= 0.03:
                break
        shortened += did
    drop.sort()
    parts, kept, t, pos = [], [], 0.0, 0
    for a, b in drop + [(len(y) / SR, len(y) / SR)]:
        ia = int(a * SR)
        seg = y[pos:ia].copy()
        if len(seg) > 2 * fade and pos > 0:
            seg[:fade] *= np.linspace(0, 1, fade)
        if len(seg) > 2 * fade and ia < len(y):
            seg[-fade:] *= np.linspace(1, 0, fade)
        kept.append((pos / SR, ia / SR, t))
        parts.append(seg)
        t += len(seg) / SR
        pos = int(b * SR)
    out = np.concatenate(parts) if parts else y
    phrases = [(to_clean_time(i.s, kept), to_clean_time(i.e, kept)) for i in keep]
    report["pauses_shortened"] = shortened
    report["map"] = kept
    return out, phrases, report


def to_clean_time(t: float, kept: list) -> float:
    """Time in the original recording → time in the cleaned one (removed bits snap to the next kept sound)."""
    for a, b, start in kept:
        if t < a:
            return start
        if t <= b:
            return start + (t - a)
    return kept[-1][2] + (kept[-1][1] - kept[-1][0]) if kept else t
