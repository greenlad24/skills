import { useEffect, useRef, useState } from 'react';
import QRCode from 'qrcode';

/** "+ Add phone" tile for the end of the camera grid. Opens the QR invite. */
export function AddPhoneTile() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)} aria-haspopup="dialog"
        style={{ padding: 8, borderRadius: 18, cursor: 'pointer', color: 'var(--text-soft)', background: 'rgba(255,236,220,0.02)', border: '1px dashed rgba(255,236,220,0.18)', display: 'flex', flexDirection: 'column' }}>
        <div style={{ aspectRatio: '16 / 9', width: '100%', borderRadius: 12, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden><rect x="3" y="6" width="18" height="12" rx="2.5" /><path d="M12 9.5v5M9.5 12h5" /></svg>
          <span style={{ fontWeight: 700, fontSize: 13 }}>+ Add phone</span>
        </div>
        <span style={{ padding: '10px 4px 2px', fontSize: 12, color: 'var(--text-meta)', textAlign: 'left' }}>Scan a QR code to add a camera</span>
      </button>
      {open && <InviteModal onClose={() => setOpen(false)} />}
    </>
  );
}

function InviteModal({ onClose }: { onClose: () => void }) {
  const [url, setUrl] = useState('');
  const [qr, setQr] = useState('');
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    let alive = true;
    fetch('/api/cams/invite')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Could not make an invite (${r.status}).`))))
      .then(async (j: { url: string }) => {
        const data = await QRCode.toDataURL(j.url, { margin: 1, width: 560, errorCorrectionLevel: 'M', color: { dark: '#0B0806', light: '#F5EEE6' } });
        if (alive) { setUrl(j.url); setQr(data); }
      })
      .catch((e: Error) => alive && setError(e.message));
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeRef.current(); };
    addEventListener('keydown', onKey);
    return () => { alive = false; removeEventListener('keydown', onKey); };
  }, []);

  const copy = async () => {
    try { await navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* no clipboard on http */ }
  };

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 50, background: 'rgba(5,3,2,0.7)', backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div role="dialog" aria-modal="true" aria-label="Add a phone camera" onClick={(e) => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 640, borderRadius: 24, padding: 24, background: 'linear-gradient(180deg, rgba(40,30,23,0.97), rgba(22,16,12,0.97))', border: '1px solid rgba(255,236,220,0.1)', boxShadow: '0 40px 100px rgba(0,0,0,0.6)', display: 'flex', flexWrap: 'wrap', gap: 24 }}>
        <div style={{ flex: '0 0 240px', aspectRatio: '1', borderRadius: 16, overflow: 'hidden', background: '#F5EEE6', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto' }}>
          {qr ? <img src={qr} alt="QR code for the camera link" style={{ width: '100%', height: '100%', display: 'block' }} /> : <span style={{ color: '#5A4E45', fontSize: 13 }}>{error ? '—' : 'Making QR…'}</span>}
        </div>
        <div style={{ flex: '1 1 260px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <span style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700 }}>Add a phone camera</span>
            <span style={{ flex: 1 }} />
            <button onClick={onClose} aria-label="Close" style={{ width: 36, height: 36, borderRadius: 10, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(255,236,220,0.04)', color: 'var(--text-soft)', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}>×</button>
          </div>
          <ol style={{ margin: 0, paddingLeft: 18, color: 'var(--text-soft)', fontSize: 14, lineHeight: 1.6 }}>
            <li>Scan the code with the phone’s camera.</li>
            <li><b>iPhone:</b> open in Safari, turn sideways.</li>
            <li><b>Android:</b> install the VibeNation Camera app or use Chrome.</li>
            <li>Name the camera (e.g. “Drums”) and tap Start camera.</li>
          </ol>
          <span style={{ color: 'var(--text-meta)', fontSize: 12, lineHeight: 1.45 }}>Phones stream landscape 1080p over Wi-Fi. Keep them charging; the phone microphone is never used. The link works for 24 hours.</span>
          {error && <span role="alert" style={{ color: 'var(--error)', fontSize: 13 }}>{error}</span>}
          {url && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <code style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', padding: '9px 10px', borderRadius: 10, background: 'rgba(0,0,0,0.35)', border: '1px solid rgba(255,236,220,0.08)', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-soft)' }} title={url}>{url}</code>
              <button onClick={() => void copy()} style={{ minHeight: 36, padding: '0 12px', borderRadius: 10, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(255,236,220,0.06)', color: 'var(--text-1)', fontWeight: 700, fontSize: 12, cursor: 'pointer' }}>{copied ? 'Copied' : 'Copy'}</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
