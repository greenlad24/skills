import Fastify from 'fastify';
import fastifyCookie from '@fastify/cookie';
import fastifyStatic from '@fastify/static';
import fastifyWebsocket from '@fastify/websocket';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import type { ClientAction, HealthResponse } from '@vibenation/shared';
import { registerAuth } from './auth.js';
import { DemoShow } from './sim.js';

const PORT = Number(process.env.PORT ?? 8080);
// Bind to localhost only; Caddy in front handles HTTPS once ports are approved.
const HOST = process.env.HOST ?? '127.0.0.1';

const app = Fastify({ logger: { level: 'info' }, trustProxy: '127.0.0.1' });
await app.register(fastifyCookie);
await app.register(fastifyWebsocket);
registerAuth(app);

app.get('/api/health', async (): Promise<HealthResponse> => ({
  ok: true,
  app: 'VibeNation',
  version: '0.2.0',
  uptimeS: Math.round(process.uptime()),
}));

const show = new DemoShow();

app.get('/ws', { websocket: true }, (socket) => {
  const off = show.subscribe((msg) => socket.send(JSON.stringify(msg)));
  socket.on('message', (raw: Buffer) => {
    try {
      show.apply(JSON.parse(String(raw)) as ClientAction);
    } catch (err) {
      app.log.warn({ err }, 'bad client action');
    }
  });
  socket.on('close', off);
});

// Listen to the master mix (MP3) — same login as the app.
app.get('/api/audio/stream.mp3', async (req, reply) => {
  const upstream = await show.audio.stream().catch(() => null);
  if (!upstream?.ok || !upstream.body) return reply.code(503).send({ error: 'Audio engine not running.' });
  const { Readable } = await import('node:stream');
  const body = Readable.fromWeb(upstream.body as import('node:stream/web').ReadableStream);
  req.raw.on('close', () => body.destroy());
  return reply.header('content-type', 'audio/mpeg').header('cache-control', 'no-store').send(body);
});

const webDist = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../web/dist');
if (existsSync(webDist)) {
  await app.register(fastifyStatic, { root: webDist });
  app.setNotFoundHandler((req, reply) =>
    req.url.startsWith('/api') ? reply.code(404).send({ error: 'not found' }) : reply.sendFile('index.html'),
  );
}

await app.listen({ port: PORT, host: HOST });
