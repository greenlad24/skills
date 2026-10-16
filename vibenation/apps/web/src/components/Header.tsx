import type { Platform } from '@vibenation/shared';
import { useElapsed, useShow } from '../store';
import { go, useRoute, type Route } from '../route';
import { Transport } from './Transport';

export const PLATFORM_BG: Record<Platform, string> = { YT: '#C4302B', TW: '#7B4BD6', FB: '#2D63D8', TT: '#1F1F1F', IG: '#C23A7E' };
const PLATFORM_NAME: Record<Platform, string> = { YT: 'YouTube', TW: 'Twitch', FB: 'Facebook', TT: 'TikTok', IG: 'Instagram' };

export function Logo() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ width: 34, height: 34, borderRadius: 10, background: 'radial-gradient(circle at 30% 25%, #FFD08A 0%, #FF8A3D 45%, #C8401F 100%)', boxShadow: '0 6px 20px rgba(255,122,61,0.35), inset 0 1px 0 rgba(255,255,255,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#1A0E08" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M3 13c2.5-6 4.5-6 6 0s3.5 6 6 0 3.5-6 6 0" /></svg>
      </div>
      <span style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 19, letterSpacing: '-0.02em' }}>VibeNation</span>
    </div>
  );
}

const pill = { display: 'flex', alignItems: 'center', borderRadius: 999, background: 'rgba(255,236,220,0.05)', border: '1px solid rgba(255,236,220,0.08)' } as const;

const NAV: [Route, string][] = [['show', 'Show'], ['mix', 'Mix'], ['fx', 'Effects'], ['golive', 'Go Live'], ['slate', 'Slate']];

export function Header() {
  const s = useShow();
  const route = useRoute();
  const elapsed = useElapsed(s?.onAir ? s.liveSince : null);
  if (!s) return null;
  const dests = (Object.keys(s.destinations) as Platform[]).filter((p) => s.destinations[p]);
  const heldCount = s.held.length;
  return (
    <header style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 14, padding: '14px 22px', borderBottom: '1px solid rgba(255,236,220,0.07)', background: 'rgba(18,12,9,0.6)', backdropFilter: 'blur(16px)', position: 'sticky', top: 0, zIndex: 10 }}>
      <Logo />
      <div style={{ height: 26, width: 1, background: 'rgba(255,236,220,0.1)' }} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        <span style={{ fontWeight: 600, fontSize: 14 }}>{s.showName}</span>
        <span style={{ color: 'var(--text-meta)', fontSize: 12 }}>youtube.com/@MusicLiveLove · 1080p60</span>
      </div>
      <nav aria-label="Screens" style={{ display: 'flex', gap: 2, padding: 3, borderRadius: 12, background: 'rgba(255,236,220,0.05)', border: '1px solid rgba(255,236,220,0.08)' }}>
        {NAV.map(([r, label]) => (
          <button key={r} onClick={() => go(r)} aria-current={route === r ? 'page' : undefined}
            style={{ minHeight: 34, padding: '0 12px', borderRadius: 9, border: 0, cursor: 'pointer', fontWeight: route === r ? 700 : 600, background: route === r ? 'var(--text-1)' : 'transparent', color: route === r ? '#140D09' : 'var(--text-meta)' }}>
            {label}
          </button>
        ))}
      </nav>
      <div style={{ flex: '1 1 40px' }} />
      {s.onAir ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 14px 7px 10px', borderRadius: 999, background: 'linear-gradient(180deg, #2E7BFF, #1A5ED6)', color: '#FFFFFF', fontWeight: 700, fontFamily: 'var(--font-mono)', fontSize: 13, boxShadow: '0 6px 24px rgba(31,102,224,0.45), inset 0 1px 0 rgba(255,255,255,0.25)' }}>
          <span style={{ width: 9, height: 9, borderRadius: '50%', background: '#FFFFFF', animation: 'vnPulse 1.8s ease-out infinite' }} />LIVE · {elapsed}
        </div>
      ) : (
        <div style={{ ...pill, gap: 8, padding: '7px 14px', fontWeight: 700, fontSize: 13, color: 'var(--text-soft)' }}>OFF AIR</div>
      )}
      <div style={{ ...pill, gap: 6, padding: '5px 10px 5px 6px' }} aria-label={`Live on ${dests.length} platforms`}>
        {dests.map((p) => (
          <span key={p} title={PLATFORM_NAME[p]} style={{ width: 22, height: 22, borderRadius: 7, background: PLATFORM_BG[p], color: '#FFFFFF', fontSize: 9, fontWeight: 800, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 0 2px #120C09' }}>{p}</span>
        ))}
        <span style={{ fontSize: 12, fontWeight: 700, color: '#E9DED2' }}>on {dests.length}</span>
      </div>
      <div style={{ ...pill, gap: 7, padding: '7px 12px', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#C9BDB1" strokeWidth="2" aria-label="Viewers"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z" /><circle cx="12" cy="12" r="3" /></svg>{s.health.viewers.toLocaleString('en')}
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#C9BDB1" strokeWidth="2" aria-label="Likes" style={{ marginLeft: 6 }}><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21l7.8-7.5 1-1.1a5.5 5.5 0 0 0 0-7.8z" /></svg>{s.health.likes}
      </div>
      <div style={{ ...pill, gap: 12, padding: '7px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-soft)' }} aria-label="Stream health">
        <span>{s.health.mbps.toFixed(1)} Mbps</span><span>{s.health.fps} fps</span><span>CPU {s.health.cpu}%</span>
        <span style={{ color: s.health.dropped ? 'var(--warn)' : undefined }}>{s.health.dropped} dropped</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 14px', borderRadius: 999, background: 'rgba(185,166,255,0.1)', border: '1px solid rgba(185,166,255,0.35)', color: 'var(--ai-text)', fontWeight: 600, fontSize: 13 }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--ai)', boxShadow: '0 0 10px var(--ai)', animation: 'vnBreath 2.4s ease-in-out infinite' }} />
        AUTO · Claude is running the show{heldCount > 0 && <span style={{ color: 'var(--text-1)' }}> · {heldCount} held by you</span>}
      </div>
      {s.audio ? <Transport a={s.audio} /> : (
        <span role="status" style={{ padding: '4px 10px', borderRadius: 999, background: 'rgba(255,90,82,0.12)', border: '1px solid rgba(255,90,82,0.4)', color: 'var(--error)', fontSize: 11, fontWeight: 700, letterSpacing: '0.1em' }}>MIX ENGINE OFFLINE</span>
      )}
    </header>
  );
}
