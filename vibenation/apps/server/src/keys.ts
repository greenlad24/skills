// Keys screen: the user pastes API keys in the app (logged in, HTTPS). Each key is tested with
// its provider, then written to the private .env (mode 600) and applied live via process.env.
// A key is never sent back to the browser: only whether it is set and its last 4 characters.

import { readFileSync, renameSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { FastifyInstance } from 'fastify';
import type { KeyName, KeyStatus } from '@vibenation/shared';

const ENV_FILE = process.env.VN_ENV_FILE ?? path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../.env');

type Check = (v: string) => Promise<Response>;
const KEYS: Record<KeyName, { label: string; use: string; get: string; check: Check }> = {
  GEMINI_API_KEY: {
    label: 'Gemini', use: 'The listener: hears the mix every 20 s (about $1–2 per show)', get: 'https://aistudio.google.com/apikey',
    check: (v) => fetch('https://generativelanguage.googleapis.com/v1beta/models?pageSize=1', { headers: { 'x-goog-api-key': v } }),
  },
  OPENAI_API_KEY: {
    label: 'OpenAI', use: 'Thumbnails (GPT Image) from a live camera frame', get: 'https://platform.openai.com/api-keys',
    check: (v) => fetch('https://api.openai.com/v1/models', { headers: { authorization: `Bearer ${v}` } }),
  },
  DIGITALOCEAN_TOKEN: {
    label: 'DigitalOcean', use: 'Creates and destroys the GPU show server (~$0.76/h while it runs)', get: 'https://cloud.digitalocean.com/account/api/tokens',
    check: (v) => fetch('https://api.digitalocean.com/v2/sizes?per_page=1', { headers: { authorization: `Bearer ${v}` } }),
  },
};

const isKey = (n: unknown): n is KeyName => typeof n === 'string' && Object.hasOwn(KEYS, n);

function status(name: KeyName): KeyStatus {
  const v = process.env[name] ?? '';
  const k = KEYS[name];
  return { name, label: k.label, use: k.use, get: k.get, set: v !== '', hint: v ? `…${v.slice(-4)}` : null };
}

/** Replace or add NAME=value in the .env file, keeping it readable by this user only. */
function writeEnv(name: KeyName, value: string) {
  let lines: string[] = [];
  try { lines = readFileSync(ENV_FILE, 'utf8').split('\n'); } catch { /* new file */ }
  if (lines.at(-1) === '') lines.pop();
  const i = lines.findIndex((l) => l.startsWith(`${name}=`));
  if (i >= 0) lines[i] = `${name}=${value}`; else lines.push(`${name}=${value}`);
  const tmp = `${ENV_FILE}.tmp`;
  writeFileSync(tmp, lines.join('\n') + '\n', { mode: 0o600 });
  renameSync(tmp, ENV_FILE);
}

export function registerKeys(app: FastifyInstance) {
  app.get('/api/keys', async (): Promise<KeyStatus[]> => (Object.keys(KEYS) as KeyName[]).map(status));

  app.post<{ Body: { name?: string; value?: string } }>('/api/keys', async (req, reply) => {
    const name = req.body?.name;
    const value = (req.body?.value ?? '').trim();
    if (!isKey(name)) return reply.code(400).send({ error: 'Unknown key.' });
    if (!/^[A-Za-z0-9_.-]{20,300}$/.test(value)) return reply.code(400).send({ error: 'That doesn’t look like a key. Copy it again without spaces or line breaks.' });
    let ok = false;
    try { ok = (await KEYS[name].check(value)).ok; } catch {
      return reply.code(502).send({ error: `Couldn’t reach ${KEYS[name].label} to test the key. Try again in a minute.` });
    }
    if (!ok) return reply.code(400).send({ error: `${KEYS[name].label} rejected this key. Check you copied all of it.` });
    writeEnv(name, value);
    process.env[name] = value;
    req.log.info({ key: name }, 'key saved');
    return status(name);
  });
}
