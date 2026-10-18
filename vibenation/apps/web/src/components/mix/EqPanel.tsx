import { useRef } from 'react';
import type { Section } from '@vibenation/shared';
import { fmtDb } from '../../store';
import { BAND_COLOR, SECTION_COLOR, specFor, TYPE_LABEL, type Band, type BandType } from '../../demo/mix';

// EQ graph: viewBox 360×170, log frequency (100 Hz at x=60, 120 px/decade), 0 dB at y=85, 6 px/dB.
const W = 360;
const H = 170;
const xOf = (f: number) => 60 + 120 * Math.log10(f / 100);
const fOf = (x: number) => 100 * 10 ** ((x - 60) / 120);
const yOf = (db: number) => Math.min(H - 2, Math.max(2, 85 - 6 * db));
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

function resp(b: Band, f: number) {
  switch (b.type) {
    case 'HPF': return -10 * Math.log10(1 + (b.f / f) ** 8); // 24 dB/oct, as in the engine
    case 'LPF': return -10 * Math.log10(1 + (f / b.f) ** 8);
    case 'LOW': return b.g / (1 + (f / b.f) ** 2);
    case 'SHELF': return b.g / (1 + (b.f / f) ** 2);
    default: { const x = Math.log2(f / b.f); return b.g * Math.exp(-((x * b.q) ** 2) * 2.8); }
  }
}

const XS = Array.from({ length: W / 4 + 1 }, (_, k) => k * 4);
const pathOf = (fn: (f: number) => number) => XS.map((x, k) => `${k ? 'L' : 'M'}${x} ${yOf(fn(fOf(x))).toFixed(1)}`).join(' ');
const fillOf = (b: Band) => `${pathOf((f) => resp(b, f))} L${W} 85 L0 85 Z`;

export const fmtFreq = (f: number) => (f >= 1000 ? `${(f / 1000).toFixed(f < 10000 ? 1 : 0).replace(/\.0$/, '')}k` : String(Math.round(f)));
const isFilter = (b: Band) => b.type === 'HPF' || b.type === 'LPF';
const nodeY = (b: Band) => (isFilter(b) ? yOf(-3) : yOf(b.g));

/** Big EQ over the live spectrum. Nodes drag (x = freq, y = gain); keys: ←/→ freq, ↑/↓ gain, Shift+↑/↓ Q.
 *  Double-click an empty spot to add a point there. */
export function EqGraph({ section, bands, editable, post, onBand, live, selected, onSelect, onAdd }: {
  section: Section; bands: Band[]; editable: boolean; post: boolean; onBand: (i: number, patch: Partial<Band>) => void; live?: number[];
  selected?: number; onSelect?: (i: number) => void; onAdd?: (f: number, g: number) => void;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const dragging = useRef<number | null>(null);
  const col = SECTION_COLOR[section];
  const spec = specFor(section, 48, post ? 100 : 200);
  const curve = pathOf((f) => bands.reduce((s, b) => s + resp(b, f), 0));

  const moveTo = (i: number, cx: number, cy: number) => {
    const r = svg.current!.getBoundingClientRect();
    const sx = ((cx - r.left) / r.width) * W;
    const sy = ((cy - r.top) / r.height) * H;
    const b = bands[i];
    const f = Math.round(clamp(fOf(sx), b.type === 'HPF' ? 20 : 30, b.type === 'HPF' ? 400 : 18000));
    if (isFilter(b)) onBand(i, { f });
    else onBand(i, { f, g: Math.round(clamp((85 - sy) / 6, -12, 12) * 2) / 2 });
  };

  return (
    <div style={{ borderRadius: 16, background: 'radial-gradient(120% 120% at 50% 0%, #1A120E, #080504)', border: '1px solid rgba(255,236,220,0.06)', padding: 10, position: 'relative' }}>
      <div style={{ position: 'absolute', left: 10, right: 10, top: 18, bottom: 30, display: 'flex', alignItems: 'flex-end', gap: 2 }} aria-hidden="true">
        {live
          ? live.map((v, k) => (
            <span key={k} style={{ flex: 1, height: `${Math.round(Math.max(2, Math.min(100, ((v + 90) / 80) * 100)))}%`, borderRadius: '2px 2px 0 0', background: `linear-gradient(to top, ${col}22, ${col}88)`, transition: 'height 100ms linear' }} />
          ))
          : spec.map((b, k) => (
            <span key={k} style={{ flex: 1, height: b.h, borderRadius: '2px 2px 0 0', background: `linear-gradient(to top, ${col}22, ${col}88)`, transformOrigin: 'bottom', animation: `vnRta ${b.d} ease-in-out ${b.dl} infinite` }} />
          ))}
      </div>
      <span style={{ position: 'absolute', right: 16, top: 14, display: 'flex', alignItems: 'center', gap: 6, padding: '3px 8px', borderRadius: 999, background: 'rgba(10,6,4,0.6)', fontSize: 10, fontWeight: 800, letterSpacing: '0.1em', color: '#E9DED2' }}>
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--text-1)' }} />LIVE SPECTRUM · {post ? 'POST' : 'PRE'}
      </span>
      <svg ref={svg} viewBox={`0 0 ${W} ${H}`} width="100%" style={{ position: 'relative', display: 'block', touchAction: 'none' }} role="group" aria-label="EQ: numbered bands over the live spectrum"
        onDoubleClick={(e) => {
          if (!editable || !onAdd || e.target !== e.currentTarget) return;
          const r = svg.current!.getBoundingClientRect();
          onAdd(Math.round(clamp(fOf(((e.clientX - r.left) / r.width) * W), 30, 18000)), Math.round(clamp((85 - ((e.clientY - r.top) / r.height) * H) / 6, -12, 12) * 2) / 2);
        }}>
        <g stroke="rgba(255,236,220,0.06)" strokeWidth="1">
          <line x1="0" y1="85" x2="360" y2="85" /><line x1="0" y1="45" x2="360" y2="45" /><line x1="0" y1="125" x2="360" y2="125" />
          <line x1="60" y1="0" x2="60" y2="170" /><line x1="140" y1="0" x2="140" y2="170" /><line x1="220" y1="0" x2="220" y2="170" /><line x1="300" y1="0" x2="300" y2="170" />
        </g>
        {bands.map((b, i) => <path key={i} d={fillOf(b)} fill={BAND_COLOR[i % 8]} fillOpacity={0.22} />)}
        <path d={curve} fill="none" stroke="var(--text-1)" strokeWidth="2.5" />
        <g fontFamily="Sora, sans-serif" fontSize="9" fontWeight="800" textAnchor="middle">
          {bands.map((b, i) => {
            const x = clamp(xOf(b.f), 9, W - 9);
            const y = nodeY(b);
            return (
              <g key={i} role="slider" tabIndex={editable ? 0 : -1} aria-label={`Band ${i + 1} ${b.type}`} aria-valuetext={`${fmtFreq(b.f)} Hz${isFilter(b) ? '' : `, ${fmtDb(b.g)} dB`}`}
                style={{ cursor: editable ? 'move' : 'default', outline: 'none' }}
                onPointerDown={(e) => { onSelect?.(i); if (!editable) return; (e.currentTarget as Element).setPointerCapture(e.pointerId); dragging.current = i; }}
                onFocus={() => onSelect?.(i)}
                onPointerMove={(e) => { if (dragging.current === i) moveTo(i, e.clientX, e.clientY); }}
                onPointerUp={() => { dragging.current = null; }}
                onPointerCancel={() => { dragging.current = null; }}
                onKeyDown={(e) => {
                  if (!editable) return;
                  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') onBand(i, { f: Math.round(clamp(b.f * (e.key === 'ArrowRight' ? 1.06 : 1 / 1.06), 20, 18000)) });
                  else if ((e.key === 'ArrowUp' || e.key === 'ArrowDown') && e.shiftKey && b.type === 'BELL') onBand(i, { q: Math.round(clamp(b.q + (e.key === 'ArrowUp' ? 0.1 : -0.1), 0.3, 8) * 10) / 10 });
                  else if ((e.key === 'ArrowUp' || e.key === 'ArrowDown') && !isFilter(b)) onBand(i, { g: clamp(b.g + (e.key === 'ArrowUp' ? 0.5 : -0.5), -12, 12) });
                  else return;
                  e.preventDefault();
                }}>
                <circle cx={x} cy={y} r="14" fill="transparent" />
                {selected === i && <circle cx={x} cy={y} r="11.5" fill="none" stroke="var(--text-1)" strokeWidth="2" />}
                <circle cx={x} cy={y} r="8" fill={BAND_COLOR[i % 8]} />
                <text x={x} y={y + 3} fill="#140D09" style={{ pointerEvents: 'none' }}>{i + 1}</text>
              </g>
            );
          })}
        </g>
        <g fill="#7D7268" fontSize="9" fontFamily="JetBrains Mono, monospace"><text x="54" y="166">100</text><text x="134" y="166">500</text><text x="214" y="166">2k</text><text x="292" y="166">10k</text></g>
      </svg>
    </div>
  );
}

const rowLabel = { fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-ui)', fontWeight: 700 } as const;

/** FREQ / GAIN / Q table under the graph; tap a column to pick that point. */
export function EqTable({ bands, selected, onSelect }: { bands: Band[]; selected?: number; onSelect?: (i: number) => void }) {
  const gain = (b: Band) => (isFilter(b) ? '24/oct' : fmtDb(b.g));
  const gainCol = (b: Band) => (isFilter(b) ? 'var(--text-soft)' : 'var(--text-1)');
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `44px repeat(${bands.length}, minmax(0, 1fr))`, gap: 6, alignItems: 'center', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
      <span />
      {bands.map((b, i) => (
        <button key={i} type="button" onClick={() => onSelect?.(i)} aria-pressed={selected === i} aria-label={`Point ${i + 1}, ${TYPE_LABEL[b.type]}`}
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, padding: '5px 0', borderRadius: 8, border: 0, cursor: onSelect ? 'pointer' : 'default', minWidth: 0, background: selected === i ? 'rgba(255,236,220,0.16)' : 'rgba(255,236,220,0.05)', boxShadow: selected === i ? 'inset 0 0 0 1px var(--text-1)' : undefined }}>
          <span style={{ width: 16, height: 16, borderRadius: '50%', background: BAND_COLOR[i % 8], color: '#140D09', fontFamily: 'var(--font-display)', fontSize: 9, fontWeight: 800, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{i + 1}</span>
          <span style={{ fontFamily: 'var(--font-ui)', fontSize: 10, color: 'var(--text-meta)', fontWeight: 700 }}>{b.type}</span>
        </button>
      ))}
      <span style={rowLabel}>FREQ</span>
      {bands.map((b, i) => <span key={i} style={{ textAlign: 'center', color: 'var(--text-1)' }}>{fmtFreq(b.f)}</span>)}
      <span style={rowLabel}>GAIN</span>
      {bands.map((b, i) => <span key={i} style={{ textAlign: 'center', color: gainCol(b) }}>{gain(b)}</span>)}
      <span style={rowLabel}>Q</span>
      {bands.map((b, i) => <span key={i} style={{ textAlign: 'center', color: 'var(--text-soft)' }}>{isFilter(b) ? '—' : b.q.toFixed(1)}</span>)}
    </div>
  );
}

const TYPES: BandType[] = ['BELL', 'LOW', 'SHELF', 'HPF', 'LPF'];
const field = { display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 } as const;
const input = { width: '100%', minHeight: 32, padding: '0 8px', borderRadius: 8, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(0,0,0,0.3)', color: 'var(--text-1)', fontFamily: 'var(--font-mono)', fontSize: 13 } as const;
const smallBtn = { minHeight: 32, padding: '0 12px', borderRadius: 8, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(255,236,220,0.06)', color: 'var(--text-1)', fontSize: 12, fontWeight: 700, cursor: 'pointer' } as const;

/** Edit the picked point exactly (type, frequency, gain, Q), remove it, or add a new one. */
export function EqPointEditor({ bands, selected, noHpf, onBand, onAdd, onRemove }: {
  bands: Band[]; selected: number; noHpf?: boolean; onBand: (i: number, patch: Partial<Band>) => void; onAdd: () => void; onRemove: (i: number) => void;
}) {
  const b = bands[selected];
  const full = bands.length >= 8;
  const types = TYPES.filter((t) => !(noHpf && t === 'HPF') || b?.type === t);
  const num = (v: string, lo: number, hi: number) => { const x = Number(v); return Number.isFinite(x) ? clamp(x, lo, hi) : null; };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: 12, borderRadius: 14, background: 'rgba(255,236,220,0.035)', border: '1px solid rgba(255,236,220,0.06)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>{b ? `Point ${selected + 1}` : 'No points'}</span>
        <span style={{ flex: 1 }} />
        <button type="button" onClick={onAdd} disabled={full} style={{ ...smallBtn, opacity: full ? 0.5 : 1, cursor: full ? 'default' : 'pointer' }}>+ Add point</button>
        {b && <button type="button" onClick={() => onRemove(selected)} style={smallBtn}>Remove point</button>}
      </div>
      {b && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(96px, 1fr))', gap: 8 }}>
          <label style={field}><span style={rowLabel}>TYPE</span>
            <select value={b.type} onChange={(e) => onBand(selected, { type: e.target.value as BandType })} style={input}>
              {types.map((t) => <option key={t} value={t}>{TYPE_LABEL[t]}</option>)}
            </select>
          </label>
          <label style={field}><span style={rowLabel}>FREQ (Hz)</span>
            <input key={`f${selected}-${b.f}`} type="number" inputMode="numeric" min={20} max={20000} defaultValue={Math.round(b.f)} style={input}
              onBlur={(e) => { const v = num(e.target.value, 20, 20000); if (v !== null && v !== b.f) onBand(selected, { f: Math.round(v) }); }}
              onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }} />
          </label>
          {!isFilter(b) && (
            <label style={field}><span style={rowLabel}>GAIN (dB)</span>
              <input key={`g${selected}-${b.g}`} type="number" inputMode="decimal" step={0.5} min={-12} max={12} defaultValue={b.g} style={input}
                onBlur={(e) => { const v = num(e.target.value, -12, 12); if (v !== null && v !== b.g) onBand(selected, { g: v }); }}
                onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }} />
            </label>
          )}
          {b.type === 'BELL' && (
            <label style={field}><span style={rowLabel}>Q</span>
              <input key={`q${selected}-${b.q}`} type="number" inputMode="decimal" step={0.1} min={0.3} max={8} defaultValue={b.q} style={input}
                onBlur={(e) => { const v = num(e.target.value, 0.3, 8); if (v !== null && v !== b.q) onBand(selected, { q: v }); }}
                onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }} />
            </label>
          )}
        </div>
      )}
      <span style={{ fontSize: 11, color: 'var(--text-3)', lineHeight: 1.4 }}>Drag a point on the graph, or double-click an empty spot to add one there. Up to 8 points per channel.</span>
    </div>
  );
}
