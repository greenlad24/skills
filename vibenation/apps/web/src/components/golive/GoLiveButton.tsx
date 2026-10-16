import { useElapsed } from '../../store';

interface Props {
  onAir: boolean;
  liveSince: number | null;
  count: number;
  /** Title of the first pre-flight check with level 'error', or a reason the button can't be used. */
  blocker: { text: string; level: 'error' | 'warn' } | null;
  /** Seconds left in the go-live countdown, or null when not counting. */
  countdown: number | null;
  onGo: () => void;
  onCancel: () => void;
}

const big = { minHeight: 72, borderRadius: 18, border: 0, fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 800, letterSpacing: '-0.01em', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, width: '100%' } as const;
const blueFill = 'linear-gradient(180deg, #3A86FF 0%, #1F66E0 60%, #1A57C2 100%)';
const dot = { width: 14, height: 14, borderRadius: '50%', background: '#FFFFFF', boxShadow: '0 0 0 5px rgba(255,255,255,0.25)', flex: 'none' } as const;

export function GoLiveButton({ onAir, liveSince, count, blocker, countdown, onGo, onCancel }: Props) {
  const elapsed = useElapsed(onAir ? liveSince : null);

  if (onAir) {
    return (
      <div role="status" style={{ ...big, flexDirection: 'column', gap: 4, padding: '12px 16px', background: 'rgba(31,102,224,0.14)', border: '2px solid var(--on-air)', color: '#FFFFFF', animation: 'vnGlow 2.6s ease-in-out infinite' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ ...dot, background: 'var(--on-air)', boxShadow: undefined, animation: 'vnPulse 1.8s ease-out infinite' }} />You’re live
        </span>
        <span className="vn-mono" style={{ fontSize: 13, fontWeight: 600, color: '#CFE0FF' }}>{elapsed} · on {count} platform{count === 1 ? '' : 's'} · Claude is running the show</span>
      </div>
    );
  }

  if (countdown !== null) {
    return (
      <div style={{ display: 'flex', gap: 8 }} role="status" aria-live="assertive">
        <div style={{ ...big, flex: 1, background: blueFill, color: '#FFFFFF', animation: 'vnGlow 1s ease-in-out infinite' }}>
          <span style={dot} />Going live in <span className="vn-mono">{countdown}</span>
        </div>
        <button onClick={onCancel} style={{ minHeight: 72, padding: '0 18px', borderRadius: 18, border: '1px solid rgba(255,236,220,0.2)', background: 'rgba(255,236,220,0.06)', color: 'var(--text-1)', fontWeight: 800, fontSize: 15, cursor: 'pointer' }}>Cancel</button>
      </div>
    );
  }

  const disabled = !!blocker;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <button onClick={onGo} disabled={disabled} aria-describedby={disabled ? 'vn-golive-blocker' : undefined}
        style={{ ...big, cursor: disabled ? 'not-allowed' : 'pointer', ...(disabled ? { background: 'rgba(255,236,220,0.08)', color: 'var(--text-3)' } : { background: blueFill, color: '#FFFFFF', animation: 'vnGlow 2.6s ease-in-out infinite' }) }}>
        <span style={{ ...dot, ...(disabled ? { background: 'var(--text-3)', boxShadow: 'none' } : {}) }} />Go Live on {count}
      </button>
      {blocker && (
        <span id="vn-golive-blocker" style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: blocker.level === 'error' ? 'var(--error)' : 'var(--warn)', fontWeight: 600 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'currentColor', flex: 'none' }} />{blocker.level === 'error' ? `Blocked by: ${blocker.text}` : blocker.text}
        </span>
      )}
    </div>
  );
}
