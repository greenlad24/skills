// The director: picks the on-air camera from what the band is playing.
// Deterministic and fast (every 0.5 s). The main camera is the one whose name lists the lead
// singer (Vox C or Vox P) and it is held steady; the director cuts away only for an instrumental
// solo, to the camera whose name lists that instrument, and comes back when the solo ends
// (user, 24 Oct 2026). A manual cut is respected: the director waits out the hold, then carries on.

import type { CameraState, ShowState } from '@vibenation/shared';
import type { AudioLink } from './audio.js';
import { loadPlaybook } from './learning.js';

export type Subject = 'wide' | 'vocal' | 'keys' | 'drums' | 'guitar' | 'bass' | 'horns' | 'perc' | 'crowd';

/** Which channels make each subject "featured". */
const SUBJECT_CHANNELS: Record<Subject, number[]> = {
  vocal: [9, 10], keys: [6, 7], drums: [1, 2, 3], guitar: [4, 5, 8], bass: [12, 14], horns: [11, 15, 16], perc: [11, 13], wide: [], crowd: [],
};

export interface Playbook {
  version: number;
  minDwellS: number; // never cut sooner
  maxWideS: number; // cap on wide shots
  maxShotS: number; // cap on any shot unless a solo is still going
  soloLiftDb: number; // a channel this much above its own median while the vocal rests = solo
  holdDrumsInGrooveS: number; // keep the drum cam longer when kick+snare lock in
  manualHoldS: number; // after a human cut, wait this long before the director cuts again
}

export const DEFAULT_PLAYBOOK: Playbook = { version: 1, minDwellS: 4, maxWideS: 12, maxShotS: 16, soloLiftDb: 6, holdDrumsInGrooveS: 10, manualHoldS: 8 };

/** Which mixer channels a camera shows, read from its name. A name can list several people
 *  ("Piano, Gtr and Vox P", "Vox C, Drummer"); channel names from the mixer work too.
 *  "Wide", "stage", "band" or "front" = the whole band. */
const NAME_CHANNELS: [RegExp, number[]][] = [
  [/vox\s*c|vocal\s*c|centre|center/, [9]],
  [/vox\s*p|vocal\s*p/, [10]],
  [/piano|keys?\b|rhodes|organ/, [6, 7]],
  [/acoustic(\s*(gtr|guitar))?|ac\s*di|\bdi\s*1\b/g, [4]],
  [/(gtr|guitar)\s*di/g, [8]],
  [/gtr|guitar/g, [5]], // a plain "Gtr" / "Guitar" is the guitar amp
  [/drum|kit\b|kick|snare/, [1, 2, 3]],
  [/bass/, [12, 14]],
  [/sax|horn|trombone|trumpet|harmonica|flute|brass/, [11, 15, 16]],
  [/cong[ao]|perc/, [11, 13]], // "Congas" or "Congos"
];
export function channelsOf(c: CameraState): { wide: boolean; chans: Set<number> } {
  const n = c.name.toLowerCase();
  const chans = new Set<number>();
  // Most specific first; a matched phrase is used up, so "Acoustic guitar" isn't also the guitar amp.
  let rest = n;
  for (const [re, chs] of NAME_CHANNELS) {
    if (!rest.match(re)) continue;
    chs.forEach((x) => chans.add(x));
    rest = rest.replace(re, ' ');
  }
  if (!chans.has(9) && !chans.has(10) && /vocal|vox|sing|lead/.test(n)) { chans.add(9); chans.add(10); }
  const wide = /wide|stage|band|front|crowd|audience/.test(n) || chans.size === 0;
  return { wide, chans };
}
export function subjectOf(c: CameraState): Subject {
  const { wide, chans } = channelsOf(c);
  if (wide) return 'wide';
  for (const [subj, chs] of Object.entries(SUBJECT_CHANNELS) as [Subject, number[]][]) if (chs.some((x) => chans.has(x))) return subj;
  return 'wide';
}

// Floors so cuts feel like a human director, not a metronome.
const SETTLE_S = 2;        // a new lead singer or soloist must hold this long before it causes a cut
const MIN_DWELL_S = 8;     // never cut between singers sooner than this
const SOLO_MIN_S = 4;      // a solo shot lasts at least this long
// The main singer: the one who sang lead most over the last 30 s. The other singer takes the main
// camera only when they clearly own that window, so trading lines or a duet keeps the shot steady.
const LEAD_WINDOW_S = 30;
const LEAD_TAKEOVER = 0.65;

/** Guitars stand in for each other when no camera names the exact one: the two acoustic
 *  channels (4 acoustic DI, 8 guitar DI) first, then the guitar amp (5). */
const STAND_INS: Record<number, number[]> = { 4: [8, 5], 8: [4, 5], 5: [8, 4] };

export class Director {
  playbook: Playbook = loadPlaybook().director ?? { ...DEFAULT_PLAYBOOK };
  private lastCut = Date.now();
  private manualUntil = 0;
  private focus: { key: string; since: number } | null = null;
  private lead: number | null = null; // the main singer, kept while they rest between phrases
  private leads: number[] = [];       // who sang lead, one entry per tick while someone sings (LEAD_WINDOW_S)
  private onSolo = false; // the live shot is a solo shot
  reason = '';

  constructor(
    private state: () => ShowState,
    private audio: AudioLink,
    private cut: (cam: number, why: string, conf: 'sure' | 'likely' | 'guessing') => void,
  ) {
    setInterval(() => this.tick(), 500);
  }

  /** A human cut: hold it, then carry on from there. */
  manualCut() {
    this.lastCut = Date.now();
    this.manualUntil = Date.now() + this.playbook.manualHoldS * 1000;
    this.onSolo = false;
  }

  private tick() {
    const s = this.state();
    if (!s.onAir || s.slate) return;
    const cams = s.cams.filter((c) => c.connected && !c.error);
    if (cams.length < 2) return;
    const now = Date.now();
    const a = this.audio.history.at(-1)?.arrangement;
    if (a?.lead) {
      this.leads.push(a.lead);
      if (this.leads.length > LEAD_WINDOW_S * 2) this.leads.shift();
      const share = this.leads.filter((x) => x === a.lead).length / this.leads.length;
      if (this.lead === null || (a.lead !== this.lead && share >= LEAD_TAKEOVER)) this.lead = a.lead;
    }
    const solo = a?.feature ?? a?.solo ?? null;
    // Track what the shot should follow with a settle time, so a breath or a fill never causes a cut.
    const key = `${this.lead}/${solo}`;
    if (!this.focus || this.focus.key !== key) this.focus = { key, since: now };
    if (now < this.manualUntil) return;
    if ((now - this.focus.since) / 1000 < SETTLE_S) return;
    const held = (now - this.lastCut) / 1000;

    const info = new Map(cams.map((c) => [c.id, channelsOf(c)]));
    const live = cams.find((c) => c.id === s.liveCam);
    const covers = (c: CameraState | undefined, ch: number) => !!c && info.get(c.id)!.chans.has(ch);
    // The camera that shows a performer best: the fewest other people in its name.
    const best = (ch: number) => cams.filter((c) => covers(c, ch)).sort((x, y) => info.get(x.id)!.chans.size - info.get(y.id)!.chans.size)[0];
    const camFor = (ch: number) => best(ch) ?? (STAND_INS[ch] ?? []).map(best).find(Boolean);
    const name = (ch: number) => s.channels.find((c) => c.n === ch)?.name ?? `ch${ch}`;

    let target: CameraState | undefined;
    let why = '';
    if (solo !== null && camFor(solo)) {
      // A solo: film the soloist, unless the live camera already shows them.
      if (!covers(live, solo) && camFor(solo)!.id !== s.liveCam) {
        target = camFor(solo);
        why = `${name(solo)} solo`;
      }
    } else if (this.lead !== null && camFor(this.lead)) {
      // The main camera: the lead singer's. Back at once after a solo, otherwise not before the dwell.
      const main = camFor(this.lead)!;
      if (main.id !== s.liveCam && (this.onSolo ? held >= SOLO_MIN_S : held >= Math.max(MIN_DWELL_S, this.playbook.minDwellS))) {
        target = main;
        why = this.onSolo ? `solo over: back to ${name(this.lead)}` : `${name(this.lead)} singing lead`;
      }
    }
    if (target && target.id !== s.liveCam) {
      this.lastCut = now;
      this.onSolo = solo !== null;
      this.reason = why;
      this.cut(target.id, why, 'likely');
    }
  }
}
