"""4B ASS builder + caption-mode tests (pure — WhisperX not required)."""

from __future__ import annotations

from app.modules.editing.captions import (
    _ass_time,
    build_ass,
    build_disclosure_ass,
    choose_mode,
)
from app.modules.editing.types import AlignResult, Segment, WordTiming


def test_ass_time_centisecond_format():
    assert _ass_time(0) == "0:00:00.00"
    assert _ass_time(3.0) == "0:00:03.00"
    assert _ass_time(65.5) == "0:01:05.50"


def test_choose_mode_karaoke_only_when_trustworthy():
    good = Segment("x", 0, 1, [WordTiming("a", 0, 0.5, 0.9), WordTiming("b", 0.5, 1, 0.8)],
                   align_type="acoustic")
    assert choose_mode(good) == "karaoke"
    # interpolated -> static (T-8)
    interp = Segment("x", 0, 1, [WordTiming("a", 0, 1, 0.9)], align_type="interpolated")
    assert choose_mode(interp) == "static"
    # low confidence -> static (T-8)
    lowconf = Segment("x", 0, 1, [WordTiming("a", 0, 0.5, 0.9), WordTiming("b", 0.5, 1, 0.2)],
                      align_type="acoustic")
    assert choose_mode(lowconf) == "static"
    # no words -> static
    assert choose_mode(Segment("x", 0, 1, [], align_type="acoustic")) == "static"


def test_build_ass_header_and_events():
    seg = Segment("hello", 0.0, 1.0, [WordTiming("hello", 0.0, 1.0, 0.9)], align_type="acoustic")
    ass = build_ass(AlignResult(segments=[seg]))
    assert "[Script Info]" in ass
    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1920" in ass
    assert "Style: Caption" in ass
    assert "Dialogue:" in ass
    # karaoke tag present for a trustworthy segment
    assert "\\k" in ass


def test_build_ass_static_has_no_karaoke_tags():
    seg = Segment("hi", 0.0, 1.0, [WordTiming("hi", 0.0, 1.0, 0.1)], align_type="interpolated")
    ass = build_ass(AlignResult(segments=[seg]))
    assert "\\k" not in ass  # interpolated -> static, no karaoke sweep


def test_build_ass_omits_disclosure_by_default():
    ass = build_ass(AlignResult(segments=[]), include_disclosure=False)
    assert "Disclosure,," not in ass


def test_build_disclosure_ass_first_three_seconds():
    ass = build_disclosure_ass()
    assert "Style: Disclosure" in ass
    assert "0:00:00.00,0:00:03.00,Disclosure" in ass
    assert "AI-generated" in ass
    assert "สร้างโดย AI" in ass
