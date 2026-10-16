import { useEffect, useState, type CSSProperties } from 'react';
import { send, useShow } from '../store';
import { Fit16x9, SLATE_COPY, SlateArt, type SlateColours, type SlateMode } from '../components/slate/SlateArt';

const MODES: SlateMode[] = ['Starting soon', 'Break', 'Thanks for watching'];
const DEFAULT_MIN = 15;

const panel: CSSProperties = { borderRadius: 22, background: 'linear-gradient(180deg, rgba(36,27,21,0.8), rgba(20,15,11,0.8))', border: '1px solid rgba(255,236,220,0.07)', boxShadow: 'inset 0 1px 0 rgba(255,236,220,0.05), 0 24px 60px rgba(0,0,0,0.4)', padding: 18, display: 'flex', flexDirection: 'column', gap: 16 };
const ghost: CSSProperties = { flex: 1, minHeight: 44, borderRadius: 12, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(255,236,220,0.04)', color: 'var(--text-1)', fontWeight: 700, cursor: 'pointer' };

const fmt = (ms: number) => {
  const s = Math.max(0, Math.ceil(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
};

export function SlateScreen() {
  const s = useShow();
  const [preview, setPreview] = useState<SlateMode>('Break');
  const [minutes, setMinutes] = useState(DEFAULT_MIN);
  const [endAt, setEndAt] = useState(() => Date.now() + DEFAULT_MIN * 60_000);
  const [now, setNow] = useState(Date.now());
  const [colours, setColours] = useState<SlateColours>({ c1: '#FF5E62', c2: '#FF9966', c3: '#FFC371' });

  const live = s?.slate ?? null;
  const mode: SlateMode = live ?? preview;

  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);

  // A new slate from the server (or from this tab) restarts the countdown.
  useEffect(() => {
    if (live) { setPreview(live); setEndAt(Date.now() + minutes * 60_000); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live]);

  if (!s) return null;

  const left = endAt - now;
  const time = fmt(left);
  const timed = SLATE_COPY[mode].showTime;
  const onStream = s.onAir && !!live;

  const choose = (m: SlateMode) => {
    setPreview(m);
    setEndAt(Date.now() + minutes * 60_000);
    send({ type: 'slate', slate: m });
  };
  const setMin = (v: number) => {
    const m = Math.min(60, Math.max(1, Math.round(v) || 1));
    setMinutes(m);
    setEndAt(Date.now() + m * 60_000);
  };

  return (
    <main style={{ flex: '1 1 auto', display: 'flex', flexWrap: 'wrap', gap: 24, padding: 'clamp(20px, 3vw, 36px) clamp(16px, 3vw, 40px)', maxWidth: 1380, width: '100%', margin: '0 auto', alignItems: 'flex-start' }}>
      <section aria-label="Slate preview" style={{ flex: '999 1 600px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span className="vn-label">SLATE · WHAT VIEWERS SEE</span>
          <span style={{ flex: 1 }} />
          {onStream ? (
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 12px', borderRadius: 999, background: 'var(--on-air-fill)', color: '#FFFFFF', fontWeight: 700, fontSize: 12 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#FFFFFF', animation: 'vnPulse 1.8s ease-out infinite' }} />ON STREAM
            </span>
          ) : (
            <span style={{ padding: '5px 12px', borderRadius: 999, border: '1px solid rgba(255,236,220,0.12)', color: 'var(--text-meta)', fontWeight: 700, fontSize: 12 }}>{live ? 'SELECTED · OFF AIR' : 'PREVIEW'}</span>
          )}
        </div>
        <Fit16x9 label={`${mode} slate${timed ? `, ${time} left` : ''}`}>
          <SlateArt mode={mode} time={time} colours={colours} />
        </Fit16x9>
      </section>

      <aside aria-label="Slate controls" style={{ flex: '1 1 300px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 18 }}>
        <div style={panel}>
          <span className="vn-label">MODE</span>
          <div role="radiogroup" aria-label="Slate mode" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {MODES.map((m) => {
              const active = live === m;
              const selected = mode === m;
              return (
                <button key={m} role="radio" aria-checked={selected} onClick={() => choose(m)}
                  style={{ minHeight: 48, padding: '0 14px', borderRadius: 14, textAlign: 'left', display: 'flex', alignItems: 'center', gap: 10, fontWeight: 700, fontSize: 14, cursor: 'pointer', border: active ? '1px solid var(--on-air)' : selected ? '1px solid rgba(245,238,230,0.35)' : '1px solid rgba(255,236,220,0.08)', background: active ? 'rgba(31,102,224,0.16)' : 'rgba(255,236,220,0.03)', color: 'var(--text-1)' }}>
                  <span style={{ width: 10, height: 10, borderRadius: '50%', flex: 'none', background: active ? 'var(--on-air)' : selected ? 'var(--text-1)' : 'rgba(255,236,220,0.15)' }} />
                  {m}
                  <span style={{ flex: 1 }} />
                  {active && <span style={{ fontSize: 11, color: '#CFE0FF', letterSpacing: '0.08em' }}>SHOWING</span>}
                </button>
              );
            })}
          </div>
          {live && (
            <button style={ghost} onClick={() => send({ type: 'slate', slate: null })}>Back to the show</button>
          )}
        </div>

        <div style={{ ...panel, opacity: timed ? 1 : 0.5 }} aria-disabled={!timed}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span className="vn-label">COUNTDOWN</span>
            <span style={{ flex: 1 }} />
            <span className="vn-mono" style={{ fontSize: 22, fontWeight: 700, color: left <= 0 ? 'var(--warn)' : 'var(--text-1)' }}>{time}</span>
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: 'var(--text-soft)' }}>
            Minutes
            <input type="number" min={1} max={60} value={minutes} disabled={!timed} onChange={(e) => setMin(Number(e.target.value))}
              className="vn-mono" style={{ width: 80, minHeight: 38, padding: '0 10px', borderRadius: 10, border: '1px solid rgba(255,236,220,0.15)', background: 'rgba(0,0,0,0.3)', color: 'var(--text-1)', fontSize: 14 }} />
            <button style={{ ...ghost, flex: 'none', minHeight: 38, padding: '0 10px', fontWeight: 600, fontSize: 12 }} disabled={!timed} onClick={() => setMin(minutes)}>Restart</button>
          </label>
          <div style={{ display: 'flex', gap: 8 }}>
            <button style={ghost} disabled={!timed} onClick={() => setEndAt((e) => Math.max(e, Date.now()) + 5 * 60_000)}>+5 min</button>
            <button style={ghost} disabled={!timed} onClick={() => setEndAt(Date.now())}>End now</button>
          </div>
          {timed && left <= 0 && <span style={{ fontSize: 12, color: 'var(--text-meta)' }}>Countdown finished. Returning to the show automatically is coming later — tap “Back to the show”.</span>}
        </div>

        <div style={panel}>
          <span className="vn-label">BAND COLOURS</span>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {(['c1', 'c2', 'c3'] as const).map((k, i) => (
              <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-soft)' }}>
                <input type="color" value={colours[k]} onChange={(e) => setColours((c) => ({ ...c, [k]: e.target.value }))}
                  aria-label={`Band colour ${i + 1}`} style={{ width: 40, height: 32, padding: 0, border: '1px solid rgba(255,236,220,0.15)', borderRadius: 8, background: 'transparent', cursor: 'pointer' }} />
                <span className="vn-mono" style={{ fontSize: 12 }}>{colours[k].toUpperCase()}</span>
              </label>
            ))}
          </div>
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>Preview only — colours aren’t saved yet.</span>
        </div>
      </aside>
    </main>
  );
}
