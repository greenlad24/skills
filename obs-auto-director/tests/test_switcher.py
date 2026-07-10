import math
import random

from autodirector.core import (EvidenceSwitcher, SwitcherConfig,
                               min_shot_factor)

TICK = 0.05


def make_switcher(**overrides):
    kwargs = dict(
        dwell_s={"VOCAL": 0.5, "INSTRUMENTAL": 2.5},
        cooldown_s=3.0,
    )
    kwargs.update(overrides)
    return EvidenceSwitcher(SwitcherConfig(**kwargs))


def drive(sw, segments, start_t=0.0):
    """segments: (duration_s, {state: conf}). Returns [(t, SwitchEvent)]."""
    t = start_t
    events = []
    for dur, conf in segments:
        end = t + dur
        while t < end:
            ev = sw.update(t, conf)
            if ev:
                events.append((t, ev))
            t += TICK
    return events, t


class TestBasicSwitching:
    def test_adopts_initial_state(self):
        sw = make_switcher()
        events, _ = drive(sw, [(2, {"INSTRUMENTAL": 0.9, "VOCAL": 0.1})])
        assert events and events[0][1].state == "INSTRUMENTAL"
        assert events[0][1].kind == "initial"

    def test_switches_after_dwell_not_before(self):
        sw = make_switcher()
        events, t = drive(sw, [(5, {"INSTRUMENTAL": 0.9, "VOCAL": 0.1})])
        events2, _ = drive(sw, [(4, {"INSTRUMENTAL": 0.1, "VOCAL": 0.9})],
                           start_t=t)
        assert events2, "must eventually switch to VOCAL"
        t_sw, ev = events2[0]
        assert ev.state == "VOCAL"
        # EMA crossing (~0.3s) + 0.5s dwell => roughly 0.7-1.2s after change
        assert 0.6 <= (t_sw - 5.0) <= 1.3

    def test_ambiguity_holds_current_state(self):
        # Two moderately confident states: hold the current shot.
        sw = make_switcher()
        drive(sw, [(3, {"INSTRUMENTAL": 0.9, "VOCAL": 0.1})])
        events, _ = drive(sw, [(20, {"INSTRUMENTAL": 0.55, "VOCAL": 0.55})],
                          start_t=3.0)
        assert events == [], "ambiguous evidence must not cause a switch"
        assert sw.state == "INSTRUMENTAL"

    def test_brief_flicker_does_not_switch(self):
        sw = make_switcher(dwell_s={"VOCAL": 0.5, "INSTRUMENTAL": 2.5})
        drive(sw, [(5, {"INSTRUMENTAL": 0.9, "VOCAL": 0.1})])
        # 0.3s vocal blip (shorter than EMA+dwell), then back
        events, _ = drive(sw, [(0.3, {"INSTRUMENTAL": 0.1, "VOCAL": 0.9}),
                               (5, {"INSTRUMENTAL": 0.9, "VOCAL": 0.1})],
                          start_t=5.0)
        assert all(ev.state != "VOCAL" for _, ev in events)

    def test_nan_and_inf_are_harmless(self):
        sw = make_switcher()
        drive(sw, [(2, {"A": 0.9, "B": 0.1})],)
        events, _ = drive(sw, [(2, {"A": float("nan"), "B": float("inf")}),
                               (2, {"A": 0.9, "B": float("-inf")})],
                          start_t=2.0)
        assert sw.state is not None  # no crash, state remains sane


class TestRelaxedRules:
    def test_cooldown_blocks_quick_second_switch(self):
        sw = make_switcher(dwell_s={"A": 0.3, "B": 0.3, "C": 0.3},
                           cooldown_s=3.0)
        drive(sw, [(2, {"A": 0.9, "B": 0.1, "C": 0.1})])
        ev_b, t = drive(sw, [(1.2, {"A": 0.1, "B": 0.9, "C": 0.1})],
                        start_t=2.0)
        assert ev_b and ev_b[0][1].state == "B"
        t_b = ev_b[0][0]
        # C becomes dominant immediately after -> must wait out the cooldown
        ev_c, _ = drive(sw, [(5, {"A": 0.1, "B": 0.15, "C": 0.75})],
                        start_t=t)
        assert ev_c, "C must eventually win"
        assert (ev_c[0][0] - t_b) >= 3.0 - TICK, "cooldown must be respected"

    def test_return_penalty_slows_ping_pong(self):
        dwells = {"A": 1.0, "B": 1.0}
        sw = make_switcher(dwell_s=dwells, cooldown_s=0.5,
                           return_penalty=1.5, return_window_s=20.0)
        drive(sw, [(3, {"A": 0.9, "B": 0.1})])
        ev_b, t = drive(sw, [(4, {"A": 0.1, "B": 0.9})], start_t=3.0)
        t_to_b = ev_b[0][0] - 3.0
        # now return to A: same signal shape, but dwell is 1.5x
        ev_a, _ = drive(sw, [(6, {"A": 0.9, "B": 0.1})], start_t=t)
        t_back_to_a = ev_a[0][0] - t
        assert t_back_to_a > t_to_b + 0.3, \
            f"returning must cost extra dwell ({t_back_to_a:.2f} vs {t_to_b:.2f})"

    def test_priority_bypasses_cooldown(self):
        sw = make_switcher(dwell_s={"A": 0.5, "B": 0.5},
                           cooldown_s=8.0, priority_conf=0.85,
                           priority_sustain_s=1.5)
        drive(sw, [(10, {"A": 0.9, "B": 0.05})])  # outlive initial cooldown
        ev_b, t = drive(sw, [(2, {"A": 0.05, "B": 0.9})], start_t=10.0)
        assert ev_b
        t_b = ev_b[0][0]
        # immediately after, A comes back overwhelming (e.g. vocals in)
        ev_a, _ = drive(sw, [(4, {"A": 0.97, "B": 0.03})], start_t=t)
        assert ev_a, "overwhelming evidence must not wait out an 8s cooldown"
        t_a, ev = ev_a[0]
        assert ev.priority and ev.kind == "priority"
        assert (t_a - t_b) < 8.0

    def test_commit_confidence_and_min_shot_factor(self):
        assert min_shot_factor(1.0) == 1.0
        assert abs(min_shot_factor(0.7) - 1.3) < 1e-9
        assert min_shot_factor(0.0) == 2.0
        sw = make_switcher(dwell_s={"A": 0.3, "B": 0.3})
        drive(sw, [(2, {"A": 0.9, "B": 0.1})])
        ev, _ = drive(sw, [(3, {"A": 0.1, "B": 0.7})], start_t=2.0)
        assert ev and 0.5 <= ev[0][1].commit_conf <= 0.75

    def test_calibration_multiplier_stretches_dwell(self):
        fast = make_switcher(dwell_s={"A": 1.0, "B": 1.0})
        slow = make_switcher(dwell_s={"A": 1.0, "B": 1.0},
                             dwell_multiplier=1.5)
        for sw in (fast, slow):
            drive(sw, [(3, {"A": 0.9, "B": 0.1})])
        ev_f, _ = drive(fast, [(5, {"A": 0.1, "B": 0.9})], start_t=3.0)
        ev_s, _ = drive(slow, [(5, {"A": 0.1, "B": 0.9})], start_t=3.0)
        assert ev_s[0][0] - ev_f[0][0] > 0.3


class TestInvariants:
    """Property-style invariants under adversarial and random inputs."""

    def test_rate_cap_under_adversarial_square_wave(self):
        sw = make_switcher(dwell_s={"A": 0.5, "B": 0.5}, cooldown_s=3.0,
                           max_switches_per_min=10)
        events = []
        t = 0.0
        while t < 180.0:
            phase = int(t / 2.0) % 2  # perfect 2s square wave at conf 0.95
            conf = {"A": 0.95 if phase == 0 else 0.05,
                    "B": 0.05 if phase == 0 else 0.95}
            ev = sw.update(t, conf)
            if ev:
                events.append(t)
            t += TICK
        # sliding 60s windows: never more than the cap
        for i, t0 in enumerate(events):
            in_window = [x for x in events if t0 <= x <= t0 + 60.0]
            assert len(in_window) <= 10, \
                f"rate cap violated: {len(in_window)} switches in 60s"

    def test_non_priority_switches_respect_cooldown_under_fuzz(self):
        rng = random.Random(1234)
        sw = make_switcher(dwell_s={"A": 0.4, "B": 0.4, "C": 0.4},
                           cooldown_s=3.0)
        conf = {"A": 0.5, "B": 0.5, "C": 0.5}
        events = []
        t = 0.0
        while t < 300.0:
            for k in conf:  # random walk, clamped
                conf[k] = min(1.0, max(0.0, conf[k] + rng.uniform(-0.15, 0.15)))
            ev = sw.update(t, dict(conf))
            if ev:
                events.append((t, ev))
            t += TICK
        times = [t for t, ev in events if not ev.priority]
        for a, b in zip(times, times[1:]):
            assert b - a >= 3.0 - TICK, "cooldown violated under fuzz"

    def test_dt_invariance(self):
        # The same confidence timeline at 20/50/100ms ticks must produce
        # switch decisions within a small tolerance of each other.
        def run_at(step):
            sw = make_switcher(dwell_s={"A": 0.5, "B": 2.0})
            switch_ts = []
            t = 0.0
            while t < 30.0:
                conf = ({"A": 0.9, "B": 0.1} if (t < 10 or t >= 20)
                        else {"A": 0.1, "B": 0.9})
                ev = sw.update(t, conf)
                if ev and ev.kind != "initial":
                    switch_ts.append(t)
                t += step
            return switch_ts

        runs = [run_at(s) for s in (0.02, 0.05, 0.10)]
        assert all(len(r) == len(runs[0]) for r in runs), \
            f"different switch counts across tick rates: {[len(r) for r in runs]}"
        for r in runs[1:]:
            for a, b in zip(runs[0], r):
                assert abs(a - b) <= 0.2, f"dt-variance too high: {a} vs {b}"

    def test_gap_does_not_grant_free_dwell(self):
        sw = make_switcher(dwell_s={"A": 0.5, "B": 2.5})
        drive(sw, [(3, {"A": 0.9, "B": 0.1})])
        # B looks strong for one tick, then a 10s stall, then one more tick.
        sw.update(3.0, {"A": 0.1, "B": 0.9})
        ev = sw.update(13.0, {"A": 0.1, "B": 0.9})
        assert ev is None, "a stall must not count as accumulated dwell"
