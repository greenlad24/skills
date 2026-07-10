"""Synthetic audio fixtures with ground truth, for DSP-layer tests.

Deterministic (seeded), generated in-memory — no binary fixtures in git.
"""

import numpy as np

SR = 48000


def _env_ar(n, attack, release, sr=SR):
    e = np.ones(n)
    a = int(attack * sr)
    r = int(release * sr)
    if a > 0:
        e[:a] = np.linspace(0, 1, a)
    if r > 0:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def synth_instrumental(dur_s: float, seed: int = 1) -> np.ndarray:
    """Band bed: bass line + sustained chord pad + drum-ish noise bursts."""
    rng = np.random.default_rng(seed)
    n = int(dur_s * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)

    # bass: slow root movement
    roots = [55.0, 73.4, 61.7, 82.4]
    seg = n // len(roots)
    for i, f in enumerate(roots):
        sl = slice(i * seg, (i + 1) * seg if i < len(roots) - 1 else n)
        tt = t[sl]
        out[sl] += 0.25 * np.sin(2 * np.pi * f * tt) \
            + 0.1 * np.sin(2 * np.pi * 2 * f * tt)

    # pad: detuned saw-ish chord (static pitch, no vibrato, no syllables)
    for f in (220.0, 277.2, 329.6):
        for h in range(1, 6):
            out += (0.04 / h) * np.sin(2 * np.pi * f * h * t + rng.uniform(0, 6))

    # drums: noise bursts every ~0.5 s
    period = int(0.5 * SR)
    for start in range(0, n - 2000, period):
        burst = rng.normal(0, 0.35, 1600) * _env_ar(1600, 0.001, 0.02)
        out[start:start + 1600] += burst
    return (out / (np.max(np.abs(out)) + 1e-9) * 0.5).astype(np.float64)


def synth_vocal(dur_s: float, f0: float = 220.0, seed: int = 2,
                vibrato_hz: float = 5.5, vibrato_cents: float = 40.0,
                syllable_hz: float = 3.5) -> np.ndarray:
    """A sung voice: harmonic series on a moving F0 with vibrato, formant
    coloration, and syllabic amplitude modulation."""
    rng = np.random.default_rng(seed)
    n = int(dur_s * SR)
    t = np.arange(n) / SR

    # melody: slow pitch drift + vibrato (in cents)
    drift = 80.0 * np.sin(2 * np.pi * 0.15 * t + rng.uniform(0, 6))
    vib = vibrato_cents * np.sin(2 * np.pi * vibrato_hz * t)
    f0_t = f0 * (2.0 ** ((drift + vib) / 1200.0))
    phase = 2 * np.pi * np.cumsum(f0_t) / SR

    # harmonics with a crude formant envelope (peaks ~500 / 1500 / 2500 Hz)
    out = np.zeros(n)
    for h in range(1, 14):
        fh = f0 * h
        formant = (np.exp(-((fh - 500) / 350) ** 2)
                   + 0.7 * np.exp(-((fh - 1500) / 500) ** 2)
                   + 0.5 * np.exp(-((fh - 2500) / 700) ** 2))
        out += (formant / h ** 0.5) * np.sin(h * phase)

    # syllables: smoothed on/off amplitude gating
    syl = 0.5 * (1 + np.sign(np.sin(2 * np.pi * syllable_hz * t + 0.3)))
    kernel = np.ones(int(0.03 * SR)) / int(0.03 * SR)
    syl = np.convolve(syl, kernel, mode="same")
    out *= (0.15 + 0.85 * syl)
    out += rng.normal(0, 0.003, n)  # breathiness
    return (out / (np.max(np.abs(out)) + 1e-9) * 0.5).astype(np.float64)


def synth_lead_guitar(dur_s: float, seed: int = 3) -> np.ndarray:
    """The honest hard case: a sustained lead line with vibrato but no
    syllabic modulation and a brighter, more static spectrum."""
    rng = np.random.default_rng(seed)
    n = int(dur_s * SR)
    t = np.arange(n) / SR
    notes = [330.0, 392.0, 440.0, 494.0, 392.0, 330.0]
    seg = n // len(notes)
    out = np.zeros(n)
    for i, f in enumerate(notes):
        sl = slice(i * seg, (i + 1) * seg if i < len(notes) - 1 else n)
        tt = t[sl] - t[sl.start]
        vib = 25.0 * np.sin(2 * np.pi * 5.0 * tt)
        ft = f * (2.0 ** (vib / 1200.0))
        ph = 2 * np.pi * np.cumsum(ft) / SR
        tone = np.zeros(len(tt))
        for h in range(1, 9):
            tone += (1.0 / h ** 0.7) * np.sin(h * ph)
        out[sl] += tone * np.exp(-0.5 * tt / (len(tt) / SR + 1e-9))
    out += rng.normal(0, 0.002, n)
    return (out / (np.max(np.abs(out)) + 1e-9) * 0.5).astype(np.float64)


def mix(*tracks, gains=None) -> np.ndarray:
    n = max(len(x) for x in tracks)
    out = np.zeros(n)
    gains = gains or [1.0] * len(tracks)
    for x, g in zip(tracks, gains):
        out[:len(x)] += g * x
    peak = np.max(np.abs(out)) + 1e-9
    return (out / peak * 0.6).astype(np.float64)


def synth_speech(dur_s: float, f0: float = 120.0, seed: int = 4) -> np.ndarray:
    """Conversational speech-ish signal (for podcast-side tests): pitch
    wobble, strong syllabic AM, pauses between 'phrases'."""
    v = synth_vocal(dur_s, f0=f0, seed=seed, vibrato_hz=2.0,
                    vibrato_cents=90.0, syllable_hz=4.5)
    n = len(v)
    t = np.arange(n) / SR
    phrases = 0.5 * (1 + np.sign(np.sin(2 * np.pi * 0.25 * t + 1.0)))
    kernel = np.ones(int(0.05 * SR)) / int(0.05 * SR)
    phrases = np.convolve(phrases, kernel, mode="same")
    return (v * (0.05 + 0.95 * phrases)).astype(np.float64)
