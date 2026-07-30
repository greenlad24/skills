"""Template selection for variant generation (spec §5B.7 softmax + §5B.8 bandit).

`pick_weighted` samples templates proportional to their `operator_win_score`
(softmax over weights, temperature T) so hooks/formulas/pacings that actually
earned engagement — and especially sales — for *this operator* get chosen more
often, while underperformers fade but never vanish (FLOOR keeps exploration).

Optional multi-armed bandit over HookTemplates (Thompson / UCB1) is a drop-in
replacement selected by `HOOK_SELECTOR`. Bandit state is kept lightweight and
derived from `operator_win_score` history so it works over the canonical model
without new columns; a production build could persist per-arm alpha/beta.

Everything here is pure given an injected RNG, so selection is deterministically
testable (acceptance §5E statistical test).
"""

from __future__ import annotations

import math
import random
from typing import Any, Sequence

from app.modules.posting.scoring import BASELINE, FLOOR, softmax_weights


def _weight_of(tpl: Any) -> float:
    w = getattr(tpl, "operator_win_score", None)
    if w is None:
        w = BASELINE
    return max(float(w), FLOOR)


def pick_weighted(
    templates: Sequence[Any],
    n: int,
    *,
    temperature: float = 0.7,
    distinct: bool = True,
    rng: random.Random | None = None,
) -> list[Any]:
    """Sample `n` templates ∝ softmax(operator_win_score).

    `distinct=True` samples WITHOUT replacement (used for hooks: every variant in a
    cohort must use a distinct HookTemplate — spec §5B.2 hard rule). If fewer than
    `n` distinct templates exist, returns as many distinct ones as possible.
    """
    rng = rng or random.Random()
    pool = list(templates)
    if not pool:
        return []
    chosen: list[Any] = []
    limit = min(n, len(pool)) if distinct else n
    for _ in range(limit):
        weights = [_weight_of(t) for t in pool]
        probs = softmax_weights(weights, temperature=temperature)
        pick = _sample_index(probs, rng)
        chosen.append(pool[pick])
        if distinct:
            pool.pop(pick)
            if not pool:
                break
    return chosen


def _sample_index(probs: list[float], rng: random.Random) -> int:
    """Inverse-CDF sample of an index given a probability vector."""
    r = rng.random()
    cumulative = 0.0
    for i, p in enumerate(probs):
        cumulative += p
        if r <= cumulative:
            return i
    return len(probs) - 1


# --------------------------------------------------------------------------- #
# Optional bandit over hooks (spec §5B.8). HOOK_SELECTOR=softmax|thompson|ucb1
# --------------------------------------------------------------------------- #
def _arm_stats(tpl: Any) -> tuple[float, int]:
    """(mean_reward, n_trials) for a hook arm.

    Derived from the canonical fields: `operator_win_score` is the running mean
    reward, `win_score` (or a `samples`-like attr when present) approximates trials.
    Cold-start defaults keep unseen arms optimistic so they get explored.
    """
    mean = getattr(tpl, "operator_win_score", None)
    mean = BASELINE if mean is None else float(mean)
    n = getattr(tpl, "samples", None)
    if n is None:
        # No sample counter on the canonical model; treat presence of a real score
        # as ~1 observation, otherwise 0 (fully unexplored).
        n = 1 if getattr(tpl, "operator_win_score", None) is not None else 0
    return mean, int(n)


def pick_thompson(
    templates: Sequence[Any], n: int, *, rng: random.Random | None = None
) -> list[Any]:
    """Thompson sampling (Beta-Bernoulli) over hook arms — spec §5B.8.

    success ~ mean reward (score above operator median, binarized to a rate),
    trials ~ observation count. Sample θ ~ Beta(α, β) per arm, pick the top `n`
    distinct arms by sampled θ.
    """
    rng = rng or random.Random()
    scored: list[tuple[float, Any]] = []
    for tpl in templates:
        mean, trials = _arm_stats(tpl)
        alpha = 1.0 + mean * trials          # pseudo-successes (+1 prior)
        beta = 1.0 + (1.0 - mean) * trials   # pseudo-failures  (+1 prior)
        theta = rng.betavariate(max(alpha, 1e-3), max(beta, 1e-3))
        scored.append((theta, tpl))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [tpl for _, tpl in scored[: min(n, len(scored))]]


def pick_ucb1(
    templates: Sequence[Any], n: int, *, c: float = 1.4
) -> list[Any]:
    """UCB1 selection — spec §5B.8. argmax(mean_i + c*sqrt(ln(total)/n_i))."""
    stats = [(_arm_stats(t), t) for t in templates]
    total = sum(max(n_i, 0) for (_, n_i), _ in stats) or 1
    ranked: list[tuple[float, Any]] = []
    for (mean, n_i), tpl in stats:
        if n_i <= 0:
            ucb = float("inf")  # force-explore an untried arm first
        else:
            ucb = mean + c * math.sqrt(math.log(total) / n_i)
        ranked.append((ucb, tpl))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [tpl for _, tpl in ranked[: min(n, len(ranked))]]


def pick_hooks(
    templates: Sequence[Any],
    n: int,
    *,
    strategy: str = "softmax",
    temperature: float = 0.7,
    rng: random.Random | None = None,
) -> list[Any]:
    """Dispatch hook selection by `strategy` (config flag HOOK_SELECTOR).

    All strategies return DISTINCT hooks (spec §5B.2 hard rule).
    """
    strat = (strategy or "softmax").lower()
    if strat == "thompson":
        return pick_thompson(templates, n, rng=rng)
    if strat == "ucb1":
        return pick_ucb1(templates, n)
    return pick_weighted(
        templates, n, temperature=temperature, distinct=True, rng=rng
    )
