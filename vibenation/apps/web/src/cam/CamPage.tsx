import { useEffect, useRef, useState, useSyncExternalStore, type CSSProperties, type FormEvent } from 'react';
import { Logo } from '../components/Header';
import { cameraError, goFullscreen, isIOS, isStandalone, openCamera } from './device';
import { CamSession, joinShow, savedCam } from './session';
import { CamScreen } from './CamScreen';

// Phone camera page (iPhone Safari, Android Chrome). Opened from the QR invite:
// https://<host>/cam?k=<invite>. No login — the invite is the key.

export function CamPage() {
  const k = new URLSearchParams(location.search).get('k') ?? '';
  const [name, setName] = useState(() => savedCam().name ?? 'Camera');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [session, setSession] = useState<CamSession | null>(null);

  useEffect(() => () => { void session?.stop(); }, [session]);

  async function start(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    // Fullscreen + landscape lock must happen inside the tap (Android; iPhone ignores it).
    void goFullscreen();
    let track: MediaStreamTrack | null = null;
    try {
      track = await openCamera();
    } catch (err) {
      setBusy(false);
      setError(cameraError(err));
      return;
    }
    try {
      const info = await joinShow(k, name.trim() || 'Camera');
      const s = new CamSession(k, info, track);
      setSession(s);
      await s.start();
    } catch (err) {
      track.stop();
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (session) return <Running session={session} onLeave={() => { void session.stop(); setSession(null); }} />;

  const input: CSSProperties = { minHeight: 48, padding: '0 14px', borderRadius: 12, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(255,236,220,0.04)', color: 'var(--text-1)', fontSize: 16, fontFamily: 'inherit' };
  return (
    <div className="vn-app" style={{ alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <form onSubmit={start} style={{ width: '100%', maxWidth: 420, display: 'flex', flexDirection: 'column', gap: 12, padding: 22, borderRadius: 24, background: 'linear-gradient(180deg, rgba(36,27,21,0.8), rgba(20,15,11,0.8))', border: '1px solid rgba(255,236,220,0.08)', boxShadow: '0 30px 80px rgba(0,0,0,0.5)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><Logo /><span className="vn-label" style={{ marginLeft: 'auto' }}>CAMERA</span></div>
        {!k ? (
          <span role="alert" style={{ color: 'var(--text-soft)', fontSize: 14, lineHeight: 1.5 }}>Open this page by scanning the camera QR code in VibeNation (Show screen › Add phone).</span>
        ) : (
          <>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span className="vn-label">CAMERA NAME</span>
              <input style={input} value={name} maxLength={40} onChange={(e) => setName(e.target.value)} placeholder="e.g. Lead vocal" autoComplete="off" />
            </label>
            <span style={{ color: 'var(--text-meta)', fontSize: 12, lineHeight: 1.45 }}>
              Turn the phone sideways and put it on a tripod. The back camera streams in 1080p; the phone microphone is never used.
              {isIOS() && !isStandalone() && ' For full screen: Share › Add to Home Screen, then open it from there.'}
            </span>
            {error && <span role="alert" style={{ color: 'var(--error)', fontSize: 13, lineHeight: 1.4 }}>{error}</span>}
            <button disabled={busy} style={{ minHeight: 48, borderRadius: 12, border: 0, background: 'var(--text-1)', color: '#140D09', fontWeight: 700, fontSize: 15, cursor: busy ? 'default' : 'pointer' }}>
              {busy ? 'Starting camera…' : 'Start camera'}
            </button>
          </>
        )}
      </form>
    </div>
  );
}

function Running({ session, onLeave }: { session: CamSession; onLeave: () => void }) {
  const snap = useSyncExternalStore(session.subscribe, () => session.snap);
  const portrait = usePortrait();
  const videoRef = useRef<HTMLVideoElement>(null);
  useEffect(() => { void session.setPortrait(portrait); }, [session, portrait]);
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    v.srcObject = new MediaStream([session.track]);
    void v.play().catch(() => undefined);
  }, [session, portrait]);

  if (portrait) {
    return (
      <div role="alert" style={{ position: 'fixed', inset: 0, background: '#000', color: 'var(--text-1)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 18, padding: 24, textAlign: 'center' }}>
        <svg width="72" height="72" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden>
          <rect x="7" y="2.5" width="10" height="19" rx="2" /><path d="M2.5 9a7 7 0 0 1 3-4.5M21.5 15a7 7 0 0 1-3 4.5" /><path d="M5.5 2.5v2h2M18.5 21.5v-2h-2" />
        </svg>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700 }}>Turn your phone sideways</span>
        <span style={{ color: 'var(--text-meta)', fontSize: 14, maxWidth: 280, lineHeight: 1.5 }}>VibeNation cameras only stream in landscape. {snap.num} is paused until you turn it back.</span>
      </div>
    );
  }
  return <CamScreen snap={snap} session={session} videoRef={videoRef} onLeave={onLeave} />;
}

function usePortrait() {
  return useSyncExternalStore(
    (f) => { const m = matchMedia('(orientation: portrait)'); m.addEventListener('change', f); return () => m.removeEventListener('change', f); },
    () => matchMedia('(orientation: portrait)').matches,
  );
}
