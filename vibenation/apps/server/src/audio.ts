// Link to the Python audio engine (127.0.0.1:8091): mirrors its mix state into the
// show state, turns its measurement frames into meter frames for browsers, and
// forwards mix actions. Reconnects forever; the demo meters run while it's down.

import type { AudioStatus, ChannelState, ClientAction, EqBand, MeterFrame } from '@vibenation/shared';

const URL_BASE = process.env.VN_AUDIO_URL ?? 'http://127.0.0.1:8091';

export type EngineStrip = {
  n: number; fader: number; pan: number; trim: number; mute: boolean; solo: boolean; no_hpf: boolean;
  eq: [EqBand['kind'], number, number, number][];
  comp: { thresh: number; ratio: number; attack: number; release: number; makeup: number; mix: number } | null;
  plate: number | null; room: number | null; delay: number | null;
};
type EngineState = {
  type: 'engine';
  mix: { strips: Record<string, EngineStrip>; base?: Record<string, EngineStrip>; master_gain: number; bpm: number };
  transport: Omit<AudioStatus, 'connected' | 'calibrating' | 'leveller'>;
  leveller: boolean;
  calibrating: boolean;
};
export type EngineFrame = {
  type: 'meters';
  peak: number[]; rms: number[]; raw: number[]; spec: number[][]; gr: number[]; ride?: number[]; singing?: boolean[];
  /** Arrangement follower: who sings lead/backing, who soloes, which idle channels are auto-muted. */
  arrangement?: { lead: number | null; backing: number[]; solo: number | null; muted: number[] };
  master: { lufsM: number; lufsS: number; lufsI: number; truePeak: number; limiterGr: number; drive: number; spec: number[] };
};

const toBands = (eq: EngineStrip['eq']): EqBand[] => eq.map(([kind, f, gain, q]) => ({ kind, f, gain, q }));
/** Post-fader peak in dBFS -> 0..1 meter position (−60 dB = 0, 0 dBFS ≈ 0.91, +6 = 1). */
const meterPos = (db: number) => Math.max(0, Math.min(1, (db + 60) / 66));

export class AudioLink {
  connected = false;
  status: AudioStatus | null = null;
  private ws: WebSocket | null = null;
  strips: Record<string, EngineStrip> = {};
  /** Last ~30 s of measurement frames (10 per second) for the mixer loop. */
  history: EngineFrame[] = [];
  onAlert?: (a: { level: 'error' | 'info'; ch: number; text: string }) => void;
  private base: Record<string, EngineStrip> = {};

  constructor(
    private onState: (patch: { audio: AudioStatus | null; channels?: (c: ChannelState) => ChannelState; bpm?: number }) => void,
    private onMeters: (f: MeterFrame) => void,
    private log: (msg: string) => void,
  ) {
    this.open();
  }

  private open() {
    const ws = new WebSocket(URL_BASE.replace(/^http/, 'ws') + '/ws');
    this.ws = ws;
    ws.onopen = () => { this.connected = true; this.log('audio engine connected'); };
    ws.onmessage = (e) => {
      const msg = JSON.parse(String(e.data)) as EngineState | EngineFrame | { type: 'error'; error: string } | { type: 'alert'; level: 'error' | 'info'; ch: number; text: string };
      if (msg.type === 'engine') this.applyState(msg);
      else if (msg.type === 'meters') this.applyFrame(msg);
      else if (msg.type === 'alert') this.onAlert?.(msg);
      else this.log(`audio engine: ${msg.error}`);
    };
    // Node's WebSocket may emit only 'error' (no 'close') when the engine is down, so
    // either event schedules exactly one retry.
    let done = false;
    const retry = () => {
      if (done) return;
      done = true;
      if (this.connected) this.log('audio engine disconnected');
      this.connected = false;
      this.status = null;
      this.ws = null;
      this.onState({ audio: null });
      setTimeout(() => this.open(), 2000);
    };
    ws.onclose = retry;
    ws.onerror = retry;
  }

  private applyState(s: EngineState) {
    this.strips = s.mix.strips;
    if (s.mix.base) this.base = s.mix.base;
    this.status = { connected: true, ...s.transport, calibrating: s.calibrating, leveller: s.leveller };
    this.onState({
      audio: this.status,
      bpm: s.mix.bpm,
      channels: (c) => {
        const e = this.strips[String(c.n)];
        if (!e) return c;
        const b = this.base[String(c.n)];
        return {
          ...c, fader: e.fader, pan: e.pan, trim: e.trim, mute: e.mute, solo: e.solo, noHpf: e.no_hpf,
          eq: toBands(e.eq), eqBase: b ? toBands(b.eq) : undefined, comp: e.comp,
          sends: { plate: e.plate, room: e.room, delay: e.delay },
        };
      },
    });
  }

  private applyFrame(f: EngineFrame) {
    this.history.push(f);
    if (this.history.length > 300) this.history.shift();
    const post = f.peak.map((p, i) => {
      const s = this.strips[String(i + 1)];
      return s ? p + s.fader : p;
    });
    this.onMeters({
      type: 'meters',
      ch: post.map(meterPos),
      gr: f.gr,
      peakDb: post,
      spec: f.spec,
      masterSpec: f.master.spec,
      master: { lufsI: f.master.lufsI, lufsS: f.master.lufsS, lufsM: f.master.lufsM, truePeak: f.master.truePeak, limiterGr: f.master.limiterGr, drive: f.master.drive },
    });
  }

  /** Forward a browser action to the engine if it's a mix action. Returns true if handled. */
  forward(a: ClientAction): boolean {
    if (!this.connected || !this.ws) return false;
    const mixTypes = ['fader', 'mute', 'solo', 'pan', 'eq', 'comp', 'send', 'transport', 'calibrate'];
    if (!mixTypes.includes(a.type)) return false;
    this.ws.send(JSON.stringify(a));
    return true;
  }

  /** Send a command that didn't come from a person (e.g. Claude's mixer loop). */
  command(c: Record<string, unknown>) {
    if (this.connected) this.ws?.send(JSON.stringify(c));
  }

  async stream(): Promise<Response> {
    return fetch(URL_BASE + '/stream.mp3');
  }
}
