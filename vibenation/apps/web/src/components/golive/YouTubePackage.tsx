import { useEffect, useState } from 'react';

interface Pkg { titles: string[]; description: string; tags: string[]; thumbnailText: string; createdAt: number }

const small = { fontSize: 10, letterSpacing: '0.12em', color: 'var(--text-meta)', fontWeight: 700 } as const;
const pillBtn = { minHeight: 28, padding: '0 10px', borderRadius: 999, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(255,236,220,0.04)', color: 'var(--text-1)', fontSize: 11, cursor: 'pointer' } as const;

export function Thumbnail({ from, text = 'LIVE FUNK & SOUL' }: { from: string; text?: string }) {
  return (
    <div role="img" aria-label="Generated thumbnail: band on stage with bold title text"
      style={{ aspectRatio: '16 / 9', borderRadius: 16, overflow: 'hidden', position: 'relative', background: 'radial-gradient(70% 90% at 70% 100%, rgba(255,120,60,0.7), rgba(0,0,0,0) 60%), radial-gradient(50% 60% at 75% 10%, rgba(255,111,160,0.45), rgba(0,0,0,0) 70%), linear-gradient(120deg,#1A0B07,#2E140B 60%,#140806)', boxShadow: '0 16px 40px rgba(0,0,0,0.5)' }}>
      <svg viewBox="0 0 160 90" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} aria-hidden="true">
        <g fill="#050302" opacity="0.95">
          <circle cx="112" cy="36" r="12" /><path d="M94 90 C96 62 104 50 112 50 C120 50 128 62 130 90 Z" />
          <rect x="111" y="46" width="2" height="44" fill="#1A0B07" />
          <circle cx="146" cy="46" r="8" /><path d="M134 90 C136 70 140 60 146 60 C152 60 156 70 158 90 Z" />
        </g>
      </svg>
      <div style={{ position: 'absolute', left: 14, top: 14, bottom: 14, width: '58%', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 4 }}>
        <span style={{ alignSelf: 'flex-start', padding: '3px 8px', borderRadius: 5, background: 'var(--on-air-fill)', color: '#FFFFFF', fontSize: 10, fontWeight: 800, letterSpacing: '0.1em' }}>LIVE</span>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 26, lineHeight: 0.95, letterSpacing: '-0.02em', color: '#FFF4E6', textShadow: '0 3px 12px rgba(0,0,0,0.6)', textTransform: 'uppercase' }}>{text}</span>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 12, color: '#FFC371' }}>Music Live Love · Not AI</span>
      </div>
      <span style={{ position: 'absolute', right: 10, bottom: 10, padding: '3px 8px', borderRadius: 6, background: 'rgba(10,6,4,0.65)', backdropFilter: 'blur(8px)', color: '#E9DED2', fontSize: 10, fontWeight: 600 }}>preview · GPT Image from {from} frame</span>
    </div>
  );
}

export function YouTubePackage({ channel }: { channel: string | null }) {
  const [pkg, setPkg] = useState<Pkg | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');

  useEffect(() => { fetch('/api/package').then((r) => r.json()).then((j) => setPkg(j.package)).catch(() => undefined); }, []);

  const write = async () => {
    setBusy(true); setError('');
    const r = await fetch('/api/package/generate', { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}' });
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (r.ok) setPkg(j.package); else setError(j.error ?? 'Claude could not write it right now.');
  };
  const save = async (next: Pkg) => {
    const r = await fetch('/api/package', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(next) });
    const j = await r.json().catch(() => ({}));
    if (r.ok) setPkg(j.package); else setError(j.error ?? 'Not saved.');
  };
  const pick = (i: number) => {
    if (!pkg) return;
    const titles = [...pkg.titles];
    [titles[0], titles[i]] = [titles[i], titles[0]];
    void save({ ...pkg, titles });
  };

  const header = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--ai)', boxShadow: '0 0 10px var(--ai)' }} />
      <span className="vn-label" style={{ color: 'var(--ai-text)' }}>YOUTUBE PACKAGE · WRITTEN BY CLAUDE</span>
      <span style={{ flex: 1 }} />
      {pkg && <button style={pillBtn} onClick={write} disabled={busy}>{busy ? 'Writing…' : 'Rewrite'}</button>}
    </div>
  );

  if (!pkg) {
    return (
      <>
        {header}
        <p style={{ margin: 0, color: 'var(--text-soft)', fontSize: 13, lineHeight: 1.5 }}>Claude writes a click-optimised title (with ranked alternatives), an SEO description with live chapters, tags, and captions for every platform.</p>
        <button onClick={write} disabled={busy} style={{ minHeight: 44, borderRadius: 12, border: 0, background: 'var(--text-1)', color: '#140D09', fontWeight: 700, cursor: busy ? 'wait' : 'pointer' }}>{busy ? 'Claude is writing… (about 20 s)' : 'Write it with Claude'}</button>
        {error && <span role="alert" style={{ color: 'var(--error)', fontSize: 12 }}>{error}</span>}
      </>
    );
  }

  const title = pkg.titles[0] ?? '';
  return (
    <>
      {header}
      <Thumbnail from="a live camera" text={pkg.thumbnailText} />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={small}>TITLE · optimised for clicks</span>
          <span style={{ flex: 1 }} />
          <button style={pillBtn} onClick={() => { if (editing) void save({ ...pkg, titles: [draft, ...pkg.titles.slice(1)] }); else setDraft(title); setEditing((e) => !e); }} aria-pressed={editing}>{editing ? 'Save' : 'Edit'}</button>
        </div>
        {editing ? (
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={3} aria-label="Stream title" maxLength={100}
            style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 15, lineHeight: 1.3, padding: '8px 10px', borderRadius: 10, border: '1px solid rgba(255,236,220,0.15)', background: 'rgba(0,0,0,0.3)', color: 'var(--text-1)', resize: 'vertical' }} />
        ) : (
          <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 16, lineHeight: 1.3 }}>{title}</span>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {pkg.titles.slice(1).map((a, i) => (
            <button key={i} onClick={() => pick(i + 1)} title="Use this title instead"
              style={{ textAlign: 'left', padding: '8px 10px', borderRadius: 10, border: '1px solid rgba(255,236,220,0.07)', background: 'rgba(255,236,220,0.03)', color: 'var(--text-soft)', fontSize: 12, cursor: 'pointer', lineHeight: 1.35 }}>{a}</button>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <span style={small}>DESCRIPTION · SEO</span>
        <div style={{ borderRadius: 12, background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(255,236,220,0.06)', padding: '10px 12px', fontSize: 12, lineHeight: 1.55, color: '#E9DED2', whiteSpace: 'pre-line', maxHeight: 220, overflowY: 'auto' }}>{pkg.description}</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
          {pkg.tags.map((t) => (
            <span key={t} style={{ padding: '3px 9px', borderRadius: 999, background: 'rgba(255,236,220,0.06)', color: 'var(--text-soft)', fontSize: 11 }}>{t}</span>
          ))}
        </div>
      </div>
      {error && <span role="alert" style={{ color: 'var(--error)', fontSize: 12 }}>{error}</span>}

      <dl style={{ margin: 0, display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '7px 18px', fontSize: 12 }}>
        <dt style={{ color: 'var(--text-meta)' }}>Channel</dt><dd style={{ margin: 0, fontWeight: 600 }}>{channel ?? '@MusicLiveLove (not connected yet)'}</dd>
        <dt style={{ color: 'var(--text-meta)' }}>Quality</dt><dd className="vn-mono" style={{ margin: 0 }}>1080p30 · 9 Mbps · AAC 128k</dd>
      </dl>
    </>
  );
}
