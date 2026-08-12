import { clearSessionCookie } from '../lib/auth.mjs';

export default async () =>
  Response.json({ ok: true }, { headers: { 'Set-Cookie': clearSessionCookie() } });

export const config = { path: '/api/admin/logout', method: 'POST' };
