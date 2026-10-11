"""Sound effects synthesized in code — royalty-free by construction, no downloads."""

from __future__ import annotations

import functools

import numpy as np

SR = 48000


def _t(dur):
    return np.arange(int(SR * dur)) / SR


def _env(n, attack=0.004, decay=0.15):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-t / max(decay, 1e-4))


def pop():
    t = _t(0.12)
    f = 900 * np.exp(-t * 28) + 260
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(len(t), 0.002, 0.035)


def click():
    t = _t(0.04)
    return np.sin(2 * np.pi * 2200 * t) * _env(len(t), 0.0005, 0.008)


def tick():
    t = _t(0.06)
    return (np.sin(2 * np.pi * 1600 * t) + 0.4 * np.sin(2 * np.pi * 3200 * t)) * _env(len(t), 0.001, 0.012) * 0.6


def ding():
    t = _t(0.9)
    tone = sum(a * np.sin(2 * np.pi * f * t) for f, a in ((1318.5, 1), (2637, 0.35), (3955, 0.12)))
    return tone * _env(len(t), 0.002, 0.28) * 0.6


def cash():
    """Cash-register 'ka-ching': click + two bright bells."""
    out = np.zeros(int(SR * 0.9))
    c = click() * 1.2
    out[: len(c)] += c
    t = _t(0.75)
    for start, f in ((0.07, 2093), (0.16, 2637)):
        bell = (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 2.01 * t)) * _env(len(t), 0.001, 0.2) * 0.45
        i = int(SR * start)
        out[i:i + len(bell)] += bell[: len(out) - i]
    return out


def whoosh():
    rng = np.random.default_rng(7)
    n = int(SR * 0.45)
    noise = rng.standard_normal(n)
    # sweep a simple one-pole low-pass up then down for a "whoosh"
    t = np.arange(n) / n
    cutoff = 0.02 + 0.25 * np.sin(np.pi * t)
    y = np.zeros(n)
    acc = 0.0
    for i in range(n):
        acc += cutoff[i] * (noise[i] - acc)
        y[i] = acc
    env = np.sin(np.pi * t) ** 1.5
    return y * env * 2.2


def boom():
    t = _t(0.7)
    f = 120 * np.exp(-t * 6) + 38
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(len(t), 0.002, 0.25)
    rng = np.random.default_rng(3)
    hit = rng.standard_normal(len(t)) * _env(len(t), 0.0005, 0.02) * 0.4
    return (body + hit) * 0.95


def sparkle():
    out = np.zeros(int(SR * 0.7))
    t = _t(0.25)
    for k, f in enumerate((2637, 3136, 3520, 4186, 3951)):
        s = np.sin(2 * np.pi * f * t) * _env(len(t), 0.001, 0.06) * 0.3
        i = int(SR * 0.07 * k)
        out[i:i + len(s)] += s
    return out


def shutter():
    rng = np.random.default_rng(11)
    out = np.zeros(int(SR * 0.16))
    for start in (0.0, 0.07):
        n = int(SR * 0.05)
        burst = rng.standard_normal(n) * _env(n, 0.0005, 0.012) * 0.5
        i = int(SR * start)
        out[i:i + n] += burst
    return out


def riser():
    t = _t(1.2)
    f = 200 + 1400 * (t / t[-1]) ** 2
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.clip(t / 1.2, 0, 1) ** 2 * 0.35


def boing():
    t = _t(0.5)
    f = 300 + 120 * np.sin(2 * np.pi * 9 * t) * np.exp(-t * 5)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(len(t), 0.002, 0.18) * 0.7


BANK = {"pop": pop, "click": click, "tick": tick, "ding": ding, "cash": cash, "whoosh": whoosh, "boom": boom,
        "sparkle": sparkle, "shutter": shutter, "riser": riser, "boing": boing}
LEVEL = {"boom": 0.55, "whoosh": 0.4, "riser": 0.35}  # relative loudness under the voice


@functools.lru_cache(maxsize=32)
def get(name: str) -> np.ndarray:
    fn = BANK.get(name)
    if not fn:
        return np.zeros(1)
    y = fn().astype(np.float32)
    peak = float(np.max(np.abs(y))) or 1.0
    return y / peak * LEVEL.get(name, 0.45)
