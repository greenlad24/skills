"""Run the arrangement follower over a whole recorded set, offline (no engine, no player: the live
mix and anyone listening are untouched). Levels are computed exactly like the analyzer: 100 ms RMS
per channel plus the soundcheck trims from data/mix_state.json.

usage: python -m tools.arrangement_sim ["Set 1"] [--events]
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import soundfile as sf

from vn_audio.arrangement import FPS, Arrangement
from vn_audio.player import find_sets

STEMS = os.environ.get('VN_STEMS', '/home/vibe/vibenation-media/stems-2026-04-04')
STATE = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'mix_state.json')
NAMES = {1: 'Kick', 2: 'Snare', 3: 'OH', 4: 'Ac DI', 5: 'Gtr amp', 6: 'Piano', 7: 'Piano R', 8: 'Gtr DI', 9: 'Vox centre',
         10: 'Vox piano', 11: 'Congas', 12: 'Bass', 13: 'Util 3', 14: 'DI 2', 15: 'Sax', 16: 'Harmonica'}


def levels(path: str) -> np.ndarray:
    """100 ms RMS in dBFS, like the analyzer's raw meters."""
    blk = 48000 // FPS
    out = []
    with sf.SoundFile(path) as f:
        while True:
            x = f.read(blk * 600, dtype='float32', always_2d=True)
            if not len(x):
                break
            x = x.mean(1)
            n = len(x) // blk
            r = np.sqrt((x[: n * blk].reshape(n, blk) ** 2).mean(1))
            out.append(20 * np.log10(r + 1e-9))
    return np.concatenate(out)


def mmss(i: int) -> str:
    s = i // FPS
    return f'{s // 60:02d}:{s % 60:02d}'


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    set_name = args[0] if args else 'Set 1'
    files = find_sets(STEMS)[set_name]
    trims = {int(k): v.get('trim', 0.0) for k, v in json.load(open(STATE)).get('strips', {}).items()}
    lv = {n: levels(p) for n, p in files.items()}
    frames = min(len(v) for v in lv.values())
    arr = Arrangement()
    roles_t = {n: {} for n in range(1, 17)}
    events, last = [], None
    for i in range(frames):
        raw = {n: float(lv[n][i]) for n in lv}
        playing = {n: raw[n] + trims.get(n, 0) > -32 and raw[n] > -60 for n in raw}
        arr.frame(playing, {n: raw[n] + trims.get(n, 0) for n in raw}, raw)
        for n in range(1, 17):
            r = arr.role(n) or 'normal'
            roles_t[n][r] = roles_t[n].get(r, 0) + 1
        s = arr.summary()
        key = (s['lead'], tuple(s['backing']), s['solo'])
        if key != last:
            events.append((i, s))
            last = key
    dur = frames / FPS / 60
    print(f'{set_name}: {dur:.1f} min')
    leads = [e[1]['lead'] for e in events]
    sw = sum(1 for a, b in zip(leads, leads[1:]) if a and b and a != b)
    solos = [(e[0], e[1]['solo']) for e in events if e[1]['solo']]
    print(f'lead switches (one singer to another, no gap): {sw}; solo starts: {len(solos)}')
    for n in range(1, 17):
        t = roles_t[n]
        parts = ', '.join(f'{k} {100 * v / frames:.0f}%' for k, v in sorted(t.items(), key=lambda kv: -kv[1]) if k != 'normal')
        if parts:
            print(f'  ch{n:2} {NAMES[n]:10} {parts}')
    if '--events' in sys.argv:
        for i, s in events:
            who = f"lead {NAMES.get(s['lead'], '-')}" + (f", backing {', '.join(NAMES[b] for b in s['backing'])}" if s['backing'] else '') + (f", SOLO {NAMES[s['solo']]}" if s['solo'] else '')
            print(f'  {mmss(i)}  {who}')


if __name__ == '__main__':
    main()
