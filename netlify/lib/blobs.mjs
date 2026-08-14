import { getStore } from '@netlify/blobs';

/**
 * Every read and write the site makes goes through here.
 *
 * Netlify Blobs is a service, not a setting, so no environment variable can
 * point this at Cloudflare KV or anywhere else — but the surface it needs is
 * four calls wide. Keeping them in one file means moving hosts is rewriting
 * this module, and nothing above it: the auth, the text-only merge, Live
 * Shows and the poster reader are all plain JavaScript that never mentions
 * a host.
 */

const NAMES = {
  menu: 'vibration-menu',
  images: 'vibration-images',
  auth: 'vibration-menu-auth',
};

/**
 * @param {'menu'|'images'|'auth'} which
 * @param {{ consistency?: 'strong'|'eventual' }} [options]
 *
 * Strong consistency by default: after Save, the next read of the public menu
 * must show the new price rather than a stale cached one. Images are the
 * exception — their keys are content hashes, so a stale read is impossible.
 */
export function storage(which, { consistency = 'strong' } = {}) {
  const name = NAMES[which];
  if (!name) throw new Error(`unknown store: ${which}`);
  const store = getStore({ name, consistency });

  return {
    /** Parsed JSON, or null when nothing is stored under that key. */
    getJSON: (key) => store.get(key, { type: 'json' }),

    setJSON: (key, value) => store.setJSON(key, value),

    /**
     * Bytes plus whatever was stored alongside them, or null if absent.
     * Uint8Array rather than Buffer, so this stays true on a runtime that has
     * no Node globals.
     */
    async getFile(key) {
      const blob = await store.getWithMetadata(key, { type: 'arrayBuffer' });
      if (!blob) return null;
      return { bytes: new Uint8Array(blob.data), metadata: blob.metadata || {} };
    },

    putFile: (key, bytes, metadata) => store.set(key, bytes, { metadata }),
  };
}
