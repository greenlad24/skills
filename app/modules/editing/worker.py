"""4D — the render worker: VideoJob -> output/final.mp4 + output/final_captioned.mp4.

Responsibilities (§4D.1):
  1. Resolve input MediaAsset paths from local storage.
  2. Build the EDL (hook-first, silence-trim, beat-fit, ramps) — ``edl.build_edl``.
  3. Align on the CLEAN VO (§4B) -> ``captions.ass``.
  4. Render ``final.mp4`` (cut + audio mix + disclosure overlay).
  5. Render ``final_captioned.mp4`` (burn ASS over final.mp4).
  6. Write a MediaAsset row per output; advance EDITING -> CAPTIONING -> AWAITING_APPROVAL.
  7. Persist manifest.json / captions.ass / edl.json for deterministic re-render; clean temp.

State note: the canonical states are ``EDITING`` and ``CAPTIONING`` (spec §4's informal
"RENDERING" maps onto EDITING). The worker is enqueued while the job is EDITING; it does
the cut (editing), moves to CAPTIONING for the burn-in, then to AWAITING_APPROVAL.

This module does NO billable adapter calls (all local) -> no cost-ledger entries.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.models import MediaAsset, PacingTemplate, Scene, Script, VideoJob
from app.core.state_machine import IllegalTransitionError, JobState, transition

from .captions import align_captions, build_ass, build_disclosure_ass
from .config import CONFIG, EditingConfig
from .edl import build_edl, validate_scenes
from .manifest import build_manifest, write_manifest
from .render import (
    RenderError,
    ffmpeg_burn_ass,
    ffmpeg_render_cut,
    probe_source,
)
from .types import JobSpec, PacingSpec, SceneSpec


# --------------------------------------------------------------------------- #
# Path helpers
# --------------------------------------------------------------------------- #
def job_output_dir(job_id: str) -> Path:
    return Path(settings.MEDIA_ROOT) / "jobs" / str(job_id) / "output"


def job_render_dir(job_id: str) -> Path:
    return Path(settings.MEDIA_ROOT) / "jobs" / str(job_id) / "render"


def scratch_dir(job_id: str) -> Path:
    return Path("/var/tmp/autougc") / str(job_id)


def _local_path(asset: MediaAsset | None) -> str | None:
    """Resolve a MediaAsset to a local path.

    ``storage_key`` may already be an absolute local path (local media store) or a MinIO
    object key; in the latter case it is resolved under ``MEDIA_ROOT``.
    """
    if asset is None or not asset.storage_key:
        return None
    key = asset.storage_key
    if key.startswith("/"):
        return key
    return str(Path(settings.MEDIA_ROOT) / key)


# --------------------------------------------------------------------------- #
# DB -> JobSpec mapping (§4.0 input contract)
# --------------------------------------------------------------------------- #
def _pacing_spec(tpl: PacingTemplate | None, n_scenes: int) -> PacingSpec:
    """Map a DB PacingTemplate onto the module's PacingSpec.

    The core PacingTemplate stores a free-form ``cut_profile`` JSON + ``avg_scene_sec``;
    §4's richer fields (per_shot_ms, shot_count, bpm_hint, ramp_factor) are read from
    ``cut_profile`` when present, else derived from ``avg_scene_sec``.
    """
    prof = (tpl.cut_profile if tpl and isinstance(tpl.cut_profile, dict) else {}) or {}
    shot_count = int(prof.get("shot_count") or n_scenes or 1)
    per_shot_ms = prof.get("per_shot_ms")
    if not per_shot_ms:
        avg_sec = float(tpl.avg_scene_sec) if tpl and tpl.avg_scene_sec else 2.0
        per_shot_ms = [int(avg_sec * 1000)] * max(shot_count, n_scenes, 1)
    return PacingSpec(
        id=str(tpl.id) if tpl else "default",
        shot_count=shot_count,
        per_shot_ms=[int(x) for x in per_shot_ms],
        bpm_hint=prof.get("bpm_hint", CONFIG.pacing.default_bpm),
        max_avg_cut_ms=int(prof.get("max_avg_cut_ms", CONFIG.pacing.max_avg_cut_ms)),
        ramp_factor=float(prof.get("ramp_factor", CONFIG.pacing.ramp_factor)),
    )


def _scene_spec_from_row(
    scene: Scene, index: int, is_hook: bool, vo_start_ms: int, vo_end_ms: int,
    asset: MediaAsset | None,
) -> SceneSpec:
    """Map a DB Scene onto a SceneSpec.

    The core ``Scene`` model does not carry §4's ``is_hook``/``is_payoff``/``no_crop`` or
    VO spans, so hook/ordering is derived (see ``resolve_job_spec``) and payoff/no_crop
    are read from the linked MediaAsset's ``meta`` when present (integration seam).
    """
    meta = (asset.meta if asset and isinstance(asset.meta, dict) else {}) or {}
    kind = "avatar" if (scene.scene_type or "").lower() == "avatar" else "broll"
    path = _local_path(asset) or f"missing://scene/{scene.id}"
    src_ms = None
    if asset and asset.duration_sec:
        src_ms = int(float(asset.duration_sec) * 1000)
    return SceneSpec(
        id=str(scene.id),
        index=index,
        kind=kind,
        is_hook=bool(meta.get("is_hook", is_hook)),
        is_payoff=bool(meta.get("is_payoff", False)),
        asset_path=path,
        vo_start_ms=vo_start_ms,
        vo_end_ms=vo_end_ms,
        target_duration_ms=(int(float(scene.duration_sec) * 1000)
                            if scene.duration_sec else None),
        no_crop=bool(meta.get("no_crop", kind == "broll" and meta.get("packshot", False))),
        source_duration_ms=src_ms,
    )


def resolve_job_spec(db, job: VideoJob) -> JobSpec:
    """Build a fully-resolved ``JobSpec`` from a persisted ``VideoJob``."""
    script = db.query(Script).filter(Script.video_job_id == job.id).first()
    scenes: list[Scene] = []
    if script:
        scenes = (
            db.query(Scene)
            .filter(Scene.script_id == script.id)
            .order_by(Scene.sequence_no)
            .all()
        )
    if not scenes:
        raise RenderError(f"job {job.id} has no scenes to render")

    # Assets for scenes (avatar/broll clips) + the clean VO + optional music.
    assets = db.query(MediaAsset).filter(MediaAsset.video_job_id == job.id).all()
    by_id = {str(a.id): a for a in assets}
    # Faceless writes the full Thai VO as role "vo_track" (constants.MEDIA_VO_TRACK,
    # "the clean, full Thai VO track for §04 editing"); "tts_audio" is the dormant
    # per-avatar-scene lane. Prefer the editing VO track, fall back to per-scene TTS.
    vo_asset = next((a for a in assets if a.role == "vo_track"), None) or next(
        (a for a in assets if a.role == "tts_audio"), None
    )
    music_asset = next((a for a in assets if a.role == "music"), None)

    # Derive hook (lowest sequence_no unless a scene's asset meta overrides) + VO spans
    # from cumulative scene durations on the clean-VO timeline.
    specs: list[SceneSpec] = []
    cursor_ms = 0

    def _asset_says_hook(scene: Scene) -> bool:
        a = by_id.get(str(scene.media_asset_id))
        return bool(a and isinstance(a.meta, dict) and a.meta.get("is_hook"))

    hook_marked = any(_asset_says_hook(s) for s in scenes)
    for i, scene in enumerate(scenes):
        asset = by_id.get(str(scene.media_asset_id))
        dur_ms = int(float(scene.duration_sec) * 1000) if scene.duration_sec else 2000
        default_hook = (not hook_marked) and (i == 0)
        specs.append(
            _scene_spec_from_row(
                scene, i, default_hook, cursor_ms, cursor_ms + dur_ms, asset
            )
        )
        cursor_ms += dur_ms

    # Ensure exactly one hook (defensive; upstream should guarantee it, §4D.4).
    _ensure_single_hook(specs)

    pacing = _pacing_spec(
        db.get(PacingTemplate, job.pacing_template_id) if job.pacing_template_id else None,
        len(specs),
    )

    return JobSpec(
        id=str(job.id),
        scenes=specs,
        pacing=pacing,
        vo_path=_local_path(vo_asset) or f"missing://vo/{job.id}",
        music_path=_local_path(music_asset),
        fps=CONFIG.render.fps,
    )


def _ensure_single_hook(specs: list[SceneSpec]) -> None:
    hooks = [s for s in specs if s.is_hook]
    if len(hooks) == 1:
        return
    if len(hooks) == 0 and specs:
        specs[0].is_hook = True
        return
    # More than one: keep the first, demote the rest.
    seen = False
    for s in specs:
        if s.is_hook and not seen:
            seen = True
        elif s.is_hook:
            s.is_hook = False


# --------------------------------------------------------------------------- #
# Core edit pipeline (no DB / no state changes) — reusable + testable
# --------------------------------------------------------------------------- #
@dataclass
class EditOutputs:
    final_mp4: str
    final_captioned_mp4: str
    ass_path: str
    disclosure_ass_path: str | None
    manifest_path: str
    edl_path: str
    avg_cut_ms: float
    shot_count: int


def run_edit(
    spec: JobSpec,
    job_id: str,
    *,
    cfg: EditingConfig = CONFIG,
    dry_run: bool = False,
    brand_terms: list[str] | None = None,
    glossary: str = "",
) -> EditOutputs:
    """Plan + render both outputs. Pure of DB/state; raises RenderError on failure."""
    out_dir = job_output_dir(job_id)
    render_dir = job_render_dir(job_id)
    tmp = scratch_dir(job_id)
    for d in (out_dir, render_dir, tmp):
        d.mkdir(parents=True, exist_ok=True)

    validate_scenes(spec.scenes)

    # 1. Source integrity (§4D.4) — skipped in DRY_RUN (paths are placeholders).
    if not dry_run:
        for s in spec.scenes:
            probe_source(s.asset_path)
        probe_source(spec.vo_path)

    # 2. EDL (§4A)
    edl = build_edl(spec)

    # 3. Align on the CLEAN VO (§4B) -> captions.ass
    if dry_run:
        from .types import AlignResult
        align = AlignResult(segments=[], meta={"type": "dry_run"}, degraded=True)
    else:
        align = align_captions(spec.vo_path, glossary=glossary, brand_terms=brand_terms)

    ass_path = str(render_dir / "captions.ass")
    # disclosure_in_base -> omit badge from captions.ass to avoid a double label (§4C)
    build_ass(
        align,
        cfg.caption,
        cfg,
        include_disclosure=not cfg.disclosure.in_base,
        brand_terms=brand_terms,
        out_path=ass_path,
    )

    disclosure_ass_path: str | None = None
    if cfg.disclosure.in_base:
        disclosure_ass_path = str(render_dir / "disclosure.ass")
        build_disclosure_ass(cfg, out_path=disclosure_ass_path)

    # persist EDL + manifest for deterministic re-render (§4D.2)
    edl_path = str(render_dir / "edl.json")
    with open(edl_path, "w", encoding="utf-8") as fh:
        json.dump(edl.as_dict(), fh, ensure_ascii=False, indent=2, sort_keys=True)
    manifest_path = str(render_dir / "manifest.json")
    write_manifest(
        manifest_path,
        build_manifest(edl, align, cfg, ass_path, hash_sources=not dry_run),
    )

    # 4. Render the cut (§4A.8) with the disclosure baked in (§4C)
    final_mp4 = str(out_dir / "final.mp4")
    ffmpeg_render_cut(edl, final_mp4, cfg, disclosure_ass_path, dry_run=dry_run)

    # 5. Burn captions over the cut (§4B.5)
    final_captioned = str(out_dir / "final_captioned.mp4")
    ffmpeg_burn_ass(final_mp4, ass_path, final_captioned, cfg, dry_run=dry_run)

    # 6. Acceptance-lite (§4F): hook first + avg cut < ceiling
    if not edl.shots[0].is_hook:
        raise RenderError("acceptance T-2: first shot is not the hook")
    if edl.avg_cut_ms() >= cfg.pacing.max_avg_cut_ms:
        raise RenderError(
            f"acceptance T-2: avg cut {edl.avg_cut_ms():.0f}ms "
            f">= {cfg.pacing.max_avg_cut_ms}ms"
        )

    return EditOutputs(
        final_mp4=final_mp4,
        final_captioned_mp4=final_captioned,
        ass_path=ass_path,
        disclosure_ass_path=disclosure_ass_path,
        manifest_path=manifest_path,
        edl_path=edl_path,
        avg_cut_ms=edl.avg_cut_ms(),
        shot_count=edl.shot_count,
    )


# --------------------------------------------------------------------------- #
# State + persistence helpers
# --------------------------------------------------------------------------- #
def _set_state(db, job: VideoJob, target: JobState) -> None:
    transition(job, target)
    db.commit()


def _write_media_asset(db, job: VideoJob, path: str, role: str, cfg: EditingConfig) -> MediaAsset:
    size = Path(path).stat().st_size if Path(path).exists() else 0
    asset = MediaAsset(
        video_job_id=job.id,
        role=role,
        storage_key=path,
        mime_type="video/mp4",
        provider="local-ffmpeg",
        status="ready",
        meta={
            "width": cfg.render.width,
            "height": cfg.render.height,
            "fps": cfg.render.fps,
            "pix_fmt": cfg.render.pix_fmt,
            "bytes": size,
        },
    )
    db.add(asset)
    return asset


def cleanup(tmp: Path, keep: tuple[str, ...] = ()) -> None:
    """Remove scratch, retaining named files (§4D.3)."""
    if not tmp.exists():
        return
    for child in tmp.iterdir():
        if child.name in keep:
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Entry point (called by the Celery task ``editing.run``)
# --------------------------------------------------------------------------- #
def run(job_id: str, reroll: str | None = None, cfg: EditingConfig = CONFIG) -> dict:
    """Render a job end-to-end and advance EDITING -> CAPTIONING -> AWAITING_APPROVAL.

    On any RenderError the job is set to FAILED and scratch is retained (§4D.3/§4D.4).
    Deterministic: re-running from unchanged sources reproduces the outputs (§4D.2).
    """
    dry_run = settings.DRY_RUN
    db = SessionLocal()
    job: VideoJob | None = None
    try:
        job = db.get(VideoJob, job_id)
        if job is None:
            raise RenderError(f"job not found: {job_id}")

        # Normalize current state; the worker owns the EDITING stage.
        current = job.state if isinstance(job.state, JobState) else JobState(job.state)
        if current not in (JobState.EDITING,):
            # A reroll lands the job back in EDITING via the API; anything else is a bug.
            raise RenderError(
                f"editing.run expected state EDITING, found {current.value}"
            )

        spec = resolve_job_spec(db, job)

        # --- EDITING: build the cut (final.mp4) ---
        outputs = run_edit(spec, str(job.id), cfg=cfg, dry_run=dry_run)
        final_asset = _write_media_asset(db, job, outputs.final_mp4, "final", cfg)
        job.last_completed_stage = "editing"
        job.draft_asset_key = outputs.final_mp4
        db.commit()

        # --- CAPTIONING: captioned variant already burned in run_edit ---
        _set_state(db, job, JobState.CAPTIONING)
        _write_media_asset(db, job, outputs.final_captioned_mp4, "final_captioned", cfg)
        job.last_completed_stage = "captioning"
        db.commit()

        # --- gate ---
        _set_state(db, job, JobState.AWAITING_APPROVAL)

        cleanup(
            scratch_dir(str(job.id)),
            keep=("manifest.json", "captions.ass", "edl.json"),
        )
        return {
            "ok": True,
            "job_id": str(job.id),
            "state": JobState.AWAITING_APPROVAL.value,
            "final_mp4": outputs.final_mp4,
            "final_captioned_mp4": outputs.final_captioned_mp4,
            "shot_count": outputs.shot_count,
            "avg_cut_ms": round(outputs.avg_cut_ms, 1),
            "dry_run": dry_run,
            "media_asset_id": str(final_asset.id),
        }

    except (RenderError, IllegalTransitionError) as exc:
        db.rollback()
        if job is not None:
            try:
                current = (
                    job.state if isinstance(job.state, JobState) else JobState(job.state)
                )
                if current in (JobState.EDITING, JobState.CAPTIONING):
                    transition(job, JobState.FAILED)
                    job.failure_reason = str(exc)
                    db.commit()
            except Exception:  # noqa: BLE001 — never mask the original error
                db.rollback()
        return {"ok": False, "job_id": str(job_id), "error": str(exc)}
    finally:
        db.close()
