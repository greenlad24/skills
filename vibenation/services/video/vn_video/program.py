"""The program: camera frames + slates -> 16:9 program and 9:16 vertical, encoded once per
output profile and fanned out to the RTMP destinations.

    srcA (on-air camera) ─┬─> prog compositor ─> tee ─┬─ valve ─ enc 16x9-9M ─> appsink ─┐
    slate16 (RGBA still) ─┘   (black live base pad)    ├─ valve ─ enc 16x9-6M ─> appsink ─┤ fan-out to
                                                        └─ 2 fps RGB ─> snapshot          │ Destination
    srcC (close-up cam) ─ crop 9:16 ────────┐                                             │ pipelines
                      └ crop band close-up ─┤                                             │ (+ AAC from
    srcW (wide cam) ─ scale 16:9 ───────────┼─> vert compositor ─> tee ─ valve ─ enc 9x16 ┘  audio.py)
    strip (title, RGBA) ────────────────────┤                          └ 2 fps RGB ─> snapshot
    slate9 (RGBA still) ────────────────────┘

The compositors are driven by a live black test source, so the output frame rate is
constant whatever the phones do; a camera that stalls holds its last frame. Cuts are
instant: the router simply starts feeding the other camera into srcA.
"""
from __future__ import annotations

import asyncio
import io
import logging
import time

from PIL import Image

from . import graphics
from .config import OUTPUT_PROFILES, Settings, even
from .gst import CLOCK, Gst, GstVideo, abs_time, has, set_prop

log = logging.getLogger('vn_video.program')

APPSRC = 'is-live=true do-timestamp=true format=time min-latency=0 max-bytes=0 max-buffers=3 leaky-type=downstream'


def _caps(fmt: str, w: int, h: int, fps: int | None = None) -> str:
    s = f'video/x-raw,format={fmt},width={w},height={h},pixel-aspect-ratio=1/1'
    return s + (f',framerate={fps}/1' if fps is not None else '')


class Program:
    def __init__(self, cfg: Settings, on_encoded):
        self.cfg = cfg
        self.p = cfg.profile
        self.on_encoded = on_encoded          # (profile, sample, abs_ts, key) from streaming threads
        self.pipe: Gst.Pipeline | None = None
        self.encoder_name: dict[str, str] = {}
        self.enc_caps: dict[str, Gst.Caps] = {}
        self.enc_stats = {k: {'active': False, 'frames': 0, 'bytes': 0, 'fps': 0.0, 'kbps': 0.0, 'keyframes': 0} for k in OUTPUT_PROFILES}
        self._enc_prev = {k: (time.time(), 0, 0) for k in OUTPUT_PROFILES}
        self.snap: dict[str, Gst.Sample | None] = {'program': None, 'vertical': None}
        self.counts = {'program': 0, 'vertical': 0}
        self._count_prev = (time.time(), 0, 0)
        self.fps = {'program': 0.0, 'vertical': 0.0}
        self.qos_dropped: dict[str, int] = {}
        self._capcache: dict[tuple[int, int], tuple[Gst.Caps, bool]] = {}

    # ---------- build ----------
    def build(self):
        p, n = self.p, f'n-threads={self.p.threads}'
        lat = int(1.5e9 / p.fps)
        vlat = int(1.5e9 / p.vfps)
        q1 = 'queue max-size-buffers=2 max-size-bytes=0 max-size-time=0 leaky=downstream'
        cam_norm = f'videoconvert {n} ! videoscale add-borders=true {n} ! {_caps("I420", p.w, p.h)}'
        still = 'is-live=true do-timestamp=true format=time min-latency=0'
        desc = f"""
            videotestsrc is-live=true pattern=black ! {_caps('I420', p.w, p.h, p.fps)} ! prog.sink_0
            compositor name=prog background=black latency={lat} ignore-inactive-pads=true
              ! {_caps('I420', p.w, p.h, p.fps)} ! identity name=progcount ! tee name=progt allow-not-linked=true
            appsrc name=srcA {APPSRC} ! {q1} ! {cam_norm} ! {q1} ! prog.sink_1
            appsrc name=slate16 {still} caps="{_caps('RGBA', p.w, p.h, 0)}" ! videoconvert {n} ! video/x-raw,format=I420 ! {q1} ! prog.sink_2
            progt. ! queue max-size-buffers=1 leaky=downstream ! videorate drop-only=true max-rate=2 ! videoconvert ! video/x-raw,format=RGB
              ! appsink name=snap_program sync=false emit-signals=true max-buffers=1 drop=true
            progt. ! queue name=encq_16x9-9M max-size-buffers=4 max-size-bytes=0 max-size-time=0 leaky=downstream ! valve name=valve_16x9-9M drop=true
            progt. ! queue name=encq_16x9-6M max-size-buffers=4 max-size-bytes=0 max-size-time=0 leaky=downstream ! valve name=valve_16x9-6M drop=true

            videotestsrc is-live=true pattern=black ! {_caps('I420', p.vw, p.vh, p.vfps)} ! vert.sink_0
            compositor name=vert background=black latency={vlat} ignore-inactive-pads=true
              ! {_caps('I420', p.vw, p.vh, p.vfps)} ! identity name=vertcount ! tee name=vertt allow-not-linked=true
            appsrc name=srcC {APPSRC} ! {q1} ! {cam_norm} ! tee name=camC
            camC. ! {q1} ! valve name=vv_close drop=false ! videocrop name=crop_close ! videoscale {n} ! {_caps('I420', p.vw, p.vh)} ! {q1} ! vert.sink_1
            camC. ! {q1} ! valve name=vv_bclose drop=true ! videocrop name=crop_bclose ! videoscale {n} ! {_caps('I420', p.vw, p.bclose_h)} ! {q1} ! vert.sink_2
            appsrc name=srcW {APPSRC} ! {q1} ! valve name=vv_wide drop=true ! videoconvert {n} ! videoscale add-borders=true {n} ! {_caps('I420', p.vw, p.wide_h)} ! {q1} ! vert.sink_3
            appsrc name=strip {still} caps="{_caps('RGBA', p.vw, p.strip_h, 0)}" ! videoconvert ! video/x-raw,format=I420 ! {q1} ! vert.sink_4
            appsrc name=slate9 {still} caps="{_caps('RGBA', p.vw, p.vh, 0)}" ! videoconvert {n} ! video/x-raw,format=I420 ! {q1} ! vert.sink_5
            vertt. ! queue max-size-buffers=1 leaky=downstream ! videorate drop-only=true max-rate=2 ! videoconvert ! video/x-raw,format=RGB
              ! appsink name=snap_vertical sync=false emit-signals=true max-buffers=1 drop=true
            vertt. ! queue name=encq_9x16 max-size-buffers=4 max-size-bytes=0 max-size-time=0 leaky=downstream ! valve name=valve_9x16 drop=true
        """
        pipe = Gst.parse_launch(desc)
        pipe.use_clock(CLOCK)
        self.pipe = pipe
        g = pipe.get_by_name

        # Compositor pad layout.
        prog, vert = g('prog'), g('vert')
        self._pad(prog, 0, z=0)
        self._pad(prog, 1, z=1)
        self._pad(prog, 2, z=9, alpha=0)                       # slate
        self._pad(vert, 0, z=0)
        self._pad(vert, 1, z=1)                                # close-up (full frame)
        self._pad(vert, 2, z=2, y=p.strip_h + p.wide_h, alpha=0)  # band view: close-up
        self._pad(vert, 3, z=2, y=p.strip_h, alpha=0)          # band view: wide
        self._pad(vert, 4, z=2, y=0, alpha=0)                  # band view: title strip
        self._pad(vert, 5, z=9, alpha=0)                       # slate

        for which in ('program', 'vertical'):
            g(f'snap_{which}').connect('new-sample', self._snap, which)
        g('progcount').get_static_pad('src').add_probe(Gst.PadProbeType.BUFFER, self._count, 'program')
        g('vertcount').get_static_pad('src').add_probe(Gst.PadProbeType.BUFFER, self._count, 'vertical')

        for prof in OUTPUT_PROFILES:
            self._encoder_branch(prof)

        self.srcA, self.srcC, self.srcW = g('srcA'), g('srcC'), g('srcW')
        self.slate16, self.slate9, self.strip = g('slate16'), g('slate9'), g('strip')
        self.crop_close, self.crop_bclose = g('crop_close'), g('crop_bclose')
        if pipe.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError('program pipeline failed to start')

    def _pad(self, comp, i, z, x=0, y=0, alpha=1.0):
        pad = comp.get_static_pad(f'sink_{i}')
        pad.set_property('zorder', z)
        pad.set_property('xpos', x)
        pad.set_property('ypos', y)
        pad.set_property('alpha', alpha)

    def pad_alpha(self, comp: str, i: int, alpha: float):
        self.pipe.get_by_name(comp).get_static_pad(f'sink_{i}').set_property('alpha', alpha)

    def _make_encoder(self, prof: str) -> Gst.Element:
        p = self.p
        fps = p.vfps if prof == '9x16' else p.fps
        kbps = p.kbps[prof]
        gop = int(round(fps * self.cfg.gop_s))
        if p.encoder == 'nvenc':
            for fac in ('nvh264enc', 'nvcudah264enc', 'nvautogpuh264enc'):
                if not has(fac):
                    continue
                e = Gst.ElementFactory.make(fac, f'enc_{prof}')
                if fac == 'nvh264enc':
                    set_prop(e, 'preset', 'low-latency-hq')
                else:
                    set_prop(e, 'preset', 'p4')
                    set_prop(e, 'tune', 'low-latency')
                set_prop(e, 'rc-mode', 'cbr')
                set_prop(e, 'bitrate', kbps)
                set_prop(e, 'max-bitrate', kbps)
                set_prop(e, 'vbv-buffer-size', kbps)       # 1 s of buffer
                set_prop(e, 'gop-size', gop)
                set_prop(e, 'bframes', 0)
                set_prop(e, 'zerolatency', True)
                set_prop(e, 'rc-lookahead', 0)
                set_prop(e, 'aud', False)
                self.encoder_name[prof] = fac
                return e
            log.warning('NVENC not available: falling back to x264 for %s', prof)
        e = Gst.ElementFactory.make('x264enc', f'enc_{prof}')
        set_prop(e, 'speed-preset', 'ultrafast' if p.name == 'cpu-test' else 'veryfast')
        set_prop(e, 'tune', 'zerolatency')
        set_prop(e, 'bitrate', kbps)
        set_prop(e, 'vbv-buf-capacity', 1000)
        set_prop(e, 'key-int-max', gop)
        set_prop(e, 'bframes', 0)
        set_prop(e, 'option-string', 'scenecut=0:nal-hrd=cbr' if p.name != 'cpu-test' else 'scenecut=0')
        if p.name == 'cpu-test':
            set_prop(e, 'threads', 1)
        self.encoder_name[prof] = 'x264enc'
        return e

    def _encoder_branch(self, prof: str):
        pipe = self.pipe
        valve = pipe.get_by_name(f'valve_{prof}')
        enc = self._make_encoder(prof)
        parse = Gst.ElementFactory.make('h264parse')
        parse.set_property('config-interval', -1)
        caps = Gst.ElementFactory.make('capsfilter')
        caps.set_property('caps', Gst.Caps.from_string('video/x-h264,stream-format=avc,alignment=au'))
        sink = Gst.ElementFactory.make('appsink', f'out_{prof}')
        for k, v in (('emit-signals', True), ('sync', False), ('max-buffers', 120), ('drop', True)):
            sink.set_property(k, v)
        sink.connect('new-sample', self._encoded, prof)
        for e in (enc, parse, caps, sink):
            pipe.add(e)
        valve.link(enc)
        enc.link(parse)
        parse.link(caps)
        caps.link(sink)

    # ---------- streaming-thread callbacks ----------
    def _count(self, pad, info, which):
        self.counts[which] += 1
        return Gst.PadProbeReturn.OK

    def _snap(self, sink, which):
        self.snap[which] = sink.emit('pull-sample')
        return Gst.FlowReturn.OK

    def _encoded(self, sink, prof):
        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.OK
        buf = sample.get_buffer()
        key = not buf.has_flags(Gst.BufferFlags.DELTA_UNIT)
        st = self.enc_stats[prof]
        st['frames'] += 1
        st['bytes'] += buf.get_size()
        if key:
            st['keyframes'] += 1
        self.enc_caps[prof] = sample.get_caps()
        ts = abs_time(sample, self.pipe)
        if ts is not None:
            self.on_encoded(prof, sample, ts, key)
        return Gst.FlowReturn.OK

    # ---------- control (event loop) ----------
    def set_encoder_active(self, prof: str, on: bool):
        st = self.enc_stats[prof]
        if st['active'] == on:
            return
        st['active'] = on
        self.pipe.get_by_name(f'valve_{prof}').set_property('drop', not on)
        log.info('encoder %s %s', prof, 'on' if on else 'off')

    def request_keyframe(self, prof: str):
        sink = self.pipe.get_by_name(f'out_{prof}')
        if sink is not None:
            sink.send_event(GstVideo.video_event_new_upstream_force_key_unit(Gst.CLOCK_TIME_NONE, True, 0))

    def wrap_frame(self, frame) -> Gst.Sample | None:
        """LiveKit I420 frame -> Gst.Sample (repacked if strides differ from GStreamer's)."""
        w, h = frame.width, frame.height
        if w < 2 or h < 2:
            return None
        c = self._capcache.get((w, h))
        if c is None:
            caps = Gst.Caps.from_string(f'video/x-raw,format=I420,width={w},height={h},framerate=0/1,pixel-aspect-ratio=1/1')
            vi = GstVideo.VideoInfo.new_from_caps(caps)
            cw, ch = (w + 1) // 2, (h + 1) // 2
            tight = (list(vi.stride[:3]) == [w, cw, cw] and list(vi.offset[:3]) == [0, w * h, w * h + cw * ch])
            c = (caps, tight, vi)
            self._capcache[(w, h)] = c
        caps, tight, vi = c
        if tight:
            data = bytes(frame.data)
        else:
            data = bytearray(vi.size)
            heights = (h, (h + 1) // 2, (h + 1) // 2)
            for i in range(3):
                plane = frame.get_plane(i)
                src_stride = len(plane) // heights[i]
                row = min(src_stride, vi.stride[i])
                for r in range(heights[i]):
                    o = vi.offset[i] + r * vi.stride[i]
                    data[o:o + row] = plane[r * src_stride:r * src_stride + row]
            data = bytes(data)
        return Gst.Sample.new(Gst.Buffer.new_wrapped(data), caps, None, None)

    def push(self, src: Gst.Element, sample: Gst.Sample):
        src.emit('push-sample', sample)

    def push_still(self, src: Gst.Element, rgba: bytes):
        src.emit('push-buffer', Gst.Buffer.new_wrapped(rgba))

    def set_crop(self, x: float):
        """Close-up crops: a 9:16 window (and the band-view close-up window) at x in 0..1."""
        p = self.p
        x = min(1.0, max(0.0, x))
        for el, out_w, out_h in ((self.crop_close, p.vw, p.vh), (self.crop_bclose, p.vw, p.bclose_h)):
            cw = even(p.h * out_w / out_h)
            if cw <= p.w:
                left = even(x * (p.w - cw))
                vals = dict(left=left, right=p.w - cw - left, top=0, bottom=0)
            else:  # window wider than the frame: crop top/bottom instead (keep heads: bias up)
                chh = even(p.w * out_h / out_w)
                top = even(0.3 * (p.h - chh))
                vals = dict(left=0, right=0, top=top, bottom=p.h - chh - top)
            for k, v in vals.items():
                if el.get_property(k) != v:
                    el.set_property(k, v)

    def handle(self, msg: Gst.Message) -> str | None:
        t = msg.type
        if t == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            log.error('program pipeline: %s (%s)', err.message, dbg)
            return err.message
        if t == Gst.MessageType.QOS:
            _, _, dropped = msg.parse_qos_stats()
            self.qos_dropped[msg.src.get_name()] = dropped
        elif t == Gst.MessageType.WARNING:
            w, _ = msg.parse_warning()
            log.warning('program pipeline: %s', w.message)
        return None

    def tick(self):
        now = time.time()
        t, a, b = self._count_prev
        dt = max(1e-3, now - t)
        self.fps = {'program': (self.counts['program'] - a) / dt, 'vertical': (self.counts['vertical'] - b) / dt}
        self._count_prev = (now, self.counts['program'], self.counts['vertical'])
        for k, st in self.enc_stats.items():
            t0, f0, b0 = self._enc_prev[k]
            d = max(1e-3, now - t0)
            st['fps'] = (st['frames'] - f0) / d
            st['kbps'] = (st['bytes'] - b0) * 8 / 1000 / d
            self._enc_prev[k] = (now, st['frames'], st['bytes'])

    def snapshot_jpeg(self, which: str, width: int | None = None, quality: int = 85) -> bytes | None:
        sample = self.snap.get(which)
        if sample is None:
            return None
        caps = sample.get_caps()
        vi = GstVideo.VideoInfo.new_from_caps(caps)
        buf = sample.get_buffer()
        ok, mi = buf.map(Gst.MapFlags.READ)
        if not ok:
            return None
        try:
            img = Image.frombuffer('RGB', (vi.width, vi.height), bytes(mi.data), 'raw', 'RGB', vi.stride[0], 1)
        finally:
            buf.unmap(mi)
        return encode_jpeg(img, width, quality)

    def stop(self):
        if self.pipe is not None:
            self.pipe.set_state(Gst.State.NULL)


def encode_jpeg(img: Image.Image, width: int | None, quality: int) -> bytes:
    if width and width < img.width:
        img = img.resize((width, round(img.height * width / img.width)), Image.BILINEAR)
    out = io.BytesIO()
    img.save(out, 'JPEG', quality=quality)
    return out.getvalue()


async def render(fn, *args):
    return await asyncio.get_running_loop().run_in_executor(None, fn, *args)


__all__ = ['Program', 'graphics', 'render', 'encode_jpeg']
