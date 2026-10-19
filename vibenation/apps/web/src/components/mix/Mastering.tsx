import { useState, type CSSProperties } from 'react';
import type { ClientAction, EqBand, MasteringState } from '@vibenation/shared';

type EqKind = EqBand['kind'];
import { useMeters, useShow } from '../../store';
import { fromEngine, TYPE_TO_KIND, type Band } from '../../demo/mix';
import { EqGraph, EqPointEditor, EqTable } from './EqPanel';
import { COLORS, Group, KnobCell, db, ms, pct, type P } from './ChannelFx';
import { sendSoon } from './sendSoon';

// Every knob of the mastering chain, in signal order: master EQ → console → bus glue → tape → limiter, plus the
// master level. What's shown is what the engine runs; turning a knob sends it straight there.

const enumP = (sym: string, label: string, opts: string[], def: number): P => ({ sym, label, min: 0, max: opts.length - 1, step: 1, def, fmt: (v) => opts[Math.round(v)] ?? '', opts });

const CONSOLE: P[] = [
  { sym: 'drive', label: 'DRIVE', min: -12, max: 18, step: 0.5, def: 0, fmt: db },
  { sym: 'colour', label: 'COLOUR', min: 0, max: 100, step: 1, def: 40, fmt: pct },
  { sym: 'crosstalk', label: 'CROSSTALK', min: 0, max: 100, step: 1, def: 0, fmt: pct },
];
const BUS: P[] = [
  { sym: 'threshold', label: 'THRESH', min: -40, max: 0, step: 0.5, def: -10, fmt: db },
  enumP('ratio', 'RATIO', ['2:1', '4:1', '10:1'], 0),
  { sym: 'attack', label: 'ATTACK', min: 0.1, max: 30, step: 0.1, def: 10, fmt: ms },
  enumP('release', 'RELEASE', ['0.1 s', '0.3 s', '0.6 s', '1.2 s', 'Auto'], 4),
  { sym: 'sc_hpf', label: 'SC HPF', min: 0, max: 300, step: 5, def: 90, fmt: (v) => (v <= 0 ? 'off' : `${Math.round(v)} Hz`) },
  { sym: 'makeup', label: 'MAKEUP', min: 0, max: 20, step: 0.1, def: 0, fmt: db },
  { sym: 'mix', label: 'MIX', min: 0, max: 100, step: 1, def: 80, fmt: pct },
];
const TAPE: P[] = [
  enumP('speed', 'SPEED', ['7.5 ips', '15 ips', '30 ips'], 1),
  { sym: 'drive', label: 'DRIVE', min: -12, max: 18, step: 0.5, def: 0, fmt: db },
  { sym: 'saturation', label: 'SATURATION', min: 0, max: 100, step: 1, def: 30, fmt: pct },
  { sym: 'bias', label: 'BIAS', min: 0, max: 100, step: 1, def: 50, fmt: pct },
  { sym: 'bump', label: 'HEAD BUMP', min: 0, max: 100, step: 1, def: 40, fmt: pct },
  { sym: 'wow', label: 'WOW', min: 0, max: 100, step: 1, def: 0, fmt: pct },
  { sym: 'flutter', label: 'FLUTTER', min: 0, max: 100, step: 1, def: 0, fmt: pct },
  { sym: 'mix', label: 'MIX', min: 0, max: 100, step: 1, def: 50, fmt: pct },
];
const CEILING: P = { sym: 'ceiling', label: 'CEILING', min: -6, max: -0.5, step: 0.1, def: -2, fmt: (v) => `${v.toFixed(1)} dBTP` };
const LEVEL: P = { sym: 'drive', label: 'LEVEL', min: -20, max: 12, step: 0.1, def: 0, fmt: db };

const panel: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 };
const toggle = (on: boolean): CSSProperties => ({
  minHeight: 32, padding: '0 12px', borderRadius: 999, fontSize: 12, fontWeight: 700, cursor: 'pointer',
  border: `1px solid ${on ? 'rgba(185,166,255,0.5)' : 'rgba(255,236,220,0.14)'}`,
  background: on ? 'rgba(185,166,255,0.16)' : 'rgba(255,236,220,0.04)', color: on ? 'var(--ai-text)' : 'var(--text-soft)',
});

function Section({ m, keyName, params, offset }: { m: MasteringState; keyName: 'console' | 'bus' | 'tape'; params: P[]; offset: number }) {
  const vals = m[keyName];
  return (
    <>
      {params.filter((p) => p.sym in vals).map((p, i) => (
        <KnobCell key={p.sym} p={p} v={vals[p.sym] ?? p.def} color={COLORS[(i + offset) % 7]}
          onChange={(v) => sendSoon(`master.${keyName}.${p.sym}`, { type: 'master', [keyName]: { [p.sym]: v } } as ClientAction)} />
      ))}
    </>
  );
}

export function MasteringPanel() {
  const s = useShow();
  const meters = useMeters();
  const [pick, setPick] = useState(0);
  const m = s?.mastering;
  if (!m) return <div style={{ padding: 24, color: 'var(--text-meta)', textAlign: 'center' }}>The mix engine isn't connected, so the mastering chain can't be shown.</div>;

  const bands = fromEngine(m.eq);
  const sendEq = (next: Band[]) => sendSoon('master.eq', { type: 'master', eq: next.map((b) => [TYPE_TO_KIND[b.type], b.f, b.type === 'HPF' || b.type === 'LPF' ? 0 : b.g, b.q] as [EqKind, number, number, number]) });
  const onBand = (i: number, p: Partial<Band>) => sendEq(bands.map((b, k) => (k === i ? { ...b, ...p } : b)));
  const sel = Math.min(pick, Math.max(0, bands.length - 1));
  const add = (f: number, g: number) => { if (bands.length < 8) { sendEq([...bands, { type: 'BELL', f, g, q: 1 }]); setPick(bands.length); } };
  const remove = (i: number) => { sendEq(bands.filter((_, k) => k !== i)); setPick(Math.max(0, i - 1)); };
  const master = meters?.master ?? s?.master;

  return (
    <div style={panel}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
        <span className="vn-label">MASTER EQ</span>
        <span style={{ flex: 1 }} />
        <button type="button" onClick={() => sendSoon('master.tone', { type: 'master', tone: !m.tone })} aria-pressed={m.tone} style={toggle(m.tone)}
          title="Tone keeper: slowly nudges the master EQ to keep Mix F's tone">{m.tone ? 'Tone keeper on' : 'Tone keeper off'}</button>
      </div>
      <EqGraph section="keys" bands={bands} editable post onBand={onBand} live={meters?.masterSpec} selected={sel} onSelect={setPick} onAdd={add} />
      <EqTable bands={bands} selected={sel} onSelect={setPick} />
      <EqPointEditor bands={bands} selected={sel} onBand={onBand} onAdd={() => add(1000, 0)} onRemove={remove} />

      <Group title="Console" note="analog summing colour">
        <Section m={m} keyName="console" params={CONSOLE} offset={0} />
      </Group>
      <Group title="Bus glue" note="parallel compressor on the whole mix">
        <Section m={m} keyName="bus" params={BUS} offset={2} />
      </Group>
      <Group title="Tape" note="saturation and warmth">
        <Section m={m} keyName="tape" params={TAPE} offset={4} />
      </Group>
      <Group title="Limiter and level" note={`true peak, last stage · limiting ${master && master.limiterGr >= 0.05 ? '−' + master.limiterGr.toFixed(1) : '0'} dB`}>
        <KnobCell p={CEILING} v={m.ceiling} color={COLORS[1]} onChange={(v) => sendSoon('master.ceiling', { type: 'master', ceiling: v })} />
        <KnobCell p={LEVEL} v={m.drive} color={COLORS[3]} onChange={(v) => sendSoon('master.fader', { type: 'master_fader', db: v })} />
      </Group>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
        <button type="button" onClick={() => sendSoon('master.leveller', { type: 'master', leveller: !m.leveller })} aria-pressed={m.leveller} style={toggle(m.leveller)}
          title="Automatic level: rides the master level toward −16 LUFS">{m.leveller ? 'Auto level on' : 'Auto level off'}</button>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>The mix is locked: tone keeper and auto level stay off unless you turn them on here.</span>
      </div>
    </div>
  );
}
