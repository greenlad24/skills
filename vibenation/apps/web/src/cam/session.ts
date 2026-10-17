// One phone camera session: join the show, publish the camera to LiveKit, report status
// every ~2 s over /cam-ws and receive the on-air tally. Reconnects on its own.

import { ConnectionState, Room, RoomEvent, Track, VideoPreset, type LocalTrackPublication, type LocalVideoTrack } from 'livekit-client';
import type { CamCommand, CamStatus } from '@vibenation/shared';
import { isIOS, keepAwake, lockPicture, networkType, watchBattery, type BatteryInfo, type LockResult } from './device';

export interface JoinInfo {
  camId: number;
  num: string;
  name: string;
  room: string;
  livekitUrl: string;
  token: string;
  camToken: string;
}

export interface CamSnapshot {
  num: string;
  name: string;
  live: boolean;
  /** LiveKit media link. */
  media: 'connecting' | 'live' | 'reconnecting' | 'down';
  /** Status/tally socket to the VibeNation server. */
  control: boolean;
  lock: LockResult | null;
  battery: BatteryInfo;
  awake: boolean;
  kbps?: number;
  fps?: number;
  width?: number;
  height?: number;
  /** Why the encoder is holding back ('cpu' = phone too hot/busy, 'bandwidth' = network). */
  limit?: 'cpu' | 'bandwidth';
  link?: { label: string; rttMs?: number; lossPct?: number };
  error?: string;
}

const STORE = 'vn.cam';
export function savedCam(): { camId?: number; name?: string } {
  try { return JSON.parse(localStorage.getItem(STORE) ?? '{}'); } catch { return {}; }
}
function saveCam(camId: number, name: string) {
  try { localStorage.setItem(STORE, JSON.stringify({ camId, name })); } catch { /* private mode */ }
}

export async function joinShow(k: string, name: string): Promise<JoinInfo> {
  const r = await fetch('/api/cams/join', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ k, name, device: isIOS() ? 'iphone' : 'android', camId: savedCam().camId }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `Could not join (${r.status}).`);
  saveCam(j.camId, j.name);
  return j as JoinInfo;
}

/** H.264 (hardware encoder on iPhone and most Androids); VP8 only if the browser lacks it. */
function pickCodec(): 'h264' | 'vp8' {
  const codecs = typeof RTCRtpSender !== 'undefined' ? RTCRtpSender.getCapabilities?.('video')?.codecs ?? [] : [];
  return codecs.some((c) => c.mimeType.toLowerCase() === 'video/h264') ? 'h264' : 'vp8';
}

export class CamSession {
  private room: Room | null = null;
  private pub: LocalTrackPublication | null = null;
  private ws: WebSocket | null = null;
  private timers: number[] = [];
  private cleanups: (() => void)[] = [];
  private stopped = false;
  private lastBytes = 0;
  private lastT = 0;
  private wsBackoff = 1000;
  private subs = new Set<() => void>();
  snap: CamSnapshot;

  constructor(private k: string, private info: JoinInfo, readonly track: MediaStreamTrack) {
    this.snap = { num: info.num, name: info.name, live: false, media: 'connecting', control: false, lock: null, battery: {}, awake: false };
  }

  subscribe = (f: () => void) => { this.subs.add(f); return () => { this.subs.delete(f); }; };
  private set(p: Partial<CamSnapshot>) {
    this.snap = { ...this.snap, ...p };
    this.subs.forEach((f) => f());
  }

  async start() {
    this.cleanups.push(keepAwake((awake) => this.set({ awake })));
    this.cleanups.push(await watchBattery((battery) => this.set({ battery })));
    this.openSocket();
    await this.connectMedia();
    // Let auto white balance / exposure settle on the stage lights, then freeze them.
    this.timers.push(window.setTimeout(() => void this.relock(), 3000));
    this.timers.push(window.setInterval(() => void this.poll(), 2000));
  }

  /** In portrait the picture would arrive sideways, so stop sending it until the phone is turned back. */
  private portrait = false;
  async setPortrait(p: boolean) {
    this.portrait = p;
    const t = this.pub?.track as LocalVideoTrack | undefined;
    if (!t) return;
    if (p && !t.isMuted) await t.mute().catch(() => undefined);
    else if (!p && t.isMuted) await t.unmute().catch(() => undefined);
  }

  async relock() {
    const lock = await lockPicture(this.track);
    this.set({ lock });
  }

  // ---------- LiveKit ----------

  private async connectMedia() {
    const room = new Room({ adaptiveStream: false, dynacast: true, stopLocalTrackOnUnpublish: false });
    this.room = room;
    room.on(RoomEvent.Reconnecting, () => this.set({ media: 'reconnecting' }));
    room.on(RoomEvent.Reconnected, () => this.set({ media: 'live', error: undefined }));
    room.on(RoomEvent.Disconnected, () => {
      if (this.stopped || this.room !== room) return;
      this.set({ media: 'down' });
      // Fresh token + republish after a short pause.
      this.timers.push(window.setTimeout(() => void this.rejoin(), 3000));
    });
    try {
      await room.connect(this.info.livekitUrl, this.info.token);
      this.pub = await room.localParticipant.publishTrack(this.track, {
        name: 'camera',
        source: Track.Source.Camera,
        videoCodec: pickCodec(),
        backupCodec: false,
        videoEncoding: { maxBitrate: 8_000_000, maxFramerate: 60 },
        simulcast: true,
        videoSimulcastLayers: [new VideoPreset(640, 360, 700_000, 30)],
        degradationPreference: 'maintain-framerate',
      });
      this.set({ media: 'live', error: undefined });
      if (this.portrait) await this.setPortrait(true);
    } catch (e) {
      this.set({ media: 'down', error: `Video link failed: ${(e as Error).message}` });
      if (this.room === room) {
        await room.disconnect().catch(() => undefined);
        if (!this.stopped) this.timers.push(window.setTimeout(() => void this.rejoin(), 4000));
      }
    }
  }

  private async rejoin() {
    if (this.stopped || this.room?.state === ConnectionState.Connected) return;
    try {
      this.info = await joinShow(this.k, this.info.name);
      this.set({ num: this.info.num, name: this.info.name });
      await this.connectMedia();
    } catch (e) {
      this.set({ media: 'down', error: (e as Error).message });
      this.timers.push(window.setTimeout(() => void this.rejoin(), 5000));
    }
  }

  // ---------- status socket ----------

  private openSocket() {
    if (this.stopped) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/cam-ws?ct=${encodeURIComponent(this.info.camToken)}`);
    this.ws = ws;
    ws.onopen = () => { this.wsBackoff = 1000; this.set({ control: true }); void this.poll(); };
    ws.onmessage = (e) => {
      let c: CamCommand;
      try { c = JSON.parse(String(e.data)); } catch { return; }
      if (c.type === 'tally') this.set({ live: c.live });
      else if (c.type === 'rename') this.set({ name: c.name });
    };
    ws.onclose = (e) => {
      if (this.ws !== ws) return;
      this.ws = null;
      this.set({ control: false, live: false });
      if (this.stopped) return;
      if (e.code === 4003) {
        // Camera token expired: join again for a new one.
        void joinShow(this.k, this.info.name).then((i) => { this.info = { ...this.info, camToken: i.camToken }; this.openSocket(); })
          .catch((err) => this.set({ error: (err as Error).message }));
        return;
      }
      this.timers.push(window.setTimeout(() => this.openSocket(), this.wsBackoff));
      this.wsBackoff = Math.min(10_000, this.wsBackoff * 2);
    };
  }

  // ---------- stats + status report ----------

  private async poll() {
    await this.readStats();
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    const s = this.snap;
    const msg: CamStatus = {
      type: 'status',
      battery: s.battery.level,
      charging: s.battery.charging,
      wifi: s.link ? `${s.link.label}${s.link.rttMs !== undefined ? ` · ${s.link.rttMs} ms` : ''}` : undefined,
      kbps: s.kbps,
      fps: s.fps,
      width: s.width,
      height: s.height,
      wb: s.lock?.wb,
      exposure: s.lock?.exposure,
      locked: s.lock?.locked,
      landscape: !matchMedia('(orientation: portrait)').matches,
    };
    this.ws.send(JSON.stringify(msg));
  }

  private async readStats() {
    const track = this.pub?.track as LocalVideoTrack | undefined;
    if (!track) return;
    const report = await track.getRTCStatsReport().catch(() => undefined);
    if (!report) return;
    let bytes = 0;
    let top: { w: number; h: number; fps?: number } | null = null;
    let rtt: number | undefined;
    let lost = 0;
    let lossN = 0;
    let limit: CamSnapshot['limit'];
    report.forEach((r: Record<string, unknown> & { type: string }) => {
      if (r.type === 'outbound-rtp' && r.kind === 'video') {
        bytes += Number(r.bytesSent ?? 0);
        if (r.qualityLimitationReason === 'cpu' || r.qualityLimitationReason === 'bandwidth') limit = r.qualityLimitationReason;
        const w = Number(r.frameWidth ?? 0);
        if (w && (!top || w > top.w)) top = { w, h: Number(r.frameHeight ?? 0), fps: r.framesPerSecond as number | undefined };
      } else if (r.type === 'remote-inbound-rtp' && r.kind === 'video') {
        if (typeof r.roundTripTime === 'number') rtt = Math.max(rtt ?? 0, r.roundTripTime);
        if (typeof r.fractionLost === 'number') { lost += r.fractionLost; lossN++; }
      } else if (r.type === 'candidate-pair' && (r.nominated || r.selected) && r.state === 'succeeded' && typeof r.currentRoundTripTime === 'number') {
        rtt = rtt ?? r.currentRoundTripTime;
      }
    });
    const t = performance.now();
    const kbps = this.lastT && bytes >= this.lastBytes ? Math.round(((bytes - this.lastBytes) * 8) / (t - this.lastT)) : undefined;
    this.lastBytes = bytes;
    this.lastT = t;
    const rttMs = rtt !== undefined ? Math.round(rtt * 1000) : undefined;
    const lossPct = lossN ? Math.round((lost / lossN) * 1000) / 10 : undefined;
    const bad = (rttMs ?? 0) > 250 || (lossPct ?? 0) > 5;
    const ok = (rttMs ?? 0) <= 100 && (lossPct ?? 0) <= 1;
    const kind = networkType();
    const label = `${kind ? `${kind} ` : ''}${bad ? 'weak' : ok ? 'strong' : 'OK'}`;
    const best = top as { w: number; h: number; fps?: number } | null;
    this.set({
      kbps,
      fps: best?.fps ?? this.snap.fps,
      width: best?.w,
      height: best?.h,
      limit,
      link: { label: label.charAt(0).toUpperCase() + label.slice(1), rttMs, lossPct },
    });
  }

  async stop() {
    this.stopped = true;
    this.timers.forEach((t) => { clearTimeout(t); clearInterval(t); });
    this.cleanups.forEach((f) => f());
    this.ws?.close();
    await this.room?.disconnect().catch(() => undefined);
    this.track.stop();
  }
}
