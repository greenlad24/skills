import { useState, type CSSProperties } from 'react';
import type { ChannelState } from '@vibenation/shared';
import { go } from '../../route';
import { EXTRAS, KNOBS, MACROS, macroSub, type Band, type ChangeCard, type KnobKey, type MacroKey } from '../../demo/mix';
import { EqGraph, EqPointEditor, EqTable } from './EqPanel';
import { ChannelFx } from './ChannelFx';
import { useMeters } from '../../store';
import type { Section } from '@vibenation/shared';
import { Knob } from './Knob';
import { LcdGr } from './Meters';
import { faderText } from './Fader';

export interface ChMix {
  pan?: number; // demo only (no engine)
  a: Band[]; // before Claude
  bands: Band[]; // current
  easy: Record<MacroKey, number>;
  knobs: Record<KnobKey, number>;
  changes: (ChangeCard & { undone?: boolean })[];
}

const card: CSSProperties = { borderRadius: 22, background: 'linear-gradient(180deg, rgba(36,27,21,0.8), rgba(20,15,11,0.8))', border: '1px solid rgba(255,236,220,0.07)', boxShadow: 'inset 0 1px 0 rgba(255,236,220,0.05), 0 24px 60px rgba(0,0,0,0.4)' };
const seg: CSSProperties = { display: 'flex', gap: 2, padding: 3, borderRadius: 10, background: 'rgba(0,0,0,0.3)' };
const segBtn = (on: boolean, onBg = 'var(--text-1)', h = 28, pad = '0 10px'): CSSProperties => ({ minHeight: h, padding: pad, borderRadius: 7, border: 0, fontSize: 11, fontWeight: 700, cursor: 'pointer', background: on ? onBg : 'transparent', color: on ? '#140D09' : 'var(--text-meta)' });

/** Pan readout: L 30% / C / R 30%. */
export const panText = (v: number) => (v < 0 ? `L ${Math.round(-v)}%` : v > 0 ? `R ${Math.round(v)}%` : 'C');

export function SelectedPanel({ c, mix, bpm, ab, setAb, onBand, onAddBand, onRemoveBand, pan, onPan, onEasy, onKnob }: {
  c: ChannelState; mix: ChMix; bpm: number; ab: 'A' | 'B'; setAb: (v: 'A' | 'B') => void;
  onBand: (i: number, patch: Partial<Band>) => void; onAddBand: (f: number, g: number) => void; onRemoveBand: (i: number) => void;
  pan: number; onPan: (v: number) => void;
  onEasy: (k: MacroKey, v: number) => void; onKnob: (k: KnobKey, v: number) => void;
}) {
  const [post, setPost] = useState(true);
  const [pick, setPick] = useState(0);
  const [fx, setFx] = useState<'easy' | 'detail'>(c.eq ? 'detail' : 'easy');
  const name = c.role ?? c.name;
  const bands = ab === 'A' ? mix.a : mix.bands;
  const selBand = Math.min(pick, Math.max(0, bands.length - 1));
  const addBand = (f: number, g: number) => { onAddBand(f, g); setPick(bands.length); };
  const removeBand = (i: number) => { onRemoveBand(i); setPick(Math.max(0, i - 1)); };

  return (
    <section style={{ ...card, padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ borderRadius: 16, padding: '14px 16px', background: 'linear-gradient(160deg, #F3E7D6 0%, #E4D3BC 100%)', color: '#2A1B12', boxShadow: 'inset 0 2px 8px rgba(0,0,0,0.25), 0 0 0 4px rgba(0,0,0,0.35)', display: 'grid', gridTemplateColumns: 'auto 1fr auto', alignItems: 'end', gap: '4px 14px' }} role="img" aria-label={`Channel display: ${name}`}>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 48, lineHeight: 0.9, letterSpacing: '-0.04em', color: '#8A3A12' }}>{String(c.n).padStart(2, '0')}</span>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, paddingBottom: 4, minWidth: 0 }}>
          <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 18 }}>{name}</span>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', color: '#6B5444' }}>{c.held ? 'HELD BY YOU' : 'MIX LOCKED'} · {c.section.toUpperCase()}</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2, paddingBottom: 4, fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700 }}>
          <span>{c.mute ? 'mute' : `${faderText(c.fader)} dB`}</span><LcdGr i={c.n - 1} fallback={c.gr} />
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ flex: 1 }} />
        {c.held
          ? <span style={{ padding: '5px 11px', borderRadius: 999, background: 'var(--text-1)', color: '#140D09', fontSize: 12, fontWeight: 700 }}>Held by you · rest of show</span>
          : <span style={{ padding: '5px 11px', borderRadius: 999, background: 'rgba(185,166,255,0.12)', border: '1px solid rgba(185,166,255,0.35)', color: 'var(--ai-text)', fontSize: 12, fontWeight: 700 }}>Mix locked · no auto changes</span>}
      </div>
      {c.held && <span style={{ fontSize: 12, color: 'var(--text-meta)', lineHeight: 1.45 }}>You changed this channel, so Claude leaves it alone until the stream ends. It only steps in for an emergency: feedback, clipping or a dead signal.</span>}

      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
        <span className="vn-label">EQ</span>
        <span style={{ flex: 1 }} />
        <div style={seg} role="group" aria-label="Compare">
          <button onClick={() => setAb('A')} aria-pressed={ab === 'A'} style={segBtn(ab === 'A')}>A · before</button>
          <button onClick={() => setAb('B')} aria-pressed={ab === 'B'} style={segBtn(ab === 'B', 'var(--ai)')}>B · Claude</button>
        </div>
        <div style={seg} role="group" aria-label="Analyser">
          <button onClick={() => setPost(false)} aria-pressed={!post} style={{ ...segBtn(!post, 'rgba(255,236,220,0.12)', 28, '0 9px'), color: !post ? 'var(--text-1)' : 'var(--text-meta)', fontWeight: !post ? 700 : 600 }}>Pre</button>
          <button onClick={() => setPost(true)} aria-pressed={post} style={{ ...segBtn(post, 'rgba(255,236,220,0.12)', 28, '0 9px'), color: post ? 'var(--text-1)' : 'var(--text-meta)', fontWeight: post ? 700 : 600 }}>Post</button>
        </div>
      </div>
      <LiveEq n={c.n} section={c.section} bands={bands} editable={ab === 'B'} post={post} onBand={onBand} selected={selBand} onSelect={setPick} onAdd={addBand} />
      <EqTable bands={bands} selected={selBand} onSelect={setPick} />
      {ab === 'B' && <EqPointEditor bands={bands} selected={selBand} noHpf={c.noHpf} onBand={onBand} onAdd={() => addBand(1000, 0)} onRemove={removeBand} />}
      {ab === 'A' && <span style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.4, marginTop: -6 }}>Showing the EQ before Claude's changes. Switch to B to edit.</span>}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="vn-label">PAN</span>
          <span style={{ flex: 1 }} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, minWidth: 64, textAlign: 'right' }} aria-live="polite">{panText(pan)}</span>
          <button type="button" onClick={() => onPan(0)} disabled={pan === 0} style={{ minHeight: 28, padding: '0 10px', borderRadius: 8, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(255,236,220,0.06)', color: 'var(--text-1)', fontSize: 11, fontWeight: 700, cursor: pan === 0 ? 'default' : 'pointer', opacity: pan === 0 ? 0.5 : 1 }}>Center</button>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-meta)' }}>L</span>
          <input type="range" min={-100} max={100} step={1} value={pan} aria-label={`Pan, ${panText(pan)}`} aria-valuetext={panText(pan)}
            onChange={(e) => onPan(Number(e.target.value))} onDoubleClick={() => onPan(0)} style={{ width: '100%', accentColor: 'var(--text-1)' }} />
          <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-meta)' }}>R</span>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="vn-label">EFFECTS</span>
          <span style={{ flex: 1 }} />
          <div style={seg} role="tablist" aria-label="Effects view">
            <button role="tab" aria-selected={fx === 'easy'} onClick={() => setFx('easy')} style={segBtn(fx === 'easy', 'var(--text-1)', 28, '0 11px')}>Easy</button>
            <button role="tab" aria-selected={fx === 'detail'} onClick={() => setFx('detail')} style={segBtn(fx === 'detail', 'var(--text-1)', 28, '0 11px')}>Detailed</button>
          </div>
        </div>

        {fx === 'easy' ? (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10 }}>
              {MACROS.map((m) => {
                const v = mix.easy[m.key];
                return (
                  <div key={m.key} style={{ borderRadius: 16, padding: '12px 10px', background: 'rgba(255,236,220,0.035)', border: '1px solid rgba(255,236,220,0.06)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, minWidth: 0 }}>
                    <Knob big glow value={v} min={0} max={100} step={1} color={m.c} label={m.name} valueText={`${v}%`} onChange={(n) => onEasy(m.key, n)} />
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 15, fontWeight: 700 }}>{v}%</span>
                    <label style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, width: '100%' }}>
                      <span style={{ fontWeight: 700, fontSize: 13 }}>{m.name}</span>
                      <input type="range" min={0} max={100} value={v} onChange={(e) => onEasy(m.key, Number(e.target.value))} style={{ width: '100%', accentColor: m.c }} />
                    </label>
                    <span style={{ fontSize: 11, color: 'var(--text-meta)', textAlign: 'center', lineHeight: 1.3 }}>{macroSub(m.key, c.section, bpm)}</span>
                  </div>
                );
              })}
            </div>
            <span style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.4 }}>Each knob drives several settings at once. Turning one holds that effect for you for the rest of the show.</span>
          </>
        ) : c.eq ? (
          <>
            <ChannelFx c={c} />
            <a href="#/fx" onClick={(e) => { e.preventDefault(); go('fx'); }} style={{ fontSize: 13, fontWeight: 700 }}>Open the effects rack →</a>
          </>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gap: 8 }}>
              {KNOBS.map((k) => {
                const v = mix.knobs[k.key];
                return (
                  <div key={k.key} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                    <Knob value={v} min={k.min} max={k.max} step={k.step} color={k.c} label={k.label} valueText={k.fmt(v)} onChange={(n) => onKnob(k.key, n)} />
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-1)', whiteSpace: 'nowrap' }}>{k.fmt(v)}</span>
                    <span style={{ fontSize: 9, letterSpacing: '0.08em', color: 'var(--text-meta)', fontWeight: 700, whiteSpace: 'nowrap' }}>{k.label}</span>
                  </div>
                );
              })}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8 }}>
              {EXTRAS[c.section].map(([l, v]) => (
                <div key={l} style={{ borderRadius: 12, background: 'rgba(255,236,220,0.04)', padding: '9px 10px', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <span style={{ fontSize: 10, color: 'var(--text-meta)', fontWeight: 700, letterSpacing: '0.08em' }}>{l}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{v}</span>
                </div>
              ))}
            </div>
            <a href="#/fx" onClick={(e) => { e.preventDefault(); go('fx'); }} style={{ fontSize: 13, fontWeight: 700 }}>Open the effects rack →</a>
          </>
        )}
      </div>
    </section>
  );
}

/** Claude's recent changes on the selected channel (lilac cards). */
export function ChangeCards({ changes, ab, setAb, onUndo, onAmount }: {
  changes: ChMix['changes']; ab: 'A' | 'B'; setAb: (v: 'A' | 'B') => void; onUndo: (id: string) => void; onAmount: (id: string, v: number) => void;
}) {
  const btn: CSSProperties = { minHeight: 30, padding: '0 11px', borderRadius: 8, border: 0, background: 'rgba(255,236,220,0.08)', color: 'var(--text-1)', fontSize: 12, fontWeight: 600, cursor: 'pointer' };
  return (
    <section aria-label="Claude's changes" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {changes.map((ch) => (
        <div key={ch.id} style={{ borderRadius: 18, overflow: 'hidden', background: '#15101C', border: '1px solid rgba(185,166,255,0.3)', boxShadow: '0 16px 40px rgba(76,52,170,0.25)', opacity: ch.undone ? 0.55 : 1 }}>
          <div style={{ padding: '12px 14px', background: 'linear-gradient(135deg, #6D4DE6, #8E6BFF 60%, #A58BFF)', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" aria-hidden="true" style={{ flex: 'none', marginTop: 1 }}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6" /></svg>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 14, color: '#FFFFFF', textDecoration: ch.undone ? 'line-through' : undefined }}>{ch.what}</span>
              <span style={{ fontSize: 12, lineHeight: 1.45, color: '#ECE6FF' }}>{ch.undone ? 'Undone by you.' : ch.why}</span>
            </div>
          </div>
          <div style={{ padding: '10px 12px', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
            <span style={{ padding: '4px 8px', borderRadius: 7, background: 'rgba(255,236,220,0.06)', fontFamily: 'var(--font-mono)', fontSize: 11, color: '#B8AFCF' }}>{ch.time}</span>
            <button onClick={() => setAb(ab === 'A' ? 'B' : 'A')} aria-pressed={ab === 'A'} style={btn}>Before / after</button>
            <button onClick={() => onUndo(ch.id)} disabled={ch.undone} style={{ ...btn, cursor: ch.undone ? 'default' : 'pointer' }}>{ch.undone ? 'Undone' : 'Undo'}</button>
            <label style={{ flex: '1 1 140px', display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: '#B8AFCF' }}>Amount
              <input type="range" min={-100} max={150} value={ch.undone ? 0 : ch.amount} disabled={ch.undone} onChange={(e) => onAmount(ch.id, Number(e.target.value))} style={{ flex: 1, minWidth: 0, accentColor: 'var(--ai)' }} />
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-1)' }}>{ch.undone ? 0 : ch.amount}%</span>
            </label>
          </div>
        </div>
      ))}
    </section>
  );
}

/** EQ graph fed with the channel's real spectrum when the audio engine is running. */
function LiveEq(p: { n: number; section: Section; bands: Band[]; editable: boolean; post: boolean; onBand: (i: number, patch: Partial<Band>) => void; selected: number; onSelect: (i: number) => void; onAdd: (f: number, g: number) => void }) {
  const m = useMeters();
  return <EqGraph section={p.section} bands={p.bands} editable={p.editable} post={p.post} onBand={p.onBand} live={m?.spec?.[p.n - 1]} selected={p.selected} onSelect={p.onSelect} onAdd={p.onAdd} />;
}
