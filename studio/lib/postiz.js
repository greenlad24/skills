// Postiz API client — schedules the finished posters to Instagram and
// Facebook. Works with Postiz cloud (https://api.postiz.com/public/v1) or a
// self-hosted instance ({backend-url}/public/v1). Docs: https://docs.postiz.com/public-api
const fs = require('fs');
const path = require('path');

const DEFAULT_BASE = 'https://api.postiz.com/public/v1';

function baseUrl(settings) {
  return (settings?.postizBaseUrl || DEFAULT_BASE).replace(/\/+$/, '');
}

async function api(apiKey, base, method, route, body, isForm = false) {
  if (!apiKey) throw new Error('Postiz API key is missing — add it in Settings.');
  const headers = { Authorization: apiKey };
  if (body && !isForm) headers['Content-Type'] = 'application/json';
  const res = await fetch(`${base}${route}`, {
    method,
    headers,
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  });
  const text = await res.text();
  let json;
  try { json = JSON.parse(text); } catch { json = null; }
  if (!res.ok) {
    const msg = json?.message || json?.error || text.slice(0, 300) || `HTTP ${res.status}`;
    throw new Error(`Postiz ${route}: ${Array.isArray(msg) ? msg.join('; ') : msg}`);
  }
  return json;
}

/** List connected channels: [{ id, name, identifier, picture, disabled }] */
async function listIntegrations(apiKey, settings) {
  const json = await api(apiKey, baseUrl(settings), 'GET', '/integrations');
  return Array.isArray(json) ? json : json?.integrations || [];
}

/** Upload a local image; returns the media object ({ id, path, ... }). */
async function uploadMedia(apiKey, settings, localPath) {
  const buf = fs.readFileSync(localPath);
  const ext = path.extname(localPath).toLowerCase();
  const mime = { '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp' }[ext] || 'image/png';
  const form = new FormData();
  form.append('file', new Blob([buf], { type: mime }), path.basename(localPath));
  const json = await api(apiKey, baseUrl(settings), 'POST', '/upload', form, true);
  if (!json?.id) throw new Error('Postiz /upload returned no media id');
  return json;
}

/**
 * Schedule one post on one channel.
 * integration: { id, identifier } from listIntegrations (identifier drives
 * the platform-specific settings, e.g. instagram needs post_type).
 */
async function createPost(apiKey, settings, { integration, text, media, scheduledTime }) {
  const ident = integration.identifier || '';
  const postSettings = { __type: ident };
  if (ident.startsWith('instagram')) postSettings.post_type = 'post';
  const body = {
    type: scheduledTime ? 'schedule' : 'now',
    date: scheduledTime || new Date().toISOString(),
    shortLink: false,
    tags: [],
    posts: [
      {
        integration: { id: String(integration.id) },
        value: [
          {
            content: text,
            image: (media || []).map((m) => ({ id: m.id, path: m.path })),
          },
        ],
        settings: postSettings,
      },
    ],
  };
  return api(apiKey, baseUrl(settings), 'POST', '/posts', body);
}

module.exports = { listIntegrations, uploadMedia, createPost, DEFAULT_BASE };
