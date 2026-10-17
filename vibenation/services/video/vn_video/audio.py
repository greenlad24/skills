"""Program audio: the engine's mastered output from JACK -> AAC 128 kb/s, 44.1 kHz.

Runs as its own pipeline so a JACK/engine restart never touches the video. If JACK is
not reachable the service falls back to digital silence (the streams must keep audio
flowing, otherwise flvmux would hold the video) and retries JACK every few seconds.
The JACK client is 'vn_video'; it never auto-connects to physical ports: the service
connects effect_1042:outL/outR (the x42 limiter inside the engine's mod-host) with
jack_connect and re-connects if the engine restarts.
"""
from __future__ import annotations

import asyncio
import logging
import math
import shutil
import time

from .gst import CLOCK, Gst, abs_time

log = logging.getLogger('vn_video.audio')

ENCODE = ('audioconvert ! level name=level interval=1000000000 post-messages=true '
          '! audioresample ! audioconvert ! audio/x-raw,rate=44100,channels=2 '
          '! avenc_aac bitrate=128000 ! aacparse ! audio/mpeg,mpegversion=4,stream-format=raw '
          '! appsink name=aac emit-signals=true sync=false max-buffers=200 drop=true')

SOURCES = {
    'jack': 'jackaudiosrc name=jack client-name=vn_video connect=none buffer-time=100000 latency-time=10000 '
            '! audio/x-raw,channels=2 ! queue max-size-time=500000000 leaky=downstream ! ',
    'test': 'audiotestsrc is-live=true wave=sine freq=440 volume=0.1 ! audio/x-raw,rate=48000,channels=2 ! ',
    'silence': 'audiotestsrc is-live=true wave=silence ! audio/x-raw,rate=48000,channels=2 ! ',
}


class Audio:
    def __init__(self, want: str, jack_ports: tuple[str, ...], on_sample):
        self.want = want                       # configured source
        self.jack_ports = jack_ports
        self.on_sample = on_sample             # (sample, abs_ts) from a streaming thread
        self.pipe: Gst.Pipeline | None = None
        self.source = None                     # source actually running
        self.error: str | None = None
        self.connected = False                 # JACK ports linked to the master
        self.rms_db: float | None = None
        self.caps: Gst.Caps | None = None
        self.last_sample = 0.0
        self._next_jack_try = 0.0

    def start(self, source: str | None = None):
        self.stop()
        source = source or self.want
        if source == 'jack' and not shutil.which('jack_connect'):
            source, self.error = 'silence', 'jack_connect not installed'
        p = Gst.parse_launch(SOURCES[source] + ENCODE)
        p.use_clock(CLOCK)
        sink = p.get_by_name('aac')
        sink.connect('new-sample', self._new_sample)
        self.pipe, self.source = p, source
        self.connected = False
        self.last_sample = time.time()
        if p.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self._failed(f'{source} audio would not start')
        log.info('audio source: %s', self.source)

    def stop(self):
        if self.pipe is not None:
            p, self.pipe = self.pipe, None
            p.set_state(Gst.State.NULL)

    def _new_sample(self, sink):
        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.OK
        self.caps = sample.get_caps()
        ts = abs_time(sample, self.pipe) if self.pipe is not None else None
        if ts is not None:
            self.last_sample = time.time()
            self.on_sample(sample, ts)
        return Gst.FlowReturn.OK

    def _failed(self, msg: str):
        log.warning('audio: %s', msg)
        self.error = msg
        if self.source != 'silence':
            self._next_jack_try = time.time() + 10
            self.start('silence')

    def handle(self, msg: Gst.Message):
        if msg.type == Gst.MessageType.ERROR:
            err, _ = msg.parse_error()
            self._failed(err.message)
        elif msg.type == Gst.MessageType.ELEMENT and msg.get_structure() and msg.get_structure().get_name() == 'level':
            rms = msg.get_structure().get_value('rms')
            if rms:
                v = max(rms)
                self.rms_db = round(v, 1) if v > -200 and not math.isinf(v) else None

    async def supervise(self):
        """Keep the JACK ports wired to the master; go back to JACK when it returns."""
        while True:
            await asyncio.sleep(3)
            try:
                if self.pipe is not None:
                    for m in iter(lambda: self.pipe.get_bus().pop() if self.pipe else None, None):
                        self.handle(m)
                if self.want == 'jack' and self.source == 'silence' and time.time() >= self._next_jack_try:
                    self.start('jack')
                if self.source == 'jack':
                    await self._wire()
                if self.pipe is not None and self.last_sample and time.time() - self.last_sample > 5:
                    self._failed('no audio from the source for 5 s')
            except Exception as e:  # noqa: BLE001
                log.exception('audio supervisor: %s', e)

    async def _wire(self):
        mine = ('vn_video:in_jack_1', 'vn_video:in_jack_2')
        proc = await asyncio.create_subprocess_exec('jack_lsp', '-c', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out = (await proc.communicate())[0].decode(errors='replace')
        links: dict[str, set[str]] = {}
        cur = None
        for line in out.splitlines():
            if line.startswith((' ', '\t')):
                if cur:
                    links.setdefault(cur, set()).add(line.strip())
            else:
                cur = line.strip()
                links.setdefault(cur, set())
        ok = True
        for src, dst in zip(self.jack_ports, mine):
            if src not in links:
                ok = False      # engine not running (yet)
                continue
            if dst in links and src not in links[dst]:
                p = await asyncio.create_subprocess_exec('jack_connect', src, dst, stderr=asyncio.subprocess.DEVNULL)
                await p.wait()
                ok = ok and p.returncode == 0
        self.connected = ok
        if ok:
            self.error = None
        elif not self.error:
            self.error = f'waiting for {self.jack_ports[0]}'

    def info(self) -> dict:
        return {'source': self.source, 'want': self.want, 'connected': self.connected if self.source == 'jack' else None,
                'rmsDb': self.rms_db, 'error': self.error}
