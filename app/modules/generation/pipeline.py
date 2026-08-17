"""Per-video generation pipeline (§3D).

Given an approved script, split scenes into two lanes and fan them out through the
async submit→poll pattern:

  * AVATAR lane (HOOK, CTA): synth the Thai VO (TTS) → audio-driven talking head
    via the reused ``avatar_id`` + ``voice_id`` → ``avatar_clip``.
  * BROLL lane (DEMO, PROOF): lock ONE seeded hero image (Nano Banana) from the
    real product photos, then image-to-video (fal.ai Kling/Veo/Seedance) with
    first/last-frame conditioning → product-consistency QA gate → accept or reroll
    (new seed, attempt+1) up to ``MAX_REROLLS``.

Plus a clean, full Thai VO track for the §04 editing module.

Every external call is submitted (``GenAttempt.request_id`` persisted BEFORE
polling so a crash re-attaches instead of resubmitting), billed to the cost
ledger, and budget-guarded. Duplicate webhook+poll deliveries funnel through the
same idempotent finaliser (``UNIQUE(request_id)`` / ``UNIQUE(idempotency_key)``).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.adapters import registry
from app.core.adapters.base import ProviderResult
from app.core.models import GenAttempt, MediaAsset, VideoJob
from app.modules.generation import cost, qa
from app.modules.generation.constants import (
    ASPECT_VERTICAL,
    ASSET_AVATAR,
    DEFAULT_I2V_MODEL,
    DEFAULT_TTS_MODEL,
    KIND_AVATAR,
    KIND_HERO_IMAGE,
    KIND_I2V,
    KIND_TTS,
    MAX_REROLLS,
    MEDIA_AVATAR_CLIP,
    MEDIA_BROLL,
    MEDIA_HERO_IMAGE,
    MEDIA_TTS_AUDIO,
    MEDIA_VO_TRACK,
    POLL_INTERVAL_SEC,
    POLL_MAX_ATTEMPTS,
    QA_SIMILARITY_THRESHOLD,
    ROLE_HOOK,
)
from app.modules.generation.invariants import compose_hero_prompt
from app.modules.generation.scripting import duration_seconds


# --------------------------------------------------------------------------- #
# Result container
# --------------------------------------------------------------------------- #
@dataclass
class RenderResult:
    avatar_assets: list[MediaAsset] = field(default_factory=list)
    broll_assets: list[MediaAsset] = field(default_factory=list)
    hero_asset: MediaAsset | None = None
    vo_track_asset: MediaAsset | None = None
    reroll_count: int = 0
    broll_count: int = 0
    halted: bool = False
    halt_reason: str | None = None
    blocked_scene_ids: list[str] = field(default_factory=list)

    @property
    def reroll_rate(self) -> float:
        return qa.reroll_rate(self.reroll_count, self.broll_count)

    @property
    def all_ready(self) -> bool:
        assets = self.avatar_assets + self.broll_assets
        return bool(assets) and all(a.status == "ready" for a in assets) and not self.halted


def idem_key(video_job_id: Any, scene_id: Any, kind: str, attempt: int) -> str:
    """§3D.10 idempotency key: ``{video_job_id}:{scene_id}:{kind}:{attempt}``."""
    return f"{video_job_id}:{scene_id}:{kind}:{attempt}"


def _find_attempt(db: Session, *, idempotency_key: str) -> GenAttempt | None:
    return db.execute(
        select(GenAttempt).where(GenAttempt.idempotency_key == idempotency_key)
    ).scalars().first()


def _poll_until_ready(
    provider: Any, provider_job_id: str, *, sleep: float = 0.0
) -> ProviderResult:
    """Poll fallback (§3D.4). Fakes complete immediately; reals may need retries."""
    result = provider.poll(provider_job_id=provider_job_id)
    attempts = 1
    while result.ok and result.data.get("status") not in {"ready", "completed", "COMPLETED"}:
        if result.data.get("status") in {"failed", "FAILED"}:
            break
        if attempts >= POLL_MAX_ATTEMPTS:
            break
        if sleep:
            time.sleep(min(sleep, POLL_INTERVAL_SEC))
        result = provider.poll(provider_job_id=provider_job_id)
        attempts += 1
    return result


# --------------------------------------------------------------------------- #
# Clean Thai VO track (§3D — handoff to editing)
# --------------------------------------------------------------------------- #
def build_clean_vo_track(
    db: Session, job: VideoJob, *, scenes: list[dict[str, Any]], voice_id: str
) -> MediaAsset:
    """Synthesize the full, clean Thai VO track for the editing module."""
    full_text = " ".join(
        s.get("thai_narration", "").strip()
        for s in sorted(scenes, key=lambda s: s.get("order", 0))
        if s.get("thai_narration", "").strip()
    ) or "…"
    tts = registry.get_tts_provider()
    key = f"{job.id}:vo_track:1"
    cost.guard(job, KIND_TTS)
    result = tts.synthesize(
        text=full_text,
        voice_id=voice_id,
        language="th",
        model=DEFAULT_TTS_MODEL,
        idempotency_key=key,
    )
    asset = MediaAsset(
        video_job_id=job.id,
        role=MEDIA_VO_TRACK,
        storage_key=result.data.get("audio_key"),
        mime_type=result.data.get("mime_type", "audio/mpeg"),
        provider=getattr(tts, "provider_name", None),
        idempotency_key=key,
        status="ready" if result.ok else "failed",
        duration_sec=result.data.get("duration_sec"),
        meta={"track": "clean_vo", "chars": len(full_text)},
        cost_usd=result.cost_usd,
    )
    db.add(asset)
    cost.record(
        db, job, kind=KIND_TTS, provider=getattr(tts, "provider_name", None),
        model=DEFAULT_TTS_MODEL, amount_usd=result.cost_usd,
        usage=result.usage, line_item="clean_vo_track",
    )
    return asset


# --------------------------------------------------------------------------- #
# AVATAR lane (§3D.1)
# --------------------------------------------------------------------------- #
def render_avatar_scene(
    db: Session,
    job: VideoJob,
    scene: dict[str, Any],
    *,
    avatar_id: str,
    voice_id: str,
    options: dict[str, Any] | None = None,
) -> MediaAsset:
    """Render one AVATAR scene: TTS VO → audio-driven talking head → poll → asset."""
    options = options or {}
    sleep = float(options.get("poll_sleep", 0.0))
    scene_id = scene["scene_id"]
    narration = scene.get("thai_narration", "")

    # 1) Per-scene Thai VO (audio-driven lip-sync targets the exact phonemes, §3D.6).
    tts = registry.get_tts_provider()
    tts_key = idem_key(job.id, scene_id, KIND_TTS, 1)
    cost.guard(job, KIND_TTS)
    tts_result = tts.synthesize(
        text=narration or "…",
        voice_id=voice_id,
        language="th",
        model=DEFAULT_TTS_MODEL,
        idempotency_key=tts_key,
    )
    audio_key = tts_result.data.get("audio_key", f"fake/tts/{scene_id}.mp3")
    tts_asset = MediaAsset(
        video_job_id=job.id, role=MEDIA_TTS_AUDIO, storage_key=audio_key,
        mime_type=tts_result.data.get("mime_type", "audio/mpeg"),
        provider=getattr(tts, "provider_name", None), idempotency_key=tts_key,
        status="ready" if tts_result.ok else "failed",
        duration_sec=tts_result.data.get("duration_sec"),
        meta={"scene_id": str(scene_id), "role": scene.get("role")},
        cost_usd=tts_result.cost_usd,
    )
    db.add(tts_asset)
    cost.record(
        db, job, kind=KIND_TTS, provider=getattr(tts, "provider_name", None),
        model=DEFAULT_TTS_MODEL, amount_usd=tts_result.cost_usd,
        scene_id=_uuid_or_none(scene_id), usage=tts_result.usage, line_item="scene_vo",
    )

    # 2) Talking head (reused avatar_id + audio-driven).
    avatar = registry.get_avatar_provider()
    a_key = idem_key(job.id, scene_id, KIND_AVATAR, 1)

    attempt = _find_attempt(db, idempotency_key=a_key)
    if attempt is not None:
        # Re-entry / duplicate delivery: reuse the existing asset, no new spend.
        clip_asset = db.get(MediaAsset, attempt.media_asset_id) if attempt.media_asset_id else None
        if clip_asset is None:
            clip_asset = MediaAsset(
                video_job_id=job.id, role=MEDIA_AVATAR_CLIP,
                provider=getattr(avatar, "provider_name", None), idempotency_key=a_key,
                status="processing", duration_sec=scene.get("duration_s"),
                meta={"scene_id": str(scene_id), "role": scene.get("role")},
                provider_job_id=attempt.request_id,
            )
            db.add(clip_asset)
            db.flush()
    else:
        cost.guard(job, KIND_AVATAR)
        clip_asset = MediaAsset(
            video_job_id=job.id, role=MEDIA_AVATAR_CLIP,
            provider=getattr(avatar, "provider_name", None),
            idempotency_key=a_key, status="processing",
            duration_sec=scene.get("duration_s"),
            meta={"scene_id": str(scene_id), "role": scene.get("role")},
        )
        db.add(clip_asset)
        db.flush()
        submit = avatar.submit_talking_head(
            avatar_id=avatar_id, audio_key=audio_key,
            script_text=narration, aspect=ASPECT_VERTICAL, idempotency_key=a_key,
        )
        attempt = GenAttempt(
            video_job_id=job.id, scene_id=_uuid_or_none(scene_id),
            media_asset_id=clip_asset.id, provider=getattr(avatar, "provider_name", None),
            model="heygen-avatar-v", kind=KIND_AVATAR, attempt=1,
            request_id=submit.provider_job_id, idempotency_key=a_key,
            status="processing", cost_usd=submit.cost_usd,
        )
        db.add(attempt)
        clip_asset.provider_job_id = submit.provider_job_id
        db.flush()  # persist request_id BEFORE polling (§3 no-double-billing)
        cost.record(
            db, job, kind=KIND_AVATAR, provider=getattr(avatar, "provider_name", None),
            model="heygen-avatar-v", amount_usd=submit.cost_usd,
            scene_id=_uuid_or_none(scene_id), attempt=1, usage=submit.usage,
        )

    poll = _poll_until_ready(avatar, attempt.request_id, sleep=sleep)
    _finalize_media(clip_asset, attempt, poll)
    return clip_asset


# --------------------------------------------------------------------------- #
# BROLL lane (§3D.2, §3D.3, §3D.5)
# --------------------------------------------------------------------------- #
def _product_image_refs(product: dict[str, Any], limit: int = 3) -> list[str]:
    """Collect up to `limit` product reference images for the hero step.

    The real research pipeline stores `images` as a list of local path strings
    (post-download), while tests and some payloads use `[{"url": ...}]` dicts —
    accept BOTH. Falls back to any operator-supplied `manual_images` (a URL the
    operator pasted when scraping — e.g. a TikTok short link — yielded nothing).
    """
    refs: list[str] = []
    for source in ("images", "manual_images"):
        for img in product.get(source, []) or []:
            url: str | None = None
            if isinstance(img, str) and img.strip():
                url = img.strip()
            elif isinstance(img, dict):
                cand = img.get("url") or img.get("src") or img.get("local_path")
                if isinstance(cand, str) and cand.strip():
                    url = cand.strip()
            if url and url not in refs:
                refs.append(url)
                if len(refs) >= limit:
                    return refs
        if refs:  # prefer real scraped images; only touch manual_images if none
            break
    return refs


def generate_hero_image(
    db: Session,
    job: VideoJob,
    *,
    product: dict[str, Any],
    invariants: dict[str, str],
    hero_action_en: str = "bottle standing, cap beside it, single dewy droplet on applicator",
) -> MediaAsset:
    """Lock ONE seeded hero image from the real product photos (§3D.2).

    Reused by every b-roll scene so DEMO + PROOF share product identity; NOT
    regenerated on reroll.
    """
    refs = _product_image_refs(product)
    prompt = compose_hero_prompt(invariants, hero_action_en)
    key = f"{job.id}:hero:1"

    existing = db.execute(
        select(MediaAsset)
        .where(MediaAsset.video_job_id == job.id)
        .where(MediaAsset.role == MEDIA_HERO_IMAGE)
    ).scalars().first()
    if existing is not None:
        return existing

    video = registry.get_video_gen_provider()
    cost.guard(job, KIND_HERO_IMAGE)
    result = video.generate_hero_image(prompt=prompt, refs=refs, idempotency_key=key)
    seed = result.data.get("seed")
    asset = MediaAsset(
        video_job_id=job.id, role=MEDIA_HERO_IMAGE,
        storage_key=result.data.get("image_key"),
        mime_type=result.data.get("mime_type", "image/png"),
        provider=getattr(video, "provider_name", None), idempotency_key=key,
        status="ready" if result.ok else "failed",
        meta={"seed": seed, "prompt": prompt, "refs": refs},
        cost_usd=result.cost_usd,
    )
    db.add(asset)
    db.flush()
    # Record the hero attempt (synchronous provider → immediately ready).
    db.add(
        GenAttempt(
            video_job_id=job.id, media_asset_id=asset.id,
            provider=getattr(video, "provider_name", None),
            model="nano-banana-pro", kind=KIND_HERO_IMAGE, attempt=1,
            seed=seed, request_id=key, idempotency_key=key,
            status="ready" if result.ok else "failed", cost_usd=result.cost_usd,
        )
    )
    cost.record(
        db, job, kind=KIND_HERO_IMAGE, provider=getattr(video, "provider_name", None),
        model="nano-banana-pro", amount_usd=result.cost_usd, usage=result.usage,
    )
    return asset


def _submit_i2v(
    db: Session,
    job: VideoJob,
    scene: dict[str, Any],
    hero: MediaAsset,
    *,
    attempt_n: int,
    model: str,
    is_reroll: bool,
) -> tuple[MediaAsset, GenAttempt]:
    """Submit one image-to-video attempt with first/last-frame conditioning."""
    scene_id = scene["scene_id"]
    key = idem_key(job.id, scene_id, KIND_I2V, attempt_n)
    seconds = duration_seconds(scene)

    existing = _find_attempt(db, idempotency_key=key)
    if existing is not None:
        # Duplicate submit for the same idempotency key: reuse the asset, no spend.
        clip_asset = db.get(MediaAsset, existing.media_asset_id) if existing.media_asset_id else None
        if clip_asset is None:
            clip_asset = MediaAsset(
                video_job_id=job.id, role=MEDIA_BROLL, idempotency_key=key,
                status="processing", duration_sec=scene.get("duration_s"),
                provider_job_id=existing.request_id,
                meta={"scene_id": str(scene_id), "role": scene.get("role"), "attempt": attempt_n},
            )
            db.add(clip_asset)
            db.flush()
        return clip_asset, existing

    clip_asset = MediaAsset(
        video_job_id=job.id, role=MEDIA_BROLL,
        provider=None, idempotency_key=key, status="processing",
        duration_sec=scene.get("duration_s"),
        meta={"scene_id": str(scene_id), "role": scene.get("role"), "attempt": attempt_n},
    )
    db.add(clip_asset)
    db.flush()

    video = registry.get_video_gen_provider()
    cost.guard(job, KIND_I2V)
    submit = video.submit_image_to_video(
        image_key=hero.storage_key or "",
        prompt=scene.get("visual_prompt_en", ""),
        model=model,
        seconds=float(seconds),
        aspect=ASPECT_VERTICAL,
        idempotency_key=key,
    )
    # Seed derived from attempt so a reroll re-conditions from the same hero with a
    # NEW seed (§3D.5) — hero image itself is never regenerated.
    seed_base = (hero.meta or {}).get("seed") or 0
    attempt = GenAttempt(
        video_job_id=job.id, scene_id=_uuid_or_none(scene_id),
        media_asset_id=clip_asset.id, provider=getattr(video, "provider_name", None),
        model=model, kind=KIND_I2V, attempt=attempt_n,
        seed=int(seed_base) + attempt_n, request_id=submit.provider_job_id,
        status_url=submit.data.get("status_url"), idempotency_key=key,
        status="processing", is_reroll=is_reroll, cost_usd=submit.cost_usd,
    )
    db.add(attempt)
    clip_asset.provider = getattr(video, "provider_name", None)
    clip_asset.provider_job_id = submit.provider_job_id
    db.flush()  # persist request_id BEFORE polling
    cost.record(
        db, job, kind=KIND_I2V, provider=getattr(video, "provider_name", None),
        model=model, amount_usd=submit.cost_usd, scene_id=_uuid_or_none(scene_id),
        attempt=attempt_n, is_reroll=is_reroll, usage=submit.usage,
    )
    return clip_asset, attempt


def render_broll_scene(
    db: Session,
    job: VideoJob,
    scene: dict[str, Any],
    hero: MediaAsset,
    *,
    options: dict[str, Any] | None = None,
) -> tuple[MediaAsset | None, int]:
    """Render one BROLL scene with the QA gate + budgeted reroll loop (§3D.5).

    Returns ``(accepted_asset_or_None, rerolls_used)``. On exhausted rerolls the
    scene is left NEEDS_ATTENTION (asset status ``failed``) and the caller halts
    the job to the operator gate.
    """
    options = options or {}
    sleep = float(options.get("poll_sleep", 0.0))
    model = options.get("i2v_model", DEFAULT_I2V_MODEL)
    threshold = float(options.get("qa_threshold", QA_SIMILARITY_THRESHOLD))
    video = registry.get_video_gen_provider()

    order_key = str(scene.get("order"))
    forced_sims = (options.get("qa_similarities") or {}).get(order_key, [])
    forced_checks = (options.get("checklist_overrides") or {}).get(order_key, [])

    rerolls = 0
    last_asset: MediaAsset | None = None
    for attempt_n in range(1, MAX_REROLLS + 2):  # attempt 1 + up to MAX_REROLLS
        is_reroll = attempt_n > 1
        if is_reroll:
            rerolls += 1
        clip_asset, attempt = _submit_i2v(
            db, job, scene, hero, attempt_n=attempt_n, model=model, is_reroll=is_reroll,
        )
        poll = _poll_until_ready(video, attempt.request_id, sleep=sleep)
        _finalize_media(clip_asset, attempt, poll)
        last_asset = clip_asset

        if clip_asset.status != "ready":
            continue  # transport failure — treated as a failed attempt

        # QA gate: inject forced values (tests / real vision backend) into meta.
        clip_meta = dict(clip_asset.meta or {})
        clip_meta["video_key"] = clip_asset.storage_key
        idx = attempt_n - 1
        if idx < len(forced_sims):
            clip_meta["qa_similarity"] = forced_sims[idx]
        if idx < len(forced_checks):
            clip_meta["checklist"] = forced_checks[idx]

        result = qa.evaluate(hero.meta or {}, clip_meta, threshold=threshold)
        clip_asset.meta = {
            **(clip_asset.meta or {}),
            "qa_similarity": result.similarity,
            "qa_accepted": result.accepted,
            "qa_reason": result.reason,
        }
        if result.accepted:
            return clip_asset, rerolls
        clip_asset.status = "failed"  # rejected clip is not shippable

    # Exhausted rerolls → operator gate (§3D.5 / §3D.10).
    if last_asset is not None:
        last_asset.status = "failed"
        last_asset.meta = {**(last_asset.meta or {}), "needs_attention": True}
    return None, rerolls


# --------------------------------------------------------------------------- #
# Orchestrator (§3D.8) — fan-out submit, then poll/QA
# --------------------------------------------------------------------------- #
def render_video(
    db: Session,
    job: VideoJob,
    *,
    script: dict[str, Any],
    product: dict[str, Any],
    invariants: dict[str, str],
    avatar_id: str,
    voice_id: str,
    options: dict[str, Any] | None = None,
) -> RenderResult:
    """Render every scene of an approved script into media assets (§3D).

    Fan-out: hero image → all b-roll i2v + all avatar scenes are independent; one
    scene failing does not fail siblings (§3D.10 partial-failure isolation). On a
    budget breach or exhausted rerolls the job halts (``result.halted``) so the
    caller routes it to the operator gate instead of §04 assembly.
    """
    options = options or {}
    result = RenderResult()
    scenes = sorted(script.get("scenes", []), key=lambda s: s.get("order", 0))
    avatar_scenes = [s for s in scenes if s.get("asset_type") == ASSET_AVATAR]
    broll_scenes = [s for s in scenes if s.get("asset_type") != ASSET_AVATAR]
    result.broll_count = len(broll_scenes)

    try:
        # Clean full VO track for §04 (also usable as avatar audio source).
        result.vo_track_asset = build_clean_vo_track(
            db, job, scenes=scenes, voice_id=voice_id
        )

        # AVATAR lane.
        for scene in avatar_scenes:
            asset = render_avatar_scene(
                db, job, scene, avatar_id=avatar_id, voice_id=voice_id, options=options,
            )
            result.avatar_assets.append(asset)
            if asset.status != "ready":
                result.blocked_scene_ids.append(str(scene["scene_id"]))

        # BROLL lane — lock hero once, then per-scene i2v + QA/reroll.
        if broll_scenes:
            result.hero_asset = generate_hero_image(
                db, job, product=product, invariants=invariants,
            )
            if result.hero_asset.status != "ready":
                result.halted = True
                result.halt_reason = "hero image failed QA"
            else:
                for scene in broll_scenes:
                    asset, rerolls = render_broll_scene(
                        db, job, scene, result.hero_asset, options=options,
                    )
                    result.reroll_count += rerolls
                    if asset is None:
                        result.blocked_scene_ids.append(str(scene["scene_id"]))
                    else:
                        result.broll_assets.append(asset)

    except cost.BudgetExceededError as exc:
        result.halted = True
        result.halt_reason = str(exc)

    if result.blocked_scene_ids and not result.halted:
        result.halted = True
        result.halt_reason = (
            f"{len(result.blocked_scene_ids)} scene(s) never reached READY "
            f"(operator gate): {result.blocked_scene_ids}"
        )

    _link_scene_assets(db, job, script, result)
    return result


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _finalize_media(asset: MediaAsset, attempt: GenAttempt, poll: ProviderResult) -> None:
    """Idempotent result funnel (§3D.4/§3D.10): webhook + poll converge here.

    No cost is added on finalise (billed at submit); a second call on an already
    ready asset is a no-op so duplicate deliveries produce exactly one READY asset.
    """
    if asset.status == "ready":
        return
    status = (poll.data or {}).get("status") if poll else None
    if poll and poll.ok and status in {"ready", "completed", "COMPLETED"}:
        asset.storage_key = poll.data.get("video_key") or poll.data.get("media_url") \
            or asset.storage_key
        asset.mime_type = poll.data.get("mime_type", asset.mime_type or "video/mp4")
        asset.status = "ready"
        attempt.status = "ready"
    else:
        asset.status = "failed"
        attempt.status = "failed"
        attempt.error = (poll.error if poll else None) or "poll did not reach READY"


def _link_scene_assets(
    db: Session, job: VideoJob, script: dict[str, Any], result: RenderResult
) -> None:
    """Persist Scene.media_asset_id links for accepted scene assets when Scene rows exist."""
    from app.core.models import Scene, Script  # local import to avoid cycles

    script_row = db.execute(
        select(Script).where(Script.video_job_id == job.id).order_by(Script.created_at.desc())
    ).scalars().first()
    if script_row is None:
        return
    scene_rows = db.execute(
        select(Scene).where(Scene.script_id == script_row.id)
    ).scalars().all()
    by_seq = {row.sequence_no: row for row in scene_rows}
    accepted = {
        str((a.meta or {}).get("scene_id")): a
        for a in result.avatar_assets + result.broll_assets
        if a.status == "ready"
    }
    for scene in script.get("scenes", []):
        row = by_seq.get(scene.get("order"))
        asset = accepted.get(str(scene.get("scene_id")))
        if row is not None and asset is not None:
            row.media_asset_id = asset.id


def _uuid_or_none(value: Any):
    """Coerce a scene_id string to UUID for FK columns; None if not a UUID."""
    import uuid as _uuid

    if value is None:
        return None
    if isinstance(value, _uuid.UUID):
        return value
    try:
        return _uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None
