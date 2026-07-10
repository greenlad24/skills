from obs_auto_director import (
    LevelVAD, PacingEngine, apply_crosstalk_gate, NEG_INF_DB,
)

TICK = 0.05


def run_vad(vad, segments, on_state=None):
    """segments: list of (duration_s, level_db). Returns list of (t, active)."""
    t = 0.0
    out = []
    for dur, level in segments:
        end = t + dur
        while t < end:
            out.append((t, vad.update(t, level)))
            t += TICK
    return out


def first_time(states, want, after=0.0):
    for t, active in states:
        if t >= after and active == want:
            return t
    return None


class TestLevelVAD:
    def test_activates_after_attack_and_releases_after_release(self):
        vad = LevelVAD(margin_db=8, attack_s=0.25, release_s=2.0)
        states = run_vad(vad, [(2, -55), (5, -18), (5, -55)])
        t_on = first_time(states, True)
        assert t_on is not None and 2.2 <= t_on <= 2.5
        t_off = first_time(states, False, after=t_on)
        assert t_off is not None and 8.9 <= t_off <= 9.3

    def test_short_blip_does_not_activate(self):
        vad = LevelVAD(margin_db=8, attack_s=0.25, release_s=2.0)
        states = run_vad(vad, [(2, -55), (0.1, -18), (3, -55)])
        assert first_time(states, True) is None

    def test_pauses_shorter_than_release_do_not_deactivate(self):
        vad = LevelVAD(margin_db=8, attack_s=0.2, release_s=2.0)
        states = run_vad(vad, [(1, -55), (3, -18), (1, -55), (3, -18)])
        t_on = first_time(states, True)
        assert first_time(states, False, after=t_on) is None

    def test_noise_floor_adapts_downward_quickly(self):
        vad = LevelVAD(margin_db=8, attack_s=0.2, release_s=1.0,
                       floor_db=-30.0)
        run_vad(vad, [(3, -70)])
        assert vad.floor_db < -60

    def test_handles_neg_inf_and_nan(self):
        vad = LevelVAD()
        assert vad.update(0.0, float("-inf")) is False
        assert vad.update(0.05, float("nan")) is False
        assert vad.floor_db >= NEG_INF_DB


class TestPacingEngine:
    def test_min_shot_blocks_early_cut(self):
        pace = PacingEngine(min_shot_s=3.0)
        assert pace.request(0.0, "A", "start") is not None
        assert pace.request(1.0, "B", "too soon") is None
        assert pace.request(3.1, "B", "ok now") is not None

    def test_priority_overrides_min_shot(self):
        pace = PacingEngine(min_shot_s=3.0)
        pace.request(0.0, "A", "start")
        cut = pace.request(0.5, "B", "vocals!", priority=True)
        assert cut is not None and cut.scene == "B"

    def test_never_recuts_same_scene(self):
        pace = PacingEngine(min_shot_s=1.0)
        pace.request(0.0, "A", "start")
        assert pace.request(10.0, "A", "same") is None

    def test_sync_tracks_manual_cuts(self):
        pace = PacingEngine(min_shot_s=1.0)
        pace.request(0.0, "A", "start")
        pace.sync("B")  # user cut manually
        assert pace.request(5.0, "B", "same as manual") is None
        assert pace.request(5.0, "A", "back") is not None


class TestCrosstalkGate:
    def test_quiet_bleed_suppressed(self):
        talking = [True, True]
        levels = [-15.0, -30.0]
        assert apply_crosstalk_gate(talking, levels) == [True, False]

    def test_genuine_overlap_kept(self):
        talking = [True, True]
        levels = [-15.0, -18.0]
        assert apply_crosstalk_gate(talking, levels) == [True, True]

    def test_single_speaker_untouched(self):
        assert apply_crosstalk_gate([False, True], [-15.0, -60.0]) == \
            [False, True]
