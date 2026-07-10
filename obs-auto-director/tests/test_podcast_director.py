from obs_auto_director import PodcastConfig, PodcastDirector, SpeakerCfg

TICK = 0.05
QUIET = None  # marker: not talking


def make_director(**overrides):
    kwargs = dict(
        speakers=[
            SpeakerCfg("Anna", "Anna Medium", "Anna Close"),
            SpeakerCfg("Ben", "Ben Medium", "Ben Close"),
        ],
        wide_scene="Two Shot",
        min_shot_s=2.6,
        pause_tolerance_s=1.2,
        backchannel_max_s=0.9,
        interrupt_commit_s=1.6,
        closeup_after_s=10.0,
        closeup_grace_s=3.0,
        closeup_max_s=25.0,
    )
    kwargs.update(overrides)
    return PodcastDirector(PodcastConfig(**kwargs))


def run(director, segments, start_t=0.0, levels_for=None):
    """segments: (duration_s, anna_talking, ben_talking). Returns [(t, Cut)]."""
    t = start_t
    cuts = []
    for seg in segments:
        dur, a, b = seg[0], seg[1], seg[2]
        end = t + dur
        while t < end:
            talking = [a, b]
            levels = levels_for(t, talking) if levels_for else None
            cut = director.update(t, talking, levels)
            if cut:
                cuts.append((t, cut))
            t += TICK
    return cuts, t


class TestFloorLogic:
    def test_first_speaker_gets_medium(self):
        d = make_director()
        cuts, _ = run(d, [(5, True, False)])
        assert cuts and cuts[0][1].scene == "Anna Medium"
        assert cuts[0][1].priority

    def test_backchannel_does_not_steal_floor(self):
        d = make_director()
        # Ben says "mm-hm" for 0.5s while Anna talks — no cut to Ben.
        cuts, _ = run(d, [(4, True, False), (0.5, True, True),
                          (4, True, False)])
        assert all("Ben" not in c.scene for _, c in cuts)

    def test_pause_handoff_cuts_to_new_speaker(self):
        d = make_director()
        cuts, _ = run(d, [(5, True, False),      # Anna talks
                          (1.5, False, False),   # pause > tolerance
                          (5, False, True)])     # Ben talks
        ben = [(t, c) for t, c in cuts if c.scene == "Ben Medium"]
        assert ben
        t, c = ben[0]
        # cut lands once Ben's utterance outlasts the backchannel filter
        assert 7.3 <= t <= 8.0 and c.priority

    def test_short_pause_keeps_floor(self):
        d = make_director()
        cuts, _ = run(d, [(5, True, False),
                          (0.8, False, False),   # pause < tolerance
                          (5, True, False)])
        assert all(c.scene.startswith("Anna") for _, c in cuts)

    def test_sustained_interruption_steals_floor(self):
        d = make_director()
        cuts, _ = run(d, [(5, True, False),
                          (3, True, True),       # Ben talks over Anna
                          (4, False, True)])
        ben = [t for t, c in cuts if c.scene == "Ben Medium"]
        assert ben
        # steals after interrupt_commit_s (1.6s) of sustained overlap
        assert 6.5 <= ben[0] <= 7.2

    def test_no_instant_steal_back_after_interruption(self):
        # Ben's utterance started before Anna's interruption; once Anna has
        # the floor, Ben's ongoing speech must not instantly steal it back.
        d = make_director(wide_scene="")
        cuts, _ = run(d, [(5, False, True),      # Ben talks
                          (3, True, True),       # Anna interrupts (overlap)
                          (4, True, False)])     # Anna alone
        scenes = [c.scene for _, c in cuts]
        assert scenes.count("Ben Medium") == 1
        assert scenes[-1].startswith("Anna")

    def test_no_cut_when_nobody_has_spoken(self):
        d = make_director()
        cuts, _ = run(d, [(5, False, False)])
        assert cuts == []


class TestShotSelection:
    def test_closeup_after_holding_floor(self):
        d = make_director(closeup_after_s=10.0)
        cuts, _ = run(d, [(20, True, False)])
        close = [t for t, c in cuts if c.scene == "Anna Close"]
        assert close
        # no micro-pause in continuous speech -> fires after grace deadline
        assert 12.8 <= close[0] <= 13.4

    def test_closeup_cuts_on_micro_pause_when_available(self):
        d = make_director(closeup_after_s=10.0, closeup_grace_s=3.0)
        cuts, _ = run(d, [(10.5, True, False),
                          (0.6, False, False),   # a natural beat
                          (8, True, False)])
        close = [t for t, c in cuts if c.scene == "Anna Close"]
        assert close and 10.4 <= close[0] <= 11.2

    def test_closeup_relaxes_back_to_medium(self):
        d = make_director(closeup_after_s=5.0, closeup_grace_s=2.0,
                          closeup_max_s=10.0)
        cuts, _ = run(d, [(30, True, False)])
        scenes = [c.scene for _, c in cuts]
        i_close = scenes.index("Anna Close")
        assert "Anna Medium" in scenes[i_close + 1:]

    def test_floor_change_resets_to_medium(self):
        d = make_director(closeup_after_s=5.0, closeup_grace_s=1.0)
        cuts, _ = run(d, [(9, True, False),       # Anna -> close-up
                          (1.5, False, False),
                          (5, False, True)])      # handoff to Ben
        ben = [c.scene for _, c in cuts if "Ben" in c.scene]
        assert ben and ben[0] == "Ben Medium"

    def test_emphasis_pushes_in_early(self):
        d = make_director(closeup_after_s=30.0, emphasis_db=6.0,
                          emphasis_hold_s=1.0)

        def levels_for(t, talking):
            # Anna at a steady -20 dB, then jumps to -10 dB at t=8.
            return [-10.0 if t >= 8.0 else -20.0, -60.0]

        cuts, _ = run(d, [(16, True, False)], levels_for=levels_for)
        close = [t for t, c in cuts if c.scene == "Anna Close"]
        assert close and 8.9 <= close[0] <= 9.6


class TestRapidExchange:
    def test_ping_pong_goes_wide_then_settles(self):
        d = make_director()
        cuts, _ = run(d, [
            (6, True, False),
            (2.5, False, True), (2.5, True, False),
            (2.5, False, True), (2.5, True, False),
            (12, True, False),        # Anna settles in
        ])
        scenes = [c.scene for _, c in cuts]
        assert "Two Shot" in scenes
        i_wide = scenes.index("Two Shot")
        assert "Anna Medium" in scenes[i_wide + 1:], \
            "should settle back on the holder after the exchange"
        # Once settled, stale floor changes must not flip us straight
        # back to the wide shot.
        i_settle = i_wide + 1 + scenes[i_wide + 1:].index("Anna Medium")
        assert "Two Shot" not in scenes[i_settle + 1:]

    def test_no_wide_scene_configured_no_wide_cut(self):
        d = make_director(wide_scene="")
        cuts, _ = run(d, [
            (6, True, False),
            (2.5, False, True), (2.5, True, False),
            (2.5, False, True), (2.5, True, False),
        ])
        assert all(c.scene != "Two Shot" for _, c in cuts)


class TestPacing:
    def test_min_shot_prevents_flicker(self):
        d = make_director(min_shot_s=2.6, wide_scene="")
        cuts, _ = run(d, [
            (5, True, False), (2, False, True), (2, True, False),
            (2, False, True), (2, True, False), (5, False, True),
        ])
        times = [t for t, c in cuts if not c.priority]
        gaps = [b - a for a, b in zip(times, times[1:])]
        assert all(g >= 1.0 for g in gaps)  # sanity: no per-tick flicker
