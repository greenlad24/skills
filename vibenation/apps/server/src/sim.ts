// Demo show: fake cameras, meters and Claude activity so the UI can be built and
// reviewed before the real audio/video engines exist. Replaced piece by piece in
// later milestones; the held-by-you rules here are the real rules.

import { CHANNELS, type ClientAction, type FeedItem, type ShowState, type MeterFrame, type ChatMessage } from '@vibenation/shared';

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
  private aiTouched = new Map<number, number>(); // ch -> last AI touch time
  private lastCut = now();
  private undo = new Map<string, () => void>();

  constructor() {
    const t = now();
    this.state = {
      showName: '[Band Name] · Friday Session',
      onAir: true,
      liveSince: t - (72 * 60 + 48) * 1000,
      slate: null,
      destinations: { YT: true, TW: true, FB: true, TT: true, IG: true },
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
      health: { mbps: 9.0, fps: 60, cpu: 38, dropped: 0, viewers: 1240, likes: 86 },
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
    };
    this.feed({ kind: 'SHOW', text: 'Demo show running.', why: 'Fake cameras and audio until the real engines are connected.' });
    this.refreshProcs();
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
  }

  private feed(f: Omit<FeedItem, 'id' | 't'>, undo?: () => void) {
    const item: FeedItem = { ...f, id: id(), t: now(), undoable: !!undo };
    if (undo) this.undo.set(item.id, undo);
    this.state.feed = [item, ...this.state.feed].slice(0, 60);
    return item;
  }

  private hold(key: string, ch?: number) {
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
    const camWarn = s.cams.find((c) => c.warn);
    s.procs = [
      { name: 'Mixer audio link', meta: '16 ch · 48k', level: 'ok' },
      { name: 'Cameras', meta: `${s.cams.filter((c) => c.connected).length} / ${s.cams.length}`, level: 'ok' },
      { name: 'Mix engine', meta: '3.1 ms', level: 'ok' },
      { name: 'Listener (hearing)', meta: 'every 8 s', level: 'ai' },
      { name: 'Director', meta: s.vmodeHeld ? 'auto · vertical yours' : 'auto', level: 'ai' },
      { name: 'YouTube ingest', meta: `${s.health.mbps.toFixed(1)} Mbps`, level: 'ok' },
      ...(camWarn ? [{ name: `${camWarn.num} battery`, meta: `${camWarn.battery}%`, level: 'warn' as const }] : []),
    ];
  }

  private meters() {
    const t = now() / 1000;
    const s = this.state;
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
    s.health.viewers = Math.max(0, s.health.viewers + Math.round((Math.random() - 0.45) * 20));
    s.health.likes += Math.random() < 0.4 ? 1 : 0;

    if (now() - this.lastCut > 14_000 && Math.random() < 0.6) {
      const options = s.cams.filter((c) => c.connected && c.id !== s.liveCam && !c.error);
      const next = pick(options);
      s.liveCam = next.id;
      this.lastCut = now();
      this.feed({ kind: 'DIRECTOR', text: `Cut to ${next.num} · ${next.name}.`, why: pick(['Phrase ended on the downbeat; held the last shot 14 s.', 'Solo detected on this player.', 'Vocal came back in after the break.']) , confidence: 'likely' });
      this.state.thinking = { text: `Holding ${next.num} through this phrase, then looking for the next solo.`, heard: pick(['groove locked', 'vocal phrase', 'keys solo']), confidence: 'likely' };
    } else {
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
    switch (a.type) {
      case 'take': {
        const cam = s.cams.find((c) => c.id === a.cam);
        if (!cam) return;
        s.liveCam = cam.id;
        this.lastCut = now();
        this.feed({ kind: 'YOURS', text: `You cut to ${cam.num} · ${cam.name}.`, why: 'Claude keeps directing from the shot you picked.' });
        break;
      }
      case 'fader': {
        const c = s.channels[a.ch - 1];
        if (!c) return;
        c.fader = clamp(Math.round(a.db * 10) / 10, -60, 10);
        this.hold(`ch${a.ch}.fader`, a.ch);
        break;
      }
      case 'mute':
      case 'solo': {
        const c = s.channels[a.ch - 1];
        if (!c) return;
        c[a.type] = a.on;
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
        s.onAir = true;
        s.liveSince = now();
        s.held = [];
        s.controls = {};
        for (const c of s.channels) c.held = false;
        this.feed({ kind: 'SHOW', text: 'Went live.', why: 'All holds cleared; Claude starts from the learned mix.' });
        break;
      case 'end':
        s.onAir = false;
        s.slate = 'Thanks for watching';
        this.feed({ kind: 'SHOW', text: 'Show ended.' });
        break;
      case 'slate':
        s.slate = a.slate;
        break;
    }
    this.refreshProcs();
    this.push();
  }
}
