import { useEffect, useState } from 'react';
import type { Platform } from '@vibenation/shared';
import { send, useShow } from '../store';
import { DESTINATIONS } from '../demo/golive';
import { Preflight } from '../components/golive/Preflight';
import { Destinations } from '../components/golive/Destinations';
import { YouTubePackage } from '../components/golive/YouTubePackage';
import { GoLiveButton } from '../components/golive/GoLiveButton';
import { ShowServer } from '../components/golive/ShowServer';

const COUNTDOWN_S = 5;
const linkBtn = { background: 'none', border: 0, padding: 0, cursor: 'pointer', fontWeight: 600, color: '#FF9A5A', textDecoration: 'underline' } as const;
const ghostBtn = { flex: 1, minHeight: 44, borderRadius: 12, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(255,236,220,0.04)', color: 'var(--text-1)', fontWeight: 700, cursor: 'pointer' } as const;

export function GoLiveScreen() {
  const s = useShow();
  const [countdown, setCountdown] = useState<number | null>(null);
  const [privacy, setPrivacy] = useState<'public' | 'private'>('public');
  const [pb, setPb] = useState<{ director: { version: number }; shows: number; lessons: { k: string; t: string }[] } | null>(null);
  useEffect(() => { fetch('/api/playbook').then((r) => r.json()).then(setPb).catch(() => undefined); }, [s?.golive.phase]);
  const [scheduled, setScheduled] = useState<{ id: string; title: string; scheduledStart?: string }[]>([]);
  useEffect(() => {
    if (!s?.youtube.connected) return;
    fetch('/api/youtube/upcoming').then((r) => r.json()).then((j) => setScheduled(j.items ?? [])).catch(() => undefined);
  }, [s?.youtube.connected]);

  // Tick the 5-second countdown; send golive when it reaches 0.
  useEffect(() => {
    if (countdown === null) return;
    if (countdown <= 0) { send({ type: 'golive', privacy }); setCountdown(null); return; }
    const t = window.setTimeout(() => setCountdown((c) => (c === null ? null : c - 1)), 1000);
    return () => clearTimeout(t);
  }, [countdown]);

  // If the show goes live from elsewhere, drop any running countdown.
  useEffect(() => { if (s?.onAir) setCountdown(null); }, [s?.onAir]);

  if (!s) return null;

  const on = s.destinations;
  const checks = s.preflight;
  const count = (Object.keys(on) as Platform[]).filter((p) => on[p] && s.ready[p]).length;
  const perfect = checks.filter((c) => c.level === 'ok').length;
  const firstError = checks.find((c) => c.level === 'error');
  const blocker = firstError
    ? { text: `${firstError.title}: ${firstError.detail}`, level: 'error' as const }
    : count === 0 ? { text: 'Connect at least one destination to go live', level: 'warn' as const } : null;
  const start = (p: 'public' | 'private' = 'public') => { if (!blocker && !s.onAir) { setPrivacy(p); setCountdown(COUNTDOWN_S); } };
  const next = scheduled.find((b) => b.scheduledStart && Date.parse(b.scheduledStart) > Date.now() - 3600_000);

  return (
    <main style={{ flex: '1 1 auto', display: 'flex', flexWrap: 'wrap', gap: 24, padding: 'clamp(20px, 3vw, 36px) clamp(16px, 3vw, 40px)', maxWidth: 1380, width: '100%', margin: '0 auto', background: 'radial-gradient(700px 500px at 0% 100%, rgba(61,139,255,0.06), rgba(61,139,255,0) 60%)' }}>
      <section aria-label="Pre-flight checks" style={{ flex: '999 1 560px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <span style={{ fontSize: 11, letterSpacing: '0.16em', color: '#FF9A5A', fontWeight: 700 }}>PRE-FLIGHT · {perfect} OF {checks.length} PERFECT</span>
          <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 'clamp(34px, 4vw, 46px)', fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.05 }}>
            {s.onAir ? 'You’re on air.' : 'Ready when you are.'}
          </h1>
          <p style={{ margin: 0, color: 'var(--text-soft)', fontSize: 16, lineHeight: 1.55, maxWidth: 600 }}>
            Claude checked everything below. Tap Go Live and it takes over — cameras, mix, breaks and the ending.
          </p>
        </div>
        <Preflight checks={checks} />
        <Destinations list={DESTINATIONS} on={on} ready={s.ready} locked={countdown !== null} />
      </section>

      <aside style={{ flex: '1 1 380px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 18 }}>
        <section aria-label="Go live" style={{ borderRadius: 24, background: 'linear-gradient(180deg, rgba(40,30,23,0.85), rgba(20,15,11,0.85))', border: '1px solid rgba(255,236,220,0.08)', boxShadow: 'inset 0 1px 0 rgba(255,236,220,0.06), 0 30px 70px rgba(0,0,0,0.5)', padding: 22, display: 'flex', flexDirection: 'column', gap: 18 }}>
          <ShowServer />
          <YouTubePackage channel={s.youtube.channel} />
          <GoLiveButton onAir={s.onAir} liveSince={s.liveSince} count={count} blocker={blocker} countdown={countdown} onGo={() => start('public')} onCancel={() => setCountdown(null)} />
          {s.golive.message && <span role="status" style={{ fontSize: 13, textAlign: 'center', color: s.golive.phase === 'error' ? 'var(--error)' : 'var(--text-soft)' }}>{s.golive.message}</span>}
          {s.onAir ? (
            <button style={{ ...ghostBtn, flex: 'none' }} onClick={() => { if (confirm('End the stream? Viewers see the thanks-for-watching slate, then the stream stops.')) send({ type: 'end' }); }}>End the show…</button>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, fontSize: 13 }}>
              <button style={linkBtn} disabled={!!blocker} onClick={() => start('private')}>Start a private test stream first</button>
            </div>
          )}
        </section>

        <section aria-label="What Claude learned" style={{ position: 'relative', borderRadius: 20, padding: 1, background: 'linear-gradient(140deg, rgba(185,166,255,0.85), rgba(185,166,255,0.12) 60%, rgba(255,138,61,0.35))', boxShadow: '0 14px 40px rgba(124,102,217,0.2)' }}>
          <div style={{ borderRadius: 19, padding: 16, background: 'linear-gradient(180deg, #1C1626, #15101C)', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
              <span className="vn-label" style={{ color: 'var(--ai-text)' }}>LEARNED FROM LAST SHOW</span>
              <span style={{ flex: 1 }} />
              <span className="vn-mono" style={{ fontSize: 11, color: '#8F86A8' }}>playbook v{pb?.director.version ?? 1} · {pb?.shows ?? 0} shows</span>
            </div>
            {pb?.lessons.length ? pb.lessons.map((l, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <span style={{ flex: 'none', marginTop: 2, padding: '1px 6px', borderRadius: 5, background: 'rgba(185,166,255,0.15)', color: '#D9CFFF', fontSize: 9, fontWeight: 800, letterSpacing: '0.06em' }}>{l.k}</span>
                <span style={{ fontSize: 12, lineHeight: 1.45, color: '#ECE6FF' }}>{l.t}</span>
              </div>
            )) : <span style={{ fontSize: 12, lineHeight: 1.45, color: '#ECE6FF' }}>No shows reviewed yet. After each show Claude reviews its decision log against your manual cuts, holds and undos, and lists what it changes for the next show here.</span>}

          </div>
        </section>

        {!s.onAir && next && (
          <section aria-label="Scheduled stream" style={{ borderRadius: 20, border: '1px solid rgba(255,236,220,0.1)', background: 'rgba(255,236,220,0.03)', padding: 18, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#C9BDB1" strokeWidth="2" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M8 3v4M16 3v4M3 10h18" /></svg>
              <span style={{ fontWeight: 700 }}>Scheduled on YouTube</span>
              <span style={{ flex: 1 }} />
              <span className="vn-mono" style={{ fontSize: 12, color: 'var(--text-soft)' }}>{next.scheduledStart ? new Date(next.scheduledStart).toLocaleString('en-GB', { weekday: 'short', hour: '2-digit', minute: '2-digit' }) : ''}</span>
            </div>
            <span style={{ color: 'var(--text-meta)', fontSize: 13, lineHeight: 1.5 }}>“{next.title}” — Go Live binds the stream to this broadcast.</span>
            <button style={{ ...ghostBtn, cursor: blocker || countdown !== null ? 'not-allowed' : 'pointer' }} disabled={!!blocker || countdown !== null} onClick={() => start('public')}>Go now</button>
          </section>
        )}
      </aside>
    </main>
  );
}
