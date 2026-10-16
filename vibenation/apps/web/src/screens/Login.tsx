import { useState, type FormEvent } from 'react';
import { Logo } from '../components/Header';

export function Login({ onDone }: { onDone: () => void }) {
  const [user, setUser] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    const r = await fetch('/api/login', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ user, password }) });
    setBusy(false);
    if (r.ok) onDone();
    else setError((await r.json().catch(() => ({}))).error ?? 'Could not log in.');
  }

  const input = { minHeight: 48, padding: '0 14px', borderRadius: 12, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(255,236,220,0.04)', color: 'var(--text-1)', fontSize: 16, fontFamily: 'inherit' } as const;
  return (
    <div className="vn-app" style={{ alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <form onSubmit={submit} style={{ width: '100%', maxWidth: 380, display: 'flex', flexDirection: 'column', gap: 14, padding: 28, borderRadius: 24, background: 'linear-gradient(180deg, rgba(36,27,21,0.8), rgba(20,15,11,0.8))', border: '1px solid rgba(255,236,220,0.08)', boxShadow: '0 30px 80px rgba(0,0,0,0.5)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}><Logo /></div>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="vn-label">NAME</span>
          <input style={input} value={user} onChange={(e) => setUser(e.target.value)} autoComplete="username" autoFocus />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="vn-label">PASSWORD</span>
          <input style={input} type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </label>
        {error && <span role="alert" style={{ color: 'var(--error)', fontSize: 13 }}>{error}</span>}
        <button disabled={busy} style={{ minHeight: 48, borderRadius: 12, border: 0, background: 'var(--text-1)', color: '#140D09', fontWeight: 700, fontSize: 15, cursor: 'pointer', marginTop: 6 }}>
          {busy ? 'Checking…' : 'Log in'}
        </button>
      </form>
    </div>
  );
}
