"""Pure-function tests for the winner-loop scoring & reweighting (spec §5B.6/§5B.7)."""

from __future__ import annotations

from types import SimpleNamespace

from app.modules.posting import scoring


def _rec(**kw):
    base = dict(
        views=0, likes=0, comments=0, shares=0, favorites=0,
        full_video_watch_rate=None, orders=None, gmv=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_engagement_rate_intent_weights():
    # share(3) > comment(2) > favorite(1.5) > like(1)
    er = scoring.engagement_rate(likes=10, comments=0, shares=0, favorites=0, views=100)
    er_share = scoring.engagement_rate(likes=0, comments=0, shares=10, favorites=0, views=100)
    assert er_share > er
    assert er == 0.1


def test_compute_score_engagement_only_branch():
    # orders is None -> score == E_scaled, no commercial contribution.
    rec = _rec(views=1000, likes=100, comments=20, shares=10, favorites=5)
    score = scoring.compute_score(rec)
    e = scoring.engagement_component(rec)
    assert score == scoring._squash(e)
    assert 0.0 <= score <= 1.0


def test_compute_score_sales_dominant_branch():
    # Two posts, identical engagement; the one with sales scores higher and uses the
    # 0.20/0.80 blend (sales dominates).
    no_sales = _rec(views=1000, likes=100, comments=20, shares=10, favorites=5)
    with_sales = _rec(views=1000, likes=100, comments=20, shares=10, favorites=5,
                      orders=50, gmv=5000)
    s_no = scoring.compute_score(no_sales)
    s_yes = scoring.compute_score(with_sales)
    assert s_yes > s_no

    # Verify the explicit blend weights are applied.
    e = scoring.engagement_component(with_sales)
    c, has_sales = scoring.commercial_component(with_sales)
    assert has_sales is True
    expected = 0.20 * scoring._squash(e) + 0.80 * scoring._squash(c)
    assert abs(s_yes - expected) < 1e-9


def test_commercial_component_absent_when_no_orders():
    c, has_sales = scoring.commercial_component(_rec(views=1000))
    assert c == 0.0 and has_sales is False


def test_trajectory_bonus_rewards_growth_and_is_capped():
    assert scoring.trajectory_bonus(100, 100) == 0.0
    assert scoring.trajectory_bonus(100, 400) == 0.1 * 3.0 * (1 / 1)  # traj=3 -> capped
    # capped at 3 even if growth is larger
    assert scoring.trajectory_bonus(100, 10000) == 0.1 * 3.0


def test_update_operator_win_score_moves_and_floors():
    # High score raises weight above baseline; low score lowers it; both >= FLOOR.
    high = scoring.update_operator_win_score(None, 0.9)
    low = scoring.update_operator_win_score(None, 0.1)
    assert high > scoring.BASELINE * 0.9  # clearly increased toward the high signal
    assert high > low
    assert low >= scoring.FLOOR

    # Repeated zero scores never drive weight to 0 (exploration preserved).
    w = 0.5
    for _ in range(100):
        w = scoring.update_operator_win_score(w, 0.0)
    assert w >= scoring.FLOOR


def test_attribute_to_templates_updates_each_independently():
    hook = SimpleNamespace(operator_win_score=0.5, signal_type="engagement_proxy")
    formula = SimpleNamespace(operator_win_score=0.5, signal_type="engagement_proxy")
    pacing = SimpleNamespace(operator_win_score=0.2, signal_type="engagement_proxy")
    scoring.attribute_to_templates([hook, formula, pacing, None], 0.9)
    assert hook.operator_win_score > 0.5
    assert formula.operator_win_score > 0.5
    assert pacing.operator_win_score > 0.2
    # signal label flips off "engagement_proxy" once a real operator score exists.
    assert hook.signal_type == "operator_win"


def test_softmax_weights_normalized_and_monotonic():
    probs = scoring.softmax_weights([0.1, 0.9, 0.5])
    assert abs(sum(probs) - 1.0) < 1e-9
    # highest weight -> highest probability
    assert probs[1] == max(probs)
