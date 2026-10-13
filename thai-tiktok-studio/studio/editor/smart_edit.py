"""Smart edit: the voice drives the video, Claude Opus picks the pictures.

1. The voice is ONE continuous track — your narration (only the silence before the first
   word and after the last word is removed), or in talking videos your on-camera clips
   joined only at real pauses. It is never chopped into per-line pieces.
2. Claude Opus sees every clip you uploaded (3 frames each), how long each clip is, when
   each phrase of the voice is spoken and the script — and writes an edit decision list
   (EDL) that only uses those clips. Cuts land on phrase boundaries; clips may be reused
   from other in-points; there are never gaps or "missing footage" cards.
3. Without AI (copy/paste mode, or if the AI call fails) a built-in editor does the same
   job: phrase-based cuts, the shot the script asked for when it was filmed, otherwise
   the next best clip you uploaded.
4. Pacing and look follow YOUR style reference (built in from your best posted edit, or a
   reference video uploaded in Settings): calm 2.5-6 s shots, no zoom punches or flashes.
5. Graphics are exactly the plan's animations (re-timed to when their words are spoken).
   Subtitles are not shown. Prices never appear.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ..plan_schema import EFFECTS
from . import audio_io, elements as E, matcher, media, orient, reference, tts, voice
from .timeline import FPS, SR, Resolved, Segment, _weight

LEAD = 0.15          # silence before the first word
TAIL = 0.6           # picture after the last word (lets the CTA breathe)
MIN_SEG = 0.45       # shortest shot on screen
MAX_SEG = 3.6        # longest shot before the built-in editor changes picture
AROLL = "AROLL"      # talking videos: "show the person speaking, in sync"


# --------------------------------------------------------------------------- data
@dataclass
class Clip:
    id: str
    path: str
    kind: str            # video | image
    type: str            # talk | broll | photo
    duration: float      # inf for photos
    shots: list = field(default_factory=list)   # planned shot ids this file was matched to
    crop: str = ""       # black bars baked into the picture → cropped off
    rotate: int = 0      # degrees clockwise to make it upright (Claude's vision check)

    @property
    def pre(self) -> str:
        return ",".join(x for x in (self.crop, orient.ffmpeg_filter(self.rotate)) if x)


@dataclass
class Spine:
    """The audio the video is built around."""
    audio: np.ndarray | None           # mono float32 @48k, already placed (starts at t=0)
    total: float
    phrases: list                      # [(t0, t1)] spoken phrases on the output timeline
    aroll: list = field(default_factory=list)   # talking: [(t0, t1, path, src_in)]
    source: str = "none"               # narration | talking | tts | none
    report: dict = field(default_factory=dict)   # voice clean-up: breaths / false starts / pauses


# --------------------------------------------------------------------------- clips
def clip_catalog(files: list, product_images: list, assign: dict, work_dir: Path | None = None) -> list:
    by_name = {}
    for sid, name in (assign.get("shots") or {}).items():
        by_name.setdefault(name, []).append(sid)
    out = []
    for f in sorted(files, key=matcher.order_key):
        p = Path(f)
        k = media.kind(p)
        if k != "video":          # only the clips you filmed — no photos / product images
            continue
        if k == "video":
            info = media.probe(p)
            if not info["has_video"] or info["duration"] < 0.3:
                continue
            dur = info["duration"]
        else:
            dur = float("inf")
        out.append(Clip("", str(p), k, matcher.classify(p), dur, sorted(by_name.get(p.name, []))))
    up_dir = (work_dir.parent if work_dir else Path(out[0].path).parent if out else Path(".")) / "upright"
    for i, c in enumerate(out):
        c.id = f"C{i + 1}"
        if c.kind == "image":
            c.path = orient.upright_photo(c.path, up_dir)     # phone photos stored sideways + EXIF tag
        c.crop = media.black_bars(c.path)
    return out


def _frame(path: str, t: float, w: int = 240, pre: str = "") -> Image.Image | None:
    """One frame exactly as the render will see it (same rotation handling and fix-ups)."""
    vf = (pre + "," if pre else "") + f"scale={w}:-2"
    p = subprocess.run([media.ffmpeg_exe(), "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", path,
                        "-frames:v", "1", "-vf", vf, "-f", "image2pipe", "-vcodec", "png", "-"],
                       capture_output=True)
    if p.returncode != 0 or not p.stdout:
        return None
    import io
    try:
        return Image.open(io.BytesIO(p.stdout)).convert("RGB")
    except Exception:
        return None


def contact_sheet(c: Clip, out: Path) -> Path | None:
    """3 frames (10/50/90%) side by side, labelled with the clip id — what the AI 'sees'."""
    if out.exists():
        return out
    if c.kind == "image":
        frames = [f for f in [_frame(c.path, 0, 300, c.pre)] if f]
    else:
        frames = [f for f in (_frame(c.path, c.duration * k, 240, c.pre) for k in (0.1, 0.5, 0.9)) if f]
    if not frames:
        return None
    h = max(f.height for f in frames)
    sheet = Image.new("RGB", (sum(f.width for f in frames) + 8 * (len(frames) - 1), h + 44), (20, 20, 20))
    x = 0
    for f in frames:
        sheet.paste(f, (x, 44))
        x += f.width + 8
    dur = "photo" if c.kind == "image" else f"{c.duration:.1f}s"
    ImageDraw.Draw(sheet).text((8, 12), f"{c.id}  {c.type}  {dur}", fill=(255, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=82)
    return out


# --------------------------------------------------------------------------- the voice
def _norm(y: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    return (y / peak * 0.89).astype(np.float32) if peak > 1e-4 else y.astype(np.float32)


def _fade(y: np.ndarray, ms: float = 12) -> np.ndarray:
    n = min(len(y) // 2, int(SR * ms / 1000))
    if n > 1:
        y = y.copy()
        ramp = np.linspace(0, 1, n, dtype=np.float32)
        y[:n] *= ramp
        y[-n:] *= ramp[::-1]
    return y


def narration_spine(path: Path, clean: bool = True) -> Spine | None:
    """Whole narration as one take: breaths, clicks, false starts and over-long pauses removed
    (every spoken word stays exactly as recorded), loudness normalised."""
    y = audio_io.decode(path)
    if y is None or not len(y):
        return None
    if clean:
        from . import cleanup
        out, ph, rep = cleanup.clean(_norm(y))
        if ph:
            a = max(0.0, ph[0][0] - 0.08)
            b = min(len(out) / SR, ph[-1][1] + 0.25)
            seg = _fade(_norm(out[int(a * SR): int(b * SR)]))
            total = LEAD + len(seg) / SR + TAIL
            sp = Spine(_place(seg, LEAD, total), total, [(LEAD + s - a, LEAD + e - a) for s, e in ph],
                       source="narration", report=rep)
            return sp
    ph = voice._phrases(path)
    a = max(0.0, ph[0][0] - 0.08)
    b = min(len(y) / SR, ph[-1][1] + 0.25)
    seg = _fade(_norm(y[int(a * SR): int(b * SR)]))
    total = LEAD + len(seg) / SR + TAIL
    phrases = [(LEAD + s - a, LEAD + e - a) for s, e in ph]
    return Spine(_place(seg, LEAD, total), total, phrases, source="narration")


def _place(y: np.ndarray, at: float, total: float) -> np.ndarray:
    out = np.zeros(int(total * SR) + SR, dtype=np.float32)
    i = int(at * SR)
    y = y[: max(0, len(out) - i)]
    out[i:i + len(y)] += y
    return out


def _talk_pieces(path: str) -> list:
    """Phrases of an on-camera clip, joined across normal pauses so speech is never chopped mid-sentence."""
    dur = media.probe(path)["duration"]
    isl = media.speech_islands(path, min_silence=0.3, noise_db=-35)
    if not isl:
        return [(0.0, dur)]
    merged = [list(isl[0])]
    for s, e in isl[1:]:
        if s - merged[-1][1] <= 1.2:          # breaths and natural pauses stay in
            merged[-1][1] = e
        else:                                  # a long dead gap (retake, fumbling) is skipped
            merged.append([s, e])
    return [(max(0.0, s - 0.12), min(dur, e + 0.22)) for s, e in merged if e - s > 0.25]


def talking_spine(video: dict, clips: list, assign: dict) -> Spine | None:
    shots = {s["id"]: s for s in video["shots"]}
    want = [b["shot_id"] for b in video["timeline"] if shots.get(b["shot_id"], {}).get("audio") == "sync"]
    paths, seen = [], set()
    by_shot = {sid: c for c in clips for sid in c.shots}
    for sid in want:
        c = by_shot.get(sid)
        if c and c.kind == "video" and c.path not in seen and media.probe(c.path)["has_audio"]:
            paths.append(c.path)
            seen.add(c.path)
    if not paths:
        return None
    parts, aroll, phrases, t = [], [], [], LEAD
    for p in paths:
        for s, e in _talk_pieces(p):
            y = audio_io.decode(p, s, e - s)
            if y is None or not len(y):
                continue
            parts.append((t, _fade(y)))
            aroll.append((t, t + len(y) / SR, p, s))
            for a, b in media.speech_islands(p, min_silence=0.25, noise_db=-35):
                if b > s and a < e:
                    phrases.append((t + max(a, s) - s, t + min(b, e) - s))
            t += len(y) / SR
    if not parts:
        return None
    total = t + TAIL
    audio = np.zeros(int(total * SR) + SR, dtype=np.float32)
    for at, y in parts:
        i = int(at * SR)
        audio[i:i + len(y)] += y[: len(audio) - i]
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = (audio / peak * 0.89).astype(np.float32)
    return Spine(audio, total, sorted(phrases) or [(LEAD, t)], aroll, "talking")


def tts_spine(video: dict, settings: dict, work_dir: Path) -> Spine | None:
    text = " ".join(b["vo_th"] for b in video["timeline"] if b["vo_th"]).strip()
    v, rate = settings.get("tts_voice", "Kanya"), int(settings.get("tts_rate", 185))
    if not text or not tts.available(v):
        return None
    wav = work_dir / f"{video['id']}_tts.wav"
    y = tts.synth(text, wav, v, rate)
    if y is None or not len(y):
        return None
    audio_io.write_wav(wav, y)
    sp = narration_spine(wav)
    if sp:
        sp.source = "tts"
    return sp


def silent_spine(video: dict) -> Spine:
    t, phrases = LEAD, []
    for b in video["timeline"]:
        d = max(b["duration"], tts.estimate_seconds(b["vo_th"]) if b["vo_th"] else 0)
        phrases.append((t, t + d))
        t += d
    return Spine(None, t + TAIL, phrases, source="none")


# --------------------------------------------------------------------------- beats ↔ voice
def beat_windows(video: dict, sp: Spine) -> list:
    """[(t0, t1)] per beat on the output timeline, cuts snapped to the voice's phrase gaps."""
    beats = video["timeline"]
    n = len(beats)
    if not n:
        return []
    if sp.source == "none":
        return [(a, b) for a, b in sp.phrases[:n]]
    spoken = [i for i, b in enumerate(beats) if b["vo_th"]] or list(range(n))
    weights = [_weight(beats[i]["vo_th"] or "x") for i in spoken]
    ph = sp.phrases or [(LEAD, sp.total - TAIL)]
    cuts = voice._choose_cuts(ph, weights)
    if len(weights) > 1 and cuts:
        bounds = [0.0] + [(ph[c][1] + ph[c + 1][0]) / 2 for c in cuts] + [sp.total]
    else:  # not enough pauses: split by text length
        s0, e0 = ph[0][0], ph[-1][1]
        wt = sum(weights) or 1
        bounds, a = [0.0], s0
        for w in weights[:-1]:
            a += (e0 - s0) * w / wt
            bounds.append(a)
        bounds.append(sp.total)
    win = {bi: (bounds[k], bounds[k + 1]) for k, bi in enumerate(spoken)}
    # silent beats borrow the start of the next spoken beat (or the end of the previous one)
    out = [None] * n
    for i in range(n):
        if i in win:
            out[i] = win[i]
    for i in range(n):
        if out[i] is not None:
            continue
        j = next((k for k in range(i + 1, n) if k in win), None)
        if j is not None:
            a, b = win[j]
            cut = _gap_near(ph, a, b, a + min(beats[i]["duration"], (b - a) * 0.4), a)
            out[i], win[j] = (a, cut), (cut, b)
            out[j] = win[j]
        else:
            k = max(win)
            a, b = win[k]
            cut = _gap_near(ph, a, b, b - min(beats[i]["duration"], (b - a) * 0.4), b)
            out[i], win[k] = (cut, b), (a, cut)
            out[k] = win[k]
    return out


def _gap_near(phrases: list, a: float, b: float, target: float, none: float) -> float:
    """A pause between phrases inside (a, b) closest to target — so picture changes never land mid-word."""
    gaps = [(p[1] + q[0]) / 2 for p, q in zip(phrases, phrases[1:])]
    gaps += [phrases[0][0] - 0.05, phrases[-1][1] + 0.05]
    ok = [g for g in gaps if a + 0.4 <= g <= b - 0.4]
    return min(ok, key=lambda g: abs(g - target)) if ok else none


# --------------------------------------------------------------------------- pace (from the style reference)
CALM_DROP = {"punch_in": "none", "punch_shake": "none", "shake": "none", "flash": "none"}


def pace(prof: dict) -> dict:
    if prof.get("calm"):
        return {"calm": True, "max": min(6.5, max(3.0, prof.get("max_shot", 5.0))),
                "target": min(4.5, max(2.2, prof.get("avg_shot", 3.0)))}
    return {"calm": False, "max": MAX_SEG, "target": 2.0}


def _calm_effect(eff: str, p: dict) -> str:
    return CALM_DROP.get(eff, eff) if p["calm"] else eff


# --------------------------------------------------------------------------- built-in editor (no AI)
def _overlays_for(video, sp, windows) -> list:
    overlays = []
    for bi, b in enumerate(video["timeline"]):
        t0, t1 = windows[bi]
        for o in b["overlays"]:
            s = t0 + min(o["at"], max(0.0, t1 - t0 - 0.3))
            e = sp.total if o["type"] == "cta_basket" and bi == len(windows) - 1 else min(sp.total, s + o["dur"])
            overlays.append(dict(o, at=round(s, 2), dur=round(e - s, 2)))
    return overlays


def _snap(t: float, gaps: list, lo: float, hi: float) -> float:
    near = [g for g in gaps if lo <= g <= hi and abs(g - t) <= 1.5]
    return min(near, key=lambda g: abs(g - t)) if near else min(max(t, lo), hi)


def _fit(c: "Clip", ln: float) -> tuple:
    """(in_point, speed) to fill ln seconds with ONE pass of clip c: trim if longer, slow down if shorter."""
    use = max(0.4, c.duration - 0.45)                 # skip the shaky first/last moments
    if use >= ln:
        return min(0.25, c.duration - ln) + (use - ln) * 0.15, 1.0
    return 0.0, max(0.5, min(1.0, (c.duration - 0.05) / ln))   # beyond 0.5x the last frame is held


def chrono_edl(video: dict, clips: list, sp: Spine, windows: list, p: dict) -> dict:
    """Each clip you filmed appears ONCE, in the order you filmed it (= the order of the steps).

    Clips get time in proportion to their length; cuts snap to pauses in the voice. When there is more
    voice than footage, clips play slower instead of repeating.
    """
    D = sp.total
    vids = [c for c in clips if c.kind == "video"]
    lengths = [max(0.4, c.duration - 0.45) for c in vids]
    scale = D / sum(lengths)
    gaps = [(x[1] + y[0]) / 2 for x, y in zip(sp.phrases, sp.phrases[1:])]
    cut_ix = voice._choose_cuts(sp.phrases, lengths) if 0 < len(lengths) - 1 <= len(gaps) else []
    if cut_ix:   # every clip change sits in a pause of the voice (best overall fit, in order)
        bounds = [0.0] + [gaps[i] for i in cut_ix] + [D]
    else:        # more clips than pauses: proportional, snapped to the nearest free pause
        bounds, t = [0.0], 0.0
        for ln in lengths[:-1]:
            t += ln * scale
            bounds.append(_snap(t, gaps, bounds[-1] + MIN_SEG, D - MIN_SEG))
        bounds.append(D)
    segs = []
    for k, c in enumerate(vids):
        a, b = bounds[k], bounds[k + 1]
        if b - a < 0.05:
            continue
        src_in, speed = _fit(c, b - a)
        eff = "slow_zoom" if (len(segs) % 2 == 1 and b - a >= 2.0) else "none"
        if not segs:
            eff = _calm_effect(video["timeline"][0]["effect"] if video["timeline"] else "none", p)
        segs.append({"start": a, "end": b, "clip": c.id, "in": src_in, "effect": eff, "speed": speed})
    if segs:
        segs[0]["start"], segs[-1]["end"] = 0.0, D
    return {"segments": segs, "overlays": _overlays_for(video, sp, windows), "notes": "built-in editor"}


def talking_edl(video: dict, clips: list, sp: Spine, windows: list, p: dict) -> dict:
    """Talking video: the speaker in sync, with each B-roll clip shown ONCE as a cutaway (filmed order)."""
    shots = {x["id"]: x for x in video["shots"]}
    talk_paths = {r[2] for r in sp.aroll}
    broll = [c for c in clips if c.kind == "video" and c.path not in talk_paths]
    slots = [w for b, w in zip(video["timeline"], windows) if shots.get(b["shot_id"], {}).get("audio") != "sync"]
    segs, t = [], 0.0
    for c, (a, b) in zip(broll, slots):
        a, b = max(a, t), min(b, a + max(1.2, c.duration - 0.45))
        if b - a < MIN_SEG:
            continue
        if a - t > 0.05:
            segs.append({"start": t, "end": a, "clip": AROLL, "in": 0.0, "effect": "none", "speed": 1.0})
        src_in, speed = _fit(c, b - a)
        segs.append({"start": a, "end": b, "clip": c.id, "in": src_in, "effect": "none", "speed": speed})
        t = b
    if sp.total - t > 0.05:
        segs.append({"start": t, "end": sp.total, "clip": AROLL, "in": 0.0, "effect": "none", "speed": 1.0})
    return {"segments": segs, "overlays": _overlays_for(video, sp, windows), "notes": "built-in editor"}


def fallback_edl(video: dict, clips: list, sp: Spine, windows: list, p: dict | None = None) -> dict:
    p = p or pace(reference.DEFAULT_PROFILE)
    return talking_edl(video, clips, sp, windows, p) if sp.aroll else chrono_edl(video, clips, sp, windows, p)


# --------------------------------------------------------------------------- AI editor
EDL_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["segments", "notes"],
    "properties": {
        "segments": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["start", "end", "clip", "in", "effect"],
            "properties": {
                "start": {"type": "number"}, "end": {"type": "number"},
                "clip": {"type": "string", "description": "A clip id like 'C3' (or 'AROLL' in talking videos)."},
                "in": {"type": "number", "description": "Seconds into the clip where this shot starts."},
                "effect": {"type": "string", "enum": EFFECTS},
            }}},
        "notes": {"type": "string", "description": "One line: the editing idea."},
    },
}


def edl_prompt(video: dict, clips: list, sp: Spine, windows: list, draft: dict, sheet_names: dict,
               prof: dict | None = None, ref_sheet: str = "") -> str:
    prof = prof or reference.DEFAULT_PROFILE
    p = pace(prof)
    beats = []
    for i, (b, (t0, t1)) in enumerate(zip(video["timeline"], windows)):
        beats.append({"beat": i + 1, "time": [round(t0, 2), round(t1, 2)], "role": b["role"],
                      "planned_shot": b["shot_id"], "spoken_th": b["vo_th"], "effect": b["effect"]})
    shots = {s["id"]: s.get("what_to_film_th", "") for s in video["shots"]}
    cl = [{"id": c.id, "type": c.type, "seconds": None if c.kind == "image" else round(c.duration, 2),
           "matched_to_planned_shot": c.shots, "what_that_shot_should_show": [shots.get(s, "") for s in c.shots],
           "frames_image": sheet_names.get(c.id, "")} for c in clips]
    talking = bool(sp.aroll)
    graphics = [{"type": o["type"], "text": o["text"], "at": o["at"], "dur": o["dur"]} for o in draft.get("overlays", [])]
    return f"""You are a top Thai TikTok Shop video editor. Edit ONE short vertical affiliate video.

THE VOICE IS FIXED and THE ANIMATED GRAPHICS ARE FIXED. It is one continuous take, {sp.total:.2f} s long including a short tail. Never cut,
reorder or shorten it — your job is only the PICTURE: which clip is on screen when.
Spoken phrases (seconds on the final video): {json.dumps([[round(a, 2), round(b, 2)] for a, b in sp.phrases])}

Script beats (what is said when, and which shot the script planned):
{json.dumps(beats, ensure_ascii=False, indent=1)}

The ONLY footage that exists (the creator filmed these; nothing else is available):
{json.dumps(cl, ensure_ascii=False, indent=1)}
Look at each clip's frames image (3 frames from 10%, 50%, 90% of the clip, labelled with its id) to see
what it really shows — the matching to planned shots was automatic and may be wrong.
{"'AROLL' = the creator speaking on camera, in sync with the voice. Use it for most talking moments and cut to other clips as cutaways." if talking else ""}

RULES
- segments must cover 0 → {sp.total:.2f} exactly: sorted, contiguous (each start = previous end), no gaps.
- Cut on phrase boundaries or between words — never in the middle of a word.
- PACING: copy the creator's own style reference below — typical shot {p["target"]:.1f} s, up to {p["max"]:.1f} s.
- Show what is being said: when the voice talks about a feature/result, pick the clip that shows it.
- ORDER: the clips are listed in the order the creator FILMED them, which is the order of the steps
  (C1 first). Keep that order: a clip may only appear after all earlier clips' moments, never jump back to an
  earlier clip. Use EVERY clip EXACTLY ONCE as one continuous shot — never show the same clip twice, never
  split one clip into several shots. Skip a clip only if it is broken. Video clips: in + (end - start) must be
  <= the clip's seconds (a clip may run up to 2x slower if the voice is longer than the footage).
- Never use a clip that looks broken, black, or a retake fumble if a better one exists.
- First 1.5 s must be the most eye-catching footage.
- effect: {"slow_zoom (a gentle zoom the creator likes) on about every other shot, otherwise none; never shake or flash" if p["calm"] else "punch_in / punch_shake on emphasis, slow_zoom on calm shots, flash at most once, otherwise none"}.

THE CREATOR'S STYLE REFERENCE (their best-performing posted edit — match its rhythm and feel):
{reference.describe(prof)}
{("Frames of the reference video: " + ref_sheet) if ref_sheet else ""}

The plan's animated graphics will appear at these times (keep the footage under them relevant):
{json.dumps(graphics, ensure_ascii=False)}

Draft cut list from the built-in editor (improve it; you may change every segment):
{json.dumps(draft["segments"], ensure_ascii=False)}

Reply with ONE JSON object: {{"segments":[...], "notes":"..."}}"""


def ai_ready(settings: dict) -> bool:
    provider = settings.get("provider", "claude_code")
    key = {"claude": "anthropic_api_key", "openai": "openai_api_key", "claude_code": "claude_code_token"}.get(provider)
    return bool(key and settings.get(key))


def build_sheets(clips: list, work_dir: Path) -> dict:
    sheets = {}
    for c in clips:
        tag = hashlib.sha1(c.pre.encode()).hexdigest()[:6]
        p = contact_sheet(c, work_dir / "sheets" / f"{c.id}_{_short_hash(c.path)}_{tag}.jpg")
        if p:
            sheets[c.id] = str(p.resolve())
    return sheets


def ai_edl(video, clips, sp, windows, draft, settings, work_dir: Path, log, prof: dict | None = None,
           sheets: dict | None = None) -> dict | None:
    if not ai_ready(settings):
        return None
    provider = settings.get("provider", "claude_code")
    sheets = sheets if sheets is not None else build_sheets(clips, work_dir)
    ref = reference.sheet_path()
    prompt = edl_prompt(video, clips, sp, windows, draft, {k: Path(v).name for k, v in sheets.items()}, prof,
                        ref.name if ref else "")
    from ..planner import _provider
    mod = _provider(provider)
    log("Claude is watching your clips and planning the edit…")
    images = list(sheets.values()) + ([str(ref.resolve())] if ref else [])
    return mod.make_edl(prompt, images, EDL_SCHEMA, settings, log=log, workdir=work_dir)


def _short_hash(s: str) -> str:
    p = Path(s)
    st = p.stat() if p.exists() else None
    return hashlib.sha1(f"{s}|{st.st_mtime if st else 0}|{st.st_size if st else 0}".encode()).hexdigest()[:10]


# --------------------------------------------------------------------------- validation
def validate_edl(edl: dict, clips: list, sp: Spine, fallback: dict, p: dict | None = None) -> dict:
    """Make any EDL safe: full coverage, real clips, in-points inside the clip, no slivers."""
    ids = {c.id: c for c in clips}
    total = sp.total
    segs = []
    for s in (edl or {}).get("segments") or []:
        try:
            a, b = float(s["start"]), float(s["end"])
        except (KeyError, TypeError, ValueError):
            continue
        clip = str(s.get("clip", "")).strip().upper()
        if clip != AROLL and clip not in ids or clip == AROLL and not sp.aroll:
            continue
        a, b = max(0.0, a), min(total, b)
        if b - a < 0.05:
            continue
        eff = s.get("effect") if s.get("effect") in EFFECTS else "none"
        if p:
            eff = _calm_effect(eff, p)
        try:
            src_in = max(0.0, float(s.get("in", 0)))
        except (TypeError, ValueError):
            src_in = 0.0
        try:
            spd = min(1.0, max(0.5, float(s.get("speed", 1.0))))
        except (TypeError, ValueError):
            spd = 1.0
        segs.append({"start": a, "end": b, "clip": clip, "in": src_in, "effect": eff, "speed": spd})
    segs.sort(key=lambda s: s["start"])
    if not segs:
        return fallback
    # contiguous coverage 0 → total (overlaps trimmed, gaps closed by stretching the earlier shot)
    segs[0]["start"] = 0.0
    out = [segs[0]]
    for s in segs[1:]:
        prev = out[-1]
        if s["start"] >= total:
            break
        if s["end"] <= prev["start"] + 0.05:
            continue
        s["start"] = prev["end"] = s["start"] if s["start"] > prev["start"] + 0.05 else prev["end"]
        if s["end"] - s["start"] > 0.05:
            out.append(s)
    out[-1]["end"] = total
    # merge slivers into their neighbour
    merged = []
    for s in out:
        if merged and s["end"] - s["start"] < MIN_SEG * 0.6:
            merged[-1]["end"] = s["end"]
        else:
            merged.append(s)
    if len(merged) > 1 and merged[0]["end"] - merged[0]["start"] < MIN_SEG * 0.6:
        merged[1]["start"] = 0.0
        merged.pop(0)
    # the steps must stay in the order they were filmed (C1 → Cn): put the chosen footage back in order
    order = [c.id for c in clips]
    rank = {cid: i for i, cid in enumerate(order)}
    own = [s for s in merged if s["clip"] != AROLL]
    keys = [(rank[s["clip"]], s["in"]) for s in own]
    if keys != sorted(keys):
        picks = sorted(((rank[s["clip"]], s["in"], s["clip"], s["speed"]) for s in own))
        for s, (_, src_in, cid, spd) in zip(own, picks):
            s["clip"], s["in"], s["speed"] = cid, src_in, spd
    # each clip ONCE: a repeat of a clip already shown becomes more time for the shot before it
    seen, dedup = set(), []
    for s in merged:
        if s["clip"] != AROLL and s["clip"] in seen and dedup:
            dedup[-1]["end"] = s["end"]
            continue
        seen.add(s["clip"])
        if dedup and s["clip"] == AROLL and dedup[-1]["clip"] == AROLL:
            dedup[-1]["end"] = s["end"]
            continue
        dedup.append(s)
    merged = dedup
    # clip length limits: shift the in-point back, else play it slower (never fill with another clip)
    fixed = []
    for s in merged:
        while True:
            ln = (s["end"] - s["start"]) * s.get("speed", 1.0)
            c = ids.get(s["clip"])
            if c is None or c.kind == "image":
                if c is not None:
                    s["in"] = 0.0
                fixed.append(s)
                break
            usable = max(0.1, c.duration - 0.05)
            if s["in"] + ln <= usable:
                fixed.append(s)
                break
            if ln <= usable:
                s["in"] = max(0.0, usable - ln)
                fixed.append(s)
                break
            s["in"], s["speed"] = 0.0, max(0.5, min(1.0, usable / max(0.1, s["end"] - s["start"])))
            fixed.append(s)
            break
    return {"segments": fixed, "overlays": fallback.get("overlays", []), "notes": str((edl or {}).get("notes", ""))[:300]}


# --------------------------------------------------------------------------- EDL → renderable timeline
def to_resolved(video: dict, edl: dict, clips: list, sp: Spine) -> Resolved:
    R = Resolved()
    ctx = E.Ctx(video)
    ids = {c.id: c for c in clips}
    pre_by_path = {c.path: c.pre for c in clips}
    for s in edl["segments"]:
        a, b = s["start"], s["end"]
        if s["clip"] == AROLL:
            pieces = _aroll_cover(sp.aroll, a, b)
            for k, (path, src, d) in enumerate(pieces):
                R.segments.append(Segment(path, "video", src, d, 1.0, False, s["effect"] if k == 0 else "none",
                                          pre=pre_by_path.get(path, "")))
        else:
            c = ids.get(s["clip"])
            if c is None:
                R.segments.append(Segment(None, "color", 0.0, b - a, 1.0, False, "none"))
            else:
                eff = s["effect"]
                if c.kind == "image" and eff == "none":
                    eff = "slow_zoom"
                R.segments.append(Segment(c.path, c.kind, s["in"], b - a, s.get("speed", 1.0), False, eff, pre=c.pre))
        if s["effect"] == "flash":
            R.elements.append(E.flash(a))
        R.beats.append((a, b))
    R.total = round(sp.total * FPS) / FPS
    _snap_to_frames(R)
    for o in edl["overlays"]:
        if o.get("hidden"):        # removed on the review screen
            continue
        s = o["at"]
        e = min(R.total, s + o["dur"])
        if o["type"] == "cta_basket" and e > R.total - 1.0:
            e = R.total
        R.elements += E.build_overlay(o, s, e, ctx)
    if video.get("progress_bar"):
        R.progress_color = ctx.theme["accent"]
    R.elements.sort(key=lambda el: el.z)
    n = int(R.total * SR) + SR
    if sp.audio is None:
        R.speech = np.zeros(n, dtype=np.float32)
    else:
        y = sp.audio[:n]
        R.speech = np.pad(y, (0, n - len(y))) if len(y) < n else y
    return R


def _aroll_cover(aroll: list, a: float, b: float) -> list:
    """[(path, src_in, dur)] showing the speaker in sync over [a, b]; outside the talk audio, hold the nearest take."""
    out, t = [], a
    for p0, p1, path, src in aroll:
        if p1 <= t:
            continue
        if p0 >= b:
            break
        if p0 > t:      # before this piece (lead-in): show its first frames early
            out.append((path, max(0.0, src - (p0 - t)), p0 - t))
            t = p0
        hi = min(b, p1)
        out.append((path, src + (t - p0), hi - t))
        t = hi
    if b - t > 1e-3:    # tail after the last word: keep rolling the last take
        p0, p1, path, src = aroll[-1]
        out.append((path, src + (p1 - p0), b - t))
    return [x for x in out if x[2] > 1e-3]


def _snap_to_frames(R: Resolved) -> None:
    """Segment lengths on whole frames, summing exactly to the total (no drift between voice and picture)."""
    t_prev, acc = 0, 0.0
    for seg in R.segments:
        acc += seg.dur
        f = int(round(acc * FPS))
        seg.dur = max(1, f - t_prev) / FPS
        t_prev = t_prev + max(1, f - t_prev)
    tot = int(round(R.total * FPS))
    if R.segments and t_prev != tot:
        R.segments[-1].dur = max(1, int(round(R.segments[-1].dur * FPS)) + tot - t_prev) / FPS


# --------------------------------------------------------------------------- entry point
def resolve(video: dict, assign: dict, footage_files: list, product_images: list, settings: dict, work_dir: Path,
            log=print, narration_dir: Path | None = None, use_ai: bool = True,
            edl_override: dict | None = None) -> Resolved:
    """Plan (or, with edl_override, re-use a reviewed plan) and build the renderable timeline.

    R.edl holds the final cut list + stickers, so it can be saved for the review screen.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    clips = clip_catalog(footage_files, product_images, assign, work_dir)
    notes = []
    sp = None
    nar = (assign.get("narration") or {}).get(video["id"])
    nar_path = narration_dir / nar if nar and narration_dir and (narration_dir / nar).exists() else None
    if nar_path is None:
        vo = (assign.get("vo") or {}).get(video["id"])
        files = {Path(f).name: Path(f) for f in footage_files}
        nar_path = files.get(vo) if vo else None
    if nar_path is not None:
        sp = narration_spine(nar_path, settings.get("voice_cleanup", True))
        if sp:
            notes.append(f"Your narration '{nar_path.name}' is used as one continuous take ({sp.total - LEAD - TAIL:.1f}s).")
            r = sp.report
            if r and any(r.values()):
                notes.append(f"Voice cleaned: {r.get('false_start', 0)} false start(s), {r.get('breath', 0)} breath(s), "
                             f"{r.get('click', 0)} click(s) removed; {r.get('pauses_shortened', 0)} long pause(s) shortened.")
    if sp is None and video["audio_mode"] == "talking":
        sp = talking_spine(video, clips, assign)
        if sp:
            notes.append("Using the sound of your on-camera clips, joined only at natural pauses.")
    if sp is None and video["audio_mode"] == "voiceover" and settings.get("voice_source") == "tts":
        sp = tts_spine(video, settings, work_dir)
    if sp is None:
        sp = silent_spine(video)
        if video["audio_mode"] != "music_only":
            notes.append("No voice recording found for this video — upload your narration (any filename) "
                         "in the Narration box and render again.")
    if not clips:
        notes.append("No video clips uploaded yet — the video has a plain background. Upload your clips and render again.")
    windows = beat_windows(video, sp)
    prof = reference.load()
    pc = pace(prof)
    draft = fallback_edl(video, clips, sp, windows, pc) if clips else \
        {"segments": [{"start": 0.0, "end": sp.total, "clip": "", "in": 0.0, "effect": "none"}],
         "overlays": [], "notes": ""}
    if not clips:
        draft["overlays"] = _overlays_only(video, sp, windows)
    edl = draft
    use_claude = bool(clips) and use_ai and settings.get("provider") != "manual" and ai_ready(settings)
    for c in clips:   # upright answers already known for these files (no AI needed)
        c.rotate = orient.cached(c, work_dir.parent / "orient.json")
    sheets = {}
    if use_claude:   # make sure no clip is sideways or upside down before anything is planned
        sheets = build_sheets(clips, work_dir)
        try:
            turns = orient.check(clips, sheets, settings, work_dir.parent / "orient.json", log)
            for c in clips:
                c.rotate = turns.get(c.id, 0)
            if any(c.rotate for c in clips):
                sheets = build_sheets(clips, work_dir)
                notes.append("Turned upright: " + ", ".join(Path(c.path).name for c in clips if c.rotate))
        except Exception as e:
            log(f"Upright check unavailable ({str(e)[:160]}).")
    if any(c.crop for c in clips):
        notes.append("Removed black bars from: " + ", ".join(Path(c.path).name for c in clips if c.crop))
    if edl_override is not None:   # the reviewed edit: render exactly that (stickers as edited)
        edl = validate_edl(edl_override, clips, sp, {"overlays": edl_override.get("overlays", [])}, pc) \
            if clips else dict(draft, overlays=edl_override.get("overlays", []))
        edl["overlays"] = edl_override.get("overlays", [])
    elif use_claude and settings.get("smart_edit", True):
        key = _cache_key(video, clips, sp, settings, prof)
        cache = work_dir / f"edl_{key}.json"
        got = None
        if cache.exists():
            try:
                got = json.loads(cache.read_text("utf-8"))
                log("Re-using Claude's edit plan for these clips.")
            except ValueError:
                got = None
        if got is None:
            try:
                got = ai_edl(video, clips, sp, windows, _round(draft), settings, work_dir, log, prof, sheets)
                if got:
                    cache.write_text(json.dumps(got, ensure_ascii=False, indent=1), "utf-8")
            except Exception as e:   # the built-in editor always works
                msg = str(e)
                log(f"AI edit unavailable ({msg[:160]}) — using the built-in editor.")
                got = None
        if got:
            edl = validate_edl(got, clips, sp, draft, pc)
            if edl.get("notes"):
                notes.append("Edit idea: " + edl["notes"])
    if clips and edl is draft:
        edl = validate_edl(draft, clips, sp, draft, pc)
    R = to_resolved(video, edl, clips, sp)
    R.edl = edl
    if pc["calm"]:
        R.progress_color = None   # the creator's style has no progress bar
    R.notes = notes
    return R


def _overlays_only(video, sp, windows) -> list:
    out = []
    for bi, b in enumerate(video["timeline"]):
        t0, t1 = windows[bi]
        for o in b["overlays"]:
            s = t0 + min(o["at"], max(0.0, t1 - t0 - 0.3))
            out.append(dict(o, at=s, dur=min(sp.total - s, o["dur"])))
    return out


def _round(edl: dict) -> dict:
    return {"segments": [dict(s, start=round(s["start"], 2), end=round(s["end"], 2), **{"in": round(s["in"], 2)})
                         for s in edl["segments"]],
            "overlays": edl["overlays"]}


def _cache_key(video: dict, clips: list, sp: Spine, settings: dict, prof: dict | None = None) -> str:
    """Same clips + same voice + same script → same edit (extra animation versions re-use it)."""
    script = [(b["shot_id"], b["vo_th"], b["overlays"]) for b in video["timeline"]]
    blob = json.dumps({"clips": [(c.id, _short_hash(c.path), c.pre) for c in clips], "total": round(sp.total, 2),
                       "phrases": [(round(a, 2), round(b, 2)) for a, b in sp.phrases], "script": script,
                       "provider": settings.get("provider"), "style": prof, "v": 2}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]
