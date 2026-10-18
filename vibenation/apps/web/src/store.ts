import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { ClientAction, MeterFrame, ServerMessage, ShowState } from '@vibenation/shared';

// One WebSocket per tab. Full state arrives on every change; meters arrive ~10×/s
// and are kept in a separate store so only meter components re-render.

let state: ShowState | null = null;
let meters: MeterFrame | null = null;
let ws: WebSocket | null = null;
let status: 'connecting' | 'open' | 'closed' | 'unauthorized' = 'connecting';
const stateSubs = new Set<() => void>();
const meterSubs = new Set<() => void>();
const emit = (s: Set<() => void>) => s.forEach((f) => f());

export function connect() {
  if (ws && ws.readyState <= 1) return;
  status = 'connecting';
  emit(stateSubs);
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => { status = 'open'; emit(stateSubs); };
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data) as ServerMessage;
    if (msg.type === 'state') { state = msg.state; emit(stateSubs); }
    else { meters = msg; emit(meterSubs); }
  };
  ws.onclose = async () => {
    ws = null;
    const me = await fetch('/api/me').then((r) => r.json()).catch(() => ({ authed: true }));
    status = me.authed ? 'closed' : 'unauthorized';
    emit(stateSubs);
    if (me.authed) setTimeout(connect, 1500);
  };
}

export function send(a: ClientAction) {
  if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(a));
}

export function useShow() {
  return useSyncExternalStore((f) => { stateSubs.add(f); return () => stateSubs.delete(f); }, () => state);
}

export function useStatus() {
  return useSyncExternalStore((f) => { stateSubs.add(f); return () => stateSubs.delete(f); }, () => status);
}

export function useMeters() {
  return useSyncExternalStore((f) => { meterSubs.add(f); return () => meterSubs.delete(f); }, () => meters);
}

/** True while the engine keeps this channel muted because nobody plays it (re-renders only when that flips). */
export function useAutoMuted(n: number) {
  return useSyncExternalStore((f) => { meterSubs.add(f); return () => meterSubs.delete(f); }, () => !!meters?.autoMuted?.includes(n));
}

/** Elapsed "HH:MM:SS" since a timestamp, ticking every second. */
export function useElapsed(since: number | null) {
  const [, tick] = useState(0);
  const ref = useRef<number>();
  useEffect(() => {
    ref.current = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(ref.current);
  }, []);
  if (!since) return '00:00:00';
  const s = Math.max(0, Math.floor((Date.now() - since) / 1000));
  return [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60].map((n) => String(n).padStart(2, '0')).join(':');
}

/** "−9.5" style dB text with a real minus sign. */
export const fmtDb = (v: number, digits = 1) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(digits);
