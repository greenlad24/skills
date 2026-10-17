// Show server card on Go Live: start / watch / stop the per-show GPU server from the app, so the
// show never depends on a chat session. Wraps infra/showserver/showserver.py. Create and destroy run
// as their own systemd jobs: when the server is ready the script restarts this web app to switch it
// over, which would kill a child process.

import { execFile } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import type { FastifyInstance } from 'fastify';

const run = promisify(execFile);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const SCRIPT = path.join(ROOT, 'infra/showserver/showserver.py');
const JOB = 'vibenation-showserver-job';

async function job(): Promise<{ active: boolean; log: string[] }> {
  const st = await run('systemctl', ['is-active', JOB]).then((r) => r.stdout.trim(), (e) => String(e.stdout ?? '').trim());
  const log = await run('sudo', ['-n', 'journalctl', '-u', JOB, '-n', '12', '-o', 'cat', '--no-pager']).then((r) => r.stdout, () => '');
  return { active: st === 'active' || st === 'activating', log: log.split('\n').filter(Boolean).slice(-12) };
}

async function launch(args: string[]) {
  await run('sudo', ['-n', 'systemctl', 'reset-failed', JOB]).catch(() => undefined);
  await run('sudo', ['-n', 'systemd-run', `--unit=${JOB}`, '--uid=vibe', '--gid=vibe', `--working-directory=${ROOT}`,
    '--setenv=HOME=/home/vibe', '/usr/bin/python3', '-u', SCRIPT, ...args]);
}

export function registerShowServer(app: FastifyInstance) {
  app.get('/api/showserver', async () => {
    const [st, j] = await Promise.all([
      run('python3', [SCRIPT, 'status-json'], { cwd: ROOT, timeout: 30_000 }).then((r) => JSON.parse(r.stdout), (e) => ({ error: String(e.stderr || e.message).slice(-300) })),
      job(),
    ]);
    return { ...st, job: j };
  });

  app.post<{ Body: { confirm?: boolean; ttlMin?: number } }>('/api/showserver/start', async (req, reply) => {
    if (req.body?.confirm !== true) return reply.code(400).send({ error: 'Confirm the cost first.' });
    if ((await job()).active) return reply.code(409).send({ error: 'A show server job is already running.' });
    const ttl = Math.max(60, Math.min(600, Math.round(Number(req.body.ttlMin) || 300)));
    await launch(['create', '--retry', '180', '--ttl', String(ttl)]);
    req.log.info({ ttl }, 'show server start requested');
    return { ok: true, ttlMin: ttl };
  });

  app.post('/api/showserver/stop', async (req) => {
    await run('sudo', ['-n', 'systemctl', 'stop', JOB]).catch(() => undefined); // a create still waiting for a GPU
    await launch(['destroy']);
    req.log.info('show server stop requested');
    return { ok: true };
  });
}
