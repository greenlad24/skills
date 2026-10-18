import { useEffect, useRef } from 'react';
import { CHANNELS, type ClientAction } from '@vibenation/shared';
import { fmtDb } from '../../store';
import { sendSoon } from './sendSoon';

// Console-style taper: −60 dB (−∞) at the bottom, 0 dB at 75 %, +10 dB at the top.
const TAPER: [number, number][] = [[-60, 0], [-30, 0.25], [-10, 0.5], [0, 0.75], [10, 1]];
export const MIN_DB = -60;
export const MAX_DB = 10;

export function dbToPos(db: number) {
  if (db <= MIN_DB) return 0;
  for (let k = 1; k < TAPER.length; k++) {
    const [d1, p1] = TAPER[k];
    if (db <= d1) { const [d0, p0] = TAPER[k - 1]; return p0 + ((db - d0) / (d1 - d0)) * (p1 - p0); }
  }
  return 1;
}

export function posToDb(p: number) {
  if (p <= 0) return MIN_DB;
  for (let k = 1; k < TAPER.length; k++) {
    const [d1, p1] = TAPER[k];
    if (p <= p1) { const [d0, p0] = TAPER[k - 1]; return d0 + ((p - p0) / (p1 - p0)) * (d1 - d0); }
  }
  return MAX_DB;
}

export const faderText = (db: number) => (db <= MIN_DB + 0.05 ? '−∞' : fmtDb(db));

const TRACK_H = 180;
const round = (db: number) => Math.round(db * 10) / 10;

/** Draggable fader cap (`db` is what to show; `onLocal` sets/clears the parent's local override). Drag is relative (no jump); FINE makes it 4× finer.
 *  Double-click resets to the channel's starting level. Arrow keys nudge. */
export function Fader({ ch, name, db, fine, onLocal, toAction, resetDb }: {
  ch: number; name: string; db: number; fine: boolean; onLocal: (db: number | null) => void;
  /** For non-channel faders (master): the action to send, and the double-click level. */
  toAction?: (db: number) => ClientAction; resetDb?: number;
}) {
  const drag = useRef<{ y: number; p: number } | null>(null);
  const release = useRef<number>();
  const shown = db; // parent shows its local value while dragging

  useEffect(() => () => clearTimeout(release.current), []);
  // Hold the local value briefly after release so the cap doesn't snap back before the server echoes.
  const setL = onLocal;
  const commit = (v: number) => {
    const d = round(Math.min(MAX_DB, Math.max(MIN_DB, v)));
    setL(d);
    sendSoon(toAction ? `${name}.fader` : `ch${ch}.fader`, toAction ? toAction(d) : { type: 'fader', ch, db: d });
    clearTimeout(release.current);
    if (!drag.current) release.current = window.setTimeout(() => setL(null), 600);
  };

  return (
    <span
      role="slider" tabIndex={0} aria-label={`${name} fader`} aria-valuemin={MIN_DB} aria-valuemax={MAX_DB} aria-valuenow={shown} aria-valuetext={`${faderText(shown)} dB`}
      style={{ width: 24, height: '100%', position: 'relative', cursor: 'ns-resize', touchAction: 'none', outlineOffset: 2 }}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        clearTimeout(release.current);
        drag.current = { y: e.clientY, p: dbToPos(shown) };
      }}
      onPointerMove={(e) => {
        const d = drag.current;
        if (!d) return;
        const p = d.p - ((e.clientY - d.y) / TRACK_H) * (fine ? 0.25 : 1);
        commit(posToDb(Math.min(1, Math.max(0, p))));
      }}
      onPointerUp={() => { drag.current = null; release.current = window.setTimeout(() => setL(null), 600); }}
      onPointerCancel={() => { drag.current = null; setL(null); }}
      onDoubleClick={() => commit(resetDb ?? CHANNELS.find((c) => c.n === ch)?.fader ?? 0)}
      onKeyDown={(e) => {
        const step = fine ? 0.1 : 0.5;
        if (e.key === 'ArrowUp') commit(shown + step);
        else if (e.key === 'ArrowDown') commit(shown - step);
        else return;
        e.preventDefault();
      }}
    >
      <span style={{ position: 'absolute', left: 10, width: 4, top: 4, bottom: 4, background: 'rgba(0,0,0,0.6)', borderRadius: 2, boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.6)' }} />
      <span style={{ position: 'absolute', left: 0, right: 0, height: 28, bottom: `calc(${(dbToPos(shown) * 100).toFixed(2)}% - 14px)`, borderRadius: 5, background: 'linear-gradient(180deg, #FAF5EF 0%, #D9CFC5 48%, #B8ADA2 52%, #E6DDD3 100%)', boxShadow: '0 3px 8px rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none' }}>
        <span style={{ width: 14, height: 2, background: '#3A2E26', borderRadius: 1 }} />
      </span>
    </span>
  );
}
