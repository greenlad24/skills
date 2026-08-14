// Segmind API client — cheap per-image access to many models. Default model:
// nano-banana (Google's image-edit model, ~$0.04/image, excellent typography
// and face preservation). API key: https://cloud.segmind.com → API keys.
const API = 'https://api.segmind.com/v1';

/**
 * Generate one poster. images: [{buffer, mime}] are sent as data URLs in
 * image_urls (Segmind accepts URLs or base64 data URIs). Returns image Buffer.
 */
async function generateImage({ apiKey, model, prompt, images = [], aspectRatio = '2:3' }) {
  if (!apiKey) throw new Error('Segmind API key is missing — add it in Settings.');
  const slug = model || 'nano-banana';
  const body = {
    prompt,
    aspect_ratio: aspectRatio,
  };
  if (images.length) {
    body.image_urls = images.slice(0, 10).map((img) => `data:${img.mime};base64,${img.buffer.toString('base64')}`);
  }

  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 180000);
  try {
    const res = await fetch(`${API}/${slug}`, {
      method: 'POST',
      headers: { 'x-api-key': apiKey, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    const ct = res.headers.get('content-type') || '';
    if (!res.ok) {
      const text = await res.text();
      let msg;
      try { msg = JSON.parse(text)?.error || text; } catch { msg = text; }
      throw new Error(`Segmind ${slug}: ${String(msg).slice(0, 300) || `HTTP ${res.status}`}`);
    }
    // Segmind returns either raw image bytes or JSON with base64/URL fields.
    if (ct.startsWith('image/')) {
      return Buffer.from(await res.arrayBuffer());
    }
    const json = await res.json();
    const b64 = json?.image || json?.images?.[0] || json?.output?.image;
    if (typeof b64 === 'string' && !b64.startsWith('http')) {
      return Buffer.from(b64.replace(/^data:[\w/+.-]+;base64,/, ''), 'base64');
    }
    const url = typeof b64 === 'string' ? b64 : json?.output?.[0] || json?.image_url;
    if (typeof url === 'string' && url.startsWith('http')) {
      const imgRes = await fetch(url);
      if (!imgRes.ok) throw new Error(`Segmind result download failed (HTTP ${imgRes.status})`);
      return Buffer.from(await imgRes.arrayBuffer());
    }
    throw new Error(`Segmind ${slug}: unrecognised response shape`);
  } finally {
    clearTimeout(t);
  }
}

module.exports = { generateImage };
