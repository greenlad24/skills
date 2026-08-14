import { createHmac, randomBytes, timingSafeEqual, createHash } from 'node:crypto';

const COOKIE_NAME = 'vm_session';
const SESSION_TTL_SECONDS = 60 * 60 * 12; // 12h, so a shift doesn't end with a surprise logout

/**
 * The password the editor logs in with. Set as a Netlify environment variable;
 * it is never written to the repo.
 */
function adminPassword() {
  const value = process.env.ADMIN_PASSWORD;
  if (!value) throw new Error('ADMIN_PASSWORD is not set on this site');
  return value;
}

/**
 * Key used to sign session cookies. A dedicated SESSION_SECRET is preferred, but
 * deriving one from the password keeps the site working if only ADMIN_PASSWORD
 * was set. The derived form has a useful property: changing the password
 * invalidates every outstanding session.
 */
function sessionSecret() {
  const explicit = process.env.SESSION_SECRET;
  if (explicit) return explicit;
  return createHash('sha256').update(`derived:${adminPassword()}`).digest('hex');
}

function base64url(buffer) {
  return Buffer.from(buffer).toString('base64url');
}

function sign(payload) {
  return createHmac('sha256', sessionSecret()).update(payload).digest('base64url');
}

/** Constant-time string compare that does not leak length through early return. */
function safeEqual(a, b) {
  const ha = createHash('sha256').update(String(a)).digest();
  const hb = createHash('sha256').update(String(b)).digest();
  return timingSafeEqual(ha, hb);
}

export function passwordMatches(candidate) {
  if (typeof candidate !== 'string' || candidate.length === 0) return false;
  return safeEqual(candidate, adminPassword());
}

export function createSessionCookie() {
  const payload = base64url(
    JSON.stringify({
      exp: Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS,
      jti: randomBytes(8).toString('hex'),
    }),
  );
  const token = `${payload}.${sign(payload)}`;
  return [
    `${COOKIE_NAME}=${token}`,
    'HttpOnly',
    'Secure',
    'SameSite=Strict',
    'Path=/',
    `Max-Age=${SESSION_TTL_SECONDS}`,
  ].join('; ');
}

export function clearSessionCookie() {
  return `${COOKIE_NAME}=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0`;
}

function readCookie(request, name) {
  const header = request.headers.get('cookie');
  if (!header) return null;
  for (const part of header.split(';')) {
    const [key, ...rest] = part.trim().split('=');
    if (key === name) return rest.join('=');
  }
  return null;
}

/** True when the request carries a valid, unexpired, correctly signed session. */
export function isAuthenticated(request) {
  const token = readCookie(request, COOKIE_NAME);
  if (!token) return false;

  const [payload, signature] = token.split('.');
  if (!payload || !signature) return false;

  let expected;
  try {
    expected = sign(payload);
  } catch {
    return false; // ADMIN_PASSWORD missing: fail closed
  }
  if (!safeEqual(signature, expected)) return false;

  try {
    const { exp } = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
    return typeof exp === 'number' && exp > Math.floor(Date.now() / 1000);
  } catch {
    return false;
  }
}

/**
 * Rejects cross-site form posts. The session cookie is already SameSite=Strict;
 * requiring a header the browser will not attach on a cross-origin form submit
 * closes the remaining gap without a token round-trip.
 */
export function hasCsrfHeader(request) {
  return request.headers.get('x-requested-with') === 'vibration-admin';
}

export function unauthorized(message = 'Not signed in') {
  return Response.json({ error: message }, { status: 401 });
}
