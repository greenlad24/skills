// Demo show: fake cameras, meters and Claude activity so the UI can be built and
// reviewed before the real audio/video engines exist. Replaced piece by piece in
// later milestones; the held-by-you rules here are the real rules.

import { CHANNELS, type CameraState, type ClientAction, type FeedItem, type ShowState, type MeterFrame, type ChatMessage } from '@vibenation/shared';
import { AudioLink } from './audio.js';
import { MixerLoop } from './mixer.js';
import { Director } from './director.js';
import { Listener as AudioListener } from './listener.js';
import { GoLive } from './golive.js';
import { loadPackage } from './package.js';
import { ShowLog, loadPlaybook, reviewShow } from './learning.js';

type Listener = (msg: { type: 'state'; state: ShowState } | MeterFrame) => void;

const now = () => Date.now();
let seq = 0;
const id = () => `${now().toString(36)}-${(seq++).toString(36)}`;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const pick = <T>(a: readonly T[]) => a[Math.floor(Math.random() * a.length)];

const SONGS = ['Song 7 · second chorus', 'Song 7 · keys solo', 'Song 8 · intro', 'Song 8 · verse', 'Song 8 · chorus'];

const DEMO_CHAT: Omit<ChatMessage, 'id'>[] = [
  { p: 'YT', who: 'groovecat_88', text: 'can you guys do Superstition next?? 🎹', tag: 'SONG REQUEST', note: 'Flagged for the band' },
  { p: 'IG', who: 'maria.l', text: 'that sax solo omg' },
  { p: 'TW', who: 'jonah_beats', text: 'shout out to the drummer!', tag: 'SHOUT-OUT', note: 'Flagged for the singer between songs' },
  { p: 'TT', who: 'kenji', text: 'audio sounds amazing tonight' },
  { p: 'FB', who: 'soulful_sam', text: 'Lose Control again pls 🙏', tag: 'SONG REQUEST', note: 'Flagged for the band' },
  { p: 'TT', who: 'ana.r', text: 'first time here, this is so good' },
  { p: 'YT', who: 'theo', text: 'the keys tone 🔥' },
];

export class DemoShow {
  state: ShowState;
  private listeners = new Set<Listener>();
  private realCams = new Map<number, CameraState>();
  private demoCams: CameraState[] = [];
  private camWatchers: (() => void)[] = [];
  private aiTouched = new Map<number, number>(); // ch -> last AI touch time
  private lastCut = now();
  private undo = new Map<string, () => void>();
  readonly audio: AudioLink;
  readonly mixer: MixerLoop;
  readonly director: Director;
  readonly golive: GoLive;
  readonly listener: AudioListener;
  private videoSent = { cam: -1, slate: '' as string | null };
  readonly log = new ShowLog();

  constructor() {
    const t = now();
    this.state = {
      showName: 'MusicLiveLove · Live Session',
      onAir: false,
      liveSince: null,
      slate: null,
      destinations: { YT: true, TW: true, FB: true, TT: true, IG: true }, // switched on; 'ready' says which are connected
      cams: [
        { id: 1, num: 'CAM 1', name: 'Wide stage', device: 'android', connected: true, battery: 74, charging: true },
        { id: 2, num: 'CAM 2', name: 'Lead vocal', device: 'android', connected: true, battery: 86, charging: false },
        { id: 3, num: 'CAM 3', name: 'Keys', device: 'android', connected: true, battery: 63, charging: true },
        { id: 4, num: 'CAM 4', name: 'Drums', device: 'android', connected: true, battery: 18, charging: false, warn: 'Battery 18%' },
        { id: 5, num: 'CAM 5', name: 'Crowd · iPhone', device: 'iphone', connected: true, battery: 91, charging: true },
      ],
      liveCam: 2,
      vmode: 'auto',
      vmodeHeld: false,
      vAutoPick: 'close',
      channels: CHANNELS.map((c) => ({
        n: c.n, name: c.name, short: c.short, section: c.section, fader: c.fader,
        meter: 0, gr: 0, mute: c.n === 4, solo: false, held: false, aiRecent: false,
        role: c.n === 11 ? 'Trombone' : undefined,
      })),
      master: { lufsI: -16.2, lufsS: -16.0, truePeak: -1.4, limiterGr: 1.8 },
      song: SONGS[0],
      bpm: 118,
      health: { mbps: 0, fps: 0, cpu: 0, dropped: 0, viewers: 0, likes: 0 },
      thinking: {
        text: 'Piano solo is starting — keys up 6 dB and melodic, vocal silent for 4 bars. Planning to cut to CAM 3 · Keys on the next downbeat.',
        heard: 'keys solo',
        confidence: 'likely',
      },
      procs: [],
      feed: [],
      chat: DEMO_CHAT.map((m) => ({ ...m, id: id() })),
      held: [],
      controls: {},
      demo: true,
      audio: null,
      preflight: [],
      youtube: { configured: false, connected: false, channel: null },
      ready: { YT: false, TW: false, FB: false, TT: false, IG: false },
      golive: { phase: 'idle' },
    };
    this.feed({ kind: 'SHOW', text: 'Demo show running.', why: 'Fake cameras and audio until the real engines are connected.' });
    this.refreshProcs();
    this.audio = new AudioLink(
      (patch) => {
        this.state.audio = patch.audio;
        if (patch.channels) this.state.channels = this.state.channels.map(patch.channels);
        if (patch.bpm) this.state.bpm = patch.bpm;
        this.refreshProcs();
        this.push();
      },
      (frame) => {
        this.state.master = { ...this.state.master, ...frame.master };
        for (const fn of this.listeners) fn(frame);
      },
      (msg) => console.log(msg),
    );
    this.audio.onAlert = (al) => {
      this.feed({ kind: al.level === 'error' ? 'EMERGENCY' : 'MIX', text: al.text, why: al.level === 'error' ? 'Emergency move: allowed even on a channel you hold.' : undefined, confidence: 'sure' });
      this.push();
    };
    this.listener = new AudioListener(() => !!this.state.audio?.playing);
    this.mixer = new MixerLoop({
      state: this.state,
      listener: this.listener,
      audio: this.audio,
      isHeld: (id) => this.isHeld(id),
      addFeed: (f, undo) => { this.feed(f, undo); this.push(); },
      aiTouched: (ch) => this.aiTouched.set(ch, now()),
      hold: (id, ch) => this.hold(id, ch),
      changed: () => { this.refreshProcs(); this.push(); },
    });
    setInterval(() => { if (this.state.onAir) this.log.write({ type: 'loudness', lufsI: this.state.master.lufsI, tp: this.state.master.truePeak, lim: this.state.master.limiterGr }); }, 60_000);
    this.director = new Director(() => this.state, this.audio, (cam, why, confidence) => {
      const c = this.state.cams.find((x) => x.id === cam);
      if (!c) return;
      this.state.liveCam = cam;
      this.lastCut = now();
      this.feed({ kind: 'DIRECTOR', text: `Cut to ${c.num} · ${c.name}.`, why, confidence });
      this.state.thinking = { ...this.state.thinking, text: `On ${c.num} · ${c.name}: ${why}.`, heard: why.split(' — ')[0] };
      this.push();
    });
    this.golive = new GoLive({
      state: this.state,
      audio: this.audio,
      addFeed: (f) => this.feed(f),
      push: () => this.push(),
      pkg: loadPackage,
      startShow: () => {
        this.log.start();
        this.state.onAir = true;
        this.state.liveSince = now();
        this.state.held = [];
        this.state.controls = {};
        for (const c of this.state.channels) c.held = false;
      },
    });
    // Keep the video service following the director and the slate.
    this.camWatchers.push(() => {
      const s = this.state;
      if (!s.onAir) return;
      if (s.liveCam !== this.videoSent.cam) { this.videoSent.cam = s.liveCam; void fetch((process.env.VN_VIDEO_URL ?? 'http://127.0.0.1:8092') + '/cmd', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ program: s.liveCam }) }).catch(() => undefined); }
      if (s.slate !== this.videoSent.slate) { this.videoSent.slate = s.slate; void fetch((process.env.VN_VIDEO_URL ?? 'http://127.0.0.1:8092') + '/cmd', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ slate: s.slate, minutes: 15 }) }).catch(() => undefined); }
    });
    setInterval(() => this.meters(), 100);
    setInterval(() => this.claudeTick(), 6000);
  }

  subscribe(fn: Listener) {
    this.listeners.add(fn);
    fn({ type: 'state', state: this.state });
    return () => this.listeners.delete(fn);
  }

  private push() {
    for (const fn of this.listeners) fn({ type: 'state', state: this.state });
    for (const fn of this.camWatchers) fn();
  }

  // ---- real phone cameras (CamHost) ----
  cams() { return this.state.cams; }
  liveCam() { return this.state.liveCam; }
  onCamsChanged(fn: () => void) { this.camWatchers.push(fn); }
  upsertCam(c: CameraState) {
    const isNew = !this.realCams.has(c.id);
    this.realCams.set(c.id, c);
    this.syncCams();
    if (isNew) this.feed({ kind: 'SHOW', text: `${c.num} · ${c.name} joined.`, why: c.device === 'iphone' ? 'iPhone camera page' : 'Android camera app' });
    this.refreshProcs();
    this.push();
  }
  camGone(id: number) {
    this.realCams.delete(id);
    this.syncCams();
    this.push();
  }
  private syncCams() {
    if (!this.demoCams.length) this.demoCams = this.state.cams.filter((c) => !c.identity);
    const real = [...this.realCams.values()].sort((a, b) => a.id - b.id);
    this.state.cams = real.length ? real : this.demoCams;
    if (!this.state.cams.some((c) => c.id === this.state.liveCam)) this.state.liveCam = this.state.cams[0]?.id ?? 0;
  }

  private feed(f: Omit<FeedItem, 'id' | 't'>, undo?: () => void) {
    const item: FeedItem = { ...f, id: id(), t: now(), undoable: !!undo };
    const type = f.kind === 'DIRECTOR' ? 'cut' : f.kind === 'MIX' ? 'mix' : f.kind === 'EMERGENCY' ? 'alert' : f.kind === 'YOURS'
      ? (/^You cut/.test(f.text) ? 'human_cut' : /^Undid/.test(f.text) ? 'undo' : 'hold') : 'show';
    this.log.write({ type, text: f.text, why: f.why, confidence: f.confidence });
    if (undo) this.undo.set(item.id, undo);
    this.state.feed = [item, ...this.state.feed].slice(0, 60);
    return item;
  }

  /** True if a human holds this control (ids like "ch9.fader", "ch9.eq", "ch9.comp", "ch9.send"). */
  isHeld(id: string) {
    return this.state.held.some((h) => h === id || normalizeHold(h) === id);
  }

  hold(key: string, ch?: number) {
    if (!this.state.held.includes(key)) {
      this.state.held.push(key);
      if (ch) {
        const c = this.state.channels[ch - 1];
        if (!c.held) {
          c.held = true;
          this.feed({ kind: 'YOURS', text: `You moved ${c.name} — held by you for the rest of the show.`, why: 'Claude only steps in for feedback, clipping or a dead signal.' });
        }
      }
    }
  }

  private refreshProcs() {
    const s = this.state;
    s.procs = [
      s.audio
        ? { name: 'Mixer audio link', meta: s.audio.source === 'recording' ? `test recording · ${s.audio.playing ? 'playing' : 'paused'}` : '16 ch · 48k', level: s.audio.playing ? 'ok' : 'warn' }
        : { name: 'Mix engine', meta: 'not connected', level: 'error' },
      { name: 'Cameras', meta: `${s.cams.filter((c) => c.connected).length} / ${s.cams.length}`, level: 'ok' },
      ...(s.audio ? [{ name: 'Mix engine', meta: `${s.master.lufsI.toFixed(1)} LUFS · TP ${s.master.truePeak.toFixed(1)}`, level: (s.master.truePeak > -1 ? 'warn' : 'ok') as 'warn' | 'ok' }] : []),
      { name: 'Claude mixer', meta: this.mixer?.status() ?? 'starting', level: this.mixer?.lastError ? 'warn' : 'ai' },
      { name: 'Listener (hearing)', meta: this.listener?.status() ?? 'off', level: this.listener?.enabled ? (this.listener.lastError ? 'warn' : 'ai') : 'ok' },
      { name: 'Director', meta: s.vmodeHeld ? 'auto · vertical yours' : 'auto', level: 'ai' },
      { name: 'YouTube ingest', meta: `${s.health.mbps.toFixed(1)} Mbps`, level: 'ok' },
      ...s.cams.filter((c) => c.warn || c.error).map((c) => ({ name: c.num, meta: (c.error ?? c.warn)!, level: (c.error ? 'error' : 'warn') as 'error' | 'warn' })),
    ];
  }

  private meters() {
    const t = now() / 1000;
    const s = this.state;
    for (const c of s.channels) c.aiRecent = (this.aiTouched.get(c.n) ?? 0) > now() - 30_000;
    if (this.audio.connected) return; // real meters come from the audio engine
    const anySolo = s.channels.some((c) => c.solo);
    for (const c of s.channels) {
      const silent = c.mute || (anySolo && !c.solo) || c.n === 15 && Math.sin(t / 20) < 0;
      const base = clamp((c.fader + 30) / 36, 0, 1);
      const beat = c.section === 'drums' || c.section === 'perc' ? Math.abs(Math.sin(t * Math.PI * (s.bpm / 60))) : 0.6 + 0.4 * Math.sin(t * 1.3 + c.n);
      c.meter = silent ? 0 : clamp(base * (0.55 + 0.45 * beat) + (Math.random() - 0.5) * 0.06, 0, 1);
      c.gr = silent ? 0 : clamp(c.meter * (c.section === 'bass' ? 8 : 4), 0, 12);
      c.aiRecent = (this.aiTouched.get(c.n) ?? 0) > now() - 30_000;
    }
    s.master.lufsS = -16 + Math.sin(t / 7) * 0.8 + (Math.random() - 0.5) * 0.3;
    s.master.lufsI = s.master.lufsI * 0.999 + s.master.lufsS * 0.001;
    s.master.truePeak = clamp(-1.6 + Math.random() * 0.4, -3, -1);
    s.master.limiterGr = clamp(1.5 + Math.random() * 1.2, 0, 4);
    const frame: MeterFrame = { type: 'meters', ch: s.channels.map((c) => c.meter), gr: s.channels.map((c) => c.gr), master: { ...s.master } };
    for (const fn of this.listeners) fn(frame);
  }

  /** Stand-in for the real Claude loop: small bounded moves on controls nobody holds. */
  private claudeTick() {
    const s = this.state;

    if (!this.audio.connected && now() - this.lastCut > 14_000 && Math.random() < 0.6) {
      const options = s.cams.filter((c) => c.connected && c.id !== s.liveCam && !c.error);
      const next = options.length ? pick(options) : null;
      if (next) s.liveCam = next.id;
      this.lastCut = now();
      if (next) this.feed({ kind: 'DIRECTOR', text: `Cut to ${next.num} · ${next.name}.`, why: pick(['Phrase ended on the downbeat; held the last shot 14 s.', 'Solo detected on this player.', 'Vocal came back in after the break.']) , confidence: 'likely' });
      if (next) this.state.thinking = { text: `Holding ${next.num} through this phrase, then looking for the next solo.`, heard: pick(['groove locked', 'vocal phrase', 'keys solo']), confidence: 'likely' };
    } else if (!this.audio.connected) {
      const free = s.channels.filter((c) => !c.held && !c.mute && !this.state.held.includes(`ch${c.n}.fader`));
      if (free.length) {
        const c = pick(free);
        const before = c.fader;
        const delta = Math.random() < 0.5 ? -0.5 : 0.5;
        c.fader = Math.round((c.fader + delta) * 10) / 10;
        this.aiTouched.set(c.n, now());
        this.feed(
          { kind: 'MIX', text: `${c.name} ${delta > 0 ? '+' : '−'}0.5 dB.`, why: 'Listener: “sitting a little ' + (delta > 0 ? 'low' : 'forward') + ' in the chorus.”', confidence: 'likely' },
          () => { if (!c.held) c.fader = before; },
        );
      }
    }
    s.song = Math.random() < 0.15 ? pick(SONGS) : s.song;
    this.refreshProcs();
    this.push();
  }

  apply(a: ClientAction) {
    const s = this.state;
    if (a.type === 'control') {
      const cmd = controlToEngine(a.id, a.value);
      if (cmd) this.audio.command(cmd);
    }
    const forwarded = this.audio.forward(a);
    switch (a.type) {
      case 'take': {
        const cam = s.cams.find((c) => c.id === a.cam);
        if (!cam) return;
        s.liveCam = cam.id;
        this.lastCut = now();
        this.director.manualCut();
        this.feed({ kind: 'YOURS', text: `You cut to ${cam.num} · ${cam.name}.`, why: 'Claude keeps directing from the shot you picked.' });
        break;
      }
      case 'fader': {
        const c = s.channels[a.ch - 1];
        if (!c) return;
        if (!forwarded) c.fader = clamp(Math.round(a.db * 10) / 10, -60, 10);
        this.hold(`ch${a.ch}.fader`, a.ch);
        break;
      }
      case 'mute':
      case 'solo': {
        const c = s.channels[a.ch - 1];
        if (!c) return;
        if (!forwarded) c[a.type] = a.on;
        this.hold(`ch${a.ch}.${a.type}`, a.ch);
        break;
      }
      case 'control': {
        s.controls[a.id] = a.value;
        const m = /^ch(\d+)\./.exec(a.id);
        this.hold(a.id, m ? Number(m[1]) : undefined);
        break;
      }
      case 'vmode':
        s.vmode = a.mode;
        s.vmodeHeld = a.mode !== 'auto';
        if (s.vmodeHeld) this.hold('vmode');
        break;
      case 'undo': {
        const fn = this.undo.get(a.feedId);
        if (!fn) return;
        fn();
        this.undo.delete(a.feedId);
        const item = s.feed.find((f) => f.id === a.feedId);
        if (item) item.undoable = false;
        this.feed({ kind: 'YOURS', text: `Undid: ${item?.text ?? 'change'}` });
        break;
      }
      case 'destination':
        s.destinations[a.p] = a.on;
        break;
      case 'golive':
        void this.golive.start(a.privacy);
        break;
      case 'end':
        s.slate = 'Thanks for watching';
        this.feed({ kind: 'SHOW', text: 'Ending: thanks-for-watching slate, then the stream stops in 30 s.' });
        setTimeout(() => {
          void this.golive.end().then(async () => {
            const showId = this.log.end();
            if (!showId) return;
            this.feed({ kind: 'SHOW', text: 'Show over. Claude is reviewing it to improve the next one…' });
            this.push();
            const r = await reviewShow(showId);
            this.director.playbook = loadPlaybook().director;
            this.feed({ kind: 'SHOW', text: r.message });
            this.push();
          });
        }, 30_000);
        break;
      case 'slate':
        s.slate = a.slate;
        break;
      case 'pan':
      case 'eq':
      case 'comp':
      case 'send':
        this.hold(`ch${a.ch}.${a.type}`, a.ch);
        break;
    }
    this.refreshProcs();
    this.push();
  }
}

/** Map a UI control id to an audio-engine command (null = UI-only for now). */
export function controlToEngine(id: string, value: number | string): Record<string, unknown> | null {
  const v = Number(value);
  let m = /^ch(\d+)\.eq\.(\d+)\.(gain|freq|q)$/.exec(id);
  if (m) return { type: 'eq', ch: Number(m[1]), band: Number(m[2]) - 1, [m[3] === 'freq' ? 'f' : m[3]]: v };
  m = /^ch(\d+)\.comp\.(thresh|ratio|attack|release)$/.exec(id);
  if (m) return { type: 'comp', ch: Number(m[1]), [m[2]]: v };
  m = /^ch(\d+)\.fx\.(plate|delay4)$/.exec(id);
  if (m) return { type: 'send', ch: Number(m[1]), fx: m[2] === 'plate' ? 'plate' : 'delay', db: v };
  // Easy macros (0–100): one knob drives the matching send or compressor amount.
  m = /^ch(\d+)\.fx\.(verb|delay|comp)$/.exec(id);
  if (m) {
    const ch = Number(m[1]);
    if (m[2] === 'verb') return { type: 'send', ch, fx: 'plate', db: v <= 0 ? null : -40 + v * 0.4 };
    if (m[2] === 'delay') return { type: 'send', ch, fx: 'delay', db: v <= 0 ? null : -40 + v * 0.4 };
    return { type: 'comp', ch, thresh: -6 - v * 0.3, ratio: 1.5 + v * 0.045 };
  }
  return null;
}

/** Map any held control id to the mixer's coarse ids (ch9.eq.2.gain -> ch9.eq, ch9.fx.verb -> ch9.send). */
export function normalizeHold(id: string): string {
  const m = /^ch(\d+)\.(\w+)(?:\.(\w+))?/.exec(id);
  if (!m) return id;
  const [, n, kind, sub] = m;
  if (kind === 'fx') return sub === 'comp' ? `ch${n}.comp` : `ch${n}.send`;
  if (kind === 'eq' || kind === 'comp' || kind === 'send') return `ch${n}.${kind}`;
  return `ch${n}.${kind}`;
}
