import type { CSSProperties } from 'react';
import type { ChannelState } from '@vibenation/shared';
import { send } from '../../store';
import { Knob } from './Knob';

// Every effect the engine runs on the selected channel, as knobs: compressor, the character
// inserts (our analog models), the bleed expander and the three effect sends. Turning one sends
// it straight to the engine and holds that effect for the person for the rest of the show.

export type P = { sym: string; label: string; min: number; max: number; step: number; def: number; fmt: (v: number) => string; opts?: string[] };
export const db = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)} dB`;
export const pct = (v: number) => `${Math.round(v)}%`;
export const ms = (v: number) => `${v < 10 ? v.toFixed(1) : Math.round(v)} ms`;
const x10 = (v: number) => v.toFixed(1);

/** Parameters of our insert plugins (ranges from their Faust sources in services/audio/plugins). */
const INSERT: Record<string, { name: string; params: P[] }> = {
  fet: { name: 'FET colour', params: [
    { sym: 'input', label: 'INPUT', min: -20, max: 40, step: 0.5, def: 0, fmt: db },
    { sym: 'ratio', label: 'RATIO', min: 0, max: 4, step: 1, def: 0, fmt: (v) => ['4:1', '8:1', '12:1', '20:1', 'All'][v] ?? '', opts: ['4:1', '8:1', '12:1', '20:1', 'All'] },
    { sym: 'attack', label: 'ATTACK', min: 20, max: 800, step: 10, def: 300, fmt: (v) => `${Math.round(v)} µs` },
    { sym: 'release', label: 'RELEASE', min: 50, max: 1100, step: 10, def: 300, fmt: ms },
    { sym: 'colour', label: 'COLOUR', min: 0, max: 100, step: 1, def: 50, fmt: pct },
    { sym: 'mix', label: 'MIX', min: 0, max: 100, step: 1, def: 100, fmt: pct },
    { sym: 'output', label: 'OUTPUT', min: -30, max: 20, step: 0.5, def: 0, fmt: db },
  ] },
  opto: { name: 'Opto leveller', params: [
    { sym: 'peak_reduction', label: 'PEAK RED.', min: 0, max: 100, step: 1, def: 30, fmt: pct },
    { sym: 'gain', label: 'GAIN', min: -20, max: 30, step: 0.5, def: 0, fmt: db },
    { sym: 'sc_high', label: 'SC HIGH', min: -12, max: 12, step: 0.5, def: 0, fmt: db },
    { sym: 'colour', label: 'COLOUR', min: 0, max: 100, step: 1, def: 30, fmt: pct },
    { sym: 'mix', label: 'MIX', min: 0, max: 100, step: 1, def: 100, fmt: pct },
  ] },
  deesser: { name: 'De-esser', params: [
    { sym: 'freq', label: 'FREQ', min: 3000, max: 12000, step: 100, def: 6500, fmt: (v) => `${(v / 1000).toFixed(1)} kHz` },
    { sym: 'sensitivity', label: 'SENS', min: 0, max: 100, step: 1, def: 50, fmt: pct },
    { sym: 'range', label: 'MAX RED.', min: 0, max: 24, step: 0.5, def: 8, fmt: db },
  ] },
  pultec: { name: 'Pultec EQ', params: [
    { sym: 'low_freq', label: 'LOW FREQ', min: 0, max: 3, step: 1, def: 2, fmt: (v) => ['20 Hz', '30 Hz', '60 Hz', '100 Hz'][v] ?? '', opts: ['20 Hz', '30 Hz', '60 Hz', '100 Hz'] },
    { sym: 'low_boost', label: 'LOW BOOST', min: 0, max: 10, step: 0.1, def: 0, fmt: x10 },
    { sym: 'low_atten', label: 'LOW ATTEN', min: 0, max: 10, step: 0.1, def: 0, fmt: x10 },
    { sym: 'high_boost', label: 'HIGH BOOST', min: 0, max: 10, step: 0.1, def: 0, fmt: x10 },
    { sym: 'tube', label: 'TUBE', min: 0, max: 100, step: 1, def: 30, fmt: pct },
    { sym: 'output', label: 'OUTPUT', min: -12, max: 12, step: 0.5, def: 0, fmt: db },
  ] },
};

const COMP: P[] = [
  { sym: 'thresh', label: 'THRESH', min: -60, max: 0, step: 0.5, def: -20, fmt: db },
  { sym: 'ratio', label: 'RATIO', min: 1, max: 20, step: 0.1, def: 3, fmt: (v) => `${v.toFixed(1)}:1` },
  { sym: 'attack', label: 'ATTACK', min: 0.1, max: 100, step: 0.1, def: 10, fmt: ms },
  { sym: 'release', label: 'RELEASE', min: 10, max: 1000, step: 5, def: 150, fmt: ms },
  { sym: 'makeup', label: 'MAKEUP', min: 0, max: 24, step: 0.1, def: 0, fmt: db },
  { sym: 'mix', label: 'MIX', min: 0, max: 1, step: 0.01, def: 1, fmt: (v) => pct(v * 100) },
];
const GATE: P[] = [
  { sym: 'thresh', label: 'THRESH', min: -80, max: -10, step: 0.5, def: -50, fmt: db },
  { sym: 'range', label: 'DEPTH', min: 0, max: 60, step: 0.5, def: 12, fmt: db },
  { sym: 'attack', label: 'ATTACK', min: 0.1, max: 50, step: 0.1, def: 1.5, fmt: ms },
  { sym: 'hold', label: 'HOLD', min: 0, max: 1000, step: 5, def: 120, fmt: ms },
  { sym: 'release', label: 'RELEASE', min: 5, max: 2000, step: 5, def: 300, fmt: ms },
];
const SENDS: { fx: 'plate' | 'room' | 'delay'; label: string }[] = [{ fx: 'plate', label: 'PLATE' }, { fx: 'room', label: 'ROOM' }, { fx: 'delay', label: 'ECHO' }];
const SEND_OFF = -40; // at or below this the send is off

export const COLORS = ['#E08A5A', '#E6C07A', '#B9A6FF', '#7FD1C3', '#E58FB0', '#8FA3D9', '#9FC7A8'];
const group: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 10, padding: 12, borderRadius: 14, background: 'rgba(255,236,220,0.035)', border: '1px solid rgba(255,236,220,0.06)' };
const grid: CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(64px, 1fr))', gap: 10 };

export function KnobCell({ p, v, color, onChange }: { p: P; v: number; color: string; onChange: (v: number) => void }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, minWidth: 0 }}>
      <Knob value={v} min={p.min} max={p.max} step={p.step} color={color} label={p.label} valueText={p.fmt(v)} onChange={onChange} />
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-1)', whiteSpace: 'nowrap' }}>{p.fmt(v)}</span>
      <span style={{ fontSize: 9, letterSpacing: '0.08em', color: 'var(--text-meta)', fontWeight: 700, whiteSpace: 'nowrap' }}>{p.label}</span>
    </div>
  );
}

export function Group({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <div style={group}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>{title}</span>
        {note && <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{note}</span>}
      </div>
      <div style={grid}>{children}</div>
    </div>
  );
}

/** The selected channel's real effects chain, every parameter on a knob. */
export function ChannelFx({ c }: { c: ChannelState }) {
  const ch = c.n;
  const comp = c.comp;
  const inserts = c.inserts ?? [];
  const sends = c.sends ?? { plate: null, room: null, delay: null };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {comp && (
        <Group title="Compressor" note={comp.ratio <= 1.01 ? 'off at 1:1' : undefined}>
          {COMP.map((p, i) => (
            <KnobCell key={p.sym} p={p} v={comp[p.sym as keyof typeof comp] ?? p.def} color={COLORS[i % 7]} onChange={(v) => send({ type: 'comp', ch, [p.sym]: v })} />
          ))}
        </Group>
      )}
      {inserts.map((ins, slot) => {
        const def = INSERT[ins.kind];
        if (!def) return null;
        return (
          <Group key={`${ins.kind}${slot}`} title={def.name}>
            {def.params.map((p, i) => (
              <KnobCell key={p.sym} p={p} v={ins.params[p.sym] ?? p.def} color={COLORS[(i + 2) % 7]} onChange={(v) => send({ type: 'insert', ch, slot, params: { [p.sym]: v } })} />
            ))}
          </Group>
        );
      })}
      {c.gate && (
        <Group title="Bleed expander" note="turns the mic down between phrases">
          {GATE.map((p, i) => (
            <KnobCell key={p.sym} p={p} v={c.gate![p.sym as keyof NonNullable<typeof c.gate>] ?? p.def} color={COLORS[(i + 4) % 7]} onChange={(v) => send({ type: 'gate', ch, [p.sym]: v })} />
          ))}
        </Group>
      )}
      <Group title="Effect sends" note="all the way down = off">
        {SENDS.map((s, i) => {
          const v = sends[s.fx] ?? SEND_OFF;
          const p: P = { sym: s.fx, label: s.label, min: SEND_OFF, max: 0, step: 0.5, def: SEND_OFF, fmt: (x) => (x <= SEND_OFF ? 'off' : db(x)) };
          return <KnobCell key={s.fx} p={p} v={v} color={COLORS[(i + 1) % 7]} onChange={(x) => send({ type: 'send', ch, fx: s.fx, db: x <= SEND_OFF ? null : x })} />;
        })}
      </Group>
      {!comp && inserts.length === 0 && !c.gate && <span style={{ fontSize: 12, color: 'var(--text-3)' }}>This channel runs no compressor or inserts; only its effect sends are adjustable.</span>}
    </div>
  );
}
