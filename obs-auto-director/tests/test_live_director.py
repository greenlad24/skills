import random

from obs_auto_director import LiveConfig, LiveDirector

TICK = 0.05


def make_director(**overrides):
    kwargs = dict(
        singer_scene="Singer",
        instrumental_scenes=["Wide", "Guitar", "Drums"],
        min_shot_s=3.0,
        post_vocal_hold_s=1.6,
        cut_interval_s=6.0,
        cut_jitter=0.0,
        cutaway_every_s=0.0,  # off unless a test enables it
    )
    kwargs.update(overrides)
    return LiveDirector(LiveConfig(**kwargs), rng=random.Random(42))


def run(director, segments, start_t=0.0):
    """segments: list of (duration_s, vocal_active). Returns [(t, Cut)]."""
    t = start_t
    cuts = []
    for dur, vocal in segments:
        end = t + dur
        while t < end:
            cut = director.update(t, vocal)
            if cut:
                cuts.append((t, cut))
            t += TICK
    return cuts, t


class TestLiveDirector:
    def test_vocal_onset_cuts_to_singer_immediately(self):
        d = make_director()
        cuts, _ = run(d, [(10, False), (5, True)])
        singer_cuts = [(t, c) for t, c in cuts if c.scene == "Singer"]
        assert singer_cuts
        t, c = singer_cuts[0]
        assert abs(t - 10.0) < 0.1 and c.priority

    def test_vocal_onset_overrides_min_shot(self):
        d = make_director(min_shot_s=5.0)
        # Instrumental cut lands ~t=0; vocals hit at t=1 — must not wait 5s.
        cuts, _ = run(d, [(1, False), (3, True)])
        singer = [t for t, c in cuts if c.scene == "Singer"]
        assert singer and singer[0] < 1.2

    def test_holds_singer_through_entire_vocal(self):
        d = make_director()
        cuts, _ = run(d, [(1, False), (30, True)])
        after_onset = [c for t, c in cuts if t > 1.5]
        assert all(c.scene == "Singer" for c in after_onset)

    def test_lingers_after_vocals_before_first_instrumental(self):
        d = make_director(post_vocal_hold_s=1.6)
        cuts, _ = run(d, [(1, False), (10, True), (10, False)])
        instrumental = [(t, c) for t, c in cuts
                        if t > 11 and c.scene != "Singer"]
        assert instrumental
        t_first, c_first = instrumental[0]
        assert t_first >= 11 + 1.6 - TICK
        # First instrumental shot after vocals prefers the wide (list[0]).
        assert c_first.scene == "Wide"

    def test_instrumental_rotation_paces_and_never_repeats(self):
        d = make_director(cut_interval_s=6.0)
        cuts, _ = run(d, [(60, False)])
        scenes = [c.scene for _, c in cuts]
        assert len(scenes) >= 8
        assert all(a != b for a, b in zip(scenes, scenes[1:]))
        times = [t for t, _ in cuts]
        gaps = [b - a for a, b in zip(times, times[1:])]
        assert all(5.9 <= g <= 6.2 for g in gaps)

    def test_jitter_varies_shot_lengths(self):
        d = make_director(cut_interval_s=6.0, cut_jitter=0.35)
        cuts, _ = run(d, [(120, False)])
        times = [t for t, _ in cuts]
        gaps = [round(b - a, 1) for a, b in zip(times, times[1:])]
        assert len(set(gaps)) > 3  # human-feeling variety, not a metronome

    def test_cutaway_during_long_vocal_and_return(self):
        d = make_director(cutaway_every_s=10.0, cutaway_len_s=3.0)
        cuts, _ = run(d, [(1, False), (40, True)])
        cutaways = [(t, c) for t, c in cuts
                    if c.scene != "Singer" and t > 1]
        returns = [(t, c) for t, c in cuts
                   if c.scene == "Singer" and t > 2]
        assert cutaways, "expected a cutaway during a 40s vocal"
        t_away, _ = cutaways[0]
        t_back = min(t for t, _ in returns if t > t_away)
        assert 2.9 <= (t_back - t_away) <= 3.3

    def test_no_instrumental_scenes_stays_put(self):
        d = make_director(instrumental_scenes=[])
        cuts, _ = run(d, [(5, True), (20, False)])
        assert all(c.scene == "Singer" for _, c in cuts)

    def test_energy_pacing_speeds_up_loud_sections(self):
        cfg = dict(cut_interval_s=8.0, cut_jitter=0.0)
        quiet = make_director(**cfg)
        loud = make_director(**cfg)

        def run_energy(d, level):
            # settle the EMA at -30, then play at `level`
            t, cuts = 0.0, []
            while t < 60:
                cut = d.update(t, False, energy_db=-30.0)
                t += TICK
            while t < 120:
                cut = d.update(t, False, energy_db=level)
                if cut:
                    cuts.append(t)
                t += TICK
            return cuts

        gaps = {}
        for name, d, lvl in (("quiet", quiet, -45.0), ("loud", loud, -12.0)):
            times = run_energy(d, lvl)
            gaps[name] = min(b - a for a, b in zip(times, times[1:]))
        assert gaps["loud"] < gaps["quiet"]
