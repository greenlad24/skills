// Static demo data for the Go Live screen. Replaced by server data once the
// show server, YouTube API and director playbook exist.
// Never put a location of any kind in any string here.

import type { Platform } from '@vibenation/shared';

export type CheckLevel = 'ok' | 'warn' | 'error';

export interface PreflightCheck {
  title: string;
  detail: string;
  meta: string;
  level: CheckLevel;
}

export const PREFLIGHT: PreflightCheck[] = [
  { title: 'Mixer audio link', detail: '16 channels from the mixer, raw preamp tap, 48 kHz', meta: '22 Mbps · 0 drops', level: 'ok' },
  { title: 'Preamp headroom', detail: 'Loudest peaks during soundcheck', meta: '−9 dBFS', level: 'ok' },
  { title: 'Cameras', detail: '5 phones connected in landscape, framed and focused', meta: '5 / 5', level: 'ok' },
  { title: 'White balance & exposure', detail: 'Locked per camera for this stream', meta: '4300 K · 1/100', level: 'ok' },
  { title: 'Camera power', detail: 'CAM 4 at 18% — plug it in. Claude will favour CAM 1 for drums if it drops.', meta: 'CAM 4 18%', level: 'warn' },
  { title: 'Audio / video sync', detail: 'Each phone lined up to the mix', meta: '±8 ms', level: 'ok' },
  { title: 'Mix loaded', detail: 'Base mix + 6 shows of learning', meta: '−16 LUFS', level: 'ok' },
  { title: 'YouTube', detail: 'Connected to @MusicLiveLove, private test stream healthy', meta: '9.0 Mbps', level: 'ok' },
  { title: 'Title, description & thumbnail', detail: 'Written from tonight’s line-up and a live camera frame; attached when you go live', meta: 'ready', level: 'ok' },
];

export interface DestinationInfo {
  p: Platform;
  name: string;
  acct: string;
  format: string;
  rate: string;
  note: string;
  kind: 'oauth' | 'key';
}

export const DESTINATIONS: DestinationInfo[] = [
  { p: 'YT', name: 'YouTube', acct: '@MusicLiveLove', format: '16:9 · 1080p60', rate: '9 Mbps', note: 'Title, description and thumbnail written by Claude.', kind: 'oauth' },
  { p: 'TW', name: 'Twitch', acct: 'musicliveLove', format: '16:9 · 1080p60', rate: '6 Mbps', note: 'Twitch caps around 6 Mbps, so it gets its own encode.', kind: 'oauth' },
  { p: 'FB', name: 'Facebook', acct: 'Music Live Love page', format: '16:9 · 1080p60', rate: '6 Mbps', note: 'Posts to your Page, not a personal profile.', kind: 'oauth' },
  { p: 'TT', name: 'TikTok', acct: 'stream key', format: '9:16 · 1080×1920', rate: '4 Mbps', note: 'Needs TikTok LIVE access (about 1,000 followers) and a stream key.', kind: 'key' },
  { p: 'IG', name: 'Instagram', acct: 'stream key', format: '9:16 · 720×1280', rate: '4 Mbps', note: 'Professional account; Instagram issues a new key for each show.', kind: 'key' },
];

export const PACKAGE = {
  title: 'LIVE: Funk & Soul Cover Band — Your Favourite Songs Re-Arranged | Real Musicians (Not AI)',
  alts: [
    'Friday Night Funk & Soul — Live Cover Band Arrangements (Not AI)',
    'Live Band Plays Your Favourite Hits in Funk & Soul | Music Live Love',
  ],
  description:
    'Live funk, soul and R&B cover band — real musicians, no AI — re-arranging the songs you love in real time. Tonight: Rhodes, sax, harmonica and a guest trombone.\n' +
    '00:00 Starting soon · song chapters added live (e.g. “Lose Control – Teddy Swims”)\n' +
    'Subscribe: youtube.com/@MusicLiveLove',
  tags: ['live cover band', 'funk cover', 'soul cover', 'not ai', 'live band arrangement', 'r&b live session'],
  thumbFrom: 'CAM 2',
  channel: '@MusicLiveLove',
  quality: '1080p60 · 9 Mbps · AAC 128k',
};

export const PLAYBOOK = {
  version: 'playbook v7 · 6 shows',
  lessons: [
    { k: 'DIRECTOR', t: 'You cut to the drums 4 times in grooves; Claude now holds the drum cam longer when the kick and snare lock in.' },
    { k: 'DIRECTOR', t: 'YouTube viewers dropped during long wide shots; wide shots now cap at 12 s unless the whole band is moving.' },
    { k: 'VERTICAL', t: 'TikTok held viewers 31% longer on close-ups than band view; Auto now favours close-ups for solos and vocals.' },
    { k: 'MIX', t: 'Harmonica was flagged harsh twice; its presence starts 1.5 dB lower tonight.' },
  ],
};

export const SCHEDULED = {
  when: 'Sat 20:30',
  title: 'Saturday Special — Live Funk & Soul Covers.',
  checksAt: '20:00',
  goesAt: '20:30',
};
