"""VibeNation video program service.

Control API on 127.0.0.1:8092 (see README.md). Run: python -m vn_video.server
"""
from __future__ import annotations

import asyncio
import faulthandler
import logging
import os
import signal
import shutil
import time

from aiohttp import web
from PIL import Image

from . import graphics
from .audio import Audio
from .cams import Cams
from .config import OUTPUT_PROFILES, SLATES, Settings, load
from .gst import Gst
from .outputs import Destination
from .program import Program, encode_jpeg, render

log = logging.getLogger('vn_video')
LAYOUTS = ('close', 'band')


class Service:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.program_cam: int | None = None
        self.slate: str | None = None
        self.slate_ends: float | None = None     # epoch seconds (countdown target)
        self.vertical = {'mode': 'auto', 'pick': 'close', 'x': 0.5, 'closeCam': None, 'wideCam': None}
        self.info = graphics.Info()
        self.audio_delay_ms = cfg.audio_delay_ms
        self.dests: dict[str, Destination] = {}
        self.subs: dict[str, list[Destination]] = {k: [] for k in OUTPUT_PROFILES}
        self.prog = Program(cfg, self._on_encoded)
        self.audio = Audio(cfg.audio, cfg.jack_ports, self._on_audio, cfg.slate_music_dir, cfg.slate_music_db)
        self.cams = Cams(cfg.livekit_url, cfg.livekit_key, cfg.livekit_secret, cfg.room, self._on_frame)
        self.error: str | None = None
        self.cpu = 0.0
        self.encoder_load: float | None = None
        self._cpu_prev = (time.time(), self._cpu_ticks())
        self._vert_n = 0
        self._layout = None
        self._slate_key = None
        self._strip_key = None
        self.started = time.time()

    # ---------- derived ----------
    @property
    def layout(self) -> str:
        v = self.vertical
        return v['pick'] if v['mode'] == 'auto' else v['mode']

    def close_cam(self):
        return self.vertical['closeCam'] or self.program_cam

    def wide_cam(self):
        return self.vertical['wideCam'] or self.program_cam

    # ---------- data paths ----------
    def _on_encoded(self, prof, sample, ts, key):
        for d in self.subs[prof]:
            d.push_video(sample, ts, key)

    def _on_audio(self, sample, ts):
        self.prog_audio_caps = sample.get_caps()
        ts += int(self.audio_delay_ms * 1e6)
        for d in list(self.dests.values()):
            d.push_audio(sample, ts)

    @property
    def acaps(self):          # used by Destination when it builds its pipeline
        return self.audio.caps

    def _on_frame(self, cam_id: int, frame):
        targets = []
        if cam_id == self.program_cam:
            targets.append(self.prog.srcA)
        vert_live = self.prog.enc_stats['9x16']['active']
        if not vert_live:
            # Vertical not streaming: keep it ticking at a low rate for snapshots/preview.
            self._vert_n += 1
        if vert_live or self._vert_n % 10 == 0:
            if cam_id == self.close_cam():
                targets.append(self.prog.srcC)
            if self.layout == 'band' and cam_id == self.wide_cam():
                targets.append(self.prog.srcW)
        if not targets:
            return
        sample = self.prog.wrap_frame(frame)
        if sample is not None:
            for t in targets:
                self.prog.push(t, sample)

    # ---------- control ----------
    def set_program(self, cam):
        self.program_cam = int(cam) if cam is not None else None
        self._wanted()

    def _wanted(self):
        want = {c for c in (self.program_cam, self.close_cam(), self.wide_cam() if self.layout == 'band' else None) if c}
        self.cams.wanted = want
        self.cams.apply_quality()

    def apply_vertical(self):
        self.prog.set_crop(self.vertical['x'])
        lay = self.layout
        if lay == self._layout:
            self._wanted()
            return
        self._layout = lay
        band = lay == 'band'
        g = self.prog.pipe.get_by_name
        # Open the branches for the new layout first, flip visibility a few frames later.
        if band:
            g('vv_bclose').set_property('drop', False)
            g('vv_wide').set_property('drop', False)
        else:
            g('vv_close').set_property('drop', False)

        def flip():
            if self._layout != lay:
                return
            self.prog.pad_alpha('vert', 1, 0.0 if band else 1.0)
            for i in (2, 3, 4):
                self.prog.pad_alpha('vert', i, 1.0 if band else 0.0)
            g('vv_close').set_property('drop', band)
            g('vv_bclose').set_property('drop', not band)
            g('vv_wide').set_property('drop', not band)
        asyncio.get_running_loop().call_later(0.15, flip)
        self._wanted()

    async def refresh_strip(self):
        key = self.info.key()
        if key == self._strip_key:
            return
        self._strip_key = key
        p = self.cfg.profile
        rgba = await render(graphics.render_strip, p.vw, p.strip_h, self.info)
        self.prog.push_still(self.prog.strip, rgba)

    async def refresh_slate(self, force=False):
        """Render + push the slate (once per second while a countdown runs)."""
        p = self.cfg.profile
        if not self.slate:
            if self._slate_key is not None:
                self._slate_key = None
                self.prog.pad_alpha('prog', 2, 0.0)
                self.prog.pad_alpha('vert', 5, 0.0)
            return
        timed = graphics.MODES[self.slate]['time']
        remaining = max(0, int(round(self.slate_ends - time.time()))) if (timed and self.slate_ends) else None
        key = (self.slate, remaining, self.info.key())
        if key == self._slate_key and not force:
            return
        first = self._slate_key is None
        self._slate_key = key
        a = await render(graphics.render_slate, self.slate, p.w, p.h, remaining, self.info)
        b = await render(graphics.render_slate, self.slate, p.vw, p.vh, remaining, self.info)
        if self.slate is None:   # cleared while rendering
            return
        self.prog.push_still(self.prog.slate16, a)
        self.prog.push_still(self.prog.slate9, b)
        if first:
            await asyncio.sleep(0.1)   # let the frame reach the compositor before showing it
            if self.slate:
                self.prog.pad_alpha('prog', 2, 1.0)
                self.prog.pad_alpha('vert', 5, 1.0)

    def start_dests(self, items):
        for it in items:
            name = str(it.get('name') or '').strip()
            prof = it.get('profile')
            if not name or prof not in OUTPUT_PROFILES:
                raise ValueError(f'each destination needs name and profile in {list(OUTPUT_PROFILES)}')
            d = Destination(name, str(it.get('url') or ''), str(it.get('key') or ''), prof, self)
            old = self.dests.pop(name, None)
            if old:
                old.stop()
            self.dests[name] = d
        self._resub()

    def stop_dests(self, names):
        for n in (list(self.dests) if names is True else names):
            d = self.dests.pop(n, None)
            if d:
                d.stop()
        self._resub()

    def _resub(self):
        subs = {k: [] for k in OUTPUT_PROFILES}
        for d in self.dests.values():
            subs[d.profile].append(d)
        self.subs = subs
        for k in OUTPUT_PROFILES:
            self.prog.set_encoder_active(k, bool(subs[k]))
            if subs[k]:
                self.prog.request_keyframe(k)

    async def command(self, body: dict):
        if 'program' in body:
            self.set_program(body['program'])
        if 'info' in body:
            i = body['info'] or {}
            inf = self.info
            inf.show_name = str(i.get('showName', inf.show_name))[:120]
            inf.channel = str(i.get('channel', inf.channel))[:60]
            inf.song = str(i.get('song', inf.song))[:120]
            inf.now_playing = str(i.get('nowPlaying', inf.now_playing))[:120]
            if isinstance(i.get('colors'), list) and len(i['colors']) == 3:
                inf.colors = tuple(str(c) for c in i['colors'])
            if isinstance(i.get('foot'), dict):
                inf.foot = {k: str(v)[:80] for k, v in i['foot'].items() if k in SLATES}
            await self.refresh_strip()
            if self.slate:
                await self.refresh_slate(force=True)
        if 'slate' in body:
            s = body['slate']
            if s is not None and s not in SLATES:
                raise ValueError(f'slate must be null or one of {list(SLATES)}')
            if s is None:
                self.slate, self.slate_ends = None, None
            else:
                changed = s != self.slate
                self.slate = s
                if body.get('endsAt'):
                    self.slate_ends = float(body['endsAt']) / 1000.0
                elif 'minutes' in body or changed:
                    mins = float(body.get('minutes') or (15 if s == 'Break' else 5))
                    self.slate_ends = time.time() + mins * 60
            self.audio.set_slate(self.slate is not None)   # band <-> slate music crossfade
            await self.refresh_slate(force=True)
        if 'vertical' in body:
            v = body['vertical'] or {}
            if 'mode' in v:
                if v['mode'] not in ('auto', *LAYOUTS):
                    raise ValueError("vertical.mode must be 'auto', 'close' or 'band'")
                self.vertical['mode'] = v['mode']
            if 'pick' in v:
                if v['pick'] not in LAYOUTS:
                    raise ValueError("vertical.pick must be 'close' or 'band'")
                self.vertical['pick'] = v['pick']
            if 'x' in v:
                self.vertical['x'] = min(1.0, max(0.0, float(v['x'])))
            for k in ('closeCam', 'wideCam'):
                if k in v:
                    self.vertical[k] = int(v[k]) if v[k] is not None else None
            self.apply_vertical()
        if 'audio' in body and 'delayMs' in (body['audio'] or {}):
            self.audio_delay_ms = max(-1000, min(2000, int(body['audio']['delayMs'])))
        if 'start' in body:
            self.start_dests(body['start'] or [])
        if 'stop' in body:
            st = body['stop']
            self.stop_dests(True if st is True or st is None else list(st))

    # ---------- loops ----------
    async def bus_loop(self):
        while True:
            for m in iter(self.prog.pipe.get_bus().pop, None):
                err = self.prog.handle(m)
                if err:
                    self.error = err
            if self.audio.pipe is not None:
                for m in iter(self.audio.pipe.get_bus().pop, None):
                    self.audio.handle(m)
            for d in list(self.dests.values()):
                pipe = d.pipe
                if pipe is None:
                    continue
                for m in iter(pipe.get_bus().pop, None):
                    if m.type == Gst.MessageType.ERROR:
                        err, dbg = m.parse_error()
                        log.warning('%s: %s', d.name, err.message)
                        d.fail(err.message)
                        break
                    if m.type == Gst.MessageType.EOS:
                        d.fail('connection closed')
                        break
            await asyncio.sleep(0.05)

    async def tick_loop(self):
        n = 0
        while True:
            await asyncio.sleep(1)
            n += 1
            try:
                self.prog.tick()
                for d in list(self.dests.values()):
                    d.tick()
                    if d.pipe is None and d.state in ('waiting', 'reconnecting') and n % 2 == 0:
                        self.prog.request_keyframe(d.profile)
                await self.refresh_slate()
                self._cpu()
                if n % 5 == 0 and self.cfg.profile.encoder == 'nvenc':
                    await self._gpu()
            except Exception:  # noqa: BLE001
                log.exception('tick')

    @staticmethod
    def _cpu_ticks() -> int:
        with open('/proc/self/stat') as f:
            parts = f.read().rsplit(')', 1)[1].split()
        return int(parts[11]) + int(parts[12])

    def _cpu(self):
        now, ticks = time.time(), self._cpu_ticks()
        t0, k0 = self._cpu_prev
        self.cpu = (ticks - k0) / os.sysconf('SC_CLK_TCK') / max(1e-3, now - t0) * 100
        self._cpu_prev = (now, ticks)

    async def _gpu(self):
        if not shutil.which('nvidia-smi'):
            return
        try:
            proc = await asyncio.create_subprocess_exec('nvidia-smi', '--query-gpu=utilization.encoder', '--format=csv,noheader,nounits',
                                                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out = (await asyncio.wait_for(proc.communicate(), 5))[0].decode().strip().splitlines()
            self.encoder_load = float(out[0]) if out else None
        except Exception:  # noqa: BLE001
            self.encoder_load = None

    # ---------- state ----------
    def state(self) -> dict:
        p = self.cfg.profile
        remaining = max(0, round(self.slate_ends - time.time())) if (self.slate and self.slate_ends and graphics.MODES[self.slate]['time']) else None
        enc = {k: {'active': v['active'], 'encoder': self.prog.encoder_name.get(k), 'fps': round(v['fps'], 1),
                   'kbps': round(v['kbps']), 'targetKbps': p.kbps[k]} for k, v in self.prog.enc_stats.items()}
        dropped = sum(self.prog.qos_dropped.values()) + sum(d.dropped for d in self.dests.values())
        return {
            'profile': p.name,
            'size': {'program': [p.w, p.h, p.fps], 'vertical': [p.vw, p.vh, p.vfps]},
            'program': {'cam': self.program_cam, 'slate': self.slate,
                        'slateEndsAt': int(self.slate_ends * 1000) if self.slate_ends else None, 'slateRemainingS': remaining},
            'vertical': {**self.vertical, 'layout': self.layout, 'closeCamEff': self.close_cam(), 'wideCamEff': self.wide_cam()},
            'info': {'showName': self.info.show_name, 'channel': self.info.channel, 'song': self.info.song,
                     'nowPlaying': self.info.now_playing, 'colors': list(self.info.colors)},
            'audio': {**self.audio.info(), 'delayMs': self.audio_delay_ms},
            'cameras': self.cams.info(),
            'encoders': enc,
            'outputs': [d.info() for d in self.dests.values()],
            'stats': {'fps': round(self.prog.fps['program'], 1), 'verticalFps': round(self.prog.fps['vertical'], 1),
                      'dropped': dropped, 'cpuPct': round(self.cpu), 'ncpu': os.cpu_count(),
                      'encoderLoadPct': self.encoder_load, 'uptimeS': round(time.time() - self.started)},
            'error': self.error,
        }

    def cam_jpeg(self, cam_id: int, width, quality) -> bytes | None:
        from livekit import rtc
        cam = self.cams.cams.get(cam_id)
        if not cam or cam.last_frame is None:
            return None
        f = cam.last_frame.convert(rtc.VideoBufferType.RGBA)
        img = Image.frombytes('RGBA', (f.width, f.height), bytes(f.data)).convert('RGB')
        return encode_jpeg(img, width, quality)


# ---------- HTTP ----------
def make_app(svc: Service) -> web.Application:
    app = web.Application()

    async def state(_req):
        return web.json_response(svc.state())

    async def cmd(req: web.Request):
        try:
            body = await req.json()
            if not isinstance(body, dict):
                raise ValueError('body must be a JSON object')
            await svc.command(body)
        except (ValueError, TypeError, KeyError) as e:
            return web.json_response({'ok': False, 'error': str(e)}, status=400)
        return web.json_response({'ok': True, 'state': svc.state()})

    async def snapshot(req: web.Request):
        q = dict(req.query)
        if req.method == 'POST' and req.can_read_body:
            try:
                q.update({k: v for k, v in (await req.json()).items() if v is not None})
            except Exception:  # noqa: BLE001
                pass
        which = q.get('which', 'program')
        width = int(q['width']) if q.get('width') else None
        quality = int(q.get('quality', 85))
        if which == 'cam':
            data = await render(svc.cam_jpeg, int(q.get('cam', 0)), width, quality)
        elif which in ('program', 'vertical'):
            data = await render(svc.prog.snapshot_jpeg, which, width, quality)
        else:
            return web.json_response({'error': "which must be 'program', 'vertical' or 'cam'"}, status=400)
        if data is None:
            return web.json_response({'error': 'no frame yet'}, status=503)
        return web.Response(body=data, content_type='image/jpeg', headers={'Cache-Control': 'no-store'})

    app.router.add_get('/state', state)
    app.router.add_post('/cmd', cmd)
    app.router.add_get('/snapshot', snapshot)
    app.router.add_post('/snapshot', snapshot)
    app.router.add_get('/health', lambda _r: web.json_response({'ok': True}))
    return app


async def main():
    faulthandler.register(signal.SIGUSR1)  # kill -USR1 <pid> dumps all Python stacks
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
    cfg = load()
    svc = Service(cfg)
    svc.prog.build()
    svc.audio.start()
    svc.apply_vertical()
    await svc.refresh_strip()
    tasks = [asyncio.ensure_future(t) for t in (svc.bus_loop(), svc.tick_loop(), svc.audio.supervise(), svc.cams.run())]
    runner = web.AppRunner(make_app(svc), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, cfg.host, cfg.port).start()
    log.info('video service on http://%s:%s (profile %s)', cfg.host, cfg.port, cfg.profile.name)
    try:
        await asyncio.gather(*tasks)
    finally:
        svc.stop_dests(True)
        svc.audio.stop()
        svc.prog.stop()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
