import { useCallback, useState, type CSSProperties } from 'react';
import type { ChannelState } from '@vibenation/shared';
import { useShow } from '../store';
import { changesFor, easyFor, eqFor, knobsFor, type Band, type KnobKey, type MacroKey } from '../demo/mix';
import { Strip } from '../components/mix/Strip';
import { MasterStrip } from '../components/mix/Meters';
import { ChangeCards, SelectedPanel, type ChMix } from '../components/mix/SelectedPanel';
import { sendControl } from '../components/mix/sendSoon';

// Mixing station — Engineer mode. Strips + master on the left, selected channel on the right.

type Layer = 'all' | 'a' | 'b' | 'bus' | 'fxr';
const LAYERS: [Layer, string][] = [['all', 'All 16'], ['a', 'CH 1–8'], ['b', 'CH 9–16'], ['bus', 'Buses'], ['fxr', 'FX returns']];

const panel: CSSProperties = { borderRadius: 22, background: 'linear-gradient(180deg, rgba(36,27,21,0.8), rgba(20,15,11,0.8))', border: '1px solid rgba(255,236,220,0.07)', boxShadow: 'inset 0 1px 0 rgba(255,236,220,0.05), 0 24px 60px rgba(0,0,0,0.4)' };

const initMix = (c: ChannelState): ChMix => {
  const eq = eqFor(c.n, c.section);
  return { a: eq.a, bands: eq.b, easy: easyFor(c.section), knobs: knobsFor(c.section), changes: changesFor(c.n, c.section) };
};

const KNOB_ID: Record<KnobKey, string> = { thresh: 'comp.thresh', ratio: 'comp.ratio', attack: 'comp.attack', release: 'comp.release', plate: 'fx.plate', delay: 'fx.delay4' };

export function MixScreen() {
  const s = useShow();
  const [sel, setSel] = useState(9);
  const [layer, setLayer] = useState<Layer>('all');
  const [fine, setFine] = useState(false);
  const [ab, setAb] = useState<'A' | 'B'>('B');
  const [mixes, setMixes] = useState<Record<number, ChMix>>({});
  const pick = useCallback((n: number) => setSel(n), []);

  if (!s) return null;
  const chans = s.channels;
  const cur = chans.find((c) => c.n === sel) ?? chans[0];
  const mixOf = (c: ChannelState) => mixes[c.n] ?? initMix(c);
  const mix = mixOf(cur);
  const n = cur.n;
  const patch = (p: Partial<ChMix>) => setMixes((m) => ({ ...m, [n]: { ...(m[n] ?? initMix(cur)), ...p } }));

  const onBand = (i: number, p: Partial<Band>) => {
    patch({ bands: mix.bands.map((b, k) => (k === i ? { ...b, ...p } : b)) });
    for (const key of Object.keys(p) as (keyof Band)[]) {
      if (key === 'type') continue;
      if (p[key] !== mix.bands[i][key]) sendControl(`ch${n}.eq.${i + 1}.${key === 'g' ? 'gain' : key === 'f' ? 'freq' : 'q'}`, p[key] as number);
    }
  };
  const onEasy = (k: MacroKey, v: number) => { patch({ easy: { ...mix.easy, [k]: v } }); sendControl(`ch${n}.fx.${k}`, v); };
  const onKnob = (k: KnobKey, v: number) => { patch({ knobs: { ...mix.knobs, [k]: v } }); sendControl(`ch${n}.${KNOB_ID[k]}`, v); };
  const onUndo = (id: string) => {
    patch({ changes: mix.changes.map((c) => (c.id === id ? { ...c, undone: true } : c)) });
    sendControl(`ch${n}.change.${id}.undo`, 1);
  };
  const onAmount = (id: string, v: number) => {
    patch({ changes: mix.changes.map((c) => (c.id === id ? { ...c, amount: v } : c)) });
    sendControl(`ch${n}.change.${id}.amount`, v);
  };

  const shown = layer === 'a' ? chans.filter((c) => c.n <= 8) : layer === 'b' ? chans.filter((c) => c.n > 8) : chans;
  const stripsOn = layer === 'all' || layer === 'a' || layer === 'b';

  return (
    <main style={{ display: 'flex', flexWrap: 'wrap', gap: 18, padding: '20px 22px', flex: '1 1 auto', minWidth: 0 }}>
      <section aria-label="Channel strips" style={{ ...panel, flex: '999 1 720px', minWidth: 0, padding: 16, overflowX: 'auto' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <div style={{ display: 'flex', gap: 2, padding: 3, borderRadius: 12, background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,236,220,0.06)' }} role="group" aria-label="Layers">
            {LAYERS.map(([l, label]) => (
              <button key={l} onClick={() => setLayer(l)} aria-pressed={layer === l} style={{ minHeight: 34, padding: '0 12px', borderRadius: 9, border: 0, fontSize: 12, cursor: 'pointer', fontWeight: layer === l ? 700 : 600, background: layer === l ? 'rgba(255,236,220,0.12)' : 'transparent', color: layer === l ? 'var(--text-1)' : 'var(--text-meta)' }}>{label}</button>
            ))}
          </div>
          <span style={{ flex: 1 }} />
          <button onClick={() => setFine((f) => !f)} aria-pressed={fine} style={{ minHeight: 34, padding: '0 14px', borderRadius: 10, fontWeight: 700, fontSize: 12, cursor: 'pointer', border: `1px solid ${fine ? 'var(--text-1)' : 'rgba(255,236,220,0.12)'}`, background: fine ? 'var(--text-1)' : 'rgba(255,236,220,0.04)', color: fine ? '#140D09' : 'var(--text-soft)' }}>FINE faders</button>
        </div>
        {stripsOn ? (
          <div style={{ display: 'flex', gap: 6, minWidth: layer === 'all' ? 1100 : 640 }}>
            {shown.map((c) => (
              <Strip key={c.n} c={c} selected={c.n === sel} fine={fine} compOn={mixOf(c).easy.comp > 0} onPick={pick} />
            ))}
            <MasterStrip />
          </div>
        ) : (
          <div style={{ minHeight: 200, borderRadius: 16, border: '1px dashed rgba(255,236,220,0.14)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, color: 'var(--text-meta)', textAlign: 'center' }}>
            {layer === 'bus' ? 'Buses' : 'FX returns'} are coming in the audio milestone.
          </div>
        )}
      </section>

      <aside aria-label="Selected channel" style={{ flex: '1 1 400px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <SelectedPanel c={cur} mix={mix} bpm={s.bpm} ab={ab} setAb={setAb} onBand={onBand} onEasy={onEasy} onKnob={onKnob} />
        <ChangeCards changes={mix.changes} ab={ab} setAb={setAb} onUndo={onUndo} onAmount={onAmount} />
      </aside>
    </main>
  );
}
