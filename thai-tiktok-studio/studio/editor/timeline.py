"""Resolve a plan video + the user's files into an exact, frame-level edit.

Pure planning step — no rendering. Produces:
  segments  (what source to show, from where, how long, with which camera effect)
  elements  (captions + motion graphics with absolute times)
  speech    (voice-over audio track, numpy, full length)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..plan_schema import strip_caption_price
from . import audio_io, elements as E, media, tts, voice

FPS = 30
SR = audio_io.SR


@dataclass
class Segment:
    path: str | None          # None → solid colour card
    kind: str                 # video | image | color
    src_in: float
    dur: float                # output seconds
    speed: float = 1.0
    use_audio: bool = False
    effect: str = "none"
    effect_t: float = 0.0     # seconds from this segment's start where the effect begins (0 = start)


@dataclass
class Resolved:
    segments: list = field(default_factory=list)
    elements: list = field(default_factory=list)
    speech: np.ndarray | None = None                 # mono float32 @48k
    total: float = 0.0
    beats: list = field(default_factory=list)        # [(t0, t1)]
    missing: list = field(default_factory=list)
    progress_color: tuple | None = None
    notes: list = field(default_factory=list)


def _chunk_text(text: str, max_chars: int = 18) -> list:
    words, out, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        out.append(cur)
    return [{"text": c, "highlight": []} for c in out]


def _weight(s: str) -> int:
    return max(1, len(re.sub(r"[ัิ-ฺ็-๎\s]", "", s)))


def _caption_elements(caps, start, length, ctx):
    caps = [dict(c, text=strip_caption_price(c["text"])) for c in caps]   # also covers older plans
    caps = [c for c in caps if c["text"]]
    if not caps or length <= 0.2:
        return []
    weights = [_weight(c["text"]) for c in caps]
    tot = sum(weights)
    els, t = [], start
    for c, w in zip(caps, weights):
        d = length * w / tot
        el = E.caption(c["text"], c["highlight"], t, t + d, ctx)
        if el:
            els.append(el)
        t += d
    return els


def _pick_in(trim: str, clip_len: float, need: float) -> float:
    if clip_len <= need + 0.05:
        return 0.0
    if trim == "middle":
        return (clip_len - need) / 2
    if trim == "end":
        return max(0.0, clip_len - need - 0.25)
    return min(0.35, clip_len - need)   # skip the shaky first frames


def _talking_pieces(path, max_gap=0.3):
    """Speech islands → jump-cut pieces (pauses removed), with natural padding."""
    info = media.probe(path)
    isl = media.speech_islands(path)
    if not isl:
        return [(0.0, info["duration"])]
    merged = [list(isl[0])]
    for s, e in isl[1:]:
        if s - merged[-1][1] <= max_gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    dur = info["duration"]
    return [(max(0.0, s - 0.08), min(dur, e + 0.14)) for s, e in merged if e - s > 0.15]


def resolve(video: dict, assign: dict, footage_dir: Path, product_images: list, settings: dict,
            work_dir: Path, log=print, narration_dir: Path | None = None) -> Resolved:
    R = Resolved()
    ctx = E.Ctx(video)
    shots = {s["id"]: s for s in video["shots"]}
    mode = video["audio_mode"]
    tts_voice, rate = settings.get("tts_voice", "Kanya"), int(settings.get("tts_rate", 185))
    vo_file = None
    nar = (assign.get("narration") or {}).get(video["id"])
    if nar and narration_dir and (narration_dir / nar).exists():
        vo_file = narration_dir / nar      # your narration (video or audio) — its audio is used
        mode = "voiceover"                 # narration replaces on-camera sound for this video
    else:
        vo_name = (assign.get("vo") or {}).get(video["id"])
        if vo_name and (footage_dir / vo_name).exists():
            vo_file = footage_dir / vo_name
    wants_tts = settings.get("voice_source", "mine") == "tts"
    use_tts = mode == "voiceover" and not vo_file and wants_tts
    tts_ok = use_tts and tts.available(tts_voice)
    if mode == "voiceover" and not vo_file and not wants_tts:
        R.notes.append("No voice-over recording found for this video — rendering with captions only. "
                       "Record the script in one take (any filename) and drop it in.")
    elif use_tts and not tts_ok:
        R.notes.append(f"Thai TTS voice '{tts_voice}' not found — rendering without voice-over (captions still show). "
                       "On a Mac: System Settings → Accessibility → Spoken Content → System voice → Manage Voices → Thai → Kanya.")
    speech_chunks = []   # (t, np.ndarray)
    work_dir.mkdir(parents=True, exist_ok=True)

    # --- your own recorded voice-over: one take per video, split into lines ------
    vo_chunks = {}
    if vo_file and mode == "voiceover":
        vo_beats = [i for i, b in enumerate(video["timeline"]) if b["vo_th"]]
        chunks = voice.split_recording(vo_file, [_weight(video["timeline"][i]["vo_th"]) for i in vo_beats])
        if chunks:
            vo_chunks = dict(zip(vo_beats, chunks))
            R.notes.append(f"Using your voice-over '{vo_file.name}' (split into {len(chunks)} lines).")
        else:
            vo_file = None

    t = 0.0
    product_images = [p for p in product_images if Path(p).exists()]
    for bi, b in enumerate(video["timeline"]):
        shot = shots.get(b["shot_id"], {"id": b["shot_id"], "audio": "mute", "shot_size": "medium"})
        fname = (assign.get("shots") or {}).get(b["shot_id"])
        path = footage_dir / fname if fname and (footage_dir / fname).exists() else None
        if path is None and shot.get("shot_size") == "product_photo" and product_images:
            path = Path(product_images[bi % len(product_images)])
        kind = media.kind(path) if path else "color"
        info = media.probe(path) if kind == "video" else {"duration": 0, "has_audio": False}
        speed = b["speed"] if kind == "video" else 1.0
        t0 = t
        caps = b["captions"] or (_chunk_text(b["vo_th"]) if b["vo_th"] else [])

        talking = (mode == "talking" and shot.get("audio") == "sync" and kind == "video" and info["has_audio"])
        if talking:
            pieces = _talking_pieces(path)
            for k, (s, e) in enumerate(pieces):
                d = (e - s) / speed
                R.segments.append(Segment(str(path), kind, s, d, speed, True,
                                          b["effect"] if k == 0 else ("punch_in" if k % 2 else "none")))
                t += d
            beat_len = t - t0
            R.elements += _caption_elements(caps, t0 + 0.05, beat_len - 0.1, ctx)
        else:
            speak_len = 0.0
            if b["vo_th"] and mode == "voiceover":
                y = vo_chunks.get(bi)
                if y is None and tts_ok:
                    y = tts.synth(b["vo_th"], work_dir / f"{video['id']}_b{bi:02d}.wav", tts_voice, rate)
                if y is not None and len(y):
                    speak_len = len(y) / SR
                    speech_chunks.append((t0 + 0.1, y))
                if not speak_len:
                    speak_len = tts.estimate_seconds(b["vo_th"])
                beat_len = max(speak_len + 0.25, min(b["duration"], speak_len + 0.9))
            else:
                beat_len = b["duration"]
            if kind == "video":
                need = beat_len * speed
                clip_len = info["duration"]
                if 0 < clip_len < need and speed > 0.6:  # stretch a short clip a little before freezing
                    speed = max(0.6, clip_len / beat_len)
                    need = beat_len * speed
                src_in = _pick_in(b["trim"], clip_len, need)
            else:
                src_in = 0.0
            if kind == "color":
                R.missing.append(b["shot_id"])
                R.elements.append(E.missing_card(shot, t0, t0 + beat_len))
            R.segments.append(Segment(str(path) if path else None, kind, src_in, beat_len, speed, False, b["effect"]))
            t += beat_len
            cap_start = t0 + 0.1 if speak_len else t0 + 0.05
            cap_len = speak_len if speak_len else beat_len - 0.1
            R.elements += _caption_elements(caps, cap_start, cap_len, ctx)
        R.beats.append((t0, t))
        if b["effect"] == "flash":
            R.elements.append(E.flash(t0))

    R.total = round(t * FPS) / FPS
    # --- overlays (absolute times) -------------------------------------------
    for bi, b in enumerate(video["timeline"]):
        t0, t1 = R.beats[bi]
        for o in b["overlays"]:
            s = t0 + min(o["at"], max(0.0, t1 - t0 - 0.2))
            e = min(R.total, s + o["dur"])
            if o["type"] == "cta_basket" and bi == len(video["timeline"]) - 1:
                e = R.total
            R.elements += E.build_overlay(o, s, e, ctx)
    if video.get("progress_bar"):
        R.progress_color = ctx.theme["accent"]
    R.elements.sort(key=lambda el: el.z)

    # --- speech track ---------------------------------------------------------
    n = int(R.total * SR) + SR
    speech = np.zeros(n, dtype=np.float32)
    for at, y in speech_chunks:
        i = int(at * SR)
        seg = y[: max(0, n - i)]
        speech[i:i + len(seg)] += seg
    R.speech = speech
    return R
