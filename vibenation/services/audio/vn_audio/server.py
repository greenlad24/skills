"""VibeNation audio service: mix engine + measurements + listen stream.

Local API (127.0.0.1:8091, reached only through the web server):
  GET  /state        engine snapshot + transport
  POST /cmd          {"type": ..., ...}  see handle()
  GET  /ws           meters/spectrum/loudness frames (~10 Hz) and state changes
  GET  /stream.mp3   the master mix, for listening in the browser
"""

from __future__ import annotations

import asyncio
import copy
import json
import math
import logging
import os
import subprocess
import threading
import time
from collections import deque

from aiohttp import WSMsgType, web

from . import presets as P
from .analyzer import Analyzer
from .graph import COMP, LIMITER, MCOMP, MTAPE, MixGraph, port
from .modhost import ModHost
from .player import StemPlayer

log = logging.getLogger('vn_audio')
STEMS = os.environ.get('VN_STEMS', '/root/vibenation-media/stems-2026-04-04')
DATA = os.environ.get('VN_DATA', os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data'))
LINKED = {6: 7, 7: 6}  # piano L/R share one trim so the stereo image holds
HOST, PORT = '127.0.0.1', int(os.environ.get('VN_AUDIO_PORT', '8091'))


class Engine:
    def __init__(self) -> None:
        t0 = time.time()
        self.player = StemPlayer(STEMS)
        log.info('player ready %.1f s', time.time() - t0)
        self.analyzer = Analyzer()
        self.mh = ModHost.launch()
        log.info('plugin host up %.1f s', time.time() - t0)
        self.gr = [0.0] * 16
        self.bus_gr = 0.0
        self.ride = [0.0] * 16  # current rider gain (dB) per channel
        self.lar_hist: deque = deque(maxlen=150)  # 15 s of vocal-over-band while singing
        self.last_lar = 0.0
        self.ride_lvl: list[deque] = [deque(maxlen=4) for _ in range(16)]  # 400 ms of channel power
        self.ride_ref: list[deque] = [deque(maxlen=600) for _ in range(16)]  # 60 s of active levels
        self.st_hist: deque = deque(maxlen=120)  # short-term loudness history for the leveller brake
        self.limiter_gr = 0.0
        self.mh.feedback(self._feedback)
        a = self.analyzer.client.name
        self.graph = MixGraph(
            self.mh,
            sources=self.player.port_names,
            outputs=[[f'{a}:master_l', f'{a}:master_r']],
        )
        self.state_file = os.path.join(DATA, 'mix_state.json')
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file) as fh:
                    self.graph.load(json.load(fh))
                log.info('restored mix from %s', self.state_file)
            except (OSError, ValueError) as e:
                log.warning('could not restore mix: %s', e)
        self.graph.build()
        # Analysis taps: each strip after its compressor (pre-fader), and the master before the limiter.
        for n in range(1, 17):
            self.mh.connect_ports(self.graph.strip_out(n), f'{a}:ch_{n}')
        for n, src in enumerate(self.player.port_names, 1):
            self.mh.connect_ports(src, f'{a}:raw_{n}')
        self.mh.connect_ports(port(MTAPE, 'out_l'), f'{a}:pre_l')
        self.mh.connect_ports(port(MTAPE, 'out_r'), f'{a}:pre_r')
        self.leveller_on = True
        # Soundcheck calibration: digital trims so each source's active level sits near -20 dBFS RMS.
        self.calibrating_until = 0.0
        self.active: list[deque] = [deque(maxlen=600) for _ in range(16)]
        self.last_trim = 0.0
        self.locked = [False] * 16
        self.calibrated_session = False
        self.analyzer.listeners.append(self._on_frame)
        self.stream = Mp3Stream(self.mh)
        self.subscribers: set[asyncio.Queue] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.last_level = 0.0

    # mod-host feedback: compressor gain reduction meters (linear gain, 1 = none)
    def _feedback(self, msg: str) -> None:
        if msg == 'data_finish':  # mod-host waits for this before sending the next batch
            threading.Thread(target=self._ready, daemon=True).start()
            return
        parts = msg.split()
        if len(parts) == 4 and parts[0] == 'output_set':
            inst, val = int(parts[1]), float(parts[3])
            if parts[2] == 'gr' and inst == MCOMP:
                self.bus_gr = round(abs(val), 1)
            elif parts[2] == 'rlm' and COMP < inst <= COMP + 16:
                self.gr[inst - COMP - 1] = round(-20 * math.log10(max(val, 1e-6)), 1)


    def _ready(self) -> None:
        time.sleep(0.05)
        try:
            self.mh.cmd('output_data_ready')
        except Exception:  # noqa: BLE001 - next batch will retry
            pass

    def _on_frame(self, f: dict) -> None:
        m = f['master']
        self.limiter_gr = round(max(0.0, m['prePeak'] + self.graph.master_gain - m['peak']), 1)
        self._level(m)
        self._calibrate(f['raw'])
        self._ride(f)
        self._keep_vocals_on_top(f)
        frame = {'type': 'meters', **f, 'gr': self.gr, 'ride': self.ride, 'master': {**m, 'limiterGr': self.limiter_gr, 'busGr': self.bus_gr, 'drive': round(self.graph.master_gain, 1), 'bandOffset': round(self.graph.band_offset, 1)}}
        self.broadcast(frame)

    def _level(self, m: dict) -> None:
        """Master loudness leveller (after master_me): rides short-term loudness toward -16 LUFS,
        up at most 1 dB/s and down 3 dB/s, within -10..+20 dB of drive. A brake freezes it when
        the music drops more than 14 dB under its recent median (song ends, talk, breaks)."""
        now = time.time()
        if not self.leveller_on or now - self.last_level < 1.0 or not self.player.playing:
            return
        self.last_level = now
        s = m['lufsS']
        if s > -60:
            self.st_hist.append(s)
        if s < -40 or len(self.st_hist) < 5:
            return
        median = sorted(self.st_hist)[len(self.st_hist) // 2]
        if s < median - 14:  # brake
            return
        err = P.TARGET_LUFS - s
        if abs(err) < 0.5:
            return
        if err > 0 and self.limiter_gr > 4:  # louder would only mean more limiting: fix it upstream
            return
        step = max(-3.0, min(1.0, err * 0.3))
        g = max(-10.0, min(20.0, self.graph.master_gain + step))
        if abs(g - self.graph.master_gain) >= 0.05:
            self.graph.master_gain = round(g, 2)
            self.mh.param(LIMITER, 'gain', self.graph.master_gain)

    def _ride(self, f: dict) -> None:
        """Vocal/solo rider: keeps a channel near its own running level (+ Claude's offset),
        only while the source itself is playing. Up 1 dB/s, down 3 dB/s, within ±3 dB."""
        g = self.graph
        for n, s in g.strips.items():
            if s.rider is None:
                continue
            i = n - 1
            ride = g.ride.get(n, 0.0)
            lvl = f['rms'][i] - ride  # level before the ride
            self.ride_lvl[i].append(10 ** (lvl / 10))
            if f['raw'][i] < -50 or g.mute[n]:
                continue  # silent or only bleed: hold the current ride
            short = 10 * math.log10(sum(self.ride_lvl[i]) / len(self.ride_lvl[i]))
            self.ride_ref[i].append(short)
            if len(self.ride_ref[i]) < 50:
                continue
            ref = sorted(self.ride_ref[i])[len(self.ride_ref[i]) // 2]
            if short < ref - 15:
                continue  # a breath or a pause, not a quiet phrase
            want = max(-3.0, min(3.0, ref + s.rider - short))
            if abs(want - ride) < 0.5:
                continue
            new = ride + max(-0.3, min(0.1, want - ride))
            g.ride[n] = round(new, 2)
            self.ride[i] = round(new, 1)
            g.apply_gain(n)

    def _keep_vocals_on_top(self, f: dict) -> None:
        """Holds the lead-vocal-to-band ratio near +5 dB by moving one shared offset on all
        non-vocal channels (their balance against each other stays as set). Only learns while
        a vocal is actually singing; moves at most 0.5 dB every 2 s, range -12..+3 dB."""
        g = self.graph
        p = [10 ** ((f['rms'][i] + g.gain_db(i + 1)) / 10) * (0 if g.mute[i + 1] else 1) for i in range(16)]
        voc = sum(p[i - 1] for i in P.VOCALS)
        band = sum(p) - voc
        sing = any(f['raw'][i - 1] > -50 for i in P.VOCALS) and voc > 1e-7 and band > 1e-9
        if sing:
            self.lar_hist.append(10 * math.log10(voc / band))
        now = time.time()
        if now - self.last_lar < 2 or len(self.lar_hist) < 30:
            return
        self.last_lar = now
        lar = sorted(self.lar_hist)[len(self.lar_hist) // 2]
        err = P.TARGET_LAR - lar
        if abs(err) < 1.0:
            return
        new = max(-12.0, min(3.0, g.band_offset - max(-0.5, min(0.5, err * 0.25))))
        if abs(new - g.band_offset) >= 0.05:
            g.band_offset = round(new, 2)
            for k in g.strips:
                if k not in P.VOCALS:
                    g.apply_fader(k)
                    g.apply_sends(k)

    def start_calibration(self, minutes: float = 20) -> None:
        """Soundcheck: for the next `minutes` of playback, set each channel's digital trim
        so its active level (90th percentile of 100 ms RMS) sits near -20 dBFS.
        A channel locks once it has heard 30 s of real signal; silent channels stay at 0."""
        for d in self.active:
            d.clear()
        self.locked = [False] * 16
        self.calibrating_until = time.time() + minutes * 60

    def _calibrate(self, raw: list[float]) -> None:
        if not self.player.playing or time.time() > self.calibrating_until:
            return
        for i, v in enumerate(raw):
            if v > -50:  # the source itself is playing (not hiss or stage bleed)
                self.active[i].append(v)
        now = time.time()
        if now - self.last_trim < 5:
            return
        self.last_trim = now
        changed = False
        for n, s in self.graph.strips.items():
            d = self.active[n - 1]
            if self.locked[n - 1] or len(d) < 50:
                continue
            level = sorted(d)[int(len(d) * 0.9)]
            want = max(-20.0, min(30.0, -20.0 - level))
            pair = LINKED.get(n)
            if pair and len(self.active[pair - 1]) >= 50:  # stereo pair: one trim from the louder side
                other = sorted(self.active[pair - 1])[int(len(self.active[pair - 1]) * 0.9)]
                want = max(-20.0, min(30.0, -20.0 - max(level, other)))
            step = max(-6.0, min(6.0, want - s.trim))
            if abs(step) >= 0.5:
                s.trim = round(s.trim + step, 1)
                changed = True
            if len(d) >= 300 and abs(want - s.trim) < 1:
                self.locked[n - 1] = True
        if all(self.locked[i] or len(self.active[i]) == 0 for i in range(16)) and any(self.locked):
            self.calibrating_until = 0
            changed = True
        if changed:
            for k in self.graph.strips:
                self.graph.apply_gain(k)
            self.save()
            self.broadcast(self.state())

    def save(self) -> None:
        os.makedirs(DATA, exist_ok=True)
        tmp = self.state_file + '.tmp'
        with open(tmp, 'w') as fh:
            json.dump(self.graph.snapshot(), fh)
        os.replace(tmp, self.state_file)

    def broadcast(self, msg: dict) -> None:
        if not self.loop:
            return
        data = json.dumps(msg, separators=(',', ':'))
        for q in list(self.subscribers):
            self.loop.call_soon_threadsafe(_offer, q, data)

    def state(self) -> dict:
        return {'type': 'engine', 'mix': self.graph.snapshot(), 'transport': self.player.status(), 'leveller': self.leveller_on,
                'calibrating': self.calibrating_until > time.time()}

    # ---------- commands ----------

    def handle(self, c: dict) -> dict:
        g, t = self.graph, c.get('type')
        n = int(c.get('ch', 0))
        s = g.strips.get(n)
        if t == 'fader' and s:
            s.fader = max(-60.0, min(10.0, float(c['db'])))
            g.apply_fader(n)
            g.apply_sends(n)
        elif t == 'pan' and s:
            s.pan = max(-100.0, min(100.0, float(c['pan'])))
            g.apply_fader(n)
        elif t in ('mute', 'solo') and s:
            getattr(g, t)[n] = bool(c['on'])
            g.apply_fader(n)
            g.apply_sends(n)
        elif t == 'send' and s and c.get('fx') in ('plate', 'room', 'delay'):
            setattr(s, c['fx'], None if c.get('db') is None else max(-60.0, min(6.0, float(c['db']))))
            g.apply_sends(n)
        elif t == 'eq' and s:
            i = int(c['band'])
            kind, f, gain, q = s.eq[i] if i < len(s.eq) else ('bell', 1000.0, 0.0, 1.0)
            if s.no_hpf and c.get('kind', kind) == 'hpf':
                raise ValueError('No high-pass on kick or bass (band rule).')
            band = (c.get('kind', kind), float(c.get('f', f)), max(-15.0, min(15.0, float(c.get('gain', gain)))), float(c.get('q', q)))
            s.eq = [*s.eq, band] if i >= len(s.eq) else [band if j == i else b for j, b in enumerate(s.eq)]
            g.apply_strip(n)
        elif t == 'comp' and s and s.comp:
            for k in ('thresh', 'ratio', 'attack', 'release', 'makeup', 'mix'):
                if k in c:
                    setattr(s.comp, k, float(c[k]))
            g.apply_strip(n)
        elif t == 'rider' and s and s.rider is not None:
            s.rider = max(-3.0, min(3.0, float(c['target'])))  # offset around the channel's own level
        elif t == 'fx' and c.get('fx') in g.fx:
            g.fx[c['fx']].update({k: v for k, v in c.items() if k not in ('type', 'fx')})
            g.apply_fx()
        elif t == 'bpm':
            g.set_bpm(float(c['bpm']))
        elif t == 'transport':
            act = c.get('action')
            if act == 'play':
                if not self.player.playing and not self.calibrated_session:
                    self.calibrated_session = True  # first play after start: (re)calibrate trims
                    self.start_calibration()
                self.player.play()
            elif act == 'pause':
                self.player.pause()
            elif act == 'seek':
                self.player.seek(float(c['seconds']) * self.player.client.samplerate)
            elif act == 'load':
                self.player.load(str(c['set']))
            if act in ('seek', 'load'):
                self.analyzer.loud.reset_integrated()
        elif t == 'calibrate':
            self.start_calibration(float(c.get('minutes', 20)))
        elif t == 'leveller':
            self.leveller_on = bool(c['on'])
        elif t == 'reset':
            self.graph.strips = {st.n: st for st in copy.deepcopy(P.STRIPS)}
            for k in range(1, 17):
                g.mute[k] = g.solo[k] = False
                g.apply_strip(k)
        else:
            raise ValueError(f'unknown command {t!r}')
        if t not in ('transport', 'leveller'):
            self.save()
        st = self.state()
        self.broadcast(st)
        return st


def _offer(q: asyncio.Queue, data: str) -> None:
    if q.full():
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
    q.put_nowait(data)


class Mp3Stream:
    """ffmpeg reads the master from JACK and encodes MP3 for browser listening."""

    def __init__(self, mh: ModHost):
        self.mh = mh
        self.listeners: set[asyncio.Queue] = set()
        self.proc: subprocess.Popen | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        threading.Thread(target=self._run, name='mp3', daemon=True).start()

    def _run(self) -> None:
        while True:
            self.proc = subprocess.Popen(
                ['ffmpeg', '-loglevel', 'error', '-f', 'jack', '-channels', '2', '-i', 'vn_stream',
                 '-c:a', 'libmp3lame', '-b:a', '192k', '-f', 'mp3', '-'],
                stdout=subprocess.PIPE,
            )
            threading.Thread(target=self._connect, daemon=True).start()
            assert self.proc.stdout
            while chunk := self.proc.stdout.read(4096):
                for q in list(self.listeners):
                    if self.loop:
                        self.loop.call_soon_threadsafe(_offer, q, chunk)
            self.proc.wait()
            time.sleep(1)

    def _connect(self) -> None:
        for _ in range(50):
            try:
                self.mh.connect_ports(port(LIMITER, 'outL'), 'vn_stream:input_1')
                self.mh.connect_ports(port(LIMITER, 'outR'), 'vn_stream:input_2')
                return
            except Exception:  # noqa: BLE001 - ports appear once ffmpeg registers them
                time.sleep(0.2)


# ---------- HTTP ----------

def make_app(engine: Engine) -> web.Application:
    app = web.Application()

    async def state(_req: web.Request) -> web.Response:
        return web.json_response(engine.state())

    async def cmd(req: web.Request) -> web.Response:
        try:
            body = await req.json()
            return web.json_response(await asyncio.to_thread(engine.handle, body))
        except (ValueError, KeyError) as e:
            return web.json_response({'error': str(e)}, status=400)

    async def ws(req: web.Request) -> web.WebSocketResponse:
        sock = web.WebSocketResponse(heartbeat=20)
        await sock.prepare(req)
        q: asyncio.Queue = asyncio.Queue(maxsize=20)
        engine.subscribers.add(q)
        await sock.send_str(json.dumps(engine.state()))

        async def pump():
            while True:
                await sock.send_str(await q.get())

        task = asyncio.create_task(pump())
        try:
            async for msg in sock:
                if msg.type == WSMsgType.TEXT:
                    try:
                        await asyncio.to_thread(engine.handle, json.loads(msg.data))
                    except (ValueError, KeyError) as e:
                        await sock.send_str(json.dumps({'type': 'error', 'error': str(e)}))
        finally:
            task.cancel()
            engine.subscribers.discard(q)
        return sock

    async def stream(req: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse(headers={'Content-Type': 'audio/mpeg', 'Cache-Control': 'no-store'})
        await resp.prepare(req)
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        engine.stream.listeners.add(q)
        try:
            while True:
                await resp.write(await q.get())
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            engine.stream.listeners.discard(q)
        return resp

    async def on_start(_app: web.Application) -> None:
        loop = asyncio.get_running_loop()
        engine.loop = loop
        engine.stream.start(loop)

    app.router.add_get('/state', state)
    app.router.add_post('/cmd', cmd)
    app.router.add_get('/ws', ws)
    app.router.add_get('/stream.mp3', stream)
    app.on_startup.append(on_start)
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
    engine = Engine()
    log.info('mix graph built; %s sets available', engine.player.sets.keys())
    web.run_app(make_app(engine), host=HOST, port=PORT, print=None)


if __name__ == '__main__':
    main()
