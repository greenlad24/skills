#!/usr/bin/env python3
"""Offline simulation of the AutoDirector — no OBS or audio needed.

Run it to watch how the director would cut a show:

    python3 demo.py live
    python3 demo.py podcast

Each demo feeds a scripted timeline (who is making sound, and when) into the
exact same directing code the OBS plugin runs, and prints every cut with its
timestamp and the director's reasoning.
"""

import random
import sys

from autodirector.core import (
    LevelVAD, LiveConfig, LiveDirector,
    PodcastConfig, PodcastDirector, SpeakerCfg,
    apply_crosstalk_gate, NEG_INF_DB,
)

TICK = 0.05


def _print_cut(t, cut):
    print(f"  {t:7.2f}s  CUT -> {cut.scene:<18} ({cut.reason})")


def demo_live():
    print("LIVE SHOW demo — song: intro / verse / solo / verse / outro")
    cfg = LiveConfig(
        singer_scene="Singer",
        instrumental_scenes=["Wide", "Guitar", "Drums", "Keys"],
        cut_interval_s=6.0,
        cutaway_every_s=20.0,
    )
    director = LiveDirector(cfg, rng=random.Random(7))
    vad = LevelVAD(margin_db=8.0, attack_s=0.25, release_s=2.3)

    # (duration_s, vocal mic level dB) — pauses between sung lines included.
    song = [
        (8, -55),                      # instrumental intro
        (4, -18), (1, -55), (4, -17), (1.2, -55), (5, -16),   # verse 1
        (14, -55),                     # guitar solo
        (4, -17), (0.8, -55), (4, -18), (1, -55), (26, -15),  # verse 2 + big held chorus
        (10, -55),                     # outro
    ]
    t = 0.0
    for dur, level in song:
        end = t + dur
        while t < end:
            vocal = vad.update(t, level + random.Random(int(t * 20)).uniform(-2, 2))
            cut = director.update(t, vocal)
            if cut:
                _print_cut(t, cut)
            t += TICK
    print(f"song length {t:.0f}s — done.\n")


def demo_podcast():
    print("PODCAST demo — Anna hosts, Ben guests")
    cfg = PodcastConfig(
        speakers=[
            SpeakerCfg("Anna", "Anna Medium", "Anna Close"),
            SpeakerCfg("Ben", "Ben Medium", "Ben Close"),
        ],
        wide_scene="Two Shot",
    )
    director = PodcastDirector(cfg)
    vads = [LevelVAD(margin_db=8, attack_s=0.15, release_s=0.35)
            for _ in range(2)]

    QUIET = -60.0
    # (duration_s, anna dB, ben dB)
    convo = [
        (6, -18, QUIET),               # Anna opens
        (0.5, -18, -20),               # Ben: "mm-hm" (backchannel, no cut)
        (8, -18, QUIET),               # Anna keeps going ... 14s -> close-up
        (12, -18, QUIET),
        (1.5, QUIET, QUIET),           # Anna pauses...
        (7, QUIET, -19),               # ...Ben takes the floor
        (3, -17, -19),                 # Anna interrupts, sustained overlap
        (5, -17, QUIET),               # Anna has it
        # rapid back-and-forth -> wide shot
        (2, QUIET, -18), (2, -18, QUIET), (2, QUIET, -18), (2, -18, QUIET),
        (12, QUIET, -18),              # Ben settles in and holds forth
        (4, QUIET, QUIET),             # beat of silence
        (8, -10, QUIET),               # Anna comes back HOT (emphasis)
    ]
    t = 0.0
    for dur, a, b in convo:
        end = t + dur
        while t < end:
            levels = [a, b]
            talking = [vads[i].update(t, levels[i]) for i in range(2)]
            talking = apply_crosstalk_gate(talking, levels)
            cut = director.update(t, talking, levels)
            if cut:
                _print_cut(t, cut)
            t += TICK
    print(f"conversation length {t:.0f}s — done.\n")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("live", "both"):
        demo_live()
    if which in ("podcast", "both"):
        demo_podcast()
