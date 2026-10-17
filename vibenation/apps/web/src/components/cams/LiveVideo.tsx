import { useEffect, useRef, type ReactNode } from 'react';
import { useCamTrack } from './liveVideo';

/** A phone camera's live picture (fills its parent). Shows `fallback` until video arrives. */
export function LiveVideo({ identity, label, fallback }: { identity: string; label: string; fallback?: ReactNode }) {
  const track = useCamTrack(identity);
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!track || !el) return;
    track.attach(el);
    return () => { track.detach(el); };
  }, [track]);
  return (
    <>
      {!track && (fallback ?? <NoPicture text="Waiting for video…" />)}
      <video ref={ref} aria-label={label} playsInline muted autoPlay
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', background: '#070403', display: track ? 'block' : 'none' }} />
    </>
  );
}

export function NoPicture({ text }: { text: string }) {
  return (
    <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(180deg, #160E0A, #0A0605)', color: 'var(--text-meta)', fontSize: 12, fontWeight: 600, textAlign: 'center', padding: 8 }}>
      {text}
    </div>
  );
}
