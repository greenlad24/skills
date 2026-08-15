// Storage-agnostic persistence. A "driver" supplies four async primitives so
// the same code runs on a local disk (server.js) and on Netlify Blobs
// (netlify/functions/api.mjs):
//   getJson(key) -> object|null      setJson(key, obj)
//   getFile(name) -> Buffer|null     putFile(name, buffer)
const DAY_KEYS = ['tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];

const DEFAULT_SETTINGS = {
  // image generation
  // openai     = GPT Image 2, best text + face fidelity, ~$0.03-0.06/image (default)
  // cloudflare = the verified 100%-free engine (10k neurons/day) — draft quality
  // gemini     = nano-banana class, ~$0.04/image (free tier for images was removed Dec 2025)
  // segmind    = aggregator, ~$0.04/image (requires a $10 top-up to start)
  // vertex     = Google $300/90-day trial credits -> Nano Banana Pro, free for ~3 months
  imageEngine: 'openai',
  openaiImageModel: 'gpt-image-2',
  vertexApiKey: '',
  vertexServiceAccountJson: '',
  vertexModel: 'gemini-3-pro-image',
  vertexLocation: 'global',
  cfAccountId: '',
  cfApiToken: '',
  cfModel: '@cf/black-forest-labs/flux-2-klein-9b',
  geminiApiKey: '',
  geminiModel: 'gemini-3.1-flash-image-preview',
  segmindApiKey: '',
  segmindModel: 'nano-banana',
  openaiApiKey: '',
  imageQuality: 'high', // openai only: low | medium | high
  // captions
  captionModel: 'gpt-4.1', // used when OpenAI key present; otherwise Gemini writes captions
  // scheduling
  scheduler: 'buffer', // buffer | postiz
  bufferApiKey: '',
  cloudinaryCloudName: '',
  cloudinaryUploadPreset: '',
  postizApiKey: '',
  postizBaseUrl: 'https://api.postiz.com/public/v1',
  instagramIntegrationId: '',
  instagramIdentifier: 'instagram',
  facebookIntegrationId: '',
  facebookIdentifier: 'facebook',
  defaultPostTime: '17:00',
  postTimes: {}, // e.g. { friday: '15:30' }
  // When hosted (Netlify runs in UTC), set the bar's UTC offset, e.g. "+07:00".
  // Empty = use the machine's local timezone (fine for the local app).
  postTimezone: '',
  venueName: 'Vibration',
  venueBlurb: 'Live music bar — bands & singers five nights a week.',
  onboarded: false,
};

const SECRET_KEYS = ['openaiApiKey', 'geminiApiKey', 'segmindApiKey', 'postizApiKey', 'bufferApiKey', 'cfApiToken', 'vertexApiKey', 'vertexServiceAccountJson'];

let driver = null;
function setDriver(d) { driver = d; }

// Local-timezone yyyy-mm-dd (toISOString would shift the date in UTC+ zones).
function ymd(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function emptyDay(dayKey) {
  return {
    day: dayKey,
    date: '',
    characters: [],
    keyword: '',
    references: [],
    info: { artistName: '', genres: '', showTime: '', special: '', mustWords: '', notes: '' },
    stylePreset: 'auto',
    generations: [],
    winner: '',
    captions: { instagram: '', facebook: '' },
    scheduled: null,
  };
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

// Small auxiliary JSON records (e.g. background-job status) stored beside the db.
async function getAux(key) {
  return driver.getJson(key);
}
async function setAux(key, obj) {
  await driver.setJson(key, obj);
}

async function load() {
  if (!driver) throw new Error('storage driver not initialised');
  const db = (await driver.getJson('db.json')) || defaultDb();
  db.settings = { ...DEFAULT_SETTINGS, ...db.settings };
  if (!db.voice) db.voice = { profile: null, examples: [] };
  if (!db.brand) db.brand = { logoFile: '' };
  if (!db.weeks) db.weeks = {};
  return db;
}

async function save(db) {
  await driver.setJson('db.json', db);
}

function getWeek(db, weekStart) {
  if (!db.weeks[weekStart]) db.weeks[weekStart] = emptyWeek(weekStart);
  return db.weeks[weekStart];
}

function getDay(db, weekStart, dayKey) {
  const day = getWeek(db, weekStart).days[dayKey];
  if (!day) throw new Error(`Unknown day "${dayKey}"`);
  return day;
}

function newId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

const MIME_BY_EXT = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp' };
function mimeForName(name) {
  return MIME_BY_EXT[String(name).split('.').pop().toLowerCase()] || 'image/png';
}

/** Save a base64 data URL (or raw base64) as a stored file; returns the file name. */
async function saveFileFromBase64(base64, extHint) {
  let ext = extHint || 'png';
  let data = base64;
  const m = /^data:([\w/+.-]+);base64,(.*)$/s.exec(base64);
  if (m) {
    data = m[2];
    ext = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp' }[m[1]] || ext;
  }
  const name = `${newId()}.${ext}`;
  await driver.putFile(name, Buffer.from(data, 'base64'));
  return name;
}

async function saveFileFromBuffer(buf, ext) {
  const name = `${newId()}.${ext || 'jpg'}`;
  await driver.putFile(name, buf);
  return name;
}

/** Read a stored file as {buffer, mime, name}; throws if missing. */
async function readFile(name) {
  if (!/^[\w.-]+$/.test(name)) throw new Error('Bad file name');
  const buffer = await driver.getFile(name);
  if (!buffer) throw new Error(`Stored file not found: ${name}`);
  return { buffer, mime: mimeForName(name), name };
}

module.exports = {
  DAY_KEYS,
  DEFAULT_SETTINGS,
  SECRET_KEYS,
  setDriver,
  ymd,
  load,
  save,
  getAux,
  setAux,
  getWeek,
  getDay,
  newId,
  mimeForName,
  saveFileFromBase64,
  saveFileFromBuffer,
  readFile,
};
