import { createHmac, scryptSync, timingSafeEqual, randomBytes } from 'node:crypto';
import type { FastifyInstance, FastifyRequest } from 'fastify';

// Single shared login for the band's web app. Credentials live in .env (never committed).
const USER = process.env.VN_ADMIN_USER ?? '';
const PASSWORD = process.env.VN_ADMIN_PASSWORD ?? '';
const SECRET = process.env.VN_SESSION_SECRET || randomBytes(32).toString('hex');
const COOKIE = 'vn_session';
const MAX_AGE_S = 60 * 60 * 24 * 14;

const salt = randomBytes(16);
const hash = (s: string) => scryptSync(s, salt, 32);
const expected = hash(`${USER}\n${PASSWORD}`);

function sign(payload: string) {
  return createHmac('sha256', SECRET).update(payload).digest('base64url');
}

export function makeToken() {
  const exp = Math.floor(Date.now() / 1000) + MAX_AGE_S;
  const payload = `v1.${exp}`;
  return `${payload}.${sign(payload)}`;
}

export function isValidToken(token: string | undefined) {
  if (!token) return false;
  const i = token.lastIndexOf('.');
  if (i < 0) return false;
  const payload = token.slice(0, i);
  const sig = Buffer.from(token.slice(i + 1));
  const want = Buffer.from(sign(payload));
  if (sig.length !== want.length || !timingSafeEqual(sig, want)) return false;
  const exp = Number(payload.split('.')[1]);
  return Number.isFinite(exp) && exp * 1000 > Date.now();
}

export function isAuthed(req: FastifyRequest) {
  return isValidToken(req.cookies[COOKIE]);
}

// Simple per-IP brake on password guessing.
const attempts = new Map<string, { n: number; until: number }>();

export function registerAuth(app: FastifyInstance) {
  if (!USER || !PASSWORD) app.log.warn('VN_ADMIN_USER / VN_ADMIN_PASSWORD not set: login is disabled');

  app.post<{ Body: { user?: string; password?: string } }>('/api/login', async (req, reply) => {
    const a = attempts.get(req.ip);
    if (a && a.n >= 5 && a.until > Date.now()) return reply.code(429).send({ error: 'Too many attempts. Try again in a minute.' });
    const ok =
      USER !== '' &&
      PASSWORD !== '' &&
      timingSafeEqual(hash(`${req.body?.user ?? ''}\n${req.body?.password ?? ''}`), expected);
    if (!ok) {
      const n = (a && a.until > Date.now() ? a.n : 0) + 1;
      attempts.set(req.ip, { n, until: Date.now() + 60_000 });
      return reply.code(401).send({ error: 'Wrong name or password.' });
    }
    attempts.delete(req.ip);
    reply.setCookie(COOKIE, makeToken(), {
      path: '/',
      httpOnly: true,
      sameSite: 'lax',
      secure: req.protocol === 'https',
      maxAge: MAX_AGE_S,
    });
    return { ok: true };
  });

  app.post('/api/logout', async (_req, reply) => {
    reply.clearCookie(COOKIE, { path: '/' });
    return { ok: true };
  });

  app.get('/api/me', async (req) => ({ authed: isAuthed(req) }));

  // Everything under /api except login/logout/me/health needs a session.
  app.addHook('onRequest', async (req, reply) => {
    const url = req.url.split('?')[0];
    const open = ['/api/login', '/api/logout', '/api/me', '/api/health', '/api/cams/join'];
    if ((url.startsWith('/api/') || url === '/ws') && !open.includes(url) && !isAuthed(req)) {
      return reply.code(401).send({ error: 'Please log in.' });
    }
  });
}
