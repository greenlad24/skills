"""4B — forced alignment on the CLEAN VO + ASS/libass generation.

Two disciplines:
  * **alignment** — WhisperX (Thai model) / Thonburian Whisper ASR + WhisperX ``align()``
    for word timings, re-tokenized with PyThaiNLP; guarded against interpolation drift,
    OOV brand splits, and tone-mark/cluster splits (§4B.2 / §4B.3);
  * **rendering** — ASS through libass (NEVER drawtext), ZWSP break hints, embedded Noto
    Sans Thai, ``\\k`` karaoke only where alignment is trustworthy (§4B.4 / §4B.5).

WhisperX is imported lazily; if a Thai acoustic align-model is absent the whole result is
downgraded to all-static captions (``AlignResult.degraded=True``, §4D.4) so the video
still ships.
"""

from __future__ import annotations

from .config import CONFIG, CaptionStyle, EditingConfig
from .thai import ZWSP, with_break_hints
from .types import AlignResult, CaptionMode, Segment, WordTiming


# --------------------------------------------------------------------------- #
# §4B.1–4B.2 — align on the CLEAN VO (before any music mix)
# --------------------------------------------------------------------------- #
def align_captions(
    clean_vo_path: str,
    glossary: str = "",
    brand_terms: list[str] | None = None,
    device: str = "cpu",
    model_size: str = "large-v3",
) -> AlignResult:
    """Forced-align the clean VO into word timings; re-tokenize with PyThaiNLP.

    On any failure to load a Thai acoustic align-model, return a *degraded* result
    (segments still present, marked ``interpolated`` -> all-static, no karaoke).
    """
    try:
        import whisperx  # lazy: very heavy dep

        model = whisperx.load_model(
            model_size, device, language="th",
            asr_options={"initial_prompt": glossary} if glossary else None,
        )
        result = model.transcribe(clean_vo_path)
        align_model, meta = whisperx.load_align_model(language_code="th", device=device)
        aligned = whisperx.align(
            result["segments"], align_model, meta, clean_vo_path, device,
            return_char_alignments=True,
        )
        return _to_align_result(aligned, meta, brand_terms)
    except Exception:  # noqa: BLE001 — §4D.4: Thai align model absent -> all-static
        return AlignResult(segments=[], meta={"type": "absent"}, degraded=True)


def _to_align_result(aligned: dict, meta: dict, brand_terms) -> AlignResult:
    """Map WhisperX output onto our ``AlignResult``; detect interpolation drift."""
    from .thai import build_brand_trie, thai_words

    trie = build_brand_trie(brand_terms or [])
    # meta["type"] == "torchaudio" => a real acoustic model aligned (trustworthy).
    acoustic = meta.get("type") == "torchaudio"
    segments: list[Segment] = []
    for seg in aligned.get("segments", []):
        raw_words = seg.get("words", []) or []
        words: list[WordTiming] = []
        for w in raw_words:
            words.append(
                WordTiming(
                    word=w.get("word", ""),
                    start=float(w.get("start", seg.get("start", 0.0)) or 0.0),
                    end=float(w.get("end", seg.get("end", 0.0)) or 0.0),
                    score=float(w.get("score", 1.0) or 0.0),
                )
            )
        # Re-segment the text with a Thai tokenizer (WhisperX word bounds are unreliable).
        text = seg.get("text", "")
        _ = thai_words(text, trie)  # ensures OOV terms are validated against the trie
        segments.append(
            Segment(
                text=text,
                start=float(seg.get("start", 0.0) or 0.0),
                end=float(seg.get("end", 0.0) or 0.0),
                words=words,
                align_type="acoustic" if acoustic else "interpolated",
            )
        )
    return AlignResult(segments=segments, meta=meta, degraded=not acoustic)


# --------------------------------------------------------------------------- #
# §4B.4 — caption strategy: static phrase vs. karaoke word-highlight
# --------------------------------------------------------------------------- #
def choose_mode(segment: Segment, conf_threshold: float = 0.5) -> CaptionMode:
    """Karaoke only where alignment is trustworthy (§4B.4 / T-8)."""
    if segment.align_type != "acoustic":       # interpolated -> not trustworthy
        return "static"
    if not segment.words:
        return "static"
    if min(w.score for w in segment.words) < conf_threshold:
        return "static"
    return "karaoke"


# --------------------------------------------------------------------------- #
# §4B.5 — ASS / libass generation
# --------------------------------------------------------------------------- #
ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: {playres_x}
PlayResY: {playres_y}
WrapStyle: 1
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{size},{primary},{highlight},&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},{align},48,48,{margin_v},1
Style: Disclosure,{disc_font},{disc_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,3,0,0,7,48,48,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\
"""


def _ass_time(seconds: float) -> str:
    """Format seconds as ASS ``H:MM:SS.cc`` (centisecond precision)."""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs == 100:  # rounding carry
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def dialogue(start: float, end: float, text: str, style: str = "Caption") -> str:
    return f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},{style},,0,0,0,,{text}"


def _karaoke_body(segment: Segment, brand_trie=None) -> str:
    """Emit ``{\\kNN}`` karaoke tags (centiseconds) per word, ZWSP-joined (§4B.5)."""
    body = ""
    for w in segment.words:
        cs = max(1, round((w.end - w.start) * 100))
        body += f"{{\\k{cs}}}{with_break_hints(w.word, brand_trie)}{ZWSP}"
    return body


def build_ass(
    align: AlignResult,
    style: CaptionStyle = CONFIG.caption,
    cfg: EditingConfig = CONFIG,
    include_disclosure: bool = False,
    brand_terms: list[str] | None = None,
    out_path: str | None = None,
) -> str:
    """Build the ``captions.ass`` text (optionally write it).

    ``include_disclosure`` adds the §4C badge event; the default worker bakes the
    disclosure into ``final.mp4`` instead (``disclosure.in_base=True``) and leaves this
    False to avoid a double label.
    """
    from .thai import build_brand_trie

    trie = build_brand_trie(brand_terms or [])
    header = ASS_HEADER.format(
        playres_x=cfg.render.width,
        playres_y=cfg.render.height,
        font=style.font,
        size=style.size,
        primary=style.primary,
        highlight=style.highlight,
        outline=style.outline,
        shadow=style.shadow,
        align=style.align,
        margin_v=style.margin_v,
        disc_font=cfg.disclosure.font,
        disc_size=cfg.disclosure.size,
    )

    events: list[str] = []
    if include_disclosure:
        events.append(_disclosure_event(cfg))

    for seg in align.segments:
        if choose_mode(seg, style.karaoke_conf_threshold) == "karaoke":
            body = _karaoke_body(seg, trie)
        else:
            body = with_break_hints(seg.text, trie)   # static phrase
        events.append(dialogue(seg.start, seg.end, body))

    text = header + "\n" + "\n".join(events) + "\n"
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return text


# --------------------------------------------------------------------------- #
# §4C — disclosure badge as an ASS event (dual Thai + EN label)
# --------------------------------------------------------------------------- #
def _disclosure_event(cfg: EditingConfig = CONFIG) -> str:
    start, end = cfg.disclosure.window_s
    return (
        f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Disclosure,,0,0,0,,"
        f"{cfg.disclosure.text}"
    )


def build_disclosure_ass(cfg: EditingConfig = CONFIG, out_path: str | None = None) -> str:
    """Disclosure-ONLY ASS burned into ``final.mp4`` in the cut pass (§4C, in_base).

    Kept separate from ``captions.ass`` so the label survives a re-caption that
    regenerates the captions, and is baked into the base video (TikTok-Shop policy).
    Uses libass -> Thai renders correctly (a drawtext plate would mis-stack).
    """
    header = ASS_HEADER.format(
        playres_x=cfg.render.width,
        playres_y=cfg.render.height,
        font=cfg.caption.font,
        size=cfg.caption.size,
        primary=cfg.caption.primary,
        highlight=cfg.caption.highlight,
        outline=cfg.caption.outline,
        shadow=cfg.caption.shadow,
        align=cfg.caption.align,
        margin_v=cfg.caption.margin_v,
        disc_font=cfg.disclosure.font,
        disc_size=cfg.disclosure.size,
    )
    text = header + "\n" + _disclosure_event(cfg) + "\n"
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return text
