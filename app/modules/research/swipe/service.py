"""Swipe-engine service (§2B.6/§2B.7): refresh_niche, process_video, get_templates.

Ties the sourcing → extraction → template distillation pipeline to persistence
(SwipeSource / SwipeVideo / Transcript / SceneAnalysis / Formula|Hook|Pacing templates).
Everything runs $0 under DRY_RUN (fake scraper/LLM + stub media tools) and is idempotent
per `SwipeVideo.processed_stages`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import (
    FormulaTemplate,
    HookTemplate,
    PacingTemplate,
    SwipeSource,
    SwipeVideo,
)

from .. import config
from ..models import SceneAnalysis, Transcript
from ..schemas import RefreshReport
from . import templates as tmpl
from .extraction import MergedTranscript, TranscriptSegment, extract_transcript
from .mediatools import MediaTools, Scene, get_media_tools
from .sourcing import mine_source

_STAGES = ["download", "transcribe", "ocr", "merge", "pacing", "hook"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# process_video — per-video stages, idempotent by processed_stages bitmap (§2B.9)
# --------------------------------------------------------------------------- #
def process_video(
    db: Session,
    video: SwipeVideo,
    *,
    tools: MediaTools | None = None,
    force: bool = False,
) -> dict:
    """Run download→transcribe→ocr→merge→pacing→hook for one video. Skips completed
    stages unless `force`. Persists Transcript + SceneAnalysis and links them on the
    SwipeVideo. Returns the resulting processed_stages bitmap."""
    tools = tools or get_media_tools()
    stages = dict(video.processed_stages or {})

    def done(s: str) -> bool:
        return bool(stages.get(s)) and not force

    transcript_obj: MergedTranscript | None = None

    # download + transcribe + ocr + merge → Transcript
    if not (done("download") and done("transcribe") and done("ocr") and done("merge")):
        transcript_obj, local_path = extract_transcript(
            video.url or "", video.tiktok_id, video.duration_s, tools=tools
        )
        video.local_video_path = local_path
        row = Transcript(
            swipe_video_id=video.id,
            tiktok_id=video.tiktok_id,
            language=transcript_obj.language,
            segments=[s.__dict__ for s in transcript_obj.segments],
            vo_text=transcript_obj.vo_text,
            osd_text=transcript_obj.osd_text,
            merged_text=transcript_obj.merged_text,
            tokens=transcript_obj.tokens,
        )
        db.add(row)
        db.flush()
        video.transcript_id = row.id
        stages.update(download=True, transcribe=True, ocr=True, merge=True)

    # pacing → SceneAnalysis + PacingTemplate
    if not done("pacing"):
        scenes = tools.scenes.detect(video.local_video_path or video.url or video.tiktok_id)
        if transcript_obj is None:
            transcript_obj = _load_transcript(db, video)
        pacing = tmpl.extract_pacing(
            video.tiktok_id, scenes, transcript_obj, video.niche or "misc",
            float(video.proxy_score or 0.0), video.id,
        )
        sa = SceneAnalysis(swipe_video_id=video.id, **pacing["scene_analysis"])
        db.add(sa)
        db.flush()
        video.scene_data_id = sa.id
        _upsert_pacing_template(db, pacing["template"])
        stages["pacing"] = True

    # hook → HookTemplate
    if not done("hook"):
        if transcript_obj is None:
            transcript_obj = _load_transcript(db, video)
        if transcript_obj is not None:
            hook = tmpl.extract_hook(
                transcript_obj, video.niche or "misc", float(video.proxy_score or 0.0), video.id
            )
            _upsert_hook_template(db, hook)
        stages["hook"] = True

    video.processed_stages = stages
    db.add(video)
    return stages


def _load_transcript(db: Session, video: SwipeVideo) -> MergedTranscript | None:
    if not video.transcript_id:
        return None
    row = db.get(Transcript, video.transcript_id)
    if row is None:
        return None
    segs = [
        TranscriptSegment(
            s.get("t_start"), s.get("t_end"), s.get("source"), s.get("text"), s.get("bbox") or []
        )
        for s in (row.segments or [])
    ]
    return MergedTranscript(
        tiktok_id=row.tiktok_id or "", language=row.language, segments=segs,
        vo_text=row.vo_text or "", osd_text=row.osd_text or "",
        merged_text=row.merged_text or "", tokens=row.tokens or [],
    )


# --------------------------------------------------------------------------- #
# Template upserts
# --------------------------------------------------------------------------- #
def _upsert_hook_template(db: Session, h: dict) -> None:
    existing = db.scalar(
        select(HookTemplate).where(HookTemplate.name == h["name"])
    )
    if existing is None:
        db.add(HookTemplate(
            name=h["name"], pattern_th=h["pattern_th"], hook_type=h["hook_type"],
            proxy_score=h["proxy_score"], signal_type=h["signal_type"],
        ))
    else:
        # blend proxy score, bump support
        existing.proxy_score = _blend(existing.proxy_score, h["proxy_score"])


def _upsert_pacing_template(db: Session, p: dict) -> None:
    existing = db.scalar(
        select(PacingTemplate).where(PacingTemplate.name == p["name"])
    )
    if existing is None:
        db.add(PacingTemplate(
            name=p["name"], cut_profile=p["cut_profile"], avg_scene_sec=p["avg_scene_sec"],
            proxy_score=p["proxy_score"], signal_type=p["signal_type"],
        ))
    else:
        existing.cut_profile = p["cut_profile"]
        existing.proxy_score = _blend(existing.proxy_score, p["proxy_score"])


def _formula_source(niche: str) -> str:
    return "swipe:" + (niche or "")


def _upsert_formula_template(db: Session, f: dict) -> str:
    src = _formula_source(f.get("niche") or "")
    # dedup per (name, source) so the same formula name in different niches stays distinct
    existing = db.scalar(
        select(FormulaTemplate).where(
            FormulaTemplate.name == f["name"], FormulaTemplate.source == src
        )
    )
    if existing is None:
        db.add(FormulaTemplate(
            name=f["name"], structure=f["structure"], source=src,
            proxy_score=f["proxy_score"], signal_type=f["signal_type"],
        ))
        return "created"
    existing.structure = f["structure"]
    existing.proxy_score = _blend(existing.proxy_score, f["proxy_score"])
    return "updated"


def _blend(old, new) -> float:
    if old is None:
        return float(new)
    return round((float(old) + float(new)) / 2.0, 6)


# --------------------------------------------------------------------------- #
# refresh_niche — nightly / on-demand (§2B.10)
# --------------------------------------------------------------------------- #
def refresh_niche(
    db: Session,
    niche: str,
    top_k: int = config.DEFAULT_TOP_K,
    *,
    tools: MediaTools | None = None,
    force: bool = False,
    market: str = "TH",
) -> RefreshReport:
    report = RefreshReport(niche=niche)
    budget = dict(config.REFRESH_BUDGET)
    tools = tools or get_media_tools()

    sources = list(db.scalars(
        select(SwipeSource).where(SwipeSource.niche == niche, SwipeSource.enabled.is_(True))
    ))

    processed_transcripts: list[MergedTranscript] = []
    proxy_scores: list[float] = []
    example_ids: list = []

    for src in sources:
        # source-level throttle (§2B.9)
        if not force and src.last_scraped_at is not None:
            age_h = (_now() - _ensure_tz(src.last_scraped_at)).total_seconds() / 3600.0
            if age_h < config.SOURCE_REFRESH_WINDOW_HOURS:
                continue
        if budget["apify_runs"] <= 0:
            report.budget_hit = "apify_runs"
            break

        scored, cost = mine_source(
            src.handle or "", market, top_k, idempotency_key=f"refresh:{niche}:{src.id}"
        )
        budget["apify_runs"] -= 1
        budget["usd"] -= cost
        report.spend_usd += cost
        report.sources_scraped += 1
        report.videos_seen += len(scored)
        src.last_scraped_at = _now()

        for sv in scored:
            existing = db.scalar(select(SwipeVideo).where(SwipeVideo.tiktok_id == sv.tiktok_id))
            if existing is None:
                video = SwipeVideo(
                    tiktok_id=sv.tiktok_id, source_id=src.id, niche=niche,
                    author_handle=sv.author_handle, author_gender=sv.author_gender,
                    url=sv.url, duration_s=sv.duration_s, posted_at=sv.posted_at,
                    views=sv.views, likes=sv.likes, shares=sv.shares,
                    comments=sv.comments, saves=sv.saves, proxy_score=sv.proxy_score,
                    signal_type="engagement_proxy", processed_stages={},
                )
                db.add(video)
                db.flush()
                report.new_videos += 1
            else:
                existing.proxy_score = sv.proxy_score  # refresh metrics
                video = existing

            # process only new / incomplete videos, within download budget
            if _all_stages_done(video) and not force:
                continue
            if budget["downloads"] <= 0:
                report.budget_hit = "downloads"
                break
            if budget["usd"] <= 0:
                report.budget_hit = "usd"
                break
            try:
                process_video(db, video, tools=tools, force=force)
                budget["downloads"] -= 1
                report.videos_processed += 1
                t = _load_transcript(db, video)
                if t is not None:
                    processed_transcripts.append(t)
                    proxy_scores.append(float(video.proxy_score or 0.0))
                    example_ids.append(video.id)
            except Exception as exc:  # noqa: BLE001 — one bad video shouldn't kill the run
                report.failures.append(f"{video.tiktok_id}: {exc}")
        if report.budget_hit:
            break

    # cluster-level formula extraction (§2B.3) over this niche's processed transcripts
    if len(processed_transcripts) >= config.MIN_SUPPORT and budget["llm_calls"] > 0:
        formula = tmpl.extract_formula(
            processed_transcripts, niche, proxy_scores, example_ids
        )
        budget["llm_calls"] -= 1
        if formula is not None:
            outcome = _upsert_formula_template(db, formula)
            if outcome == "created":
                report.templates_created += 1
            else:
                report.templates_updated += 1

    _decay_stale_templates(db, niche)
    db.commit()
    return report


def _ensure_tz(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _all_stages_done(video: SwipeVideo) -> bool:
    stages = video.processed_stages or {}
    return all(stages.get(s) for s in _STAGES)


def _decay_stale_templates(db: Session, niche: str) -> None:
    """Recency decay so the library tracks current trends (§2B.10). Cheap multiplicative
    decay on proxy_score; operator_win_score (from §05) is never decayed."""
    for model in (FormulaTemplate, HookTemplate, PacingTemplate):
        for row in db.scalars(select(model)):
            if row.proxy_score:
                row.proxy_score = round(float(row.proxy_score) * 0.98, 6)


# --------------------------------------------------------------------------- #
# get_templates — ranked, proxy blended with operator_win_score when available (§2B.7)
# --------------------------------------------------------------------------- #
_MODEL_BY_KIND = {
    "formula": FormulaTemplate,
    "hook": HookTemplate,
    "pacing": PacingTemplate,
}


def get_templates(
    db: Session,
    niche: str,
    kind: Literal["formula", "hook", "pacing"],
    limit: int = 10,
    *,
    operator_blend: float = 0.5,
) -> list:
    """Ranked templates. Combined score blends proxy_score with operator_win_score when
    §05 has populated it (blend weight supplied by §05; default 0.5)."""
    model = _MODEL_BY_KIND[kind]
    # Core template models have no niche column; scope via the columns we encoded it into.
    if kind == "formula":
        stmt = select(model).where(model.source == _formula_source(niche))
    elif kind == "pacing":
        stmt = select(model).where(model.name == f"pacing/{niche}")
    else:  # hook — niche prefixed into name
        stmt = select(model).where(model.name.like(f"{niche}:%"))
    rows = list(db.scalars(stmt))

    def combined(row) -> float:
        proxy = float(row.proxy_score or 0.0)
        op = row.operator_win_score
        if op is None:
            return proxy
        return operator_blend * float(op) + (1 - operator_blend) * proxy

    rows.sort(key=combined, reverse=True)
    return rows[:limit]
