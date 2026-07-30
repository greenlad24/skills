"""Winner-loop scoring, attribution & template reweighting (spec §5B.6 / §5B.7).

Everything here is a **pure function** of its inputs (no DB, no I/O), so the
scoring/weighting logic can be unit-tested in isolation (acceptance §5E). The
Celery ingestion task (tasks.py / ingest.py) is the only place these are wired to
the ORM.

HONESTY CONTRACT (carried from the data model): engagement is a *proxy* signal;
real sales (`orders`/`gmv`) are the true signal and **dominate** the blend when
present. When sales data is absent we fall back to an engagement-only score and
never pretend a proxy is a conversion.

Deviation from the spec text, reconciled against core models: spec §5B.7 mutates
`tpl.perf_ema` / `tpl.weight` / `tpl.weight_prior` / `tpl.samples`, but the
canonical templates (`HookTemplate`/`FormulaTemplate`/`PacingTemplate` in
app/core/models.py) expose `operator_win_score` as the operator-real selection
weight. We therefore fold the EMA directly into `operator_win_score` — a floored,
decayed exponential moving average — which is the field CONTRACTS.md names for
this loop. `proxy_score` stays reserved for the engagement-only proxy.
"""

from __future__ import annotations

import math
from typing import Any, Callable

# --- Scoring constants (spec §5B.6) ---
K_REV: float = 0.5           # revenue-per-view weight inside the commercial term
WATCH_DEFAULT: float = 0.5   # assumed full-video watch rate when not exposed
SALES_BLEND_E: float = 0.20  # engagement weight when sales are present
SALES_BLEND_C: float = 0.80  # commercial weight when sales are present (dominates)

# --- Reweight constants (spec §5B.7) ---
ALPHA: float = 0.3           # EMA learning rate (higher = faster, noisier)
DECAY: float = 0.98          # pulls unused templates back toward baseline
FLOOR: float = 0.05          # a weight never hits 0 -> keeps exploration alive
BASELINE: float = 0.5        # cold-start prior for an unseen template


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _attr(rec: Any, name: str, default: Any = None) -> Any:
    """Read `name` from an ORM row, a dataclass, a SimpleNamespace, or a dict."""
    if isinstance(rec, dict):
        return rec.get(name, default)
    return getattr(rec, name, default)


def _num(value: Any, default: float = 0.0) -> float:
    """Coerce a possibly-None / Decimal value to float."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _squash(x: float) -> float:
    """Saturating map [0, inf) -> [0, 1). Monotonic, deterministic, no fitted params.

    Used as the DEFAULT normalizer for E and C so scores are bounded and comparable
    across posts of very different view counts without needing the trailing-90-day
    distribution wired in. The ingestion task may pass real min-max / z-score→sigmoid
    scalers (spec §5B.6) via `e_scaler` / `c_scaler`; storing the raw E/C components on
    the record lets us rescale later without re-fetching.
    """
    if x <= 0:
        return 0.0
    return x / (1.0 + x)


# --------------------------------------------------------------------------- #
# Step 1 — engagement rate (proxy signal)
# --------------------------------------------------------------------------- #
def engagement_rate(
    *, likes: float, comments: float, shares: float, favorites: float, views: float
) -> float:
    """Intent-weighted engagement / views (spec §5B.6 step 1).

    Weights reflect intent depth: share(3) > comment(2) > favorite(1.5) > like(1).
    """
    weighted = likes + 2.0 * comments + 3.0 * shares + 1.5 * favorites
    return weighted / max(views, 1.0)


def engagement_component(rec: Any, *, watch_default: float = WATCH_DEFAULT) -> float:
    """E = engagement_rate * (0.5 + watch_factor) — watch-through amplifies."""
    er = engagement_rate(
        likes=_num(_attr(rec, "likes")),
        comments=_num(_attr(rec, "comments")),
        shares=_num(_attr(rec, "shares")),
        favorites=_num(_attr(rec, "favorites")),
        views=_num(_attr(rec, "views")),
    )
    fvwr = _attr(rec, "full_video_watch_rate")
    watch_factor = clamp(_num(fvwr, watch_default), 0.0, 1.0)
    return er * (0.5 + watch_factor)


# --------------------------------------------------------------------------- #
# Step 2 — commercial rate (real signal, when available)
# --------------------------------------------------------------------------- #
def commercial_component(rec: Any, *, k_rev: float = K_REV) -> tuple[float, bool]:
    """C, has_sales (spec §5B.6 step 2). Sales absent -> (0.0, False)."""
    orders = _attr(rec, "orders")
    views = _num(_attr(rec, "views"))
    if orders is None or views <= 0:
        return 0.0, False
    orders_f = _num(orders)
    conversion_rate = orders_f / views
    revenue_per_view = _num(_attr(rec, "gmv")) / max(views, 1.0)
    c = 1000.0 * conversion_rate + k_rev * revenue_per_view
    return c, True


# --------------------------------------------------------------------------- #
# Step 3 — blend (sales dominates when present)
# --------------------------------------------------------------------------- #
def compute_score(
    rec: Any,
    *,
    k_rev: float = K_REV,
    watch_default: float = WATCH_DEFAULT,
    e_scaler: Callable[[float], float] | None = None,
    c_scaler: Callable[[float], float] | None = None,
) -> float:
    """Per-record score in [0, 1] (spec §5B.6). Pure function.

    - `orders is None`  -> engagement-only branch: score == E_scaled.
    - `orders` present  -> sales-dominant branch: 0.20*E_scaled + 0.80*C_scaled.

    `e_scaler`/`c_scaler` default to a saturating squash; the ingestion task may
    inject distribution-aware normalizers.
    """
    e = engagement_component(rec, watch_default=watch_default)
    c, has_sales = commercial_component(rec, k_rev=k_rev)
    escale = e_scaler or _squash
    cscale = c_scaler or _squash
    e_scaled = clamp(escale(e), 0.0, 1.0)
    if not has_sales:
        return e_scaled
    c_scaled = clamp(cscale(c), 0.0, 1.0)
    return SALES_BLEND_E * e_scaled + SALES_BLEND_C * c_scaled


def trajectory_bonus(views_day1: float, views_day7: float) -> float:
    """Reward sustained growth (spec §5B.6 trajectory bonus).

    traj = (v7 - v1) / max(v1, 1); bonus = 0.1 * clamp(traj, 0, 3). Prevents a
    one-day spike from beating a slow-burn winner.
    """
    traj = (views_day7 - views_day1) / max(views_day1, 1.0)
    return 0.1 * clamp(traj, 0.0, 3.0)


def aggregate_post_score(record_score: float, *, traj: float = 0.0) -> float:
    """Aggregate post score = latest record score + trajectory bonus, clamped [0,1]."""
    return clamp(record_score + traj, 0.0, 1.0)


# --------------------------------------------------------------------------- #
# Attribution + weight update (closing the loop) — spec §5B.7
# --------------------------------------------------------------------------- #
def update_operator_win_score(
    prev_weight: float | None,
    post_score_norm: float,
    *,
    alpha: float = ALPHA,
    decay: float = DECAY,
    floor: float = FLOOR,
    baseline: float = BASELINE,
) -> float:
    """Floored, decayed EMA update of a template's `operator_win_score`.

    new = max(floor, alpha*post_score_norm + (1-alpha)*decay*prev)

    - A high-scoring template's weight rises; a low-scoring one's falls.
    - `floor` guarantees the weight never hits 0, so a template can always be
      re-explored (spec §5B.7 FLOOR rationale).
    - `decay` gently pulls a template toward baseline when it stops earning.
    Pure function: returns the new weight, mutates nothing.
    """
    prev = baseline if prev_weight is None else float(prev_weight)
    ema = alpha * post_score_norm + (1.0 - alpha) * decay * prev
    return max(floor, ema)


def attribute_to_templates(
    templates: list[Any],
    post_score_norm: float,
    *,
    alpha: float = ALPHA,
    decay: float = DECAY,
    floor: float = FLOOR,
) -> None:
    """Attribute a post's aggregate score to each template independently (shared,
    not double-counted — spec §5B.7). Mutates each template's `operator_win_score`
    in place; the caller commits. Skips None entries (a job may lack a template).
    """
    for tpl in templates:
        if tpl is None:
            continue
        prev = getattr(tpl, "operator_win_score", None)
        tpl.operator_win_score = update_operator_win_score(
            prev, post_score_norm, alpha=alpha, decay=decay, floor=floor
        )
        # Keep the honesty label truthful: once a real operator score exists the
        # signal is no longer a pure proxy.
        if getattr(tpl, "signal_type", None) == "engagement_proxy" and post_score_norm > 0:
            tpl.signal_type = "operator_win"


# --------------------------------------------------------------------------- #
# Selection weights -> probabilities (softmax with temperature) — spec §5B.7
# --------------------------------------------------------------------------- #
def softmax_weights(
    weights: list[float], *, temperature: float = 0.7
) -> list[float]:
    """Softmax over selection weights with temperature T (default 0.7).

    Higher-weight templates are sampled proportionally more often; T controls
    exploration (higher T -> flatter, more exploratory). Pure function.
    """
    if not weights:
        return []
    t = max(temperature, 1e-6)
    scaled = [w / t for w in weights]
    m = max(scaled)
    exps = [math.exp(s - m) for s in scaled]
    total = sum(exps) or 1.0
    return [e / total for e in exps]
