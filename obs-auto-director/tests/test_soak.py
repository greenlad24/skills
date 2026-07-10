"""Soak / cut-quality regression: long randomized shows through the
directors, asserting professional-pacing invariants (the metrics that
define 'relaxed switching').

Amended P2 (per the team review): A->B->A flicker is only a violation via
non-priority cuts — a singer genuinely resuming after a break MUST get a
priority cut back; that's directing, not flicker.
"""

import random

from autodirector.core import (LiveConfig, LiveDirector, PodcastConfig,
                               PodcastDirector, SpeakerCfg)

TICK = 0.05


def cut_metrics(cuts, duration_s):
    """cuts: [(t, Cut)] -> dict of pacing-quality metrics."""
    times = [t for t, _ in cuts]
    cpm = len(cuts) / max(duration_s, 1.0) * 60.0
    sub_min_gaps = 0
    flicker = 0
    for i in range(1, len(cuts)):
        t, c = cuts[i]
        if not c.priority and (t - times[i - 1]) < 3.0:
            sub_min_gaps += 1
    for i in range(2, len(cuts)):
        t, c = cuts[i]
        # A->B->A is flicker only when the whole exchange is non-priority;
        # a priority cut in the middle (vocals in, clean handoff) makes the
        # return a legitimate bookend, not indecision.
        if (c.scene == cuts[i - 2][1].scene
                and not c.priority and not cuts[i - 1][1].priority
                and (t - times[i - 2]) < 8.0):
            flicker += 1
    return {"cuts_per_min": cpm, "sub_min_gaps": sub_min_gaps,
            "flicker": flicker}


class TestLiveSoak:
    def test_thirty_minute_show(self):
        rng = random.Random(2024)
        d = LiveDirector(LiveConfig(
            singer_scene="Singer",
            instrumental_scenes=["Wide", "Guitar", "Drums", "Keys"],
        ), rng=random.Random(7))
        # start deep in a show (t=1e6): large timestamps must not break
        t = 1e6
        end = t + 1800.0
        cuts = []
        vocal = False
        next_flip = t
        while t < end:
            if t >= next_flip:
                vocal = not vocal
                # phrases 5-25s, instrumental sections 8-40s
                next_flip = t + (rng.uniform(5, 25) if vocal
                                 else rng.uniform(8, 40))
            cut = d.update(t, vocal)
            if cut:
                cuts.append((t, cut))
            t += TICK

        m = cut_metrics(cuts, 1800.0)
        assert 1.0 <= m["cuts_per_min"] <= 10.0, m
        assert m["sub_min_gaps"] == 0, m
        assert m["flicker"] == 0, m
        scenes = {c.scene for _, c in cuts}
        assert "Singer" in scenes
        assert len(scenes) >= 4, "should use the shot variety available"


class TestPodcastSoak:
    def test_forty_minute_conversation(self):
        rng = random.Random(99)
        d = PodcastDirector(PodcastConfig(
            speakers=[SpeakerCfg("A", "A Med", "A Close"),
                      SpeakerCfg("B", "B Med", "B Close")],
            wide_scene="Two Shot",
        ))
        t = 1e6
        end = t + 2400.0
        cuts = []
        talking = [False, False]
        next_change = t
        current = 0
        while t < end:
            if t >= next_change:
                r = rng.random()
                if r < 0.12:                     # dead air
                    talking = [False, False]
                    next_change = t + rng.uniform(0.5, 4.0)
                elif r < 0.22:                   # overlap / interjection
                    talking = [True, True]
                    next_change = t + rng.uniform(0.3, 2.5)
                else:                            # somebody holds forth
                    if rng.random() < 0.45:
                        current = 1 - current
                    talking = [current == 0, current == 1]
                    next_change = t + rng.uniform(2.0, 20.0)
            # detector jitter: 2% flicker
            eff = [x if rng.random() > 0.02 else not x for x in talking]
            levels = [-20.0 if x else -55.0 for x in eff]
            cut = d.update(t, eff, levels)
            if cut:
                cuts.append((t, cut))
            t += TICK

        m = cut_metrics(cuts, 2400.0)
        assert 0.5 <= m["cuts_per_min"] <= 10.0, m
        assert m["sub_min_gaps"] == 0, m
        assert m["flicker"] == 0, m
        scenes = [c.scene for _, c in cuts]
        assert any("Close" in s for s in scenes), \
            "long floor holds should have produced close-ups"
