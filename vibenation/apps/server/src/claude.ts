// Runs Claude headlessly through the Claude Code CLI on this server (the band's Max
// plan, not the API). No tools, no MCP, no session files: one prompt in, one JSON out.

import { spawn } from 'node:child_process';

const CLAUDE_BIN = process.env.VN_CLAUDE_BIN ?? `${process.env.HOME ?? '/root'}/.local/bin/claude`;
export const CLAUDE_MODEL = process.env.VN_CLAUDE_MODEL ?? 'opus';

export interface ClaudeResult<T> {
  ok: boolean;
  data?: T;
  error?: string;
  ms: number;
}

export function askClaude<T>(system: string, prompt: string, opts: { timeoutMs?: number; model?: string } = {}): Promise<ClaudeResult<T>> {
  const t0 = Date.now();
  return new Promise((resolve) => {
    const child = spawn(
      CLAUDE_BIN,
      ['-p', '--output-format', 'json', '--tools', '', '--no-session-persistence', '--strict-mcp-config', '--setting-sources', '',
        '--model', opts.model ?? CLAUDE_MODEL, '--system-prompt', system],
      { stdio: ['pipe', 'pipe', 'pipe'], cwd: '/tmp' },
    );
    let out = '';
    let err = '';
    const timer = setTimeout(() => child.kill('SIGKILL'), opts.timeoutMs ?? 120_000);
    child.stdout.on('data', (d) => { out += d; });
    child.stderr.on('data', (d) => { err += d; });
    child.on('close', (code) => {
      clearTimeout(timer);
      const ms = Date.now() - t0;
      try {
        const env = JSON.parse(out) as { result?: string; is_error?: boolean };
        if (env.is_error || typeof env.result !== 'string') return resolve({ ok: false, error: env.result ?? `exit ${code}`, ms });
        resolve({ ok: true, data: parseJson<T>(env.result), ms });
      } catch (e) {
        resolve({ ok: false, error: `${(e as Error).message}; ${err.slice(0, 300) || out.slice(0, 300)}`, ms });
      }
    });
    child.stdin.end(prompt);
  });
}

/** Pull the first JSON object out of a reply that may be wrapped in prose or a code fence. */
export function parseJson<T>(text: string): T {
  const fenced = /```(?:json)?\s*([\s\S]*?)```/.exec(text);
  const body = fenced ? fenced[1] : text;
  const start = body.indexOf('{');
  const end = body.lastIndexOf('}');
  if (start < 0 || end < start) throw new Error('no JSON object in reply');
  return JSON.parse(body.slice(start, end + 1)) as T;
}
