import { useState } from 'react';
import type { Platform } from '@vibenation/shared';
import { send } from '../../store';
import { PLATFORM_BG } from '../Header';
import type { DestinationInfo } from '../../demo/golive';

const chip = { padding: '3px 8px', borderRadius: 7, background: 'rgba(255,236,220,0.06)', fontSize: 11, color: 'var(--text-soft)' } as const;

function DestinationCard({ d, on, ready, locked }: { d: DestinationInfo; on: boolean; ready: boolean; locked: boolean }) {
  const [err, setErr] = useState('');
  const [keyOpen, setKeyOpen] = useState(false);
  const [key, setKey] = useState('');

  const live = on && ready;
  const toggle = () => {
    if (live) { send({ type: 'destination', p: d.p, on: false }); return; }
    if (ready) { send({ type: 'destination', p: d.p, on: true }); return; }
    if (d.p === 'YT') { location.href = '/api/oauth/youtube/start'; return; }
    setKeyOpen(true);
  };
  const submitKey = async () => {
    if (!key.trim()) return;
    setErr('');
    const r = await fetch('/api/destinations/key', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ p: d.p, key }) });
    if (!r.ok) { setErr((await r.json().catch(() => ({}))).error ?? 'Not saved.'); return; }
    send({ type: 'destination', p: d.p, on: true });
    setKey('');
    setKeyOpen(false);
  };

  const btnLabel = live ? 'Switch off' : ready ? `Switch on ${d.name}` : d.p === 'YT' ? 'Connect YouTube' : 'Connect · paste stream key';
  return (
    <div style={{ borderRadius: 18, padding: 14, display: 'flex', flexDirection: 'column', gap: 10, background: 'linear-gradient(180deg, rgba(36,27,21,0.8), rgba(20,15,11,0.8))', border: `1px solid ${live ? 'rgba(245,238,230,0.35)' : 'rgba(255,236,220,0.07)'}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ width: 34, height: 34, borderRadius: 10, background: PLATFORM_BG[d.p], color: '#FFFFFF', fontSize: 12, fontWeight: 800, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 6px 16px rgba(0,0,0,0.4)', flex: 'none' }}>{d.p}</span>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
          <span style={{ fontWeight: 700, fontSize: 15 }}>{d.name}</span>
          <span style={{ fontSize: 12, color: live ? 'var(--text-soft)' : 'var(--text-3)' }}>{live ? `On · ${d.p === 'YT' ? d.acct : 'key saved'}` : ready ? 'Connected · switched off' : 'Not connected'}</span>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <span className="vn-mono" style={chip}>{d.format}</span>
        <span className="vn-mono" style={chip}>{d.rate}</span>
      </div>
      <span style={{ fontSize: 12, color: 'var(--text-meta)', lineHeight: 1.4, minHeight: 34 }}>{d.note}</span>
      {keyOpen && !ready ? (
        <form onSubmit={(e) => { e.preventDefault(); void submitKey(); }} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11, color: 'var(--text-meta)', fontWeight: 700, letterSpacing: '0.08em' }}>
            {d.name.toUpperCase()} STREAM KEY
            <input autoFocus type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder="Paste stream key"
              className="vn-mono" style={{ minHeight: 38, padding: '0 10px', borderRadius: 10, border: '1px solid rgba(255,236,220,0.15)', background: 'rgba(0,0,0,0.3)', color: 'var(--text-1)', fontSize: 12 }} />
          </label>
          <span style={{ fontSize: 11, color: 'var(--text-3)' }}>Saved privately on the server, never shown again.{d.p === 'IG' ? ' Instagram gives a new key every show.' : ''}</span>
          {err && <span role="alert" style={{ fontSize: 11, color: 'var(--error)' }}>{err}</span>}
          <div style={{ display: 'flex', gap: 6 }}>
            <button type="submit" disabled={!key.trim()} style={{ flex: 1, minHeight: 38, borderRadius: 10, border: 0, background: key.trim() ? '#F5EEE6' : 'rgba(245,238,230,0.25)', color: '#140D09', fontWeight: 700, fontSize: 13, cursor: key.trim() ? 'pointer' : 'not-allowed' }}>Connect</button>
            <button type="button" onClick={() => { setKeyOpen(false); setKey(''); }} style={{ minHeight: 38, padding: '0 12px', borderRadius: 10, border: '1px solid rgba(255,236,220,0.12)', background: 'transparent', color: 'var(--text-meta)', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>Cancel</button>
          </div>
        </form>
      ) : (
        <button onClick={toggle} disabled={locked && live} title={locked && live ? 'Can’t switch off while counting down' : undefined}
          style={{ minHeight: 42, borderRadius: 12, fontWeight: 700, fontSize: 13, cursor: 'pointer', ...(live ? { border: '1px solid rgba(255,236,220,0.12)', background: 'transparent', color: 'var(--text-meta)' } : { border: 0, background: '#F5EEE6', color: '#140D09' }) }}>
          {btnLabel}
        </button>
      )}
    </div>
  );
}

export function Destinations({ list, on, ready, locked }: { list: DestinationInfo[]; on: Record<Platform, boolean>; ready: Record<Platform, boolean>; locked: boolean }) {
  const count = list.filter((d) => on[d.p] && ready[d.p]).length;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span className="vn-label" style={{ letterSpacing: '0.16em' }}>DESTINATIONS</span>
        <span style={{ color: 'var(--text-3)', fontSize: 12 }}>{count} of {list.length} on · Claude writes a title and caption for each</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(250px, 100%), 1fr))', gap: 12 }}>
        {list.map((d) => <DestinationCard key={d.p} d={d} on={!!on[d.p]} ready={!!ready[d.p]} locked={locked} />)}
      </div>
    </div>
  );
}
