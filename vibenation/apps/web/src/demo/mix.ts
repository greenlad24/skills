// Demo data for the Mix screen: EQ bands, effect settings, Claude change cards and
// spectrum shapes per section. Replaced by real DSP state in the audio milestone.

import { CHANNELS, type Section } from '@vibenation/shared';

export const SECTION_COLOR: Record<Section, string> = {
  drums: '#E08A5A', perc: '#D9A066', gtr: '#E6C07A', keys: '#9FC7A8', vox: '#F5EEE6', bass: '#8FA3D9', horn: '#E58FB0',
};

/** Mini EQ curves drawn over each strip's spectrum (viewBox 54×22). */
export const MINI_EQ = [
  'M0 16 C10 10 20 12 30 11 S45 9 54 10',
  'M0 14 C12 8 22 14 32 10 S46 8 54 9',
  'M0 18 C14 12 26 11 40 10 S50 9 54 8',
  'M0 12 C12 13 24 9 36 12 S48 10 54 10',
];

const SHAPE: Record<Section, number[]> = {
  drums: [0.95, 0.9, 0.7, 0.5, 0.45, 0.5, 0.55, 0.6, 0.55, 0.5, 0.45, 0.4, 0.35, 0.3],
  bass: [0.9, 1, 0.95, 0.8, 0.6, 0.4, 0.3, 0.22, 0.18, 0.14, 0.1, 0.08, 0.06, 0.05],
  keys: [0.3, 0.45, 0.65, 0.8, 0.85, 0.75, 0.6, 0.5, 0.4, 0.32, 0.25, 0.2, 0.15, 0.1],
  gtr: [0.1, 0.2, 0.4, 0.65, 0.8, 0.85, 0.75, 0.6, 0.5, 0.4, 0.3, 0.2, 0.12, 0.08],
  vox: [0.05, 0.12, 0.35, 0.6, 0.8, 0.85, 0.75, 0.7, 0.65, 0.55, 0.45, 0.4, 0.35, 0.25],
  horn: [0.05, 0.1, 0.25, 0.5, 0.75, 0.85, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.12],
  perc: [0.2, 0.35, 0.55, 0.7, 0.6, 0.55, 0.6, 0.65, 0.55, 0.45, 0.35, 0.3, 0.25, 0.2],
};

export interface SpecBar { h: string; d: string; dl: string }

const cache = new Map<string, SpecBar[]>();
/** Deterministic animated-bar heights/timings, cached so animations don't restart on re-render. */
export function specFor(kind: Section, n: number, seedBase: number): SpecBar[] {
  const key = `${kind}:${n}:${seedBase}`;
  const hit = cache.get(key);
  if (hit) return hit;
  let seed = 11 + seedBase * 37;
  const rnd = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
  const base = SHAPE[kind];
  const out: SpecBar[] = [];
  for (let i = 0; i < n; i++) {
    const v = base[Math.min(base.length - 1, Math.floor((i * base.length) / n))];
    out.push({ h: Math.round(Math.max(6, v * (70 + rnd() * 30))) + '%', d: (0.5 + rnd() * 0.9).toFixed(2) + 's', dl: (-rnd() * 1.4).toFixed(2) + 's' });
  }
  cache.set(key, out);
  return out;
}

// ---- EQ ----

export type BandType = 'HPF' | 'LOW' | 'BELL' | 'SHELF';
export interface Band { type: BandType; f: number; g: number; q: number }
export const BAND_COLOR = ['#E08A5A', '#E6C07A', '#B9A6FF', '#7FD1C3'];

type EqPreset = { a: Band[]; b: Band[] };
const hpf = (f: number): Band => ({ type: 'HPF', f, g: 0, q: 0.7 });
const bell = (f: number, g: number, q: number): Band => ({ type: 'BELL', f, g, q });
const shelf = (f: number, g: number): Band => ({ type: 'SHELF', f, g, q: 0.7 });

const EQ: Record<Section, EqPreset> = {
  vox: { a: [hpf(100), bell(250, -1, 1.5), bell(1500, 0, 1.1), shelf(10000, 2)], b: [hpf(100), bell(250, -2.5, 1.5), bell(1500, -1, 1.1), shelf(10000, 2)] },
  drums: { a: [hpf(40), bell(400, -2, 1.2), bell(3500, 1.5, 1), shelf(9000, 1)], b: [hpf(40), bell(400, -3.5, 1.4), bell(3500, 2, 1), shelf(9000, 1.5)] },
  perc: { a: [hpf(80), bell(300, -1, 1), bell(2500, 1, 1.2), shelf(8000, 1)], b: [hpf(80), bell(300, -2, 1), bell(2500, 1.5, 1.2), shelf(8000, 1)] },
  gtr: { a: [hpf(90), bell(300, -1.5, 1.2), bell(2500, 1, 1), shelf(7000, -1)], b: [hpf(90), bell(300, -2.5, 1.2), bell(2500, 1.5, 1), shelf(7000, -1.5)] },
  keys: { a: [hpf(60), bell(350, -1, 1), bell(2000, 0.5, 0.9), shelf(9000, 1)], b: [hpf(60), bell(350, -2, 1), bell(2000, 1, 0.9), shelf(9000, 1.5)] },
  bass: { a: [hpf(35), bell(90, 1.5, 1), bell(800, 1, 1.2), shelf(5000, -2)], b: [hpf(35), bell(90, 2, 1), bell(800, 1.5, 1.2), shelf(5000, -3)] },
  horn: { a: [hpf(120), bell(350, -1, 1.3), bell(3000, 0.5, 1), shelf(9000, 1.5)], b: [hpf(120), bell(350, -2, 1.3), bell(3000, 1, 1), shelf(9000, 2)] },
};

/** A (before Claude) and B (Claude's current) bands for a channel. Channels with the
 *  user's no-HPF rule get a low shelf on band 1 instead. */
export function eqFor(ch: number, section: Section): EqPreset {
  const p = EQ[section];
  const noHpf = CHANNELS.find((c) => c.n === ch)?.noHpf;
  const fix = (bands: Band[], g: number) => (noHpf ? [{ type: 'LOW' as const, f: 70, g, q: 0.7 }, ...bands.slice(1)] : bands.map((b) => ({ ...b })));
  return { a: fix(p.a, 1), b: fix(p.b, 1.5) };
}

// ---- Effects ----

export type MacroKey = 'comp' | 'verb' | 'delay' | 'warm' | 'pres' | 'width';
export const MACROS: { key: MacroKey; name: string; c: string }[] = [
  { key: 'comp', name: 'Compression', c: '#B9A6FF' },
  { key: 'verb', name: 'Reverb', c: '#E6C07A' },
  { key: 'delay', name: 'Delay', c: '#7FD1C3' },
  { key: 'warm', name: 'Warmth', c: '#E08A5A' },
  { key: 'pres', name: 'Presence', c: '#F5EEE6' },
  { key: 'width', name: 'Width', c: '#8FA3D9' },
];

const VERB_SUB: Record<Section, string> = {
  vox: 'Vocal plate · 1.5 s', drums: 'Room · 0.8 s', perc: 'Room · 0.9 s', gtr: 'Hall · 1.8 s', keys: 'Hall · 2.0 s', bass: 'Dry · off', horn: 'Plate · 1.4 s',
};
export const macroSub = (k: MacroKey, s: Section, bpm: number) => ({
  comp: 'Evens out the level · 3:1, 12 ms',
  verb: VERB_SUB[s],
  delay: `¼ note · ${bpm} BPM · ducked`,
  warm: 'Tape saturation',
  pres: 'Clarity & air · 2–10 kHz',
  width: 'Stereo spread · mono-safe',
})[k];

const EASY: Record<Section, Record<MacroKey, number>> = {
  vox: { comp: 45, verb: 35, delay: 20, warm: 25, pres: 55, width: 30 },
  drums: { comp: 55, verb: 15, delay: 0, warm: 30, pres: 40, width: 50 },
  perc: { comp: 30, verb: 25, delay: 0, warm: 20, pres: 35, width: 45 },
  gtr: { comp: 30, verb: 30, delay: 15, warm: 35, pres: 40, width: 40 },
  keys: { comp: 25, verb: 35, delay: 10, warm: 20, pres: 35, width: 60 },
  bass: { comp: 60, verb: 0, delay: 0, warm: 40, pres: 20, width: 0 },
  horn: { comp: 40, verb: 35, delay: 15, warm: 25, pres: 45, width: 25 },
};
export const easyFor = (s: Section) => ({ ...EASY[s] });

export type KnobKey = 'thresh' | 'ratio' | 'attack' | 'release' | 'plate' | 'delay';
export interface KnobDef { key: KnobKey; id: string; label: string; min: number; max: number; step: number; c: string; fmt: (v: number) => string }
const neg = (v: number) => (v < 0 ? '−' : '') + Math.abs(v);
export const KNOBS: KnobDef[] = [
  { key: 'thresh', id: 'comp.thresh', label: 'THRESH', min: -40, max: 0, step: 1, c: '#B9A6FF', fmt: (v) => `${neg(v)} dB` },
  { key: 'ratio', id: 'comp.ratio', label: 'RATIO', min: 1, max: 10, step: 0.5, c: '#B9A6FF', fmt: (v) => `${v}:1` },
  { key: 'attack', id: 'comp.attack', label: 'ATTACK', min: 1, max: 40, step: 1, c: '#B9A6FF', fmt: (v) => `${v} ms` },
  { key: 'release', id: 'comp.release', label: 'RELEASE', min: 20, max: 320, step: 10, c: '#B9A6FF', fmt: (v) => `${v} ms` },
  { key: 'plate', id: 'fx.plate', label: 'PLATE', min: -30, max: 0, step: 1, c: '#E6C07A', fmt: neg },
  { key: 'delay', id: 'fx.delay4', label: 'DELAY ¼', min: -30, max: 0, step: 1, c: '#7FD1C3', fmt: neg },
];
export const knobsFor = (s: Section): Record<KnobKey, number> =>
  s === 'drums' || s === 'bass'
    ? { thresh: -18, ratio: 4, attack: 8, release: 120, plate: -24, delay: -30 }
    : { thresh: -20, ratio: 3, attack: 12, release: 150, plate: -12, delay: -18 };

export const EXTRAS: Record<Section, [string, string][]> = {
  vox: [['DE-ESSER', '6.5 kHz · −3 dB'], ['SATURATION', 'tape · 18% mix'], ['GATE / EXP', 'off']],
  drums: [['TRANSIENT', 'attack +15%'], ['SATURATION', 'tape · 22% mix'], ['GATE / EXP', '−42 dB · 6 ms']],
  perc: [['TRANSIENT', 'attack +8%'], ['SATURATION', 'off'], ['GATE / EXP', 'off']],
  gtr: [['DE-ESSER', 'off'], ['SATURATION', 'amp · 12% mix'], ['GATE / EXP', 'off']],
  keys: [['DE-ESSER', 'off'], ['SATURATION', 'tape · 10% mix'], ['GATE / EXP', 'off']],
  bass: [['SUB', '55 Hz · +1 dB'], ['SATURATION', 'tube · 25% mix'], ['GATE / EXP', 'off']],
  horn: [['DE-ESSER', '7 kHz · −2 dB'], ['SATURATION', 'tape · 12% mix'], ['GATE / EXP', 'off']],
};

// ---- Claude's change cards ----

export interface ChangeCard { id: string; time: string; what: string; why: string; amount: number }
const CHANGES: Record<Section, Omit<ChangeCard, 'id'>[]> = {
  vox: [
    { time: '21:41:12', what: 'High-mid −1.0 dB at 1.5 kHz', why: 'Listener: “vocal edges a little sharp in the chorus.” Harshness 0.42 → 0.31.', amount: 100 },
    { time: '21:33:50', what: 'Compressor threshold −2 dB', why: 'Singer louder in the second set; level range 9 LU → 6 LU.', amount: 80 },
  ],
  drums: [{ time: '21:38:04', what: 'Low-mid −1.5 dB at 400 Hz', why: 'Boxy build-up when the full band plays; mud score 0.51 → 0.36.', amount: 100 }],
  perc: [{ time: '21:29:31', what: 'Presence +0.5 dB at 2.5 kHz', why: 'Congas getting lost under the horns in the bridge.', amount: 100 }],
  gtr: [{ time: '21:36:18', what: 'Low-mid −1.0 dB at 300 Hz', why: 'Guitar and piano fighting in the same range during verses.', amount: 100 }],
  keys: [{ time: '21:40:02', what: 'Fader +2 dB for the solo', why: 'Keys solo started; back down when the vocal returns.', amount: 100 }],
  bass: [{ time: '21:31:45', what: 'Sub +0.5 dB at 90 Hz', why: 'Low end thinner than the reference after the room filled up.', amount: 100 }],
  horn: [{ time: '21:34:27', what: 'Reverb send +3 dB', why: 'Solo section; more space behind the horn line.', amount: 100 }],
};
export const changesFor = (ch: number, s: Section): ChangeCard[] => CHANGES[s].map((c, i) => ({ ...c, id: `${ch}-${i}` }));
