import Anthropic from '@anthropic-ai/sdk';

/**
 * Reading a gig poster into a schedule entry.
 *
 * Two providers, same contract. Groq is tried first because its vision models
 * are free at the volumes this venue posts at — a month of posters is a few
 * dozen calls. Anthropic is the fallback for when Groq cannot read a poster, or
 * when only ANTHROPIC_API_KEY is set. With neither key the caller degrades to
 * typing the details in by hand.
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
  + 'a date, or a genre. If a field is not on the poster, return an empty string for it.';

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
 * Groq's vision line-up is served as preview models and IDs get retired, so
 * this is a preference list rather than one hard-coded name: the first model
 * the account can actually reach wins, and a retirement stops being an outage.
 * Set GROQ_MODEL to pin one instead.
 */
const GROQ_MODELS = [
  'meta-llama/llama-4-scout-17b-16e-instruct',
  'meta-llama/llama-4-maverick-17b-128e-instruct',
  'llama-3.2-90b-vision-preview',
  'llama-3.2-11b-vision-preview',
];

/** Groq caps inline base64 at 4 MB. Bigger posters go by URL — /api/img is
    public and content-addressed, so the link is stable and safe to hand out. */
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
    max_completion_tokens: 700,
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

async function readWithGroq({ apiKey, bytes, mime, key, today }) {
  const imageUrl = groqImageUrl(bytes, mime, key);
  if (!imageUrl) throw new Error('poster too large to send');

  const pinned = (process.env.GROQ_MODEL || '').trim();
  const models = pinned ? [pinned] : GROQ_MODELS;
  const tried = [];

  for (const model of models) {
    // Not every Groq model accepts a JSON schema; plain JSON mode is the fallback.
    for (const structured of [true, false]) {
      const res = await groqPost(groqBody(model, imageUrl, today, structured), apiKey);

      if (res.ok) {
        const json = await res.json();
        const text = json.choices?.[0]?.message?.content;
        if (!text) throw new Error('groq returned no content');
        return {
          provider: `groq:${model}`,
          ...toEvent(JSON.parse(text)),
          usage: { input: json.usage?.prompt_tokens ?? 0, output: json.usage?.completion_tokens ?? 0 },
        };
      }

      const detail = await res.text();
      tried.push(`${model}${structured ? '' : ' (json mode)'}: ${res.status}`);

      if (isModelFault(res.status, detail)) break;          // wrong model — next model
      if (structured && /response_format|json_schema|schema/i.test(detail)) continue; // retry unstructured
      throw new Error(`groq ${res.status}: ${detail.slice(0, 200)}`);
    }
  }

  throw new Error(`no usable Groq vision model (tried ${tried.join(', ')})`);
}

/* --------------------------- Anthropic --------------------------- */

async function readWithAnthropic({ bytes, mime, today }) {
  const response = await new Anthropic().messages.create({
    model: 'claude-opus-5',
    max_tokens: 4000,
    // Low effort suits a scoped read-and-transcribe task, and structured
    // output means the result is schema-valid without any parsing.
    output_config: { effort: 'low', format: { type: 'json_schema', schema: EVENT_SCHEMA } },
    system: SYSTEM,
    messages: [{
      role: 'user',
      content: [
        { type: 'image', source: { type: 'base64', media_type: mime, data: bytes.toString('base64') } },
        { type: 'text', text: askFor(today) },
      ],
    }],
  });

  const block = response.content.find((b) => b.type === 'text');
  if (!block) throw new Error('no content returned');

  return {
    provider: 'anthropic',
    ...toEvent(JSON.parse(block.text)),
    usage: { input: response.usage.input_tokens, output: response.usage.output_tokens },
  };
}

/* ---------------------------- entry ---------------------------- */

export const extractionConfigured = () =>
  Boolean(process.env.GROQ_API_KEY || process.env.ANTHROPIC_API_KEY);

/**
 * Read one poster. Groq first when its key is present; Anthropic picks up both
 * when it is the only key configured and when Groq fails, so a rate limit or a
 * retired model degrades to a slightly pricier read rather than to no read.
 */
export async function extractEvent({ bytes, mime, key, today }) {
  const groqKey = process.env.GROQ_API_KEY;
  const hasAnthropic = Boolean(process.env.ANTHROPIC_API_KEY);

  if (groqKey) {
    try {
      return await readWithGroq({ apiKey: groqKey, bytes, mime, key, today });
    } catch (error) {
      if (!hasAnthropic) throw error;
      console.warn('extract: Groq failed, falling back to Anthropic —', error.message);
    }
  }

  if (!hasAnthropic) throw new Error('no extraction provider configured');
  return readWithAnthropic({ bytes, mime, today });
}
