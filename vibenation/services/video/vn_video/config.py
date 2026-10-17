"""Encoder profiles and service settings (all overridable from the environment)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def even(n: float) -> int:
    n = int(round(n))
    return n - (n % 2)


@dataclass
class Profile:
    name: str
    w: int                 # 16:9 program size
    h: int
    fps: int
    vw: int                # 9:16 vertical size
    vh: int
    vfps: int
    encoder: str           # 'nvenc' | 'x264'
    kbps: dict[str, int] = field(default_factory=dict)  # per output profile
    threads: int = 1       # videoconvert/videoscale worker threads

    @property
    def strip_h(self) -> int:   # band view: title strip (22 % of the height, as in Show.tsx)
        return even(self.vh * 0.22)

    @property
    def wide_h(self) -> int:    # band view: 16:9 wide shot
        return even(self.vw * 9 / 16)

    @property
    def bclose_h(self) -> int:  # band view: close-up fills the rest
        return self.vh - self.strip_h - self.wide_h


PROFILES = {
    # Show server (RTX 4000 Ada): NVENC, 1080p60 program, two 16:9 encodes + vertical.
    'gpu': Profile('gpu', 1920, 1080, 60, 720, 1280, 30, 'nvenc',
                   {'16x9-9M': 9000, '16x9-6M': 6000, '9x16': 4000}, threads=4),
    # Dedicated-CPU show server (CPU-Optimized c-16, no GPU): x264 veryfast, 1080p30 program.
    # Measured need ~12-13 cores with 3 phones; 30 fps halves compositing vs 60.
    'cpu': Profile('cpu', 1920, 1080, 30, 720, 1280, 30, 'x264',
                   {'16x9-9M': 9000, '16x9-6M': 6000, '9x16': 4000}, threads=4),
    # Build server smoke test: x264 ultrafast, tiny sizes.
    'cpu-test': Profile('cpu-test', 640, 360, 30, 360, 640, 30, 'x264',
                        {'16x9-9M': 1500, '16x9-6M': 1000, '9x16': 800}),
}

OUTPUT_PROFILES = ('16x9-9M', '16x9-6M', '9x16')
SLATES = ('Starting soon', 'Break', 'Thanks for watching')


@dataclass
class Settings:
    profile: Profile
    host: str = os.environ.get('VN_VIDEO_HOST', '127.0.0.1')
    port: int = int(os.environ.get('VN_VIDEO_PORT', '8092'))
    audio: str = os.environ.get('VN_VIDEO_AUDIO', 'jack')          # jack | test | silence
    jack_ports: tuple[str, str] = tuple(os.environ.get('VN_VIDEO_JACK_PORTS', 'effect_1042:outL,effect_1042:outR').split(','))  # type: ignore[assignment]
    audio_delay_ms: int = int(os.environ.get('VN_VIDEO_AUDIO_DELAY_MS', '0'))
    # Slate music: 16-bit 48 kHz stereo WAVs (normalised to about -20 LUFS); VN_SLATE_MUSIC_DB trims them.
    slate_music_dir: str = os.environ.get('VN_SLATE_MUSIC_DIR', '/home/vibe/vibenation-media/slate-music')
    slate_music_db: float = float(os.environ.get('VN_SLATE_MUSIC_DB', '0'))
    livekit_url: str = os.environ.get('LIVEKIT_URL', 'ws://127.0.0.1:7880')
    livekit_key: str = os.environ.get('LIVEKIT_API_KEY', '')
    livekit_secret: str = os.environ.get('LIVEKIT_API_SECRET', '')
    room: str = os.environ.get('VN_VIDEO_ROOM', 'show')
    gop_s: float = 2.0


def load() -> Settings:
    name = os.environ.get('VN_VIDEO_PROFILE', 'cpu-test')
    if name not in PROFILES:
        raise SystemExit(f'VN_VIDEO_PROFILE must be one of {list(PROFILES)}')
    return Settings(profile=PROFILES[name])
