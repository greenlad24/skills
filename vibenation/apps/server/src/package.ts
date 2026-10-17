// Claude writes the per-platform stream package: ranked titles, SEO description with
// chapters, and tags. Hard rules are checked in code after Claude answers.

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { FastifyInstance } from 'fastify';
import { askClaude } from './claude.js';

const PKG_FILE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../data/package.json');
export function loadPackage(): StreamPackage | null {
  try { return JSON.parse(readFileSync(PKG_FILE, 'utf8')) as StreamPackage; } catch { return null; }
}
export function savePackage(p: StreamPackage) {
  mkdirSync(path.dirname(PKG_FILE), { recursive: true });
  writeFileSync(PKG_FILE, JSON.stringify(p, null, 2));
}

export interface StreamPackage {
  titles: string[]; // ranked, best first
  description: string;
  tags: string[];
  platforms: { twitch: string; facebook: string; tiktok: string; instagram: string };
  thumbnailText: string;
  createdAt: number;
}

const SYSTEM = `You write the YouTube live-stream package for "MusicLiveLove" (one word; @MusicLiveLove), a live funk, soul and R&B cover band: real musicians, no AI, re-arranging songs live.
Channel title style: "LIVE: Funk & Soul Cover Band — <hook> | Real Musicians (Not AI)"; single songs: "Song – Artist | Live <Genre> Cover Band Arrangement (Not AI)".
Hard rules: never mention any location (no city, country, island, venue or region names); never mention "Sunrise Jam"; no community/Skool links; the only link is the subscribe link https://youtube.com/@MusicLiveLove. No hashtags inside titles. Titles ≤ 100 characters and click-optimised but honest.
Answer JSON only: {"titles": [5 ranked titles], "description": "<SEO description: 2 short paragraphs with keywords (live funk band, soul covers, R&B, live music stream, real musicians), the line-up if given, a 'Chapters' block starting '00:00 Starting soon' (song chapters are added live), and the subscribe link>", "tags": [15-25 tags], "platforms": {"twitch": "<Twitch title ≤140 chars>", "facebook": "<Facebook post text, 1-2 sentences>", "tiktok": "<TikTok LIVE title ≤32 chars>", "instagram": "<Instagram caption, 1 sentence>"}, "thumbnailText": "<2-4 punchy words for the thumbnail>"}`;

const LOCATION_WORDS = /\b(thailand|samui|koh|island|phuket|bangkok|beach bar)\b/i;
const clean = (s: string) => s.replace(/https?:\/\/(?!youtube\.com\/@MusicLiveLove)\S+/gi, '').replace(/\bskool\b/gi, '').replace(/sunrise jam/gi, '').trim();

export function checkPackage(p: StreamPackage): string[] {
  const problems: string[] = [];
  const all = [...p.titles, p.description, ...p.tags, ...Object.values(p.platforms), p.thumbnailText].join('\n');
  if (LOCATION_WORDS.test(all)) problems.push('mentions a location');
  if (/sunrise jam/i.test(all)) problems.push('mentions Sunrise Jam');
  if (/skool/i.test(all)) problems.push('mentions Skool');
  return problems;
}

export async function writePackage(info: { lineup?: string; songs?: string[]; mood?: string }): Promise<StreamPackage> {
  const prompt = `Tonight's show.\nLine-up: ${info.lineup || 'not given (keep generic: vocals, keys, guitar, bass, drums, horns)'}\nSongs planned/played so far: ${info.songs?.join('; ') || 'not given'}\nMood: ${info.mood || 'feel-good Friday funk & soul'}\nWrite the package.`;
  for (let attempt = 0; attempt < 2; attempt++) {
    const r = await askClaude<StreamPackage>(SYSTEM, prompt, { timeoutMs: 120_000 });
    if (!r.ok || !r.data) continue;
    const p: StreamPackage = {
      titles: (r.data.titles ?? []).map((t) => clean(t).slice(0, 100)).filter(Boolean).slice(0, 5),
      description: clean(r.data.description ?? ''),
      tags: (r.data.tags ?? []).map((t) => clean(t)).filter(Boolean).slice(0, 25),
      platforms: {
        twitch: clean(r.data.platforms?.twitch ?? '').slice(0, 140),
        facebook: clean(r.data.platforms?.facebook ?? ''),
        tiktok: clean(r.data.platforms?.tiktok ?? '').slice(0, 32),
        instagram: clean(r.data.platforms?.instagram ?? ''),
      },
      thumbnailText: clean(r.data.thumbnailText ?? 'LIVE FUNK & SOUL'),
      createdAt: Date.now(),
    };
    if (!p.description.includes('youtube.com/@MusicLiveLove')) p.description += '\n\nSubscribe: https://youtube.com/@MusicLiveLove';
    if (p.titles.length && !checkPackage(p).length) return p;
  }
  throw new Error('Claude could not write a package that passes the rules; try again.');
}

export function registerPackage(app: FastifyInstance, store = { get: loadPackage, set: savePackage }) {
  app.get('/api/package', async () => ({ package: store.get() }));
  app.post<{ Body: { lineup?: string; songs?: string[]; mood?: string } }>('/api/package/generate', async (req, reply) => {
    try {
      const p = await writePackage(req.body ?? {});
      store.set(p);
      return { package: p };
    } catch (e) {
      return reply.code(502).send({ error: (e as Error).message });
    }
  });
  app.put<{ Body: StreamPackage }>('/api/package', async (req, reply) => {
    const p = { ...req.body, createdAt: Date.now() };
    const problems = checkPackage(p);
    if (problems.length) return reply.code(400).send({ error: `Not saved: it ${problems.join(', ')}.` });
    store.set(p);
    return { package: p };
  });
}
