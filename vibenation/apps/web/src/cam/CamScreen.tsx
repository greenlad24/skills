import { useEffect, useRef, useState, useSyncExternalStore, type CSSProperties, type RefObject } from 'react';
import { canFullscreen, goFullscreen, isIOS, isStandalone, unlockPicture } from './device';
import type { CamSession, CamSnapshot } from './session';

// Landscape camera screen (design: Phone.dc.html / PhoneOpen.dc.html).
// The full 16:9 picture edge to edge with NOTHING over it; the tally line sits in the
// left strip, a small drawer handle with a status dot in the right strip.

const ON_AIR = '#3D8BFF';
const ON_AIR_FILL = '#1F66E0';
const WARN = '#FFB224';
const ERROR = '#FF5A52';
const TEXT = '#F5EEE6';
const META = '#9C9084';

export function CamScreen({ snap, session, videoRef, onLeave }: { snap: CamSnapshot; session: CamSession; videoRef: RefObject<HTMLVideoElement>; onLeave: () => void }) {
  const [open, setOpen] = useState(false);
  const [guides, setGuides] = useState(false);
  const { w: vw, h: vh } = useViewport();

  // Picture as large as possible at 16:9, leaving at least a 48 px strip each side.
  const imgW = Math.min(vw - 96, (vh * 16) / 9);
  const imgH = (imgW * 9) / 16;
  const strip = (vw - imgW) / 2;

  const down = snap.media === 'down' || !snap.control;
  const warn = snap.media === 'reconnecting' || battLow(snap) || (snap.fps !== undefined && snap.fps < 50) || snap.link?.label.endsWith('weak');
  const dot = down ? ERROR : warn ? WARN : snap.live ? ON_AIR : '#8F8378';
  const tally = snap.live ? ON_AIR : '#2A211B';

  return (
    <div style={{ position: 'fixed', inset: 0, background: '#000', color: TEXT, fontFamily: "'DM Sans', system-ui, sans-serif", overflow: 'hidden', touchAction: 'manipulation', userSelect: 'none', WebkitUserSelect: 'none' }}>
      {/* left strip: tally */}
      <div aria-hidden style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: strip, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ width: 4, height: '70%', borderRadius: 2, background: tally, boxShadow: snap.live ? `0 0 18px ${tally}` : 'none', transition: 'background 120ms, box-shadow 120ms' }} />
      </div>

      {/* the picture, exactly what goes on air */}
      <div style={{ position: 'absolute', left: strip, top: (vh - imgH) / 2, width: imgW, height: imgH, overflow: 'hidden', background: '#070403' }} role="img" aria-label="Full camera image, exactly what goes on air">
        <video ref={videoRef} playsInline muted autoPlay disablePictureInPicture style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block', background: '#070403' }} />
        {guides && (
          <svg aria-hidden viewBox="0 0 3 3" preserveAspectRatio="none" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
            <path d="M1 0V3M2 0V3M0 1H3M0 2H3" stroke="rgba(255,255,255,0.45)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          </svg>
        )}
      </div>

      {/* right strip: drawer handle */}
      <div style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: strip, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <button onClick={() => setOpen(true)} aria-label="Open drawer" aria-expanded={open}
          style={{ width: 44, height: 88, borderRadius: 22, border: '1px solid rgba(255,236,220,0.14)', background: 'rgba(255,236,220,0.06)', color: TEXT, cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8, padding: 0 }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden><path d="M15 6l-6 6 6 6" /></svg>
          <span role="img" aria-label={down ? 'Problem' : warn ? 'Warning' : snap.live ? 'On air' : 'Standby'} style={{ width: 6, height: 6, borderRadius: '50%', background: dot }} />
        </button>
      </div>

      {open && <Drawer snap={snap} session={session} guides={guides} setGuides={setGuides} onClose={() => setOpen(false)} onLeave={onLeave} />}
    </div>
  );
}

const battLow = (s: CamSnapshot) => s.battery.level !== undefined && s.battery.level < 25 && !s.battery.charging;

function Drawer({ snap, session, guides, setGuides, onClose, onLeave }: { snap: CamSnapshot; session: CamSession; guides: boolean; setGuides: (g: boolean) => void; onClose: () => void; onLeave: () => void }) {
  const [unlocked, setUnlocked] = useState(false);
  const [relocking, setRelocking] = useState(false);
  const btn: CSSProperties = { flex: 1, minHeight: 44, borderRadius: 12, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(255,236,220,0.04)', color: TEXT, fontWeight: 700, fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, padding: '0 8px' };

  // Settings lock themselves again after 20 s.
  useEffect(() => {
    if (!unlocked) return;
    const t = setTimeout(() => setUnlocked(false), 20_000);
    return () => clearTimeout(t);
  }, [unlocked, relocking]);

  const relock = async () => {
    setRelocking(true);
    await unlockPicture(session.track);
    await new Promise((r) => setTimeout(r, 3000));
    await session.relock();
    setRelocking(false);
  };

  const lockColor = (v?: string) => (!v ? META : v.includes('lock') && !v.startsWith('auto') ? TEXT : WARN);
  // Short forms for the drawer; the full wording goes to the server/Show screen.
  const short = (v?: string) => (!v ? 'locking…' : v.startsWith('auto (not supported') ? 'auto · no lock' : v.startsWith('auto (lock failed') ? 'auto · lock failed' : v);
  const b = snap.battery;
  const stats: { k: string; v: string; c: string }[] = [
    { k: 'WHITE BAL.', v: short(snap.lock?.wb), c: lockColor(snap.lock?.wb) },
    { k: 'EXPOSURE', v: short(snap.lock?.exposure), c: lockColor(snap.lock?.exposure) },
    { k: 'BATTERY', v: b.level === undefined ? 'not shared' : `${b.level}%${b.charging ? ' · charging' : ''}`, c: b.level === undefined ? META : battLow(snap) ? WARN : TEXT },
    { k: 'TEMP', v: 'not shared', c: META },
    { k: 'WI-FI', v: snap.link ? `${snap.link.label}${snap.link.rttMs !== undefined ? ` ${snap.link.rttMs}ms` : ''}` : '—', c: snap.link?.label.endsWith('weak') ? WARN : TEXT },
    { k: 'BITRATE', v: snap.kbps !== undefined ? `${(snap.kbps / 1000).toFixed(1)} Mbps` : '—', c: TEXT },
    { k: 'VIDEO', v: snap.height ? `${snap.height}p${snap.fps !== undefined ? ` · ${Math.round(snap.fps)} fps` : ''}${snap.limit ? ` · ${snap.limit === 'cpu' ? 'busy/hot' : 'net limit'}` : ''}` : '—', c: (snap.fps !== undefined && snap.fps < 50) || snap.limit ? WARN : TEXT },
    { k: 'LINK', v: snap.media === 'live' && snap.control ? (snap.awake ? 'OK · awake' : 'OK') : snap.media === 'reconnecting' ? 'reconnecting…' : snap.media === 'connecting' ? 'connecting…' : 'down', c: snap.media === 'down' || !snap.control ? ERROR : snap.media === 'live' ? TEXT : WARN },
  ];

  return (
    <div role="dialog" aria-label="Camera status" style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: 'min(300px, 70vw)', boxSizing: 'border-box', padding: '14px 14px 14px 16px', display: 'flex', flexDirection: 'column', gap: 10, background: 'rgba(16,11,8,0.82)', backdropFilter: 'blur(22px)', WebkitBackdropFilter: 'blur(22px)', borderLeft: '1px solid rgba(255,236,220,0.1)', boxShadow: '-20px 0 50px rgba(0,0,0,0.55)', borderRadius: '22px 0 0 22px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {snap.live ? (
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 10px', borderRadius: 8, background: ON_AIR_FILL, color: '#FFFFFF', fontWeight: 800, fontSize: 11, letterSpacing: '0.1em', boxShadow: '0 4px 14px rgba(31,102,224,0.5)' }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#FFFFFF', animation: 'vnBreath 1.4s ease-in-out infinite' }} />ON AIR
          </span>
        ) : (
          <span style={{ padding: '5px 10px', borderRadius: 8, border: '1px solid rgba(255,236,220,0.15)', color: '#C9BDB1', fontWeight: 800, fontSize: 11, letterSpacing: '0.1em' }}>STANDBY</span>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: META, fontWeight: 700 }}>{snap.num}</span>
          <span style={{ fontFamily: 'Sora, sans-serif', fontSize: 15, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{snap.name}</span>
        </div>
        <span style={{ flex: 1 }} />
        <button onClick={onClose} aria-label="Close drawer" style={{ width: 40, height: 40, flex: '0 0 40px', borderRadius: 12, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(255,236,220,0.04)', color: '#C9BDB1', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0 }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden><path d="M9 6l6 6-6 6" /></svg>
        </button>
      </div>

      {snap.error && <span role="alert" style={{ color: ERROR, fontSize: 12, lineHeight: 1.4 }}>{snap.error}</span>}

      <div style={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
      {!unlocked ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 6 }}>
          {stats.map((s) => (
            <div key={s.k} style={{ borderRadius: 12, background: 'rgba(255,236,220,0.05)', border: '1px solid rgba(255,236,220,0.06)', padding: '6px 9px', display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
              <span style={{ fontSize: 10, color: META, fontWeight: 700, letterSpacing: '0.06em' }}>{s.k}</span>
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: s.v.length > 14 ? 11 : 13, fontWeight: 700, color: s.c, lineHeight: 1.3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.v}</span>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span className="vn-label">SETTINGS · UNLOCKED</span>
          <button style={btn} disabled={relocking} onClick={() => void relock()}>{relocking ? 'Measuring the light…' : 'Re-lock white balance & exposure'}</button>
          {canFullscreen() && <button style={btn} onClick={() => void goFullscreen()}>Full screen</button>}
          <button style={{ ...btn, color: ERROR, borderColor: 'rgba(255,90,82,0.35)' }} onClick={onLeave}>Stop camera</button>
          <button style={btn} onClick={() => setUnlocked(false)}>Lock settings</button>
        </div>
      )}

      {isIOS() && !isStandalone() && <span style={{ fontSize: 11, color: META, lineHeight: 1.4 }}>Full screen on iPhone: Share › Add to Home Screen, then open VibeNation from the icon.</span>}
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={() => setGuides(!guides)} aria-pressed={guides} style={btn}>{guides ? 'Guides on' : 'Guides off'}</button>
        {canFullscreen() && !document.fullscreenElement && <button onClick={() => void goFullscreen()} aria-label="Full screen" style={{ ...btn, flex: '0 0 44px', padding: 0 }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></svg>
        </button>}
        {!unlocked && <HoldToUnlock style={btn} onUnlock={() => setUnlocked(true)} />}
      </div>
    </div>
  );
}

function HoldToUnlock({ style, onUnlock }: { style: CSSProperties; onUnlock: () => void }) {
  const [p, setP] = useState(0);
  const raf = useRef(0);
  const start = () => {
    const t0 = performance.now();
    const step = () => {
      const v = Math.min(1, (performance.now() - t0) / 1200);
      setP(v);
      if (v >= 1) { setP(0); onUnlock(); return; }
      raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
  };
  const cancel = () => { cancelAnimationFrame(raf.current); setP(0); };
  useEffect(() => () => cancelAnimationFrame(raf.current), []);
  return (
    <button onPointerDown={start} onPointerUp={cancel} onPointerLeave={cancel} onPointerCancel={cancel} onContextMenu={(e) => e.preventDefault()}
      aria-label="Hold to unlock settings" style={{ ...style, position: 'relative', overflow: 'hidden' }}>
      <span aria-hidden style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${p * 100}%`, background: 'rgba(255,236,220,0.14)' }} />
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden style={{ position: 'relative' }}><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>
      <span style={{ position: 'relative' }}>{p > 0 ? 'Keep holding…' : 'Hold to unlock'}</span>
    </button>
  );
}

function useViewport() {
  const read = () => `${innerWidth}x${innerHeight}`;
  const s = useSyncExternalStore((f) => { addEventListener('resize', f); addEventListener('orientationchange', f); return () => { removeEventListener('resize', f); removeEventListener('orientationchange', f); }; }, read);
  const [w, h] = s.split('x').map(Number);
  return { w, h };
}
