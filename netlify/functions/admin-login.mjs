import { getStore } from '@netlify/blobs';
import { passwordMatches, createSessionCookie, hasCsrfHeader } from '../lib/auth.mjs';

const MAX_ATTEMPTS = 10;
const WINDOW_MS = 15 * 60 * 1000;

function attemptStore() {
  return getStore({ name: 'vibration-menu-auth', consistency: 'strong' });
}

/**
 * Throttles guessing per client IP. Serverless instances are short-lived, so the
 * counter lives in Blobs rather than memory. A failure to read or write the
 * counter must not lock the owner out, so it degrades to "allow".
 */
async function readAttempts(key) {
  try {
    const record = await attemptStore().get(key, { type: 'json' });
    if (!record || Date.now() - record.first > WINDOW_MS) return null;
    return record;
  } catch (error) {
    console.error('Attempt-counter read failed:', error);
    return null;
  }
}

async function recordFailure(key, existing) {
  try {
    const record = existing
      ? { count: existing.count + 1, first: existing.first }
      : { count: 1, first: Date.now() };
    await attemptStore().setJSON(key, record);
  } catch (error) {
    console.error('Attempt-counter write failed:', error);
  }
}

async function clearAttempts(key) {
  try {
    await attemptStore().delete(key);
  } catch {
    // Not worth failing a successful login over.
  }
}

export default async (request) => {
  if (!hasCsrfHeader(request)) {
    return Response.json({ error: 'Bad request' }, { status: 400 });
  }

  const ip = request.headers.get('x-nf-client-connection-ip') || 'unknown';
  const key = `attempts-${ip.replace(/[^a-zA-Z0-9.:_-]/g, '')}`;

  const attempts = await readAttempts(key);
  if (attempts && attempts.count >= MAX_ATTEMPTS) {
    return Response.json(
      { error: 'Too many attempts. Try again in 15 minutes.' },
      { status: 429 },
    );
  }

  let password;
  try {
    ({ password } = await request.json());
  } catch {
    return Response.json({ error: 'Bad request' }, { status: 400 });
  }

  let ok;
  try {
    ok = passwordMatches(password);
  } catch (error) {
    // ADMIN_PASSWORD missing on the site: tell the operator, do not let anyone in.
    console.error(error);
    return Response.json(
      { error: 'Admin password is not configured on this site.' },
      { status: 500 },
    );
  }

  if (!ok) {
    await recordFailure(key, attempts);
    return Response.json({ error: 'Incorrect password' }, { status: 401 });
  }

  await clearAttempts(key);
  return Response.json({ ok: true }, { headers: { 'Set-Cookie': createSessionCookie() } });
};

export const config = { path: '/api/admin/login', method: 'POST' };
