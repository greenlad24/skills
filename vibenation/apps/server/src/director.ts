// The director: picks the on-air camera from what the band is playing.
// Deterministic and fast (every 0.5 s): solos and the lead vocal pull the shot to that
// player's camera; otherwise it alternates vocal/feature shots with the wide, within
// dwell limits from the playbook. A manual cut is respected: the director waits out the
// dwell, then carries on from the shot the human picked. Claude reviews the rules and
// the camera roles every few minutes (see directorReview).

import type { CameraState, ShowState } from '@vibenation/shared';
import type { AudioLink } from './audio.js';

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

export class Director {
  playbook: Playbook = { ...DEFAULT_PLAYBOOK };
  private lastCut = Date.now();
  private manualUntil = 0;
  private medians: number[][] = Array.from({ length: 16 }, () => []);
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

  private featured(): { subject: Subject; why: string } | null {
    const frames = this.audio.history.slice(-20); // last 2 s
    if (frames.length < 10) return null;
    const lvl = (ch: number) => frames.reduce((s, f) => s + f.rms[ch - 1], 0) / frames.length;
    const playing = (ch: number) => frames.filter((f) => f.singing?.[ch - 1]).length > frames.length * 0.6;
    for (let ch = 1; ch <= 16; ch++) {
      const m = this.medians[ch - 1];
      if (playing(ch)) { m.push(lvl(ch)); if (m.length > 600) m.shift(); }
    }
    const median = (ch: number) => { const m = [...this.medians[ch - 1]].sort((a, b) => a - b); return m.length > 20 ? m[m.length >> 1] : null; };
    const vocalOn = playing(9) || playing(10);
    // Solo: an instrument well above its own usual level while the vocal rests.
    if (!vocalOn) {
      let best: { subject: Subject; lift: number } | null = null;
      for (const subject of ['keys', 'guitar', 'horns', 'bass', 'perc'] as Subject[]) {
        for (const ch of SUBJECT_CHANNELS[subject]) {
          const med = median(ch);
          if (med === null || !playing(ch)) continue;
          const lift = lvl(ch) - med;
          if (lift >= this.playbook.soloLiftDb && (!best || lift > best.lift)) best = { subject, lift };
        }
      }
      if (best) return { subject: best.subject, why: `${best.subject} solo — ${best.lift.toFixed(0)} dB above its usual level, vocal resting` };
    }
    if (vocalOn) return { subject: 'vocal', why: 'lead vocal singing' };
    const groove = playing(1) && playing(2);
    if (groove) return { subject: 'drums', why: 'kick and snare locked in, no vocal' };
    return null;
  }

  private tick() {
    const s = this.state();
    if (!s.onAir || s.slate) return;
    const cams = s.cams.filter((c) => c.connected && !c.error);
    if (cams.length < 2) return;
    const now = Date.now();
    if (now < this.manualUntil) return;
    const held = (now - this.lastCut) / 1000;
    if (held < this.playbook.minDwellS) return;
    const live = cams.find((c) => c.id === s.liveCam);
    const liveSubject = live ? subjectOf(live) : 'wide';
    const f = this.featured();
    const camFor = (subj: Subject) => cams.find((c) => subjectOf(c) === subj);
    const wide = camFor('wide');

    let target: CameraState | undefined;
    let why = '';
    if (f && camFor(f.subject) && liveSubject !== f.subject) {
      target = camFor(f.subject);
      why = f.why;
    } else if (liveSubject === 'wide' && held > this.playbook.maxWideS) {
      target = (f && camFor(f.subject)) || cams.find((c) => subjectOf(c) !== 'wide' && subjectOf(c) !== 'crowd');
      why = `wide held ${Math.round(held)} s (cap ${this.playbook.maxWideS} s)`;
    } else if (liveSubject !== 'wide' && held > this.playbook.maxShotS + (liveSubject === 'drums' ? this.playbook.holdDrumsInGrooveS : 0) && (!f || f.subject !== liveSubject)) {
      target = wide ?? cams.find((c) => c.id !== s.liveCam);
      why = `${liveSubject} shot held ${Math.round(held)} s; ${wide ? 'back to the wide' : 'changing angle'}`;
    }
    if (target && target.id !== s.liveCam) {
      this.lastCut = now;
      this.reason = why;
      this.cut(target.id, why, f ? 'likely' : 'sure');
    }
  }
}
