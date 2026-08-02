"""Wan (Alibaba) image-to-video via a self-hosted ComfyUI server — the FREE
`VideoGenProvider` (§1.6).

This is the open-source, near-$0 alternative to the paid Seedance/fal route. It
drives a ComfyUI instance running a Wan 2.x (or CogVideoX / LTX) image-to-video
workflow. Host ComfyUI for free on a Kaggle/Colab GPU (see
`notebooks/wan_comfyui_kaggle.ipynb`) or on a cheap rented GPU, then set:

    VIDEOGEN_PROVIDER=wan_comfyui
    COMFYUI_URL=https://<your-comfyui-tunnel-or-host>

Cost model: generation is free (your GPU / a free tier), so every ProviderResult
reports `cost_usd=0.0` — the pipeline's budget guard simply never trips on video.

How it maps to the contract:
  * generate_hero_image → passes the REAL product photo straight through as the
    hero (no paid image model, no GPU) — cheapest and most faithful.
  * submit_image_to_video → uploads the hero image to ComfyUI, fills the workflow
    template's placeholders, queues it (POST /prompt), returns the prompt_id.
  * poll → GET /history/{id}; while running returns status "processing"; when done
    downloads the video into MEDIA_ROOT and returns status "ready" + video_key.

The ComfyUI *workflow* is install-specific (node ids depend on your graph), so the
graph itself is a JSON template you export from ComfyUI ("Save (API Format)") with
these placeholder tokens substituted at runtime:

    __INPUT_IMAGE__  __PROMPT__  __NEGATIVE__  __FRAMES__  __WIDTH__  __HEIGHT__  __SEED__

A minimal sample lives at real/workflows/wan_i2v_template.json — replace it with
your own exported graph and point COMFYUI_WORKFLOW_PATH at it.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.core.adapters.base import ProviderResult
from app.core.adapters.registry import register_real
from app.core.config import settings

_ASPECTS = {"9:16": (480, 832), "16:9": (832, 480), "1:1": (512, 512)}
_DEFAULT_WH = (480, 832)  # 9:16, small enough for a free-tier GPU
_VIDEO_EXTS = (".mp4", ".webm", ".mov", ".gif")
_OUTPUT_KEYS = ("videos", "gifs", "images")  # ComfyUI output node result keys
_SAMPLE_WORKFLOW = Path(__file__).parent / "workflows" / "wan_i2v_template.json"


def _seed_from(key: str) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def _substitute(node: Any, mapping: dict[str, Any]) -> Any:
    """Recursively replace placeholder tokens in every string value of the graph."""
    if isinstance(node, dict):
        return {k: _substitute(v, mapping) for k, v in node.items()}
    if isinstance(node, list):
        return [_substitute(v, mapping) for v in node]
    if isinstance(node, str):
        if node in mapping:                       # whole-value token → keep native type
            return mapping[node]
        for token, value in mapping.items():      # inline token inside a longer string
            if token in node:
                node = node.replace(token, str(value))
        return node
    return node


class WanComfyUIVideoProvider:
    """Free `VideoGenProvider` backed by a self-hosted ComfyUI + Wan workflow."""

    provider_name = "wan-comfyui"

    def __init__(self) -> None:
        if not settings.COMFYUI_URL:
            raise RuntimeError(
                "COMFYUI_URL is not set. Point it at your ComfyUI server "
                "(free Kaggle/Colab GPU — see notebooks/wan_comfyui_kaggle.ipynb — "
                "or a rented GPU), or set DRY_RUN=true for the fake provider."
            )
        self._base = settings.COMFYUI_URL.rstrip("/")
        self._fps = max(1, int(settings.COMFYUI_FPS))
        wf_path = settings.COMFYUI_WORKFLOW_PATH or str(_SAMPLE_WORKFLOW)
        self._workflow = json.loads(Path(wf_path).read_text(encoding="utf-8"))
        self._client_id = uuid.uuid4().hex

    # -- VideoGenProvider ---------------------------------------------------- #

    def generate_hero_image(
        self, *, prompt: str, refs: list[str], idempotency_key: str
    ) -> ProviderResult:
        """Free hero = the real product photo, passed straight through (no gen)."""
        if not refs:
            return ProviderResult(
                ok=False,
                error="wan_comfyui hero needs a product reference image (refs is empty); "
                "the free adapter does not text-to-image.",
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
            image_name = self._upload_image(image_key)
            width, height = _ASPECTS.get(aspect, _DEFAULT_WH)
            frames = max(1, round(float(seconds) * self._fps))
            graph = _substitute(self._workflow, {
                "__INPUT_IMAGE__": image_name,
                "__PROMPT__": prompt,
                "__NEGATIVE__": "blurry, distorted, watermark, text, extra fingers",
                "__FRAMES__": frames,
                "__WIDTH__": width,
                "__HEIGHT__": height,
                "__SEED__": _seed_from(idempotency_key),
            })
            with httpx.Client(base_url=self._base, timeout=60) as c:
                r = c.post("/prompt", json={"prompt": graph, "client_id": self._client_id})
                r.raise_for_status()
                prompt_id = r.json()["prompt_id"]
        except httpx.HTTPError as exc:
            return ProviderResult(ok=False, error=f"comfyui submit error: {exc}")
        except (KeyError, ValueError) as exc:
            return ProviderResult(ok=False, error=f"comfyui bad response: {exc}")

        return ProviderResult(
            ok=True,
            data={"status": "processing", "model": model or "wan", "seconds": seconds, "aspect": aspect},
            cost_usd=0.0,                       # free — your GPU
            usage={"seconds": seconds, "frames": frames},
            provider_job_id=prompt_id,
        )

    def poll(self, *, provider_job_id: str) -> ProviderResult:
        try:
            with httpx.Client(base_url=self._base, timeout=30) as c:
                r = c.get(f"/history/{provider_job_id}")
                r.raise_for_status()
                history = r.json()
        except httpx.HTTPError as exc:
            return ProviderResult(ok=False, error=f"comfyui poll error: {exc}")

        entry = history.get(provider_job_id)
        if not entry:                            # not in history yet → still queued/running
            return ProviderResult(
                ok=True, data={"status": "processing"}, provider_job_id=provider_job_id,
            )

        status = (entry.get("status") or {})
        if status.get("status_str") == "error":
            return ProviderResult(ok=False, error="comfyui workflow errored", provider_job_id=provider_job_id)

        file_ref = self._find_output(entry.get("outputs") or {})
        if file_ref is None:
            # Completed with no discoverable video, or still running.
            done = status.get("completed") is True
            if done:
                return ProviderResult(ok=False, error="comfyui finished with no video output",
                                      provider_job_id=provider_job_id)
            return ProviderResult(ok=True, data={"status": "processing"}, provider_job_id=provider_job_id)

        try:
            video_key = self._download(file_ref, provider_job_id)
        except (httpx.HTTPError, OSError) as exc:
            return ProviderResult(ok=False, error=f"comfyui download error: {exc}",
                                  provider_job_id=provider_job_id)

        return ProviderResult(
            ok=True,
            data={"status": "ready", "video_key": video_key, "mime_type": "video/mp4"},
            cost_usd=0.0,
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

    def _upload_image(self, image_key: str) -> str:
        data = self._read_bytes(image_key)
        name = f"{hashlib.sha256(data).hexdigest()[:16]}.png"
        with httpx.Client(base_url=self._base, timeout=120) as c:
            r = c.post("/upload/image",
                       files={"image": (name, data, "image/png")},
                       data={"overwrite": "true"})
            r.raise_for_status()
            return r.json().get("name", name)

    @staticmethod
    def _find_output(outputs: dict) -> dict | None:
        """Find the first video-like output file across all output nodes."""
        for node_out in outputs.values():
            for key in _OUTPUT_KEYS:
                for f in node_out.get(key, []) or []:
                    fn = f.get("filename", "")
                    if fn.lower().endswith(_VIDEO_EXTS):
                        return f
        return None

    def _download(self, file_ref: dict, prompt_id: str) -> str:
        params = {
            "filename": file_ref.get("filename", ""),
            "subfolder": file_ref.get("subfolder", ""),
            "type": file_ref.get("type", "output"),
        }
        with httpx.Client(base_url=self._base, timeout=300) as c:
            r = c.get("/view", params=params); r.raise_for_status()
            content = r.content
        out_dir = Path(settings.MEDIA_ROOT) / "broll"
        out_dir.mkdir(parents=True, exist_ok=True)
        ext = os.path.splitext(params["filename"])[1] or ".mp4"
        out_path = out_dir / f"{prompt_id}{ext}"
        out_path.write_bytes(content)
        return str(out_path)


# Selected when VIDEOGEN_PROVIDER=wan_comfyui and DRY_RUN=false.
register_real("videogen", "wan_comfyui", WanComfyUIVideoProvider)
