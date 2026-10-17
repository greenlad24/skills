"""Offline sound recognition on a recorded stem: prints the role timeline the live engine
would see, and the switches the 8-second rule would confirm.

usage:
  python -m tools.classify_offline CH [SET] [--from MM:SS] [--to MM:SS] [--hop 2] [--windows]
    CH   channel number (11, 15, 16, 9, 10 ...) - file from vn_audio.player.CHANNEL_FILES
    SET  1 or 2 (default 1)
  --windows  also print every classified window

Activity ("is the source itself playing") is estimated offline like the engine does live:
the window's RMS within 12 dB of the stem's active level (90th percentile).
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np
import soundfile as sf

from vn_audio.classifier import (REGISTER_CHANNELS, REGISTER_SECONDS, ROLE_CHANNELS, SR_IN, WIN_IN, Switcher, Yamnet, classify)
from vn_audio.player import CHANNEL_FILES

STEMS = os.environ.get('VN_STEMS', '/root/vibenation-media/stems-2026-04-04')


def mmss(t: float) -> str:
    return f'{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}' if t >= 3600 else f'{int(t // 60):02d}:{int(t % 60):02d}'


def parse_t(s: str) -> float:
    p = [float(v) for v in s.split(':')]
    return sum(v * 60 ** i for i, v in enumerate(reversed(p)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('ch', type=int)
    ap.add_argument('set', nargs='?', default='1')
    ap.add_argument('--from', dest='t0', default='0')
    ap.add_argument('--to', dest='t1', default=None)
    ap.add_argument('--hop', type=float, default=2.0)
    ap.add_argument('--windows', action='store_true')
    a = ap.parse_args()
    suffix = '' if a.set == '1' else f'({a.set})'
    path = os.path.join(STEMS, f'{CHANNEL_FILES[a.ch]}{suffix}.wav')
    info = sf.info(path)
    t0 = parse_t(a.t0)
    t1 = min(info.duration, parse_t(a.t1)) if a.t1 else info.duration
    print(f'ch {a.ch}  {os.path.basename(path)}  {mmss(t0)}-{mmss(t1)}  hop {a.hop}s', flush=True)

    # Pass 1: window levels -> active level
    hop_n = int(a.hop * SR_IN)
    starts = list(range(int(t0 * SR_IN), int(t1 * SR_IN) - WIN_IN, hop_n))
    rms = []
    with sf.SoundFile(path) as f:
        for s in starts:
            f.seek(s)
            x = f.read(WIN_IN, dtype='float32')
            rms.append(10 * np.log10(np.mean(x * x) + 1e-12))
    rms = np.array(rms)
    active = float(np.percentile(rms, 90))
    thr = max(active - 12.0, -60.0)
    print(f'active level {active:.1f} dBFS, playing threshold {thr:.1f} dBFS', flush=True)

    model = Yamnet()
    roles = ROLE_CHANNELS.get(a.ch)
    default = {11: 'congas', 15: 'sax', 16: 'harmonica'}.get(a.ch)
    sw_role = Switcher(default) if roles else None
    sw_reg = Switcher(None, need=REGISTER_SECONDS) if a.ch in REGISTER_CHANNELS else None
    segs: list[list] = []  # [label, start, end, conf_sum, n]
    switches = []
    counts: dict[str, float] = {}
    cpu = 0.0
    nrun = 0
    with sf.SoundFile(path) as f:
        for s, r in zip(starts, rms):
            t = s / SR_IN
            if r < thr:
                label, conf = None, 0.0
                w = None
            else:
                f.seek(s)
                x = f.read(WIN_IN, dtype='float32')
                c0 = time.process_time()
                w = classify(model, a.ch, x)
                cpu += time.process_time() - c0
                nrun += 1
                if roles:
                    label, conf = w.role, w.conf
                else:
                    label, conf = w.register, w.reg_conf
            if a.windows and w:
                print(f'  {mmss(t)} {r:6.1f}dB  {str(label):9s} {conf:.2f}  f0 {w.f0:6.1f} v{w.voiced:.2f} on{w.onsets:4.1f} sh{w.sharp:5.1f} '
                      f'{w.scores}  reg={w.register}  {w.top}', flush=True)
            lab = label if (label and conf >= 0.55) else ('-' if label is None else '?')
            counts[lab] = counts.get(lab, 0) + a.hop
            if segs and segs[-1][0] == lab and t - segs[-1][2] <= a.hop + 0.01:
                segs[-1][2] = t + a.hop
                segs[-1][3] += conf
                segs[-1][4] += 1
            else:
                segs.append([lab, t, t + a.hop, conf, 1])
            for sw, kind, lbl, cf in ((sw_role, 'role', w.role if w else None, w.conf if w else 0),
                                       (sw_reg, 'register', w.register if w else None, w.reg_conf if w else 0)):
                if sw is None:
                    continue
                ev = sw.update(lbl if w else None, cf, t)
                if ev:
                    switches.append((t, kind, ev))

    print('\nTimeline (merged; "-" = not playing, "?" = unclear):')
    for lab, a0, a1, cs, n in segs:
        if lab == '-' and a1 - a0 < 20:
            continue
        print(f'  {mmss(a0)}-{mmss(a1)}  {a1 - a0:6.0f}s  {lab:9s}' + (f'  conf {cs / n:.2f}' if lab not in ('-', '?') else ''))
    print('\nConfirmed switches (8 s rule' + (', 16 s for register' if sw_reg else '') + '):')
    for t, kind, ev in switches:
        print(f'  {mmss(t)}  {kind}: {ev["from"]} -> {ev["to"]}  (conf {ev["confidence"]}, {ev["seconds"]} s)')
    tot = sum(v for k, v in counts.items() if k != '-') or 1
    print('\nPlaying time by label: ' + ', '.join(f'{k} {v / 60:.1f} min ({100 * v / tot:.0f}%)' for k, v in sorted(counts.items(), key=lambda kv: -kv[1]) if k != '-'))
    if nrun:
        print(f'CPU per window (classify incl. resample+YIN+YAMNet): {1000 * cpu / nrun:.1f} ms over {nrun} windows')


if __name__ == '__main__':
    sys.exit(main())
