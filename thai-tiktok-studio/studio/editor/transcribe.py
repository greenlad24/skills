"""Hear your narration: Thai speech → text with times, on your Mac (Whisper, free, offline after setup).

Used to (1) recognise WHICH script each voice recording reads, so only those videos are made,
and (2) cut on the words you actually said. The speech engine (faster-whisper) and its model
(~460 MB) are installed the first time they're needed; if that fails, everything still works
the old way (recordings matched in recording order, cuts by text length).
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import re
import subprocess
import sys
import threading
from difflib import SequenceMatcher
from pathlib import Path

from .. import config

MODEL = "small"
_LOCK = threading.Lock()
_MODEL = None


def installed() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def ensure(log=print) -> bool:
    if installed():
        return True
    log("Installing speech recognition (one time, about 1–2 minutes)…")
    p = subprocess.run([sys.executable, "-m", "pip", "install", "--prefer-binary", "faster-whisper>=1.0"],
                       capture_output=True, text=True)
    importlib.invalidate_caches()
    if p.returncode != 0 or not installed():
        log("Speech recognition couldn't be installed — recordings are matched in recording order instead.")
        return False
    return True


def _model(log):
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel
        root = config.HOME / "models"
        if not any(root.glob(f"**/*{MODEL}*")):
            log("Downloading the Thai speech model (one time, about 460 MB)…")
        _MODEL = WhisperModel(MODEL, device="cpu", compute_type="int8", download_root=str(root))
    return _MODEL


def _key(path: Path) -> str:
    st = path.stat()
    return hashlib.sha1(f"{path.name}|{st.st_size}|{st.st_mtime}".encode()).hexdigest()[:16]


def _run(path: Path, log) -> dict:
    """→ {"text": str, "words": [{"w", "s", "e"}]} (times in seconds of the original file)."""
    with _LOCK:
        m = _model(log)
        segs, _ = m.transcribe(str(path), language="th", word_timestamps=True, beam_size=5,
                               condition_on_previous_text=False)
        words = []
        for s in segs:
            for w in (s.words or []):
                if w.word.strip():
                    words.append({"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)})
    return {"text": "".join(w["w"] for w in words), "words": words}


def transcript(path: Path, cache_dir: Path, log=print, allow_install: bool = True) -> dict | None:
    """Cached per file. None when speech recognition isn't available."""
    path = Path(path)
    f = cache_dir / f"{_key(path)}.json"
    if f.exists():
        try:
            return json.loads(f.read_text("utf-8"))
        except ValueError:
            pass
    if not (installed() or (allow_install and ensure(log))):
        return None
    try:
        log(f"Listening to {path.name}…")
        t = _run(path, log)
    except Exception as e:      # model download failed, unreadable audio… → old behaviour
        log(f"Couldn't transcribe {path.name} ({str(e)[:120]}).")
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(t, ensure_ascii=False), "utf-8")
    return t


# --------------------------------------------------------------------------- text matching
_KEEP = re.compile(r"[^0-9a-zก-ฮะ-ฺเ-๎]+")


def norm(text: str) -> str:
    """Letters only (Thai + latin + digits), no spaces/punctuation — robust to how Whisper splits words."""
    return _KEEP.sub("", (text or "").lower())


def similarity(said: str, script: str) -> float:
    a, b = norm(said), norm(script)
    if not a or not b:
        return 0.0
    sm = SequenceMatcher(None, a, b, autojunk=False).ratio()
    tri = lambda s: {s[i:i + 3] for i in range(max(0, len(s) - 2))}
    ta, tb = tri(a), tri(b)
    jac = len(ta & tb) / max(1, len(ta | tb))
    return round(0.5 * sm + 0.5 * jac, 3)


def script_of(video: dict) -> str:
    return " ".join(b["vo_th"] for b in video.get("timeline", []) if b.get("vo_th")) or video.get("full_script_th", "")


def match(transcripts: dict, videos: list, min_score: float = 0.2) -> dict:
    """{file: transcript} + plan videos → {file: (video_id, score)}, each script used at most once."""
    pairs = sorted(((similarity(t["text"], script_of(v)), f, v["id"]) for f, t in transcripts.items() if t
                    for v in videos), reverse=True)
    out, used_f, used_v = {}, set(), set()
    for score, f, vid in pairs:
        if score < min_score or f in used_f or vid in used_v:
            continue
        out[f] = (vid, score)
        used_f.add(f)
        used_v.add(vid)
    return out


def beat_starts(words: list, video: dict) -> list:
    """Time (original file) where each spoken beat of the script starts, from what was actually said.

    → [time | None] per timeline beat (None for silent beats or lines that weren't found).
    """
    stream, times = [], []
    for w in words:
        t = norm(w["w"])
        for k, ch in enumerate(t):
            stream.append(ch)
            times.append(w["s"] + (w["e"] - w["s"]) * k / max(1, len(t)))
    said = "".join(stream)
    script, owner = [], []
    for bi, b in enumerate(video.get("timeline", [])):
        t = norm(b.get("vo_th", ""))
        script.append(t)
        owner += [bi] * len(t)
    script = "".join(script)
    if not said or not script:
        return [None] * len(video.get("timeline", []))
    pos = {}
    for blk in SequenceMatcher(None, script, said, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            pos[blk.a + k] = blk.b + k
    out, start = [], 0
    for bi, b in enumerate(video.get("timeline", [])):
        n = len(norm(b.get("vo_th", "")))
        i0 = next((i for i in range(start, start + n) if i in pos), None) if n else None
        # first recognised letter of the line, moved back by the letters before it (~12 Thai letters/s)
        out.append(max(0.0, times[pos[i0]] - (i0 - start) / 12.0) if i0 is not None and i0 - start < n * 0.6 else None)
        start += n
    # keep it in order (a later line can't start before an earlier one)
    last = -1.0
    for i, t in enumerate(out):
        if t is not None:
            if t < last:
                out[i] = None
            else:
                last = t
    return out


# --------------------------------------------------------------------------- one recording, several scripts
def _tri(s: str) -> set:
    return {s[i:i + 3] for i in range(max(0, len(s) - 2))}


def split(words: list, videos: list, gap: float = 0.5, min_cover: float = 0.4) -> list:
    """You read several scripts in ONE recording → [(video_id, t0, t1, coverage)] in recording order.

    The recording is cut into sentences at pauses; each sentence is labelled with the script it belongs
    to (or none, for chit-chat), preferring to stay on the same script; each script keeps its most
    complete reading (a later retake wins a tie). Returns [] when fewer than 2 scripts were read.
    """
    if not words or len(videos) < 2:
        return []
    chunks = []
    for w in words:
        if chunks and w["s"] - chunks[-1]["e"] < gap:
            chunks[-1]["e"], chunks[-1]["t"] = w["e"], chunks[-1]["t"] + w["w"]
        else:
            chunks.append({"s": w["s"], "e": w["e"], "t": w["w"]})
    scripts = [(v["id"], _tri(norm(script_of(v)))) for v in videos]
    scripts = [(vid, t) for vid, t in scripts if t]
    if len(scripts) < 2:
        return []
    labels = [None] + [vid for vid, _ in scripts]
    tris = dict(scripts)

    def emit(ch, lab):
        t = _tri(norm(ch["t"]))
        if len(t) < 2:
            return 0.0                       # "เอ่อ", "โอเค" — fits anywhere
        return 0.3 if lab is None else len(t & tris[lab]) / len(t)
    SWITCH = 0.25
    best = {lab: (emit(chunks[0], lab), [lab]) for lab in labels}
    for ch in chunks[1:]:
        nxt = {}
        for lab in labels:
            prev, path = max(((sc - (SWITCH if pl != lab else 0.0), p) for pl, (sc, p) in best.items()),
                             key=lambda x: x[0])
            nxt[lab] = (prev + emit(ch, lab), path + [lab])
        best = nxt
    path = max(best.values(), key=lambda x: x[0])[1]
    runs = []
    for ch, lab in zip(chunks, path):
        if runs and runs[-1]["lab"] == lab:
            runs[-1]["e"], runs[-1]["t"] = ch["e"], runs[-1]["t"] + ch["t"]
        else:
            runs.append({"lab": lab, "s": ch["s"], "e": ch["e"], "t": ch["t"]})
    pick = {}
    for r in runs:
        if r["lab"] is None:
            continue
        cover = len(_tri(norm(r["t"])) & tris[r["lab"]]) / len(tris[r["lab"]])
        if cover >= min_cover and (r["lab"] not in pick or cover >= pick[r["lab"]][3] - 0.1):
            pick[r["lab"]] = (r["lab"], r["s"], r["e"], round(cover, 3))
    out = sorted(pick.values(), key=lambda x: x[1])
    if len(out) < 2:
        return []
    res = []
    for i, (vid, s, e, cov) in enumerate(out):        # a little air around each reading, never into the next
        lo = out[i - 1][2] if i else 0.0
        hi = out[i + 1][1] if i + 1 < len(out) else e + 0.6
        res.append((vid, round(max(lo, s - 0.3), 3), round(min(hi, e + 0.45), 3), cov))
    return res
