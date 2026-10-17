"""Program audio: the engine's mastered output from JACK -> AAC 128 kb/s, 44.1 kHz.

Runs as its own pipeline so a JACK/engine restart never touches the video. If JACK is
not reachable the service falls back to digital silence (the streams must keep audio
flowing, otherwise flvmux would hold the video) and retries JACK every few seconds.
The JACK client is 'vn_video'; it never auto-connects to physical ports: the service
connects effect_1042:outL/outR (the x42 limiter inside the engine's mod-host) with
jack_connect and re-connects if the engine restarts.

Slate music: while a slate ("Starting soon", "Break", "Thanks for watching") is on air the
band is muted in the stream and copyright-free background music plays instead:

    band (jack|test|silence) ─ F32 48k ─ volume bandvol ─┐
                                                         ├─ audiomixer ─ level ─ AAC ─> outputs
    music appsrc (WAV playlist, looped) ─ volume musvol ─┘

Both volumes are driven by GstController curves in stream time, so the ~2 s crossfade is
sample-accurate (no zipper/clicks) whatever the Python event loop is doing. The music is
fed by a thread reading 16-bit 48 kHz stereo WAVs from VN_SLATE_MUSIC_DIR in name order,
gapless, looping forever; it runs (silently) all the time so a break never waits for it.
No music files -> slates are just silent (the band is still muted) and a warning is logged.
"""
from __future__ import annotations

import asyncio
import glob
import logging
import math
import os
import shutil
import threading
import time
import wave

import gi

gi.require_version('GstController', '1.0')
from gi.repository import GstController  # noqa: E402

from .gst import CLOCK, Gst, abs_time  # noqa: E402

log = logging.getLogger('vn_video.audio')

RAW = 'audio/x-raw,format=F32LE,rate=48000,channels=2,layout=interleaved'
MUSIC_CAPS = 'audio/x-raw,format=S16LE,rate=48000,channels=2,layout=interleaved'

ENCODE = (f'audiomixer name=mix ! {RAW} ! audioconvert ! level name=level interval=1000000000 post-messages=true '
          '! audioresample ! audioconvert ! audio/x-raw,rate=44100,channels=2 '
          '! avenc_aac bitrate=128000 ! aacparse ! audio/mpeg,mpegversion=4,stream-format=raw '
          '! appsink name=aac emit-signals=true sync=false async=false max-buffers=200 drop=true ')

SOURCES = {
    'jack': 'jackaudiosrc name=jack client-name=vn_video connect=none buffer-time=100000 latency-time=10000 '
            '! audio/x-raw,channels=2 ! queue max-size-time=500000000 leaky=downstream ! ',
    'test': 'audiotestsrc is-live=true wave=sine freq=440 volume=0.1 ! audio/x-raw,rate=48000,channels=2 ! ',
    'silence': 'audiotestsrc is-live=true wave=silence ! audio/x-raw,rate=48000,channels=2 ! ',
}
BAND = f'audioconvert ! audioresample ! {RAW} ! volume name=bandvol ! mix. '
MUSIC = (f'appsrc name=music format=time is-live=false block=true max-bytes=384000 caps="{MUSIC_CAPS}" '
         f'! audioconvert ! {RAW} ! volume name=musvol ! mix. ')

FADE_S = float(os.environ.get('VN_SLATE_FADE_S', '2.0'))
LEAD_NS = int(0.3 * Gst.SECOND)        # ramps start this far ahead of "now" (both branches are < this ahead)
CHUNK = 2400                           # frames per music buffer (50 ms)


def _db(v: float) -> float:
    return 10 ** (v / 20)


class Fader:
    """A volume element's gain as a GstController curve (absolute values, stream time)."""

    def __init__(self, el: Gst.Element, value: float):
        self.cs = GstController.InterpolationControlSource()
        self.cs.set_property('mode', GstController.InterpolationMode.LINEAR)
        el.add_control_binding(GstController.DirectControlBinding.new_absolute(el, 'volume', self.cs))
        self.points: dict[int, float] = {}      # mirror of the curve (cs.get_value is not usable from Python)
        self.target = value
        self._set(0, value)

    def _set(self, t: int, v: float):
        self.cs.set(t, v)
        self.points[t] = v

    def value_at(self, t: int) -> float:
        """The curve at t: linear between our points, held after the last one."""
        before = [p for p in self.points if p <= t]
        after = [p for p in self.points if p > t]
        if not before:
            return self.points[min(after)] if after else self.target
        a = max(before)
        if not after:
            return self.points[a]
        b = min(after)
        return self.points[a] + (self.points[b] - self.points[a]) * (t - a) / (b - a)

    def ramp(self, t0: int, target: float, dur_s: float):
        """From whatever the curve is at t0, an S-curve to target over dur_s (replaces later points)."""
        start = self.value_at(t0)
        keep = max([p for p in self.points if p < t0 - 30 * Gst.SECOND], default=None)   # last old point stays
        for t in [p for p in self.points if p >= t0 or (p < t0 - 30 * Gst.SECOND and p != keep)]:
            self.cs.unset(t)
            del self.points[t]
        self.target = target
        n = 24
        for i in range(n + 1):
            x = i / n
            s = 0.5 - 0.5 * math.cos(math.pi * x)          # smooth start and end: no click
            self._set(t0 + int(dur_s * x * Gst.SECOND), start + (target - start) * s)


class SlateMusic:
    """Feeds the playlist into the 'music' appsrc from a thread, gapless and looping."""

    def __init__(self, folder: str):
        self.folder = folder
        self.tracks: list[str] = []
        self.skipped: list[str] = []
        self.now_playing: str | None = None
        self.resyncs = 0
        self.loops = 0
        self.error: str | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.scan()

    def scan(self):
        ok, bad = [], []
        for f in sorted(glob.glob(os.path.join(self.folder, '*.wav'))):
            try:
                with wave.open(f, 'rb') as w:
                    if (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (48000, 2, 2) and w.getnframes() > 48000:
                        ok.append(f)
                        continue
            except Exception:  # noqa: BLE001
                pass
            bad.append(os.path.basename(f))
        self.tracks, self.skipped = ok, bad
        if bad:
            log.warning('slate music: skipped %s (need 16-bit 48 kHz stereo WAV)', ', '.join(bad))
        if ok:
            log.info('slate music: %d tracks in %s', len(ok), self.folder)
            self.error = None
        else:
            self.error = f'no slate music in {self.folder}: slates will be silent'
            log.warning('slate music: %s', self.error)

    def start(self, src: Gst.Element, pipe: Gst.Pipeline):
        self.stop()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(src, pipe, self._stop), name='slate-music', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread = None

    def _run(self, src, pipe, stop: threading.Event):
        dur = int(CHUNK * Gst.SECOND / 48000)
        pts = None
        while not stop.is_set():
            for path in list(self.tracks):
                try:
                    w = wave.open(path, 'rb')
                except Exception as e:  # noqa: BLE001
                    log.warning('slate music: %s: %s', path, e)
                    time.sleep(1)
                    continue
                self.now_playing = os.path.splitext(os.path.basename(path))[0]
                with w:
                    while not stop.is_set():
                        data = w.readframes(CHUNK)
                        if not data:
                            break
                        now = CLOCK.get_time() - pipe.get_base_time()
                        buf = Gst.Buffer.new_wrapped(data)
                        if pts is None or pts < now + 20 * Gst.MSECOND:
                            # start, or fell behind the mixer (stall): jump ahead so nothing arrives late
                            if pts is not None:
                                self.resyncs += 1
                            pts = now + 200 * Gst.MSECOND
                            buf.set_flags(Gst.BufferFlags.DISCONT)
                        n = len(data) // 4
                        d = dur if n == CHUNK else int(n * Gst.SECOND / 48000)
                        buf.pts, buf.duration = pts, d
                        pts += d
                        if src.emit('push-buffer', buf) != Gst.FlowReturn.OK:
                            return            # pipeline stopped (flushing)
            self.loops += 1
            if not self.tracks:
                return

    def info(self) -> dict:
        return {'dir': self.folder, 'tracks': [os.path.splitext(os.path.basename(t))[0] for t in self.tracks],
                'skipped': self.skipped, 'track': self.now_playing if self.tracks else None,
                'loops': self.loops, 'resyncs': self.resyncs, 'error': self.error}


class Audio:
    def __init__(self, want: str, jack_ports: tuple[str, ...], on_sample, music_dir: str | None = None, music_db: float = 0.0):
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
        self.music = SlateMusic(music_dir) if music_dir else None
        self.music_gain = _db(music_db)
        self.music_db = music_db
        self.slate_on = False                  # band muted, music up
        self.band_f: Fader | None = None
        self.music_f: Fader | None = None

    def start(self, source: str | None = None):
        self.stop()
        source = source or self.want
        if source == 'jack' and not shutil.which('jack_connect'):
            source, self.error = 'silence', 'jack_connect not installed'
        music = self.music is not None and bool(self.music.tracks)
        p = Gst.parse_launch(SOURCES[source] + BAND + (MUSIC if music else '') + ENCODE)
        p.use_clock(CLOCK)
        sink = p.get_by_name('aac')
        sink.connect('new-sample', self._new_sample)
        self.pipe, self.source = p, source
        self.band_f = Fader(p.get_by_name('bandvol'), 0.0 if self.slate_on else 1.0)
        self.music_f = Fader(p.get_by_name('musvol'), self.music_gain if self.slate_on else 0.0) if music else None
        self.connected = False
        self.last_sample = time.time()
        if p.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self._failed(f'{source} audio would not start')
            return
        if music:
            self.music.start(p.get_by_name('music'), p)
        log.info('audio source: %s (slate music: %s)', self.source, 'yes' if music else 'no')

    def stop(self):
        if self.music is not None:
            self.music.stop()
        if self.pipe is not None:
            p, self.pipe = self.pipe, None
            p.set_state(Gst.State.NULL)

    def set_slate(self, on: bool):
        """Crossfade band <-> slate music (event loop)."""
        on = bool(on)
        if on == self.slate_on:
            return
        self.slate_on = on
        if self.pipe is None or self.band_f is None:
            return
        t0 = CLOCK.get_time() - self.pipe.get_base_time() + LEAD_NS
        self.band_f.ramp(t0, 0.0 if on else 1.0, FADE_S)
        if self.music_f is not None:
            self.music_f.ramp(t0, self.music_gain if on else 0.0, FADE_S)
        log.info('slate %s: %s', 'on' if on else 'off', 'band -> music' if on else 'music -> band')

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
        m = self.music.info() if self.music is not None else {'error': 'slate music disabled'}
        return {'source': self.source, 'want': self.want, 'connected': self.connected if self.source == 'jack' else None,
                'rmsDb': self.rms_db, 'error': self.error,
                'slateMusic': {**m, 'on': self.slate_on, 'gainDb': self.music_db, 'fadeS': FADE_S,
                               'loaded': self.music_f is not None}}
