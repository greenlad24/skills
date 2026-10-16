"""Starting broadcast chain per channel.

Values come from reports/Live mix chain YouTube sources.md (YouTube-verified where
possible) and the band's own rules: no high-pass on kick or either bass, piano
never below -13 dB, vocals on top, harmonica softened. These are the *starting*
point; the mixer loop and post-show learning move them within bounds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# EQ band: (type, freq Hz, gain dB, Q). Types: bell, hpf, lpf, lshelf, hshelf, off.
Band = tuple[str, float, float, float]


@dataclass
class Comp:
    thresh: float = -20.0  # dBFS
    ratio: float = 3.0
    attack: float = 12.0  # ms
    release: float = 150.0  # ms
    makeup: float = 0.0  # dB
    knee: float = -6.0  # dB (soft)
    mix: float = 1.0  # parallel: 1 = fully compressed


@dataclass
class Gate:
    thresh: float = -30.0  # dBFS
    range: float = 12.0  # dB of reduction when closed
    attack: float = 0.5
    hold: float = 45.0
    release: float = 10.0


@dataclass
class Strip:
    n: int
    name: str
    fader: float  # dB
    pan: float = 0.0  # -100 (L) .. +100 (R)
    eq: list[Band] = field(default_factory=list)
    comp: Comp | None = None
    gate: Gate | None = None
    # Send levels in dB (None = off) to the shared effects.
    plate: float | None = None
    room: float | None = None
    delay: float | None = None
    no_hpf: bool = False
    trim: float = 0.0  # digital input trim (dB) set by soundcheck calibration; never the MR18 preamp
    floor: float | None = None  # fader floor (dB) the agent may never go below


VOCAL_EQ: list[Band] = [
    ('hpf', 100, 0, 0.7),
    ('bell', 250, -3.0, 1.2),  # mud (male; female moves to 300 Hz)
    ('bell', 600, 0.0, 1.5),  # box, only if honky
    ('bell', 2000, 0.0, 1.0),  # presence, agent range ±2
    ('hshelf', 10000, 2.0, 0.7),  # air instead of a 4 kHz boost
]

STRIPS: list[Strip] = [
    Strip(1, 'Kick', -10.0, 0,
          eq=[('bell', 60, 2.0, 1.0), ('bell', 285, -3.0, 1.5), ('hshelf', 16000, 2.0, 0.7)],
          comp=Comp(-18, 4.5, 28, 85, 2), gate=Gate(-34, 12, 0.5, 45, 10), room=-22, no_hpf=True),
    Strip(2, 'Snare', -14.9, 0,
          eq=[('hpf', 100, 0, 0.7), ('bell', 200, 0, 1.0), ('bell', 420, -3.0, 2.0), ('bell', 2500, 2.0, 1.0), ('bell', 8000, 2.0, 1.0)],
          comp=Comp(-20, 4, 15, 50, 3), room=-15),
    Strip(3, 'Overheads', -23.4, 0,
          eq=[('hpf', 180, 0, 0.7)], comp=Comp(-22, 4, 15, 120, 1)),
    Strip(4, 'Acoustic DI', -14.0, -20,
          eq=[('hpf', 100, 0, 0.7), ('bell', 250, -2.5, 1.2), ('bell', 1000, -3.0, 4.0), ('hshelf', 12000, 1.5, 0.7)],
          comp=Comp(-20, 3, 5, 150, 2), plate=-24),
    Strip(5, 'Guitar amp', -12.0, -30,
          eq=[('hpf', 100, 0, 0.7), ('bell', 350, -2.0, 1.2), ('bell', 4000, -2.0, 4.0), ('lpf', 12000, 0, 0.7)],
          comp=Comp(-20, 4, 10, 100, 2, mix=0.5), room=-20),
    Strip(6, 'Piano L', -10.0, -60,
          eq=[('hpf', 35, 0, 0.7), ('bell', 200, 1.0, 0.8), ('bell', 500, -2.0, 2.0), ('bell', 1500, -1.5, 1.0), ('bell', 3000, -2.0, 1.1), ('bell', 4500, -1.5, 0.8)],
          comp=Comp(-22, 2, 30, 200, 1), plate=-14, floor=-13),
    Strip(7, 'Piano R', -10.0, 60,
          eq=[('hpf', 35, 0, 0.7), ('bell', 200, 1.0, 0.8), ('bell', 500, -2.0, 2.0), ('bell', 1500, -1.5, 1.0), ('bell', 3000, -2.0, 1.1), ('bell', 4500, -1.5, 0.8)],
          comp=Comp(-22, 2, 30, 200, 1), plate=-14, floor=-13),
    Strip(8, 'Guitar DI', -13.0, 30,
          eq=[('hpf', 120, 0, 0.7), ('bell', 4000, -2.0, 4.0), ('lpf', 9000, 0, 0.7)],
          comp=Comp(-20, 4, 10, 100, 2, mix=0.5), room=-20),
    Strip(9, 'Vocal centre', -2.0, 0, eq=list(VOCAL_EQ), comp=Comp(-22, 3, 12, 150, 3), plate=-8, delay=-18),
    Strip(10, 'Vocal piano', -2.3, -15, eq=[('hpf', 120, 0, 0.7)] + VOCAL_EQ[1:], comp=Comp(-22, 3, 12, 150, 3), plate=-10),
    Strip(11, 'Congas 1', -16.0, 35,
          eq=[('hpf', 90, 0, 0.7), ('bell', 350, -2.5, 1.2), ('bell', 4500, 2.5, 1.0)],
          comp=Comp(-20, 4, 15, 80, 2), room=-18),
    Strip(12, 'Bass DI', -10.0, 0,
          eq=[('bell', 250, -2.0, 1.5), ('bell', 800, 2.0, 1.0), ('bell', 2500, 1.5, 1.0), ('lpf', 6000, 0, 0.7)],
          comp=Comp(-24, 4, 15, 150, 5), no_hpf=True),
    Strip(13, 'Congas 2', -16.0, 50,
          eq=[('hpf', 90, 0, 0.7), ('bell', 350, -2.5, 1.2), ('bell', 4500, 2.5, 1.0)],
          comp=Comp(-20, 4, 15, 80, 2), room=-18),
    Strip(14, 'Synth bass', -9.8, 0,
          eq=[('bell', 55, 1.5, 1.0), ('bell', 300, -3.0, 1.0), ('bell', 1500, 1.5, 1.0)],
          comp=Comp(-20, 3, 20, 150, 2), no_hpf=True),
    Strip(15, 'Saxophone', -2.1, -25,
          eq=[('hpf', 120, 0, 0.7), ('bell', 400, -2.5, 1.2), ('bell', 2100, -1.5, 4.0), ('bell', 4000, -1.5, 4.0), ('hshelf', 8000, 2.0, 0.7)],
          comp=Comp(-24, 3, 10, 120, 3), plate=-10, delay=-20),
    Strip(16, 'Harmonica', -10.0, 25,
          eq=[('hpf', 120, 0, 0.7), ('bell', 250, 1.0, 1.0), ('bell', 1200, -2.0, 1.5), ('bell', 3500, -3.0, 1.5), ('lpf', 9000, 0, 0.7)],
          comp=Comp(-18, 3, 20, 150, 2), room=-12),
]

# Stream master: light glue, gentle equal-loudness EQ, true-peak limiter.
MASTER_EQ: list[Band] = [('hpf', 20, 0, 0.7), ('lshelf', 100, 2.0, 0.7), ('bell', 800, -1.0, 0.7), ('hshelf', 10000, 1.5, 0.7)]
MASTER_COMP = Comp(-14, 2, 30, 200, 0)
TARGET_LUFS = -16.0
CEILING_DBTP = -1.0

# Shared effect returns (100% wet).
FX = {
    'plate': {'decay': 1.5, 'predelay': 40, 'low_cut': 200, 'high_cut': 8000, 'return_db': -6.0},
    'room': {'decay': 0.6, 'predelay': 5, 'size': 12, 'in_high_cut': 8000, 'return_db': -6.0},
    'delay': {'note': 0.5, 'feedback': 0.35, 'hpf': 400, 'lpf': 6000, 'return_db': -6.0},
}
