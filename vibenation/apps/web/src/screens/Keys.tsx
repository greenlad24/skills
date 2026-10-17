import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import type { KeyStatus } from '@vibenation/shared';

// Keys: paste an API key once. The server tests it, stores it in its private .env and uses it
// straight away. Keys are never shown again — only "set · ends in …abcd".

const card = { borderRadius: 20, padding: 20, background: 'linear-gradient(180deg, rgba(40,30,23,0.85), rgba(20,15,11,0.85))', border: '1px solid rgba(255,236,220,0.08)', display: 'flex', flexDirection: 'column', gap: 12 } as const;
const input = { flex: '1 1 240px', minWidth: 0, minHeight: 44, padding: '0 14px', borderRadius: 12, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(0,0,0,0.3)', color: 'var(--text-1)', fontSize: 14, fontFamily: 'var(--font-mono)' } as const;
const btn = { minHeight: 44, padding: '0 18px', borderRadius: 12, border: 0, background: 'var(--text-1)', color: '#140D09', fontWeight: 700, fontSize: 14, cursor: 'pointer' } as const;

const REDIRECT = () => `${location.origin}/api/oauth/youtube/callback`;

function Field({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(120px, 190px) 1fr', gap: 10, padding: '8px 0', borderTop: '1px solid rgba(255,236,220,0.07)' }}>
      <b style={{ fontSize: 13 }}>{name}</b>
      <span style={{ fontSize: 13, color: 'var(--text-soft)', lineHeight: 1.5 }}>{children}</span>
    </div>
  );
}

function CopyValue({ value }: { value: string }) {
  const [done, setDone] = useState(false);
  return (
    <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
      <code style={{ fontFamily: 'var(--font-mono)', fontSize: 12, padding: '3px 6px', borderRadius: 6, background: 'rgba(0,0,0,0.35)', color: 'var(--text-1)', wordBreak: 'break-all' }}>{value}</code>
      <button type="button" onClick={() => { void navigator.clipboard?.writeText(value).then(() => { setDone(true); setTimeout(() => setDone(false), 1500); }).catch(() => undefined); }}
        style={{ minHeight: 28, padding: '0 10px', borderRadius: 8, border: '1px solid rgba(255,236,220,0.14)', background: 'rgba(255,236,220,0.06)', color: 'var(--text-1)', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>{done ? 'Copied' : 'Copy'}</button>
    </span>
  );
}

/** Exactly what to put in each field of Google's "Create OAuth client ID" form. */
function GoogleClientHelp() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: 14, borderRadius: 14, background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(255,236,220,0.1)' }}>
      <b style={{ fontSize: 14 }}>Google Cloud → “Create OAuth client ID”: what to put in each field</b>
      <span style={{ fontSize: 12, color: 'var(--text-meta)' }}>Open it at console.cloud.google.com → APIs &amp; Services → Credentials → <b>+ Create credentials</b> → <b>OAuth client ID</b> (or Google Auth Platform → Clients → Create client).</span>
      <Field name="Application type">Choose <b>Web application</b>.</Field>
      <Field name="Name"><CopyValue value="VibeNation web" /> (any name works; only you see it).</Field>
      <Field name="Authorized JavaScript origins">Leave <b>empty</b>.</Field>
      <Field name="Authorized redirect URIs">Click <b>+ Add URI</b> and paste exactly this (no space, no slash at the end):<br /><CopyValue value={REDIRECT()} /></Field>
      <Field name="Create">Press <b>Create</b>. A box shows two values:</Field>
      <Field name="Client ID">Ends with <code>.apps.googleusercontent.com</code>. Paste it in <b>YouTube — Client ID</b> below and press <b>Save</b> first.</Field>
      <Field name="Client secret">Starts with <code>GOCSPX-</code>. Paste it in <b>YouTube — Client secret</b> and press <b>Save</b>. VibeNation tests the pair with Google.</Field>
      <Field name="Then">Go to <b>Go Live</b> → <b>Connect YouTube</b> and sign in with the account that owns the channel. Google warns “hasn’t verified this app”: it’s your own app, so click <b>Continue</b>.</Field>
      <span style={{ fontSize: 12, color: 'var(--text-meta)', lineHeight: 1.5, paddingTop: 6, borderTop: '1px solid rgba(255,236,220,0.07)' }}>
        <b>If Google asks for the consent screen first:</b> App name <b>VibeNation</b> · User support email: yours · Audience: <b>External</b> · Contact email: yours · then <b>Audience → Test users → Add users</b>: the Google account that owns the YouTube channel. Also enable <b>YouTube Data API v3</b> (APIs &amp; Services → Library). Leave the app in <b>Testing</b>; don’t press Publish.
      </span>
    </div>
  );
}

const HELP: Partial<Record<KeyStatus['name'], () => ReactNode>> = {
  YOUTUBE_CLIENT_ID: GoogleClientHelp,
  YOUTUBE_CLIENT_SECRET: GoogleClientHelp,
};

function KeyCard({ k, onSaved }: { k: KeyStatus; onSaved: (s: KeyStatus) => void }) {
  const [value, setValue] = useState('');
  const [help, setHelp] = useState(false);
  const Help = HELP[k.name];
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(''); setSaved(false);
    try {
      const r = await fetch('/api/keys', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ name: k.name, value }) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? `Couldn’t save (${r.status}).`);
      setValue(''); setSaved(true); onSaved(j as KeyStatus);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label={`${k.label} key`} style={card}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10 }}>
        <h2 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700 }}>{k.label}</h2>
        {Help && <button type="button" onClick={() => setHelp((h) => !h)} aria-expanded={help} aria-label="How to fill in Google's Create OAuth client ID form" title="How to fill in Google's form"
          style={{ width: 26, height: 26, borderRadius: '50%', border: '1px solid var(--warn)', background: help ? 'var(--warn)' : 'rgba(255,178,36,0.12)', color: help ? '#140D09' : 'var(--warn)', fontWeight: 800, fontSize: 14, lineHeight: 1, cursor: 'pointer' }}>!</button>}
        {k.set
          ? <span className="vn-mono" style={{ fontSize: 12, padding: '3px 10px', borderRadius: 999, background: 'rgba(255,236,220,0.06)', border: '1px solid rgba(255,236,220,0.14)', color: 'var(--text-soft)' }}>Set · ends in {k.hint}</span>
          : <span className="vn-mono" style={{ fontSize: 12, padding: '3px 10px', borderRadius: 999, background: 'rgba(255,178,36,0.1)', border: '1px solid rgba(255,178,36,0.4)', color: 'var(--warn)' }}>Not set</span>}
      </div>
      <span style={{ color: 'var(--text-soft)', fontSize: 14 }}>{k.use}</span>
      {Help && help && <Help />}
      <form onSubmit={save} style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        <input type="password" autoComplete="off" spellCheck={false} value={value} onChange={(e) => setValue(e.target.value)}
          placeholder={k.set ? 'Paste a new key to replace it' : 'Paste the key'} aria-label={`${k.label} key`} style={input} />
        <button disabled={busy || !value.trim()} style={{ ...btn, opacity: busy || !value.trim() ? 0.5 : 1 }}>{busy ? 'Testing…' : k.set ? 'Replace' : 'Save'}</button>
      </form>
      {error && <span role="alert" style={{ color: 'var(--error)', fontSize: 13 }}>{error}</span>}
      {saved && <span role="status" style={{ color: 'var(--text-soft)', fontSize: 13 }}>Tested and saved. In use now.</span>}
      <a href={k.get} target="_blank" rel="noopener" style={{ fontSize: 13, alignSelf: 'flex-start' }}>Get your {k.label} key ↗</a>
    </section>
  );
}

export function KeysScreen() {
  const [keys, setKeys] = useState<KeyStatus[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    fetch('/api/keys').then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Couldn’t load keys (${r.status}).`)))).then(setKeys).catch((e: Error) => setError(e.message));
  }, []);
  return (
    <main style={{ flex: '1 1 auto', display: 'flex', flexDirection: 'column', gap: 24, padding: 'clamp(20px, 3vw, 36px) clamp(16px, 3vw, 40px)', maxWidth: 880, width: '100%', margin: '0 auto' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <span style={{ fontSize: 11, letterSpacing: '0.16em', color: '#FF9A5A', fontWeight: 700 }}>KEYS</span>
        <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 'clamp(30px, 4vw, 40px)', fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.05 }}>Connect services.</h1>
        <p style={{ margin: 0, color: 'var(--text-soft)', fontSize: 15, lineHeight: 1.55 }}>
          Paste a key once. VibeNation tests it, stores it privately on the server and starts using it straight away. Keys are never shown again, here or anywhere else.
        </p>
      </div>
      {error && <span role="alert" style={{ color: 'var(--error)' }}>{error}</span>}
      {keys?.map((k) => <KeyCard key={k.name} k={k} onSaved={(s) => setKeys((ks) => ks && ks.map((x) => (x.name === s.name ? s : x)))} />)}
    </main>
  );
}
