"""Variant-batch + duplicate-suppression tests (spec §5B.1/§5B.2)."""

from __future__ import annotations

from app.modules.posting import variants
from app.modules.posting.tests.conftest import make_hook


def test_trigram_jaccard_identical_and_disjoint():
    assert variants.trigram_jaccard("hello world", "hello world") == 1.0
    assert variants.trigram_jaccard("abcdef", "zyxwvu") == 0.0


def test_differentiation_check_flags_near_duplicates():
    lines = ["stop scrolling right now", "stop scrolling right now!!", "brand new gadget alert"]
    findings = variants.differentiation_check(lines, sim_cap=0.85)
    over = [f for f in findings if f.over_cap]
    assert any(f.i == 0 and f.j == 1 for f in over)  # the near-identical pair is flagged
    assert variants.has_duplicates(lines) is True


def test_generate_variant_batch_distinct_hooks_shared_group(session, product):
    for i in range(4):
        make_hook(session, f"hook{i}", f"totally different opening line number {i} " * 2, 0.5)
    out = variants.generate_variant_batch(str(product.id), 4, session=session)

    assert len(out["job_ids"]) == 4
    # distinct HookTemplates within the cohort (hard rule)
    from app.core.models import VideoJob

    hook_ids = set()
    group_ids = set()
    for jid in out["job_ids"]:
        job = session.get(VideoJob, jid)
        hook_ids.add(str(job.hook_template_id))
        group_ids.add(job.decision["variant_group_id"])
    assert len(hook_ids) == 4
    assert len(group_ids) == 1  # single shared variant_group_id
    assert group_ids == {out["variant_group_id"]}
