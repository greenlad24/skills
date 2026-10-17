// Phone app downloads for the Apps screen. The Android camera APK is served from the
// release build output; phones get it through a signed link (no login on a phone).
//
// /dl/vibenation-camera.apk works with a login cookie, a camera invite (?k= from /cam),
// or a 7-day download link from /api/apps (?k=, shown as a QR on the Apps screen).
// /dl/venue-sender.zip (venue laptop sender) needs a login.

import { createReadStream, existsSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { FastifyInstance } from 'fastify';
import type { AppsInfo } from '@vibenation/shared';
import { isAuthed } from './auth.js';
import { makeSigned, readSigned } from './cams.js';

const RELEASE_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../android/app/build/outputs/apk/release');
const APK = process.env.VN_ANDROID_APK ?? path.join(RELEASE_DIR, 'app-release.apk');
const LINK_TTL_S = 7 * 24 * 3600;
// Venue laptop sender (MR18 -> SRT). Holds the venue passphrase, so login only.
const VENUE_ZIP = process.env.VN_VENUE_SENDER_ZIP ?? '/home/vibe/vibenation-media/downloads/vibenation-venue-sender.zip';

function versionName(): string | null {
  try {
    const meta = JSON.parse(readFileSync(path.join(path.dirname(APK), 'output-metadata.json'), 'utf8')) as { elements?: { versionName?: string }[] };
    return meta.elements?.[0]?.versionName ?? null;
  } catch {
    return null;
  }
}

export function registerApps(app: FastifyInstance) {
  // Authenticated (/api): what's available + a download link for the QR.
  app.get('/api/apps', async (req): Promise<AppsInfo> => {
    const base = `${req.protocol}://${req.headers.host}`;
    if (!existsSync(APK)) return { android: null };
    const st = statSync(APK);
    return {
      android: {
        version: versionName(),
        sizeMB: Math.round(st.size / 1e5) / 10,
        builtAt: st.mtime.toISOString(),
        url: `${base}/dl/vibenation-camera.apk?k=${makeSigned('apk', 'android', LINK_TTL_S)}`,
        expiresInS: LINK_TTL_S,
      },
    };
  });

  // Public path, gated by a signed link, a camera invite or a login.
  app.get<{ Querystring: { k?: string } }>('/dl/vibenation-camera.apk', async (req, reply) => {
    const k = req.query.k;
    if (!isAuthed(req) && readSigned('apk', k) === null && readSigned('invite', k) === null) {
      return reply.code(403).type('text/plain').send('This download link has expired. Open Apps in VibeNation for a new one.');
    }
    if (!existsSync(APK)) return reply.code(404).type('text/plain').send('The Android app has not been built yet.');
    return reply
      .header('content-type', 'application/vnd.android.package-archive')
      .header('content-disposition', 'attachment; filename="VibeNation-Camera.apk"')
      .header('content-length', statSync(APK).size)
      .header('cache-control', 'no-store')
      .send(createReadStream(APK));
  });

  // Venue laptop sender package. Login required (it contains the SRT passphrase).
  app.get('/dl/venue-sender.zip', async (req, reply) => {
    if (!isAuthed(req)) return reply.code(401).type('text/plain').send('Log in to VibeNation to download the venue sender.');
    if (!existsSync(VENUE_ZIP)) return reply.code(404).type('text/plain').send('The venue sender package has not been made yet. Ask Claude.');
    return reply
      .header('content-type', 'application/zip')
      .header('content-disposition', 'attachment; filename="vibenation-venue-sender.zip"')
      .header('content-length', statSync(VENUE_ZIP).size)
      .header('cache-control', 'no-store')
      .send(createReadStream(VENUE_ZIP));
  });
}
