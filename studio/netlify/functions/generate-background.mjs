// Netlify BACKGROUND Function (the -background suffix gives it a 15-minute
// budget) that runs the slow poster generation — gpt-image-2 at high quality
// takes 1-5 minutes, far beyond the ~26s synchronous function cap.
//
// The client POSTs { week, day, count, jobId } here (after /api/generate
// answered { background: true }), then polls GET /api/job/<jobId> until the
// job record in Blobs flips to done/error, and refetches the day.
import { getStore } from '@netlify/blobs';
import store from '../../lib/store.js';
import routesLib from '../../lib/routes.js';
import authLib from '../../lib/auth.js';

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

export default async (request) => {
  const url = new URL(request.url);
  const password = process.env.STUDIO_PASSWORD;
  if (password && !authLib.verifyCookieHeader(request.headers.get('cookie'), password)) {
    return new Response(JSON.stringify({ error: 'auth required' }), { status: 401 });
  }

  const body = await request.json().catch(() => ({}));
  const { week, day, jobId } = body;
  if (!week || !day || !jobId) {
    return new Response(JSON.stringify({ error: 'week, day and jobId required' }), { status: 400 });
  }

  store.setDriver(blobDriver());
  const ctx = {
    origin: url.origin,
    serverless: true,
    async loadAsset(relPath) {
      const res = await fetch(`${url.origin}/${relPath}`);
      if (!res.ok) throw new Error(`Asset fetch failed (HTTP ${res.status}): ${url.origin}/${relPath}`);
      return Buffer.from(await res.arrayBuffer());
    },
  };

  await store.setAux(`jobs/${jobId}`, { status: 'running', startedAt: new Date().toISOString() });
  try {
    const out = await routesLib.runGeneration(ctx, week, day, body);
    await store.setAux(`jobs/${jobId}`, {
      status: 'done',
      generationId: out.generation.id,
      errors: out.generation.errors || [],
      finishedAt: new Date().toISOString(),
    });
  } catch (e) {
    await store.setAux(`jobs/${jobId}`, { status: 'error', error: e.message, finishedAt: new Date().toISOString() });
  }
};
