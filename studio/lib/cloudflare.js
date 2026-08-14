// Cloudflare Workers AI client — the verified 100%-free engine: every
// Cloudflare account gets 10,000 free "neurons" per day (renews at 00:00 UTC,
// no credit card). FLUX.2 models accept up to 4 reference images (each must
// be smaller than 512x512 — the app stores downscaled copies for this).
//
// Cost per 1024x1536 poster, against the 10,000 free daily neurons:
//   @cf/black-forest-labs/flux-2-klein-4b  ≈ 175  (~57 posters/day, fastest, weakest text)
//   @cf/black-forest-labs/flux-2-klein-9b  ≈ 1600 (~6 posters/day, good balance — default)
//   @cf/black-forest-labs/flux-2-dev       ≈ 7000 (~1 poster/day, best typography)
const API = 'https://api.cloudflare.com/client/v4/accounts';

/**
 * Generate one poster. images: [{buffer, mime, name}] — pass the SMALL
 * (<512px) variants; only the first 4 are sent (API limit).
 * Returns an image Buffer.
 */
async function generateImage({ accountId, apiToken, model, prompt, images = [], width = 1024, height = 1536 }) {
  if (!accountId || !apiToken) {
    throw new Error('Cloudflare account ID / API token missing — free at dash.cloudflare.com (see Settings).');
  }
  const slug = model || '@cf/black-forest-labs/flux-2-klein-9b';

  const form = new FormData();
  form.append('prompt', prompt.slice(0, 2048));
  form.append('width', String(width));
  form.append('height', String(height));
  images.slice(0, 4).forEach((img, i) => {
    form.append(`input_image_${i}`, new Blob([img.buffer], { type: img.mime }), img.name || `ref-${i}.png`);
  });

  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 180000);
  try {
    const res = await fetch(`${API}/${encodeURIComponent(accountId)}/ai/run/${slug}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${apiToken}` },
      body: form,
      signal: ctrl.signal,
    });
    const ct = res.headers.get('content-type') || '';
    if (ct.startsWith('image/')) {
      if (!res.ok) throw new Error(`Cloudflare ${slug}: HTTP ${res.status}`);
      return Buffer.from(await res.arrayBuffer());
    }
    const text = await res.text();
    let json;
    try { json = JSON.parse(text); } catch { json = null; }
    if (!res.ok || json?.success === false) {
      const msg = json?.errors?.map((e) => e.message).join('; ') || text.slice(0, 300) || `HTTP ${res.status}`;
      throw new Error(`Cloudflare ${slug}: ${msg}` + (/quota|neuron|limit/i.test(msg) ? ' (free daily neurons reset at 00:00 UTC)' : ''));
    }
    const b64 = json?.result?.image || json?.result?.images?.[0] || (typeof json?.result === 'string' ? json.result : null);
    if (b64) return Buffer.from(b64.replace(/^data:[\w/+.-]+;base64,/, ''), 'base64');
    // Some models stream raw base64 as the body.
    if (/^[A-Za-z0-9+/=\s]+$/.test(text.slice(0, 200))) return Buffer.from(text.trim(), 'base64');
    throw new Error(`Cloudflare ${slug}: unrecognised response shape`);
  } finally {
    clearTimeout(t);
  }
}

module.exports = { generateImage };
