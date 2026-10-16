import type { FxUnitDef } from '../../demo/fx';
import { Knob } from './Knob';
import { YouBadge } from './YouBadge';

interface Props {
  unit: FxUnitDef;
  bpm: number;
  on: boolean;
  preset: string;
  values: Record<string, number>;
  isHeld: (id: string) => boolean;
  onPower: (on: boolean) => void;
  onPreset: (p: string) => void;
  onKnob: (param: string, v: number) => void;
}

/** One effects unit card: name, power, presets, four arc knobs, sends and a footer note. */
export function FxUnit({ unit: u, bpm, on, preset, values, isHeld, onPower, onPreset, onKnob }: Props) {
  const id = (p: string) => `fx.${u.key}.${p}`;
  const powerHeld = isHeld(id('power'));
  const presetHeld = isHeld(id('preset'));
  return (
    <section aria-label={u.name} style={{ borderRadius: 22, padding: 18, display: 'flex', flexDirection: 'column', gap: 14, background: 'linear-gradient(180deg, rgba(36,27,21,0.85), rgba(20,15,11,0.85))', border: '1px solid rgba(255,236,220,0.07)', boxShadow: 'inset 0 1px 0 rgba(255,236,220,0.05), 0 24px 60px rgba(0,0,0,0.4)', minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ width: 10, height: 34, borderRadius: 5, background: u.color, boxShadow: `0 0 14px ${u.color}`, flex: 'none' }} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
          <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 17 }}>{u.name}</span>
          <span style={{ fontSize: 12, color: 'var(--text-meta)' }}>{u.type(bpm)}</span>
        </div>
        <span style={{ flex: 1 }} />
        {powerHeld && <YouBadge />}
        <button onClick={() => onPower(!on)} aria-pressed={on} aria-label={`${u.name} ${on ? 'on' : 'off'}${powerHeld ? ', held by you' : ''}`}
          style={{
            minHeight: 32, minWidth: 52, borderRadius: 999, fontWeight: 800, fontSize: 12, cursor: 'pointer', flex: 'none',
            ...(on
              ? { border: 0, background: u.color, color: '#140D09', boxShadow: `0 0 12px ${u.color}${powerHeld ? ', 0 0 0 2px #120C09, 0 0 0 4px #F5EEE6' : ''}` }
              : { border: '1px solid rgba(255,236,220,0.15)', background: 'transparent', color: 'var(--text-meta)', boxShadow: powerHeld ? '0 0 0 2px #F5EEE6' : undefined }),
          }}>
          {on ? 'On' : 'Off'}
        </button>
      </div>

      <div role="group" aria-label={`${u.name} presets`} style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
        {u.presets.map((p) => {
          const sel = preset === p;
          return (
            <button key={p} onClick={() => onPreset(p)} aria-pressed={sel}
              style={{
                minHeight: 32, padding: '0 12px', borderRadius: 999, fontSize: 12, fontWeight: 700, cursor: 'pointer',
                ...(sel
                  ? { border: `1px solid ${presetHeld ? '#F5EEE6' : u.color}`, background: 'rgba(255,236,220,0.08)', color: 'var(--text-1)' }
                  : { border: '1px solid rgba(255,236,220,0.1)', background: 'transparent', color: 'var(--text-meta)' }),
              }}>
              {p}
            </button>
          );
        })}
        {presetHeld && <YouBadge />}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8 }}>
        {u.knobs.map((k) => {
          const v = values[k.param] ?? k.value;
          return (
            <Knob key={k.param} label={k.label} text={k.fmt(v, bpm)} value={v} min={k.min} max={k.max} step={k.step}
              color={u.color} dim={!on} held={isHeld(id(k.param))} onChange={(n) => onKnob(k.param, n)} />
          );
        })}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={{ fontSize: 10, letterSpacing: '0.12em', color: 'var(--text-3)', fontWeight: 700 }}>SENDS FROM</span>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {u.sends.map(([n, db]) => (
            <span key={n} style={{ padding: '4px 9px', borderRadius: 999, background: 'rgba(255,236,220,0.06)', fontSize: 12, color: '#E9DED2' }}>
              {n} <span className="vn-mono" style={{ color: 'var(--text-meta)' }}>{db}</span>
            </span>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 2, borderTop: '1px solid rgba(255,236,220,0.06)', marginTop: 'auto' }}>
        <span style={{ fontSize: 12, color: 'var(--text-soft)', paddingTop: 10 }}>{u.extra}</span>
      </div>
    </section>
  );
}
