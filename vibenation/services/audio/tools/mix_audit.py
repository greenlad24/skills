"""Mix audit: record the live master at a few spots through the engine and measure how it SOUNDS
(tonal balance, mud, harshness, punch, dynamics, width) — next to qa_spots.py, which measures levels.
Restores the transport afterwards. Optional reference tracks (e.g. a Scary Pockets song) are
measured the same way so the report shows the difference.

usage: python -m tools.mix_audit OUT_DIR ["Set 1@2874" ...] [--ref song.wav ...] [--seconds 30] [--force]
Refuses to run while the player is playing (someone may be listening) unless --force.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys

import aiohttp
import numpy as np
import soundfile as sf
from scipy import signal

URL = 'http://127.0.0.1:8091'
FORCE = '--force' in sys.argv
SR = 48000
BANDS = [  # name, lo, hi (Hz) — what a mix engineer listens for
    ('sub', 30, 60), ('kick/bass', 60, 120), ('warmth', 120, 250), ('mud', 250, 500), ('mids', 500, 2000),
    ('presence', 2000, 5000), ('harsh/sibilance', 5000, 10000), ('air', 10000, 16000),
]


# ---------- recording ----------

async def record(spots: list[tuple[str, float]], seconds: int, out: str) -> list[str]:
    files = []
    async with aiohttp.ClientSession() as http:
        st = await (await http.get(URL + '/state')).json()
        was = st['transport']
        if was.get('playing') and not FORCE:
            raise SystemExit('The player is playing (someone may be listening). Pause it first, or pass --force.')
        try:
            for set_name, pos in spots:
                await http.post(URL + '/cmd', json={'type': 'transport', 'action': 'load', 'set': set_name})
                await asyncio.sleep(1)
                await http.post(URL + '/cmd', json={'type': 'transport', 'action': 'seek', 'seconds': max(0, pos - 15)})
                await http.post(URL + '/cmd', json={'type': 'transport', 'action': 'play'})
                await asyncio.sleep(15)  # let compressors, riders and the leveller settle
                parts = []
                for _ in range(max(1, seconds // 10)):
                    await asyncio.sleep(10)
                    wav = await (await http.get(URL + '/clip.wav', params={'seconds': '10'})).read()
                    parts.append(sf.read(io.BytesIO(wav), dtype='float32')[0])
                path = os.path.join(out, f'{set_name.replace(" ", "")}-{int(pos)}.wav')
                sf.write(path, np.concatenate(parts), SR)
                files.append(path)
                print('recorded', path, file=sys.stderr)
        finally:
            await http.post(URL + '/cmd', json={'type': 'transport', 'action': 'pause'})
            await http.post(URL + '/cmd', json={'type': 'transport', 'action': 'load', 'set': was['set']})
            await asyncio.sleep(1)
            await http.post(URL + '/cmd', json={'type': 'transport', 'action': 'seek', 'seconds': was['position']})
            if was.get('playing'):
                await http.post(URL + '/cmd', json={'type': 'transport', 'action': 'play'})
    return files


# ---------- measuring ----------

def k_weight(x: np.ndarray, sr: int) -> np.ndarray:
    """ITU-R BS.1770 K-weighting (pre-filter shelf + RLB high-pass)."""
    b1, a1 = [1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585]
    b2, a2 = [1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621]
    if sr != 48000:  # coefficients are for 48 kHz
        x = signal.resample_poly(x, 48000, sr, axis=0)
    return signal.lfilter(b2, a2, signal.lfilter(b1, a1, x, axis=0), axis=0)


def lufs(x: np.ndarray, sr: int) -> float:
    y = k_weight(x, sr)
    blk, hop = int(0.4 * 48000), int(0.1 * 48000)
    ms = np.array([(y[i:i + blk] ** 2).mean(0).sum() for i in range(0, len(y) - blk, hop)])
    l = -0.691 + 10 * np.log10(ms + 1e-12)
    g = ms[l > -70]
    rel = -0.691 + 10 * np.log10(g.mean() + 1e-12) - 10
    g = ms[(l > -70) & (l > rel)]
    return float(-0.691 + 10 * np.log10(g.mean() + 1e-12))


def measure(path: str) -> dict:
    x, sr = sf.read(path, dtype='float64', always_2d=True)
    x = x[:, :2] if x.shape[1] >= 2 else np.repeat(x, 2, 1)
    mono = x.mean(1)
    # Tonal balance: energy per band relative to the mids, from a long-term spectrum.
    f, p = signal.welch(mono, sr, nperseg=16384)
    def band_db(lo, hi):
        return 10 * np.log10(p[(f >= lo) & (f < hi)].sum() + 1e-20)
    mid = band_db(500, 2000)
    tonal = {n: round(band_db(lo, hi) - mid, 1) for n, lo, hi in BANDS}
    # Dynamics: crest factor and short-term loudness range.
    peak = 20 * np.log10(np.abs(signal.resample_poly(x, 4, 1, axis=0)).max() + 1e-12)  # ~true peak
    rms = 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-12)
    blk = int(3 * sr)
    st = [lufs(x[i:i + blk], sr) for i in range(0, len(x) - blk, sr)]
    # Punch: how far drum hits stand out — 90th vs 50th percentile of a fast envelope in the kick and snare bands.
    def punch(lo, hi):
        b = signal.butter(4, [lo, hi], 'bandpass', fs=sr, output='sos')
        env = np.abs(signal.hilbert(signal.sosfilt(b, mono)))
        env = signal.sosfilt(signal.butter(2, 40, fs=sr, output='sos'), env)
        return round(float(20 * np.log10(np.percentile(env, 99) / (np.percentile(env, 50) + 1e-12))), 1)
    # Width: side energy relative to mid.
    m, s = (x[:, 0] + x[:, 1]) / 2, (x[:, 0] - x[:, 1]) / 2
    width = 10 * np.log10((s ** 2).mean() / ((m ** 2).mean() + 1e-20) + 1e-12)
    return {
        'file': os.path.basename(path), 'lufs': round(lufs(x, sr), 1), 'true_peak': round(peak, 1),
        'crest_db': round(peak - rms, 1), 'st_range_lu': round(float(np.percentile(st, 95) - np.percentile(st, 10)), 1) if st else None,
        'punch_kick': punch(50, 110), 'punch_snare': punch(150, 300), 'width_side_vs_mid_db': round(float(width), 1),
        'tonal_vs_mids_db': tonal,
    }


def report(rows: list[dict]) -> str:
    cols = [n for n, _, _ in BANDS]
    out = ['file                     LUFS  TP   crest punchK punchS width | ' + ' '.join(f'{c[:9]:>9}' for c in cols)]
    for r in rows:
        t = r['tonal_vs_mids_db']
        out.append(f"{r['file'][:24]:24} {r['lufs']:5} {r['true_peak']:4} {r['crest_db']:5} {r['punch_kick']:6} {r['punch_snare']:6} "
                   f"{r['width_side_vs_mid_db']:5} | " + ' '.join(f'{t[c]:>9}' for c in cols))
    return '\n'.join(out)


def main() -> None:
    args = sys.argv[1:]
    out = args.pop(0)
    os.makedirs(out, exist_ok=True)
    refs, spots, seconds = [], [], 30
    while args:
        a = args.pop(0)
        if a == '--ref':
            refs.append(args.pop(0))
        elif a == '--force':
            pass
        elif a == '--seconds':
            seconds = int(args.pop(0))
        else:
            s, p = a.split('@')
            spots.append((s, float(p)))
    files = asyncio.run(record(spots, seconds, out)) if spots else []
    rows = [measure(f) for f in files + refs]
    json.dump(rows, open(os.path.join(out, 'audit.json'), 'w'), indent=1)
    print(report(rows))


if __name__ == '__main__':
    main()
