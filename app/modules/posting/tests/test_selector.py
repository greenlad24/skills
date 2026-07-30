"""Selection tests: weighted sampling + distinct hooks + bandit (spec §5B.7/§5B.8)."""

from __future__ import annotations

import random
from types import SimpleNamespace

from app.modules.posting import selector


def _tpl(score):
    return SimpleNamespace(id=id(object()), operator_win_score=score, name=f"t{score}")


def test_pick_weighted_distinct_returns_distinct():
    pool = [_tpl(0.5) for _ in range(4)]
    picked = selector.pick_weighted(pool, 4, distinct=True, rng=random.Random(1))
    assert len({id(p) for p in picked}) == 4


def test_pick_weighted_samples_proportionally_to_weight():
    # Two arms, heavy vs light; over many draws the heavy arm wins the majority.
    heavy = _tpl(3.0)
    light = _tpl(0.1)
    rng = random.Random(42)
    counts = {id(heavy): 0, id(light): 0}
    for _ in range(2000):
        pick = selector.pick_weighted([heavy, light], 1, distinct=False, rng=rng)[0]
        counts[id(pick)] += 1
    assert counts[id(heavy)] > counts[id(light)]
    # heavy should dominate clearly (well over half)
    assert counts[id(heavy)] > 1200


def test_pick_hooks_thompson_prefers_best_arm():
    best = SimpleNamespace(id=1, operator_win_score=0.95, samples=50, name="best")
    worst = SimpleNamespace(id=2, operator_win_score=0.05, samples=50, name="worst")
    rng = random.Random(7)
    wins = 0
    for _ in range(200):
        top = selector.pick_hooks([best, worst], 1, strategy="thompson", rng=rng)[0]
        wins += top is best
    assert wins > 130  # empirically-best arm selected the majority of the time


def test_pick_hooks_ucb1_explores_untried_first():
    tried = SimpleNamespace(id=1, operator_win_score=0.9, samples=10, name="tried")
    untried = SimpleNamespace(id=2, operator_win_score=None, samples=0, name="untried")
    top = selector.pick_hooks([tried, untried], 1, strategy="ucb1")[0]
    assert top is untried  # infinite UCB forces exploration of the untried arm
