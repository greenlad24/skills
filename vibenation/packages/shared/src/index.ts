// Shared constants and types for the VibeNation web app and server.

/** Semantic colours. On air is blue, errors are red only, warnings amber, Claude lilac.
 *  Brand ember is never used for state. */
export const tokens = {
  bgCanvas: '#0F0C0A',
  bgPanel: '#18130F',
  bgRaised: '#231C17',
  line: '#3B3029',
  textPrimary: '#F5EEE6',
  textSecondary: '#ADA195',
  textTertiary: '#7D7268',
  onAir: '#3D8BFF',
  onAirFill: '#1F66E0',
  warn: '#FFB224',
  error: '#FF5A52',
  errorFill: '#D7261E',
  ai: '#B9A6FF',
  okDot: '#ADA195',
  brandEmber: '#FF8A3D',
} as const;

export type Section = 'drums' | 'perc' | 'gtr' | 'keys' | 'vox' | 'bass' | 'horn';

export interface ChannelDef {
  n: number;
  name: string;
  short: string;
  section: Section;
  /** Starting server fader in dB (band's test-rig balance where known). */
  fader: number;
  /** User rule: never add a high-pass filter on this channel. */
  noHpf?: boolean;
}

/** The band's 16 MR18 channels (USB Analog tap). Roles on 11, 15, 16 can switch live. */
export const CHANNELS: ChannelDef[] = [
  { n: 1, name: 'Kick', short: 'Kick', section: 'drums', fader: -10, noHpf: true },
  { n: 2, name: 'Snare', short: 'Snare', section: 'drums', fader: -14.9 },
  { n: 3, name: 'Overheads', short: 'OH', section: 'drums', fader: -23.4 },
  { n: 4, name: 'Acoustic DI', short: 'Ac DI', section: 'gtr', fader: -14 },
  { n: 5, name: 'Guitar amp', short: 'Gtr amp', section: 'gtr', fader: -12 },
  { n: 6, name: 'Piano L', short: 'Piano L', section: 'keys', fader: -10 },
  { n: 7, name: 'Piano R', short: 'Piano R', section: 'keys', fader: -10 },
  { n: 8, name: 'Guitar DI', short: 'Gtr DI', section: 'gtr', fader: -13 },
  { n: 9, name: 'Vocal centre', short: 'Vox C', section: 'vox', fader: -2 },
  { n: 10, name: 'Vocal piano', short: 'Vox P', section: 'vox', fader: -2.3 },
  { n: 11, name: 'Congas 1', short: 'Congas', section: 'perc', fader: -16 },
  { n: 12, name: 'Bass DI', short: 'Bass DI', section: 'bass', fader: -10, noHpf: true },
  { n: 13, name: 'Congas 2', short: 'Congas 2', section: 'perc', fader: -16 },
  { n: 14, name: 'Synth bass', short: 'Synth B', section: 'bass', fader: -9.8, noHpf: true },
  { n: 15, name: 'Saxophone', short: 'Sax', section: 'horn', fader: -2.1 },
  { n: 16, name: 'Harmonica', short: 'Harm', section: 'horn', fader: -10 },
];

export const LOUDNESS_TARGET = { lufsI: -16, truePeakDb: -1 } as const;

export interface HealthResponse {
  ok: true;
  app: 'VibeNation';
  version: string;
  uptimeS: number;
}

/** GET /api/apps — phone camera apps on the Apps screen. android is null until the APK is built. */
export interface AppsInfo {
  android: { version: string | null; sizeMB: number; builtAt: string; url: string; expiresInS: number } | null;
}
export * from './state.js';
