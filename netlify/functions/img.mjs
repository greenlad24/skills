import { storage } from '../lib/blobs.mjs';

const MIME = { jpg: 'image/jpeg', png: 'image/png', webp: 'image/webp' };

/** Serves uploaded posters. Public — these appear on the public Live Shows pages. */
export default async (request) => {
  const key = new URL(request.url).pathname.split('/').pop() || '';

  // Keys are content hashes we generated; anything else is not ours to serve.
  if (!/^[a-f0-9]{32}\.(jpg|png|webp)$/.test(key)) {
    return new Response('Not found', { status: 404 });
  }

  try {
    // The key is a hash of the bytes, so a stale read cannot be wrong.
    const blob = await storage('images', { consistency: 'eventual' }).getFile(key);
    if (!blob) return new Response('Not found', { status: 404 });

    const mime = blob.metadata.mime || MIME[key.split('.').pop()] || 'application/octet-stream';
    return new Response(blob.bytes, {
      headers: {
        'Content-Type': mime,
        // The key is a hash of the bytes, so this URL is immutable.
        'Cache-Control': 'public, max-age=31536000, immutable',
        'X-Content-Type-Options': 'nosniff',
      },
    });
  } catch (error) {
    console.error('Image read failed:', error);
    return new Response('Not found', { status: 404 });
  }
};

export const config = { path: '/api/img/:key' };
