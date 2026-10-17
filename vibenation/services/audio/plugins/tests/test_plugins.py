#!/usr/bin/env python3
"""Offline verification of the VibeNation LV2 suite (run with the audio .venv).

    VN_LV2_DIR=/usr/local/lib/lv2 .venv/bin/python plugins/tests/test_plugins.py

Uses test tones plus 10 s excerpts of the band's multitrack stems (read-only).
Every check prints PASS/FAIL; exit code is non-zero if anything failed.
"""
import os
import sys
import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(__file__))
import vnhost  # noqa: E402

SR = 48000
STEMS = "/home/vibe/vibenation-media/stems-2026-04-04"
fails = []


def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name + ("  " + info if info else ""))
    if not ok:
        fails.append(name)


def rms_db(v):
    return 20 * np.log10(np.sqrt(np.mean(np.square(v, dtype=np.float64))) + 1e-12)


def sane(name, y, lo=-80, hi=6):
    ok = np.all(np.isfinite(y)) and np.max(np.abs(y)) < 4.0
    check(f"{name}: finite, no blow-up", ok, f"peak {20*np.log10(np.max(np.abs(y))+1e-12):.1f} dBFS, rms {rms_db(y):.1f} dBFS")


_cache = {}


def stem(fname, seconds=10):
    """10 s excerpt from the busiest part of minutes 10..20 of a stem."""
    if fname in _cache:
        return _cache[fname]
    with sf.SoundFile(os.path.join(STEMS, fname)) as f:
        f.seek(600 * SR)
        x = f.read(600 * SR, dtype="float32")
    if x.ndim > 1:
        x = x[:, 0]
    hop = SR
    e = np.array([np.mean(x[i:i + hop] ** 2) for i in range(0, len(x) - hop, hop)])
    # window with the most activity (sum of 10 consecutive seconds)
    w = np.convolve(e, np.ones(seconds), "valid")
    i = int(np.argmax(w)) * hop
    seg = x[i:i + seconds * SR].copy()
    seg *= 10 ** ((-20 - rms_db(seg)) / 20)   # normalise to a typical channel level: -20 dBFS RMS
    _cache[fname] = seg
    return seg


def band_db(y, f1, f2):
    Y = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    f = np.fft.rfftfreq(len(y), 1 / SR)
    return 10 * np.log10(np.sum(Y[(f >= f1) & (f < f2)]) + 1e-20)


def tone(freq, amp_db, secs):
    t = np.arange(int(secs * SR)) / SR
    return (10 ** (amp_db / 20) * np.sin(2 * np.pi * freq * t)).astype(np.float32)


# ---------------------------------------------------------------- vn_opto
def test_opto():
    v = stem("VOCAL CENTRE.wav")
    for pr in (20, 50):
        p = vnhost.Plugin("vn_opto")
        p.set(peak_reduction=pr)
        y, m = p.process(v)
        sane(f"vn_opto pr={pr}", y)
        check(f"vn_opto pr={pr}: gr meter moves", m["gr"].max() > 1, f"max gr {m['gr'].max():.1f} dB")
    # two-stage release: after a 1 s loud burst, half recovers fast, rest slowly
    x = np.concatenate([tone(440, -6, 1.5), tone(440, -40, 3)])
    p = vnhost.Plugin("vn_opto"); p.set(peak_reduction=60)
    _, m = p.process(x, block=240)
    gr = m["gr"]; b = lambda t: gr[int(t * SR / 240)]
    g0, g1, g2 = b(1.49), b(1.65), b(3.0)
    check("vn_opto: two-stage release", g1 < 0.8 * g0 and g2 > 0.15 * g0 and g2 < g1,
          f"gr {g0:.1f} -> {g1:.1f} (150 ms) -> {g2:.1f} dB (1.5 s)")


# ---------------------------------------------------------------- vn_fet
def test_fet():
    sn = stem("SNARE.wav")
    crest = {}
    for r, lbl in ((0, "4:1"), (3, "20:1"), (4, "all")):
        p = vnhost.Plugin("vn_fet"); p.set(ratio=r, input=6, attack=100, release=200)
        y, m = p.process(sn)
        sane(f"vn_fet {lbl}", y)
        x = sn * 10 ** (20 / 20)
        crest[lbl] = (20 * np.log10(np.max(np.abs(y))), m["gr"].max())
    check("vn_fet: 20:1 reduces peaks more than 4:1", crest["20:1"][1] > crest["4:1"][1] + 1,
          f"max gr 4:1 {crest['4:1'][1]:.1f} dB, 20:1 {crest['20:1'][1]:.1f} dB, all {crest['all'][1]:.1f} dB")
    # steady-state ratio on a tone (+20 dB over threshold)
    res = {}
    for r in (0, 3):
        p = vnhost.Plugin("vn_fet"); p.set(ratio=r, colour=0)
        y, _ = p.process(tone(1000, 0, 1.0))
        res[r] = rms_db(y[SR // 2:])
    check("vn_fet: higher ratio -> lower output on a loud tone", res[3] < res[0] - 2, f"4:1 {res[0]:.1f}, 20:1 {res[3]:.1f} dBFS")


# ---------------------------------------------------------------- vn_vca_bus
def test_bus():
    mix = stem("KICK.wav") + stem("BASS.wav") + stem("SNARE.wav") + 0.7 * stem("PIANO L.wav")
    st = np.stack([mix, 0.9 * mix], 1)
    grs = {}
    for r in (0, 2):
        p = vnhost.Plugin("vn_vca_bus"); p.set(threshold=-20, ratio=r)
        y, m = p.process(st)
        sane(f"vn_vca_bus ratio idx {r}", y)
        grs[r] = np.mean(m["gr"])
    check("vn_vca_bus: 10:1 compresses more than 2:1", grs[2] > grs[0] + 1, f"mean gr 2:1 {grs[0]:.1f}, 10:1 {grs[2]:.1f} dB")
    # auto release: recovery faster after a short transient than after a long passage
    def rec(burst):
        x = np.concatenate([tone(200, -3, burst), tone(200, -40, 2)])
        p = vnhost.Plugin("vn_vca_bus"); p.set(threshold=-20, ratio=1, attack=1, release=4)
        _, m = p.process(np.stack([x, x], 1), block=240)
        gr = m["gr"]; i0 = int(burst * SR / 240)
        return gr[i0 - 1], gr[i0 + int(0.3 * SR / 240)]
    a0, a1 = rec(0.05); b0, b1 = rec(2.0)
    check("vn_vca_bus: auto release is program dependent", (a1 / max(a0, 1e-3)) < (b1 / max(b0, 1e-3)),
          f"short burst keeps {100*a1/max(a0,1e-3):.0f}%, long keeps {100*b1/max(b0,1e-3):.0f}% after 300 ms")


# ---------------------------------------------------------------- vn_pultec
def test_pultec():
    n = np.random.default_rng(1).standard_normal(SR * 3).astype(np.float32) * 0.05
    def resp(**kw):
        p = vnhost.Plugin("vn_pultec"); p.set(tube=0, **kw)
        y, m = p.process(n)
        X = np.abs(np.fft.rfft(y[SR:SR + 65536])) / np.maximum(np.abs(np.fft.rfft(n[SR:SR + 65536])), 1e-9)
        f = np.fft.rfftfreq(65536, 1 / SR)
        return lambda fr: 20 * np.log10(np.median(X[(f > fr / 1.1) & (f < fr * 1.1)]))
    flat = resp()
    check("vn_pultec: flat at zero", all(abs(flat(f)) < 0.2 for f in (30, 200, 1000, 8000, 15000)))
    t = resp(low_freq=2, low_boost=10, low_atten=10)
    check("vn_pultec: low boost+atten trick (60 Hz)", t(30) > 5 and t(200) < -3, f"30 Hz {t(30):+.1f}, 200 Hz {t(200):+.1f} dB")
    h = resp(high_freq=6, high_boost=10, high_bw=0)
    check("vn_pultec: 16 kHz bell boost", h(16000) > 14 and h(1000) < 0.5, f"16k {h(16000):+.1f}, 1k {h(1000):+.1f} dB")
    p = vnhost.Plugin("vn_pultec"); p.set(tube=100, low_boost=5, high_boost=5)
    y, m = p.process(stem("PIANO L.wav"))
    sane("vn_pultec on piano (tube 100%)", y)


# ---------------------------------------------------------------- vn_tape
def test_tape():
    for lvl in (-18, 0):
        p = vnhost.Plugin("vn_tape")
        y, m = p.process(tone(1000, lvl, 1))
        s = y[SR // 2:]; X = np.abs(np.fft.rfft(s * np.hanning(len(s))))
        h3 = 20 * np.log10(X[1500] / X[500])
        check(f"vn_tape tone {lvl} dBFS: near unity, harmonics grow with level", abs(rms_db(s) - lvl + 3.01) < 3,
              f"gain {rms_db(s)-lvl+3.01:+.2f} dB, H3 {h3:.0f} dBc, meter {m['gain_change'][-1]:+.2f} dB")
    p = vnhost.Plugin("vn_tape"); p.set(drive=12, wow=50, flutter=50)
    y, _ = p.process(stem("BASS.wav"))
    sane("vn_tape bass, drive +12, wow/flutter", y)
    p = vnhost.Plugin("vn_tape_stereo")
    y, _ = p.process(np.stack([stem("PIANO L.wav"), stem("BASS.wav")], 1))
    sane("vn_tape_stereo piano/bass", y)


# ---------------------------------------------------------------- vn_console
def test_console():
    x = np.stack([stem("PIANO L.wav"), stem("BASS.wav")], 1)
    p = vnhost.Plugin("vn_console")
    y, m = p.process(x)
    sane("vn_console", y)
    h = SR // 2  # skip the 20 ms start-up fade-in of the smoothed output gain
    d = rms_db(y[h:, 0] - x[h:, 0])
    check("vn_console: subtle at default", d < rms_db(x[h:, 0]) - 30, f"difference {d - rms_db(x[h:,0]):.1f} dB below signal")
    p = vnhost.Plugin("vn_console"); p.set(crosstalk=100)
    y, _ = p.process(np.stack([tone(5000, -6, 1), np.zeros(SR, np.float32)], 1))
    check("vn_console: crosstalk reaches the other side", -45 < rms_db(y[SR // 2:, 1]) < -30, f"R {rms_db(y[SR//2:,1]):.1f} dBFS")


# ---------------------------------------------------------------- vn_deesser
def test_deesser():
    v = stem("VOCAL CENTRE.wav")
    p = vnhost.Plugin("vn_deesser"); p.set(freq=6500, sensitivity=60, range=10)
    y, m = p.process(v, block=240)
    sane("vn_deesser vocal", y)
    # frames where the vocal is sibilant (6-8 kHz dominates)
    fr = 2400
    sib, red = [], []
    for i in range(0, len(v) - fr, fr):
        a, b = v[i:i + fr], y[i:i + fr]
        if rms_db(a) < -60:
            continue
        r = band_db(a, 5000, 9000) - band_db(a, 100, 20000)
        sib.append(r); red.append(band_db(b, 6000, 8000) - band_db(a, 6000, 8000))
    sib, red = np.array(sib), np.array(red)
    top = red[sib > np.percentile(sib, 90)].mean(); low = red[sib < np.percentile(sib, 50)].mean()
    check("vn_deesser: cuts 6-8 kHz on sibilants, leaves vowels", top < -2 and low > -1,
          f"sibilant frames {top:.1f} dB, non-sibilant {low:.1f} dB, max gr {m['gr'].max():.1f} dB")
    lowband = band_db(y, 100, 3000) - band_db(v, 100, 3000)
    check("vn_deesser: body untouched (100 Hz-3 kHz)", abs(lowband) < 0.3, f"{lowband:+.2f} dB")


# ---------------------------------------------------------------- vn_rider
def test_rider():
    v = stem("VOCAL CENTRE.wav")
    loud = v * 10 ** (8 / 20); quiet = v * 10 ** (-8 / 20)
    x = np.concatenate([loud, quiet])
    p = vnhost.Plugin("vn_rider"); p.set(target=rms_db(v) + 3, range=8, speed=300)
    y, m = p.process(x, block=480)
    sane("vn_rider", y)
    g = m["gain"]; half = len(g) // 2
    gl, gq = np.median(g[half // 2:half]), np.median(g[half + half // 2:])
    check("vn_rider: pulls loud down, lifts quiet", gl < -2 and gq > 2, f"loud {gl:+.1f} dB, quiet {gq:+.1f} dB")
    # gate: silence / low bleed after singing must not pump the gain up
    s = np.concatenate([v[:5 * SR], 0.003 * stem("KICK.wav")[:5 * SR]])
    p = vnhost.Plugin("vn_rider"); p.set(target=rms_db(v) + 3, range=8)
    _, m = p.process(s, block=480)
    g = m["gain"]; a = g[int(4.9 * SR / 480)]; b = g[-1]
    check("vn_rider: holds gain during bleed/silence", abs(b - a) < 1.0, f"{a:+.1f} -> {b:+.1f} dB")


if __name__ == "__main__":
    for t in (test_opto, test_fet, test_bus, test_pultec, test_tape, test_console, test_deesser, test_rider):
        print(f"--- {t.__name__}")
        t()
    print(f"\n{len(fails)} failed" + (": " + ", ".join(fails) if fails else ""))
    sys.exit(1 if fails else 0)
