import Anthropic from '@anthropic-ai/sdk';
import { getStore } from '@netlify/blobs';
import { isAuthenticated, hasCsrfHeader, unauthorized } from '../lib/auth.mjs';
import { venueToday } from '../lib/shows.mjs';

const MIME = { jpg: 'image/jpeg', png: 'image/png', webp: 'image/webp' };

/** The shape the editor expects back. Enforced by the API, not by parsing. */
const EVENT_SCHEMA = {
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

export default async (request) => {
  if (!isAuthenticated(request)) return unauthorized();
  if (!hasCsrfHeader(request)) return Response.json({ error: 'Bad request' }, { status: 400 });

  if (!process.env.ANTHROPIC_API_KEY) {
    // Not an error: the editor falls back to filling the fields by hand.
    return Response.json({ configured: false }, { status: 200 });
  }

  let key;
  try {
    ({ key } = await request.json());
  } catch {
    return Response.json({ error: 'Bad request' }, { status: 400 });
  }
  if (!/^[a-f0-9]{32}\.(jpg|png|webp)$/.test(String(key || ''))) {
    return Response.json({ error: 'Unknown image' }, { status: 400 });
  }

  let bytes, mime;
  try {
    const blob = await getStore({ name: 'vibration-images', consistency: 'strong' })
      .getWithMetadata(key, { type: 'arrayBuffer' });
    if (!blob) return Response.json({ error: 'Image not found' }, { status: 404 });
    bytes = Buffer.from(blob.data);
    mime = blob.metadata?.mime || MIME[key.split('.').pop()];
  } catch (error) {
    console.error('extract: could not read image', error);
    return Response.json({ error: 'Could not read the image' }, { status: 500 });
  }

  const client = new Anthropic();

  try {
    const response = await client.messages.create({
      model: 'claude-opus-5',
      max_tokens: 4000,
      // Low effort suits a scoped read-and-transcribe task, and structured
      // output means the result is schema-valid without any parsing.
      output_config: { effort: 'low', format: { type: 'json_schema', schema: EVENT_SCHEMA } },
      system:
        'You read gig posters for Vibration, a live-music bar on Koh Samui, and turn them into '
        + 'schedule entries. Transcribe only what the poster actually shows — never invent an act, '
        + 'a date, or a genre. If a field is not on the poster, return an empty string for it.',
      messages: [{
        role: 'user',
        content: [
          { type: 'image', source: { type: 'base64', media_type: mime, data: bytes.toString('base64') } },
          {
            type: 'text',
            text: `Today is ${venueToday()}. Read this poster and return the event details.\n\n`
              + 'If the poster shows a day and month but no year, choose the year that puts the date '
              + 'in the near future rather than the past. The description is one short sentence for '
              + 'the event page — warm and understated, no exclamation marks, no marketing copy.',
          },
        ],
      }],
    });

    const block = response.content.find((b) => b.type === 'text');
    if (!block) throw new Error('no content returned');

    const data = JSON.parse(block.text);
    return Response.json({
      configured: true,
      event: {
        name: String(data.name || ''),
        on: /^\d{4}-\d{2}-\d{2}$/.test(data.on) ? data.on : '',
        genre: String(data.genre || ''),
        description: String(data.description || ''),
      },
      confident: data.confident !== false,
      usage: { input: response.usage.input_tokens, output: response.usage.output_tokens },
    });
  } catch (error) {
    console.error('extract: model call failed', error);
    // The editor still has the uploaded poster; only the auto-fill failed.
    return Response.json({ error: 'Could not read that poster automatically' }, { status: 502 });
  }
};

export const config = { path: '/api/admin/extract', method: 'POST' };
