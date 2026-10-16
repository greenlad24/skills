// Live show state pushed from the server to every browser over /ws,
// and the actions a browser can send back.

import type { Section } from './index.js';

export type VMode = 'auto' | 'close' | 'band';
export type Platform = 'YT' | 'TW' | 'FB' | 'TT' | 'IG';

export interface CameraState {
  id: number;
  num: string; // "CAM 2"
  name: string; // "Lead vocal"
  device: 'android' | 'iphone';
  connected: boolean;
  battery: number; // %
  charging: boolean;
  warn?: string; // amber chip text, e.g. "Battery 18%"
  error?: string; // red chip text, e.g. "Disconnected"
}

export interface ChannelState {
  n: number;
  name: string;
  short: string;
  section: Section;
  fader: number; // dB
  meter: number; // 0..1 post-fader level for display
  gr: number; // compressor gain reduction, dB (positive number)
  mute: boolean;
  solo: boolean;
  /** Held by a human for the rest of the stream (any control on this channel). */
  held: boolean;
  /** Claude touched this channel in the last 30 s. */
  aiRecent: boolean;
  role?: string; // for role-switching channels: "Congas", "Trombone", "Backing vocal"…
}

export interface MasterState {
  lufsI: number;
  lufsS: number;
  truePeak: number;
  limiterGr: number;
}

export type FeedKind = 'DIRECTOR' | 'MIX' | 'ROLE' | 'YOURS' | 'EMERGENCY' | 'SHOW';

export interface FeedItem {
  id: string;
  t: number; // epoch ms
  kind: FeedKind;
  text: string;
  why?: string;
  /** Present on reversible Claude changes. */
  undoable?: boolean;
  confidence?: 'sure' | 'likely' | 'guessing';
}

export interface ChatMessage {
  id: string;
  p: Platform;
  who: string;
  text: string;
  tag?: 'SONG REQUEST' | 'SHOUT-OUT';
  note?: string;
}

export interface ProcessRow {
  name: string;
  meta: string;
  level: 'ok' | 'ai' | 'warn' | 'error';
}

export interface StreamHealth {
  mbps: number;
  fps: number;
  cpu: number;
  dropped: number;
  viewers: number;
  likes: number;
}

export interface Thinking {
  text: string;
  heard: string;
  confidence: 'sure' | 'likely' | 'guessing';
}

export interface ShowState {
  showName: string; // user setting; placeholder "[Band Name] · Friday Session"
  onAir: boolean;
  liveSince: number | null; // epoch ms
  slate: null | 'Starting soon' | 'Break' | 'Thanks for watching';
  destinations: Record<Platform, boolean>;
  cams: CameraState[];
  liveCam: number;
  vmode: VMode;
  vmodeHeld: boolean;
  vAutoPick: 'close' | 'band';
  channels: ChannelState[];
  master: MasterState;
  song: string; // "Song 7 · second chorus"
  bpm: number;
  health: StreamHealth;
  thinking: Thinking;
  procs: ProcessRow[];
  feed: FeedItem[];
  chat: ChatMessage[];
  /** Ids of controls held by a human this stream, e.g. "ch9.fader", "fx.A.decay", "vmode". */
  held: string[];
  /** Last value of every 'control' action (EQ bands, effect knobs, presets), by id. */
  controls: Record<string, number | string>;
  demo: boolean;
}

/** Lightweight high-rate update (meters) sent between full state pushes. */
export interface MeterFrame {
  type: 'meters';
  ch: number[]; // meter 0..1 per channel
  gr: number[];
  master: MasterState;
}

export type ServerMessage = { type: 'state'; state: ShowState } | MeterFrame;

export type ClientAction =
  | { type: 'take'; cam: number }
  | { type: 'fader'; ch: number; db: number }
  | { type: 'mute'; ch: number; on: boolean }
  | { type: 'solo'; ch: number; on: boolean }
  /** Any other per-channel control (EQ band, effect macro, comp knob). Holds the control. */
  | { type: 'control'; id: string; value: number | string }
  | { type: 'vmode'; mode: VMode }
  | { type: 'undo'; feedId: string }
  | { type: 'destination'; p: Platform; on: boolean }
  | { type: 'golive' }
  | { type: 'end' }
  | { type: 'slate'; slate: ShowState['slate'] };
