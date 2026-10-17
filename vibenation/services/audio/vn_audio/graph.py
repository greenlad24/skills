"""Builds the broadcast mix inside mod-host and maps mix settings to plugin ports.

Signal flow per channel:  source -> [gate, kick only] -> EQ (8 bands) -> compressor
  -> main mixer (fader, pan, mute, solo)  and  -> send mixers (plate / room / delay)
Effects:  send mixer -> Dragonfly plate | Dragonfly room | Calf vintage delay -> returns mixer
Master:   main mixer + returns -> stream EQ -> glue compressor -> x42 true-peak limiter
"""

from __future__ import annotations

import copy
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
    'mcomp': LSP + 'compressor_stereo',
    'limiter': 'http://gareus.org/oss/lv2/dpl#stereo',
}

# Instance ids
GATE, EQ, COMP = 100, 200, 300
MIXER, SEND = 1000, {'plate': 1010, 'room': 1011, 'delay': 1012}
FXI = {'plate': 1020, 'room': 1021, 'delay': 1022}
RETURNS, MEQ, MCOMP, LIMITER = 1030, 1040, 1041, 1042
RETURN_SLOT = {'plate': 1, 'room': 2, 'delay': 3}

EQ_TYPE = {'off': 0, 'bell': 1, 'hpf': 2, 'hshelf': 3, 'lpf': 4, 'lshelf': 5}

lin = lambda db: 10 ** (db / 20)  # noqa: E731


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
        self.solo = {n: False for n in self.strips}
        self.global_trim = 0.0  # overall gain staging (dB) applied to every channel after its compressor
        self.ride: dict[int, float] = {}  # current rider gain per channel (dB)
        self.master_gain = 0.0  # limiter input drive, dB (set by the loudness leveller)
        self.fx = {k: dict(v) for k, v in P.FX.items()}
        self.bpm = 118.0

    # ---------- build ----------

    def build(self) -> None:
        mh = self.mh  # the plugin host is restarted clean before each engine start
        t0 = time.time()

        mh.add(URI['mixer'], MIXER)
        for k, inst in SEND.items():
            mh.add(URI['send'], inst)
            mh.add(URI[k], FXI[k])
        mh.add(URI['returns'], RETURNS)
        mh.add(URI['meq'], MEQ)
        mh.add(URI['mcomp'], MCOMP)
        mh.add(URI['limiter'], LIMITER)

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
            out = self.strip_out(n)
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
            mh.connect_ports(port(MEQ, f'out_{side}'), port(MCOMP, f'in_{side}'))
        mh.connect_ports(port(MCOMP, 'out_l'), port(LIMITER, 'inL'))
        mh.connect_ports(port(MCOMP, 'out_r'), port(LIMITER, 'inR'))
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

    def strip_out(self, n: int) -> str:
        return port(COMP + n, 'out')

    def apply_gain(self, n: int) -> None:
        """Gain staging around the compressor: the per-channel trim sets the level the
        compressor sees (so thresholds mean the same on every source); after it, the level
        is handed back (global trim - trim) so the recording's own balance and the band's
        faders keep their meaning. The rider adds its current ride on top."""
        s = self.strips[n]
        self.mh.param(COMP + n, 'g_in', lin(s.trim))
        self.mh.param(COMP + n, 'g_out', lin(self.global_trim - s.trim + self.ride.get(n, 0.0)))

    def apply_fader(self, n: int) -> None:
        s = self.strips[n]
        mh = self.mh
        mh.param(MIXER, f'cg_{n}', min(3.98107, lin(s.fader)))
        mh.param(MIXER, f'cp_{n}l', s.pan)
        mh.param(MIXER, f'cp_{n}r', s.pan)
        mh.param(MIXER, f'cm_{n}', 1 if self.mute[n] else 0)
        mh.param(MIXER, f'cs_{n}', 1 if self.solo[n] else 0)

    def apply_sends(self, n: int) -> None:
        s = self.strips[n]
        # Sends are post-fader: send gain = fader gain x send level.
        for k, inst in SEND.items():
            db = getattr(s, k)
            on = db is not None and not self.mute[n]
            self.mh.param(inst, f'cg_{n}', min(3.98107, lin(s.fader + db)) if on else 0)

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
        for k, slot in RETURN_SLOT.items():
            mh.param(RETURNS, f'cg_{slot}', lin(fx[k]['return_db']))
        mh.param(RETURNS, 'cg_4', 0)

    def apply_master(self) -> None:
        self._eq(MEQ, P.MASTER_EQ, stereo=True)
        self._comp(MCOMP, P.MASTER_COMP)
        mh = self.mh
        mh.param(LIMITER, 'threshold', P.CEILING_DBTP)
        mh.param(LIMITER, 'truepeak', 1)
        mh.param(LIMITER, 'release', 0.12)
        mh.param(LIMITER, 'gain', self.master_gain)

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
        self.master_gain = float(data.get('master_gain', 0.0))
        self.global_trim = float(data.get('global_trim', 0.0))

    def snapshot(self) -> dict:
        return {
            'strips': {n: {**asdict(s), 'mute': self.mute[n], 'solo': self.solo[n]} for n, s in self.strips.items()},
            'base': {s.n: asdict(s) for s in P.STRIPS},
            'fx': self.fx,
            'master_gain': self.master_gain,
            'global_trim': self.global_trim,
            'bpm': self.bpm,
        }


def db(x: float) -> float:
    return 20 * math.log10(max(x, 1e-9))
