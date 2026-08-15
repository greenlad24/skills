// Google Vertex AI client — the door to Google's $300 / 90-day trial credits
// (which explicitly do NOT cover AI-Studio Gemini API keys, only Vertex).
// Runs Nano Banana Pro (gemini-3-pro-image) class models: GPT-Image-2-grade
// face preservation and typography, free while the trial credits last.
//
// Two auth modes:
//  1. Express-mode API key (simplest): key from the Vertex/Gemini Enterprise
//     express-mode console, sent as x-goog-api-key to the global endpoint.
//  2. Service-account JSON (full project with trial billing): the JSON key
//     file's contents pasted into Settings; we self-sign a JWT (pure Node
//     crypto, no dependencies) and exchange it for an OAuth token.
const crypto = require('crypto');
const { buildImageRequestBody, parseImageResponse } = require('./gemini');

let tokenCache = { token: null, exp: 0, keyId: '' };

function b64url(buf) {
  return Buffer.from(buf).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** Exchange a service-account key for an OAuth access token (cached ~50 min). */
async function serviceAccountToken(sa) {
  const cacheKey = sa.client_email + sa.private_key_id;
  if (tokenCache.token && tokenCache.keyId === cacheKey && Date.now() < tokenCache.exp) {
    return tokenCache.token;
  }
  const now = Math.floor(Date.now() / 1000);
  const header = b64url(JSON.stringify({ alg: 'RS256', typ: 'JWT', kid: sa.private_key_id }));
  const claims = b64url(JSON.stringify({
    iss: sa.client_email,
    scope: 'https://www.googleapis.com/auth/cloud-platform',
    aud: sa.token_uri || 'https://oauth2.googleapis.com/token',
    iat: now,
    exp: now + 3600,
  }));
  const signer = crypto.createSign('RSA-SHA256');
  signer.update(`${header}.${claims}`);
  const jwt = `${header}.${claims}.${b64url(signer.sign(sa.private_key))}`;

  const res = await fetch(sa.token_uri || 'https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `grant_type=${encodeURIComponent('urn:ietf:params:oauth:grant-type:jwt-bearer')}&assertion=${jwt}`,
  });
  const json = await res.json().catch(() => null);
  if (!res.ok || !json?.access_token) {
    throw new Error(`Vertex auth failed: ${json?.error_description || json?.error || `HTTP ${res.status}`}`);
  }
  tokenCache = { token: json.access_token, exp: Date.now() + 50 * 60 * 1000, keyId: cacheKey };
  return json.access_token;
}

/**
 * Generate one poster via Vertex AI. settings needs either vertexApiKey, or
 * vertexServiceAccountJson (paste of the downloaded key file). Returns Buffer.
 */
async function generateImage({ settings, prompt, images = [], aspectRatio = '2:3' }) {
  const model = settings.vertexModel || 'gemini-3-pro-image';
  const location = (settings.vertexLocation || 'global').trim() || 'global';
  const body = JSON.stringify(buildImageRequestBody(prompt, images, aspectRatio));
  const headers = { 'Content-Type': 'application/json' };
  let url;

  const saRaw = (settings.vertexServiceAccountJson || '').trim();
  if (saRaw) {
    let sa;
    try { sa = JSON.parse(saRaw); } catch { throw new Error('Vertex service-account JSON is not valid JSON — paste the whole downloaded key file.'); }
    if (!sa.client_email || !sa.private_key || !sa.project_id) {
      throw new Error('Vertex service-account JSON is missing client_email / private_key / project_id.');
    }
    headers.Authorization = `Bearer ${await serviceAccountToken(sa)}`;
    const host = location === 'global' ? 'aiplatform.googleapis.com' : `${location}-aiplatform.googleapis.com`;
    url = `https://${host}/v1/projects/${sa.project_id}/locations/${location}/publishers/google/models/${model}:generateContent`;
  } else if (settings.vertexApiKey) {
    headers['x-goog-api-key'] = settings.vertexApiKey;
    url = `https://aiplatform.googleapis.com/v1/publishers/google/models/${model}:generateContent`;
  } else {
    throw new Error('Vertex is not configured — add an express-mode API key or paste a service-account JSON in Settings.');
  }

  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 180000);
  try {
    const res = await fetch(url, { method: 'POST', headers, body, signal: ctrl.signal });
    const text = await res.text();
    let json;
    try { json = JSON.parse(text); } catch { json = null; }
    if (!res.ok) {
      throw new Error(`Vertex ${model}: ${json?.error?.message || text.slice(0, 300) || `HTTP ${res.status}`}`);
    }
    return parseImageResponse(json, 'Vertex');
  } finally {
    clearTimeout(t);
  }
}

module.exports = { generateImage };
