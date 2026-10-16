import type { ClientAction } from '@vibenation/shared';
import { send } from '../../store';

// Per-control throttle (~20/s) that always delivers the trailing value.
const last = new Map<string, number>();
const pending = new Map<string, number>();
const GAP = 50;

export function sendSoon(key: string, a: ClientAction) {
  const now = performance.now();
  clearTimeout(pending.get(key));
  const wait = GAP - (now - (last.get(key) ?? 0));
  if (wait <= 0) { last.set(key, now); send(a); return; }
  pending.set(key, window.setTimeout(() => { last.set(key, performance.now()); pending.delete(key); send(a); }, wait));
}

export const sendControl = (id: string, value: number | string) => sendSoon(id, { type: 'control', id, value });
