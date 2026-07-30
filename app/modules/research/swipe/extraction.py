"""Script-extraction pipeline (§2B.2): yt-dlp → audio → Whisper VO → Thai OCR (OSD) →
PyThaiNLP segmentation → merged timed transcript.

`extract_transcript` runs the whole pipeline over injectable `MediaTools` (stubs in
DRY_RUN) and returns a `MergedTranscript` carrying both VO and OSD segments on one
timeline plus tokenized text — exactly the §2B.2 merge shape.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .mediatools import MediaTools, OsdEvent, VoSegment, get_media_tools
from .thai import word_tokenize

# On-screen chrome to skip (TikTok watermark/handle overlays). CTA text like
# "ปักตะกร้า" is intentionally KEPT — it's script, not chrome.
_CHROME_MARKERS = ("tiktok.com", "@", "follow", "ติดตาม")


@dataclass
class TranscriptSegment:
    t_start: float
    t_end: float
    source: str          # "vo" | "osd"
    text: str
    bbox: list[float] = field(default_factory=list)


@dataclass
class MergedTranscript:
    tiktok_id: str
    language: str
    segments: list[TranscriptSegment]
    vo_text: str
    osd_text: str
    merged_text: str
    tokens: list[str]

    def as_dict(self) -> dict:
        d = asdict(self)
        return d


def _is_chrome(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _CHROME_MARKERS)


def _dedupe_osd(events: list[OsdEvent]) -> list[OsdEvent]:
    """Collapse consecutive identical OSD strings into single timed events."""
    out: list[OsdEvent] = []
    for e in events:
        if _is_chrome(e.text):
            continue
        if out and out[-1].text == e.text:
            out[-1].t_end = max(out[-1].t_end, e.t_end)
        else:
            out.append(e)
    return out


def merge(
    tiktok_id: str,
    vo: list[VoSegment],
    osd: list[OsdEvent],
    *,
    language: str = "th",
) -> MergedTranscript:
    """Interleave VO + OSD on one timeline (ordered by t_start) and tokenize (§2B.2.6)."""
    osd = _dedupe_osd(osd)
    segs: list[TranscriptSegment] = []
    for s in vo:
        segs.append(TranscriptSegment(s.t_start, s.t_end, "vo", s.text))
    for e in osd:
        segs.append(TranscriptSegment(e.t_start, e.t_end, "osd", e.text, list(e.bbox)))
    segs.sort(key=lambda x: (x.t_start, 0 if x.source == "vo" else 1))

    vo_text = " ".join(s.text for s in vo).strip()
    osd_text = " ".join(e.text for e in osd).strip()
    merged_text = " ".join(f"[{s.source}] {s.text}" for s in segs).strip()
    tokens = word_tokenize(f"{vo_text} {osd_text}")

    return MergedTranscript(
        tiktok_id=tiktok_id,
        language=language,
        segments=segs,
        vo_text=vo_text,
        osd_text=osd_text,
        merged_text=merged_text,
        tokens=tokens,
    )


def extract_transcript(
    url: str,
    tiktok_id: str,
    duration_s: float | None = None,
    *,
    tools: MediaTools | None = None,
    local_video_path: str | None = None,
) -> tuple[MergedTranscript, str]:
    """Run download → VO → OSD → merge. Returns (transcript, local_video_path).

    Idempotency at the video level is handled by the caller (`processed_stages`); this
    function just performs the extraction with whatever tools are supplied.
    """
    tools = tools or get_media_tools()
    path = local_video_path or tools.downloader.download(url, tiktok_id)
    vo = tools.transcriber.transcribe(path)
    osd = tools.ocr.read_frames(path, duration_s or 0.0)
    transcript = merge(tiktok_id, vo, osd)
    return transcript, path
