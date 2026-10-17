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
from .analyzer import Analyzer, wav_bytes
from .arrangement import Arrangement
from .graph import COMP, LIMITER, MCOMP, MTAPE, MixGraph, port
from .modhost import ModHost
from .player import StemPlayer
from .venue import VenueReceiver

log = logging.getLogger('vn_audio')
STEMS = os.environ.get('VN_STEMS', '/home/vibe/vibenation-media/stems-2026-04-04')
DATA = os.environ.get('VN_DATA', os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data'))
LINKED = {6: 7, 7: 6}  # piano L/R share one trim so the stereo image holds
HOST, PORT = '127.0.0.1', int(os.environ.get('VN_AUDIO_PORT', '8091'))


class Engine:
    def __init__(self) -> None:
        t0 = time.time()
        self.player = StemPlayer(STEMS)
        log.info('player ready %.1f s', time.time() - t0)
        self.analyzer = Analyzer()
        self.venue = VenueReceiver(port=int(os.environ.get('VN_VENUE_PORT', '9000')))
        self.source = 'recording'  # or 'venue'
        self.mh = ModHost.launch()
        log.info('plugin host up %.1f s', time.time() - t0)
        self.gr = [0.0] * 16
        self.bus_gr = 0.0
        self.ride = [0.0] * 16  # current rider gain (dB) per channel
        self.howl_track: dict = {}
        self.clip_count = [0] * 16
        self.last_clip_fix = [0.0] * 16
        self.last_heard = [0.0] * 16
        self.dead_alerted = [False] * 16
        self.notches: dict = {}
        self.lar_hist: deque = deque(maxlen=150)  # 15 s of vocal-over-band while singing
        self.last_lar = 0.0
        self.ride_lvl: list[deque] = [deque(maxlen=4) for _ in range(16)]  # 400 ms of channel power
        self.ride_ref: list[deque] = [deque(maxlen=600) for _ in range(16)]  # 60 s of active levels
        self.st_hist: deque = deque(maxlen=300)  # 5 min of *music* short-term loudness for the leveller brake
        self.limiter_gr = 0.0
        self.arr = Arrangement()  # lead/backing vocals, solos, auto-mute of idle channels
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
        threading.Thread(target=self._auto_source, name='auto-source', daemon=True).start()
        self.mh.connect_ports(port(MTAPE, 'out_l'), f'{a}:pre_l')
        self.mh.connect_ports(port(MTAPE, 'out_r'), f'{a}:pre_r')
        self.leveller_on = True
        self.auto_venue = True
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
        self.limiter_gr = round(max(0.0, m['prePeak'] - m['peak']), 1)
        self._level(m)
        self._calibrate(f['raw'])
        self._ride(f)
        self._follow_arrangement(f)
        self._keep_vocals_on_top(f)
        self._watch_howl(f.get('howl', []))
        self._watch_clip_and_dead(f)
        frame = {'type': 'meters', **f, 'gr': self.gr, 'ride': self.ride, 'master': {**m, 'limiterGr': self.limiter_gr, 'busGr': self.bus_gr, 'drive': round(self.graph.master_gain, 1), 'bandOffset': round(self.graph.band_offset, 1)},
                 'singing': [self.playing(n, f) for n in range(1, 17)], 'arrangement': self.arr.summary()}
        self.broadcast(frame)

    def _level(self, m: dict) -> None:
        """Master loudness leveller (after master_me): rides short-term loudness toward -16 LUFS,
        up at most 1 dB/s and down 3 dB/s, within -10..+20 dB of drive. A brake freezes it when
        the music drops more than 10 dB under its 5-minute median (song ends, talk, breaks), and
        it never lifts anything quieter than -30 LUFS."""
        now = time.time()
        if not self.leveller_on or now - self.last_level < 1.0 or not self.running():
            return
        self.last_level = now
        s = m['lufsS'] - self.graph.master_gain  # loudness before the leveller's own drive
        median = sorted(self.st_hist)[len(self.st_hist) // 2] if len(self.st_hist) >= 5 else None
        if median is not None and s < median - 10:
            return  # brake: song end, talk or break — hold the drive, don't learn from it
        if s > -45:
            self.st_hist.append(s)
        if median is None or m['lufsS'] < -30:
            return
        err = P.TARGET_LUFS - m['lufsS']
        if abs(err) < 0.5:
            return
        if err > 0 and self.limiter_gr > 3:  # louder would only mean more limiting: fix it upstream
            return
        step = max(-3.0, min(1.0, err * 0.3))
        g = max(-10.0, min(20.0, self.graph.master_gain + step))
        if abs(g - self.graph.master_gain) >= 0.05:
            self.graph.master_gain = round(g, 2)
            self.graph.apply_drive()

    def playing(self, n: int, f: dict) -> bool:
        """The source itself is playing (not just stage bleed): its input, after the soundcheck
        trim, is within 12 dB of the calibrated working level (-20 dBFS)."""
        return f['raw'][n - 1] + self.graph.strips[n].trim > -32 and f['raw'][n - 1] > -60

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
            if not self.playing(n, f) or g.mute[n]:
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

    def _watch_howl(self, cands: list[dict]) -> None:
        """Emergency only: a feedback tone that persists ~0.6 s (and isn't a held musical note:
        it must stay within 1 % in pitch) gets a narrow notch on that channel (EQ band 8),
        even if a human holds the channel. Released after 30 s without recurrence."""
        now = time.time()
        seen = set()
        for c in cands:
            key = c['ch']
            seen.add(key)
            h = self.howl_track.get(key)
            if h and abs(h['f'] - c['f']) / h['f'] < 0.01:
                h['n'] += 1
            else:
                self.howl_track[key] = h = {'f': c['f'], 'n': 1}
            if h['n'] >= 6 and key not in self.notches:
                st = self.graph.strips[key]
                band = ('bell', c['f'], -9.0, 30.0)
                st.eq = (st.eq + [band])[:8] if len(st.eq) < 8 else st.eq[:7] + [band]
                self.graph.apply_strip(key)
                self.notches[key] = {'f': c['f'], 'at': now, 'last': now}
                self.broadcast({'type': 'alert', 'level': 'error', 'ch': key, 'text': f'Feedback on {st.name} at {round(c["f"])} Hz: notched it (-9 dB, very narrow).'})
                self.broadcast(self.state())
            elif key in self.notches:
                self.notches[key]['last'] = now
        for key in list(self.howl_track):
            if key not in seen:
                del self.howl_track[key]
        for key, nt in list(self.notches.items()):
            if now - nt['last'] > 30:
                st = self.graph.strips[key]
                st.eq = [b for b in st.eq if not (b[0] == 'bell' and b[3] == 30.0 and abs(b[1] - nt['f']) < 1)]
                self.graph.apply_strip(key)
                del self.notches[key]
                self.broadcast({'type': 'alert', 'level': 'info', 'ch': key, 'text': f'Feedback gone on {st.name}: notch released.'})
                self.broadcast(self.state())

    def _watch_clip_and_dead(self, f: dict) -> None:
        """Emergencies (allowed even on held channels): a channel clipping at its digital trim
        gets the trim pulled down 3 dB; a source that was playing and goes silent for 20 s
        while the band plays raises a dead-signal alert (it may be a mic or wireless pack)."""
        now = time.time()
        band_on = sum(1 for n in range(1, 17) if self.playing(n, f)) >= 3
        for n, st in self.graph.strips.items():
            i = n - 1
            if f['peak'][i] > -0.3:
                self.clip_count[i] += 1
                if self.clip_count[i] >= 3 and now - self.last_clip_fix[i] > 5:
                    st.trim = round(st.trim - 3.0, 1)
                    self.graph.apply_gain(n)
                    self.last_clip_fix[i] = now
                    self.save()
                    self.broadcast({'type': 'alert', 'level': 'error', 'ch': n, 'text': f'{st.name} was clipping: digital trim pulled down 3 dB (the mixer preamp is untouched).'})
                    self.broadcast(self.state())
            else:
                self.clip_count[i] = 0
            if f['raw'][i] > -75:  # a live mic always hears some stage bleed; a dead one doesn't
                self.last_heard[i] = now
                if self.dead_alerted[i]:
                    self.dead_alerted[i] = False
                    self.broadcast({'type': 'alert', 'level': 'info', 'ch': n, 'text': f'{st.name} is back.'})
            elif band_on and self.last_heard[i] and now - self.last_heard[i] > 20 and not self.dead_alerted[i] and n in (9, 10, 15) and self.running():
                self.dead_alerted[i] = True
                self.broadcast({'type': 'alert', 'level': 'error', 'ch': n, 'text': f'{st.name} has no signal at all (not even stage bleed) for 20 s while the band plays — check the mic, cable or wireless pack.'})

    def _follow_arrangement(self, f: dict) -> None:
        """Lead/backing vocals, solos and auto-mute (see arrangement.py). Only while the music runs;
        channels a human muted or soloed are left alone."""
        if not self.running():
            return
        g = self.graph
        self.arr.held = {n for n in g.strips if g.mute[n] or g.solo[n]}
        playing = {n: self.playing(n, f) for n in g.strips}
        level = {n: f['raw'][n - 1] + g.strips[n].trim for n in g.strips}
        raw = {n: f['raw'][n - 1] for n in g.strips}
        for n, off in self.arr.frame(playing, level, raw).items():
            g.arr[n] = off
            g.apply_fader(n)
            g.apply_sends(n)

    def _keep_vocals_on_top(self, f: dict) -> None:
        """Holds the lead-vocal-to-band ratio near +5 dB by moving one shared offset on all
        non-vocal channels (their balance against each other stays as set). Only learns while
        a vocal is actually singing; moves at most 0.5 dB every 2 s, range -12..+3 dB."""
        g = self.graph
        p = [10 ** ((f['rms'][i] + g.gain_db(i + 1)) / 10) * (0 if g.mute[i + 1] else 1) for i in range(16)]
        lead = self.arr.lead if self.arr.lead_singing() else None
        voc = p[lead - 1] if lead else 0.0
        band = sum(p) - sum(p[i - 1] for i in self.arr.voices)  # backing voices count for neither side
        sing = lead is not None and self.playing(lead, f) and voc > 1e-9 and band > 1e-9
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
                if k not in P.OFFSET_EXEMPT:
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
        if not self.running() or time.time() > self.calibrating_until:
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

    def running(self) -> bool:
        """Audio is flowing from the current source."""
        return self.player.playing if self.source == 'recording' else self.venue.status()['connected']

    def set_source(self, source: str) -> None:
        """Switch the whole mix between the test recording and the live venue feed."""
        if source == self.source or source not in ('recording', 'venue'):
            return
        old = self.player.port_names if self.source == 'recording' else self.venue.port_names
        new = self.venue.port_names if source == 'venue' else self.player.port_names
        self.graph.set_source(old, new)
        a = self.analyzer.client.name
        for n in range(1, 17):
            try:
                self.mh.cmd(f'disconnect {old[n - 1]} {a}:raw_{n}')
            except Exception:  # noqa: BLE001
                pass
            self.mh.connect_ports(new[n - 1], f'{a}:raw_{n}')
        if source == 'venue':
            self.player.pause()
            if not self.calibrated_session:  # first live audio of the session: soundcheck calibration
                self.calibrated_session = True
                self.start_calibration()
        self.source = source
        self.analyzer.loud.reset_integrated()
        log.info('source -> %s', source)
        self.broadcast(self.state())

    def _auto_source(self) -> None:
        """When the venue laptop starts sending, the mix follows it automatically."""
        while True:
            time.sleep(1)
            on = self.venue.status()['connected']
            if on and self.source != 'venue' and self.auto_venue:
                self.set_source('venue')
            elif not on and self.source == 'venue' and time.time() - self.venue.last_data > 10:
                self.broadcast({'type': 'alert', 'level': 'error', 'ch': 0, 'text': 'Venue feed lost for 10 s — check the venue laptop and its network. Mix holds; switching back when it returns.'})
                self.venue.last_data = time.time()  # alert at most every 10 s

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
        tr = self.player.status() if self.source == 'recording' else {**self.player.status(), 'source': 'venue', 'name': 'MR18 venue feed', 'playing': self.venue.status()['connected']}
        return {'type': 'engine', 'mix': self.graph.snapshot(), 'transport': tr, 'venue': self.venue.status(), 'leveller': self.leveller_on,
                'calibrating': self.calibrating_until > time.time()}

    # ---------- commands ----------

    def handle(self, c: dict) -> dict:
        g, t = self.graph, c.get('type')
        n = int(c.get('ch', 0))
        s = g.strips.get(n)
        if t == 'master':
            # Live master-bus changes (EQ bands, bus glue, tape): {"eq": [[kind, f, gain, q], ...], "bus": {...}, "tape": {...}}
            if isinstance(c.get('eq'), list):
                P.MASTER_EQ[:] = [tuple(b) for b in c['eq']][:8]
            for key, target in (('bus', P.MASTER_BUS), ('tape', P.MASTER_TAPE), ('console', P.MASTER_CONSOLE)):
                if isinstance(c.get(key), dict):
                    target.update({k: v for k, v in c[key].items() if k in target})
            g.apply_master()
            return {'type': 'master', 'eq': P.MASTER_EQ, 'bus': P.MASTER_BUS, 'tape': P.MASTER_TAPE, 'console': P.MASTER_CONSOLE}
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
        elif t == 'param_get':  # diagnostics: read any plugin port through our mod-host connection
            return {'value': self.mh.cmd(f"param_get {int(c['inst'])} {c['symbol']}")}
        elif t == 'source':
            self.auto_venue = c.get('source') == 'venue'
            self.set_source(str(c.get('source')))
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
    async def clip(req: web.Request) -> web.Response:
        n = max(1, min(100, int(float(req.query.get('seconds', '6')) * 10)))
        return web.Response(body=wav_bytes(list(engine.analyzer.clip)[-n:]), content_type='audio/wav')

    app.router.add_get('/stream.mp3', stream)
    app.router.add_get('/clip.wav', clip)
    app.on_startup.append(on_start)
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
    engine = Engine()
    log.info('mix graph built; %s sets available', engine.player.sets.keys())
    web.run_app(make_app(engine), host=HOST, port=PORT, print=None)


if __name__ == '__main__':
    main()
