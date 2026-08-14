import { storage } from '../lib/blobs.mjs';
import { createHash } from 'node:crypto';
import { isAuthenticated, hasCsrfHeader, unauthorized } from '../lib/auth.mjs';

const MAX_BYTES = 8 * 1024 * 1024;

// Sniffed from the bytes, not from the client's Content-Type, so a mislabelled
// or hostile upload cannot get itself served back as something executable.
const SIGNATURES = [
  { ext: 'jpg', mime: 'image/jpeg', test: (b) => b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff },
  { ext: 'png', mime: 'image/png', test: (b) => b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47 },
  { ext: 'webp', mime: 'image/webp', test: (b) =>
      b.slice(0, 4).toString('latin1') === 'RIFF' && b.slice(8, 12).toString('latin1') === 'WEBP' },
];

export default async (request) => {
  if (!isAuthenticated(request)) return unauthorized();
  if (!hasCsrfHeader(request)) return Response.json({ error: 'Bad request' }, { status: 400 });

  let bytes;
  try {
    const form = await request.formData();
    const file = form.get('file');
    if (!file || typeof file.arrayBuffer !== 'function') {
      return Response.json({ error: 'No file was sent' }, { status: 400 });
    }
    bytes = Buffer.from(await file.arrayBuffer());
  } catch {
    return Response.json({ error: 'Could not read the upload' }, { status: 400 });
  }

  if (bytes.length === 0) return Response.json({ error: 'That file is empty' }, { status: 400 });
  if (bytes.length > MAX_BYTES) {
    return Response.json({ error: 'Images must be under 8MB' }, { status: 413 });
  }

  const kind = SIGNATURES.find((s) => s.test(bytes));
  if (!kind) {
    return Response.json({ error: 'Only JPEG, PNG and WebP images are supported' }, { status: 415 });
  }

  // Content-addressed: re-uploading the same image reuses the key, and the URL
  // can be cached forever because it can never point at different bytes.
  const key = createHash('sha256').update(bytes).digest('hex').slice(0, 32) + '.' + kind.ext;

  try {
    await storage('images').putFile(key, bytes, { mime: kind.mime });
  } catch (error) {
    console.error('Image upload failed:', error);
    return Response.json({ error: 'Could not store the image' }, { status: 500 });
  }

  return Response.json({ url: `/api/img/${key}`, bytes: bytes.length, type: kind.mime });
};

export const config = { path: '/api/admin/upload', method: 'POST' };
