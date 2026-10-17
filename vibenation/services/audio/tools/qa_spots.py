"""Mix QA on a recording: plays spots across each set through the live engine and
reports loudness, true peak, limiter work, compression, rider moves and vocal-to-band ratio.

usage: python -m tools.qa_spots [seconds_per_spot] [spots_per_set]
"""

import asyncio
import json
import math
import sys

import aiohttp

URL = 'http://127.0.0.1:8091'


def pw(db):
    return 10 ** (db / 10)


async def main(dur=45, per_set=6):
    async with aiohttp.ClientSession() as http:
        st = await (await http.get(URL + '/state')).json()
        sets = st['transport']['sets']
        rows = []
        async with http.ws_connect(URL + '/ws') as ws:
            for set_name in sets:
                await http.post(URL + '/cmd', json={'type': 'transport', 'action': 'load', 'set': set_name})
                await asyncio.sleep(1)
                st = await (await http.get(URL + '/state')).json()
                length = st['transport']['length']
                for k in range(per_set):
                    pos = 240 + (length - 420) * k / max(1, per_set - 1)
                    loop = asyncio.get_running_loop()
                    for _try in range(4):  # skip talk/breaks: move on a minute if the band is quiet
                        await http.post(URL + '/cmd', json={'type': 'transport', 'action': 'seek', 'seconds': pos})
                        await http.post(URL + '/cmd', json={'type': 'transport', 'action': 'play'})
                        t1, quiet = loop.time(), []
                        while loop.time() - t1 < 6:
                            d = json.loads((await ws.receive(timeout=5)).data)
                            if d['type'] == 'meters':
                                quiet.append(max(d['raw']) < -45)
                        if sum(quiet) < len(quiet) * 0.5:
                            break
                        pos += 60
                    frames, t0 = [], None
                    cur = await (await http.get(URL + '/state')).json()
                    faders = {int(n): v['fader'] for n, v in cur['mix']['strips'].items()}
                    t0 = loop.time()
                    while loop.time() - t0 < dur:
                        msg = await ws.receive(timeout=5)
                        d = json.loads(msg.data)
                        if d['type'] == 'engine':
                            faders = {int(n): v['fader'] for n, v in d['mix']['strips'].items()}
                        elif d['type'] == 'meters' and loop.time() - t0 > 12:
                            frames.append(d)
                    if not frames:
                        continue
                    faders = faders or {n: 0 for n in range(1, 17)}
                    last = frames[-1]['master']
                    tp = max(f['master']['truePeak'] for f in frames)
                    lim = max(f['master']['limiterGr'] for f in frames)
                    st_vals = [f['master']['lufsS'] for f in frames]
                    gr = [round(sum(f['gr'][i] for f in frames) / len(frames), 1) for i in range(16)]
                    ride = [round(sum(f.get('ride', [0] * 16)[i] for f in frames) / len(frames), 1) for i in range(16)]
                    # vocal (ch 9+10) vs everything else, post-fader RMS power
                    lar = []
                    for f in frames:
                        off = f['master'].get('bandOffset', 0.0)
                        p = [pw(f['rms'][i] + faders[i + 1] + (0 if i in (8, 9) else off)) for i in range(16)]
                        voc, band = p[8] + p[9], sum(p) - p[8] - p[9]
                        if (f.get('singing', [False] * 16)[8] or f.get('singing', [False] * 16)[9]) and band > 0:
                            lar.append(10 * math.log10(voc / band))
                    lar_s = f'{sorted(lar)[len(lar) // 2]:+.1f}' if lar else '  n/a'
                    rows.append((set_name, int(pos), last['lufsI'], min(st_vals), max(st_vals), tp, lim, lar_s, gr, ride, last.get('drive')))
                    print(f"{set_name} {int(pos)//60:3d}:{int(pos)%60:02d}  I {last['lufsI']:6.1f}  S {min(st_vals):6.1f}..{max(st_vals):6.1f}  TP {tp:5.1f}  lim {lim:4.1f}  LAR {lar_s}  drive {last.get('drive')}  band {last.get('bandOffset')}  bus {last.get('busGr')}", flush=True)
                    print('     GR  ', gr, flush=True)
                    print('     ride', ride, flush=True)
        await http.post(URL + '/cmd', json={'type': 'transport', 'action': 'pause'})


if __name__ == '__main__':
    asyncio.run(main(*(int(a) for a in sys.argv[1:3])))
