import { getStore } from '@netlify/blobs';
import { isAuthenticated, hasCsrfHeader, unauthorized } from '../lib/auth.mjs';
import { venueToday } from '../lib/shows.mjs';
import { extractEvent, extractionConfigured } from '../lib/extract.mjs';

const MIME = { jpg: 'image/jpeg', png: 'image/png', webp: 'image/webp' };

export default async (request) => {
  if (!isAuthenticated(request)) return unauthorized();
  if (!hasCsrfHeader(request)) return Response.json({ error: 'Bad request' }, { status: 400 });

  if (!extractionConfigured()) {
    // Not an error: the editor falls back to filling the fields by hand.
    return Response.json({ configured: false }, { status: 200 });
  }

  let key;
  try {
    ({ key } = await request.json());
  } catch {
    return Response.json({ error: 'Bad request' }, { status: 400 });
  }
  if (!/^[a-f0-9]{32}\.(jpg|png|webp)$/.test(String(key || ''))) {
    return Response.json({ error: 'Unknown image' }, { status: 400 });
  }

  let bytes, mime;
  try {
    const blob = await getStore({ name: 'vibration-images', consistency: 'strong' })
      .getWithMetadata(key, { type: 'arrayBuffer' });
    if (!blob) return Response.json({ error: 'Image not found' }, { status: 404 });
    bytes = Buffer.from(blob.data);
    mime = blob.metadata?.mime || MIME[key.split('.').pop()];
  } catch (error) {
    console.error('extract: could not read image', error);
    return Response.json({ error: 'Could not read the image' }, { status: 500 });
  }

  try {
    const { event, confident, provider, usage } = await extractEvent({
      bytes, mime, key, today: venueToday(),
    });
    return Response.json({ configured: true, event, confident, provider, usage });
  } catch (error) {
    console.error('extract: model call failed', error);
    // The editor still has the uploaded poster; only the auto-fill failed.
    return Response.json({ error: 'Could not read that poster automatically' }, { status: 502 });
  }
};

export const config = { path: '/api/admin/extract', method: 'POST' };
