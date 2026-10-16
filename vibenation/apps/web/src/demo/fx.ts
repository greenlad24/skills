// Demo data for the Effects rack: the four shared FX units every channel can send to.
// Knob values are real numbers; `fmt` turns them into display text. Control ids are
// `fx.<unit key>.<param>` (e.g. "fx.A.decay"), matching ShowState.held.

export interface KnobDef {
  param: string;
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  /** Display text. `bpm` is passed so tempo-synced knobs can show milliseconds. */
  fmt: (v: number, bpm: number) => string;
}

export interface FxUnitDef {
  key: string; // used in control ids: fx.<key>.<param>
  name: string;
  /** Subtitle; may depend on BPM (tempo-synced delay). */
  type: (bpm: number) => string;
  color: string;
  presets: string[];
  preset: string;
  /** Knob values a preset recalls (only knobs Claude still holds are moved). */
  presetValues: Record<string, Record<string, number>>;
  knobs: KnobDef[];
  sends: [string, string][];
  extra: string;
}

const sec = (v: number) => `${v.toFixed(1)} s`;
const ms = (v: number) => `${Math.round(v)} ms`;
const khz = (v: number) => `${v % 1 === 0 ? v.toFixed(0) : v.toFixed(1)} kHz`;
const pct = (v: number) => `${Math.round(v)}%`;
const hz = (v: number) => `${v.toFixed(1)} Hz`;

/** Delay note divisions, as multiples of a quarter note. Index is the TIME knob value. */
export const DELAY_DIVISIONS: [string, number][] = [
  ['⅛', 0.5],
  ['⅛ dotted', 0.75],
  ['¼', 1],
  ['¼ dotted', 1.5],
  ['½', 2],
];

/** Quarter-note length in ms at a given tempo. */
export const quarterMs = (bpm: number) => 60000 / Math.max(1, bpm);

export const FX_UNITS: FxUnitDef[] = [
  {
    key: 'A', name: 'Reverb A', type: () => 'Plate · for vocals and horns', color: '#E6C07A',
    presets: ['Vocal plate', 'Bright plate', 'Dark plate'], preset: 'Vocal plate',
    presetValues: {
      'Vocal plate': { decay: 1.5, predelay: 30, tone: 8 },
      'Bright plate': { decay: 1.8, predelay: 20, tone: 11 },
      'Dark plate': { decay: 2.2, predelay: 40, tone: 5 },
    },
    knobs: [
      { param: 'decay', label: 'DECAY', min: 0.3, max: 2.7, step: 0.1, value: 1.5, fmt: sec },
      { param: 'predelay', label: 'PRE-DELAY', min: 0, max: 100, step: 1, value: 30, fmt: ms },
      { param: 'tone', label: 'TONE', min: 2, max: 12, step: 0.5, value: 8, fmt: khz },
      { param: 'mix', label: 'MIX', min: 0, max: 100, step: 1, value: 100, fmt: pct },
    ],
    sends: [['Vocal centre', '−12'], ['Vocal piano', '−14'], ['Sax', '−15'], ['Harmonica', '−18']],
    extra: 'Ducks under the lead vocal · low cut 300 Hz',
  },
  {
    key: 'B', name: 'Reverb B', type: () => 'Room · for drums and percussion', color: '#E08A5A',
    presets: ['Drum room', 'Live room', 'Small club'], preset: 'Drum room',
    presetValues: {
      'Drum room': { decay: 0.8, predelay: 10, tone: 6 },
      'Live room': { decay: 1.2, predelay: 15, tone: 7 },
      'Small club': { decay: 0.6, predelay: 5, tone: 5 },
    },
    knobs: [
      { param: 'decay', label: 'DECAY', min: 0.2, max: 2.6, step: 0.1, value: 0.8, fmt: sec },
      { param: 'predelay', label: 'PRE-DELAY', min: 0, max: 80, step: 1, value: 10, fmt: ms },
      { param: 'tone', label: 'TONE', min: 2, max: 10, step: 0.5, value: 6, fmt: khz },
      { param: 'mix', label: 'MIX', min: 0, max: 100, step: 1, value: 100, fmt: pct },
    ],
    sends: [['Snare', '−16'], ['Kick', '−24'], ['Congas', '−18']],
    extra: 'Keeps drums dry and tight for funk · low cut 200 Hz',
  },
  {
    key: 'delay', name: 'Delay', type: (bpm) => `Tempo-synced · locked to ${Math.round(bpm)} BPM`, color: '#7FD1C3',
    presets: ['¼ note', '⅛ dotted', 'Slapback'], preset: '¼ note',
    presetValues: {
      '¼ note': { time: 2, feedback: 35, tone: 4 },
      '⅛ dotted': { time: 1, feedback: 40, tone: 4 },
      'Slapback': { time: 0, feedback: 5, tone: 6 },
    },
    knobs: [
      {
        param: 'time', label: 'TIME', min: 0, max: DELAY_DIVISIONS.length - 1, step: 1, value: 2,
        fmt: (v, bpm) => {
          const [name, mult] = DELAY_DIVISIONS[Math.round(v)] ?? DELAY_DIVISIONS[2];
          return `${name} · ${Math.round(quarterMs(bpm) * mult)} ms`;
        },
      },
      { param: 'feedback', label: 'FEEDBACK', min: 0, max: 100, step: 1, value: 35, fmt: pct },
      { param: 'tone', label: 'TONE', min: 1, max: 10, step: 0.5, value: 4, fmt: khz },
      { param: 'mix', label: 'MIX', min: 0, max: 100, step: 1, value: 100, fmt: pct },
    ],
    sends: [['Vocal centre', '−18'], ['Sax', '−20']],
    extra: 'Ducks under the vocal so echoes fill the gaps · low cut 400 Hz',
  },
  {
    key: 'doubler', name: 'Doubler / Chorus', type: () => 'Width for keys and guitar', color: '#8FA3D9',
    presets: ['Doubler', 'Rhodes chorus', 'Off'], preset: 'Doubler',
    presetValues: {
      'Doubler': { depth: 25, rate: 0.6, spread: 60, mix: 40 },
      'Rhodes chorus': { depth: 55, rate: 0.9, spread: 80, mix: 50 },
      'Off': { mix: 0 },
    },
    knobs: [
      { param: 'depth', label: 'DEPTH', min: 0, max: 100, step: 1, value: 25, fmt: pct },
      { param: 'rate', label: 'RATE', min: 0.1, max: 2, step: 0.1, value: 0.6, fmt: hz },
      { param: 'spread', label: 'SPREAD', min: 0, max: 100, step: 1, value: 60, fmt: pct },
      { param: 'mix', label: 'MIX', min: 0, max: 100, step: 1, value: 40, fmt: pct },
    ],
    sends: [['Piano L/R', '−10'], ['Guitar amp', '−16']],
    extra: 'Mono-safe: checked against phone speakers',
  },
];
