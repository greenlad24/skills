import { useEffect, useRef, useState, type ReactNode } from 'react';

export type SlateMode = 'Starting soon' | 'Break' | 'Thanks for watching';

export const SLATE_COPY: Record<SlateMode, { pill: string; headline: string; foot: string; showTime: boolean }> = {
  'Starting soon': { pill: 'STARTING SOON', headline: 'The show starts in', foot: 'Grab a drink — the band is tuning up', showTime: true },
  Break: { pill: 'SHORT BREAK', headline: 'We’ll be back in', foot: 'Grab a drink — set two starts soon', showTime: true },
  'Thanks for watching': { pill: 'THAT’S A WRAP', headline: 'Thanks for watching', foot: 'See you next week', showTime: false },
};

export interface SlateColours { c1: string; c2: string; c3: string }

/** The viewer-facing slate, drawn at its native 1280×720. Scale it with <Fit16x9>. */
export function SlateArt({ mode, time, colours }: { mode: SlateMode; time: string; colours: SlateColours }) {
  const M = SLATE_COPY[mode];
  const { c1, c2, c3 } = colours;
  return (
    <div style={{ width: 1280, height: 720, boxSizing: 'border-box', position: 'relative', overflow: 'hidden', background: '#140B08', color: '#F5EEE6', fontFamily: 'var(--font-display)' }}>
      <div aria-hidden="true" style={{ position: 'absolute', inset: 0, background: `radial-gradient(70% 90% at 50% 115%, ${c3} 0%, ${c2} 30%, ${c1} 52%, rgba(20,11,8,0) 78%)`, opacity: 0.9 }} />
      <div aria-hidden="true" style={{ position: 'absolute', left: '50%', bottom: -330, width: 760, height: 760, marginLeft: -380, borderRadius: '50%', border: '2px solid rgba(255,195,113,0.35)' }} />
      <div aria-hidden="true" style={{ position: 'absolute', left: '50%', bottom: -230, width: 560, height: 560, marginLeft: -280, borderRadius: '50%', border: '2px solid rgba(255,195,113,0.25)' }} />

      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 120, gap: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 16px', borderRadius: 999, background: 'rgba(42,22,16,0.7)', border: '1px solid rgba(245,238,230,0.18)', fontSize: 15, fontWeight: 600, letterSpacing: '0.12em' }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#FFC371' }} />{M.pill}
        </div>
        <h1 style={{ margin: 0, fontSize: 54, fontWeight: 600, letterSpacing: '-0.02em' }}>{M.headline}</h1>
        {M.showTime ? (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 168, fontWeight: 700, lineHeight: 1, letterSpacing: '-0.04em', fontVariantNumeric: 'tabular-nums' }}>{time}</div>
        ) : (
          <div style={{ fontSize: 40, fontWeight: 700, color: '#FFE3BF', textAlign: 'center', maxWidth: 900, lineHeight: 1.2 }}>Subscribe to Music Live Love for the next show</div>
        )}
        <div style={{ marginTop: 8, fontSize: 22, color: '#E9DCCD' }}>[Band Name] · live cover band session</div>
      </div>

      <div style={{ position: 'absolute', left: 48, right: 48, bottom: 40, display: 'flex', alignItems: 'center', gap: 16 }}>
        <div style={{ width: 56, height: 56, borderRadius: 12, border: '1px dashed rgba(245,238,230,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: '#E9DCCD' }}>LOGO</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span style={{ fontSize: 13, color: '#E9DCCD', letterSpacing: '0.1em', fontWeight: 600 }}>NOW PLAYING</span>
          <span style={{ fontSize: 18, fontWeight: 600 }}>[break playlist track]</span>
        </div>
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 16, color: '#E9DCCD' }}>{M.foot}</span>
      </div>
    </div>
  );
}

/** Scales a fixed 1280×720 child to the available width, keeping 16:9. */
export function Fit16x9({ children, label }: { children: ReactNode; label: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.5);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setScale(e.contentRect.width / 1280));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={ref} role="img" aria-label={label} style={{ width: '100%', aspectRatio: '16 / 9', position: 'relative', overflow: 'hidden', borderRadius: 18, boxShadow: '0 24px 60px rgba(0,0,0,0.5)' }}>
      <div aria-hidden="true" style={{ position: 'absolute', left: 0, top: 0, width: 1280, height: 720, transform: `scale(${scale})`, transformOrigin: '0 0' }}>{children}</div>
    </div>
  );
}
