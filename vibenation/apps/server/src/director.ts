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

/** Guess a camera's subject from its name ("Lead vocal", "Keys", "Drums", "Wide stage", "Crowd"). */
export function subjectOf(c: CameraState): Subject {
  const n = c.name.toLowerCase();
  if (/wide|stage|band|front/.test(n)) return 'wide';
  if (/vocal|vox|sing|lead/.test(n)) return 'vocal';
  if (/key|piano|rhodes|organ/.test(n)) return 'keys';
  if (/drum|kit/.test(n)) return 'drums';
  if (/guitar|gtr/.test(n)) return 'guitar';
  if (/bass/.test(n)) return 'bass';
  if (/sax|horn|trombone|trumpet|harmonica|flute/.test(n)) return 'horns';
  if (/conga|perc/.test(n)) return 'perc';
  if (/crowd|audience|room/.test(n)) return 'crowd';
  return 'wide';
}

/** Which subject a soloing channel belongs to (the engine names the channel). */
const SUBJECT_OF_CH: Record<number, Subject> = Object.fromEntries(
  (Object.entries(SUBJECT_CHANNELS) as [Subject, number[]][]).flatMap(([subj, chs]) => chs.map((ch) => [ch, subj])),
) as Record<number, Subject>;

// Floors so cuts feel like a human director following the performer, not a metronome.
const MIN_DWELL_S = 8;     // never cut sooner (playbook may ask for longer)
const SETTLE_S = 2;        // a new focus must hold this long before it causes a cut
const SINGER_MAX_S = 25;   // then one breather on the wide...
const BREATHER_S = 8;      // ...for this long, then back to the singer if still singing

export class Director {
  playbook: Playbook = loadPlaybook().director ?? { ...DEFAULT_PLAYBOOK };
  private lastCut = Date.now();
  private manualUntil = 0;
  private focus: { subject: Subject; since: number; why: string } | null = null;
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
  private performer(): { subject: Subject; why: string } {
    const a = this.audio.history.at(-1)?.arrangement;
    if (a?.solo) return { subject: SUBJECT_OF_CH[a.solo] ?? 'wide', why: `solo on ch${a.solo}` };
    if (a?.lead) return { subject: 'vocal', why: 'lead vocal singing' };
    return { subject: 'wide', why: 'band playing, vocal resting' };
  }

  private tick() {
    const s = this.state();
    if (!s.onAir || s.slate) return;
    const cams = s.cams.filter((c) => c.connected && !c.error);
    if (cams.length < 2) return;
    const now = Date.now();
    // Track the performer with a settle time, so a breath or a fill never causes a cut.
    const p = this.performer();
    if (!this.focus || this.focus.subject !== p.subject) this.focus = { ...p, since: now };
    const settled = (now - this.focus.since) / 1000 >= SETTLE_S;
    if (now < this.manualUntil) return;
    const held = (now - this.lastCut) / 1000;
    if (held < Math.max(MIN_DWELL_S, this.playbook.minDwellS)) return;
    const live = cams.find((c) => c.id === s.liveCam);
    const liveSubject = live ? subjectOf(live) : 'wide';
    const camFor = (subj: Subject) => cams.find((c) => subjectOf(c) === subj);
    const wide = camFor('wide') ?? cams.find((c) => subjectOf(c) !== 'vocal');
    const want = settled ? this.focus.subject : liveSubject;

    let target: CameraState | undefined;
    let why = '';
    if (want !== liveSubject && camFor(want)) {
      // Follow the performer (solo player, singer, or back to the band).
      target = camFor(want);
      why = this.focus.why;
    } else if (want === 'vocal' && liveSubject === 'vocal' && held > SINGER_MAX_S && wide && wide.id !== s.liveCam) {
      target = wide;
      why = `singer held ${Math.round(held)} s: a breather on the band`;
    } else if (want === 'vocal' && liveSubject !== 'vocal' && held > BREATHER_S && camFor('vocal')) {
      target = camFor('vocal');
      why = 'back to the singer';
    } else if (want === 'wide' && liveSubject === 'wide' && held > Math.max(this.playbook.maxWideS, 15)) {
      // Long instrumental: show a featured player now and then, if there's a camera for one.
      const feature = cams.find((c) => !['wide', 'vocal', 'crowd'].includes(subjectOf(c)));
      if (feature) { target = feature; why = `instrumental: featuring ${subjectOf(feature)}`; }
    } else if (want === 'wide' && liveSubject !== 'wide' && liveSubject !== this.focus.subject && held > this.playbook.maxShotS && wide) {
      target = wide;
      why = 'back to the band';
    }
    if (target && target.id !== s.liveCam) {
      this.lastCut = now;
      this.reason = why;
      this.cut(target.id, why, settled ? 'likely' : 'guessing');
    }
  }
}
