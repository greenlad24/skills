"""LTX-2.5 image-to-video via a self-deployed Modal serverless app — the cheap
"no GPU to babysit" `VideoGenProvider` (§1.6).

The single approved video route: instead of keeping a GPU running, you deploy
LTX-2.5 to Modal once (see deploy/modal_ltx.py) and it scales to zero between
renders. Set:

    VIDEOGEN_PROVIDER=ltx_modal
    MODAL_LTX_URL=https://<you>--autougc-ltx-web.modal.run
    MODAL_LTX_TOKEN=<the shared secret you set in the Modal secret>

Cost model: Modal bills per GPU-second. The pipeline records the i2v cost at SUBMIT,
so this adapter charges an estimate there (`MODAL_LTX_EST_SECONDS_PER_CLIP` ×
`MODAL_GPU_USD_PER_SEC`); at poll it reports the render's ACTUAL `compute_seconds`
(and derived `actual_usd`) in `usage` for reconciliation, without double-charging.
Inside Modal's $30/month free credit your real out-of-pocket is $0.

Contract mapping (identical shape to the other VideoGenProviders):
  * generate_hero_image → passes the REAL product photo straight through (no paid
    image model) — cheapest and most faithful.
  * submit_image_to_video → base64-encodes the hero, POSTs /submit, returns the
    Modal function call id as provider_job_id.
  * poll → GET /result/{id}; 202 => still rendering ("processing"); 200 => decode
    the mp4 into MEDIA_ROOT/broll and return "ready" + video_key.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import httpx

from app.core.adapters.base import ProviderResult
from app.core.adapters.registry import register_real
from app.core.config import settings

# LTX likes dimensions divisible by 32; keep clips small for cheap/fast renders.
_ASPECTS = {"9:16": (480, 832), "16:9": (832, 480), "1:1": (512, 512)}
_DEFAULT_WH = (480, 832)


def _seed_from(key: str) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def _snap_frames(seconds: float, fps: int) -> int:
    """LTX needs (num_frames - 1) divisible by 8; snap to the nearest valid count."""
    raw = max(1.0, float(seconds)) * max(1, int(fps))
    k = max(1, round((raw - 1) / 8))
    return 8 * k + 1


class LTXModalVideoProvider:
    """Serverless `VideoGenProvider` backed by LTX-2.5 on Modal."""

    provider_name = "ltx-modal"

    def __init__(self) -> None:
        if not settings.MODAL_LTX_URL:
            raise RuntimeError(
                "MODAL_LTX_URL is not set. Deploy deploy/modal_ltx.py "
                "(`modal deploy deploy/modal_ltx.py`) and point MODAL_LTX_URL at the "
                "URL it prints, or set DRY_RUN=true for the fake provider."
            )
        self._base = settings.MODAL_LTX_URL.rstrip("/")
        self._fps = max(1, int(settings.LTX_FPS))
        self._timeout = max(30, int(settings.MODAL_LTX_TIMEOUT_SECONDS))
        self._usd_per_sec = float(settings.MODAL_GPU_USD_PER_SEC)
        self._est_seconds = float(settings.MODAL_LTX_EST_SECONDS_PER_CLIP)
        self._headers = (
            {"X-LTX-Token": settings.MODAL_LTX_TOKEN} if settings.MODAL_LTX_TOKEN else {}
        )

    # -- VideoGenProvider ---------------------------------------------------- #

    def generate_hero_image(
        self, *, prompt: str, refs: list[str], idempotency_key: str
    ) -> ProviderResult:
        """Cheapest hero = the real product photo, passed straight through."""
        if not refs:
            return ProviderResult(
                ok=False,
                error="ltx_modal hero needs a product reference image (refs is empty); "
                "the serverless adapter does image-to-video, not text-to-image.",
            )
        return ProviderResult(
            ok=True,
            data={"image_key": refs[0], "mime_type": "image/*", "seed": _seed_from(idempotency_key)},
            cost_usd=0.0,
            usage={"images": 0, "note": "real-product-passthrough"},
        )

    def submit_image_to_video(
        self, *, image_key: str, prompt: str, model: str, seconds: float, aspect: str,
        idempotency_key: str,
    ) -> ProviderResult:
        try:
            image_b64 = base64.b64encode(self._read_bytes(image_key)).decode("ascii")
            width, height = _ASPECTS.get(aspect, _DEFAULT_WH)
            frames = _snap_frames(seconds, self._fps)
            payload = {
                "image_b64": image_b64,
                "prompt": prompt,
                "negative": "blurry, distorted, watermark, text, extra fingers",
                "num_frames": frames,
                "width": width,
                "height": height,
                "fps": self._fps,
                "seed": _seed_from(idempotency_key),
            }
            with httpx.Client(base_url=self._base, timeout=self._timeout) as c:
                r = c.post("/submit", json=payload, headers=self._headers)
                r.raise_for_status()
                call_id = r.json()["call_id"]
        except httpx.HTTPError as exc:
            return ProviderResult(ok=False, error=f"modal ltx submit error: {exc}")
        except (KeyError, ValueError) as exc:
            return ProviderResult(ok=False, error=f"modal ltx bad response: {exc}")

        # The pipeline bills the i2v step from the SUBMIT result, so charge an
        # estimate here (est_seconds * $/GPU-sec); poll returns the actual
        # compute_seconds in usage for reconciliation. Inside Modal's free credit
        # your real out-of-pocket is still $0.
        est_cost = round(self._est_seconds * self._usd_per_sec, 6)
        return ProviderResult(
            ok=True,
            data={"status": "processing", "model": model or "ltx-2.5", "seconds": seconds, "aspect": aspect},
            cost_usd=est_cost,
            usage={"seconds": seconds, "frames": frames, "est_render_seconds": self._est_seconds},
            provider_job_id=call_id,
        )

    def poll(self, *, provider_job_id: str) -> ProviderResult:
        try:
            with httpx.Client(base_url=self._base, timeout=self._timeout) as c:
                r = c.get(f"/result/{provider_job_id}", headers=self._headers)
                if r.status_code == 202:
                    return ProviderResult(
                        ok=True, data={"status": "processing"}, provider_job_id=provider_job_id,
                    )
                r.raise_for_status()
                body = r.json()
        except httpx.HTTPError as exc:
            return ProviderResult(ok=False, error=f"modal ltx poll error: {exc}",
                                  provider_job_id=provider_job_id)
        except ValueError as exc:
            return ProviderResult(ok=False, error=f"modal ltx bad result: {exc}",
                                  provider_job_id=provider_job_id)

        if body.get("status") == "failed":
            return ProviderResult(ok=False, error=f"modal ltx render failed: {body.get('error', '?')}",
                                  provider_job_id=provider_job_id)
        if body.get("status") != "ready" or "video_b64" not in body:
            return ProviderResult(ok=False, error="modal ltx result missing video",
                                  provider_job_id=provider_job_id)

        try:
            video_key = self._save_video(body["video_b64"], provider_job_id)
        except (ValueError, OSError) as exc:
            return ProviderResult(ok=False, error=f"modal ltx save error: {exc}",
                                  provider_job_id=provider_job_id)

        # Cost was billed at submit (pipeline convention); report the ACTUAL compute
        # time here for reconciliation without double-charging the ledger.
        compute_seconds = float(body.get("compute_seconds", 0.0))
        return ProviderResult(
            ok=True,
            data={"status": "ready", "video_key": video_key, "mime_type": "video/mp4"},
            cost_usd=0.0,
            usage={
                "compute_seconds": compute_seconds,
                "actual_usd": round(compute_seconds * self._usd_per_sec, 6),
            },
            provider_job_id=provider_job_id,
        )

    # -- helpers ------------------------------------------------------------- #

    def _read_bytes(self, image_key: str) -> bytes:
        """Resolve an image_key to bytes: a URL, an absolute path, or MEDIA_ROOT-relative."""
        if image_key.startswith(("http://", "https://")):
            with httpx.Client(timeout=60) as c:
                r = c.get(image_key); r.raise_for_status(); return r.content
        p = Path(image_key)
        if not p.is_absolute():
            p = Path(settings.MEDIA_ROOT) / image_key
        return p.read_bytes()

    def _save_video(self, video_b64: str, call_id: str) -> str:
        data = base64.b64decode(video_b64)
        out_dir = Path(settings.MEDIA_ROOT) / "broll"
        out_dir.mkdir(parents=True, exist_ok=True)
        # Sanitize the call id for use as a filename.
        safe = hashlib.sha256(call_id.encode()).hexdigest()[:16]
        out_path = out_dir / f"{safe}.mp4"
        out_path.write_bytes(data)
        return str(out_path)


# Selected when VIDEOGEN_PROVIDER=ltx_modal and DRY_RUN=false.
register_real("videogen", "ltx_modal", LTXModalVideoProvider)
