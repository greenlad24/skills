import { useEffect, useState } from 'react';

// Show server card: the GPU machine that mixes, composites and encodes the live stream.
// Start costs money, so it asks first; it auto-destroys after the chosen time as a safety net.

interface Server { name: string; ip: string | null; region: string; status: string; size: string; up_min: number; ttl_min: number; price_hourly: number }
interface Status { servers?: Server[]; connected?: boolean; error?: string; job: { active: boolean; log: string[] } }

const PRICE = 0.5; // CPU-Optimized c-16, $/hour
const btn = { minHeight: 44, padding: '0 16px', borderRadius: 12, border: 0, background: 'var(--text-1)', color: '#140D09', fontWeight: 700, fontSize: 14, cursor: 'pointer' } as const;
const ghost = { ...btn, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(255,236,220,0.04)', color: 'var(--text-1)' } as const;

export function ShowServer() {
  const [st, setSt] = useState<Status | null>(null);
  const [hours, setHours] = useState(5);
  const [asking, setAsking] = useState<'start' | 'stop' | null>(null);
  const [error, setError] = useState('');

  const load = () => fetch('/api/showserver').then((r) => r.json()).then(setSt).catch(() => undefined);
  useEffect(() => { void load(); const t = setInterval(() => void load(), 5000); return () => clearInterval(t); }, []);

  async function act(what: 'start' | 'stop') {
    setError(''); setAsking(null);
    const r = await fetch(`/api/showserver/${what}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ confirm: true, ttlMin: hours * 60 }) });
    if (!r.ok) setError((await r.json().catch(() => ({}))).error ?? `Failed (${r.status})`);
    void load();
  }

  const s = st?.servers?.[0];
  const busy = st?.job.active;
  const cost = s ? (s.up_min / 60) * s.price_hourly : 0;
  const headline = s ? (st?.connected ? `Running · ${s.region.toUpperCase()} · connected` : `${busy ? 'Setting up' : s.status} · ${s.region.toUpperCase()}`) : busy ? 'Starting…' : 'Off';

  return (
    <section aria-label="Show server" style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingBottom: 14, borderBottom: '1px solid rgba(255,236,220,0.08)' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span className="vn-label">SHOW SERVER</span>
        <span style={{ fontWeight: 700 }}>{headline}</span>
      </div>
      {s && <span className="vn-mono" style={{ fontSize: 12, color: 'var(--text-meta)' }}>
        {s.size} · up {Math.round(s.up_min)} min · ≈ ${cost.toFixed(2)} so far · auto-off in {Math.max(0, Math.round(s.ttl_min - s.up_min))} min
      </span>}
      {s?.ip && <span style={{ fontSize: 13 }}>Venue laptop: put <b className="vn-mono" style={{ fontSize: 15 }}>{s.ip}</b> as <b>server</b> in sender.ini.</span>}
      {busy && st?.job.log.length ? <code style={{ fontSize: 11, color: 'var(--text-soft)', whiteSpace: 'pre-wrap', maxHeight: 90, overflow: 'auto' }}>{st.job.log.slice(-4).join('\n')}</code> : null}
      {error && <span role="alert" style={{ color: 'var(--error)', fontSize: 13 }}>{error}</span>}
      {st?.error && <span role="alert" style={{ color: 'var(--warn)', fontSize: 12 }}>{st.error}</span>}

      {asking === 'start' ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span style={{ fontSize: 13, color: 'var(--text-soft)' }}>
            Show server (16 dedicated CPUs) ≈ ${PRICE.toFixed(2)}/hour. It sets up (~15 min) in the nearest region with room and connects; the venue laptop then needs its address. Auto-off after:
          </span>
          <div style={{ display: 'flex', gap: 6 }}>
            {[3, 5, 8].map((h) => <button key={h} onClick={() => setHours(h)} style={{ ...ghost, flex: 1, minHeight: 36, background: hours === h ? 'rgba(255,236,220,0.14)' : ghost.background }}>{h} h · ${(h * PRICE).toFixed(2)} max</button>)}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button style={{ ...btn, flex: 1 }} onClick={() => void act('start')}>Start · up to ${(hours * PRICE).toFixed(2)}</button>
            <button style={ghost} onClick={() => setAsking(null)}>Cancel</button>
          </div>
        </div>
      ) : asking === 'stop' ? (
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={{ ...btn, flex: 1, background: 'rgba(255,178,36,0.16)', border: '1px solid var(--warn)', color: 'var(--warn)' }} onClick={() => void act('stop')}>Yes, destroy the show server</button>
          <button style={ghost} onClick={() => setAsking(null)}>Cancel</button>
        </div>
      ) : s || busy ? (
        <button style={ghost} onClick={() => setAsking('stop')}>Stop show server…</button>
      ) : (
        <button style={btn} onClick={() => setAsking('start')}>Start show server…</button>
      )}
    </section>
  );
}
