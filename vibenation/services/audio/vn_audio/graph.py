"""Builds the broadcast mix inside mod-host and maps mix settings to plugin ports.

Signal flow per channel:  source -> [gate, kick only] -> EQ (8 bands) -> compressor
  -> main mixer (fader, pan, mute, solo)  and  -> send mixers (plate / room / delay)
Effects:  send mixer -> Dragonfly plate | Dragonfly room | Calf vintage delay -> returns mixer
Master:   main mixer + returns -> stream EQ -> glue compressor -> x42 true-peak limiter
"""

from __future__ import annotations

import copy
import os
import logging
import math
import time
from dataclasses import asdict

from . import presets as P
from .modhost import ModHost

log = logging.getLogger('vn_audio.graph')

LSP = 'http://lsp-plug.in/plugins/lv2/'
URI = {
    'gate': LSP + 'gate_mono',
    'eq': LSP + 'para_equalizer_x8_mono',
    'comp': LSP + 'compressor_mono',
    'mixer': LSP + 'mixer_x16_stereo',
    'send': LSP + 'mixer_x16_mono',
    'returns': LSP + 'mixer_x4_stereo',
    'plate': 'urn:dragonfly:plate',
    'room': 'urn:dragonfly:room',
    'delay': 'http://calf.sourceforge.net/plugins/VintageDelay',
    'meq': LSP + 'para_equalizer_x8_stereo',
    'mcomp': 'https://vibenation.app/lv2/vn_vca_bus',
    'mconsole': 'https://vibenation.app/lv2/vn_console',
    'mtape': 'https://vibenation.app/lv2/vn_tape_stereo',
    'limiter': 'http://gareus.org/oss/lv2/dpl#stereo',
}

# Instance ids
GATE, EQ, COMP = 100, 200, 300
MIXER, SEND = 1000, {'plate': 1010, 'room': 1011, 'delay': 1012}
FXI = {'plate': 1020, 'room': 1021, 'delay': 1022}
RETURNS, MEQ, MCOMP, LIMITER, MCONSOLE, MTAPE = 1030, 1040, 1041, 1042, 1043, 1044
INS = 500  # character inserts: 500 + 10*n + k
CONV = 700  # per-channel stereo convolution (measured impulse responses): 700 + n
CONV_URI = 'http://gareus.org/oss/lv2/zeroconvolv#MonoToStereo'
IR_DIR = os.environ.get('VN_IR_DIR', '/home/vibe/vibenation-media/megami/approved')
RETURN_SLOT = {'plate': 1, 'room': 2, 'delay': 3}

EQ_TYPE = {'off': 0, 'bell': 1, 'hpf': 2, 'hshelf': 3, 'lpf': 4, 'lshelf': 5}

lin = lambda db: 10 ** (db / 20)  # noqa: E731


_IR_BUNDLE = os.path.join(os.environ.get('VN_DATA', os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data')), 'vn-impulse-responses.lv2')


def register_ir_presets(mh, paths: dict[int, str]) -> None:
    """Our mod-host can't set file properties directly, but it loads presets: write one LV2 preset bundle
    (one preset per channel, pointing at its impulse response) and register it once."""
    if not paths:
        return
    os.makedirs(_IR_BUNDLE, exist_ok=True)
    pre = '@prefix lv2: <http://lv2plug.in/ns/lv2core#> .\n@prefix pset: <http://lv2plug.in/ns/ext/presets#> .\n@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n@prefix state: <http://lv2plug.in/ns/ext/state#> .\n\n'
    man, body = pre, pre
    for ch, p in sorted(paths.items()):
        uri = f'urn:vibenation:ir:ch{ch}'
        man += f'<{uri}> a pset:Preset ; lv2:appliesTo <{CONV_URI}> ; rdfs:seeAlso <presets.ttl> .\n'
        body += f'<{uri}> a pset:Preset ; lv2:appliesTo <{CONV_URI}> ; rdfs:label "VibeNation ch{ch}" ;\n    state:state [ <http://gareus.org/oss/lv2/zeroconvolv#ir> <file://{os.path.abspath(p)}> ] .\n'
    open(os.path.join(_IR_BUNDLE, 'manifest.ttl'), 'w').write(man)
    open(os.path.join(_IR_BUNDLE, 'presets.ttl'), 'w').write(body)
    try:
        mh.cmd(f'bundle_add {os.path.abspath(_IR_BUNDLE)}/')
    except Exception as e:  # noqa: BLE001 - channels then run without their impulse responses (logged per channel)
        log.warning('impulse-response presets could not be registered: %s', e)

def port(inst: int, sym: str) -> str:
    return f'effect_{inst}:{sym}'


class MixGraph:
    """Owns the plugin graph and the current value of every mix control."""

    def __init__(self, mh: ModHost, sources: list[str], outputs: list[list[str]]):
        self.mh = mh
        self.sources = sources  # 16 JACK output ports feeding the strips
        self.outputs = outputs  # master L/R go to each of these [L, R] port pairs
        self.strips = {s.n: copy.deepcopy(s) for s in P.STRIPS}
        self.mute = {n: False for n in self.strips}
        self.conv_on: set[int] = set()  # channels running their impulse response (stereo into the mixer)
        self.solo = {n: False for n in self.strips}
        self.global_trim = 0.0  # unused (kept for saved-state compatibility)
        self.band_offset = P.BAND_OFFSET_FIXED if P.BALANCE_LOCKED else 0.0  # "vocals on top": shared offset on every non-vocal channel (dB)
        self.master_eq_live: list[P.Band] | None = None  # MASTER_EQ + tone keeper offsets
        self.fx_duck = 0.0  # dB on the plate/echo returns while the lead vocal sings 
        self.ride: dict[int, float] = {}  # current rider gain per channel (dB)
        self.arr: dict[int, float] = {}  # arrangement offset per channel (dB): lead/backing/solo/auto-mute, not saved
        self.master_gain = 0.0  # limiter input drive, dB (set by the loudness leveller)
        self.fx = {k: dict(v) for k, v in P.FX.items()}
        self.bpm = 118.0

    # ---------- build ----------

    def build(self) -> None:
        mh = self.mh  # the plugin host is restarted clean before each engine start
        self.conv_on.clear()
        t0 = time.time()

        mh.add(URI['mixer'], MIXER)
        for k, inst in SEND.items():
            mh.add(URI['send'], inst)
            mh.add(URI[k], FXI[k])
        mh.add(URI['returns'], RETURNS)
        mh.add(URI['meq'], MEQ)
        mh.add(URI['mcomp'], MCOMP)
        mh.add(URI['mconsole'], MCONSOLE)
        mh.add(URI['mtape'], MTAPE)
        mh.monitor(MCOMP, 'gr')
        mh.add(URI['limiter'], LIMITER)

        # all impulse-response presets in one bundle, registered once (mod-host caches a bundle on first load)
        register_ir_presets(mh, {n: os.path.join(IR_DIR, st.conv) for n, st in self.strips.items()
                                 if st.conv and os.path.exists(os.path.join(IR_DIR, st.conv))})
        for n, s in self.strips.items():
            if s.gate:
                mh.add(URI['gate'], GATE + n)
            mh.add(URI['eq'], EQ + n)
            mh.add(URI['comp'], COMP + n)
            mh.monitor(COMP + n, 'rlm')
            first = GATE + n if s.gate else EQ + n
            mh.connect_ports(self.sources[n - 1], port(first, 'in'))
            if s.gate:
                mh.connect_ports(port(GATE + n, 'out'), port(EQ + n, 'in'))
            mh.connect_ports(port(EQ + n, 'out'), port(COMP + n, 'in'))
            prev = port(COMP + n, 'out')
            for k, (kind, _params) in enumerate(s.inserts):
                inst = INS + 10 * n + k
                mh.add(P.INSERT_URI[kind], inst)
                mh.connect_ports(prev, port(inst, 'in'))
                prev = port(inst, 'out')
            out = self.strip_out(n)
            conv_ok = False
            if s.conv and os.path.exists(os.path.join(IR_DIR, s.conv)):
                try:
                    mh.add(CONV_URI, CONV + n)
                    mh.cmd(f'preset_load {CONV + n} urn:vibenation:ir:ch{n}')
                    mh.connect_ports(out, port(CONV + n, 'in'))
                    mh.connect_ports(port(CONV + n, 'out_1'), port(MIXER, f'in_{n}l'))
                    mh.connect_ports(port(CONV + n, 'out_2'), port(MIXER, f'in_{n}r'))
                    conv_ok = True
                    self.conv_on.add(n)
                    log.info('ch%d: impulse response %s', n, s.conv)
                except Exception as e:  # noqa: BLE001 - never let a missing IR stop the engine
                    log.warning('ch%d: impulse response %s could not load (%s); channel runs without it', n, s.conv, e)
                    mh.remove(CONV + n)
            if not conv_ok:
                if s.conv and not os.path.exists(os.path.join(IR_DIR, s.conv)):
                    log.warning('ch%d: impulse response %s not found in %s; channel runs without it', n, s.conv, IR_DIR)
                mh.connect_ports(out, port(MIXER, f'in_{n}l'))
                mh.connect_ports(out, port(MIXER, f'in_{n}r'))
            for k, inst in SEND.items():
                mh.connect_ports(out, port(inst, f'in_{n}'))
            self.apply_strip(n)

        # Effects: mono send bus -> stereo effect -> returns mixer slot
        for k, inst in SEND.items():
            fx_in = ('lv2_audio_in_1', 'lv2_audio_in_2') if k != 'delay' else ('in_l', 'in_r')
            fx_out = ('lv2_audio_out_1', 'lv2_audio_out_2') if k != 'delay' else ('out_l', 'out_r')
            for p in fx_in:
                mh.connect_ports(port(inst, 'out'), port(FXI[k], p))
            slot = RETURN_SLOT[k]
            mh.connect_ports(port(FXI[k], fx_out[0]), port(RETURNS, f'in_{slot}l'))
            mh.connect_ports(port(FXI[k], fx_out[1]), port(RETURNS, f'in_{slot}r'))
        self.apply_fx()

        # Master
        for side in ('l', 'r'):
            mh.connect_ports(port(MIXER, f'out_{side}'), port(MEQ, f'in_{side}'))
            mh.connect_ports(port(RETURNS, f'out_{side}'), port(MEQ, f'in_{side}'))
            mh.connect_ports(port(MEQ, f'out_{side}'), port(MCONSOLE, f'in_{side}'))
            mh.connect_ports(port(MCONSOLE, f'out_{side}'), port(MCOMP, f'in_{side}'))
            mh.connect_ports(port(MCOMP, f'out_{side}'), port(MTAPE, f'in_{side}'))
        mh.connect_ports(port(MTAPE, 'out_l'), port(LIMITER, 'inL'))
        mh.connect_ports(port(MTAPE, 'out_r'), port(LIMITER, 'inR'))
        for pair in self.outputs:
            mh.connect_ports(port(LIMITER, 'outL'), pair[0])
            mh.connect_ports(port(LIMITER, 'outR'), pair[1])
        self.apply_master()
        log.info('graph built in %.1f s', time.time() - t0)

    # ---------- apply ----------

    def _eq(self, inst: int, bands: list[P.Band], stereo: bool = False) -> None:
        mh = self.mh
        mh.param(inst, 'mode', 0)  # IIR, zero latency
        for i in range(8):
            if i < len(bands):
                kind, f, g, q = bands[i]
                mh.param(inst, f'ft_{i}', EQ_TYPE[kind])
                mh.param(inst, f'fm_{i}', 0)
                mh.param(inst, f's_{i}', 1 if kind in ('hpf', 'lpf') else 0)
                mh.param(inst, f'f_{i}', f)
                mh.param(inst, f'g_{i}', lin(g))
                mh.param(inst, f'q_{i}', q)
            else:
                mh.param(inst, f'ft_{i}', 0)

    def _comp(self, inst: int, c: P.Comp) -> None:
        mh = self.mh
        mh.param(inst, 'cm', 0)  # downward
        mh.param(inst, 'scm', 0 if c.peak else 1)  # sidechain: peak for drums, RMS otherwise
        mh.param(inst, 'al', lin(c.thresh))
        mh.param(inst, 'cr', c.ratio)
        mh.param(inst, 'at', c.attack)
        mh.param(inst, 'rt', c.release)
        mh.param(inst, 'kn', lin(c.knee))
        mh.param(inst, 'mk', lin(c.makeup))
        mh.param(inst, 'cdr', 1 - c.mix)
        mh.param(inst, 'cwt', c.mix)

    def apply_strip(self, n: int) -> None:
        s = self.strips[n]
        mh = self.mh
        if s.gate:
            g = s.gate
            mh.param(GATE + n, 'gt', lin(g.thresh))
            mh.param(GATE + n, 'gr', lin(-g.range))
            mh.param(GATE + n, 'at', g.attack)
            mh.param(GATE + n, 'rt', g.release + g.hold)
        bands = [b for b in s.eq if not (s.no_hpf and b[0] == 'hpf')]  # user rule: never high-pass kick/bass
        self._eq(EQ + n, bands)
        if s.comp:
            self._comp(COMP + n, s.comp)
        else:
            mh.param(COMP + n, 'cr', 1)
        self.apply_fader(n)
        self.apply_sends(n)

    def input_port(self, n: int) -> str:
        """First plugin input of a strip (where the source plugs in)."""
        return port(GATE + n, 'in') if self.strips[n].gate else port(EQ + n, 'in')

    def set_source(self, old: list[str], new: list[str]) -> None:
        """Re-plug all 16 strips from one source (recording / venue) to another."""
        for n in range(1, 17):
            try:
                self.mh.cmd(f'disconnect {old[n - 1]} {self.input_port(n)}')
            except Exception:  # noqa: BLE001 - may already be disconnected
                pass
            self.mh.connect_ports(new[n - 1], self.input_port(n))
        self.sources = new

    def strip_out(self, n: int) -> str:
        k = len(self.strips[n].inserts)
        return port(INS + 10 * n + k - 1, 'out') if k else port(COMP + n, 'out')

    def apply_inserts(self, n: int) -> None:
        for k, (_kind, params) in enumerate(self.strips[n].inserts):
            for sym, v in params.items():
                self.mh.param(INS + 10 * n + k, sym, v)

    def apply_gain(self, n: int) -> None:
        """Gain staging: the per-channel trim (soundcheck calibration) brings every source to
        the same working level, so compressor thresholds and the band's faders mean the same
        on every channel. The rider adds its current ride after the compressor."""
        s = self.strips[n]
        self.mh.param(COMP + n, 'g_in', lin(s.trim))
        self.mh.param(COMP + n, 'g_out', lin(self.ride.get(n, 0.0)))

    def gain_db(self, n: int) -> float:
        """Effective channel gain: the fader, the band offset on the mid-range instruments, and the
        arrangement offset (lead/backing/solo/auto-mute)."""
        s = self.strips[n]
        return s.fader + (0.0 if n in P.OFFSET_EXEMPT else self.band_offset) + self.arr.get(n, 0.0)

    def apply_fader(self, n: int) -> None:
        s = self.strips[n]
        mh = self.mh
        mh.param(MIXER, f'cg_{n}', min(3.98107, lin(self.gain_db(n))))
        if n in self.conv_on:  # stereo after its impulse response: pan works as balance and keeps the width
            mh.param(MIXER, f'cp_{n}l', max(-100.0, min(100.0, -100.0 + s.pan)))
            mh.param(MIXER, f'cp_{n}r', max(-100.0, min(100.0, 100.0 + s.pan)))
        else:
            mh.param(MIXER, f'cp_{n}l', s.pan)
            mh.param(MIXER, f'cp_{n}r', s.pan)
        mh.param(MIXER, f'cm_{n}', 1 if self.mute[n] else 0)
        mh.param(MIXER, f'cs_{n}', 1 if self.solo[n] else 0)

    def apply_sends(self, n: int) -> None:
        s = self.strips[n]
        # Sends are post-fader: send gain = fader gain x send level.
        for k, inst in SEND.items():
            db = getattr(s, k)
            soloing = any(self.solo.values())
            on = db is not None and not self.mute[n] and (not soloing or self.solo[n])  # solo silences the others' effect sends too
            self.mh.param(inst, f'cg_{n}', min(3.98107, lin(self.gain_db(n) + db)) if on else 0)

    def apply_fx(self) -> None:
        mh, fx = self.mh, self.fx
        p = fx['plate']
        for sym, v in (('dry_level', 0), ('early_level', 100), ('decay', p['decay']), ('predelay', p['predelay']), ('low_cut', p['low_cut']), ('high_cut', p['high_cut'])):
            mh.param(FXI['plate'], sym, v)
        r = fx['room']
        for sym, v in (('dry_level', 0), ('early_level', 30), ('early_send', 30), ('late_level', 100), ('decay', r['decay']), ('predelay', r['predelay']), ('size', r['size']), ('in_high_cut', r['in_high_cut']), ('in_low_cut', 200)):
            mh.param(FXI['room'], sym, v)
        d = fx['delay']
        sixteenths = round(d['note'] * 8)  # note length in whole notes -> 16ths
        for sym, v in (('timing', 0), ('bpm', self.bpm), ('subdiv', 4), ('time_l', sixteenths), ('time_r', sixteenths), ('feedback', d['feedback']), ('amount', 1), ('dry', 0), ('medium', 1)):
            mh.param(FXI['delay'], sym, v)
        self.apply_returns()
        mh.param(RETURNS, 'cg_4', 0)

    def apply_returns(self) -> None:
        """Effect return levels, minus the vocal ducking (plate and echo dip while the lead sings)."""
        for k, slot in RETURN_SLOT.items():
            duck = self.fx_duck if k in ('plate', 'delay') else 0.0
            self.mh.param(RETURNS, f'cg_{slot}', lin(self.fx[k]['return_db'] + duck))

    def apply_master_eq(self) -> None:
        """Master EQ as set, plus the tone keeper's small offsets (server._keep_tone)."""
        self._eq(MEQ, self.master_eq_live or P.MASTER_EQ, stereo=True)

    def apply_master(self) -> None:
        self.apply_master_eq()
        mh = self.mh
        for inst, params in ((MCONSOLE, P.MASTER_CONSOLE), (MCOMP, P.MASTER_BUS), (MTAPE, P.MASTER_TAPE)):
            for sym, v in params.items():
                mh.param(inst, sym, v)
        mh.param(LIMITER, 'threshold', P.CEILING_DBTP)
        mh.param(LIMITER, 'truepeak', 1)
        mh.param(LIMITER, 'release', 0.12)
        mh.param(LIMITER, 'gain', 0)
        self.apply_drive()

    def apply_drive(self) -> None:
        """Leveller drive sits at the master EQ output, so the console, bus glue and tape
        work on a signal already near the -16 LUFS target and the limiter only catches peaks."""
        self.mh.param(MEQ, 'g_out', min(10.0, lin(self.master_gain)))

    def set_bpm(self, bpm: float) -> None:
        self.bpm = max(60.0, min(200.0, bpm))
        self.mh.param(FXI['delay'], 'bpm', self.bpm)

    # ---------- snapshot ----------

    def load(self, data: dict) -> None:
        """Restore saved strips/fx (from snapshot()) before build()."""
        for k, d in data.get('strips', {}).items():
            n = int(k)
            if n not in self.strips:
                continue
            st = self.strips[n]
            for f in ('fader', 'pan', 'trim', 'plate', 'room', 'delay', 'rider'):
                if f in d:
                    setattr(st, f, d[f])
            if 'eq' in d:
                st.eq = [tuple(b) for b in d['eq']]  # type: ignore[misc]
            if d.get('comp') and st.comp:
                for f, v in d['comp'].items():
                    setattr(st.comp, f, v)
            self.mute[n] = bool(d.get('mute', False))
            self.solo[n] = False
        for k, v in data.get('fx', {}).items():
            if k in self.fx:
                self.fx[k].update(v)
        self.master_gain = min(P.MAX_DRIVE_DB, float(data.get('master_gain', 0.0)))
        self.band_offset = max(-3.0, min(2.0, float(data.get('band_offset', 0.0))))  # same range as the keeper
        if P.BALANCE_LOCKED:
            self.band_offset = P.BAND_OFFSET_FIXED  # the user's saved balance was set with this offset in place

    def snapshot(self) -> dict:
        return {
            'strips': {n: {**asdict(s), 'mute': self.mute[n], 'solo': self.solo[n]} for n, s in self.strips.items()},
            'base': {s.n: asdict(s) for s in P.STRIPS},
            'master': {'console': P.MASTER_CONSOLE, 'bus': P.MASTER_BUS, 'tape': P.MASTER_TAPE},
            'fx': self.fx,
            'master_gain': self.master_gain,
            'global_trim': self.global_trim,
            'band_offset': self.band_offset,
            'bpm': self.bpm,
        }


def db(x: float) -> float:
    return 20 * math.log10(max(x, 1e-9))
