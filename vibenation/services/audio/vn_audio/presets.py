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
    peak: bool = False  # peak detection (drums/percussion); RMS otherwise


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
    rider: float | None = None  # rider offset (dB) around the channel's own running level; None = no rider
    trim: float = 0.0  # digital input trim (dB) set by soundcheck calibration; never the MR18 preamp
    floor: float | None = None  # fader floor (dB) the agent may never go below
    # Character inserts after the compressor: [(plugin key, {symbol: value})], our own analog models.
    inserts: list[tuple[str, dict]] = field(default_factory=list)
    # Stereo impulse response (file in VN_IR_DIR) after the inserts: mono in -> stereo out to the mixer's L/R.
    # Carries a measured EQ + stereo + space exactly (the MEGAMI 1:1 copies); the sends stay on the mono channel.
    conv: str | None = None


VOCAL_EQ: list[Band] = [
    ('hpf', 100, 0, 0.7),
    ('bell', 250, -3.0, 1.2),  # mud (male; female moves to 300 Hz)
    ('bell', 600, 0.0, 1.5),  # box, only if honky
    ('bell', 2000, 0.0, 1.0),  # presence, agent range ±2
    ('hshelf', 10000, 2.0, 0.7),  # air instead of a 4 kHz boost
]

STRIPS: list[Strip] = [
    # Kick, user 18 Oct 2026: "less punchy, more rounded", like Scary Pockets. Measured on the 17 Oct live test vs the
    # reference: ours had ~7 dB more 100-200 Hz knock and ~6 dB more 3-6 kHz beater click. So: no click boost (a gentle
    # cut), knock cut, low thump kept, softer top; faster/gentler compression (doesn't sharpen the attack) and a gate
    # that lets the drum ring instead of chopping it.
    # 18 Oct (MEGAMI test): roundness kept, but MEGAMI's knock kept too: no 160/285 Hz cuts
    # Kick, user's pick 18 Oct 2026: MEGAMI's kick copied 1:1 (its fast gentle compression + its measured stereo impulse
    # response) with the user's rules on top (rounder: +1.4 dB at 60 Hz, -4 dB click at 3.5 kHz, soft above 12 kHz; knock kept).
    Strip(1, 'Kick', -17.0, 0,  # -16.5 dB: the impulse response carries MEGAMI's gain; same drum balance as approved
          eq=[('bell', 60, 1.4, 1.0), ('bell', 3500, -4.0, 1.2), ('lpf', 12000, 0.0, 0.7)],
          comp=Comp(-48.4, 1.3, 0.5, 30, 4.6), no_hpf=True, conv='ch01_kick_ir_engine.wav'),
    # Snare + overheads, user's pick 18 Oct 2026 (version 3): MEGAMI's measured impulse responses with the user's rules on
    # top. Drum balance = MEGAMI's plus the rules, anchored on the kick (faders set by measurement after the switch).
    Strip(2, 'Snare', -12.3, 0,  # S3 rules: more body, softer top, +5 dB over MEGAMI's level (fader measured with its impulse response)
          eq=[('bell', 200, 2.3, 1.0), ('bell', 2500, -0.5, 1.0), ('bell', 8000, -1.0, 1.0)],
          comp=Comp(-20, 1.0, 20, 80, 0), conv='ch02_snare_ir_engine.wav'),
    Strip(3, 'Overheads', -32.0, 0,  # rules: cleaner lows, softer top, 20 dB under MEGAMI's level (-17, then 3 lower; measured with its impulse response)
          eq=[('hpf', 250, 0.0, 0.7), ('hshelf', 9000, -1.0, 0.7)], comp=Comp(-22, 1.0, 15, 120, 0), conv='ch03_overheads_ir_engine.wav'),
    Strip(4, 'Acoustic DI', -18.0, -20,  # user 17 Oct 2026: supporting channels (4, 8, 13, 15, 16) sit 4 dB back
          eq=[('hpf', 100, 0, 0.7), ('bell', 250, -2.5, 1.2), ('bell', 1000, -3.0, 4.0), ('hshelf', 12000, 1.5, 0.7)],
          comp=Comp(-20, 3, 5, 150, 2), plate=-24),
    # Version 3, user's pick 18 Oct 2026 (guitar amp, piano, vocals, synth bass): MEGAMI's channel copied 1:1 (its fitted
    # compression + measured stereo impulse response, which carries its EQ, placement and space) with the user's rules
    # on top. Levels = MEGAMI's balance plus the rules, anchored on the kick (faders set by measurement).
    Strip(5, 'Guitar amp', -8.6, 0,  # rules: low cut 110 Hz, presence at 2 kHz, +4 dB over MEGAMI (+8, then 4 lower)
          eq=[('hpf', 110, 0.0, 0.7), ('bell', 2000, 1.5, 1.0)], no_hpf=True, conv='ch05_guitar_amp_ir_engine.wav'),
    Strip(6, 'Piano L', -2.4, 0, eq=[('bell', 200, -1.0, 0.8)], no_hpf=True, floor=-13,  # rules: no 200 Hz mud, -1.5 dB
          conv='ch06_piano_l_ir_engine.wav'),
    Strip(7, 'Piano R', -4.1, 0, eq=[('bell', 200, -1.0, 0.8)], no_hpf=True, floor=-13, conv='ch07_piano_r_ir_engine.wav'),
    Strip(8, 'Guitar DI', -8.7, 0,  # V3, user's pick 18 Oct 2026: MEGAMI's acoustic guitar (piece B) copied 1:1, 4 dB back as a supporting channel
          comp=Comp(-30.0, 1.2, 0.5, 30, 2.9), no_hpf=True, conv='ch08_guitar_di_ir_engine.wav'),
    # Vocals back to the F mix (user, 18 Oct 2026: "return the vocal channels to what they were in F mix").
    # Vox C, user's pick 18 Oct 2026: "C + intimate space" (vocal tutorials: keep 200 Hz warmth, slower attack = thicker,
    # reverb behind the voice with a long pre-delay, a little short room for closeness, a quiet 1/8 echo between phrases).
    Strip(9, 'Vocal centre', -2.0, 0, eq=[('hpf', 100, 0, 0.7), ('bell', 250, -2.0, 1.2), ('bell', 600, 0.0, 1.5), ('bell', 3000, 2.0, 1.0), ('hshelf', 10000, 3.5, 0.7)],
          comp=Comp(-28, 4, 18, 150, 3), gate=Gate(-50, 12, 1.5, 120, 300), plate=-10.1, room=-13.1, delay=-16, rider=0.0),  # reverb -30% (user 18 Oct)
    Strip(10, 'Vocal piano', -2.3, -15, eq=[('hpf', 120, 0, 0.7)] + VOCAL_EQ[1:], comp=Comp(-26, 3, 12, 150, 3), gate=Gate(-50, 12, 1.5, 120, 300), plate=-13.1, rider=0.0),  # reverb -30% (user 18 Oct)
    Strip(11, 'Congas 1', -16.0, 35,
          eq=[('hpf', 90, 0, 0.7), ('bell', 350, -2.5, 1.2), ('bell', 4500, 2.5, 1.0)],
          comp=Comp(-20, 4, 15, 80, 2, peak=True), gate=Gate(-50, 12, 1.5, 120, 300), room=-18),
    Strip(12, 'Bass DI', -14.7, 0,  # user 18 Oct 2026: exactly the synth bass's mix
          eq=[('bell', 55, 1.0, 1.0), ('bell', 250, -1.0, 1.0), ('bell', 700, 2.0, 1.2), ('bell', 1000, -3.0, 1.0), ('bell', 2500, 1.5, 1.0), ('bell', 35, 1.0, 1.0)],
          no_hpf=True, conv='ch14_synth_bass_ir_engine.wav'),
    Strip(13, 'Congas 2', -20.0, 50,
          eq=[('hpf', 90, 0, 0.7), ('bell', 350, -2.5, 1.2), ('bell', 4500, 2.5, 1.0)],
          comp=Comp(-20, 4, 15, 80, 2, peak=True), room=-18),
    Strip(14, 'Synth bass', -14.7, 0,  # B2 rules on MEGAMI's copy (defined for phones), -1.2 dB vs MEGAMI (+0.3, then 1.5 lower)
          eq=[('bell', 55, 1.0, 1.0), ('bell', 250, -1.0, 1.0), ('bell', 700, 2.0, 1.2), ('bell', 1000, -3.0, 1.0), ('bell', 2500, 1.5, 1.0), ('bell', 35, 1.0, 1.0)],
          no_hpf=True, conv='ch14_synth_bass_ir_engine.wav'),
    Strip(15, 'Saxophone', -6.1, -25,
          eq=[('hpf', 120, 0, 0.7), ('bell', 400, -2.5, 1.2), ('bell', 2100, -1.5, 4.0), ('bell', 4000, -1.5, 4.0), ('hshelf', 8000, 2.0, 0.7)],
          comp=Comp(-27, 3, 10, 120, 3), plate=-10, delay=-20, rider=0.0),
    Strip(16, 'Harmonica', -14.0, 25,
          eq=[('hpf', 120, 0, 0.7), ('bell', 250, 1.0, 1.0), ('bell', 1200, -2.0, 1.5), ('bell', 3500, -3.0, 1.5), ('lpf', 9000, 0, 0.7)],
          comp=Comp(-18, 3, 20, 150, 2), room=-12, rider=0.0),
]

# Stream master: light glue, gentle equal-loudness EQ, true-peak limiter.
# Tuned 17 Oct 2026 by A/B on the same passage: the old top end measured ~8 dB dark (air -24.6 vs ~-19).
# No mid cuts: they took the piano's body away (user, 17 Oct 2026: "lacking the piano").
MASTER_EQ: list[Band] = [('hpf', 30, 0, 0.7), ('lshelf', 90, 5.3, 0.6), ('bell', 220, -1.3, 1.0), ('bell', 450, -2.3, 1.1),
                         ('bell', 1500, 1.9, 0.9), ('bell', 3000, -0.4, 1.0), ('hshelf', 5000, 4.9, 0.7), ('bell', 11000, -2.7, 0.9)]
# "Live matched to F" (user's pick 18 Oct 2026): F's master plus the curve that took the 17 Oct live recording to F's
# long-term tone, fitted to 8 bands (within 1.6 dB of the matched sample). The tone keeper holds it there all night.

# Tone keeper: F's long-term energy share per band (dB of total), measured on the approved F mix. The engine compares
# the master's last 3 minutes of music with this and nudges one master EQ band per region, slowly (user: "consistently
# matched to F the whole show"). Bands: (name, lo Hz, hi Hz, F target dB, MASTER_EQ index it steers).
TONE_TARGET = [('sub', 20, 60, -8.8, 1), ('low', 60, 250, -3.3, 1), ('lowmid', 250, 800, -6.1, 3),
               ('mid', 800, 2500, -9.5, 4), ('pres', 2500, 6000, -14.8, 5), ('air', 6000, 16000, -18.4, 7)]
# Bleed expander (user's pick 18 Oct 2026: "expander, gentle" on Vox C, Vox P and Congas 1): -12 dB between phrases,
# 1.5 ms attack, 120 ms hold, 300 ms release. The threshold is learned live per channel from its own levels: 35% of
# the way from the bleed level up to the singing level (90th percentile), so it holds whatever the preamp gain.
EXPANDER_CH = (9, 10, 11)
FX_DUCK_DB = 3.0  # plate + echo dip while the lead vocal sings (user 18 Oct: ducking essential, but the reverb stays audible at all times)
TONE_RANGE_DB = 2.0      # the keeper moves a band at most this far from MASTER_EQ
TONE_STEP_DB = 0.1       # per update (every 30 s): 0.2 dB a minute, unnoticeable
TONE_DEADBAND_DB = 1.0
MASTER_COMP = Comp(-14, 2, 30, 200, 0)
TARGET_LUFS = -16.0
VOCALS = {9, 10}  # lead + second vocal: never pulled down by the band offset
# The keeper only moves what masks a voice (keys, guitars, horns, percussion). Drums and bass stay
# where the band put them (user: drums prominent, more synth bass).
OFFSET_EXEMPT = VOCALS | {1, 2, 3, 12, 14}
TARGET_LAR = 2.0  # lead vocal over the band, dB (user, 17 Oct 2026: +5 was too much; sit the singer in the band like the reference)
CEILING_DBTP = -2.0  # YouTube's AAC re-encode added ~1 dB: -1 reached +0.1 dBTP on the 17 Oct test
# Drum balance as each drum's share of the whole mix (post-fader power while that drum plays, dB),
# measured from the meters on the user's approved mix (17 Oct 2026). Soundcheck sets the drum
# faders to these once; they don't travel during the show.
DRUM_SHARE = {1: -10.7, 2: -9.5, 3: -56.7}  # snare +5 dB (S3), overheads -17 dB (user 18 Oct 2026)

# Shared effect returns (100% wet).
FX = {
    'plate': {'decay': 1.8, 'predelay': 80, 'low_cut': 300, 'high_cut': 5000, 'return_db': -6.0},  # intimate space, darker so it sits under the voice (user 18 Oct)
    'room': {'decay': 0.6, 'predelay': 5, 'size': 12, 'in_high_cut': 8000, 'return_db': -6.0},
    'delay': {'note': 0.5, 'feedback': 0.3, 'hpf': 400, 'lpf': 6000, 'return_db': -6.0},
}


# ---- Character inserts (VibeNation's own analog-modelled plugins) ----
VN = 'https://vibenation.app/lv2/'
INSERT_URI = {
    'deesser': VN + 'vn_deesser', 'opto': VN + 'vn_opto', 'fet': VN + 'vn_fet', 'pultec': VN + 'vn_pultec',
}
_VOX = [('deesser', {'freq': 6500, 'sensitivity': 50, 'range': 6}), ('opto', {'peak_reduction': 20, 'mix': 60, 'sc_high': 2, 'colour': 30})]
_ROLE_INSERTS: dict[int, list[tuple[str, dict]]] = {
    1: [('fet', {'ratio': 1, 'attack': 300, 'release': 200, 'mix': 30, 'colour': 40})],
    2: [('fet', {'ratio': 1, 'attack': 300, 'release': 150, 'mix': 30, 'colour': 40})],
    4: [('opto', {'peak_reduction': 15, 'mix': 50, 'colour': 20})],
    9: _VOX,
    10: _VOX,
    15: [('deesser', {'freq': 4500, 'sensitivity': 45, 'range': 4}), ('opto', {'peak_reduction': 20, 'mix': 60, 'colour': 30})],
    16: [('deesser', {'freq': 3500, 'sensitivity': 55, 'range': 6}), ('opto', {'peak_reduction': 25, 'mix': 70, 'colour': 20})],
}
for _s in STRIPS:
    _s.inserts = [(k, dict(v)) for k, v in _ROLE_INSERTS.get(_s.n, [])]

# Master colour + glue + tape (before the x42 true-peak limiter).
MASTER_CONSOLE = {'drive': 0, 'colour': 40, 'crosstalk': 0}
MAX_DRIVE_DB = 12.0  # leveller drive ceiling: more only pushes weak live inputs into the limiter
MASTER_BUS = {'threshold': -10, 'ratio': 0, 'attack': 10, 'release': 4, 'sc_hpf': 90, 'makeup': 0, 'mix': 80}  # parallel 'New York' glue: density without losing punch
MASTER_TAPE = {'speed': 1, 'drive': 0, 'saturation': 30, 'bias': 50, 'bump': 40, 'wow': 0, 'flutter': 0, 'mix': 50}

# ---- The user's saved balance (18 Oct 2026, 23:27: "save the current balance - that should be the balance from now on
# with no changes to it"). Faders, pans and EQ exactly as set by hand on the demo; nothing automatic moves them. ----
BALANCE_LOCKED = True  # no automatic balance moves: no vocal riders, no lead/backing or solo offsets, no band offset, no AI fader moves
MIX_LOCKED = True  # user, 19 Oct 2026: "no auto changes to the mix": no tone keeper, no auto level, no soundcheck re-trims, no AI mixer.
# Still on (user's own picks): auto-mute of idle channels, the vocal expander, reverb ducking, and the emergency guards
# (feedback notch, clipping trim, dead-signal alert).
BAND_OFFSET_FIXED = 2.0
SAVED_BALANCE: dict[int, dict] = {
    1: {'fader': -3.5, 'pan': 0.0, 'eq': [('lshelf', 37.0, -4.0, 1.0), ('bell', 3775.0, -3.0, 1.2), ('lpf', 6490.0, 0.0, 0.7), ('bell', 160.0, 3.5, 1.0)]},
    2: {'fader': -4.5, 'pan': 0.0, 'eq': [('bell', 200.0, 2.3, 1.0), ('bell', 2500.0, -0.5, 1.0), ('bell', 8000.0, -1.0, 1.0)]},
    3: {'fader': -19.0, 'pan': 0.0, 'eq': [('hpf', 250.0, 0.0, 0.7), ('hshelf', 9000.0, -1.0, 0.7)]},
    4: {'fader': -18.0, 'pan': -20.0, 'eq': [('hpf', 100.0, 0.0, 0.7), ('bell', 250.0, -2.5, 1.2), ('bell', 1000.0, -3.0, 4.0), ('hshelf', 12000.0, 1.5, 0.7)]},
    5: {'fader': -5.3, 'pan': 35.0, 'eq': [('hpf', 110.0, 0.0, 0.7), ('bell', 2000.0, 1.5, 1.0)]},
    6: {'fader': -8.9, 'pan': -100.0, 'eq': [('lshelf', 100.0, -12.0, 0.8), ('bell', 2727.0, -3.5, 7.3), ('bell', 1000.0, 0.0, 1.0)]},
    7: {'fader': -1.0, 'pan': 100.0, 'eq': [('lshelf', 163.0, -12.0, 0.8), ('bell', 2727.0, -3.0, 2.8), ('bell', 227.0, -1.0, 1.0)]},
    8: {'fader': -13.5, 'pan': -45.0, 'eq': []},
    9: {'fader': 1.0, 'pan': 0.0, 'eq': [('hpf', 100.0, 0.0, 0.7), ('bell', 250.0, -2.0, 1.2), ('bell', 600.0, 0.0, 1.5), ('bell', 2742.0, 1.5, 1.0), ('hshelf', 10000.0, 3.5, 0.7)]},
    10: {'fader': 1.0, 'pan': -15.0, 'eq': [('hpf', 120.0, 0.0, 0.7), ('bell', 250.0, -3.0, 1.2), ('bell', 600.0, 0.0, 1.5), ('bell', 2000.0, 0.0, 1.0), ('hshelf', 10000.0, 2.0, 0.7)]},
    11: {'fader': 1.0, 'pan': 35.0, 'eq': [('hpf', 90.0, 0.0, 0.7), ('bell', 350.0, -2.5, 1.2), ('bell', 4500.0, 2.5, 1.0)]},
    12: {'fader': -4.0, 'pan': 0.0, 'eq': [('bell', 55.0, 1.0, 1.0), ('bell', 250.0, -1.0, 1.0), ('bell', 700.0, 2.0, 1.2), ('bell', 1000.0, -3.0, 1.0), ('bell', 2500.0, 1.5, 1.0), ('bell', 35.0, 1.0, 1.0)]},
    13: {'fader': -20.0, 'pan': 50.0, 'eq': [('hpf', 90.0, 0.0, 0.7), ('bell', 350.0, -2.5, 1.2), ('bell', 4500.0, 2.5, 1.0)]},
    14: {'fader': -4.0, 'pan': 0.0, 'eq': [('bell', 51.0, -2.5, 1.0), ('bell', 200.0, -3.0, 0.4), ('bell', 424.0, 2.0, 1.2), ('bell', 916.0, -5.5, 1.0), ('bell', 2114.0, -2.5, 1.0), ('lshelf', 71.0, -12.0, 1.0)]},
    15: {'fader': -14.2, 'pan': -25.0, 'eq': [('hpf', 120.0, 0.0, 0.7), ('bell', 400.0, -2.5, 1.2), ('bell', 2100.0, -1.5, 4.0), ('bell', 4000.0, -1.5, 4.0), ('hshelf', 8000.0, 2.0, 0.7)]},
    16: {'fader': -17.5, 'pan': 25.0, 'eq': [('hpf', 120.0, 0.0, 0.7), ('bell', 250.0, 1.0, 1.0), ('bell', 1200.0, -2.0, 1.5), ('bell', 3500.0, -3.0, 1.5), ('lpf', 9000.0, 0.0, 0.7)]},
}
for _s in STRIPS:
    _b = SAVED_BALANCE.get(_s.n)
    if _b:
        _s.fader, _s.pan, _s.eq = _b['fader'], _b['pan'], list(_b['eq'])
