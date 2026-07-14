// Blotato API client — used to schedule the finished posters to Instagram
// and Facebook. Docs: https://help.blotato.com/ (Settings → API for your key).
const fs = require('fs');
const path = require('path');

const BASE = 'https://backend.blotato.com';

async function api(apiKey, method, route, body) {
  if (!apiKey) throw new Error('Blotato API key is missing — add it in Settings.');
  const res = await fetch(`${BASE}${route}`, {
    method,
    headers: {
      'blotato-api-key': apiKey,
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json;
  try { json = JSON.parse(text); } catch { json = null; }
  if (!res.ok) {
    const msg = json?.message || json?.error || text.slice(0, 300) || `HTTP ${res.status}`;
    throw new Error(`Blotato ${route}: ${msg}`);
  }
  return json;
}

/** List connected social accounts (tries the known endpoints). */
async function listAccounts(apiKey) {
  const routes = ['/v2/users/me/accounts', '/v2/accounts'];
  let lastErr;
  for (const route of routes) {
    try {
      const json = await api(apiKey, 'GET', route);
      return json?.items || json?.accounts || json;
    } catch (e) {
      lastErr = e;
    }
  }
  throw new Error(
    `${lastErr.message} — if account listing is unavailable on your plan, enter the account IDs manually ` +
    '(Blotato dashboard → help.blotato.com/api/accounts explains where to find them).'
  );
}

/**
 * Make a local image publicly reachable for Blotato. Primary path: POST the
 * image as a base64 data URL to /v2/media (documented to accept URLs or data
 * URLs). Fallback: presigned upload endpoints.
 */
async function uploadMedia(apiKey, localPath) {
  const buf = fs.readFileSync(localPath);
  const ext = path.extname(localPath).toLowerCase();
  const mime = { '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp' }[ext] || 'image/png';

  try {
    const json = await api(apiKey, 'POST', '/v2/media', {
      url: `data:${mime};base64,${buf.toString('base64')}`,
    });
    const url = json?.url || json?.mediaUrl || json?.data?.url;
    if (!url) throw new Error('media upload returned no URL');
    return url;
  } catch (primaryErr) {
    // Fallback: presigned upload flow.
    for (const route of ['/v2/media/presigned-upload-url', '/v2/media/presigned']) {
      try {
        const pre = await api(apiKey, 'POST', route, { filename: path.basename(localPath) });
        const presignedUrl = pre?.presignedUrl || pre?.uploadUrl;
        const publicUrl = pre?.publicUrl || pre?.url;
        if (!presignedUrl || !publicUrl) continue;
        const put = await fetch(presignedUrl, {
          method: 'PUT',
          headers: { 'Content-Type': mime },
          body: buf,
        });
        if (!put.ok) throw new Error(`presigned PUT HTTP ${put.status}`);
        return publicUrl;
      } catch {
        // try next route
      }
    }
    throw primaryErr;
  }
}

/**
 * Create a scheduled (or immediate) post.
 * platform: 'instagram' | 'facebook'; facebook additionally needs pageId.
 */
async function createPost(apiKey, { platform, accountId, pageId, text, mediaUrls, scheduledTime }) {
  const target = { targetType: platform };
  if (platform === 'facebook') {
    if (!pageId) throw new Error('Facebook posts need a Page ID — set it in Settings.');
    target.pageId = String(pageId);
  }
  const body = {
    post: {
      accountId: String(accountId),
      target,
      content: { text, platform, mediaUrls },
    },
  };
  if (scheduledTime) body.scheduledTime = scheduledTime;
  return api(apiKey, 'POST', '/v2/posts', body);
}

module.exports = { listAccounts, uploadMedia, createPost };
