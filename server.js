#!/usr/bin/env node
// Vibration Poster Studio — local server. Zero dependencies, Node 18+.
const http = require('http');
const fs = require('fs');
const path = require('path');

const store = require('./lib/store');
const { STYLE_PRESETS, VARIANT_TAKES, buildPosterPrompt } = require('./lib/prompt');
const openai = require('./lib/openaiClient');
const pinterest = require('./lib/pinterest');
const blotato = require('./lib/blotato');

const PORT = process.env.PORT || 5713;
const PUBLIC_DIR = path.join(__dirname, 'public');
const ASSETS_DIR = path.join(__dirname, 'assets');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

function nodeMajor() {
  return parseInt(process.versions.node.split('.')[0], 10);
}

// ---------- helpers ----------

function sendJson(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) });
  res.end(body);
}

function sendFile(res, filePath) {
  fs.stat(filePath, (err, stat) => {
    if (err || !stat.isFile()) {
      res.writeHead(404);
      return res.end('Not found');
    }
    res.writeHead(200, {
      'Content-Type': MIME[path.extname(filePath).toLowerCase()] || 'application/octet-stream',
      'Content-Length': stat.size,
      'Cache-Control': 'no-cache',
    });
    fs.createReadStream(filePath).pipe(res);
  });
}

function readBody(req, limitMb = 80) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', (c) => {
      size += c.length;
      if (size > limitMb * 1024 * 1024) {
        reject(new Error('Request too large'));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on('end', () => {
      if (!chunks.length) return resolve({});
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));
      } catch (e) {
        reject(new Error('Invalid JSON body'));
      }
    });
    req.on('error', reject);
  });
}

function safeStatic(base, urlPath) {
  const resolved = path.resolve(base, '.' + urlPath);
  if (!resolved.startsWith(path.resolve(base))) return null;
  return resolved;
}

function localIso(dateStr, timeStr) {
  // dateStr yyyy-mm-dd + timeStr HH:MM in the machine's local timezone → ISO 8601 UTC.
  const [y, m, d] = dateStr.split('-').map(Number);
  const [hh, mm] = (timeStr || '17:00').split(':').map(Number);
  return new Date(y, m - 1, d, hh, mm, 0).toISOString();
}

function redactedSettings(s) {
  const mask = (k) => (k ? `set (…${k.slice(-4)})` : '');
  return { ...s, openaiApiKey: mask(s.openaiApiKey), blotatoApiKey: mask(s.blotatoApiKey) };
}

// Collect the reference images attached to a generation call, with a manifest
// so the prompt can talk about them by position.
function collectInputImages(db, day, preset) {
  const files = [];
  const manifest = [];
  for (const c of day.characters) {
    files.push(store.filePath(c.file));
    manifest.push(`PERFORMER photo${day.characters.length > 1 ? ` (${c.name || 'performer'})` : ''} — the hero of the poster`);
  }
  if (db.brand.logoFile) {
    files.push(store.filePath(db.brand.logoFile));
    manifest.push('VENUE logo — the circular V "VIBRATION" badge, reproduce exactly');
  }
  for (const r of day.references) {
    files.push(store.filePath(r.file));
    manifest.push('STYLE reference — match its art direction, palette and typography voice');
  }
  if (preset && preset.file) {
    files.push(path.join(ASSETS_DIR, 'style-presets', preset.file));
    manifest.push(`STYLE reference — a past "${preset.name}" Vibration poster; match its brand feel`);
  }
  return { files, manifest };
}

// ---------- API routes ----------

const routes = [];
function route(method, pattern, handler) {
  routes.push({ method, pattern, handler });
}

route('GET', /^\/api\/bootstrap$/, async () => {
  const db = store.load();
  if (!db.activeWeek) {
    // Default to the upcoming (or current) Tuesday.
    const now = new Date();
    const dow = now.getDay(); // 0 Sun ... 6 Sat
    const diff = (2 - dow + 7) % 7; // days until Tuesday
    const tue = new Date(now);
    tue.setDate(now.getDate() + diff);
    db.activeWeek = store.ymd(tue);
    store.getWeek(db.activeWeek);
    store.save();
  }
  return {
    settings: redactedSettings(db.settings),
    voice: { hasProfile: !!db.voice.profile, examplesCount: db.voice.examples.length, profile: db.voice.profile },
    brand: db.brand,
    activeWeek: db.activeWeek,
    week: store.getWeek(db.activeWeek),
    presets: Object.entries(STYLE_PRESETS).map(([id, p]) => ({ id, name: p.name, file: p.file })),
    variantTakes: VARIANT_TAKES.map((v) => v.label),
    weeks: Object.keys(store.load().weeks).sort(),
    nodeOk: nodeMajor() >= 18,
  };
});

route('POST', /^\/api\/week$/, async (m, body) => {
  const db = store.load();
  let start = body.weekStart;
  if (!start) throw new Error('weekStart required (yyyy-mm-dd)');
  // Snap to Tuesday.
  const d = new Date(start + 'T00:00:00');
  const shift = (2 - d.getDay() + 7) % 7;
  d.setDate(d.getDate() + shift);
  start = store.ymd(d);
  db.activeWeek = start;
  const week = store.getWeek(start);
  store.save();
  return { activeWeek: start, week, weeks: Object.keys(db.weeks).sort() };
});

route('PATCH', /^\/api\/week\/([\d-]+)\/day\/(\w+)$/, async (m, body) => {
  const day = store.getDay(m[1], m[2]);
  const allowed = ['keyword', 'stylePreset', 'winner'];
  for (const k of allowed) if (k in body) day[k] = body[k];
  if (body.info) day.info = { ...day.info, ...body.info };
  if (body.captions) day.captions = { ...day.captions, ...body.captions };
  store.save();
  return { day };
});

// Upload character or reference images: { images: [{ name, dataUrl }], kind }
route('POST', /^\/api\/week\/([\d-]+)\/day\/(\w+)\/images$/, async (m, body) => {
  const day = store.getDay(m[1], m[2]);
  const kind = body.kind === 'reference' ? 'references' : 'characters';
  for (const img of body.images || []) {
    const file = store.saveFileFromBase64(img.dataUrl);
    day[kind].push({ id: store.newId(), file, name: img.name || '', source: 'upload' });
  }
  store.save();
  return { day };
});

route('DELETE', /^\/api\/week\/([\d-]+)\/day\/(\w+)\/images\/(\w+)$/, async (m) => {
  const day = store.getDay(m[1], m[2]);
  for (const kind of ['characters', 'references']) {
    day[kind] = day[kind].filter((x) => x.id !== m[3]);
  }
  store.save();
  return { day };
});

route('GET', /^\/api\/pinterest\/search$/, async (m, body, query) => {
  const q = query.get('q');
  if (!q) throw new Error('Missing query');
  const pins = await pinterest.searchPins(q);
  return { pins };
});

// Save a chosen pin (or any image URL) as a style reference for the day.
route('POST', /^\/api\/week\/([\d-]+)\/day\/(\w+)\/reference-from-url$/, async (m, body) => {
  const day = store.getDay(m[1], m[2]);
  const { buffer, ext } = await pinterest.downloadImage(body.url);
  const file = store.saveFileFromBuffer(buffer, ext);
  day.references.push({ id: store.newId(), file, name: body.title || 'pinterest', source: body.url });
  store.save();
  return { day };
});

route('POST', /^\/api\/week\/([\d-]+)\/day\/(\w+)\/generate$/, async (m, body) => {
  const db = store.load();
  const day = store.getDay(m[1], m[2]);
  const presetId = day.stylePreset && day.stylePreset !== 'auto' ? day.stylePreset : null;
  const preset = presetId ? STYLE_PRESETS[presetId] : null;
  if (!preset && day.references.length === 0) {
    throw new Error('Pick a style preset or add at least one style reference first.');
  }
  const { files, manifest } = collectInputImages(db, day, preset);
  const count = Math.min(Math.max(body.count || 3, 1), 3);

  const jobs = Array.from({ length: count }, (_, i) => {
    const prompt = buildPosterPrompt({
      day,
      settings: db.settings,
      preset,
      variantIndex: i,
      imageManifest: manifest,
    });
    return openai
      .generatePoster({
        apiKey: db.settings.openaiApiKey || process.env.OPENAI_API_KEY,
        prompt,
        inputImages: files,
        quality: db.settings.imageQuality,
      })
      .then((b64) => ({ ok: true, b64, prompt, label: VARIANT_TAKES[i].label }))
      .catch((e) => ({ ok: false, error: e.message, label: VARIANT_TAKES[i].label }));
  });

  const results = await Promise.all(jobs);
  const okOnes = results.filter((r) => r.ok);
  if (!okOnes.length) {
    throw new Error('All variations failed: ' + results.map((r) => `${r.label}: ${r.error}`).join(' | '));
  }
  const generation = {
    id: store.newId(),
    createdAt: new Date().toISOString(),
    variants: okOnes.map((r) => ({
      file: store.saveFileFromBase64(r.b64, 'png'),
      label: r.label,
      prompt: r.prompt,
    })),
    errors: results.filter((r) => !r.ok).map((r) => `${r.label}: ${r.error}`),
  };
  day.generations.push(generation);
  store.save();
  return { day, generation };
});

route('POST', /^\/api\/week\/([\d-]+)\/day\/(\w+)\/captions$/, async (m) => {
  const db = store.load();
  const day = store.getDay(m[1], m[2]);
  const out = await openai.generateCaptions({
    apiKey: db.settings.openaiApiKey || process.env.OPENAI_API_KEY,
    model: db.settings.captionModel,
    voice: db.voice.profile,
    examples: db.voice.examples,
    day,
    settings: db.settings,
  });
  day.captions = { instagram: out.instagram || '', facebook: out.facebook || '' };
  store.save();
  return { day };
});

route('POST', /^\/api\/voice\/analyze$/, async (m, body) => {
  const db = store.load();
  const raw = (body.captions || '').trim();
  if (!raw) throw new Error('Paste at least one past caption first.');
  const examples = raw.split(/\n\s*---+\s*\n|\n{3,}/).map((s) => s.trim()).filter(Boolean);
  const profile = await openai.analyzeVoice({
    apiKey: db.settings.openaiApiKey || process.env.OPENAI_API_KEY,
    model: db.settings.captionModel,
    captions: examples.map((e, i) => `--- caption ${i + 1} ---\n${e}`).join('\n'),
  });
  db.voice = { profile, examples };
  store.save();
  return { voice: { hasProfile: true, examplesCount: examples.length, profile } };
});

route('POST', /^\/api\/brand\/logo$/, async (m, body) => {
  const db = store.load();
  db.brand.logoFile = body.dataUrl ? store.saveFileFromBase64(body.dataUrl) : '';
  store.save();
  return { brand: db.brand };
});

route('GET', /^\/api\/settings$/, async () => {
  const db = store.load();
  return { settings: redactedSettings(db.settings) };
});

route('PUT', /^\/api\/settings$/, async (m, body) => {
  const db = store.load();
  const s = body.settings || {};
  for (const k of Object.keys(db.settings)) {
    if (!(k in s)) continue;
    // Ignore masked key round-trips.
    if ((k === 'openaiApiKey' || k === 'blotatoApiKey') && /^set \(/.test(s[k])) continue;
    db.settings[k] = s[k];
  }
  store.save();
  return { settings: redactedSettings(db.settings) };
});

route('GET', /^\/api\/blotato\/accounts$/, async () => {
  const db = store.load();
  const accounts = await blotato.listAccounts(db.settings.blotatoApiKey || process.env.BLOTATO_API_KEY);
  return { accounts };
});

// Schedule the winners: { days: ['tuesday', ...], platforms: ['instagram','facebook'] }
route('POST', /^\/api\/week\/([\d-]+)\/schedule$/, async (m, body) => {
  const db = store.load();
  const week = store.getWeek(m[1]);
  const apiKey = db.settings.blotatoApiKey || process.env.BLOTATO_API_KEY;
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
      const scheduledTime = localIso(day.date, timeStr);
      const mediaUrl = await blotato.uploadMedia(apiKey, store.filePath(day.winner));
      r.steps.push('media uploaded');
      day.scheduled = day.scheduled || {};
      day.scheduled.at = scheduledTime;

      if (platforms.includes('instagram')) {
        if (!db.settings.instagramAccountId) throw new Error('Instagram account ID not set (Settings)');
        const post = await blotato.createPost(apiKey, {
          platform: 'instagram',
          accountId: db.settings.instagramAccountId,
          text: day.captions.instagram || day.captions.facebook,
          mediaUrls: [mediaUrl],
          scheduledTime,
        });
        day.scheduled.instagram = { submissionId: post?.postSubmissionId || post?.id || 'submitted', at: scheduledTime };
        r.steps.push('instagram scheduled');
      }
      if (platforms.includes('facebook')) {
        if (!db.settings.facebookAccountId || !db.settings.facebookPageId) {
          throw new Error('Facebook account/page ID not set (Settings)');
        }
        const post = await blotato.createPost(apiKey, {
          platform: 'facebook',
          accountId: db.settings.facebookAccountId,
          pageId: db.settings.facebookPageId,
          text: day.captions.facebook || day.captions.instagram,
          mediaUrls: [mediaUrl],
          scheduledTime,
        });
        day.scheduled.facebook = { submissionId: post?.postSubmissionId || post?.id || 'submitted', at: scheduledTime };
        r.steps.push('facebook scheduled');
      }
      r.ok = true;
      store.save();
    } catch (e) {
      r.error = e.message;
      store.save();
    }
  }
  return { results, week };
});

// ---------- server ----------

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const pathname = decodeURIComponent(url.pathname);

  try {
    // API
    for (const r of routes) {
      if (req.method !== r.method) continue;
      const m = r.pattern.exec(pathname);
      if (!m) continue;
      const body = ['POST', 'PUT', 'PATCH'].includes(req.method) ? await readBody(req) : {};
      const out = await r.handler(m, body, url.searchParams);
      return sendJson(res, 200, out);
    }

    // Files
    if (pathname.startsWith('/files/')) {
      const p = safeStatic(store.FILES_DIR, pathname.slice('/files'.length));
      if (p) return sendFile(res, p);
    }
    if (pathname.startsWith('/assets/')) {
      const p = safeStatic(ASSETS_DIR, pathname.slice('/assets'.length));
      if (p) return sendFile(res, p);
    }
    const staticPath = pathname === '/' ? '/index.html' : pathname;
    const p = safeStatic(PUBLIC_DIR, staticPath);
    if (p && fs.existsSync(p) && fs.statSync(p).isFile()) return sendFile(res, p);

    res.writeHead(404);
    res.end('Not found');
  } catch (e) {
    if (pathname.startsWith('/api/')) return sendJson(res, 500, { error: e.message });
    res.writeHead(500);
    res.end(e.message);
  }
});

if (nodeMajor() < 18) {
  console.error(`\n  Node ${process.versions.node} is too old — please install Node 18 or newer from https://nodejs.org\n`);
  process.exit(1);
}

server.listen(PORT, () => {
  console.log('');
  console.log('  ██  Vibration Poster Studio');
  console.log(`  ██  Open  http://localhost:${PORT}  in your browser`);
  console.log('');
});
