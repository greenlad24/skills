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
    genre: { type: 'string', description: 'Genre or style, e.g. "Funk / Soul". Separate multiple with " / ". Empty if absent.' },
    description: { type: 'string', description: 'One short sentence for the event page, in the venue\'s warm, understated voice. Empty if there is nothing to say.' },
    confident: { type: 'boolean', description: 'False if the poster was hard to read and the fields are a guess.' },
  },
  required: ['name', 'on', 'genre', 'description', 'confident'],
  additionalProperties: false,
};

const SYSTEM =
  'You read gig posters for Vibration, a live-music bar on Koh Samui, and turn them into '
  + 'schedule entries. Transcribe only what the poster actually shows — never invent an act, '
  + 'a date, or a genre. If a field is not on the poster, return an empty string for it. '
  + 'Answer with the JSON straight away; this is transcription, not a puzzle to work through.';

const askFor = (today) =>
  `Today is ${today}. Read this poster and return the event details.\n\n`
  + 'If the poster shows a day and month but no year, choose the year that puts the date '
  + 'in the near future rather than the past. The description is one short sentence for '
  + 'the event page — warm and understated, no exclamation marks, no marketing copy.';

/** Normalise whatever the model returned into the fields the editor stores. */
function toEvent(data) {
  return {
    event: {
      name: String(data.name || ''),
      on: /^\d{4}-\d{2}-\d{2}$/.test(data.on) ? data.on : '',
      genre: String(data.genre || ''),
      description: String(data.description || ''),
    },
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
            + '{"name": string, "on": "YYYY-MM-DD" or "", "genre": string, '
            + '"description": string, "confident": boolean}.',
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
  if (!imageUrl) throw new Error('poster too large to send');

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
        const text = json.choices?.[0]?.message?.content;
        if (!text) throw new Error('groq returned no content');
        return {
          provider: `groq:${model}`,
          ...toEvent(parseModelJson(text)),
          usage: { input: json.usage?.prompt_tokens ?? 0, output: json.usage?.completion_tokens ?? 0 },
        };
      }

      const detail = await res.text();
      tried.push(`${model}${structured ? '' : ' (json mode)'}: ${res.status}`);

      if (isModelFault(res.status, detail)) break;          // wrong model — next model
      if (structured && /response_format|json_schema|schema/i.test(detail)) {
        schemaAccepted = false;                             // remember, then retry plain JSON
        continue;
      }
      throw new Error(`groq ${res.status}: ${detail.slice(0, 200)}`);
    }
  }

  throw new Error(`no usable Groq vision model (tried ${tried.join(', ')})`);
}

/* ---------------------------- entry ---------------------------- */

export const extractionConfigured = () => Boolean(process.env.GROQ_API_KEY);

/** Read one poster. Throws if it cannot be read; the caller keeps the upload. */
export async function extractEvent({ bytes, mime, key, today }) {
  const apiKey = process.env.GROQ_API_KEY;
  if (!apiKey) throw new Error('GROQ_API_KEY is not set');
  return readWithGroq({ apiKey, bytes, mime, key, today });
}
