import { useRef, type KeyboardEvent, type PointerEvent } from 'react';
import { YouBadge } from './YouBadge';

interface Props {
  label: string;
  text: string; // formatted value
  value: number;
  min: number;
  max: number;
  step: number;
  color: string;
  /** Arc shown as empty (unit switched off). */
  dim: boolean;
  held: boolean;
  onChange: (v: number) => void;
}

/** Pixels of vertical drag for a full sweep. */
const DRAG_PX = 180;

const clampStep = (v: number, min: number, max: number, step: number) => {
  const s = Math.round((v - min) / step) * step + min;
  return Math.min(max, Math.max(min, Number(s.toFixed(6))));
};

/** Arc knob from the Effects rack design: drag vertically or use the arrow keys. */
export function Knob({ label, text, value, min, max, step, color, dim, held, onChange }: Props) {
  const drag = useRef<{ y: number; v: number } | null>(null);
  const p = dim ? 0 : (value - min) / (max - min || 1);
  const deg = Math.round(p * 270);
  const arc = `conic-gradient(from 225deg, ${color} 0deg ${deg}deg, rgba(255,236,220,0.08) ${deg}deg 270deg, transparent 270deg 360deg)`;

  const set = (v: number) => {
    const n = clampStep(v, min, max, step);
    if (n !== value) onChange(n);
  };

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    e.currentTarget.focus();
    drag.current = { y: e.clientY, v: value };
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    const fine = e.shiftKey ? 0.25 : 1;
    set(drag.current.v + ((drag.current.y - e.clientY) / DRAG_PX) * (max - min) * fine);
  };
  const end = () => { drag.current = null; };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const big = Math.max(step, (max - min) / 10);
    const d: Record<string, number> = { ArrowUp: step, ArrowRight: step, ArrowDown: -step, ArrowLeft: -step, PageUp: big, PageDown: -big };
    if (e.key in d) set(value + d[e.key]);
    else if (e.key === 'Home') set(min);
    else if (e.key === 'End') set(max);
    else return;
    e.preventDefault();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, minWidth: 0 }}>
      <div
        role="slider" tabIndex={0}
        aria-label={`${label}${held ? ' (held by you)' : ''}`}
        aria-valuemin={min} aria-valuemax={max} aria-valuenow={value} aria-valuetext={text}
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={end} onPointerCancel={end}
        onKeyDown={onKeyDown}
        style={{
          width: 58, height: 58, borderRadius: '50%', background: arc, display: 'flex', alignItems: 'center', justifyContent: 'center',
          cursor: 'ns-resize', touchAction: 'none', userSelect: 'none', outlineOffset: 3,
          boxShadow: held ? '0 0 0 2px #F5EEE6, 0 0 14px rgba(245,238,230,0.45)' : undefined,
        }}>
        <div style={{ width: 45, height: 45, borderRadius: '50%', background: 'radial-gradient(circle at 40% 30%, #32271F, #0F0A08)', boxShadow: '0 5px 12px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,236,220,0.1)', position: 'relative', transform: `rotate(${-135 + deg}deg)` }}>
          <span style={{ position: 'absolute', left: 21, top: 5, width: 3, height: 12, borderRadius: 2, background: '#F5EEE6' }} />
        </div>
      </div>
      <span className="vn-mono" style={{ fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap' }}>{text}</span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10, letterSpacing: '0.08em', color: 'var(--text-meta)', fontWeight: 700, whiteSpace: 'nowrap' }}>
        {label}{held && <YouBadge />}
      </span>
    </div>
  );
}
