import Fastify from 'fastify';
import fastifyStatic from '@fastify/static';
import fastifyWebsocket from '@fastify/websocket';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import type { HealthResponse } from '@vibenation/shared';

const PORT = Number(process.env.PORT ?? 8080);
// Bind to localhost only until the user approves opening ports to the internet.
const HOST = process.env.HOST ?? '127.0.0.1';

const app = Fastify({ logger: true });
await app.register(fastifyWebsocket);

app.get('/api/health', async (): Promise<HealthResponse> => ({
  ok: true,
  app: 'VibeNation',
  version: '0.1.0',
  uptimeS: Math.round(process.uptime()),
}));

// Live state channel (meters, Claude activity). Demo heartbeat for now.
app.get('/ws', { websocket: true }, (socket) => {
  const timer = setInterval(() => socket.send(JSON.stringify({ type: 'tick', t: Date.now() })), 1000);
  socket.on('close', () => clearInterval(timer));
});

const webDist = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../web/dist');
if (existsSync(webDist)) {
  await app.register(fastifyStatic, { root: webDist });
  app.setNotFoundHandler((req, reply) =>
    req.url.startsWith('/api') ? reply.code(404).send({ error: 'not found' }) : reply.sendFile('index.html'),
  );
}

await app.listen({ port: PORT, host: HOST });
