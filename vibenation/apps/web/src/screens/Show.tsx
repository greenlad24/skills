import { useEffect, useRef, useState, type CSSProperties, type PointerEvent } from 'react';
import type { CameraState, ChannelState, ProcessRow, ShowState, VMode } from '@vibenation/shared';
import { fmtDb, send, useMeters, useShow } from '../store';
import { PLATFORM_BG } from '../components/Header';
import { useLiveVideo } from '../components/cams/liveVideo';
import { LiveVideo, NoPicture } from '../components/cams/LiveVideo';
import { AddPhoneTile } from '../components/cams/AddPhone';
import { Fit16x9, SlateArt, type SlateMode } from '../components/slate/SlateArt';

// Show screen: one live program picture, click-to-cut camera tiles, all 16 faders,
// and Claude's sidebar. There is no preview monitor and no manual-mode button.

export const SECTION_COLOR = { drums: '#E08A5A', perc: '#D9A066', gtr: '#E6C07A', keys: '#9FC7A8', vox: '#F5EEE6', bass: '#8FA3D9', horn: '#E58FB0' } as const;

const panel: CSSProperties = { borderRadius: 22, background: 'linear-gradient(180deg, rgba(36,27,21,0.75), rgba(22,16,12,0.75))', border: '1px solid rgba(255,236,220,0.07)', boxShadow: 'inset 0 1px 0 rgba(255,236,220,0.05), 0 20px 50px rgba(0,0,0,0.35)' };

export function ShowScreen() {
  const s = useShow()!;
  const [open, setOpen] = useState(() => localStorage.getItem('vn.sidebar') !== 'closed');
  useEffect(() => { try { localStorage.setItem('vn.sidebar', open ? 'open' : 'closed'); } catch { /* private mode */ } }, [open]);

  // Number keys 1–9 put that camera on air.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.metaKey || e.ctrlKey || e.altKey) return;
      const n = Number(e.key);
      if (n >= 1 && n <= 9 && s.cams.some((c) => c.id === n)) send({ type: 'take', cam: n });
    };
    addEventListener('keydown', onKey);
    return () => removeEventListener('keydown', onKey);
  }, [s.cams]);

  const liveCam = s.cams.find((c) => c.id === s.liveCam);
  // Real phones (CameraState.identity set) stream over LiveKit; demo cameras keep the drawings.
  useLiveVideo(s.cams.some((c) => c.identity), liveCam?.identity);
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', flex: '1 1 auto', minHeight: 0 }}>
      <main style={{ flex: '999 1 640px', minWidth: 0, padding: 22, display: 'flex', flexDirection: 'column', gap: 18 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-start' }}>
          <div style={{ flex: '999 1 560px', minWidth: 0 }}>
            <Program label={s.slate ? `Slate · ${s.slate} · band muted, background music` : liveCam ? `${liveCam.num} · ${liveCam.name}` : '—'} song={s.song} mbps={s.health.mbps} camId={s.liveCam} cam={liveCam} slate={s.slate} />
          </div>
          <Vertical s={s} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span className="vn-label">CAMERAS</span>
          <span style={{ color: 'var(--text-3)', fontSize: 12 }}>Click a camera or press 1–{s.cams.length} to put it on air (Claude keeps directing from there) · the slate is a source too</span>
        </div>
        <section aria-label="Cameras" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(176px, 1fr))', gap: 14, marginTop: -6 }}>
          {s.cams.map((c) => <CamTile key={c.id} cam={c} live={!s.slate && c.id === s.liveCam} />)}
          <SlateTile live={s.slate} />
          <AddPhoneTile />
        </section>

        <MixRow channels={s.channels} />
      </main>
      <Sidebar s={s} open={open} setOpen={setOpen} />
    </div>
  );
}

// ---------- program monitor ----------

const SLATE_COLOURS = { c1: '#FF5E62', c2: '#FF9966', c3: '#FFC371' };

function Program({ label, song, mbps, camId, cam, slate }: { label: string; song: string; mbps: number; camId: number; cam?: CameraState; slate: ShowState['slate'] }) {
  const overlay: CSSProperties = { padding: '5px 12px', borderRadius: 8, background: 'rgba(10,6,4,0.55)', backdropFilter: 'blur(10px)', border: '1px solid rgba(255,236,220,0.12)' };
  return (
    <section aria-label="Program" style={{ borderRadius: 22, padding: 3, background: 'linear-gradient(140deg, #5EA2FF, #1F66E0 55%, #2A4F9E)', boxShadow: '0 0 0 1px rgba(61,139,255,0.25), 0 24px 70px rgba(31,102,224,0.22), 0 30px 60px rgba(0,0,0,0.5)' }}>
      <div style={{ borderRadius: 19, overflow: 'hidden', position: 'relative', aspectRatio: '16 / 9', maxHeight: 470, width: '100%', background: '#070403' }}>
        {slate
          ? <Fit16x9 label={`${slate} slate on air`}><SlateArt mode={slate} time="" colours={SLATE_COLOURS} /></Fit16x9>
          : cam?.identity
          ? <LiveVideo key={cam.identity} identity={cam.identity} label={`Live program: ${cam.num}`} fallback={<NoPicture text={cam.connected ? `Waiting for video from ${cam.num}…` : `${cam.num} is not connected`} />} />
          : <StageScene key={camId} camId={camId} />}
        <div aria-hidden style={{ position: 'absolute', inset: 0, background: 'linear-gradient(180deg, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0) 22%, rgba(0,0,0,0) 70%, rgba(0,0,0,0.55) 100%)' }} />
        <div style={{ position: 'absolute', left: 18, top: 16, display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ padding: '5px 11px', borderRadius: 8, background: 'var(--on-air-fill)', color: '#FFFFFF', fontWeight: 800, fontSize: 12, letterSpacing: '0.1em', boxShadow: '0 4px 16px rgba(31,102,224,0.6)' }}>LIVE</span>
          <span style={{ ...overlay, fontWeight: 600, fontSize: 13 }}>{label}</span>
        </div>
        <div style={{ ...overlay, position: 'absolute', right: 18, top: 16, fontFamily: 'var(--font-mono)', fontSize: 12, color: '#E9DED2' }}>1080p30 · {mbps.toFixed(1)} Mbps</div>
        <div style={{ position: 'absolute', left: 18, right: 18, bottom: 16, display: 'flex', alignItems: 'flex-end', gap: 14 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span style={{ fontSize: 11, letterSpacing: '0.14em', color: '#E9DED2', fontWeight: 700 }}>NOW PLAYING</span>
            <span style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, letterSpacing: '-0.01em' }}>{song}</span>
          </div>
          <span style={{ flex: 1 }} />
          <MasterBars />
        </div>
      </div>
    </section>
  );
}

function MasterBars() {
  const m = useMeters();
  const lvl = m ? Math.max(0.1, Math.min(1, (m.master.lufsS + 30) / 20)) : 0.7;
  return (
    <div aria-hidden style={{ display: 'flex', gap: 3, alignItems: 'flex-end', height: 46 }}>
      {[lvl * 0.92, lvl].map((h, i) => <span key={i} style={{ width: 6, height: `${Math.round(h * 100)}%`, borderRadius: 3, background: 'linear-gradient(to top, #F5EEE6, #FFD7A8)', transition: 'height 90ms linear' }} />)}
    </div>
  );
}

/** Demo stand-in for the live video: a stage silhouette per camera. */
function StageScene({ camId }: { camId: number }) {
  return (
    <svg viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} role="img" aria-label="Live program (demo picture)">
      <defs>
        <linearGradient id="vnBg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#1A0D08" /><stop offset="0.6" stopColor="#0C0604" /><stop offset="1" stopColor="#1C0F09" /></linearGradient>
        <linearGradient id="vnBeamW" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#FFC27A" stopOpacity="0.55" /><stop offset="1" stopColor="#FF8A3D" stopOpacity="0" /></linearGradient>
        <linearGradient id="vnBeamM" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#FF6FA0" stopOpacity="0.32" /><stop offset="1" stopColor="#FF6FA0" stopOpacity="0" /></linearGradient>
        <radialGradient id="vnFloor" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stopColor="#FF9A4D" stopOpacity="0.55" /><stop offset="1" stopColor="#FF9A4D" stopOpacity="0" /></radialGradient>
        <radialGradient id="vnHaze" cx="0.5" cy="0.4" r="0.6"><stop offset="0" stopColor="#FFB27A" stopOpacity="0.18" /><stop offset="1" stopColor="#FFB27A" stopOpacity="0" /></radialGradient>
        <radialGradient id="vnBokeh" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stopColor="#FFD9A8" stopOpacity="0.7" /><stop offset="1" stopColor="#FFD9A8" stopOpacity="0" /></radialGradient>
      </defs>
      <rect width="1600" height="900" fill="url(#vnBg)" />
      <polygon points="700,-20 900,-20 1180,900 420,900" fill="url(#vnBeamW)" />
      <polygon points="180,-20 280,-20 620,900 200,900" fill="url(#vnBeamM)" />
      <polygon points="1320,-20 1420,-20 1400,900 980,900" fill="url(#vnBeamM)" />
      <rect width="1600" height="900" fill="url(#vnHaze)" />
      <ellipse cx="800" cy="840" rx="620" ry="120" fill="url(#vnFloor)" />
      <circle cx="120" cy="140" r="38" fill="url(#vnBokeh)" /><circle cx="1480" cy="110" r="52" fill="url(#vnBokeh)" /><circle cx="1360" cy="220" r="24" fill="url(#vnBokeh)" /><circle cx="260" cy="260" r="20" fill="url(#vnBokeh)" />
      <g transform={camId === 1 ? 'translate(400 260) scale(0.5)' : camId === 3 ? 'translate(-260 0)' : camId === 4 ? 'translate(260 0)' : undefined}>
        <g fill="#050302">
          <rect x="210" y="560" width="300" height="26" rx="6" /><rect x="236" y="586" width="12" height="190" /><rect x="472" y="586" width="12" height="190" />
          <circle cx="360" cy="440" r="46" /><path d="M280 560 C285 500 320 486 360 486 C400 486 435 500 440 560 Z" />
          <circle cx="1270" cy="560" r="86" /><ellipse cx="1150" cy="520" rx="70" ry="16" /><ellipse cx="1400" cy="500" rx="80" ry="18" />
          <circle cx="1275" cy="400" r="42" /><path d="M1200 520 C1205 460 1240 446 1275 446 C1310 446 1345 460 1350 520 Z" />
        </g>
        <g fill="#030201">
          <circle cx="800" cy="330" r="74" /><path d="M650 900 C655 640 720 470 800 470 C880 470 945 640 950 900 Z" />
          <rect x="794" y="440" width="12" height="460" /><rect x="782" y="408" width="36" height="58" rx="18" />
        </g>
        <path d="M745 300 C760 255 840 255 856 300" fill="none" stroke="#FFB27A" strokeOpacity="0.45" strokeWidth="5" />
      </g>
    </svg>
  );
}

// ---------- vertical 9:16 output ----------

function Vertical({ s }: { s: ShowState }) {
  const eff = s.vmode === 'auto' ? s.vAutoPick : s.vmode;
  const seg = (on: boolean): CSSProperties => ({ flex: 1, minHeight: 30, borderRadius: 8, border: 0, fontSize: 11, fontWeight: 700, cursor: 'pointer', background: on ? 'rgba(255,236,220,0.14)' : 'transparent', color: on ? 'var(--text-1)' : 'var(--text-meta)' });
  const modes: [VMode, string][] = [['auto', 'Auto'], ['close', 'Close-up'], ['band', 'Band']];
  const label = s.vmode === 'auto' ? `AUTO · ${s.vAutoPick === 'close' ? 'close-up' : 'band view'}` : s.vmode === 'close' ? 'Close-up · yours' : 'Band view · yours';
  return (
    <section aria-label="Vertical program for TikTok and Instagram" style={{ flex: '0 0 224px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div role="group" aria-label="Vertical layout" style={{ display: 'flex', gap: 2, padding: 3, borderRadius: 10, background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,236,220,0.06)' }}>
        {modes.map(([m, l]) => <button key={m} aria-pressed={s.vmode === m} onClick={() => send({ type: 'vmode', mode: m })} style={seg(s.vmode === m)}>{l}</button>)}
      </div>
      <div style={{ borderRadius: 20, padding: 2, background: 'linear-gradient(160deg, #5EA2FF, #1F66E0 60%, #2A4F9E)', boxShadow: '0 18px 50px rgba(31,102,224,0.2)' }}>
        <div style={{ borderRadius: 18, overflow: 'hidden', position: 'relative', aspectRatio: '9 / 16', background: '#070403' }}>
          {eff === 'close' ? (
            <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(80% 50% at 50% 35%, rgba(255,194,122,0.5), rgba(0,0,0,0) 70%), radial-gradient(90% 40% at 50% 100%, rgba(255,140,70,0.5), rgba(0,0,0,0) 70%), linear-gradient(180deg, #1A0D08, #0B0604)' }}>
              <svg viewBox="0 0 90 160" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} aria-hidden><g fill="#030201"><circle cx="45" cy="62" r="13" /><path d="M18 160 C20 112 32 84 45 84 C58 84 70 112 72 160 Z" /><rect x="44" y="76" width="2" height="84" /><rect x="42" y="70" width="6" height="11" rx="3" /></g></svg>
            </div>
          ) : (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', background: 'linear-gradient(180deg, #160C08, #0B0604)' }}>
              <div style={{ flex: '0 0 22%', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: 2, padding: '0 10px 8px' }}>
                <span style={{ fontSize: 9, fontWeight: 800, letterSpacing: '0.12em', color: '#FFC371' }}>LIVE · MUSIC LIVE LOVE</span>
                <span style={{ fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 800, lineHeight: 1.15 }}>{s.song}</span>
              </div>
              <div style={{ aspectRatio: '16 / 9', position: 'relative', background: 'radial-gradient(60% 80% at 50% 40%, rgba(255,194,122,0.5), rgba(0,0,0,0) 70%), linear-gradient(180deg, #2A1810, #0D0705)' }}>
                <svg viewBox="0 0 160 90" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} aria-hidden><g fill="#030201"><circle cx="40" cy="44" r="7" /><path d="M30 90 C32 70 36 58 40 58 C44 58 48 70 50 90 Z" /><circle cx="80" cy="38" r="8" /><path d="M68 90 C70 64 74 52 80 52 C86 52 90 64 92 90 Z" /><circle cx="120" cy="46" r="7" /><path d="M110 90 C112 72 116 60 120 60 C124 60 128 72 130 90 Z" /></g></svg>
              </div>
              <div style={{ flex: 1, position: 'relative', background: 'radial-gradient(70% 60% at 50% 30%, rgba(255,111,160,0.35), rgba(0,0,0,0) 70%), #0E0705' }}>
                <svg viewBox="0 0 90 70" preserveAspectRatio="xMidYMax slice" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} aria-hidden><g fill="#030201"><circle cx="45" cy="30" r="10" /><path d="M24 70 C26 52 34 42 45 42 C56 42 64 52 66 70 Z" /></g></svg>
                <span style={{ position: 'absolute', left: 8, bottom: 8, fontSize: 9, fontWeight: 700, color: '#E9DED2' }}>close-up · keys</span>
              </div>
            </div>
          )}
          <span style={{ position: 'absolute', left: 10, top: 10, padding: '3px 8px', borderRadius: 6, background: 'var(--on-air-fill)', color: '#FFFFFF', fontSize: 10, fontWeight: 800, letterSpacing: '0.1em' }}>LIVE 9:16</span>
          <span style={{ position: 'absolute', right: 10, top: 10, padding: '3px 8px', borderRadius: 6, background: 'rgba(10,6,4,0.6)', fontSize: 10, fontWeight: 700, color: '#E9DED2' }}>{label}</span>
        </div>
      </div>
      <span style={{ fontSize: 11, color: 'var(--text-meta)', textAlign: 'center', lineHeight: 1.4 }}>
        {s.vmode === 'auto' ? 'Claude switches close-up / band view · TikTok + Instagram 720×1280' : 'Held by you for the rest of the show · tap Auto to give it back'}
      </span>
    </section>
  );
}

// ---------- camera tiles ----------

const SCENES: Record<number, string> = {
  1: 'radial-gradient(70% 90% at 50% 100%, rgba(255,140,70,0.55), rgba(0,0,0,0) 60%), linear-gradient(180deg,#2A1810,#0D0705)',
  2: 'radial-gradient(60% 80% at 50% 20%, rgba(255,194,122,0.6), rgba(0,0,0,0) 65%), linear-gradient(180deg,#2B160D,#0B0604)',
  3: 'radial-gradient(70% 80% at 30% 30%, rgba(255,111,160,0.38), rgba(0,0,0,0) 65%), linear-gradient(180deg,#22121A,#0A0507)',
  4: 'radial-gradient(70% 80% at 70% 30%, rgba(255,160,90,0.4), rgba(0,0,0,0) 65%), linear-gradient(180deg,#24150D,#0B0604)',
  5: 'radial-gradient(90% 70% at 50% 0%, rgba(255,210,150,0.35), rgba(0,0,0,0) 60%), linear-gradient(180deg,#1B120D,#090605)',
};
const BODIES: Record<number, string> = {
  1: 'M40 90 C42 66 52 56 64 56 C76 56 86 66 88 90 Z M96 90 C98 70 106 62 116 62 C126 62 134 70 136 90 Z',
  2: 'M58 90 C60 62 70 52 80 52 C90 52 100 62 102 90 Z',
  3: 'M44 90 C46 64 56 54 68 54 C80 54 90 64 92 90 Z M20 70 h120 v6 h-120 Z',
  4: 'M76 90 C78 64 88 54 98 54 C108 54 118 64 120 90 Z M30 64 a14 6 0 1 0 28 0 a14 6 0 1 0 -28 0',
  5: 'M10 90 C12 76 18 72 26 72 C34 72 40 76 42 90 Z M50 90 C52 74 60 70 68 70 C76 70 82 74 84 90 Z M94 90 C96 76 102 72 110 72 C118 72 124 76 126 90 Z M134 90 C136 78 142 74 148 74 C154 74 158 78 160 90 Z',
};
const HEADS: Record<number, number> = { 1: 64, 2: 80, 3: 68, 4: 98, 5: 68 };

const ROLE_NAMES = ['Wide stage', 'Singer', 'Keys', 'Drums', 'Guitar', 'Bass', 'Horns', 'Crowd'];

function CamTile({ cam, live }: { cam: CameraState; live: boolean }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(cam.name);
  const save = (n: string) => { const v = n.trim(); if (v && v !== cam.name) send({ type: 'renameCam', cam: cam.id, name: v }); setEditing(false); };
  return (
    <div style={{ position: 'relative', display: 'flex', flexDirection: 'column' }}>
      <CamButton cam={cam} live={live} />
      {editing ? (
        <form onSubmit={(e) => { e.preventDefault(); save(name); }} style={{ position: 'absolute', inset: 'auto 6px 6px 6px', padding: 8, borderRadius: 12, background: 'rgba(16,11,8,0.97)', border: '1px solid rgba(255,236,220,0.16)', display: 'flex', flexDirection: 'column', gap: 6, zIndex: 2 }}>
          <input autoFocus value={name} maxLength={40} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === 'Escape') setEditing(false); }} aria-label={`New name for ${cam.num}`}
            style={{ minHeight: 32, padding: '0 8px', borderRadius: 8, border: '1px solid rgba(255,236,220,0.16)', background: 'rgba(0,0,0,0.35)', color: 'var(--text-1)', fontSize: 13 }} />
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {ROLE_NAMES.map((r) => <button type="button" key={r} onClick={() => save(r)} style={{ padding: '3px 7px', borderRadius: 6, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(255,236,220,0.05)', color: 'var(--text-soft)', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}>{r}</button>)}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button type="submit" style={{ flex: 1, minHeight: 28, borderRadius: 7, border: 0, background: 'var(--text-1)', color: '#140D09', fontWeight: 700, fontSize: 12, cursor: 'pointer' }}>Save</button>
            <button type="button" onClick={() => setEditing(false)} style={{ minHeight: 28, padding: '0 10px', borderRadius: 7, border: '1px solid rgba(255,236,220,0.14)', background: 'none', color: 'var(--text-soft)', fontSize: 12, cursor: 'pointer' }}>Cancel</button>
          </div>
        </form>
      ) : (
        <button type="button" onClick={() => { setName(cam.name); setEditing(true); }} aria-label={`Rename ${cam.num}`} title="Rename (the director reads names as roles)"
          style={{ position: 'absolute', right: 52, bottom: cam.identity && cam.connected ? 26 : 10, width: 26, height: 22, borderRadius: 6, border: '1px solid rgba(255,236,220,0.14)', background: 'rgba(255,236,220,0.06)', color: 'var(--text-soft)', fontSize: 12, cursor: 'pointer', zIndex: 1 }}>✎</button>
      )}
    </div>
  );
}

function CamButton({ cam, live }: { cam: CameraState; live: boolean }) {
  const chip = cam.error ?? cam.warn;
  return (
    <button onClick={() => send({ type: 'take', cam: cam.id })} aria-label={`Put ${cam.num} on air`} aria-pressed={live}
      style={{ textAlign: 'left', padding: 8, borderRadius: 18, cursor: 'pointer', color: 'inherit', background: 'linear-gradient(180deg, rgba(40,30,23,0.8), rgba(24,18,14,0.8))', border: live ? '2px solid var(--on-air)' : '1px solid rgba(255,236,220,0.08)', boxShadow: live ? '0 0 0 4px rgba(61,139,255,0.18), 0 14px 30px rgba(31,102,224,0.25)' : '0 10px 24px rgba(0,0,0,0.3)' }}>
      <div style={{ aspectRatio: '16 / 9', borderRadius: 12, background: cam.identity ? '#070403' : SCENES[cam.id] ?? SCENES[5], position: 'relative', overflow: 'hidden' }}>
        {cam.identity
          ? <LiveVideo identity={cam.identity} label={`${cam.num} picture`} fallback={<NoPicture text={cam.connected ? 'Waiting for video…' : 'No signal'} />} />
          : <svg viewBox="0 0 160 90" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} aria-hidden><g fill="#050302" opacity="0.92"><circle cx={HEADS[cam.id] ?? 80} cy="40" r="11" /><path d={BODIES[cam.id] ?? BODIES[2]} /></g></svg>}
        {live && <span style={{ position: 'absolute', right: 8, top: 8, padding: '2px 8px', borderRadius: 6, fontSize: 11, fontWeight: 800, letterSpacing: '0.08em', color: '#FFFFFF', background: 'var(--on-air-fill)' }}>LIVE</span>}
        <span style={{ position: 'absolute', left: 8, top: 8, padding: '2px 7px', borderRadius: 6, background: 'rgba(10,6,4,0.55)', fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, color: 'var(--text-1)' }}>{cam.num}</span>
        {chip && (
          <span style={{ position: 'absolute', left: 8, bottom: 8, padding: '3px 8px', borderRadius: 6, background: cam.error ? 'var(--error-fill)' : 'var(--warn)', color: cam.error ? '#fff' : '#1A1206', fontSize: 11, fontWeight: 800, boxShadow: cam.error ? undefined : '0 4px 12px rgba(255,178,36,0.35)' }}>{chip}</span>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 4px 2px' }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-1)' }}>{cam.name}</span>
        <span style={{ flex: 1 }} />
        <span role="img" aria-label={cam.error ? 'Error' : cam.warn ? 'Warning' : 'Healthy'} style={{ width: 7, height: 7, borderRadius: '50%', background: cam.error ? 'var(--error)' : cam.warn ? 'var(--warn)' : '#8F8378' }} />
        <kbd aria-label={`Shortcut key ${cam.id}`} style={{ minWidth: 20, height: 20, padding: '0 5px', borderRadius: 6, background: 'rgba(255,236,220,0.06)', border: '1px solid rgba(255,236,220,0.12)', borderBottomWidth: 2, fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, color: 'var(--text-soft)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{cam.id}</kbd>
      </div>
      {cam.identity && cam.connected && (
        <div title={`White balance: ${cam.wb ?? '—'} · Exposure: ${cam.exposure ?? '—'}${cam.wifi ? ` · Link: ${cam.wifi}` : ''}`} style={{ padding: '2px 4px 0', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-meta)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {cam.height ? `${cam.height}p${cam.fps !== undefined ? ` · ${Math.round(cam.fps)} fps` : ''}` : '—'}
          {cam.kbps !== undefined ? ` · ${(cam.kbps / 1000).toFixed(1)} Mbps` : ''}
          {cam.locked !== undefined ? (cam.locked ? ' · locked' : ' · auto WB') : ''}
        </div>
      )}
    </button>
  );
}

/** The slate as a video source: pick which one, click to put it on air (the stream then mutes the
 *  band and plays background music). A camera click ends it. */
function SlateTile({ live }: { live: ShowState['slate'] }) {
  const [mode, setMode] = useState<SlateMode>(live ?? 'Starting soon');
  useEffect(() => { if (live) setMode(live); }, [live]);
  const modes: [SlateMode, string][] = [['Starting soon', 'Soon'], ['Break', 'Break'], ['Thanks for watching', 'Thanks']];
  return (
    <div style={{ padding: 8, borderRadius: 18, color: 'inherit', background: 'linear-gradient(180deg, rgba(40,30,23,0.8), rgba(24,18,14,0.8))', border: live ? '2px solid var(--on-air)' : '1px solid rgba(255,236,220,0.08)', boxShadow: live ? '0 0 0 4px rgba(61,139,255,0.18), 0 14px 30px rgba(31,102,224,0.25)' : '0 10px 24px rgba(0,0,0,0.3)', display: 'flex', flexDirection: 'column', gap: 6 }}>
      <button onClick={() => send({ type: 'slate', slate: mode })} aria-label={`Put the ${mode} slate on air`} aria-pressed={!!live}
        style={{ padding: 0, border: 0, background: 'none', cursor: 'pointer', borderRadius: 12, overflow: 'hidden', position: 'relative', aspectRatio: '16 / 9' }}>
        <Fit16x9 label={`${mode} slate preview`}><SlateArt mode={mode} time="" colours={SLATE_COLOURS} /></Fit16x9>
        {live && <span style={{ position: 'absolute', right: 8, top: 8, padding: '2px 8px', borderRadius: 6, fontSize: 11, fontWeight: 800, letterSpacing: '0.08em', color: '#FFFFFF', background: 'var(--on-air-fill)' }}>LIVE</span>}
        <span style={{ position: 'absolute', left: 8, top: 8, padding: '2px 7px', borderRadius: 6, background: 'rgba(10,6,4,0.55)', fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, color: 'var(--text-1)' }}>SLATE</span>
      </button>
      <div role="group" aria-label="Which slate" style={{ display: 'flex', gap: 4 }}>
        {modes.map(([m, short]) => (
          <button key={m} onClick={() => { setMode(m); if (live) send({ type: 'slate', slate: m }); }} aria-pressed={mode === m}
            style={{ flex: 1, minHeight: 26, borderRadius: 7, border: '1px solid rgba(255,236,220,0.12)', background: mode === m ? 'var(--text-1)' : 'rgba(255,236,220,0.04)', color: mode === m ? '#140D09' : 'var(--text-soft)', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}>{short}</button>
        ))}
      </div>
      <span style={{ fontSize: 11, color: 'var(--text-meta)', padding: '0 2px' }}>{live ? 'On air: band muted, background music. Click a camera to end.' : 'Click the picture to put it on air.'}</span>
    </div>
  );
}

// ---------- 16-channel mix row ----------

/** Fader position 0..1 for a dB value: −60…+10 dB, 0 dB at 75 %. */
export const dbToPos = (db: number) => (db >= 0 ? 0.75 + (db / 10) * 0.25 : db <= -60 ? 0 : 0.75 * Math.pow((db + 60) / 60, 2.2));
export const posToDb = (p: number) => (p >= 0.75 ? ((p - 0.75) / 0.25) * 10 : p <= 0 ? -60 : 60 * Math.pow(p / 0.75, 1 / 2.2) - 60);

function MixRow({ channels }: { channels: ChannelState[] }) {
  const m = useMeters();
  const master = m?.master;
  const lufs = master?.lufsI ?? -16;
  return (
    <section aria-label="Mix" style={{ ...panel, padding: '18px 20px', display: 'flex', flexWrap: 'wrap', gap: 22, alignItems: 'stretch' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, width: 180 }}>
        <span className="vn-label">MIX · 16 CHANNELS</span>
        <span style={{ color: 'var(--text-soft)', fontSize: 13, lineHeight: 1.45 }}>Claude is mixing. Touch a fader and it’s yours for the rest of the show.</span>
        <span style={{ flex: 1 }} />
        <div style={{ borderRadius: 16, padding: '12px 14px', background: 'rgba(255,236,220,0.04)', border: '1px solid rgba(255,236,220,0.07)', display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 30, fontWeight: 700, letterSpacing: '-0.03em' }}>{fmtDb(lufs)}</span>
          <span style={{ color: 'var(--text-meta)', fontSize: 11 }}>LUFS · target −16</span>
          <div aria-hidden style={{ marginTop: 8, height: 5, borderRadius: 3, background: 'rgba(255,236,220,0.07)', position: 'relative' }}>
            <div style={{ position: 'absolute', left: 0, width: `${Math.max(0, Math.min(100, (lufs + 36) * 4))}%`, top: 0, bottom: 0, borderRadius: 3, background: 'linear-gradient(90deg, #6E6258, #F5EEE6)' }} />
            <div style={{ position: 'absolute', left: '80%', top: -3, bottom: -3, width: 2, background: 'var(--brand)' }} />
          </div>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: master && master.truePeak > -1 ? 'var(--error)' : 'var(--text-soft)', marginTop: 6 }}>TP {fmtDb(master?.truePeak ?? -1.4)} dBTP</span>
        </div>
      </div>
      <div style={{ flex: '1 1 560px', minWidth: 0, display: 'grid', gridTemplateColumns: 'repeat(16, minmax(34px, 1fr))', gap: 4, overflowX: 'auto' }}>
        {channels.map((c, i) => <MiniStrip key={c.n} c={c} meter={m?.ch[i] ?? 0} />)}
      </div>
    </section>
  );
}

function MiniStrip({ c, meter }: { c: ChannelState; meter: number }) {
  const color = SECTION_COLOR[c.section];
  const track = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<number | null>(null);
  const last = useRef(0);
  const db = drag ?? c.fader;

  const setFromPointer = (e: PointerEvent) => {
    const r = track.current!.getBoundingClientRect();
    const p = Math.max(0, Math.min(1, (r.bottom - 13 - e.clientY) / (r.height - 26)));
    const v = Math.round(posToDb(p) * 10) / 10;
    setDrag(v);
    if (performance.now() - last.current > 50) { last.current = performance.now(); send({ type: 'fader', ch: c.n, db: v }); }
  };
  const end = () => { if (drag !== null) send({ type: 'fader', ch: c.n, db: drag }); setDrag(null); };

  const tag = c.held ? 'YOU' : c.aiRecent ? 'AI' : '·';
  const tagStyle: CSSProperties = c.held
    ? { fontSize: 9, fontWeight: 800, letterSpacing: '0.06em', padding: '1px 5px', borderRadius: 5, background: 'var(--text-1)', color: '#140D09' }
    : c.aiRecent
      ? { fontSize: 9, fontWeight: 800, letterSpacing: '0.06em', padding: '1px 5px', borderRadius: 5, background: 'rgba(185,166,255,0.16)', color: 'var(--ai-text)' }
      : { fontSize: 9, color: 'transparent', padding: '1px 5px' };
  const shown = c.mute ? 'mute' : fmtDb(db);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 7, padding: '8px 2px', borderRadius: 12, background: c.held ? 'rgba(245,238,230,0.06)' : 'transparent' }}>
      <span style={{ width: 18, height: 3, borderRadius: 2, background: color, boxShadow: `0 0 8px ${color}` }} />
      <div style={{ height: 132, display: 'flex', gap: 3, alignItems: 'flex-end' }}>
        <div aria-hidden style={{ width: 5, height: '100%', borderRadius: 3, background: 'rgba(255,236,220,0.06)', position: 'relative', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: `${Math.round(meter * 100)}%`, background: 'linear-gradient(to top, #8F8378 0%, #E9DED2 68%, #FFB224 90%, #FF5A52 100%)', backgroundSize: '100% 132px', backgroundPosition: 'bottom' }} />
          <div style={{ position: 'absolute', inset: 0, background: 'repeating-linear-gradient(to top, rgba(11,8,6,0) 0 3px, rgba(11,8,6,0.9) 3px 4px)' }} />
        </div>
        <div ref={track} role="slider" tabIndex={0} aria-label={`${c.name} fader`} aria-valuemin={-60} aria-valuemax={10} aria-valuenow={db} aria-valuetext={`${shown} dB`}
          onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); setFromPointer(e); }}
          onPointerMove={(e) => { if (drag !== null) setFromPointer(e); }}
          onPointerUp={end} onPointerCancel={end}
          onKeyDown={(e) => {
            const step = e.shiftKey ? 0.1 : 0.5;
            if (e.key === 'ArrowUp' || e.key === 'ArrowDown') { e.preventDefault(); send({ type: 'fader', ch: c.n, db: c.fader + (e.key === 'ArrowUp' ? step : -step) }); }
          }}
          style={{ width: 22, height: '100%', position: 'relative', cursor: 'ns-resize', touchAction: 'none' }}>
          <div style={{ position: 'absolute', left: 9, width: 4, top: 4, bottom: 4, background: 'rgba(0,0,0,0.55)', borderRadius: 2, boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.6)' }} />
          <div style={{ position: 'absolute', left: 0, right: 0, height: 26, bottom: `calc(${dbToPos(db) * 100}% - ${dbToPos(db) * 26}px)`, borderRadius: 5, background: 'linear-gradient(180deg, #FAF5EF 0%, #D9CFC5 48%, #B8ADA2 52%, #E6DDD3 100%)', boxShadow: '0 3px 8px rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ width: 14, height: 2, background: '#3A2E26', borderRadius: 1 }} />
          </div>
        </div>
      </div>
      <span style={{ fontSize: 10, fontWeight: 700, textAlign: 'center', lineHeight: 1.15, minHeight: 23, color: '#E9DED2' }}>{c.n === 11 && c.role ? c.role : c.short}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-meta)' }}>{shown}</span>
      <span style={tagStyle}>{tag}</span>
    </div>
  );
}

// ---------- Claude sidebar ----------

const LEVEL_COLOR: Record<ProcessRow['level'], string> = { ok: '#8F8378', ai: '#B9A6FF', warn: '#FFB224', error: '#FF5A52' };
const dot = (c: string): CSSProperties => ({ width: 8, height: 8, borderRadius: '50%', flex: 'none', background: c, boxShadow: c !== '#8F8378' ? `0 0 8px ${c}` : undefined });
const fmtTime = (t: number) => new Date(t).toLocaleTimeString('en-GB', { hour12: false });
const iconBtn: CSSProperties = { width: 40, height: 40, borderRadius: 12, border: '1px solid rgba(255,236,220,0.1)', background: 'rgba(255,236,220,0.04)', color: 'var(--text-soft)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' };
const smallBtn: CSSProperties = { minHeight: 30, padding: '0 12px', borderRadius: 999, border: '1px solid rgba(255,236,220,0.12)', background: 'rgba(255,236,220,0.04)', color: 'var(--text-1)', fontSize: 12, cursor: 'pointer' };
const CHAT_COLORS = ['#E6C07A', '#9FC7A8', '#8FA3D9', '#E58FB0', '#E08A5A', '#C9BDB1'];

function Sidebar({ s, open, setOpen }: { s: ShowState; open: boolean; setOpen: (o: boolean) => void }) {
  const [tab, setTab] = useState<'claude' | 'chat'>('claude');
  const requests = s.chat.filter((m) => m.tag === 'SONG REQUEST').length;
  const problems = s.procs.filter((p) => p.level === 'warn' || p.level === 'error');
  const tabBtn = (on: boolean): CSSProperties => ({ flex: 1, minHeight: 34, borderRadius: 9, border: 0, fontWeight: 700, fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, background: on ? 'rgba(255,236,220,0.12)' : 'transparent', color: on ? 'var(--text-1)' : 'var(--text-meta)' });

  return (
    <aside aria-label="Claude activity" style={{ flex: `0 0 ${open ? 350 : 60}px`, minWidth: 0, borderLeft: '1px solid rgba(255,236,220,0.07)', background: 'linear-gradient(180deg, rgba(20,14,11,0.85), rgba(14,10,8,0.85))', backdropFilter: 'blur(18px)', transition: 'flex-basis 180ms ease' }}>
      {open ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18, padding: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 30, height: 30, borderRadius: 9, background: 'radial-gradient(circle at 30% 25%, #E5DBFF, #B9A6FF 50%, #7C66D9)', boxShadow: '0 0 18px rgba(185,166,255,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1B1430" strokeWidth="2.2" strokeLinecap="round" aria-hidden><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6" /></svg>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 15 }}>Claude</span>
              <span style={{ color: 'var(--text-meta)', fontSize: 12 }}>Director + mixer · all on Auto</span>
            </div>
            <span style={{ flex: 1 }} />
            <button onClick={() => setOpen(false)} aria-label="Collapse sidebar" style={iconBtn}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M9 6l6 6-6 6" /></svg>
            </button>
          </div>
          <div role="tablist" aria-label="Sidebar" style={{ display: 'flex', gap: 2, padding: 3, borderRadius: 12, background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,236,220,0.06)' }}>
            <button role="tab" aria-selected={tab === 'claude'} onClick={() => setTab('claude')} style={tabBtn(tab === 'claude')}>Claude</button>
            <button role="tab" aria-selected={tab === 'chat'} onClick={() => setTab('chat')} style={tabBtn(tab === 'chat')}>
              Live chat {requests > 0 && <span style={{ padding: '1px 6px', borderRadius: 999, background: 'var(--warn)', color: '#1A1206', fontSize: 10, fontWeight: 800 }}>{requests} request{requests > 1 ? 's' : ''}</span>}
            </button>
          </div>

          {tab === 'claude' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div style={{ position: 'relative', borderRadius: 18, padding: 1, background: 'linear-gradient(140deg, rgba(185,166,255,0.9), rgba(185,166,255,0.15) 60%, rgba(255,138,61,0.4))', boxShadow: '0 12px 40px rgba(124,102,217,0.22)' }}>
                <div style={{ borderRadius: 17, padding: 14, background: 'linear-gradient(180deg, #1C1626, #15101C)', display: 'flex', flexDirection: 'column', gap: 10, overflow: 'hidden' }}>
                  <span style={{ fontSize: 11, letterSpacing: '0.14em', color: 'var(--ai-text)', fontWeight: 700 }}>DIRECTOR IS THINKING</span>
                  <span style={{ fontSize: 14, lineHeight: 1.5, color: '#F1ECFF' }}>{s.thinking.text}</span>
                  <div aria-hidden style={{ height: 3, borderRadius: 2, background: 'rgba(185,166,255,0.15)', overflow: 'hidden', position: 'relative' }}>
                    <div style={{ position: 'absolute', top: 0, bottom: 0, width: '40%', background: 'linear-gradient(90deg, rgba(185,166,255,0), #B9A6FF, rgba(185,166,255,0))', animation: 'vnThink 1.6s ease-in-out infinite' }} />
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {[`heard: ${s.thinking.heard}`, `confidence: ${s.thinking.confidence}`].map((t) => <span key={t} style={{ padding: '3px 9px', borderRadius: 999, background: 'rgba(185,166,255,0.12)', color: '#D9CFFF', fontSize: 11, fontWeight: 600 }}>{t}</span>)}
                  </div>
                </div>
              </div>

              <div style={{ borderRadius: 18, background: 'rgba(255,236,220,0.035)', border: '1px solid rgba(255,236,220,0.07)', padding: '6px 14px' }}>
                {s.procs.map((p) => (
                  <div key={p.name} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 0', borderBottom: '1px solid rgba(255,236,220,0.05)' }}>
                    <span style={dot(LEVEL_COLOR[p.level])} />
                    <span style={{ fontSize: 13, color: '#E9DED2' }}>{p.name}</span>
                    <span style={{ flex: 1 }} />
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: p.level === 'warn' ? 'var(--warn)' : p.level === 'error' ? 'var(--error)' : 'var(--text-meta)' }}>{p.meta}</span>
                  </div>
                ))}
              </div>

              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span className="vn-label" style={{ marginBottom: 10 }}>ACTIVITY</span>
                {s.feed.slice(0, 12).map((f) => {
                  const kc = f.kind === 'YOURS' ? '#F5EEE6' : f.kind === 'EMERGENCY' ? '#FF5A52' : f.kind === 'SHOW' ? '#9C9084' : '#B9A6FF';
                  return (
                    <div key={f.id} style={{ display: 'flex', gap: 12 }}>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 10 }}>
                        <span style={{ width: 9, height: 9, borderRadius: '50%', marginTop: 6, background: kc, boxShadow: '0 0 0 3px #0F0A08' }} />
                        <span style={{ flex: 1, width: 1, background: 'rgba(255,236,220,0.1)' }} />
                      </div>
                      <div style={{ flex: 1, paddingBottom: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', color: kc }}>{f.kind}</span>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)' }}>{fmtTime(f.t)}</span>
                          {f.confidence && <span style={{ fontSize: 11, color: 'var(--text-3)' }}>· {f.confidence}</span>}
                        </div>
                        <span style={{ fontSize: 13, lineHeight: 1.45, color: 'var(--text-1)' }}>{f.text}</span>
                        {f.why && <span style={{ fontSize: 12, color: 'var(--text-meta)', lineHeight: 1.45 }}>{f.why}</span>}
                        {f.undoable && (
                          <div style={{ display: 'flex', gap: 6, marginTop: 2 }}>
                            <button style={smallBtn} onClick={() => send({ type: 'undo', feedId: f.id })}>Undo</button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingBottom: 6 }}>
                <span className="vn-label">LIVE CHAT · ALL PLATFORMS</span>
                <span style={{ flex: 1 }} />
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-meta)' }}>{s.health.viewers.toLocaleString('en')} watching</span>
              </div>
              {s.chat.map((m, i) => (
                <div key={m.id} style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '9px 10px', borderRadius: 12, ...(m.tag ? { background: 'rgba(255,236,220,0.05)', border: '1px solid rgba(255,236,220,0.08)' } : {}) }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, flexWrap: 'wrap' }}>
                    <span style={{ padding: '1px 5px', borderRadius: 5, background: PLATFORM_BG[m.p], color: '#FFFFFF', fontSize: 9, fontWeight: 800 }}>{m.p}</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: CHAT_COLORS[i % CHAT_COLORS.length] }}>{m.who}</span>
                    {m.tag && <span style={{ padding: '1px 7px', borderRadius: 999, background: m.tag === 'SONG REQUEST' ? 'var(--warn)' : 'var(--ai)', color: '#140D09', fontSize: 10, fontWeight: 800 }}>{m.tag}</span>}
                  </div>
                  <span style={{ fontSize: 13, lineHeight: 1.45, color: '#E9DED2' }}>{m.text}</span>
                  {m.note && <span style={{ fontSize: 11, color: 'var(--ai-text)' }}>{m.note}</span>}
                </div>
              ))}
              <span style={{ fontSize: 12, color: 'var(--text-3)', paddingTop: 6 }}>Claude reads chat only to flag requests and shout-outs. It never posts.</span>
            </div>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, padding: '16px 0' }}>
          <button onClick={() => setOpen(true)} aria-label="Expand sidebar" style={iconBtn}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M15 6l-6 6 6 6" /></svg>
          </button>
          <span title="AUTO" style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--ai)', boxShadow: '0 0 10px var(--ai)' }} />
          {s.procs.map((p) => <span key={p.name} role="img" aria-label={`${p.name}: ${p.meta}`} title={`${p.name} · ${p.meta}`} style={dot(LEVEL_COLOR[p.level])} />)}
          {problems.length === 0 && null}
          {s.held.length > 0 && (
            <span aria-label={`${s.held.length} controls held by you`} title="Controls held by you" style={{ marginTop: 6, minWidth: 22, padding: '2px 6px', borderRadius: 999, background: 'var(--text-1)', color: '#140D09', fontSize: 11, fontWeight: 800, textAlign: 'center' }}>{s.held.length}</span>
          )}
        </div>
      )}
    </aside>
  );
}
