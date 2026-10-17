"""RTMP(S) destinations. Each destination is its own small pipeline
(appsrc video + appsrc audio -> flvmux -> rtmp2sink) fed with the shared encoded streams,
so a platform that fails or stalls never touches the program or the other platforms.
A failed destination reconnects by itself with back-off."""
from __future__ import annotations

import asyncio
import threading
import time
from urllib.parse import urlsplit

from .gst import CLOCK, Gst, set_prop

MAX_QUEUE_NS = 4 * Gst.SECOND      # more than this waiting = the link is too slow: drop to next keyframe
RESUME_QUEUE_NS = 1 * Gst.SECOND


def mask(url: str, key: str) -> str:
    return url if not key else f"{url.rstrip('/')}/{key[:4]}…"


def split_target(url: str, key: str):
    u = urlsplit(url.strip())
    if u.scheme not in ('rtmp', 'rtmps') or not u.hostname:
        raise ValueError('url must be rtmp:// or rtmps://host/app')
    path = u.path.strip('/')
    if key:
        app, stream = path, key.strip()
        if u.query:
            app += '?' + u.query
    else:
        app, _, stream = path.rpartition('/')
        if u.query:
            stream += '?' + u.query
    if not stream:
        raise ValueError('missing stream key')
    port = u.port or (443 if u.scheme == 'rtmps' else 1935)
    return u.scheme, u.hostname, port, app, stream


class Destination:
    def __init__(self, name: str, url: str, key: str, profile: str, hub):
        self.name, self.url, self.key, self.profile = name, url, key, profile
        self.target = split_target(url, key)
        self.hub = hub                       # Outputs (gives caps + keyframe requests)
        self.pipe: Gst.Pipeline | None = None
        self.vsrc = self.asrc = self.sink = None
        self.state = 'waiting'               # waiting | connecting | live | error | reconnecting | stopped
        self.error: str | None = None
        self.t0: int | None = None           # absolute clock time mapped to 0 in this stream
        self.need_key = True
        self.congested = False
        self.reconnects = 0
        self.backoff = 2.0
        self.started_at = time.time()
        self.live_since: float | None = None
        self.frames = self.dropped = 0
        self.bytes = 0
        self._rate = (time.time(), 0, 0)     # (t, bytes, acked) at last stats tick
        self.kbps = self.acked_kbps = 0.0
        self._restart: asyncio.TimerHandle | None = None
        self.loop = asyncio.get_running_loop()
        self.lock = threading.Lock()

    # ---------- lifecycle ----------
    def _build(self, vcaps: Gst.Caps, acaps: Gst.Caps):
        scheme, host, port, app, stream = self.target
        p = Gst.parse_launch(
            'appsrc name=v format=time is-live=false do-timestamp=false block=false max-bytes=0 '
            '! queue max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! mux.video '
            'appsrc name=a format=time is-live=false do-timestamp=false block=false max-bytes=0 '
            '! queue max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! mux.audio '
            'flvmux name=mux streamable=true ! rtmp2sink name=sink sync=false async-connect=true')
        p.use_clock(CLOCK)
        self.vsrc, self.asrc, self.sink = p.get_by_name('v'), p.get_by_name('a'), p.get_by_name('sink')
        self.vsrc.set_property('caps', vcaps)
        self.asrc.set_property('caps', acaps)
        set_prop(self.sink, 'scheme', scheme)
        self.sink.set_property('host', host)
        self.sink.set_property('port', port)
        self.sink.set_property('application', app)
        self.sink.set_property('stream', stream)
        set_prop(self.sink, 'timeout', 10)
        self.pipe = p
        p.set_state(Gst.State.PLAYING)
        self.state = 'connecting'
        self.t0 = None
        self.need_key = True

    def _teardown(self):
        with self.lock:
            p, self.pipe = self.pipe, None
            self.vsrc = self.asrc = self.sink = None
        if p is not None:
            p.set_state(Gst.State.NULL)

    def stop(self):
        if self._restart:
            self._restart.cancel()
        self._teardown()
        self.state = 'stopped'

    def fail(self, msg: str):
        """Error from the RTMP pipeline: tear down and reconnect later."""
        if self.state == 'stopped':
            return
        self._teardown()
        self.state, self.error = 'error', msg
        self.live_since = None
        delay = self.backoff
        self.backoff = min(30.0, self.backoff * 2)
        self.reconnects += 1

        def again():
            self._restart = None
            if self.state != 'stopped':
                self.state = 'reconnecting'
        self._restart = self.loop.call_later(delay, again)

    # ---------- data (called from GStreamer streaming threads) ----------
    def push_video(self, sample: Gst.Sample, abs_ts: int, key: bool):
        with self.lock:
            self._push_video(sample, abs_ts, key)

    def _push_video(self, sample: Gst.Sample, abs_ts: int, key: bool):
        if self.state in ('stopped', 'error'):
            return
        if self.pipe is None:
            if not key or self.hub.acaps is None:
                return
            self._build(sample.get_caps(), self.hub.acaps)
        if self.need_key:
            if not key:
                return
            self.need_key = False
        if self.t0 is None:
            self.t0 = abs_ts
        level = self.vsrc.get_property('current-level-time') if self.vsrc.find_property('current-level-time') else 0
        if self.congested or level > MAX_QUEUE_NS:
            if not self.congested:
                self.congested = True
            if not key or level > RESUME_QUEUE_NS:
                self.dropped += 1
                return
            self.congested = False
        src = sample.get_buffer()
        buf = src.copy()
        buf.pts = buf.dts = max(0, abs_ts - self.t0)
        buf.duration = src.duration
        self.frames += 1
        self.bytes += buf.get_size()
        self.vsrc.emit('push-buffer', buf)

    def push_audio(self, sample: Gst.Sample, abs_ts: int):
        with self.lock:
            self._push_audio(sample, abs_ts)

    def _push_audio(self, sample: Gst.Sample, abs_ts: int):
        if self.pipe is None or self.t0 is None or self.need_key or self.congested:
            return
        ts = abs_ts - self.t0
        if ts < 0:
            return
        src = sample.get_buffer()
        buf = src.copy()
        buf.pts = buf.dts = ts
        buf.duration = src.duration
        self.bytes += buf.get_size()
        self.asrc.emit('push-buffer', buf)

    # ---------- housekeeping (event loop) ----------
    def tick(self):
        now = time.time()
        acked = 0
        sink = self.sink
        if sink is not None:
            try:
                st = sink.get_property('stats')
                ok, v = st.get_uint64('out-bytes-acked')
                acked = v if ok else 0
            except Exception:  # noqa: BLE001
                acked = 0
        t, b, a = self._rate
        dt = max(1e-3, now - t)
        self.kbps = (self.bytes - b) * 8 / 1000 / dt
        self.acked_kbps = max(0, acked - a) * 8 / 1000 / dt if acked >= a else 0.0
        self._rate = (now, self.bytes, acked)
        if self.state == 'connecting' and acked > 0:
            self.state, self.error, self.backoff = 'live', None, 2.0
            self.live_since = now

    def info(self) -> dict:
        return {
            'name': self.name, 'profile': self.profile, 'url': mask(self.url, self.key),
            'state': self.state, 'error': self.error,
            'kbps': round(self.kbps), 'ackedKbps': round(self.acked_kbps),
            'frames': self.frames, 'dropped': self.dropped, 'reconnects': self.reconnects,
            'congested': self.congested,
            'liveForS': round(time.time() - self.live_since) if self.live_since else 0,
        }
