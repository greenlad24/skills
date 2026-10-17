// Phone cameras: QR invites, LiveKit tokens, and a small status/tally socket per phone.
//
// Flow: the web app asks for an invite link (shown as a QR). A phone opens it, posts its
// name, and gets a camera id, a LiveKit publish token and the address of /cam-ws, where it
// reports battery/heat/Wi-Fi/locks every ~2 s and receives the on-air tally.

import { createHmac, randomBytes, timingSafeEqual } from 'node:crypto';
import type { FastifyInstance } from 'fastify';
import { AccessToken } from 'livekit-server-sdk';
import type { CamCommand, CamStatus, CameraState } from '@vibenation/shared';

const SECRET = process.env.VN_SESSION_SECRET || randomBytes(32).toString('hex');
const LK_KEY = process.env.LIVEKIT_API_KEY ?? '';
const LK_SECRET = process.env.LIVEKIT_API_SECRET ?? '';
export const ROOM = 'show';

const sign = (s: string) => createHmac('sha256', SECRET).update(s).digest('base64url');
function makeSigned(kind: string, payload: string, ttlS: number) {
  const body = `${kind}.${payload}.${Math.floor(Date.now() / 1000) + ttlS}`;
  return `${Buffer.from(body).toString('base64url')}.${sign(body)}`;
}
function readSigned(kind: string, token: string | undefined): string | null {
  if (!token) return null;
  const [b, sig] = token.split('.');
  if (!b || !sig) return null;
  const body = Buffer.from(b, 'base64url').toString();
  const want = Buffer.from(sign(body));
  const got = Buffer.from(sig);
  if (want.length !== got.length || !timingSafeEqual(want, got)) return null;
  const [k, payload, exp] = body.split('.');
  if (k !== kind || Number(exp) * 1000 < Date.now()) return null;
  return payload;
}

async function lkToken(identity: string, name: string, publish: boolean) {
  const at = new AccessToken(LK_KEY, LK_SECRET, { identity, name, ttl: '12h' });
  at.addGrant({ room: ROOM, roomJoin: true, canPublish: publish, canSubscribe: !publish, canPublishData: publish });
  return at.toJwt();
}

export interface CamHost {
  cams(): CameraState[];
  upsertCam(c: CameraState): void;
  camGone(id: number): void;
  liveCam(): number;
  onCamsChanged(fn: () => void): void;
}

export function registerCams(app: FastifyInstance, host: CamHost) {
  const sockets = new Map<number, { send: (c: CamCommand) => void }>();
  let nextId = 1;

  // Authenticated: invite link for the QR code (valid 24 h).
  app.get('/api/cams/invite', async (req) => {
    const base = `${req.protocol}://${req.headers.host}`;
    return { url: `${base}/cam?k=${makeSigned('invite', 'show', 24 * 3600)}`, expiresInS: 24 * 3600 };
  });

  // Authenticated: subscribe-only LiveKit token so the web app can show the cameras.
  app.get('/api/cams/viewer-token', async (req) => {
    const id = `viewer-${randomBytes(4).toString('hex')}`;
    return { url: `wss://${req.headers.host}`, token: await lkToken(id, 'VibeNation', false), room: ROOM };
  });

  // Public, but needs a valid invite: a phone joins as a camera.
  app.post<{ Body: { k?: string; name?: string; device?: 'android' | 'iphone'; camId?: number } }>('/api/cams/join', async (req, reply) => {
    if (readSigned('invite', req.body?.k) === null) return reply.code(403).send({ error: 'This camera link has expired. Scan the QR code in VibeNation again.' });
    const existing = host.cams().filter((c) => c.identity);
    const id = req.body?.camId && existing.some((c) => c.id === req.body.camId) ? req.body.camId : (Math.max(0, ...existing.map((c) => c.id)) || nextId - 1) + 1;
    nextId = id + 1;
    const name = String(req.body?.name ?? `Camera ${id}`).slice(0, 40);
    const identity = `cam-${id}`;
    host.upsertCam({ id, num: `CAM ${id}`, name, device: req.body?.device === 'iphone' ? 'iphone' : 'android', connected: false, battery: 100, charging: false, identity });
    return {
      camId: id,
      num: `CAM ${id}`,
      name,
      room: ROOM,
      livekitUrl: `wss://${req.headers.host}`,
      token: await lkToken(identity, `CAM ${id} · ${name}`, true),
      camToken: makeSigned('cam', String(id), 24 * 3600),
    };
  });

  // Phone status + tally socket. Auth is the signed camToken from /join.
  app.get<{ Querystring: { ct?: string } }>('/cam-ws', { websocket: true }, (socket, req) => {
    const id = Number(readSigned('cam', req.query.ct));
    if (!id) return socket.close(4003, 'bad camera token');
    const send = (c: CamCommand) => socket.send(JSON.stringify(c));
    sockets.set(id, { send });
    send({ type: 'tally', live: host.liveCam() === id });
    socket.on('message', (raw: Buffer) => {
      let s: CamStatus;
      try { s = JSON.parse(String(raw)); } catch { return; }
      if (s.type !== 'status') return;
      const cur = host.cams().find((c) => c.id === id);
      if (!cur) return;
      const battery = Math.round(s.battery ?? cur.battery);
      const warn = !s.landscape && s.landscape !== undefined ? 'Turn to landscape'
        : battery < 25 && !s.charging ? `Battery ${battery}%`
        : (s.temp ?? 0) >= 45 ? `Hot ${s.temp} °C`
        : s.fps !== undefined && s.fps < 50 ? `${Math.round(s.fps)} fps`
        : undefined;
      host.upsertCam({ ...cur, connected: true, battery, charging: !!s.charging, temp: s.temp, wifi: s.wifi, kbps: s.kbps, fps: s.fps, width: s.width, height: s.height, wb: s.wb, exposure: s.exposure, locked: s.locked, warn, error: undefined });
    });
    socket.on('close', () => {
      sockets.delete(id);
      const cur = host.cams().find((c) => c.id === id);
      if (cur) host.upsertCam({ ...cur, connected: false, error: 'Disconnected', warn: undefined });
    });
  });

  // Push the tally to every phone whenever the on-air camera changes.
  let lastLive = -1;
  host.onCamsChanged(() => {
    const live = host.liveCam();
    if (live === lastLive) return;
    lastLive = live;
    for (const [id, s] of sockets) s.send({ type: 'tally', live: id === live });
  });
}
