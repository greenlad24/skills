// YouTube: OAuth connection to the band's channel, broadcast creation/binding, metadata,
// thumbnail and chat. Plain fetch against the Data API v3 (no SDK). The refresh token is
// stored in vibenation/data/secrets (git-ignored, mode 600).

import { createHmac, randomBytes } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { FastifyInstance } from 'fastify';

// Read live: the Keys screen can set these without a restart.
const clientId = () => process.env.YOUTUBE_CLIENT_ID ?? '';
const clientSecret = () => process.env.YOUTUBE_CLIENT_SECRET ?? '';
const SECRETS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../data/secrets');
const TOKEN_FILE = path.join(SECRETS, 'youtube.json');
const SCOPES = ['https://www.googleapis.com/auth/youtube', 'https://www.googleapis.com/auth/youtube.force-ssl'];
const API = 'https://www.googleapis.com/youtube/v3';
const STATE_KEY = process.env.VN_SESSION_SECRET || randomBytes(16).toString('hex');

interface Tokens { refresh_token: string; access_token?: string; expires_at?: number; channel?: { id: string; title: string } }

export interface Broadcast {
  id: string;
  title: string;
  scheduledStart?: string;
  status: string; // created | ready | testing | live | complete
  streamId?: string;
  ingest?: { url: string; key: string };
}

const configured = () => Boolean(clientId() && clientSecret());

function load(): Tokens | null {
  try { return JSON.parse(readFileSync(TOKEN_FILE, 'utf8')) as Tokens; } catch { return null; }
}
function save(t: Tokens) {
  mkdirSync(SECRETS, { recursive: true, mode: 0o700 });
  writeFileSync(TOKEN_FILE, JSON.stringify(t), { mode: 0o600 });
}

async function accessToken(): Promise<string> {
  const t = load();
  if (!t) throw new Error('YouTube is not connected.');
  if (t.access_token && (t.expires_at ?? 0) > Date.now() + 60_000) return t.access_token;
  const r = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ client_id: clientId(), client_secret: clientSecret(), refresh_token: t.refresh_token, grant_type: 'refresh_token' }),
  });
  const j = (await r.json()) as { access_token?: string; expires_in?: number; error_description?: string };
  if (!j.access_token) throw new Error(`YouTube token refresh failed: ${j.error_description ?? r.status}`);
  save({ ...t, access_token: j.access_token, expires_at: Date.now() + (j.expires_in ?? 3600) * 1000 });
  return j.access_token;
}

async function yt<T>(method: string, pathAndQuery: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API}${pathAndQuery}`, {
    method,
    headers: { authorization: `Bearer ${await accessToken()}`, ...(body ? { 'content-type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  if (!r.ok) throw new Error(`YouTube ${method} ${pathAndQuery.split('?')[0]}: ${r.status} ${text.slice(0, 300)}`);
  return (text ? JSON.parse(text) : {}) as T;
}

type BroadcastItem = { id: string; snippet: { title: string; scheduledStartTime?: string }; status: { lifeCycleStatus: string }; contentDetails?: { boundStreamId?: string } };
type StreamItem = { id: string; cdn: { ingestionInfo: { ingestionAddress: string; streamName: string } } };

async function ingestFor(streamId?: string): Promise<Broadcast['ingest']> {
  if (!streamId) return undefined;
  const s = await yt<{ items: StreamItem[] }>('GET', `/liveStreams?part=cdn&id=${streamId}`);
  const i = s.items[0]?.cdn.ingestionInfo;
  return i ? { url: i.ingestionAddress, key: i.streamName } : undefined;
}

export const youtube = {
  configured,
  connected: () => Boolean(load()),
  channel: () => load()?.channel ?? null,

  /** Upcoming broadcasts on the channel (the "scheduled show" case). */
  async upcoming(): Promise<Broadcast[]> {
    const r = await yt<{ items: BroadcastItem[] }>('GET', '/liveBroadcasts?part=snippet,status,contentDetails&broadcastStatus=upcoming&maxResults=10');
    return Promise.all(r.items.map(async (b) => ({
      id: b.id, title: b.snippet.title, scheduledStart: b.snippet.scheduledStartTime, status: b.status.lifeCycleStatus,
      streamId: b.contentDetails?.boundStreamId, ingest: await ingestFor(b.contentDetails?.boundStreamId),
    })));
  },

  /** Create a broadcast + a 1080p60 stream and bind them. Auto start/stop follow the encoder. */
  async create(opts: { title: string; description: string; privacy: 'public' | 'unlisted' | 'private'; tags?: string[] }): Promise<Broadcast> {
    const b = await yt<BroadcastItem>('POST', '/liveBroadcasts?part=snippet,status,contentDetails', {
      snippet: { title: opts.title.slice(0, 100), description: opts.description.slice(0, 5000), scheduledStartTime: new Date().toISOString() },
      status: { privacyStatus: opts.privacy, selfDeclaredMadeForKids: false },
      contentDetails: { enableAutoStart: true, enableAutoStop: true, latencyPreference: 'low', enableDvr: true },
    });
    const s = await yt<StreamItem>('POST', '/liveStreams?part=snippet,cdn,contentDetails', {
      snippet: { title: `VibeNation ${new Date().toISOString().slice(0, 16)}` },
      cdn: { ingestionType: 'rtmp', resolution: '1080p', frameRate: '60fps' },
      contentDetails: { isReusable: false },
    });
    await yt('POST', `/liveBroadcasts/bind?id=${b.id}&part=id,contentDetails&streamId=${s.id}`);
    if (opts.tags?.length) await this.setTags(b.id, opts.tags);
    return { id: b.id, title: b.snippet.title, status: b.status.lifeCycleStatus, streamId: s.id, ingest: await ingestFor(s.id) };
  },

  /** Bind our own stream to an already scheduled broadcast. */
  async bind(broadcastId: string): Promise<Broadcast> {
    const list = await this.upcoming();
    const b = list.find((x) => x.id === broadcastId);
    if (!b) throw new Error('That scheduled broadcast was not found.');
    if (b.ingest) return b;
    const s = await yt<StreamItem>('POST', '/liveStreams?part=snippet,cdn,contentDetails', {
      snippet: { title: `VibeNation ${new Date().toISOString().slice(0, 16)}` },
      cdn: { ingestionType: 'rtmp', resolution: '1080p', frameRate: '60fps' }, contentDetails: { isReusable: false },
    });
    await yt('POST', `/liveBroadcasts/bind?id=${b.id}&part=id,contentDetails&streamId=${s.id}`);
    return { ...b, streamId: s.id, ingest: await ingestFor(s.id) };
  },

  async setTags(videoId: string, tags: string[]) {
    const v = await yt<{ items: { snippet: Record<string, unknown> }[] }>('GET', `/videos?part=snippet&id=${videoId}`);
    const snippet = v.items[0]?.snippet;
    if (!snippet) return;
    await yt('PUT', '/videos?part=snippet', { id: videoId, snippet: { ...snippet, tags: tags.slice(0, 30), categoryId: snippet.categoryId ?? '10' } });
  },

  async setThumbnail(videoId: string, jpeg: Buffer) {
    const r = await fetch(`https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId=${videoId}`, {
      method: 'POST', headers: { authorization: `Bearer ${await accessToken()}`, 'content-type': 'image/jpeg' }, body: new Uint8Array(jpeg),
    });
    if (!r.ok) throw new Error(`Thumbnail upload failed: ${r.status} ${(await r.text()).slice(0, 200)} (custom thumbnails need a verified channel)`);
  },

  async status(broadcastId: string): Promise<string> {
    const r = await yt<{ items: BroadcastItem[] }>('GET', `/liveBroadcasts?part=status&id=${broadcastId}`);
    return r.items[0]?.status.lifeCycleStatus ?? 'unknown';
  },

  async end(broadcastId: string) {
    await yt('POST', `/liveBroadcasts/transition?broadcastStatus=complete&id=${broadcastId}&part=status`);
  },
};

// ---------- OAuth routes ----------

const sign = (s: string) => createHmac('sha256', STATE_KEY).update(s).digest('base64url');

export function registerYouTube(app: FastifyInstance) {
  app.get('/api/youtube/status', async () => ({ configured: configured(), connected: youtube.connected(), channel: youtube.channel() }));

  app.get('/api/oauth/youtube/start', async (req, reply) => {
    if (!configured()) return reply.code(400).send({ error: 'Add YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET to the server first (see docs/ACCOUNTS-TO-CONNECT.md).' });
    const nonce = randomBytes(8).toString('hex');
    const state = `${nonce}.${sign(nonce)}`;
    const redirect = `https://${req.headers.host}/api/oauth/youtube/callback`;
    const url = new URL('https://accounts.google.com/o/oauth2/v2/auth');
    for (const [k, v] of Object.entries({ client_id: clientId(), redirect_uri: redirect, response_type: 'code', scope: SCOPES.join(' '), access_type: 'offline', prompt: 'consent', state })) url.searchParams.set(k, v);
    return reply.redirect(url.toString());
  });

  app.get<{ Querystring: { code?: string; state?: string; error?: string } }>('/api/oauth/youtube/callback', async (req, reply) => {
    const [nonce, sig] = (req.query.state ?? '').split('.');
    if (!nonce || sig !== sign(nonce)) return reply.code(400).send('Bad state. Start again from the Go Live screen.');
    if (req.query.error || !req.query.code) return reply.redirect('/#/golive?youtube=denied');
    const r = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ code: req.query.code, client_id: clientId(), client_secret: clientSecret(), redirect_uri: `https://${req.headers.host}/api/oauth/youtube/callback`, grant_type: 'authorization_code' }),
    });
    const j = (await r.json()) as { refresh_token?: string; access_token?: string; expires_in?: number };
    if (!j.refresh_token) return reply.code(400).send('Google did not return a refresh token. Remove VibeNation from your Google account permissions and connect again.');
    save({ refresh_token: j.refresh_token, access_token: j.access_token, expires_at: Date.now() + (j.expires_in ?? 3600) * 1000 });
    try {
      const me = await yt<{ items: { id: string; snippet: { title: string } }[] }>('GET', '/channels?part=snippet&mine=true');
      const c = me.items[0];
      if (c) save({ ...load()!, channel: { id: c.id, title: c.snippet.title } });
    } catch { /* channel name is cosmetic */ }
    return reply.redirect('/#/golive?youtube=connected');
  });

  app.post('/api/youtube/disconnect', async () => {
    if (existsSync(TOKEN_FILE)) writeFileSync(TOKEN_FILE, '', { mode: 0o600 });
    return { ok: true };
  });

  app.get('/api/youtube/upcoming', async (_req, reply) => {
    try { return { items: await youtube.upcoming() }; } catch (e) { return reply.code(400).send({ error: (e as Error).message }); }
  });
}
