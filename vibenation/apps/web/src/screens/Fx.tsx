import { useState } from 'react';
import { send, useShow } from '../store';
import { go } from '../route';
import { FX_UNITS } from '../demo/fx';
import { FxUnit } from '../components/fx/FxUnit';

type Values = Record<string, Record<string, number>>;

type Saved = Record<string, number | string>;
const saved = <T,>(c: Saved, id: string, fallback: T): T => (id in c ? (c[id] as T) : fallback);

// Start from the server's last values so a reload or a second device shows the same rack.
const initialValues = (c: Saved): Values =>
  Object.fromEntries(FX_UNITS.map((u) => [u.key, Object.fromEntries(u.knobs.map((k) => [k.param, saved(c, `fx.${u.key}.${k.param}`, k.value)]))]));

/** Effects rack: shared reverbs, tempo-synced delay and doubler every channel can send to. */
export function FxScreen() {
  const s = useShow();
  const c = s?.controls ?? {};
  const [values, setValues] = useState<Values>(() => initialValues(c));
  const [power, setPower] = useState<Record<string, boolean>>(() => Object.fromEntries(FX_UNITS.map((u) => [u.key, saved<number | string>(c, `fx.${u.key}.power`, 1) !== 0])));
  const [preset, setPreset] = useState<Record<string, string>>(() => Object.fromEntries(FX_UNITS.map((u) => [u.key, saved(c, `fx.${u.key}.preset`, u.preset)])));
  // Controls touched in this tab; the server's `held` list covers reloads and other devices.
  const [mine, setMine] = useState<Set<string>>(() => new Set());

  if (!s) return null;
  const bpm = s.bpm;
  const serverHeld = new Set(s.held);
  const isHeld = (id: string) => mine.has(id) || serverHeld.has(id);

  const control = (id: string, value: number | string) => {
    send({ type: 'control', id, value });
    if (!mine.has(id)) setMine((m) => new Set(m).add(id));
  };

  return (
    <main style={{ padding: '26px 28px', display: 'flex', flexDirection: 'column', gap: 20, color: 'var(--text-1)' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12 }}>
        <button onClick={() => go('mix')}
          style={{ minHeight: 32, padding: 0, border: 0, background: 'transparent', color: 'var(--text-meta)', fontWeight: 600, fontSize: 14, cursor: 'pointer' }}>
          ← Mix
        </button>
        <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 30, fontWeight: 800, letterSpacing: '-0.02em' }}>Effects rack</h1>
        <span style={{ color: 'var(--text-meta)' }}>
          Shared effects every channel can send to. Tempo follows the band:{' '}
          <b className="vn-mono" style={{ color: 'var(--text-1)' }}>{Math.round(bpm)} BPM</b> (detected)
        </span>
        <span style={{ flex: 1 }} />
        <span style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 14px', borderRadius: 999, background: 'rgba(185,166,255,0.1)', border: '1px solid rgba(185,166,255,0.35)', color: 'var(--ai-text)', fontWeight: 600, fontSize: 13 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--ai)', boxShadow: '0 0 10px var(--ai)' }} />
          Claude tuning · touch a knob to take it over
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(300px, 100%), 1fr))', gap: 16 }}>
        {FX_UNITS.map((u) => (
          <FxUnit key={u.key} unit={u} bpm={bpm} on={power[u.key]} preset={preset[u.key]} values={values[u.key]} isHeld={isHeld}
            onPower={(on) => { setPower((p) => ({ ...p, [u.key]: on })); control(`fx.${u.key}.power`, on ? 1 : 0); }}
            onPreset={(name) => {
              setPreset((p) => ({ ...p, [u.key]: name }));
              // A preset only moves knobs Claude still holds; knobs you touched stay where you left them.
              const recall = u.presetValues[name] ?? {};
              setValues((v) => {
                const next = { ...v[u.key] };
                for (const [param, val] of Object.entries(recall)) if (!isHeld(`fx.${u.key}.${param}`)) next[param] = val;
                return { ...v, [u.key]: next };
              });
              control(`fx.${u.key}.preset`, name);
            }}
            onKnob={(param, n) => {
              setValues((v) => ({ ...v, [u.key]: { ...v[u.key], [param]: n } }));
              control(`fx.${u.key}.${param}`, n);
            }} />
        ))}
      </div>
    </main>
  );
}
