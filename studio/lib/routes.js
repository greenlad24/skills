// All API route logic, shared by the local server (server.js) and the Netlify
// Function (netlify/functions/api.mjs). Handlers get (match, body, query, ctx)
// where ctx = { origin, loadAsset(relPath) -> Buffer } and return a JSON-able
// object, or { __file: {buffer, mime} } for binary responses.
const store = require('./store');
const { STYLE_PRESETS, VARIANT_TAKES, buildPosterPrompt } = require('./prompt');
const imagegen = require('./imagegen');
const captionsLib = require('./captions');
const pinterest = require('./pinterest');
const postiz = require('./postiz');
const bufferApi = require('./buffer');
const imagehost = require('./imagehost');

const routes = [];
function route(method, pattern, handler) {
  routes.push({ method, pattern, handler });
}

// yyyy-mm-dd + HH:MM -> ISO UTC. Uses settings.postTimezone (e.g. "+07:00")
// when set — essential on Netlify, whose servers run in UTC.
function localIso(settings, dateStr, timeStr) {
  const time = timeStr || settings.defaultPostTime || '17:00';
  const tz = (settings.postTimezone || '').trim();
  if (/^[+-]\d{2}:\d{2}$/.test(tz)) {
    return new Date(`${dateStr}T${time}:00${tz}`).toISOString();
  }
  const [y, m, d] = dateStr.split('-').map(Number);
  const [hh, mm] = time.split(':').map(Number);
  return new Date(y, m - 1, d, hh, mm, 0).toISOString();
}

function redactedSettings(s) {
  const out = { ...s };
  for (const k of store.SECRET_KEYS) out[k] = s[k] ? `set (…${s[k].slice(-4)})` : '';
  return out;
}

// Cloudflare's FLUX.2 models accept at most 4 reference images, each smaller
// than 512x512 — so for that engine we use the downscaled copies (made by the
// browser at upload time / preset thumbnails) and keep only the 4 most
// important images. Other engines get the full-resolution originals.
async function collectInputImages(ctx, db, day, preset) {
  const small = (db.settings.imageEngine || 'cloudflare') === 'cloudflare';
  const chars = day.characters.map((c) => ({
    file: small && c.thumbFile ? c.thumbFile : c.file,
    manifest: `PERFORMER photo${day.characters.length > 1 ? ` (${c.name || 'performer'})` : ''} — the hero of the poster`,
  }));
  const styles = day.references.map((r) => ({
    file: small && r.thumbFile ? r.thumbFile : r.file,
    manifest: 'STYLE reference — match its art direction, palette and typography voice',
  }));
  if (preset && preset.file) {
    styles.push({
      asset: small
        ? `assets/style-presets/thumbs/${preset.file.replace(/\.jpg$/, '.png')}`
        : `assets/style-presets/${preset.file}`,
      manifest: `STYLE reference — a past "${preset.name}" Vibration poster; match its brand feel`,
    });
  }
  const logoFile = small && db.brand.logoThumbFile ? db.brand.logoThumbFile : db.brand.logoFile;
  const logo = logoFile ? { file: logoFile, manifest: 'VENUE logo — the circular V "VIBRATION" badge, reproduce exactly' } : null;

  // Under Cloudflare's 4-image cap keep: hero photos (max 2) → one style anchor
  // → logo → any remaining styles. Other engines get everything.
  const entries = small
    ? [...chars.slice(0, 2), styles[0], logo, ...styles.slice(1)].filter(Boolean).slice(0, 4)
    : [...chars, logo, ...styles].filter(Boolean);

  const picked = entries;
  const images = [];
  const manifest = [];
  for (const e of picked) {
    if (e.file) {
      images.push(await store.readFile(e.file));
    } else {
      const buf = await ctx.loadAsset(e.asset);
      images.push({ buffer: buf, mime: e.asset.endsWith('.png') ? 'image/png' : 'image/jpeg', name: e.asset.split('/').pop() });
    }
    manifest.push(e.manifest);
  }
  return { images, manifest };
}

// ---------- routes ----------

route('GET', /^\/api\/bootstrap$/, async (m, body, query, ctx) => {
  const db = await store.load();
  if (!db.activeWeek) {
    const now = new Date();
    const diff = (2 - now.getDay() + 7) % 7;
    const tue = new Date(now);
    tue.setDate(now.getDate() + diff);
    db.activeWeek = store.ymd(tue);
  }
  store.getWeek(db, db.activeWeek);
  await store.save(db);
  return {
    settings: redactedSettings(db.settings),
    voice: { hasProfile: !!db.voice.profile, examplesCount: db.voice.examples.length, profile: db.voice.profile },
    brand: db.brand,
    activeWeek: db.activeWeek,
    week: store.getWeek(db, db.activeWeek),
    presets: Object.entries(STYLE_PRESETS).map(([id, p]) => ({ id, name: p.name, file: p.file })),
    variantTakes: VARIANT_TAKES.map((v) => v.label),
    weeks: Object.keys(db.weeks).sort(),
  };
});

route('POST', /^\/api\/week$/, async (m, body) => {
  const db = await store.load();
  let start = body.weekStart;
  if (!start) throw new Error('weekStart required (yyyy-mm-dd)');
  const d = new Date(start + 'T00:00:00');
  d.setDate(d.getDate() + ((2 - d.getDay() + 7) % 7));
  start = store.ymd(d);
  db.activeWeek = start;
  const week = store.getWeek(db, start);
  await store.save(db);
  return { activeWeek: start, week, weeks: Object.keys(db.weeks).sort() };
});

route('PATCH', /^\/api\/week\/([\d-]+)\/day\/(\w+)$/, async (m, body) => {
  const db = await store.load();
  const day = store.getDay(db, m[1], m[2]);
  for (const k of ['keyword', 'stylePreset', 'winner']) if (k in body) day[k] = body[k];
  if (body.info) day.info = { ...day.info, ...body.info };
  if (body.captions) day.captions = { ...day.captions, ...body.captions };
  await store.save(db);
  return { day };
});

route('POST', /^\/api\/week\/([\d-]+)\/day\/(\w+)\/images$/, async (m, body) => {
  const db = await store.load();
  const day = store.getDay(db, m[1], m[2]);
  const kind = body.kind === 'reference' ? 'references' : 'characters';
  for (const img of body.images || []) {
    const file = await store.saveFileFromBase64(img.dataUrl);
    const thumbFile = img.thumbDataUrl ? await store.saveFileFromBase64(img.thumbDataUrl) : '';
    day[kind].push({ id: store.newId(), file, thumbFile, name: img.name || '', source: 'upload' });
  }
  await store.save(db);
  return { day };
});

route('DELETE', /^\/api\/week\/([\d-]+)\/day\/(\w+)\/images\/(\w+)$/, async (m) => {
  const db = await store.load();
  const day = store.getDay(db, m[1], m[2]);
  for (const kind of ['characters', 'references']) day[kind] = day[kind].filter((x) => x.id !== m[3]);
  await store.save(db);
  return { day };
});

route('GET', /^\/api\/pinterest\/search$/, async (m, body, query) => {
  const q = query.get('q');
  if (!q) throw new Error('Missing query');
  return { pins: await pinterest.searchPins(q) };
});

route('POST', /^\/api\/week\/([\d-]+)\/day\/(\w+)\/reference-from-url$/, async (m, body) => {
  const db = await store.load();
  const day = store.getDay(db, m[1], m[2]);
  const { buffer, ext } = await pinterest.downloadImage(body.url);
  const file = await store.saveFileFromBuffer(buffer, ext);
  // Pinterest also serves a small (<512px) variant — keep it for engines with
  // input-size limits (Cloudflare).
  let thumbFile = '';
  if (body.thumbUrl && body.thumbUrl !== body.url) {
    try {
      const t = await pinterest.downloadImage(body.thumbUrl);
      thumbFile = await store.saveFileFromBuffer(t.buffer, t.ext);
    } catch { /* thumb is best-effort */ }
  }
  day.references.push({ id: store.newId(), file, thumbFile, name: body.title || 'pinterest', source: body.url });
  await store.save(db);
  return { day };
});

/**
 * The full (slow: 1-5 min) generation pipeline for one day. Used directly by
 * the local server and by the Netlify Background Function.
 */
async function runGeneration(ctx, weekStart, dayKey, { count = 3, variantIndex = null } = {}) {
  const db = await store.load();
  const day = store.getDay(db, weekStart, dayKey);
  const presetId = day.stylePreset && day.stylePreset !== 'auto' ? day.stylePreset : null;
  const preset = presetId ? STYLE_PRESETS[presetId] : null;
  if (!preset && day.references.length === 0) {
    throw new Error('Pick a style preset or add at least one style reference first.');
  }
  const { images, manifest } = await collectInputImages(ctx, db, day, preset);
  const n = Math.min(Math.max(count, 1), 3);

  const takes = variantIndex != null ? [variantIndex] : Array.from({ length: n }, (_, i) => i);
  const results = await Promise.all(
    takes.map((i) => {
      const prompt = buildPosterPrompt({ day, settings: db.settings, preset, variantIndex: i, imageManifest: manifest });
      return imagegen
        .generatePoster(db.settings, { prompt, images })
        .then((buf) => ({ ok: true, buf, prompt, label: VARIANT_TAKES[i].label }))
        .catch((e) => ({ ok: false, error: e.message, label: VARIANT_TAKES[i].label }));
    })
  );
  const okOnes = results.filter((r) => r.ok);
  if (!okOnes.length) {
    throw new Error('All variations failed: ' + results.map((r) => `${r.label}: ${r.error}`).join(' | '));
  }
  const variants = [];
  for (const r of okOnes) {
    variants.push({ file: await store.saveFileFromBuffer(r.buf, 'png'), label: r.label, prompt: r.prompt });
  }

  // Re-read before mutating: generation is slow and other edits may have landed.
  const db2 = await store.load();
  const day2 = store.getDay(db2, weekStart, dayKey);
  const generation = {
    id: store.newId(),
    createdAt: new Date().toISOString(),
    variants,
    errors: results.filter((r) => !r.ok).map((r) => `${r.label}: ${r.error}`),
  };
  day2.generations.push(generation);
  await store.save(db2);
  return { day: day2, generation };
}

route('POST', /^\/api\/week\/([\d-]+)\/day\/(\w+)\/generate$/, async (m, body, query, ctx) =>
  runGeneration(ctx, m[1], m[2], body)
);

// Unified generation entry point. Locally it runs synchronously; on Netlify
// (where a synchronous function would time out after ~26s while gpt-image-2
// takes minutes) it tells the client to invoke the Background Function and
// poll the job record instead.
route('POST', /^\/api\/generate$/, async (m, body, query, ctx) => {
  if (ctx.serverless) return { background: true };
  const out = await runGeneration(ctx, body.week, body.day, body);
  return { ...out, background: false };
});

route('GET', /^\/api\/job\/([\w.-]+)$/, async (m) => {
  const job = await store.getAux(`jobs/${m[1]}`);
  return { job: job || { status: 'unknown' } };
});

// $0 manual mode: hand back the full designer prompts so the user can paste
// them (with the same photos) into a free web UI like Google AI Studio, then
// import the result as a variant via manual-variant below.
route('GET', /^\/api\/week\/([\d-]+)\/day\/(\w+)\/prompts$/, async (m, body, query, ctx) => {
  const db = await store.load();
  const day = store.getDay(db, m[1], m[2]);
  const presetId = day.stylePreset && day.stylePreset !== 'auto' ? day.stylePreset : null;
  const preset = presetId ? STYLE_PRESETS[presetId] : null;
  const { manifest } = await collectInputImages(ctx, db, day, preset);
  const prompts = VARIANT_TAKES.map((v, i) => ({
    label: v.label,
    text: buildPosterPrompt({ day, settings: db.settings, preset, variantIndex: i, imageManifest: manifest }),
  }));
  return { prompts, attachOrder: manifest };
});

route('POST', /^\/api\/week\/([\d-]+)\/day\/(\w+)\/manual-variant$/, async (m, body) => {
  if (!body.dataUrl) throw new Error('No image provided');
  const db = await store.load();
  const day = store.getDay(db, m[1], m[2]);
  const file = await store.saveFileFromBase64(body.dataUrl);
  day.generations.push({
    id: store.newId(),
    createdAt: new Date().toISOString(),
    variants: [{ file, label: 'Manual', prompt: '(made outside the app)' }],
    errors: [],
  });
  await store.save(db);
  return { day };
});

route('POST', /^\/api\/week\/([\d-]+)\/day\/(\w+)\/captions$/, async (m) => {
  const db = await store.load();
  const day = store.getDay(db, m[1], m[2]);
  const out = await captionsLib.generateCaptions(db.settings, {
    voice: db.voice.profile,
    examples: db.voice.examples,
    day,
  });
  const db2 = await store.load();
  const day2 = store.getDay(db2, m[1], m[2]);
  day2.captions = { instagram: out.instagram || '', facebook: out.facebook || '' };
  await store.save(db2);
  return { day: day2 };
});

route('POST', /^\/api\/voice\/analyze$/, async (m, body) => {
  const db = await store.load();
  const raw = (body.captions || '').trim();
  if (!raw) throw new Error('Paste at least one past caption first.');
  const examples = raw.split(/\n\s*---+\s*\n|\n{3,}/).map((s) => s.trim()).filter(Boolean);
  const profile = await captionsLib.analyzeVoice(
    db.settings,
    examples.map((e, i) => `--- caption ${i + 1} ---\n${e}`).join('\n')
  );
  const db2 = await store.load();
  db2.voice = { profile, examples };
  await store.save(db2);
  return { voice: { hasProfile: true, examplesCount: examples.length, profile } };
});

route('POST', /^\/api\/brand\/logo$/, async (m, body) => {
  const db = await store.load();
  db.brand.logoFile = body.dataUrl ? await store.saveFileFromBase64(body.dataUrl) : '';
  db.brand.logoThumbFile = body.thumbDataUrl ? await store.saveFileFromBase64(body.thumbDataUrl) : '';
  await store.save(db);
  return { brand: db.brand };
});

route('GET', /^\/api\/settings$/, async () => {
  const db = await store.load();
  return { settings: redactedSettings(db.settings) };
});

route('PUT', /^\/api\/settings$/, async (m, body) => {
  const db = await store.load();
  const s = body.settings || {};
  for (const k of Object.keys(db.settings)) {
    if (!(k in s)) continue;
    if (store.SECRET_KEYS.includes(k) && /^set \(/.test(s[k])) continue; // masked round-trip
    db.settings[k] = s[k];
  }
  await store.save(db);
  return { settings: redactedSettings(db.settings) };
});

route('GET', /^\/api\/channels$/, async () => {
  const db = await store.load();
  let channels;
  if (db.settings.scheduler === 'postiz') {
    channels = await postiz.listIntegrations(db.settings.postizApiKey || process.env.POSTIZ_API_KEY, db.settings);
  } else {
    channels = await bufferApi.listChannels(db.settings.bufferApiKey || process.env.BUFFER_API_KEY);
  }
  return { channels };
});

async function schedulePost(settings, { platform, text, postizMedia, publicImageUrl, scheduledTime }) {
  const channelId = platform === 'instagram' ? settings.instagramIntegrationId : settings.facebookIntegrationId;
  if (!channelId) throw new Error(`${platform} channel not set (Settings → Load my channels)`);
  if (settings.scheduler === 'postiz') {
    const post = await postiz.createPost(settings.postizApiKey || process.env.POSTIZ_API_KEY, settings, {
      integration: {
        id: channelId,
        identifier: (platform === 'instagram' ? settings.instagramIdentifier : settings.facebookIdentifier) || platform,
      },
      text,
      media: [postizMedia],
      scheduledTime,
    });
    return post?.[0]?.postId || post?.id || 'submitted';
  }
  const post = await bufferApi.createPost(settings.bufferApiKey || process.env.BUFFER_API_KEY, {
    channelId,
    text,
    imageUrl: publicImageUrl,
    dueAt: scheduledTime,
  });
  return post?.id || 'submitted';
}

route('POST', /^\/api\/week\/([\d-]+)\/schedule$/, async (m, body) => {
  const db = await store.load();
  const week = store.getWeek(db, m[1]);
  const platforms = body.platforms || ['instagram', 'facebook'];
  const wanted = body.days || store.DAY_KEYS;
  const results = [];

  for (const dayKey of wanted) {
    const day = week.days[dayKey];
    const r = { day: dayKey, ok: false, steps: [] };
    results.push(r);
    try {
      if (!day.winner) throw new Error('no winning poster selected');
      if (!day.captions.instagram && !day.captions.facebook) throw new Error('no captions generated');
      const timeStr = db.settings.postTimes[dayKey] || db.settings.defaultPostTime;
      const scheduledTime = localIso(db.settings, day.date, timeStr);
      const file = await store.readFile(day.winner);

      let postizMedia = null;
      let publicImageUrl = null;
      if (db.settings.scheduler === 'postiz') {
        postizMedia = await postiz.uploadMedia(db.settings.postizApiKey || process.env.POSTIZ_API_KEY, db.settings, file);
      } else {
        publicImageUrl = await imagehost.uploadPublicImage(db.settings, file);
      }
      r.steps.push('poster uploaded');
      day.scheduled = day.scheduled || {};
      day.scheduled.at = scheduledTime;

      for (const platform of ['instagram', 'facebook']) {
        if (!platforms.includes(platform)) continue;
        const text = platform === 'instagram'
          ? day.captions.instagram || day.captions.facebook
          : day.captions.facebook || day.captions.instagram;
        const postId = await schedulePost(db.settings, { platform, text, postizMedia, publicImageUrl, scheduledTime });
        day.scheduled[platform] = { postId, at: scheduledTime };
        r.steps.push(`${platform} scheduled`);
      }
      r.ok = true;
    } catch (e) {
      r.error = e.message;
    }
    await store.save(db);
  }
  return { results, week };
});

// Binary: stored files (uploads + generated posters).
route('GET', /^\/files\/([\w.-]+)$/, async (m) => {
  const file = await store.readFile(m[1]);
  return { __file: file };
});

/** Dispatch a request. Returns {status, json} or {status, file:{buffer,mime}} or null if no route matched. */
async function dispatch(method, pathname, body, query, ctx) {
  for (const r of routes) {
    if (method !== r.method) continue;
    const m = r.pattern.exec(pathname);
    if (!m) continue;
    const out = await r.handler(m, body || {}, query, ctx);
    if (out && out.__file) return { status: 200, file: out.__file };
    return { status: 200, json: out };
  }
  return null;
}

module.exports = { dispatch, localIso, redactedSettings, runGeneration };
