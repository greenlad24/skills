import { useEffect, useRef, useState, type CSSProperties } from 'react';
import type { AudioStatus } from '@vibenation/shared';
import { send } from '../store';

// Test source controls (the show recording standing in for the venue feed) and a
// Listen button that plays the live master mix in this browser.

const pill: CSSProperties = { display: 'flex', alignItems: 'center', gap: 8, padding: '4px 6px 4px 12px', borderRadius: 999, background: 'rgba(255,236,220,0.05)', border: '1px solid rgba(255,236,220,0.08)' };
const btn: CSSProperties = { minWidth: 32, height: 28, padding: '0 10px', borderRadius: 999, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(255,236,220,0.06)', color: 'var(--text-1)', fontWeight: 700, fontSize: 12, cursor: 'pointer' };
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

export function Transport({ a }: { a: AudioStatus }) {
  const [pos, setPos] = useState<number | null>(null);
  return (
    <div style={pill} aria-label="Test source">
      <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: '0.1em', color: 'var(--text-meta)' }}>{a.source === 'recording' ? 'TEST RECORDING' : 'VENUE'}</span>
      {a.sets.length > 1 && (
        <select value={a.set ?? ''} onChange={(e) => send({ type: 'transport', action: 'load', set: e.target.value })} aria-label="Set"
          style={{ height: 28, borderRadius: 999, border: '1px solid rgba(255,236,220,0.12)', background: '#1A130F', color: 'var(--text-1)', fontSize: 12, padding: '0 8px' }}>
          {a.sets.map((s) => <option key={s}>{s}</option>)}
        </select>
      )}
      <button style={btn} onClick={() => send({ type: 'transport', action: a.playing ? 'pause' : 'play' })} aria-label={a.playing ? 'Pause' : 'Play'}>{a.playing ? '❚❚' : '▶'}</button>
      <input type="range" min={0} max={Math.max(1, a.length)} step={1} value={pos ?? a.position} aria-label="Position"
        onChange={(e) => setPos(Number(e.target.value))}
        onPointerUp={() => { if (pos !== null) send({ type: 'transport', action: 'seek', seconds: pos }); setPos(null); }}
        onKeyUp={() => { if (pos !== null) send({ type: 'transport', action: 'seek', seconds: pos }); setPos(null); }}
        style={{ width: 120, accentColor: '#F5EEE6' }} />
      <span className="vn-mono" style={{ fontSize: 12, color: 'var(--text-soft)', minWidth: 86 }}>{mmss(pos ?? a.position)} / {mmss(a.length)}</span>
      {a.calibrating && <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--ai-text)' }} title="Claude is setting each channel's digital trim from the first minutes of playing">calibrating</span>}
      <Listen />
    </div>
  );
}

function Listen() {
  const ref = useRef<HTMLAudioElement>(null);
  const [on, setOn] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (on) {
      el.src = `/api/audio/stream.mp3?t=${Date.now()}`; // fresh connection = live, not a stale buffer
      el.play().catch(() => setOn(false));
    } else {
      el.pause();
      el.removeAttribute('src');
      el.load();
    }
  }, [on]);
  return (
    <>
      <button style={{ ...btn, background: on ? 'var(--text-1)' : btn.background, color: on ? '#140D09' : 'var(--text-1)' }} onClick={() => setOn((v) => !v)} aria-pressed={on}>
        {on ? 'Listening' : 'Listen'}
      </button>
      <audio ref={ref} preload="none" />
    </>
  );
}
