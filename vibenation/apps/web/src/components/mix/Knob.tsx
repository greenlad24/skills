import { useRef } from 'react';

const arc = (c: string, deg: number) => `conic-gradient(from 225deg, ${c} 0deg ${deg}deg, rgba(255,236,220,0.08) ${deg}deg 270deg, transparent 270deg 360deg)`;

/** Arc knob (270° sweep). Drag up/down or use arrow keys. `big` = Easy macro size. */
export function Knob({ value, min, max, step, color, label, valueText, big, glow, onChange }: {
  value: number; min: number; max: number; step: number; color: string; label: string; valueText: string; big?: boolean; glow?: boolean; onChange: (v: number) => void;
}) {
  const drag = useRef<{ y: number; v: number } | null>(null);
  const deg = Math.round(((value - min) / (max - min)) * 270);
  const outer = big ? 74 : 52;
  const inner = big ? 58 : 40;
  const set = (v: number) => {
    const q = Math.round(Math.min(max, Math.max(min, v)) / step) * step;
    const r = Math.round(q * 100) / 100;
    if (r !== value) onChange(r);
  };
  return (
    <div
      role="slider" tabIndex={0} aria-label={label} aria-valuemin={min} aria-valuemax={max} aria-valuenow={value} aria-valuetext={valueText}
      style={{ width: outer, height: outer, borderRadius: '50%', background: arc(color, deg), display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: glow ? `0 0 18px ${color}33` : undefined, cursor: 'ns-resize', touchAction: 'none', flex: 'none' }}
      onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); drag.current = { y: e.clientY, v: value }; }}
      onPointerMove={(e) => { const d = drag.current; if (d) set(d.v + ((d.y - e.clientY) / 150) * (max - min)); }}
      onPointerUp={() => { drag.current = null; }}
      onPointerCancel={() => { drag.current = null; }}
      onKeyDown={(e) => {
        if (e.key === 'ArrowUp' || e.key === 'ArrowRight') set(value + step);
        else if (e.key === 'ArrowDown' || e.key === 'ArrowLeft') set(value - step);
        else return;
        e.preventDefault();
      }}
    >
      <div style={{ width: inner, height: inner, borderRadius: '50%', background: big ? 'radial-gradient(circle at 40% 30%, #32271F, #0F0A08)' : 'radial-gradient(circle at 40% 30%, #2E241D, #0F0A08)', boxShadow: big ? '0 6px 14px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,236,220,0.1)' : '0 4px 10px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,236,220,0.08)', position: 'relative', transform: `rotate(${-135 + deg}deg)` }}>
        <span style={big
          ? { position: 'absolute', left: 27, top: 6, width: 3, height: 14, borderRadius: 2, background: 'var(--text-1)' }
          : { position: 'absolute', left: 19, top: 5, width: 2, height: 11, borderRadius: 1, background: 'var(--text-1)' }} />
      </div>
    </div>
  );
}
