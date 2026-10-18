import { memo, useState, type CSSProperties } from 'react';
import type { ChannelState } from '@vibenation/shared';
import { send, useAutoMuted } from '../../store';
import { MINI_EQ, SECTION_COLOR, specFor } from '../../demo/mix';
import { ChannelGr, ChannelMeter } from './Meters';
import { Fader, faderText } from './Fader';

const lamp = (on: boolean, c: string): CSSProperties => ({
  fontSize: 8, fontWeight: 800, letterSpacing: '0.04em', padding: '2px 3px', borderRadius: 4,
  ...(on ? { background: c, color: '#140D09', boxShadow: `0 0 8px ${c}` } : { background: 'rgba(255,236,220,0.05)', color: '#5E544B' }),
});

const sm = (active: boolean, c: string, fg: string): CSSProperties => ({
  flex: 1, minHeight: 26, borderRadius: 7, fontSize: 11, fontWeight: 800, cursor: 'pointer',
  border: `1px solid ${active ? c : 'rgba(255,236,220,0.1)'}`, background: active ? c : 'rgba(255,236,220,0.04)', color: active ? fg : 'var(--text-soft)',
  boxShadow: active ? `0 0 10px ${c}` : undefined,
});

const tagBase: CSSProperties = { fontSize: 9, fontWeight: 800, letterSpacing: '0.06em', padding: '2px 6px', borderRadius: 5 };

/** One channel bay. Name/ring select it; meters update on their own. */
export const Strip = memo(function Strip({ c, selected, fine, compOn, onPick }: { c: ChannelState; selected: boolean; fine: boolean; compOn: boolean; onPick: (n: number) => void }) {
  const [local, setLocal] = useState<number | null>(null);
  const auto = useAutoMuted(c.n) && !c.mute; // muted by the engine: nobody plays it right now
  const db = local ?? c.fader;
  const col = SECTION_COLOR[c.section];
  const i = c.n - 1;
  const name = c.role ?? c.name;
  const spec = specFor(c.section, 14, c.n);

  return (
    <div style={{
      flex: '1 0 60px', minWidth: 60, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 7, padding: '10px 5px 12px', borderRadius: 16,
      background: selected ? 'linear-gradient(180deg, rgba(255,236,220,0.1), rgba(255,236,220,0.03))' : 'linear-gradient(180deg, rgba(0,0,0,0.22), rgba(0,0,0,0.12))',
      boxShadow: `inset 0 1px 0 rgba(255,236,220,0.05), inset 0 0 0 1px ${selected ? 'rgba(245,238,230,0.5)' : 'rgba(255,236,220,0.05)'}${selected ? ', 0 12px 30px rgba(0,0,0,0.45)' : ''}`,
    }}>
      <button onClick={() => onPick(c.n)} aria-label={`Select ${name}`} aria-pressed={selected} style={{ width: '100%', padding: 0, border: 0, background: 'transparent', color: 'inherit', cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 11, fontWeight: 700, lineHeight: 1.2, minHeight: 28, textAlign: 'center', color: 'var(--text-1)' }} title={c.role ? `${c.role} (on ${c.name})` : undefined}>{name}</span>
        <span style={{ width: '100%', height: 34, borderRadius: 7, background: 'rgba(0,0,0,0.45)', boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.6)', position: 'relative', overflow: 'hidden', display: 'block' }} role="img" aria-label={`Live spectrum and EQ for ${name}`}>
          <span style={{ position: 'absolute', left: 3, right: 3, bottom: 2, top: 4, display: 'flex', alignItems: 'flex-end', gap: 1 }} aria-hidden="true">
            {spec.map((b, k) => (
              <span key={k} style={{ flex: 1, height: c.mute ? '4%' : b.h, borderRadius: '1px 1px 0 0', background: col + '66', transformOrigin: 'bottom', animation: `vnRta ${b.d} ease-in-out ${b.dl} infinite` }} />
            ))}
          </span>
          <svg width="100%" height="34" viewBox="0 0 54 22" preserveAspectRatio="none" style={{ position: 'absolute', inset: 0 }} aria-hidden="true">
            <path d={MINI_EQ[i % 4]} fill="none" stroke={col} strokeWidth="1.4" vectorEffect="non-scaling-stroke" />
          </svg>
        </span>
      </button>
      <span style={{ display: 'flex', gap: 3 }} aria-label={`Processing on ${name}`}>
        <span style={lamp(true, col)}>EQ</span>
        <span style={lamp(compOn, 'var(--ai)')}>CMP</span>
        <span style={lamp(c.section === 'drums' && c.n <= 2, '#E9DED2')}>GT</span>
      </span>
      <ChannelGr i={i} fallback={c.gr} />
      <span style={{ display: 'flex', gap: 4, width: '100%' }}>
        <button onClick={() => send({ type: 'solo', ch: c.n, on: !c.solo })} aria-pressed={c.solo} aria-label={`Solo ${name}`} style={sm(c.solo, '#F5EEE6', '#140D09')}>S</button>
        <button onClick={() => send({ type: 'mute', ch: c.n, on: !c.mute })} aria-pressed={c.mute} aria-label={auto ? `${name} is muted automatically (not playing); press to mute it yourself` : `Mute ${name}`}
          title={auto ? 'Muted automatically: nobody is playing it. It opens by itself when the instrument comes in.' : undefined}
          style={auto ? { ...sm(true, 'rgba(185,166,255,0.22)', 'var(--ai-text)'), boxShadow: 'inset 0 0 0 1px rgba(185,166,255,0.5)' } : sm(c.mute, '#F5EEE6', '#140D09')}>M</button>
      </span>
      <span style={{ padding: '3px 0', width: '100%', textAlign: 'center', borderRadius: 6, background: 'rgba(0,0,0,0.35)', fontFamily: 'var(--font-mono)', fontSize: 11, color: auto ? 'var(--ai-text)' : '#E9DED2' }}>{c.mute ? 'mute' : auto ? 'auto mute' : faderText(db)}</span>
      <span style={{ height: 180, display: 'flex', gap: 4, alignItems: 'flex-end' }}>
        <ChannelMeter i={i} muted={c.mute} fallback={c.meter} idle={auto} />
        <Fader ch={c.n} name={name} db={db} fine={fine} onLocal={setLocal} />
      </span>
      {c.held ? (
        <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: 'var(--text-1)', filter: 'drop-shadow(0 0 6px rgba(245,238,230,0.7))' }} aria-label="Held by you">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>
          <span style={{ fontSize: 9, fontWeight: 800 }}>YOU</span>
        </span>
      ) : c.aiRecent ? (
        <span style={{ ...tagBase, background: 'rgba(185,166,255,0.16)', color: 'var(--ai-text)' }} title="Claude adjusted this in the last 30 s">AI</span>
      ) : c.role ? (
        <span style={{ ...tagBase, background: 'rgba(255,236,220,0.06)', color: 'var(--text-soft)' }} title={`Guest role on ${c.name}`}>GUEST</span>
      ) : (
        <span style={{ fontSize: 9, color: 'rgba(0,0,0,0)', padding: '2px 6px' }} aria-hidden="true">·</span>
      )}
      <button onClick={() => onPick(c.n)} aria-label={`Select channel ${c.n}`} style={{
        width: 34, height: 34, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0, cursor: 'pointer',
        fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 13, color: 'var(--text-1)', background: 'radial-gradient(circle at 50% 35%, #2A211B, #120D0A)',
        border: `2px solid ${col}`, boxShadow: `0 0 ${selected ? '16px' : '8px'} ${col}`, opacity: c.mute || auto ? 0.4 : 1,
      }}>{c.n}</button>
    </div>
  );
});
