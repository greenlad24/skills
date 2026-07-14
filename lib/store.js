// Simple JSON persistence for the studio. Everything lives in data/db.json,
// uploaded/generated images live in data/files/.
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const DATA_DIR = path.join(ROOT, 'data');
const FILES_DIR = path.join(DATA_DIR, 'files');
const DB_PATH = path.join(DATA_DIR, 'db.json');

const DAY_KEYS = ['tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];

const DEFAULT_SETTINGS = {
  openaiApiKey: '',
  scheduler: 'buffer', // buffer | postiz
  bufferApiKey: '',
  cloudinaryCloudName: '',
  cloudinaryUploadPreset: '',
  postizApiKey: '',
  postizBaseUrl: 'https://api.postiz.com/public/v1',
  captionModel: 'gpt-4.1',
  imageQuality: 'high', // low | medium | high
  instagramIntegrationId: '',
  instagramIdentifier: 'instagram',
  facebookIntegrationId: '',
  facebookIdentifier: 'facebook',
  // Local time each poster gets published on its own day, per day override allowed.
  defaultPostTime: '17:00',
  postTimes: {}, // e.g. { friday: '15:30' }
  venueName: 'Vibration',
  venueBlurb: 'Live music bar — bands & singers five nights a week.',
};

function ensureDirs() {
  fs.mkdirSync(FILES_DIR, { recursive: true });
}

function emptyDay(dayKey) {
  return {
    day: dayKey,
    date: '', // yyyy-mm-dd, set when the week is created
    characters: [], // [{ id, file, name }]
    keyword: '',
    references: [], // [{ id, file, source }]
    info: {
      artistName: '',
      genres: '',
      showTime: '',
      special: '',
      mustWords: '',
      notes: '',
    },
    stylePreset: 'auto',
    generations: [], // [{ id, createdAt, variants: [{ file, label, prompt }] }]
    winner: '', // file path of chosen image
    captions: { instagram: '', facebook: '' },
    scheduled: null, // { at, instagram: {...}, facebook: {...} }
  };
}

// Local-timezone yyyy-mm-dd (toISOString would shift the date in UTC+ zones).
function ymd(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function emptyWeek(weekStart) {
  const days = {};
  const start = new Date(weekStart + 'T00:00:00');
  DAY_KEYS.forEach((key, i) => {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    days[key] = emptyDay(key);
    days[key].date = ymd(d);
  });
  return { weekStart, days };
}

function defaultDb() {
  return {
    settings: { ...DEFAULT_SETTINGS },
    voice: { profile: null, examples: [] },
    brand: { logoFile: '' },
    weeks: {},
    activeWeek: '',
  };
}

let db = null;

function load() {
  ensureDirs();
  if (db) return db;
  try {
    db = JSON.parse(fs.readFileSync(DB_PATH, 'utf8'));
  } catch {
    db = defaultDb();
  }
  // Backfill new settings keys after upgrades.
  db.settings = { ...DEFAULT_SETTINGS, ...db.settings };
  if (!db.voice) db.voice = { profile: null, examples: [] };
  if (!db.brand) db.brand = { logoFile: '' };
  if (!db.weeks) db.weeks = {};
  return db;
}

function save() {
  ensureDirs();
  fs.writeFileSync(DB_PATH, JSON.stringify(db, null, 2));
}

function getWeek(weekStart) {
  load();
  if (!db.weeks[weekStart]) {
    db.weeks[weekStart] = emptyWeek(weekStart);
    save();
  }
  return db.weeks[weekStart];
}

function getDay(weekStart, dayKey) {
  const week = getWeek(weekStart);
  const day = week.days[dayKey];
  if (!day) throw new Error(`Unknown day "${dayKey}"`);
  return day;
}

function newId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

// Saves a base64 data URL (or raw base64) to data/files, returns relative file name.
function saveFileFromBase64(base64, extHint) {
  ensureDirs();
  let ext = extHint || 'png';
  let data = base64;
  const m = /^data:([\w/+.-]+);base64,(.*)$/s.exec(base64);
  if (m) {
    const mime = m[1];
    data = m[2];
    ext = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp' }[mime] || ext;
  }
  const name = `${newId()}.${ext}`;
  fs.writeFileSync(path.join(FILES_DIR, name), Buffer.from(data, 'base64'));
  return name;
}

function saveFileFromBuffer(buf, ext) {
  ensureDirs();
  const name = `${newId()}.${ext || 'jpg'}`;
  fs.writeFileSync(path.join(FILES_DIR, name), buf);
  return name;
}

function filePath(name) {
  const resolved = path.resolve(FILES_DIR, name);
  if (!resolved.startsWith(path.resolve(FILES_DIR))) throw new Error('Bad file path');
  return resolved;
}

module.exports = {
  ymd,
  DAY_KEYS,
  DATA_DIR,
  FILES_DIR,
  load,
  save,
  getWeek,
  getDay,
  emptyWeek,
  newId,
  saveFileFromBase64,
  saveFileFromBuffer,
  filePath,
};
