import type { CSSProperties } from 'react';
import type { PreflightCheck } from '@vibenation/shared';

const ICON = { ok: 'M5 12l5 5L20 7', warn: 'M12 7v6M12 17h.01', error: 'M7 7l10 10M17 7L7 17' } as const;

const iconStyle = (level: PreflightCheck['level']): CSSProperties => {
  const base: CSSProperties = { width: 30, height: 30, borderRadius: '50%', flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center' };
  if (level === 'warn') return { ...base, background: 'var(--warn)', color: '#1A1206', boxShadow: '0 0 16px rgba(255,178,36,0.45)' };
  if (level === 'error') return { ...base, background: 'var(--error-fill)', color: '#FFFFFF', boxShadow: '0 0 16px rgba(215,38,30,0.5)' };
  return { ...base, background: 'rgba(245,238,230,0.1)', color: '#F5EEE6' };
};

const META_COLOR = { ok: 'var(--text-soft)', warn: 'var(--warn)', error: 'var(--error)' } as const;

export function Preflight({ checks }: { checks: PreflightCheck[] }) {
  return (
    <div style={{ borderRadius: 22, background: 'linear-gradient(180deg, rgba(36,27,21,0.8), rgba(20,15,11,0.8))', border: '1px solid rgba(255,236,220,0.07)', boxShadow: 'inset 0 1px 0 rgba(255,236,220,0.05), 0 24px 60px rgba(0,0,0,0.4)', padding: '6px 22px' }}>
      <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {checks.map((c, i) => (
          <li key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '15px 0', borderBottom: i < checks.length - 1 ? '1px solid rgba(255,236,220,0.05)' : undefined }}>
            <span style={iconStyle(c.level)} aria-label={c.level === 'ok' ? 'OK' : c.level === 'warn' ? 'Warning' : 'Problem'} role="img">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" aria-hidden="true"><path d={ICON[c.level]} /></svg>
            </span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
              <span style={{ fontWeight: 700, fontSize: 15 }}>{c.title}</span>
              <span style={{ color: 'var(--text-meta)', fontSize: 13, lineHeight: 1.4 }}>{c.detail}</span>
            </div>
            <span style={{ flex: 1 }} />
            <span className="vn-mono" style={{ fontSize: 12, whiteSpace: 'nowrap', padding: '4px 9px', borderRadius: 8, color: META_COLOR[c.level], background: 'rgba(255,236,220,0.04)' }}>{c.meta}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
