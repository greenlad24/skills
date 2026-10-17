// Claude's mixer loop. Every 1–3 minutes (sooner on an alert) it summarises what the
// mix is doing, asks Claude for a few small changes, clamps every change to hard
// bounds in code, skips anything a human holds, applies the rest and logs each one
// with its reason and an undo. Fast moves (riders, leveller, limiter) stay in the
// deterministic engine; Claude only sets their targets.

import { CHANNELS, type ChannelState, type FeedItem, type ShowState } from '@vibenation/shared';
import type { AudioLink, EngineFrame } from './audio.js';
import { askClaude, CLAUDE_MODEL } from './claude.js';
import { loadPlaybook } from './learning.js';

export interface MixerHost {
  state: ShowState;
  listener?: { summary(): string | null };
  audio: AudioLink;
  isHeld(id: string): boolean;
  addFeed(f: Omit<FeedItem, 'id' | 't'>, undo?: () => void): void;
  aiTouched(ch: number): void;
  hold(id: string, ch?: number): void;
  changed(): void;
}

type Change =
  | { ch: number; action: 'fader'; value: number; why: string; confidence?: Conf }
  | { ch: number; action: 'eq'; band: number; gain?: number; f?: number; why: string; confidence?: Conf }
  | { ch: number; action: 'comp'; thresh?: number; ratio?: number; why: string; confidence?: Conf }
  | { ch: number; action: 'send'; fx: 'plate' | 'room' | 'delay'; value: number | null; why: string; confidence?: Conf }
  | { ch: number; action: 'rider'; value: number; why: string; confidence?: Conf };
type Conf = 'sure' | 'likely' | 'guessing';

interface Reply {
  heard: string;
  assessment: string;
  changes: Change[];
  next_check_s?: number;
}

const BASE = Object.fromEntries(CHANNELS.map((c) => [c.n, c]));
const LOCKED_FADERS = new Set([1, 2, 3, 9, 10]); // kick, snare, OH, vocals: ±1 dB once balanced (band rule)
const PIANO = new Set([6, 7]);
const NO_HPF = new Set([1, 12, 14]);
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const r1 = (v: number) => Math.round(v * 10) / 10;
const pw = (db: number) => 10 ** (db / 10);
const dbOf = (p: number) => (p > 0 ? 10 * Math.log10(p) : -120);

export const MIXER_SYSTEM = `You are the broadcast mix engineer for VibeNation, mixing a live funk/soul/R&B cover band for a YouTube/multistream audience who mostly listen on phones and laptops.
You never touch the MR18 preamp gain (you have no access to it). Fast moves (vocal/solo riders on ch 9, 10, 15, 16 that even out each player's level, master loudness leveller, true-peak limiter) are automatic; you make small, deliberate, explainable adjustments every few minutes, like a calm A1 who listens, then nudges.

Band rules (always obey):
- Vocals on top: lead vocal (ch 9) and second vocal (ch 10) must stay intelligible. Target lead-vocal-to-band ratio (LAR) +3 to +7 dB, ideally about +5.
- No high-pass filter ever on kick (1), bass DI (12) or synth bass (14). Kick and bass work hand in hand; bass impressive but never overshadowing.
- Piano (6+7, a stereo pair: always move both the same) is rich, sits in the low-mids behind the singer and is never low: fader floor -13 dB.
- Harmonica (16) can be very sharp: soften, never harsh. Sax (15) clear, never honky or harsh.
- Drums are prominent (band preference): punchy kick and snare that drive the groove, just under the vocals. Never make them smaller with EQ, compression or sends; if something fights them, move that instead.
- Kick, snare, overheads and vocal faders are locked within ±1 dB of their balance; use EQ, compression targets, rider targets and sends there instead.
- Prefer cuts over boosts; one problem, one move. If nothing is clearly wrong, change nothing — an empty list is a good answer.
- Never chase loudness with faders: the master leveller holds -16 LUFS. If the limiter works more than 3-4 dB, the fix is upstream balance/EQ.
- Reverb/delay are the main creative dials per song section (ballad more plate, fast funk drier). Vocal plate on ch 9 never below -14 dB while singing.

Limits per change (code enforces them anyway): fader ±1.5 dB; EQ band gain ±1 dB and freq within 1/3 octave; compressor threshold ±2 dB, ratio ±0.5; send ±2 dB; rider offset ±1.5 dB per change (range -3..+3). At most 5 changes per answer. Never touch a control listed as held by a human.

Answer with JSON only:
{"heard": "<what you hear in a few words, e.g. 'keys solo, vocal resting'>", "assessment": "<one or two plain sentences>", "changes": [{"ch": <n>, "action": "fader"|"eq"|"comp"|"send"|"rider", ... , "why": "<short plain reason a musician understands>", "confidence": "sure"|"likely"|"guessing"}], "next_check_s": <60-180>}
Shapes: fader {"value": <new dB>}; eq {"band": <index from the list>, "gain"?: <new dB>, "f"?: <new Hz>}; comp {"thresh"?: <new dB>, "ratio"?: <new>}; send {"fx": "plate"|"room"|"delay", "value": <new dB or null for off>}; rider {"value": <new offset dB, -3..+3, moves that singer/soloist relative to their own running level>}.`;

export class MixerLoop {
  enabled = true;
  busy = false;
  nextAt = Date.now() + 45_000;
  lastRun = 0;
  lastError = '';
  calls = 0;
  private history: { t: number; text: string }[] = [];

  constructor(private host: MixerHost) {
    setInterval(() => this.tick(), 5_000);
  }

  status(): string {
    if (!this.enabled) return 'off';
    if (this.busy) return 'listening…';
    const a = this.host.state.audio;
    if (!a?.playing) return 'waiting for music';
    return `next check ${Math.max(0, Math.round((this.nextAt - Date.now()) / 1000))} s`;
  }

  private alert(frames: EngineFrame[]): string | null {
    const recent = frames.slice(-50);
    if (recent.length < 30) return null;
    if (recent.filter((f) => f.master.limiterGr > 4).length > 20) return 'limiter working over 4 dB';
    if (recent.some((f) => f.master.truePeak > -0.8)) return 'true peak above -1 dBTP';
    return null;
  }

  private async tick() {
    const { state, audio } = this.host;
    if (!this.enabled || this.busy || !audio.connected || !state.audio?.playing) return;
    const alert = this.alert(audio.history);
    const due = Date.now() >= this.nextAt || (alert && Date.now() - this.lastRun > 45_000);
    if (!due || audio.history.length < 200) return;
    this.busy = true;
    this.host.changed();
    try {
      await this.run(alert);
    } finally {
      this.busy = false;
      this.lastRun = Date.now();
      this.host.changed();
    }
  }

  /** Summary of the last ~30 s that Claude reads. */
  report(alert: string | null): string {
    const { state, audio } = this.host;
    const frames = audio.history;
    const n = frames.length;
    const chans = state.channels;
    const avg = (fn: (f: EngineFrame) => number) => frames.reduce((s, f) => s + fn(f), 0) / n;
    const lines: string[] = [];
    const m = frames[n - 1].master;
    const stVals = frames.map((f) => f.master.lufsS);
    lines.push(`Song position: ${state.audio?.set ?? ''} ${Math.round(state.audio?.position ?? 0)} s. Song: ${state.song}. Tempo ~${Math.round(state.bpm)} BPM.`);
    if (alert) lines.push(`ALERT: ${alert}.`);
    lines.push(`Vocals-on-top keeper: all non-vocal channels currently offset ${(m as unknown as { bandOffset?: number }).bandOffset ?? 0} dB (automatic, holds LAR near +5; you don't need to fight it with faders).`);
    lines.push(`Master: integrated ${m.lufsI} LUFS (target -16), short-term range ${Math.min(...stVals).toFixed(1)}..${Math.max(...stVals).toFixed(1)}, true peak max ${Math.max(...frames.map((f) => f.master.truePeak)).toFixed(1)} dBTP, limiter max ${Math.max(...frames.map((f) => f.master.limiterGr)).toFixed(1)} dB, leveller drive ${m.drive} dB.`);

    // Lead-to-accompaniment ratio from post-fader channel power.
    const lar: number[] = [];
    for (const f of frames) {
      const off = (f.master as unknown as { bandOffset?: number }).bandOffset ?? 0;
      const p = f.rms.map((v, i) => pw(v + chans[i].fader + (i === 8 || i === 9 ? 0 : off)) * (chans[i].mute ? 0 : 1));
      const voc = p[8] + p[9];
      const band = p.reduce((a, b) => a + b, 0) - voc;
      if ((f.singing?.[8] || f.singing?.[9]) && band > 0) lar.push(dbOf(voc / band));
    }
    lar.sort((a, b) => a - b);
    lines.push(lar.length > 20 ? `Vocal-to-band ratio (LAR) median ${lar[lar.length >> 1].toFixed(1)} dB, range ${lar[Math.floor(lar.length * 0.1)].toFixed(1)}..${lar[Math.floor(lar.length * 0.9)].toFixed(1)}.` : 'Vocals mostly silent in this window (LAR n/a).');

    // Master tonal balance in 8 groups of 4 bands (30 Hz – 16 kHz), relative to the mean.
    const groups = ['30-65', '65-140', '140-300', '300-650', '650-1.4k', '1.4k-3k', '3k-6.5k', '6.5k-16k'];
    const mspec = Array.from({ length: 8 }, (_, g) => avg((f) => (f.master as unknown as { spec: number[] }).spec.slice(g * 4, g * 4 + 4).reduce((a, b) => a + b, 0) / 4));
    const mMean = mspec.reduce((a, b) => a + b, 0) / 8;
    lines.push(`Master spectrum (dB relative to its mean, peak-per-band so a balanced mix falls ~3 dB per octave): ${groups.map((g, i) => `${g} Hz ${(mspec[i] - mMean).toFixed(1)}`).join(', ')}.`);

    lines.push('Channels (only those playing; level = post-fader RMS dBFS, active % of time, GR = compressor gain reduction, ride = rider gain now):');
    for (const c of chans) {
      const i = c.n - 1;
      const active = frames.filter((f) => f.singing?.[i] ?? f.raw[i] > -55).length / n;
      if (active < 0.05 || c.mute) continue;
      const lvl = dbOf(avg((f) => pw(f.rms[i] + c.fader)));
      const gr = avg((f) => f.gr[i]);
      const ride = avg((f) => f.ride?.[i] ?? 0);
      const spec = Array.from({ length: 8 }, (_, g) => avg((f) => f.spec[i].slice(g * 4, g * 4 + 4).reduce((a, b) => a + b, 0) / 4));
      const sMean = spec.reduce((a, b) => a + b, 0) / 8;
      const held = ['fader', 'eq', 'comp', 'send', 'pan', 'mute', 'solo'].filter((k) => this.host.isHeld(`ch${c.n}.${k}`));
      const eq = (c.eq ?? []).map((b, k) => `${k}:${b.kind} ${Math.round(b.f)}Hz ${b.kind === 'hpf' || b.kind === 'lpf' ? '' : `${b.gain > 0 ? '+' : ''}${b.gain}dB Q${b.q}`}`.trim()).join('; ');
      const comp = c.comp ? `comp ${c.comp.thresh} dB ${c.comp.ratio}:1 ${c.comp.attack}/${c.comp.release} ms` : 'no comp';
      const sends = c.sends ? `sends plate ${c.sends.plate ?? 'off'}, room ${c.sends.room ?? 'off'}, delay ${c.sends.delay ?? 'off'}` : '';
      lines.push(`- ch${c.n} ${c.name}${c.role ? ` (${c.role})` : ''}: fader ${c.fader} dB (base ${BASE[c.n].fader}), level ${lvl.toFixed(1)}, active ${Math.round(active * 100)}%, GR ${gr.toFixed(1)}, ride ${ride.toFixed(1)}; EQ [${eq}]; ${comp}; ${sends}; spectrum rel. ${spec.map((v) => (v - sMean).toFixed(0)).join('/')}${held.length ? `; HELD BY HUMAN: ${held.join(', ')}` : ''}`);
    }
    const heard = this.host.listener?.summary();
    if (heard) lines.push(heard);
    const notes = loadPlaybook().mixNotes;
    if (notes.length) lines.push(`Notes learned from previous shows: ${notes.join(' | ')}`);
    if (this.history.length) lines.push(`Your recent changes (newest last): ${this.history.slice(-8).map((h) => `[${Math.round((Date.now() - h.t) / 1000)} s ago] ${h.text}`).join(' | ')}`);
    return lines.join('\n');
  }

  private async run(alert: string | null) {
    const prompt = this.report(alert);
    this.calls++;
    const res = await askClaude<Reply>(MIXER_SYSTEM, prompt, { timeoutMs: 120_000 });
    if (!res.ok || !res.data) {
      this.lastError = res.error ?? 'no answer';
      this.nextAt = Date.now() + 60_000;
      this.host.addFeed({ kind: 'MIX', text: 'Mixer check skipped: Claude did not answer in time.', why: this.lastError.slice(0, 140), confidence: 'guessing' });
      return;
    }
    const r = res.data;
    this.lastError = '';
    this.nextAt = Date.now() + clamp(Number(r.next_check_s) || 120, 60, 180) * 1000;
    this.host.state.thinking = { text: r.assessment || 'Mix sounds balanced.', heard: r.heard || 'band playing', confidence: 'likely' };
    const applied = (r.changes ?? []).slice(0, 5).map((c) => this.apply(c)).filter(Boolean);
    if (!applied.length) this.history.push({ t: Date.now(), text: `no change (${r.assessment})` });
    console.log(`mixer: ${res.ms} ms, ${applied.length}/${r.changes?.length ?? 0} changes applied (${CLAUDE_MODEL})`);
  }

  /** Clamp to bounds, skip held controls, apply, log with undo. Returns the feed text or null. */
  apply(c: Change): string | null {
    const { state, audio } = this.host;
    const ch: ChannelState | undefined = state.channels.find((x) => x.n === Number(c.ch));
    if (!ch || ch.mute) return null;
    const n = ch.n;
    const conf: Conf = c.confidence && ['sure', 'likely', 'guessing'].includes(c.confidence) ? c.confidence : 'likely';
    let text = '';
    let cmd: Record<string, unknown> | null = null;
    let undo: Record<string, unknown> | null = null;
    const pair = PIANO.has(n) ? (n === 6 ? 7 : 6) : null;

    if (c.action === 'fader') {
      if (this.host.isHeld(`ch${n}.fader`)) return null;
      const base = BASE[n].fader;
      const lo = LOCKED_FADERS.has(n) ? base - 1 : base - 12;
      const hi = LOCKED_FADERS.has(n) ? base + 1 : base + 6;
      let v = clamp(ch.fader + clamp(Number(c.value) - ch.fader, -1.5, 1.5), lo, hi);
      if (PIANO.has(n)) v = Math.max(v, -13);
      v = r1(v);
      if (Math.abs(v - ch.fader) < 0.2) return null;
      cmd = { type: 'fader', ch: n, db: v };
      undo = { type: 'fader', ch: n, db: ch.fader };
      text = `${ch.name} fader ${ch.fader} → ${v} dB`;
    } else if (c.action === 'eq') {
      if (this.host.isHeld(`ch${n}.eq`) || !ch.eq) return null;
      const i = Number(c.band);
      const b = ch.eq[i];
      if (!b || (NO_HPF.has(n) && b.kind === 'hpf')) return null;
      const base = ch.eqBase?.[i]?.gain ?? b.gain;
      const gain = c.gain === undefined || b.kind === 'hpf' || b.kind === 'lpf' ? b.gain : r1(clamp(b.gain + clamp(Number(c.gain) - b.gain, -1, 1), base - 6, base + 6));
      const f = c.f === undefined ? b.f : Math.round(clamp(Number(c.f), b.f / 1.26, b.f * 1.26));
      if (Math.abs(gain - b.gain) < 0.2 && Math.abs(f - b.f) < 1) return null;
      cmd = { type: 'eq', ch: n, band: i, gain, f };
      undo = { type: 'eq', ch: n, band: i, gain: b.gain, f: b.f };
      text = `${ch.name} EQ ${Math.round(f)} Hz ${gain > 0 ? '+' : ''}${gain} dB`;
    } else if (c.action === 'comp') {
      if (this.host.isHeld(`ch${n}.comp`) || !ch.comp) return null;
      const thresh = c.thresh === undefined ? ch.comp.thresh : r1(clamp(ch.comp.thresh + clamp(Number(c.thresh) - ch.comp.thresh, -2, 2), -40, 0));
      const ratio = c.ratio === undefined ? ch.comp.ratio : r1(clamp(ch.comp.ratio + clamp(Number(c.ratio) - ch.comp.ratio, -0.5, 0.5), 1.2, 10));
      if (Math.abs(thresh - ch.comp.thresh) < 0.2 && Math.abs(ratio - ch.comp.ratio) < 0.05) return null;
      cmd = { type: 'comp', ch: n, thresh, ratio };
      undo = { type: 'comp', ch: n, thresh: ch.comp.thresh, ratio: ch.comp.ratio };
      text = `${ch.name} compressor ${thresh} dB, ${ratio}:1`;
    } else if (c.action === 'send') {
      if (this.host.isHeld(`ch${n}.send`) || !ch.sends || !['plate', 'room', 'delay'].includes(c.fx)) return null;
      const cur = ch.sends[c.fx];
      let v: number | null = c.value === null ? null : Number(c.value);
      if (v !== null) v = r1(clamp((cur ?? -40) + clamp(v - (cur ?? -40), -2, 2), -40, 0));
      if (n === 9 && c.fx === 'plate' && v !== null) v = Math.max(v, -14);
      if (n === 9 && c.fx === 'plate' && v === null) return null;
      if (v === cur || (v !== null && cur !== null && Math.abs(v - cur) < 0.2)) return null;
      cmd = { type: 'send', ch: n, fx: c.fx, db: v };
      undo = { type: 'send', ch: n, fx: c.fx, db: cur };
      text = `${ch.name} ${c.fx} send ${v === null ? 'off' : `${v} dB`}`;
    } else if (c.action === 'rider') {
      if (this.host.isHeld(`ch${n}.fader`)) return null;
      const cur = audio.strips[String(n)] as unknown as { rider?: number | null } | undefined;
      if (cur?.rider === null || cur?.rider === undefined) return null;
      const v = r1(clamp(cur.rider + clamp(Number(c.value) - cur.rider, -1.5, 1.5), -3, 3));
      if (Math.abs(v - cur.rider) < 0.2) return null;
      cmd = { type: 'rider', ch: n, target: v };
      undo = { type: 'rider', ch: n, target: cur.rider };
      text = `${ch.name} rider ${v > 0 ? '+' : ''}${v} dB`;
    }
    if (!cmd || !undo) return null;
    audio.command(cmd);
    if (pair !== null && cmd.type !== 'rider') audio.command({ ...cmd, ch: pair }); // piano pair moves together
    this.host.aiTouched(n);
    const why = String(c.why ?? '').slice(0, 200);
    const u = undo;
    const holdKey = c.action === 'rider' ? 'fader' : c.action;
    this.host.addFeed({ kind: 'MIX', text: `${text}.`, why, confidence: conf }, () => {
      audio.command(u);
      if (pair !== null && u.type !== 'rider') audio.command({ ...u, ch: pair });
      this.host.hold(`ch${n}.${holdKey}`, n); // undo is a human decision: that control is now yours
    });
    this.history.push({ t: Date.now(), text: `${text} (${why})` });
    if (this.history.length > 30) this.history.shift();
    return text;
  }
}
