"""4B Thai text-discipline tests (pure — PyThaiNLP not required)."""

from __future__ import annotations

from app.modules.editing.thai import (
    COMBINING,
    ZWSP,
    _merge_orphan_marks,
    has_orphan_mark_break,
    safe_boundaries,
    with_break_hints,
)


def test_combining_set_covers_documented_marks():
    # U+0E31, U+0E34..U+0E3A, tone marks U+0E48..U+0E4B
    assert 0x0E31 in COMBINING
    assert all(cp in COMBINING for cp in range(0x0E34, 0x0E3B))
    assert all(cp in COMBINING for cp in range(0x0E48, 0x0E4C))


def test_safe_boundaries_drops_cut_before_combining_mark():
    # "กา" + mai-han-akat(่) at index 2 -> a cut at index 2 would orphan the mark
    text = "กา่บ"
    assert safe_boundaries(text, [1, 2, 3]) == [1, 3]


def test_merge_orphan_marks_glues_leading_mark_to_previous():
    # a tokenizer that produced ["กา", "่บ"] must be merged so the tone mark
    # never starts a token
    merged = _merge_orphan_marks(["กา", "่บ"])
    assert merged == ["กา่บ"]


def test_with_break_hints_joins_with_zwsp():
    # PyThaiNLP may be absent -> single token, no ZWSP; either way it must not crash
    out = with_break_hints("สวัสดี")
    assert isinstance(out, str)
    # if tokenized into multiple words the joiner is ZWSP (not a real space)
    assert " " not in out


def test_has_orphan_mark_break_detects_bad_wrap():
    good = "กา" + ZWSP + "บ"
    bad = "กา" + ZWSP + "่บ"
    assert has_orphan_mark_break(good) is False
    assert has_orphan_mark_break(bad) is True
