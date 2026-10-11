"""Turn a CSV export of top-performing TikToks (e.g. the "Products & inspiration" sheet)
into few-shot examples the planner reads on every run."""

from __future__ import annotations

import csv
import io
import re

from .config import HOME

EXAMPLES_PATH = HOME / "custom_examples.md"
THAI = re.compile(r"[฀-๿]")


def _num(s) -> int:
    d = re.sub(r"[^\d]", "", str(s or ""))
    return int(d) if d else 0


def _col(row: dict, *names) -> str:
    low = {k.lower().strip(): v for k, v in row.items() if k}
    for n in names:
        for k, v in low.items():
            if n in k:
                return (v or "").strip()
    return ""


def build_examples(csv_text: str, top: int = 25) -> tuple:
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    items = []
    for r in rows:
        transcript = _col(r, "trasnscription", "transcription", "transcript")
        plays = _num(_col(r, "plays", "views"))
        if not transcript or not THAI.search(transcript) or plays <= 0:
            continue
        items.append({
            "plays": plays,
            "dur": _col(r, "duration"),
            "opening": transcript[:160],
            "caption": _col(r, "caption")[:140],
            "why": _col(r, "ชอบ", "why", "like")[:220],
            "shots": _col(r, "หน้าจอ", "screen", "shots")[:120],
        })
    items.sort(key=lambda x: -x["plays"])
    items = items[:top]
    if not items:
        return "", 0
    lines = ["# Real top-performing Thai TikTok Shop videos (your own dataset)",
             "Use these as evidence of what works: hook openers, length, shot mix, and why viewers liked them. "
             "Adapt the patterns; never copy lines word for word.", ""]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. **{it['plays']:,} plays** · {it['dur']} · shots: {it['shots'] or '?'}")
        lines.append(f"   - Opening: “{it['opening']}…”")
        if it["why"]:
            lines.append(f"   - Viewer note: {it['why']}")
    return "\n".join(lines) + "\n", len(items)


def save_examples(csv_text: str) -> int:
    md, n = build_examples(csv_text)
    if n:
        EXAMPLES_PATH.parent.mkdir(parents=True, exist_ok=True)
        EXAMPLES_PATH.write_text(md, "utf-8")
    return n
