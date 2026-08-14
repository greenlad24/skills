// Netlify Function shell for the Vibration Poster Studio. Handles /api/* and
// /files/* via the shared route table (lib/routes.js), stores everything in
// Netlify Blobs, and gates access with the STUDIO_PASSWORD env var.
import { getStore } from '@netlify/blobs';
import store from '../../lib/store.js';
import routesLib from '../../lib/routes.js';
import authLib from '../../lib/auth.js';

const { dispatch } = routesLib;

function blobDriver() {
  const blobs = getStore({ name: 'poster-studio', consistency: 'strong' });
  return {
    async getJson(key) {
      return (await blobs.get(key, { type: 'json' })) || null;
    },
    async setJson(key, obj) {
      await blobs.setJSON(key, obj);
    },
    async getFile(name) {
      const ab = await blobs.get(`files/${name}`, { type: 'arrayBuffer' });
      return ab ? Buffer.from(ab) : null;
    },
    async putFile(name, buf) {
      await blobs.set(`files/${name}`, buf);
    },
  };
}

function json(status, obj, headers = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

export default async (request) => {
  const url = new URL(request.url);
  const pathname = decodeURIComponent(url.pathname);
  const password = process.env.STUDIO_PASSWORD;

  try {
    // Login (also the place the frontend probes to see if auth is needed).
    if (pathname === '/api/login' && request.method === 'POST') {
      const body = await request.json().catch(() => ({}));
      if (!password || authLib.passwordMatches(body.password, password)) {
        return json(200, { ok: true }, password ? { 'Set-Cookie': authLib.cookieHeader(password, true) } : {});
      }
      return json(401, { error: 'Wrong password' });
    }

    if (password && !authLib.verifyCookieHeader(request.headers.get('cookie'), password)) {
      return json(401, { error: 'auth required' });
    }

    store.setDriver(blobDriver());
    const ctx = {
      origin: url.origin,
      // Style presets etc. are static site assets — fetch them from our own CDN.
      async loadAsset(relPath) {
        const res = await fetch(`${url.origin}/${relPath}`);
        if (!res.ok) throw new Error(`Asset not found: ${relPath}`);
        return Buffer.from(await res.arrayBuffer());
      },
    };

    const body = ['POST', 'PUT', 'PATCH'].includes(request.method)
      ? await request.json().catch(() => ({}))
      : {};
    const out = await dispatch(request.method, pathname, body, url.searchParams, ctx);
    if (!out) return json(404, { error: 'Not found' });
    if (out.file) {
      return new Response(out.file.buffer, {
        status: 200,
        headers: { 'Content-Type': out.file.mime, 'Cache-Control': 'private, max-age=31536000, immutable' },
      });
    }
    return json(out.status, out.json);
  } catch (e) {
    return json(500, { error: e.message });
  }
};

export const config = {
  path: ['/api/*', '/files/*'],
};
