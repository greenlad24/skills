"""Variant-batch generation + near-duplicate suppression guard (spec §5B.1/§5B.2).

For one product we spin up N variants that differ primarily by HookTemplate and
format, holding the product constant, tied together by a shared `variant_group_id`
so the cohort can be scored relative to each other. TikTok suppresses near-identical
/ unoriginal content, so differentiation is enforced BEFORE render:

  * Hard rule: every variant in a cohort uses a DISTINCT HookTemplate.
  * Differentiation score: cheap trigram-Jaccard similarity across hook opening
    lines (stdlib only — no embedding dependency). Any pair with similarity
    > SIM_CAP is flagged for regeneration.
  * A `variation_manifest` records what varied, as auditable evidence.

The similarity math is pure & unit-testable; job creation touches the DB.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.models import HookTemplate, FormulaTemplate, PacingTemplate, VideoJob
from app.core.queue import celery_app
from app.core.state_machine import JobState
from app.modules.posting import selector

# Default cohort size and similarity cap (spec §5B.1 / §5B.2).
DEFAULT_N: int = 4
SIM_CAP: float = 0.85


# --------------------------------------------------------------------------- #
# Similarity (pure)
# --------------------------------------------------------------------------- #
def _trigrams(text: str) -> set[str]:
    norm = " ".join((text or "").lower().split())
    if len(norm) < 3:
        return {norm} if norm else set()
    return {norm[i : i + 3] for i in range(len(norm) - 2)}


def trigram_jaccard(a: str, b: str) -> float:
    """Character-trigram Jaccard similarity in [0, 1]. Deterministic, stdlib-only.

    A cheap stand-in for embedding cosine similarity (spec §5B.2 allows either);
    swap in an embedding model later without changing the guard's interface.
    """
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


@dataclass
class SimilarityFinding:
    i: int
    j: int
    similarity: float
    over_cap: bool


def differentiation_check(
    opening_lines: Sequence[str], *, sim_cap: float = SIM_CAP
) -> list[SimilarityFinding]:
    """Pairwise similarity across a cohort's opening lines.

    Returns every pair's similarity; `over_cap` marks pairs whose similarity
    exceeds `sim_cap` and must be regenerated before render.
    """
    findings: list[SimilarityFinding] = []
    n = len(opening_lines)
    for i in range(n):
        for j in range(i + 1, n):
            sim = trigram_jaccard(opening_lines[i], opening_lines[j])
            findings.append(SimilarityFinding(i, j, sim, sim > sim_cap))
    return findings


def has_duplicates(
    opening_lines: Sequence[str], *, sim_cap: float = SIM_CAP
) -> bool:
    return any(f.over_cap for f in differentiation_check(opening_lines, sim_cap=sim_cap))


@dataclass
class VariationManifest:
    """Auditable evidence of differentiation, persisted per job (spec §5B.2)."""

    hook_id: str | None = None
    hook_family: str | None = None
    format: str | None = None
    pacing_id: str | None = None
    formula_id: str | None = None
    opening_line: str | None = None
    cta: str | None = None
    music_ref: str | None = None
    sim_scores_vs_cohort: list[float] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "hook_id": self.hook_id,
            "hook_family": self.hook_family,
            "format": self.format,
            "pacing_id": self.pacing_id,
            "formula_id": self.formula_id,
            "opening_line": self.opening_line,
            "cta": self.cta,
            "music_ref": self.music_ref,
            "sim_scores_vs_cohort": self.sim_scores_vs_cohort,
        }


# --------------------------------------------------------------------------- #
# Batch generation (DB)
# --------------------------------------------------------------------------- #
def _sim_scores_for(index: int, findings: list[SimilarityFinding], n: int) -> list[float]:
    scores = [0.0] * n
    for f in findings:
        if f.i == index:
            scores[f.j] = f.similarity
        elif f.j == index:
            scores[f.i] = f.similarity
    return [round(s, 4) for s in scores if s or True][:n]


def generate_variant_batch(
    product_id: str,
    n: int = DEFAULT_N,
    *,
    hook_selector: str | None = None,
    session=None,
) -> dict[str, Any]:
    """Create `n` differentiated variant jobs for one product (spec §5B.1).

    - Picks `n` DISTINCT HookTemplates (weighted / bandit per HOOK_SELECTOR) plus
      weighted formulas & pacings.
    - Runs the differentiation guard on the picked hooks; pairs over SIM_CAP are
      logged and their variant is flagged `needs_regen` in the manifest (the render
      pipeline regenerates before posting — this trigger does not itself render).
    - Persists a `variation_manifest` on each job's `decision` JSON and a shared
      `variant_group_id` so the cohort can be scored together.
    - Enqueues `research.run` (the pipeline entry) for each job.

    Returns {variant_group_id, job_ids, manifests, blocked}. Caller/tests may pass a
    `session`; otherwise a SessionLocal is opened and committed here.
    """
    own_session = session is None
    session = session or SessionLocal()
    try:
        variant_group_id = uuid.uuid4()
        hooks = selector.pick_hooks(
            session.query(HookTemplate).all(),
            n,
            strategy=hook_selector or _hook_selector_setting(),
        )
        formulas = selector.pick_weighted(
            session.query(FormulaTemplate).all(), n, distinct=False
        )
        pacings = selector.pick_weighted(
            session.query(PacingTemplate).all(), n, distinct=False
        )

        opening_lines = [getattr(h, "pattern_th", None) or getattr(h, "name", "") for h in hooks]
        findings = differentiation_check(opening_lines)

        job_ids: list[str] = []
        manifests: list[dict[str, Any]] = []
        for i, hook in enumerate(hooks):
            formula = formulas[i] if i < len(formulas) else None
            pacing = pacings[i] if i < len(pacings) else None
            manifest = VariationManifest(
                hook_id=str(hook.id),
                hook_family=getattr(hook, "hook_type", None),
                format=getattr(formula, "name", None),
                pacing_id=str(pacing.id) if pacing else None,
                formula_id=str(formula.id) if formula else None,
                opening_line=opening_lines[i],
                sim_scores_vs_cohort=_sim_scores_for(i, findings, len(hooks)),
            )
            needs_regen = any(
                f.over_cap and (f.i == i or f.j == i) for f in findings
            )
            job = VideoJob(
                product_id=uuid.UUID(str(product_id)),
                hook_template_id=hook.id,
                formula_template_id=formula.id if formula else None,
                pacing_template_id=pacing.id if pacing else None,
                state=JobState.QUEUED,
                cost_budget_usd=settings.PER_VIDEO_COST_BUDGET_USD,
                decision={
                    "variant_group_id": str(variant_group_id),
                    "variation_manifest": manifest.as_dict(),
                    "needs_regen": needs_regen,
                },
            )
            session.add(job)
            session.flush()
            job_ids.append(str(job.id))
            manifests.append(manifest.as_dict())

        if own_session:
            session.commit()

        for jid in job_ids:
            try:
                celery_app.send_task("research.run", kwargs={"job_id": jid})
            except Exception:  # noqa: BLE001 — broker may be absent in skeleton runs
                pass

        return {
            "variant_group_id": str(variant_group_id),
            "job_ids": job_ids,
            "manifests": manifests,
            "blocked": [
                {"i": f.i, "j": f.j, "similarity": round(f.similarity, 4)}
                for f in findings
                if f.over_cap
            ],
        }
    finally:
        if own_session:
            session.close()


def _hook_selector_setting() -> str:
    """HOOK_SELECTOR isn't a core Settings field; default to softmax. A vendor/config
    module can surface it later. Read defensively so a missing attr never crashes."""
    return getattr(settings, "HOOK_SELECTOR", "softmax") or "softmax"
