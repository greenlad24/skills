// Phone-side helpers: camera capture, white-balance/exposure lock, battery, wake lock.
// Everything here reports honestly: when a phone can't do something we say so.

export const isIOS = () =>
  /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.userAgent.includes('Macintosh') && navigator.maxTouchPoints > 1);

export const isStandalone = () =>
  matchMedia('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;

/** Rear camera, 1080p60 if the phone can, no audio (the mix comes from the mixer). */
export async function openCamera(): Promise<MediaStreamTrack> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error(location.protocol === 'https:' ? 'This browser cannot use the camera.' : 'The camera needs a secure (https) link.');
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: {
      facingMode: { ideal: 'environment' },
      width: { ideal: 1920 },
      height: { ideal: 1080 },
      frameRate: { ideal: 60 },
      aspectRatio: { ideal: 16 / 9 },
    },
  });
  const track = stream.getVideoTracks()[0];
  if (!track) throw new Error('No camera found.');
  track.contentHint = 'motion';
  return track;
}

export function cameraError(e: unknown): string {
  const name = (e as { name?: string })?.name;
  if (name === 'NotAllowedError') return isIOS()
    ? 'Camera access was blocked. In Settings › Safari › Camera choose "Allow", then reload this page.'
    : 'Camera access was blocked. Tap the lock icon in the address bar, allow the camera, then reload.';
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'No suitable camera found on this phone.';
  if (name === 'NotReadableError') return 'The camera is busy in another app. Close it and try again.';
  return (e as Error)?.message || 'Could not start the camera.';
}

// Image-capture constraints (Chrome on Android). Not in TypeScript's DOM lib, so typed here.
interface CaptureCaps {
  whiteBalanceMode?: string[];
  exposureMode?: string[];
  focusMode?: string[];
  colorTemperature?: { min: number; max: number; step?: number };
  exposureTime?: { min: number; max: number };
  iso?: { min: number; max: number };
}
interface CaptureSettings {
  whiteBalanceMode?: string;
  exposureMode?: string;
  focusMode?: string;
  colorTemperature?: number;
  exposureTime?: number; // units of 100 µs
  iso?: number;
  focusDistance?: number;
}

export interface LockResult {
  locked: boolean;
  wb: string;
  exposure: string;
}

const NOT_SUPPORTED = 'auto (not supported on this phone)';

/** Freeze white balance, exposure and focus at whatever the camera settled on. */
export async function lockPicture(track: MediaStreamTrack): Promise<LockResult> {
  const caps = (track.getCapabilities?.() ?? {}) as CaptureCaps;
  const cur = (track.getSettings() ?? {}) as CaptureSettings;
  const canWb = !!caps.whiteBalanceMode?.includes('manual');
  const canExp = !!caps.exposureMode?.includes('manual');
  const canFocus = !!caps.focusMode?.includes('manual');

  const tryApply = async (c: Record<string, unknown>) => {
    try {
      await track.applyConstraints({ advanced: [c as MediaTrackConstraintSet] });
      return true;
    } catch {
      return false;
    }
  };

  let wbOk = false;
  let expOk = false;
  if (canWb) wbOk = await tryApply({ whiteBalanceMode: 'manual', ...(cur.colorTemperature ? { colorTemperature: cur.colorTemperature } : {}) });
  if (canExp) {
    expOk = await tryApply({
      exposureMode: 'manual',
      ...(cur.exposureTime ? { exposureTime: cur.exposureTime } : {}),
      ...(cur.iso ? { iso: cur.iso } : {}),
    });
  }
  if (canFocus) await tryApply({ focusMode: 'manual', ...(cur.focusDistance ? { focusDistance: cur.focusDistance } : {}) });

  const now = (track.getSettings() ?? {}) as CaptureSettings;
  const wbLocked = wbOk && now.whiteBalanceMode === 'manual';
  const expLocked = expOk && now.exposureMode === 'manual';
  const k = now.colorTemperature ?? cur.colorTemperature;
  const wb = wbLocked ? `${k ? `${Math.round(k)} K` : 'manual'} · lock` : canWb ? 'auto (lock failed)' : NOT_SUPPORTED;
  let exposure = NOT_SUPPORTED;
  if (expLocked) {
    const parts: string[] = [];
    const iso = now.iso ?? cur.iso;
    const t = now.exposureTime ?? cur.exposureTime;
    if (iso) parts.push(`ISO ${Math.round(iso)}`);
    if (t) parts.push(`1/${Math.max(1, Math.round(10000 / t))}`);
    exposure = `${parts.join(' · ') || 'manual'} · lock`;
  } else if (canExp) exposure = 'auto (lock failed)';
  return { locked: wbLocked && expLocked, wb, exposure };
}

/** Put white balance/exposure/focus back to automatic (before re-locking). */
export async function unlockPicture(track: MediaStreamTrack) {
  const caps = (track.getCapabilities?.() ?? {}) as CaptureCaps;
  const c: Record<string, string> = {};
  if (caps.whiteBalanceMode?.includes('continuous')) c.whiteBalanceMode = 'continuous';
  if (caps.exposureMode?.includes('continuous')) c.exposureMode = 'continuous';
  if (caps.focusMode?.includes('continuous')) c.focusMode = 'continuous';
  if (Object.keys(c).length) await track.applyConstraints({ advanced: [c as MediaTrackConstraintSet] }).catch(() => undefined);
}

// ---------- battery ----------

interface BatteryManagerLike extends EventTarget {
  level: number;
  charging: boolean;
}

export interface BatteryInfo {
  level?: number; // 0..100, undefined = unknown (iPhone)
  charging?: boolean;
}

export async function watchBattery(onChange: (b: BatteryInfo) => void): Promise<() => void> {
  const nav = navigator as Navigator & { getBattery?: () => Promise<BatteryManagerLike> };
  if (!nav.getBattery) {
    onChange({});
    return () => undefined;
  }
  try {
    const b = await nav.getBattery();
    const emit = () => onChange({ level: Math.round(b.level * 100), charging: b.charging });
    emit();
    b.addEventListener('levelchange', emit);
    b.addEventListener('chargingchange', emit);
    return () => {
      b.removeEventListener('levelchange', emit);
      b.removeEventListener('chargingchange', emit);
    };
  } catch {
    onChange({});
    return () => undefined;
  }
}

// ---------- screen wake lock ----------

interface WakeLockSentinelLike extends EventTarget {
  release(): Promise<void>;
  released: boolean;
}

/** Keeps the screen on while streaming; re-acquired when the page becomes visible again. */
export function keepAwake(onState: (on: boolean) => void): () => void {
  const wl = (navigator as Navigator & { wakeLock?: { request(t: 'screen'): Promise<WakeLockSentinelLike> } }).wakeLock;
  if (!wl) {
    onState(false);
    return () => undefined;
  }
  let sentinel: WakeLockSentinelLike | null = null;
  let stopped = false;
  const acquire = async () => {
    if (stopped || document.visibilityState !== 'visible') return;
    try {
      sentinel = await wl.request('screen');
      onState(true);
      sentinel.addEventListener('release', () => { if (!stopped) onState(false); });
    } catch {
      onState(false);
    }
  };
  const onVis = () => { if (document.visibilityState === 'visible' && (!sentinel || sentinel.released)) void acquire(); };
  document.addEventListener('visibilitychange', onVis);
  void acquire();
  return () => {
    stopped = true;
    document.removeEventListener('visibilitychange', onVis);
    void sentinel?.release().catch(() => undefined);
  };
}

/** Network type where the browser tells us (Android Chrome); iPhone doesn't. */
export function networkType(): string | undefined {
  const c = (navigator as Navigator & { connection?: { type?: string } }).connection;
  if (!c?.type || c.type === 'unknown') return undefined;
  return c.type === 'wifi' ? 'Wi-Fi' : c.type === 'cellular' ? 'Mobile data' : c.type === 'ethernet' ? 'Wired' : undefined;
}

// ---------- full screen ----------

export async function goFullscreen() {
  const el = document.documentElement as HTMLElement & { webkitRequestFullscreen?: () => Promise<void> };
  try {
    if (!document.fullscreenElement) {
      if (el.requestFullscreen) await el.requestFullscreen({ navigationUI: 'hide' });
      else if (el.webkitRequestFullscreen) await el.webkitRequestFullscreen();
    }
    const o = screen.orientation as ScreenOrientation & { lock?: (o: string) => Promise<void> };
    await o?.lock?.('landscape');
  } catch { /* not supported (iPhone) or refused */ }
}

export const canFullscreen = () => !!(document.documentElement.requestFullscreen || (document.documentElement as HTMLElement & { webkitRequestFullscreen?: unknown }).webkitRequestFullscreen) && !isIOS();
