import { memo, useState } from 'react';
import { Fader } from './Fader';
import { fmtDb, useMeters, useShow } from '../../store';

// Meter pieces subscribe to the high-rate meter store on their own, so strips
// only re-render on full state pushes.

const LED_MASK = 'repeating-linear-gradient(to top, rgba(11,8,6,0) 0 3px, rgba(11,8,6,0.9) 3px 4px)';

/** Vertical LED meter next to a fader. */
export const ChannelMeter = memo(function ChannelMeter({ i, muted, fallback, idle }: { i: number; muted: boolean; fallback: number; idle?: boolean }) {
  const m = useMeters();
  const v = muted ? 0 : (m?.ch[i] ?? fallback);  // idle (auto-muted): still shows what comes in, greyed
  return (
    <span style={{ width: 5, height: '100%', borderRadius: 3, background: 'rgba(255,236,220,0.06)', position: 'relative', overflow: 'hidden' }}>
      <span style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: `${Math.round(Math.min(1, Math.max(0, v)) * 100)}%`, background: idle ? 'rgba(233,222,210,0.28)' : 'linear-gradient(to top, #8F8378 0%, #E9DED2 68%, #FFB224 88%, #FF5A52 100%)', transition: 'height 90ms linear' }} />
      <span style={{ position: 'absolute', inset: 0, background: LED_MASK }} />
    </span>
  );
});

const grText = (gr: number) => (gr < 0.05 ? '0' : '−' + gr.toFixed(1));

/** Compressor gain-reduction bar + number on a strip. */
export const ChannelGr = memo(function ChannelGr({ i, fallback }: { i: number; fallback: number }) {
  const m = useMeters();
  const gr = m?.gr[i] ?? fallback;
  return (
    <span style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 4, fontSize: 9, color: 'var(--text-meta)', fontFamily: 'var(--font-mono)' }}>
      <span style={{ flex: 1, height: 4, borderRadius: 2, background: 'rgba(255,236,220,0.06)', position: 'relative', overflow: 'hidden' }}>
        <span style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: `${Math.min(100, gr * 12)}%`, background: 'var(--ai)' }} />
      </span>
      {grText(gr)}
    </span>
  );
});

/** "GR −4.5 dB" on the selected-channel LCD. */
export function LcdGr({ i, fallback }: { i: number; fallback: number }) {
  const m = useMeters();
  const gr = m?.gr[i] ?? fallback;
  return <span style={{ color: '#6B5444' }}>GR {gr < 0.05 ? '0' : '−' + gr.toFixed(1)} dB</span>;
}

const masterBar = (pct: number) => (
  <span style={{ width: 8, height: '100%', borderRadius: 3, background: 'rgba(255,236,220,0.06)', position: 'relative', overflow: 'hidden' }}>
    <span style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: `${pct}%`, background: 'linear-gradient(to top, #8F8378 0%, #E9DED2 70%, #FFB224 92%)', transition: 'height 90ms linear' }} />
    <span style={{ position: 'absolute', inset: 0, background: LED_MASK }} />
  </span>
);

/** Master bay: loudness, limiter, master fader. Clicking MASTER opens every mastering knob (onPick). */
export function MasterStrip({ selected, onPick }: { selected?: boolean; onPick?: () => void } = {}) {
  const m = useMeters();
  const s = useShow();
  const [local, setLocal] = useState<number | null>(null);
  const ms = m?.master ?? s?.master;
  if (!ms) return null;
  const drive = local ?? ms.drive ?? 0;
  const held = s?.held.includes('master.fader');
  // Short-term loudness −36..−10 LUFS → 0..100 %; R a touch under L for life.
  const l = Math.round(Math.min(100, Math.max(0, ((ms.lufsS + 36) / 26) * 100)));
  const r = Math.max(0, l - 2);
  return (
    <div style={{ width: 92, flex: 'none', borderRadius: 16, padding: '10px 8px', background: 'linear-gradient(180deg, rgba(255,94,98,0.22), rgba(255,153,102,0.08) 22%, rgba(0,0,0,0.25) 40%)', border: `1px solid ${selected ? 'rgba(245,238,230,0.7)' : 'rgba(255,153,102,0.25)'}`, boxShadow: selected ? '0 12px 30px rgba(0,0,0,0.45)' : undefined, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, justifyContent: 'flex-end' }}>
      <button type="button" onClick={onPick} aria-pressed={selected} aria-label="Open the mastering knobs"
        style={{ fontSize: 11, fontWeight: 800, letterSpacing: '0.12em', padding: '6px 10px', borderRadius: 8, border: `1px solid ${selected ? 'var(--text-1)' : 'rgba(255,236,220,0.18)'}`, background: selected ? 'rgba(255,236,220,0.14)' : 'rgba(0,0,0,0.25)', color: 'var(--text-1)', cursor: onPick ? 'pointer' : 'default' }}>MASTER</button>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 700, letterSpacing: '-0.03em' }} aria-label={`Integrated loudness ${fmtDb(ms.lufsI)} LUFS`}>{fmtDb(ms.lufsI)}</span>
      <span style={{ fontSize: 10, color: 'var(--text-soft)' }}>LUFS · TP {fmtDb(ms.truePeak)}</span>
      <span style={{ padding: '3px 6px', borderRadius: 6, background: 'rgba(0,0,0,0.35)', fontFamily: 'var(--font-mono)', fontSize: 11, color: '#E9DED2' }} title="Master level into the limiter">{fmtDb(drive)} dB</span>
      <span style={{ height: 200, display: 'flex', gap: 4, alignItems: 'flex-end' }}>
        {masterBar(l)}{masterBar(r)}
        <Fader ch={0} name="Master" db={drive} fine={false} onLocal={setLocal} toAction={(db) => ({ type: 'master_fader', db })} resetDb={0} />
      </span>
      <span style={{ fontSize: 9, fontWeight: 800, color: held ? 'var(--text-1)' : 'var(--ai-text)' }}>{held ? 'YOU' : 'AUTO LEVEL'}</span>
      <span style={{ fontSize: 10, color: 'var(--text-soft)' }}>limiter {ms.limiterGr < 0.05 ? '0' : '−' + ms.limiterGr.toFixed(1)} dB</span>
    </div>
  );
}
