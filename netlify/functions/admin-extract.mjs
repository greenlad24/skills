import { storage } from '../lib/blobs.mjs';
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
    const blob = await storage('images').getFile(key);
    if (!blob) return Response.json({ error: 'Image not found' }, { status: 404 });
    bytes = Buffer.from(blob.bytes);
    mime = blob.metadata.mime || MIME[key.split('.').pop()];
  } catch (error) {
    console.error('extract: could not read image', error);
    return Response.json({ error: 'Could not read the image' }, { status: 500 });
  }

  try {
    const { event, confident, recurring, provider, usage } = await extractEvent({
      bytes, mime, key, today: venueToday(),
    });
    return Response.json({ configured: true, event, confident, recurring, provider, usage });
  } catch (error) {
    console.error('extract: model call failed', error);
    // The editor still has the uploaded poster; only the auto-fill failed. Which
    // way it failed decides what the editor does next — waiting out a rate limit
    // is worth doing, re-reading an unreadable poster is not.
    const reason = error.reason || 'unknown';
    return Response.json({
      error: EXPLANATION[reason] || 'could not be read',
      reason,
      retryAfter: error.retryAfter || 0,
    }, { status: reason === 'rate_limit' ? 429 : 502 });
  }
};

/** Said plainly enough for whoever is adding posters to know what to do next. */
const EXPLANATION = {
  rate_limit: 'Groq is rate limiting the free tier',
  too_long: 'the model ran long on this one',
  too_big: 'the image is too large to send',
  unreadable: 'nothing readable came back',
  empty: 'the model returned nothing',
  model: 'no working vision model — check GROQ_MODEL',
  http: 'Groq refused the request',
};

export const config = { path: '/api/admin/extract', method: 'POST' };
