import { useEffect, useState, type ReactNode } from 'react';
import QRCode from 'qrcode';
import type { AppsInfo } from '@vibenation/shared';

// Apps: how band members get a phone onto the show as a camera.
// Android = native VibeNation Camera app (APK download by QR). iPhone / any phone = the /cam web page.

const card = { flex: '1 1 420px', minWidth: 0, borderRadius: 24, padding: 24, background: 'linear-gradient(180deg, rgba(40,30,23,0.85), rgba(20,15,11,0.85))', border: '1px solid rgba(255,236,220,0.08)', boxShadow: 'inset 0 1px 0 rgba(255,236,220,0.06), 0 30px 70px rgba(0,0,0,0.5)', display: 'flex', flexDirection: 'column', gap: 18 } as const;
const btn = { minHeight: 44, padding: '0 16px', borderRadius: 12, border: 0, background: 'var(--text-1)', color: '#140D09', fontWeight: 700, fontSize: 14, cursor: 'pointer', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' } as const;
const ghostBtn = { ...btn, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(255,236,220,0.04)', color: 'var(--text-1)' } as const;

function useQr(url: string) {
  const [qr, setQr] = useState('');
  useEffect(() => {
    let alive = true;
    if (!url) { setQr(''); return; }
    void QRCode.toDataURL(url, { margin: 1, width: 560, errorCorrectionLevel: 'M', color: { dark: '#0B0806', light: '#F5EEE6' } }).then((d) => alive && setQr(d));
    return () => { alive = false; };
  }, [url]);
  return qr;
}

function Qr({ url, alt, empty }: { url: string; alt: string; empty: string }) {
  const qr = useQr(url);
  return (
    <div style={{ flex: '0 0 200px', width: 200, aspectRatio: '1', borderRadius: 16, overflow: 'hidden', background: '#F5EEE6', display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: qr ? 0 : 16 }}>
      {qr ? <img src={qr} alt={alt} style={{ width: '100%', height: '100%', display: 'block' }} /> : <span style={{ color: '#5A4E45', fontSize: 13 }}>{empty}</span>}
    </div>
  );
}

function Steps({ children }: { children: ReactNode }) {
  return <ol style={{ margin: 0, paddingLeft: 18, color: 'var(--text-soft)', fontSize: 14, lineHeight: 1.6, display: 'flex', flexDirection: 'column', gap: 4 }}>{children}</ol>;
}

function CopyLink({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* no clipboard on http */ }
  };
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
      <code title={url} style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', padding: '9px 10px', borderRadius: 10, background: 'rgba(0,0,0,0.35)', border: '1px solid rgba(255,236,220,0.08)', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-soft)' }}>{url}</code>
      <button onClick={() => void copy()} style={{ ...ghostBtn, minHeight: 36, padding: '0 12px', fontSize: 12 }}>{copied ? 'Copied' : 'Copy'}</button>
    </div>
  );
}

const fmtDate = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

function AndroidCard() {
  const [info, setInfo] = useState<AppsInfo | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    fetch('/api/apps').then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Could not load the app (${r.status}).`)))).then(setInfo).catch((e: Error) => setError(e.message));
  }, []);
  const a = info?.android;
  return (
    <section aria-label="Android camera app" style={card}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span className="vn-label">ANDROID · NATIVE APP</span>
        <h2 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 24, fontWeight: 700 }}>VibeNation Camera</h2>
        <span className="vn-mono" style={{ fontSize: 12, color: 'var(--text-meta)' }}>
          {a ? `v${a.version ?? '?'} · ${a.sizeMB} MB · built ${fmtDate(a.builtAt)}` : info ? 'Not built yet' : '…'}
        </span>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, alignItems: 'flex-start' }}>
        <Qr url={a?.url ?? ''} alt="QR code to download the Android camera app" empty={error || (info && !a ? 'Ask Claude to build the Android app.' : 'Making QR…')} />
        <div style={{ flex: '1 1 220px', minWidth: 0 }}>
          <Steps>
            <li>Scan this code with the Android phone’s camera and tap <b>Download</b>.</li>
            <li>Open the downloaded file. If Android asks, allow <b>Install unknown apps</b> for Chrome, then tap <b>Install</b>.</li>
            <li>Open <b>VibeNation Camera</b>, tap <b>Scan</b> and scan the web camera code on this page (or Show › Add phone).</li>
          </Steps>
        </div>
      </div>
      <span style={{ color: 'var(--text-meta)', fontSize: 12, lineHeight: 1.45 }}>
        The app holds white balance and exposure locked for the whole stream and keeps the screen on. Updates: download and install again over the old version; the camera name is kept.
      </span>
      {error && <span role="alert" style={{ color: 'var(--error)', fontSize: 13 }}>{error}</span>}
      {a && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <a href={a.url} style={btn} download>Download APK ({a.sizeMB} MB)</a>
          <CopyLink url={a.url} />
          <span style={{ color: 'var(--text-meta)', fontSize: 12 }}>Send this link to a band member’s phone, or scan the code. It works for {Math.round(a.expiresInS / 86400)} days.</span>
        </div>
      )}
    </section>
  );
}

function WebCard() {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const [n, setN] = useState(0);
  useEffect(() => {
    let alive = true;
    setError('');
    fetch('/api/cams/invite')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Could not make a camera link (${r.status}).`))))
      .then((j: { url: string }) => alive && setUrl(j.url))
      .catch((e: Error) => alive && setError(e.message));
    return () => { alive = false; };
  }, [n]);
  return (
    <section aria-label="iPhone and web camera" style={card}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span className="vn-label">IPHONE · ANY PHONE · NO INSTALL</span>
        <h2 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 24, fontWeight: 700 }}>Web camera</h2>
        <span className="vn-mono" style={{ fontSize: 12, color: 'var(--text-meta)' }}>Safari on iPhone · Chrome on Android</span>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, alignItems: 'flex-start' }}>
        <Qr url={url} alt="QR code for the camera page" empty={error || 'Making QR…'} />
        <div style={{ flex: '1 1 220px', minWidth: 0 }}>
          <Steps>
            <li>Scan this code with the iPhone’s Camera app and open the link in <b>Safari</b>.</li>
            <li>For full screen: <b>Share › Add to Home Screen</b>, then open VibeNation from the home screen.</li>
            <li>Turn the phone sideways, name the camera (e.g. “Drums”), tap <b>Start camera</b> and allow the camera.</li>
          </Steps>
        </div>
      </div>
      <span style={{ color: 'var(--text-meta)', fontSize: 12, lineHeight: 1.45 }}>
        Streams the back camera in landscape 1080p over Wi-Fi. The phone microphone is never used. Keep phones charging.
      </span>
      {error && <span role="alert" style={{ color: 'var(--error)', fontSize: 13 }}>{error}</span>}
      {url && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <a href={url} target="_blank" rel="noopener" style={btn}>Open web camera</a>
          <CopyLink url={url} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ color: 'var(--text-meta)', fontSize: 12, flex: 1 }}>This camera link works for 24 hours.</span>
            <button onClick={() => setN((x) => x + 1)} style={{ ...ghostBtn, minHeight: 36, padding: '0 12px', fontSize: 12 }}>New code</button>
          </div>
        </div>
      )}
    </section>
  );
}

export function AppsScreen() {
  return (
    <main style={{ flex: '1 1 auto', display: 'flex', flexDirection: 'column', gap: 24, padding: 'clamp(20px, 3vw, 36px) clamp(16px, 3vw, 40px)', maxWidth: 1380, width: '100%', margin: '0 auto' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <span style={{ fontSize: 11, letterSpacing: '0.16em', color: '#FF9A5A', fontWeight: 700 }}>APPS · PHONE CAMERAS</span>
        <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 'clamp(34px, 4vw, 46px)', fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.05 }}>Turn any phone into a camera.</h1>
        <p style={{ margin: 0, color: 'var(--text-soft)', fontSize: 16, lineHeight: 1.55, maxWidth: 640 }}>
          Android phones use the VibeNation Camera app. iPhones (or any phone without the app) use the web camera — nothing to install. Every camera joins the show the moment it starts.
        </p>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24 }}>
        <AndroidCard />
        <WebCard />
      </div>
    </main>
  );
}
