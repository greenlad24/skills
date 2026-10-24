// Pre-flight checks, destination keys and the go-live / end sequence.
//
// Go live: YouTube broadcast (bound to a scheduled one if there is one, else created
// with Claude's package) -> start the video service outputs (YouTube 9 Mbps, Twitch /
// Facebook 6 Mbps, TikTok / Instagram vertical) -> "Starting soon" slate -> the director
// takes over. Every step is logged in the sidebar; a failure stops the sequence and says why.

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { FastifyInstance } from 'fastify';
import type { FeedItem, Platform, PreflightCheck, ShowState } from '@vibenation/shared';
import type { AudioLink } from './audio.js';
import { LATENCY, youtube } from './youtube.js';
import type { StreamPackage } from './package.js';

const DATA = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../data');
const KEYS_FILE = path.join(DATA, 'secrets', 'stream-keys.json');
const VIDEO = process.env.VN_VIDEO_URL ?? 'http://127.0.0.1:8092';

type Keys = Partial<Record<Platform, { url: string; key: string }>>;
const DEFAULT_URL: Partial<Record<Platform, string>> = {
  TT: 'rtmp://push.tiktok.com/live/', // the real TikTok ingest URL comes with the key; editable
  IG: 'rtmps://live-upload.instagram.com:443/rtmp/',
  TW: 'rtmp://live.twitch.tv/app/',
  FB: 'rtmps://live-api-s.facebook.com:443/rtmp/',
};

function loadKeys(): Keys {
  try { return JSON.parse(readFileSync(KEYS_FILE, 'utf8')) as Keys; } catch { return {}; }
}
function saveKeys(k: Keys) {
  mkdirSync(path.dirname(KEYS_FILE), { recursive: true, mode: 0o700 });
  writeFileSync(KEYS_FILE, JSON.stringify(k), { mode: 0o600 });
}

async function video<T>(method: string, p: string, body?: unknown): Promise<T> {
  const r = await fetch(VIDEO + p, { method, headers: body ? { 'content-type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(8000) });
  if (!r.ok) throw new Error(`video service ${p}: ${r.status} ${(await r.text()).slice(0, 200)}`);
  return (await r.json()) as T;
}

export interface GoLiveHost {
  state: ShowState;
  audio: AudioLink;
  addFeed(f: Omit<FeedItem, 'id' | 't'>): void;
  push(): void;
  pkg(): StreamPackage | null;
  startShow(): void; // clears holds, sets onAir + liveSince
}

export class GoLive {
  private videoUp = false;

  constructor(private h: GoLiveHost) {
    setInterval(() => void this.refresh(), 2000);
  }

  private async refresh() {
    try { await video('GET', '/state'); this.videoUp = true; } catch { this.videoUp = false; }
    const s = this.h.state;
    s.youtube = { configured: youtube.configured(), connected: youtube.connected(), channel: youtube.channel()?.title ?? null };
    const keys = loadKeys();
    s.ready = { YT: s.youtube.connected, TW: !!keys.TW, FB: !!keys.FB, TT: !!keys.TT, IG: !!keys.IG };
    s.preflight = this.checks();
    this.h.push();
  }

  checks(): PreflightCheck[] {
    const s = this.h.state;
    const a = s.audio;
    const out: PreflightCheck[] = [];
    const add = (id: string, title: string, detail: string, meta: string, level: PreflightCheck['level']) => out.push({ id, title, detail, meta, level });

    if (!a) add('audio', 'Mixer audio link', 'The mix engine is not running', 'offline', 'error');
    else add('audio', 'Mixer audio link', a.source === 'recording' ? `Test recording (${a.set ?? ''}) standing in for the venue feed` : '16 channels from the mixer, raw preamp tap, 48 kHz',
      a.playing ? 'flowing' : 'paused', a.playing ? 'ok' : 'warn');

    const real = s.cams.filter((c) => c.identity);
    const live = real.filter((c) => c.connected);
    if (!real.length) add('cams', 'Cameras', 'No phones joined yet — use + Add phone on the Show screen', '0', 'warn');
    else add('cams', 'Cameras', `${live.length} of ${real.length} phones connected in landscape`, `${live.length} / ${real.length}`, live.length === real.length && live.length > 0 ? 'ok' : 'warn');

    if (live.length) {
      const unlocked = live.filter((c) => !c.locked);
      add('locks', 'White balance & exposure', unlocked.length ? `Not locked on ${unlocked.map((c) => c.num).join(', ')} (phone doesn't allow it, or still settling)` : 'Locked per camera for this stream',
        unlocked.length ? `${unlocked.length} unlocked` : 'locked', unlocked.length ? 'warn' : 'ok');
      const low = live.filter((c) => c.battery < 50 && !c.charging);
      add('power', 'Camera power', low.length ? `${low.map((c) => `${c.num} at ${c.battery}%`).join(', ')} — plug in` : 'All phones charging or above 50%', low.length ? low.map((c) => `${c.num} ${c.battery}%`).join(' · ') : 'ok', low.length ? 'warn' : 'ok');
      const slow = live.filter((c) => (c.fps ?? 60) < 25); // the show runs 1080p30
      if (slow.length) add('fps', 'Camera frame rate', `${slow.map((c) => `${c.num} ${Math.round(c.fps ?? 0)} fps`).join(', ')} — check Wi-Fi and heat`, `${slow.length} slow`, 'warn');
    }

    if (a) {
      add('mix', 'Mix loaded', a.calibrating ? 'Soundcheck calibration still running (first minutes of playing)' : 'Calibrated mix + learned settings', a.calibrating ? 'calibrating' : 'ready', a.calibrating ? 'warn' : 'ok');
      const m = s.master;
      const okLoud = a.playing && m.lufsI > -18 && m.lufsI < -14;
      add('loud', 'Loudness', 'Stream master target −16 LUFS, peaks ≤ −1 dBTP', a.playing ? `${m.lufsI.toFixed(1)} LUFS` : '—', okLoud || !a.playing ? 'ok' : 'warn');
    }

    if (!s.youtube.configured) add('yt', 'YouTube', 'Needs the Google client keys on the server (docs/ACCOUNTS-TO-CONNECT.md)', 'not set up', 'warn');
    else if (!s.youtube.connected) add('yt', 'YouTube', 'Tap Connect YouTube below to link @MusicLiveLove', 'not connected', 'warn');
    else add('yt', 'YouTube', `Connected to ${s.youtube.channel ?? 'the channel'}`, 'connected', 'ok');

    add('pkg', 'Title, description & thumbnail', this.h.pkg() ? 'Written by Claude; attached when you go live' : 'Claude writes them when you tap Write it', this.h.pkg() ? 'ready' : 'not written', this.h.pkg() ? 'ok' : 'warn');

    const anyDest = (Object.keys(s.destinations) as Platform[]).some((p) => s.destinations[p] && s.ready[p]);
    add('video', 'Video encoder', this.videoUp ? 'Program output ready (GPU show server)' : 'The video encoder is not running — start the show server', this.videoUp ? 'ready' : 'offline', this.videoUp ? 'ok' : 'error');
    add('dest', 'Destinations', anyDest ? 'At least one platform connected and switched on' : 'Connect and switch on at least one platform', anyDest ? 'ok' : 'none', anyDest ? 'ok' : 'error');
    return out;
  }

  async start(privacy: 'public' | 'unlisted' | 'private' = 'public') {
    const s = this.h.state;
    if (s.golive.phase === 'starting' || s.onAir) return;
    const blockers = this.checks().filter((c) => c.level === 'error');
    if (blockers.length) {
      s.golive = { phase: 'error', message: `Can't go live: ${blockers.map((b) => b.title.toLowerCase()).join(', ')}.` };
      this.h.addFeed({ kind: 'SHOW', text: s.golive.message! });
      this.h.push();
      return;
    }
    s.golive = { phase: 'starting', message: 'Setting up the broadcast…', privacy };
    this.h.push();
    try {
      const dests: { name: string; url: string; key: string; profile: string }[] = [];
      const keys = loadKeys();
      if (s.destinations.YT && s.ready.YT) {
        const pkg = this.h.pkg();
        // Never reuse a broadcast whose title breaks the hard rules (old name, any location).
        const scheduled = (await youtube.upcoming()).find((b) => b.scheduledStart && Math.abs(Date.parse(b.scheduledStart) - Date.now()) < 2 * 3600_000 && !/sunrise\s*jam|thailand|samui|island/i.test(b.title));
        const b = scheduled ? await youtube.bind(scheduled.id)
          : await youtube.create({ title: pkg?.titles[0] ?? 'LIVE: Funk & Soul Cover Band | Real Musicians (Not AI)', description: pkg?.description ?? 'Subscribe: https://youtube.com/@MusicLiveLove', privacy, tags: pkg?.tags });
        if (!b.ingest) throw new Error('YouTube did not return a stream key.');
        s.golive.broadcastId = b.id;
        const latency = await youtube.latency(b.id).catch(() => 'unknown');
        if (latency !== LATENCY) this.h.addFeed({ kind: 'EMERGENCY', text: `YouTube broadcast is on ${latency} latency, not normal: viewers may hear the sound stutter.`, why: 'Set it to Normal latency in YouTube Studio before the next show.' });
        dests.push({ name: 'YouTube', url: b.ingest.url, key: b.ingest.key, profile: '16x9-9M' });
        this.h.addFeed({ kind: 'SHOW', text: scheduled ? `Bound to your scheduled YouTube broadcast "${b.title}".` : `Created the YouTube broadcast "${b.title}" (${privacy}).` });
      }
      for (const [p, name, profile] of [['TW', 'Twitch', '16x9-6M'], ['FB', 'Facebook', '16x9-6M'], ['TT', 'TikTok', '9x16'], ['IG', 'Instagram', '9x16']] as const) {
        const k = keys[p];
        if (s.destinations[p] && k) dests.push({ name, url: k.url, key: k.key, profile });
      }
      if (!dests.length) throw new Error('No destination is connected and switched on.');
      await video('POST', '/cmd', { slate: 'Starting soon', minutes: 1 });
      await video('POST', '/cmd', { start: dests });
      this.h.startShow();
      s.slate = 'Starting soon';
      s.golive = { ...s.golive, phase: 'live', message: `Live on ${dests.map((d) => d.name).join(', ')}` };
      this.h.addFeed({ kind: 'SHOW', text: `Went live on ${dests.map((d) => d.name).join(', ')}.`, why: 'Starting-soon slate for a minute, then Claude cuts to the opening shot. All holds cleared.' });
      setTimeout(() => { if (s.slate === 'Starting soon') { s.slate = null; void video('POST', '/cmd', { slate: null }).catch(() => undefined); this.h.push(); } }, 60_000);
    } catch (e) {
      s.golive = { phase: 'error', message: (e as Error).message };
      this.h.addFeed({ kind: 'EMERGENCY', text: 'Go live failed.', why: (e as Error).message.slice(0, 200) });
    }
    this.h.push();
  }

  async end() {
    const s = this.h.state;
    s.golive = { ...s.golive, phase: 'ending', message: 'Ending…' };
    this.h.push();
    try { await video('POST', '/cmd', { stop: true }); } catch { /* encoder may already be down */ }
    try { if (s.golive.broadcastId) await youtube.end(s.golive.broadcastId); } catch { /* auto-stop also ends it */ }
    s.onAir = false;
    s.golive = { phase: 'idle' };
    this.h.push();
  }
}

export function registerDestinations(app: FastifyInstance) {
  // Save a stream key (TikTok/Instagram per show; Twitch/Facebook until OAuth is set up). Never echoed back.
  app.post<{ Body: { p: Platform; key: string; url?: string } }>('/api/destinations/key', async (req, reply) => {
    const { p, key } = req.body ?? ({} as never);
    if (!['TW', 'FB', 'TT', 'IG'].includes(p) || !key || key.length < 8) return reply.code(400).send({ error: 'Paste the full stream key.' });
    const keys = loadKeys();
    keys[p] = { url: (req.body.url || DEFAULT_URL[p] || '').trim(), key: key.trim() };
    saveKeys(keys);
    return { ok: true };
  });
  app.delete<{ Querystring: { p: Platform } }>('/api/destinations/key', async (req) => {
    const keys = loadKeys();
    delete keys[req.query.p];
    saveKeys(keys);
    return { ok: true };
  });
}
