// Show memory and post-show learning.
//
// During a show every decision is appended to data/shows/<id>/log.jsonl (director cuts,
// mixer changes with reasons, human holds and cuts, undos, alerts, periodic loudness).
// After the show Claude reviews that log and proposes small, bounded changes to the
// director playbook and the starting mix. Accepted changes become playbook v(n+1), which
// the next show starts from; the Go Live screen shows the lessons.

import { appendFileSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { FastifyInstance } from 'fastify';
import { askClaude } from './claude.js';
import { DEFAULT_PLAYBOOK, type Playbook } from './director.js';

const DATA = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../data');
const SHOWS = path.join(DATA, 'shows');
const PLAYBOOK_FILE = path.join(DATA, 'playbook.json');

export interface Lesson { k: 'DIRECTOR' | 'MIX' | 'VERTICAL'; t: string }
export interface PlaybookFile { director: Playbook; lessons: Lesson[]; shows: number; mixNotes: string[]; history: { version: number; at: string; lessons: Lesson[] }[] }

export function loadPlaybook(): PlaybookFile {
  try { return JSON.parse(readFileSync(PLAYBOOK_FILE, 'utf8')) as PlaybookFile; } catch {
    return { director: { ...DEFAULT_PLAYBOOK }, lessons: [], shows: 0, mixNotes: [], history: [] };
  }
}
function savePlaybook(p: PlaybookFile) {
  mkdirSync(DATA, { recursive: true });
  writeFileSync(PLAYBOOK_FILE, JSON.stringify(p, null, 2));
}

export class ShowLog {
  private dir: string | null = null;
  id: string | null = null;

  start() {
    this.id = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    this.dir = path.join(SHOWS, this.id);
    mkdirSync(this.dir, { recursive: true });
    this.write({ type: 'start' });
  }

  write(e: Record<string, unknown>) {
    if (!this.dir) return;
    appendFileSync(path.join(this.dir, 'log.jsonl'), JSON.stringify({ t: Date.now(), ...e }) + '\n');
  }

  end() {
    this.write({ type: 'end' });
    const id = this.id;
    this.dir = null;
    this.id = null;
    return id;
  }
}

const REVIEW_SYSTEM = `You review a finished VibeNation live show (a funk/soul/R&B cover band streamed by an automatic director and mixer) to improve the next one.
The strongest signal is the HUMAN: every manual camera cut, every control a human took over, every undo of a Claude change means the automation did something the band didn't want. Also look at long shots, missed solos, loudness/limiter alerts and Claude's own mix changes that were later undone.
Propose only small, bounded changes (the next show tries them; one show is little evidence). Never mention any location.
Director playbook fields you may change (and their limits): minDwellS 3-8, maxWideS 6-20, maxShotS 10-30, soloLiftDb 3-10, holdDrumsInGrooveS 0-20, manualHoldS 4-20. Change at most 2 fields by small steps.
Answer JSON only: {"lessons": [{"k": "DIRECTOR"|"MIX"|"VERTICAL", "t": "<one plain sentence a musician understands, what changes next show and why>"}], "director": {<only the fields you change>: <new value>}, "mixNotes": ["<short note the mixer should remember next show, e.g. 'harmonica flagged harsh twice: start its 3.5 kHz cut 1 dB deeper'>"]}`;

const LIMITS: Record<keyof Omit<Playbook, 'version'>, [number, number]> = {
  minDwellS: [3, 8], maxWideS: [6, 20], maxShotS: [10, 30], soloLiftDb: [3, 10], holdDrumsInGrooveS: [0, 20], manualHoldS: [4, 20],
};

export async function reviewShow(id: string): Promise<{ ok: boolean; message: string }> {
  const file = path.join(SHOWS, id, 'log.jsonl');
  if (!existsSync(file)) return { ok: false, message: 'No log for that show.' };
  const events = readFileSync(file, 'utf8').trim().split('\n').map((l) => JSON.parse(l) as Record<string, unknown>);
  const count = (type: string) => events.filter((e) => e.type === type).length;
  const durMin = events.length > 1 ? Math.round(((events[events.length - 1].t as number) - (events[0].t as number)) / 60000) : 0;
  const summary = [
    `Show length ${durMin} min. Director cuts: ${count('cut')}. Human cuts: ${count('human_cut')}. Human holds: ${count('hold')}. Undos of Claude changes: ${count('undo')}. Claude mix changes: ${count('mix')}. Alerts: ${count('alert')}.`,
    'Events (chronological, trimmed):',
    ...events.filter((e) => e.type !== 'loudness').slice(-400).map((e) => `${new Date(e.t as number).toISOString().slice(11, 19)} ${e.type} ${JSON.stringify({ ...e, t: undefined, type: undefined })}`),
  ].join('\n');
  const pb = loadPlaybook();
  const r = await askClaude<{ lessons: Lesson[]; director: Partial<Playbook>; mixNotes: string[] }>(REVIEW_SYSTEM, `Current director playbook: ${JSON.stringify(pb.director)}\nPrevious mix notes: ${pb.mixNotes.join(' | ') || 'none'}\n\n${summary}`, { timeoutMs: 180_000 });
  if (!r.ok || !r.data) return { ok: false, message: `Review failed: ${r.error}` };
  const director = { ...pb.director };
  let changed = 0;
  for (const [k, v] of Object.entries(r.data.director ?? {})) {
    const lim = LIMITS[k as keyof typeof LIMITS];
    if (!lim || typeof v !== 'number' || changed >= 2) continue;
    const cur = director[k as keyof typeof LIMITS];
    const next = Math.min(lim[1], Math.max(lim[0], Math.max(cur - 4, Math.min(cur + 4, v))));
    if (next !== cur) { director[k as keyof typeof LIMITS] = next; changed++; }
  }
  director.version = pb.director.version + 1;
  const lessons = (r.data.lessons ?? []).slice(0, 6).map((l) => ({ k: l.k, t: String(l.t).slice(0, 240) }));
  const next: PlaybookFile = {
    director, lessons, shows: pb.shows + 1,
    mixNotes: [...(r.data.mixNotes ?? []).map((n) => String(n).slice(0, 200)), ...pb.mixNotes].slice(0, 12),
    history: [...pb.history, { version: director.version, at: new Date().toISOString(), lessons }].slice(-20),
  };
  savePlaybook(next);
  writeFileSync(path.join(SHOWS, id, 'review.json'), JSON.stringify(r.data, null, 2));
  return { ok: true, message: `Playbook v${director.version}: ${lessons.length} lessons, ${changed} director setting(s) changed.` };
}

export function registerLearning(app: FastifyInstance, onPlaybook: (p: PlaybookFile) => void) {
  app.get('/api/playbook', async () => loadPlaybook());
  app.get('/api/shows', async () => {
    if (!existsSync(SHOWS)) return { shows: [] };
    return { shows: readdirSync(SHOWS).sort().reverse().map((id) => ({ id, reviewed: existsSync(path.join(SHOWS, id, 'review.json')) })) };
  });
  app.post<{ Body: { id: string } }>('/api/shows/review', async (req, reply) => {
    const res = await reviewShow(String(req.body?.id ?? ''));
    if (res.ok) onPlaybook(loadPlaybook());
    return res.ok ? res : reply.code(400).send({ error: res.message });
  });
}
