from __future__ import annotations

from app.modules.research.swipe import extraction
from app.modules.research.swipe.mediatools import OsdEvent, VoSegment, get_media_tools


def test_merge_has_vo_and_osd_and_tokens():
    tr, path = extraction.extract_transcript("https://tt/x", "vid123", 28.0)
    sources = {s.source for s in tr.segments}
    assert "vo" in sources and "osd" in sources
    assert tr.vo_text and tr.osd_text
    assert tr.tokens  # PyThaiNLP or fallback tokenization present
    # timeline ordered
    starts = [s.t_start for s in tr.segments]
    assert starts == sorted(starts)


def test_chrome_filtered_but_cta_kept():
    vo = [VoSegment(0.0, 2.0, "ทดสอบ")]
    osd = [
        OsdEvent(0.0, 1.0, "@brandhandle"),      # chrome → dropped
        OsdEvent(1.0, 2.0, "follow ติดตาม"),      # chrome → dropped
        OsdEvent(2.0, 3.0, "ปักตะกร้า"),          # CTA → kept
    ]
    merged = extraction.merge("v", vo, osd)
    osd_texts = [s.text for s in merged.segments if s.source == "osd"]
    assert osd_texts == ["ปักตะกร้า"]


def test_stub_tools_selected_in_dry_run():
    tools = get_media_tools()
    # stub transcriber yields canned Thai VO
    segs = tools.transcriber.transcribe("x.mp4")
    assert len(segs) >= 3
