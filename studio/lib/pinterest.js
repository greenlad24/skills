// Pinterest style search without an API key: uses Pinterest's public JSON
// resource endpoint, with an HTML-scrape fallback. Works from a normal home
// connection; Pinterest occasionally changes internals, hence two strategies
// plus manual reference upload in the UI as the final fallback.

const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';

function upgradePinUrl(url) {
  // Thumbnails come as .../236x/...; originals look best for reference use.
  return url.replace(/\/(236x|474x)\//, '/736x/');
}

async function searchViaResource(query) {
  const data = encodeURIComponent(
    JSON.stringify({ options: { query, scope: 'pins', page_size: 40 }, context: {} })
  );
  const sourceUrl = encodeURIComponent(`/search/pins/?q=${encodeURIComponent(query)}`);
  const url = `https://www.pinterest.com/resource/BaseSearchResource/get/?source_url=${sourceUrl}&data=${data}&_=${Date.now()}`;
  const res = await fetch(url, {
    headers: {
      'User-Agent': UA,
      Accept: 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
      'X-Pinterest-PWS-Handler': 'www/search/[scope].js',
    },
  });
  if (!res.ok) throw new Error(`Pinterest resource endpoint HTTP ${res.status}`);
  const json = await res.json();
  const results = json?.resource_response?.data?.results || [];
  const pins = [];
  for (const r of results) {
    const img = r?.images?.['736x']?.url || r?.images?.orig?.url;
    if (!img) continue;
    pins.push({
      id: String(r.id || pins.length),
      image: img,
      thumb: r?.images?.['236x']?.url || img,
      title: r?.grid_title || r?.title || '',
      link: r?.id ? `https://www.pinterest.com/pin/${r.id}/` : '',
    });
  }
  if (!pins.length) throw new Error('Pinterest resource endpoint returned no pins');
  return pins;
}

async function searchViaHtml(query) {
  const res = await fetch(`https://www.pinterest.com/search/pins/?q=${encodeURIComponent(query)}`, {
    headers: { 'User-Agent': UA, Accept: 'text/html' },
  });
  if (!res.ok) throw new Error(`Pinterest search page HTTP ${res.status}`);
  const html = await res.text();
  const re = /https:\/\/i\.pinimg\.com\/(?:236x|474x|736x|originals)\/[A-Za-z0-9/._-]+\.(?:jpg|jpeg|png|webp)/g;
  const seen = new Set();
  const pins = [];
  for (const m of html.matchAll(re)) {
    const url = upgradePinUrl(m[0]);
    // Dedup on the path after the size segment.
    const key = url.replace(/^https:\/\/i\.pinimg\.com\/[^/]+\//, '');
    if (seen.has(key)) continue;
    seen.add(key);
    pins.push({ id: String(pins.length), image: url, thumb: m[0], title: '', link: '' });
    if (pins.length >= 40) break;
  }
  if (!pins.length) throw new Error('No pins found in the search page');
  return pins;
}

async function searchPins(query) {
  try {
    return await searchViaResource(query);
  } catch (e1) {
    try {
      return await searchViaHtml(query);
    } catch (e2) {
      throw new Error(
        `Pinterest search failed (${e1.message}; fallback: ${e2.message}). ` +
        'You can still paste an image URL or upload a reference image manually.'
      );
    }
  }
}

/** Download a chosen pin image; returns { buffer, ext }. */
async function downloadImage(url) {
  const res = await fetch(url, { headers: { 'User-Agent': UA, Referer: 'https://www.pinterest.com/' } });
  if (!res.ok) throw new Error(`Could not download image (HTTP ${res.status})`);
  const buf = Buffer.from(await res.arrayBuffer());
  const ct = res.headers.get('content-type') || '';
  const ext = ct.includes('png') ? 'png' : ct.includes('webp') ? 'webp' : 'jpg';
  return { buffer: buf, ext };
}

module.exports = { searchPins, downloadImage };
