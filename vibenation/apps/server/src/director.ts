// The director: picks the on-air camera from what the band is playing.
// Deterministic and fast (every 0.5 s): solos and the lead vocal pull the shot to that
// player's camera; otherwise it alternates vocal/feature shots with the wide, within
// dwell limits from the playbook. A manual cut is respected: the director waits out the
// dwell, then carries on from the shot the human picked. Claude reviews the rules and
// the camera roles every few minutes (see directorReview).

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
  [/gtr|guitar/, [4, 5, 8]],
  [/drum|kit\b|kick|snare/, [1, 2, 3]],
  [/bass/, [12, 14]],
  [/sax|horn|trombone|trumpet|harmonica|flute|brass/, [11, 15, 16]],
  [/conga|perc/, [11, 13]],
];
export function channelsOf(c: CameraState): { wide: boolean; chans: Set<number> } {
  const n = c.name.toLowerCase();
  const chans = new Set<number>();
  for (const [re, chs] of NAME_CHANNELS) if (re.test(n)) chs.forEach((x) => chans.add(x));
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

// Floors so cuts feel like a human director following the performer, not a metronome.
const MIN_DWELL_S = 8;     // never cut sooner (playbook may ask for longer)
const SETTLE_S = 2;        // a new focus must hold this long before it causes a cut
// The lead singer (Vox C, Vox P, or Congas 1 when it's a voice) is on screen 80-90 % of the song (user, 19 Oct 2026):
// ~34 s on the singer's camera, then a ~6 s breather on the band, then back = 85 %.
const SINGER_MAX_S = 34;   // solos are held up to 60 s
const BREATHER_S = 6;      // a breather away from the singer is this short

export class Director {
  playbook: Playbook = loadPlaybook().director ?? { ...DEFAULT_PLAYBOOK };
  private lastCut = Date.now();
  private manualUntil = 0;
  private focus: { key: string; ch: number | null; since: number; why: string } | null = null;
  private stable: number | null = null; // the last confirmed performer
  private breather = false; // the live shot is a short breather away from the singer
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
  }

  /** Who is performing now, from the audio engine's arrangement follower (the same decisions
   *  the mix uses): a solo, else the lead vocal (pauses between phrases count as singing), else the band. */
  private performer(): { ch: number | null; why: string } {
    const a = this.audio.history.at(-1)?.arrangement;
    if (a?.solo) return { ch: a.solo, why: `solo on ch${a.solo}` };
    if (a?.lead) return { ch: a.lead, why: `ch${a.lead} singing lead` };
    return { ch: null, why: 'band playing, vocal resting' };
  }

  private tick() {
    const s = this.state();
    if (!s.onAir || s.slate) return;
    const cams = s.cams.filter((c) => c.connected && !c.error);
    if (cams.length < 2) return;
    const now = Date.now();
    // Track the performer with a settle time, so a breath or a fill never causes a cut.
    const p = this.performer();
    const key = String(p.ch);
    if (!this.focus || this.focus.key !== key) this.focus = { key, ch: p.ch, since: now, why: p.why };
    if (now < this.manualUntil) return;
    const settled = (now - this.focus.since) / 1000 >= SETTLE_S;
    const held = (now - this.lastCut) / 1000;
    if (held < (this.breather ? BREATHER_S : Math.max(MIN_DWELL_S, this.playbook.minDwellS))) return;
    const info = new Map(cams.map((c) => [c.id, channelsOf(c)]));
    const live = cams.find((c) => c.id === s.liveCam);
    const covers = (c: CameraState | undefined, ch: number) => !!c && info.get(c.id)!.chans.has(ch);
    // The camera that shows a performer best: the fewest other people in its name.
    const camFor = (ch: number) => cams.filter((c) => covers(c, ch)).sort((a, b) => info.get(a.id)!.chans.size - info.get(b.id)!.chans.size)[0];
    const wideCam = cams.find((c) => info.get(c.id)!.wide);
    const other = cams.find((c) => c.id !== s.liveCam);
    if (settled) this.stable = this.focus.ch;
    if (!settled) return; // a performer change is being confirmed: hold the shot
    const want = this.stable;

    let target: CameraState | undefined;
    let why = '';
    let breather = false;
    if (want !== null && !covers(live, want) && camFor(want)) {
      target = camFor(want);
      why = this.focus.why;
    } else if (want !== null && covers(live, want) && held > (this.focus.why.startsWith('solo') ? 60 : SINGER_MAX_S)) {
      target = wideCam && wideCam.id !== s.liveCam ? wideCam : other;
      why = `held ${Math.round(held)} s on the performer: a breather on the band`;
      breather = !this.focus.why.startsWith('solo');
    } else if (want === null && held > Math.max(this.playbook.maxWideS, 15)) {
      target = wideCam && wideCam.id !== s.liveCam && !info.get(s.liveCam)?.wide ? wideCam : other;
      why = 'instrumental: changing angle';
    }
    if (target && target.id !== s.liveCam) {
      this.lastCut = now;
      this.breather = breather;
      this.reason = why;
      this.cut(target.id, why, settled ? 'likely' : 'guessing');
    }
  }
}
