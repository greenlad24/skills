"""Product-consistency QA gate (§3D.5).

After each b-roll clip completes, run an automated vision check before accepting:
sample frames → detect/crop the product region → embed → cosine-compare to the
hero image's product embedding. Accept if ``min(frame_similarity) >= THRESHOLD``,
otherwise reroll (same hero, new seed, attempt+1) up to ``MAX_REROLLS``.

Real embeddings (CLIP/DINO) are out of scope for the DRY_RUN pipeline, so this
module exposes a pure, deterministic similarity function that:
  * honours an explicit ``qa_similarity`` in the clip meta (tests + real vision
    backends inject it there), and
  * otherwise derives a stable pseudo-similarity from the hero/clip references so
    the free dry-run path is deterministic and passes.

The frozen-frame checklist (§3D.4) is a separate pass; a clip must pass ALL.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from app.modules.generation.constants import QA_SIMILARITY_THRESHOLD

# The frozen-frame checklist items (§3D.5). A clip must pass every one.
CHECKLIST_ITEMS = (
    "single_hero_product",     # exactly one hero product visible
    "hands_ok",                # <= 2 hands, no extra/merged fingers
    "label_stable",            # no morphing label
    "no_baked_text",           # no hallucinated on-frame text
    "proportions_match",       # product proportions/color match hero
)


def _pseudo_similarity(hero_ref: str, clip_ref: str) -> float:
    """Deterministic similarity in [0.80, 0.99] seeded by the refs.

    Fake clips are conditioned on the hero, so the dry-run default lands above the
    0.85 threshold — the happy path accepts without spend. Tests that need a
    reject inject ``qa_similarity`` explicitly.
    """
    h = hashlib.sha256(f"{hero_ref}|{clip_ref}".encode("utf-8")).hexdigest()
    # Map first 4 hex digits into [0.86, 0.99] so the default always passes.
    n = int(h[:4], 16) / 0xFFFF
    return round(0.86 + n * 0.13, 4)


def product_similarity(hero_meta: dict[str, Any], clip_meta: dict[str, Any]) -> float:
    """Min cross-frame product similarity of a clip vs the hero image."""
    override = (clip_meta or {}).get("qa_similarity")
    if override is not None:
        return float(override)
    hero_ref = str((hero_meta or {}).get("image_key") or (hero_meta or {}).get("ref") or "hero")
    clip_ref = str((clip_meta or {}).get("video_key") or (clip_meta or {}).get("ref") or "clip")
    return _pseudo_similarity(hero_ref, clip_ref)


def frozen_frame_checklist(clip_meta: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return ``(passed, failures)`` for the §3D.5 frozen-frame checklist.

    Tests / real detectors put per-item booleans under
    ``clip_meta["checklist"]``; a missing item defaults to pass (the dry-run
    default is a clean clip).
    """
    overrides = (clip_meta or {}).get("checklist", {}) or {}
    failures = [item for item in CHECKLIST_ITEMS if overrides.get(item, True) is False]
    return (not failures, failures)


@dataclass
class QAResult:
    accepted: bool
    similarity: float
    threshold: float
    checklist_failures: list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        if self.accepted:
            return "ok"
        parts = []
        if self.similarity < self.threshold:
            parts.append(f"similarity {self.similarity:.3f} < {self.threshold:.3f}")
        if self.checklist_failures:
            parts.append("checklist: " + ", ".join(self.checklist_failures))
        return "; ".join(parts) or "rejected"


def evaluate(
    hero_meta: dict[str, Any],
    clip_meta: dict[str, Any],
    *,
    threshold: float = QA_SIMILARITY_THRESHOLD,
) -> QAResult:
    """Full QA gate: similarity threshold AND frozen-frame checklist must pass."""
    sim = product_similarity(hero_meta, clip_meta)
    checklist_ok, failures = frozen_frame_checklist(clip_meta)
    accepted = (sim >= threshold) and checklist_ok
    return QAResult(
        accepted=accepted,
        similarity=sim,
        threshold=threshold,
        checklist_failures=failures,
    )


def reroll_rate(rerolls: int, broll_scenes: int) -> float:
    """``reroll_rate = rerolls / broll_scenes`` (§3D.5), 0 when no b-roll."""
    if broll_scenes <= 0:
        return 0.0
    return round(rerolls / broll_scenes, 4)
