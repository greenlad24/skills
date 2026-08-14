/**
 * Reading a gig poster into a schedule entry.
 *
 * Groq does this, on its free tier — a month of posters is a few dozen calls.
 * Without GROQ_API_KEY the caller degrades to typing the details in by hand,
 * which is the only fallback: no key, no cost, no second provider to keep an
 * account with.
 */

/** The shape the editor expects back. Enforced by the API, not by parsing. */
export const EVENT_SCHEMA = {
  type: 'object',
  properties: {
    name: { type: 'string', description: 'The act or event name, as printed. Empty string if unreadable.' },
    on: { type: 'string', description: 'Date as YYYY-MM-DD, or empty string if the poster shows no date.' },
    dateText: { type: 'string', description: 'The date exactly as printed, e.g. "SAT 16 AUG" or "16/08". Empty if the poster shows no date.' },
    weekday: { type: 'string', description: 'The weekday printed with no calendar date, e.g. "FRIDAY" for a weekly night. Empty if the poster gives a real date.' },
    genre: { type: 'string', description: 'Genre or style, e.g. "Funk / Soul". Separate multiple with " / ". Empty if absent.' },
    description: { type: 'string', description: 'One or two inviting sentences for the event page that make someone want to come, true to what the poster shows.' },
    confident: { type: 'boolean', description: 'False if the poster was hard to read and the fields are a guess.' },
  },
  required: ['name', 'on', 'genre', 'description', 'confident'],
  additionalProperties: false,
};

const SYSTEM =
  'You read gig posters for Vibration, a live-music bar on Koh Samui, and turn them into '
  + 'schedule entries. Facts come only from the poster — never invent an act, a date, or a '
  + 'genre, and leave a field empty rather than guessing at it. The description is the one '
  + 'place you write rather than transcribe: it is the copy that sells the night. '
  + 'Answer with the JSON straight away; this is not a puzzle to work through.';

const askFor = (today) =>
  `Today is ${today}. Read this poster and return the event details.\n\n`
  + 'Dates: put the calendar date in "on" as YYYY-MM-DD, and whatever the poster literally '
  + 'prints in "dateText". If it shows a day and month but no year, choose the year that puts '
  + 'the date in the near future rather than the past. If it names only a weekday — a weekly '
  + 'night like "FREESTYLE FRIDAY" — put that weekday in "weekday" and leave "on" empty.\n\n'
  + 'Description: one or two sentences that make someone want to come out for this, written '
  + 'for the event page. Lead with what the night actually gives them — the sound, the room, '
  + 'the energy — and work in any detail the poster gives you, such as the start time or an '
  + 'open invitation to join in. Confident and inviting, never a list of facts, and never a '
  + 'claim the poster does not support.';

const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
const DAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];

/** Rejects 31 February and friends: a date is real only if it survives the round trip. */
function realDate(iso) {
  const d = new Date(`${iso}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === iso;
}

/**
 * Turns what a poster actually prints into an ISO date.
 *
 * Posters write dates every way there is — "SAT 16 AUG", "16/08", "August 16th"
 * — and dropping everything that is not already YYYY-MM-DD left the Date field
 * empty on posters that plainly carried one. Day comes before month in the
 * numeric form: that is how it is written here, and how the posters read.
 */
export function normaliseDate(raw, today) {
  const text = String(raw || '').trim().toLowerCase();
  if (!text) return '';
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return realDate(text) ? text : '';

  let day, month, year;
  let m = text.match(/(\d{1,2})\s*(?:st|nd|rd|th)?\s+([a-z]{3,})\.?,?\s*(\d{4})?/);
  if (m && MONTHS.includes(m[2].slice(0, 3))) {
    [day, month, year] = [+m[1], MONTHS.indexOf(m[2].slice(0, 3)), m[3] ? +m[3] : null];
  } else if ((m = text.match(/([a-z]{3,})\.?\s+(\d{1,2})\s*(?:st|nd|rd|th)?,?\s*(\d{4})?/))
             && MONTHS.includes(m[1].slice(0, 3))) {
    [month, day, year] = [MONTHS.indexOf(m[1].slice(0, 3)), +m[2], m[3] ? +m[3] : null];
  } else if ((m = text.match(/(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?/))) {
    day = +m[1];
    month = +m[2] - 1;
    year = m[3] ? (+m[3] < 100 ? 2000 + +m[3] : +m[3]) : null;
  } else {
    return '';
  }

  if (!(day >= 1 && day <= 31) || !(month >= 0 && month <= 11)) return '';
  const iso = (y) => `${y}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;

  if (year) return realDate(iso(year)) ? iso(year) : '';
  // A poster with no year means the coming one, not the one just gone.
  const thisYear = +today.slice(0, 4);
  for (const y of [thisYear, thisYear + 1]) {
    if (realDate(iso(y)) && iso(y) >= today) return iso(y);
  }
  return '';
}

/**
 * "FREESTYLE FRIDAY, 9PM–LATE" carries no date at all, so the next Friday is
 * the only sensible reading — leaving Date blank made a real event look like a
 * failed one. Recurring nights belong under Weekly entertainment, and the
 * editor says so rather than deciding for you.
 */
export function nextWeekday(raw, today) {
  const name = String(raw || '').trim().toLowerCase();
  const target = DAYS.findIndex((d) => name.startsWith(d.slice(0, 3)) && d.startsWith(name.slice(0, 3)));
  if (target < 0) return '';

  const start = new Date(`${today}T00:00:00Z`);
  if (Number.isNaN(start.getTime())) return '';
  const ahead = (target - start.getUTCDay() + 7) % 7;
  start.setUTCDate(start.getUTCDate() + ahead);
  return start.toISOString().slice(0, 10);
}

/** Normalise whatever the model returned into the fields the editor stores. */
function toEvent(data, today) {
  const printed = /^\d{4}-\d{2}-\d{2}$/.test(data.on) && realDate(data.on)
    ? data.on
    : normaliseDate(data.dateText, today);
  const weekly = !printed ? nextWeekday(data.weekday, today) : '';

  return {
    event: {
      name: String(data.name || ''),
      on: printed || weekly,
      genre: String(data.genre || ''),
      description: String(data.description || ''),
    },
    // A weekday with no date is a recurring night, not a one-off.
    recurring: Boolean(weekly),
    confident: data.confident !== false,
  };
}

/* ----------------------------- Groq ----------------------------- */

const GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions';

/**
 * qwen/qwen3.6-27b is the model Groq documents for vision. The others are
 * insurance only: Groq retires image model IDs, and trying the next name beats
 * going dark until someone redeploys. GROQ_MODEL pins one and skips the list.
 */
const GROQ_MODELS = [
  'qwen/qwen3.6-27b',
  'meta-llama/llama-4-scout-17b-16e-instruct',
  'meta-llama/llama-4-maverick-17b-128e-instruct',
];

/**
 * Whether the chosen model accepted a JSON schema, remembered for the life of
 * the function instance. A month of posters is one call each; without this,
 * every one of them would spend a rejected request rediscovering the answer.
 */
let schemaAccepted = null;

/** A request carrying an image URL may be up to 20 MB; base64 has to fit inside
    the request body, so anything sizeable goes by URL — /api/img is public and
    content-addressed, so the link is stable and safe to hand out. */
const INLINE_LIMIT = 3_500_000;

function groqImageUrl(bytes, mime, key) {
  if (bytes.length <= INLINE_LIMIT) return `data:${mime};base64,${bytes.toString('base64')}`;
  const site = process.env.DEPLOY_URL || process.env.URL;
  return site ? `${site}/api/img/${key}` : null;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * One request, with a single retry when Groq's free-tier rate limit bites.
 * The wait is capped well under the function timeout: a batch upload is
 * sequential, so a poster that has to queue is better than one that fails.
 */
async function groqPost(body, apiKey) {
  for (let attempt = 0; ; attempt += 1) {
    const res = await fetch(GROQ_URL, {
      method: 'POST',
      headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (res.status !== 429 || attempt > 0) return res;
    const wait = Math.min(4, Number(res.headers.get('retry-after')) || 2);
    await sleep(wait * 1000);
  }
}

function groqBody(model, imageUrl, today, structured) {
  return {
    model,
    temperature: 0,
    // Headroom for a model that reasons before it answers, without letting one
    // poster think for long enough to hit the function timeout.
    max_completion_tokens: 1200,
    response_format: structured
      ? { type: 'json_schema', json_schema: { name: 'gig_poster', schema: EVENT_SCHEMA, strict: true } }
      : { type: 'json_object' },
    messages: [
      {
        role: 'system',
        // Without schema enforcement the shape has to be spelled out instead.
        content: structured ? SYSTEM
          : `${SYSTEM}\n\nReply with JSON only, exactly these keys: `
            + '{"name": string, "on": "YYYY-MM-DD" or "", "dateText": string, '
            + '"weekday": string, "genre": string, "description": string, '
            + '"confident": boolean}.',
      },
      {
        role: 'user',
        content: [
          { type: 'image_url', image_url: { url: imageUrl } },
          { type: 'text', text: askFor(today) },
        ],
      },
    ],
  };
}

/** An error the editor can act on: "wait and retry" reads very differently from
    "this poster is unreadable", and only the reason tells them apart. */
function failure(reason, message, retryAfter = 0) {
  const error = new Error(message);
  error.reason = reason;
  error.retryAfter = retryAfter;
  return error;
}

/** True when the failure is about the model itself, so another one is worth trying. */
function isModelFault(status, text) {
  return (status === 404 || status === 400 || status === 403)
    && /model|decommission|not found|does not exist|unsupported/i.test(text);
}

/**
 * The documented vision model reasons before it answers, and that reasoning can
 * arrive in the reply, so the JSON is taken out of what came back rather than
 * the whole reply being trusted to be JSON.
 */
function parseModelJson(text) {
  const cleaned = text.replace(/<think>[\s\S]*?<\/think>/gi, '');
  const start = cleaned.indexOf('{');
  const end = cleaned.lastIndexOf('}');
  if (start === -1 || end <= start) throw new Error('model did not return JSON');
  return JSON.parse(cleaned.slice(start, end + 1));
}

async function readWithGroq({ apiKey, bytes, mime, key, today }) {
  const imageUrl = groqImageUrl(bytes, mime, key);
  if (!imageUrl) throw failure('too_big', 'that poster is too large to send');

  const pinned = (process.env.GROQ_MODEL || '').trim();
  const models = pinned ? [pinned] : GROQ_MODELS;
  // Once a schema has been refused, stop paying a rejected request per poster
  // to rediscover it; otherwise try the schema first and fall back to JSON mode.
  const modes = schemaAccepted === false ? [false] : [true, false];
  const tried = [];

  for (const model of models) {
    for (const structured of modes) {
      const res = await groqPost(groqBody(model, imageUrl, today, structured), apiKey);

      if (res.ok) {
        schemaAccepted = structured;
        const json = await res.json();
        const choice = json.choices?.[0];
        const text = choice?.message?.content;
        // Running out of tokens mid-answer leaves JSON with no closing brace.
        if (choice?.finish_reason === 'length' && !text?.trimEnd().endsWith('}')) {
          throw failure('too_long', 'the model ran out of room before finishing');
        }
        if (!text) throw failure('empty', 'the model returned nothing');
        try {
          return {
            provider: `groq:${model}`,
            ...toEvent(parseModelJson(text), today),
            usage: { input: json.usage?.prompt_tokens ?? 0, output: json.usage?.completion_tokens ?? 0 },
          };
        } catch (error) {
          throw failure('unreadable', error.message);
        }
      }

      const detail = await res.text();
      tried.push(`${model}${structured ? '' : ' (json mode)'}: ${res.status}`);

      if (isModelFault(res.status, detail)) break;          // wrong model — next model
      if (structured && /response_format|json_schema|schema/i.test(detail)) {
        schemaAccepted = false;                             // remember, then retry plain JSON
        continue;
      }
      if (res.status === 429) {
        throw failure('rate_limit', 'Groq is rate limiting the free tier',
          Number(res.headers.get('retry-after')) || 20);
      }
      throw failure('http', `groq ${res.status}: ${detail.slice(0, 200)}`);
    }
  }

  throw failure('model', `no usable Groq vision model (tried ${tried.join(', ')})`);
}

/* ---------------------------- entry ---------------------------- */

export const extractionConfigured = () => Boolean(process.env.GROQ_API_KEY);

/** Read one poster. Throws if it cannot be read; the caller keeps the upload. */
export async function extractEvent({ bytes, mime, key, today }) {
  const apiKey = process.env.GROQ_API_KEY;
  if (!apiKey) throw failure('unconfigured', 'GROQ_API_KEY is not set');
  return readWithGroq({ apiKey, bytes, mime, key, today });
}
