"""Formula / Hook / Pacing extraction (§2B.3–5).

LLM-driven where structure matters (formula clustering, hook classification), with a
deterministic heuristic fallback so DRY_RUN (fake LLM) still yields schema-valid,
IP-safe templates. Every template:
  * stores ABSTRACT structure/patterns with {slots}, never source sentences;
  * carries `signal_type="engagement_proxy"` and a `proxy_score` = mean of its
    supporting videos' engagement proxy (honesty contract, §2B.0);
  * records `example_video_ids` for provenance/audit only (never for copying).
"""

from __future__ import annotations

import json
from statistics import mean

from app.core.adapters import registry

from .. import config
from .extraction import MergedTranscript

# --------------------------------------------------------------------------- #
# Prompts (system sketches from §2B.3 / §2B.4)
# --------------------------------------------------------------------------- #
FORMULA_SYSTEM = (
    "You analyze Thai short-form product videos to extract REUSABLE, "
    "NON-COPYRIGHTABLE structural formulas. Output STRUCTURE and TACTICS only; NEVER "
    "reproduce, quote, or lightly paraphrase any source sentence — abstract it. Do not "
    "invent formulas unsupported by >= {min_support} videos. Return JSON with keys "
    "'name', 'beats'([{beat,purpose,typical_duration_s,example_moves}]), 'claim_cadence', "
    "'tone'(list)."
)
HOOK_SYSTEM = (
    "You classify the OPENING HOOK (first ~1.5s) of Thai product videos. Assign ONE "
    "primary hook_type. Produce an ABSTRACT opening_line_pattern with {slots} "
    "({problem},{benefit},{timeframe},{price}) — never the verbatim line. Describe "
    "visual_pattern and osd_pattern generically. Return JSON with keys 'hook_type', "
    "'opening_line_pattern', 'visual_pattern', 'osd_pattern'."
)

HOOK_TYPES = [
    "question", "bold_claim", "problem_callout", "before_after_tease",
    "negativity_warning", "curiosity_gap", "social_proof", "price_shock", "POV", "unboxing",
]


def _llm():
    return registry.get_llm_provider()


def _parse_json(text: str) -> dict | None:
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None


# --------------------------------------------------------------------------- #
# Formula (§2B.3)
# --------------------------------------------------------------------------- #
def _heuristic_formula(transcripts: list[MergedTranscript]) -> dict:
    avg_len = mean(
        [max((s.t_end for s in t.segments), default=0.0) for t in transcripts] or [0.0]
    )
    return {
        "name": "Problem-Agitate-Demo-Proof-CTA",
        "beats": [
            {"beat": "hook", "purpose": "stop the scroll", "typical_duration_s": 1.5,
             "example_moves": "big-bold OSD question over an extreme close-up"},
            {"beat": "problem", "purpose": "name the pain", "typical_duration_s": 2.5,
             "example_moves": "relatable first-person confession"},
            {"beat": "agitate", "purpose": "raise the stakes", "typical_duration_s": 2.0,
             "example_moves": "show the failed status quo"},
            {"beat": "demo", "purpose": "show the product working", "typical_duration_s": 6.0,
             "example_moves": "application / usage in one continuous shot"},
            {"beat": "proof", "purpose": "make it believable", "typical_duration_s": 4.0,
             "example_moves": "before/after split screen with a {timeframe} label"},
            {"beat": "cta", "purpose": "drive the tap", "typical_duration_s": 3.0,
             "example_moves": "cart-tap OSD + urgency"},
        ],
        "claim_cadence": "hard benefit by ~3s, proof by mid, urgency at CTA",
        "tone": ["relatable", "urgent"],
    }


def extract_formula(
    transcripts: list[MergedTranscript],
    niche: str,
    proxy_scores: list[float],
    example_video_ids: list,
    *,
    llm=None,
    min_support: int = config.MIN_SUPPORT,
) -> dict | None:
    """Extract ONE FormulaTemplate from a cluster of transcripts. None if under-supported."""
    if len(transcripts) < min_support:
        return None
    llm = llm or _llm()
    payload = "\n\n".join(
        f"VIDEO {i}: {t.merged_text[:1200]}" for i, t in enumerate(transcripts[:12])
    )
    body = None
    try:
        res = llm.complete(
            prompt="Transcripts:\n" + payload,
            system=FORMULA_SYSTEM.format(min_support=min_support),
            model=config.LLM_EXTRACT_MODEL,
            max_tokens=1024,
            idempotency_key=f"formula:{niche}:{len(transcripts)}",
        )
        if res and res.ok:
            body = _parse_json((res.data or {}).get("text", ""))
    except Exception:  # noqa: BLE001
        body = None
    if body is None or "beats" not in body:
        body = _heuristic_formula(transcripts)

    avg_len = round(
        mean([max((s.t_end for s in t.segments), default=0.0) for t in transcripts]), 2
    )
    return {
        # niche is encoded into FormulaTemplate.source (no niche column in core model).
        "name": body.get("name", "Problem-Agitate-Demo-Proof-CTA"),
        "niche": niche,
        "structure": {
            "beats": body.get("beats", []),
            "claim_cadence": body.get("claim_cadence"),
            "tone": body.get("tone", []),
            "avg_length_s": avg_len,
        },
        "support_count": len(transcripts),
        "proxy_score": round(mean(proxy_scores), 6) if proxy_scores else 0.0,
        "operator_win_score": None,
        "signal_type": "engagement_proxy",
        "example_video_ids": list(example_video_ids),
    }


# --------------------------------------------------------------------------- #
# Hook taxonomy (§2B.4)
# --------------------------------------------------------------------------- #
def _opening_window(t: MergedTranscript, t_end: float = 1.6) -> tuple[str, str]:
    vo = " ".join(s.text for s in t.segments if s.source == "vo" and s.t_start <= t_end)
    osd = " ".join(s.text for s in t.segments if s.source == "osd" and s.t_start <= t_end)
    return vo.strip(), osd.strip()


def _heuristic_hook_type(vo: str, osd: str) -> str:
    text = f"{vo} {osd}"
    if "?" in text or "ใคร" in text or "ทำไม" in text:
        return "question"
    if "อย่า" in text or "ระวัง" in text or "ห้าม" in text:
        return "negativity_warning"
    if any(c.isdigit() for c in text) and ("บาท" in text or "฿" in text):
        return "price_shock"
    if "ก่อน" in text and "หลัง" in text:
        return "before_after_tease"
    return "problem_callout"


def extract_hook(
    t: MergedTranscript,
    niche: str,
    proxy_score: float,
    example_video_id,
    *,
    llm=None,
) -> dict:
    """Classify one video's opening into an abstract HookTemplate row."""
    vo, osd = _opening_window(t)
    llm = llm or _llm()
    body = None
    try:
        res = llm.complete(
            prompt=json.dumps(
                {"opening_vo_text": vo, "opening_osd_text": osd,
                 "opening_visual_description": "representative frame at t~0.5s", "t_end": 1.6},
                ensure_ascii=False,
            ),
            system=HOOK_SYSTEM,
            model=config.LLM_CLASSIFY_MODEL,
            max_tokens=256,
            idempotency_key=f"hook:{t.tiktok_id}",
        )
        if res and res.ok:
            body = _parse_json((res.data or {}).get("text", ""))
    except Exception:  # noqa: BLE001
        body = None

    hook_type = (body or {}).get("hook_type")
    if hook_type not in HOOK_TYPES:
        hook_type = _heuristic_hook_type(vo, osd)
    pattern = (body or {}).get("opening_line_pattern")
    if not pattern:
        # Abstract slot pattern by hook_type — never the source line.
        pattern = {
            "question": "ใครที่ {problem} ห้ามพลาด",
            "negativity_warning": "อย่าซื้อ {category} ถ้ายังไม่รู้ {benefit}",
            "price_shock": "แค่ {price} ก็ได้ {benefit}",
            "before_after_tease": "{timeframe} เห็นผล {benefit}",
            "problem_callout": "ถ้าคุณมีปัญหา {problem} ลองตัวนี้",
        }.get(hook_type, "{problem} → {benefit}")

    return {
        # core HookTemplate has no niche column → encode niche in the name for scoping.
        "name": f"{niche}:{hook_type} hook",
        "niche": niche,
        "hook_type": hook_type,
        "pattern_th": pattern,
        "visual_pattern": (body or {}).get("visual_pattern", "extreme close-up / hold product to camera"),
        "osd_pattern": (body or {}).get("osd_pattern", "big bold question or countdown at t~0"),
        "duration_s": 1.6,
        "support_count": 1,
        "proxy_score": round(proxy_score, 6),
        "operator_win_score": None,
        "signal_type": "engagement_proxy",
        "example_video_ids": [example_video_id] if example_video_id else [],
    }


# --------------------------------------------------------------------------- #
# Pacing (§2B.5)
# --------------------------------------------------------------------------- #
def extract_pacing(
    tiktok_id: str,
    scenes: list,
    transcript: MergedTranscript | None,
    niche: str,
    proxy_score: float,
    example_video_id,
) -> dict:
    """Build a PacingTemplate + SceneAnalysis payload from PySceneDetect scenes.

    `scenes` are `mediatools.Scene` objects. Beat map is derived by aligning formula
    beats to scene boundaries (hook = first scene; cta = last scene)."""
    total = round(scenes[-1].end, 2) if scenes else 0.0
    shot_count = len(scenes)
    cut_rhythm = [{"idx": s.idx, "start": s.start, "end": s.end, "dur": s.dur} for s in scenes]
    avg_shot = round(mean([s.dur for s in scenes]), 3) if scenes else 0.0
    shots_per_10s = round((shot_count / total) * 10, 3) if total else 0.0

    hook_end = scenes[0].end if scenes else 1.5
    cta_start = scenes[-1].start if scenes else max(total - 3, 0.0)
    beat_map = []
    if scenes:
        beat_map = [
            {"beat": "hook", "t": [0.0, hook_end]},
            {"beat": "demo", "t": [hook_end, cta_start]},
            {"beat": "cta", "t": [cta_start, total]},
        ]

    return {
        "template": {
            "name": f"pacing/{niche}",
            "niche": niche,
            "cut_profile": {"cut_rhythm": cut_rhythm, "shots_per_10s": shots_per_10s,
                            "hook_end_s": hook_end, "cta_start_s": cta_start,
                            "beat_map": beat_map},
            "avg_scene_sec": avg_shot,
            "proxy_score": round(proxy_score, 6),
            "operator_win_score": None,
            "signal_type": "engagement_proxy",
            "example_video_ids": [example_video_id] if example_video_id else [],
        },
        "scene_analysis": {
            "tiktok_id": tiktok_id,
            "total_duration_s": total,
            "shot_count": shot_count,
            "avg_shot_len_s": avg_shot,
            "cut_rhythm": cut_rhythm,
            "beat_map": beat_map,
            "hook_end_s": hook_end,
            "cta_start_s": cta_start,
            "shots_per_10s": shots_per_10s,
        },
    }
