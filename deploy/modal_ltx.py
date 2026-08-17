"""Serverless LTX-2.5 image-to-video on Modal — the cheap "no GPU to babysit" path.

Deploy this once, then point the app's `ltx_modal` adapter at the URL it prints:

    pip install modal
    modal token new                      # one-time auth
    modal secret create autougc-ltx AUTOUGC_LTX_TOKEN=<pick-a-long-random-string>
    modal deploy deploy/modal_ltx.py     # prints https://<you>--autougc-ltx-web.modal.run

Then in the app's .env:

    VIDEOGEN_PROVIDER=ltx_modal
    MODAL_LTX_URL=https://<you>--autougc-ltx-web.modal.run
    MODAL_LTX_TOKEN=<the same random string>
    DRY_RUN=false

Cost model: Modal bills per GPU-second and scales to zero between renders, so a
~4s clip on an A10G (~60–120s render) costs ~$0.02–0.04, and 90 videos/month
(~360 clips) is ~$7–13 of compute — inside Modal's $30/month free credit, i.e.
effectively $0. The web app exposes a submit/poll contract that mirrors the
`VideoGenProvider` the adapter expects:

    POST /submit   {image_b64, prompt, negative, num_frames, width, height, seed}
                   -> {"call_id": "<modal-function-call-id>"}
    GET  /result/{call_id}
                   -> 202 {"status":"processing"}                       (still rendering)
                   -> 200 {"status":"ready","video_b64":...,"compute_seconds":N}

Both endpoints require the header `X-LTX-Token: <MODAL_LTX_TOKEN>`.

> Model id: the exact LTX-2.5 weights repo may change. `LTX_MODEL_ID` (below, or
> set it in the Modal secret) is the ONE place to update if a download 404s — the
> rest is stable. The default targets the current distilled LTX image-to-video
> checkpoint; swap it for the 2.5 weights once you've confirmed the repo name.
"""

from __future__ import annotations

import os

import modal

# --- The one thing to update if a download 404s: the model repo id. -----------
LTX_MODEL_ID = os.environ.get("LTX_MODEL_ID", "Lightricks/LTX-Video-0.9.7-distilled")
# GPU tier. A10G (24GB) is the cheap default; bump to "L40S" for the 48GB models.
LTX_GPU = os.environ.get("LTX_GPU", "A10G")
# ------------------------------------------------------------------------------

CACHE_DIR = "/cache"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "torch",
        "diffusers>=0.32.0",
        "transformers>=4.44",
        "accelerate",
        "sentencepiece",
        "imageio[ffmpeg]",
        "pillow",
        "fastapi[standard]",
    )
    # Keep the big weights on a persistent volume so cold starts don't re-download.
    .env({"HF_HOME": CACHE_DIR})
)

app = modal.App("autougc-ltx")
cache = modal.Volume.from_name("autougc-ltx-cache", create_if_missing=True)
secret = modal.Secret.from_name("autougc-ltx")


@app.cls(
    gpu=LTX_GPU,
    image=image,
    volumes={CACHE_DIR: cache},
    secrets=[secret],
    scaledown_window=120,   # stay warm 2 min after a render, then scale to zero
    timeout=1200,           # a single render may take a couple of minutes
)
class LTX:
    @modal.enter()
    def load(self) -> None:
        import torch
        from diffusers import LTXImageToVideoPipeline

        self.pipe = LTXImageToVideoPipeline.from_pretrained(
            LTX_MODEL_ID,
            torch_dtype=torch.bfloat16,
            cache_dir=CACHE_DIR,
        ).to("cuda")
        # Persist any newly-downloaded weights for the next cold start.
        cache.commit()

    @modal.method()
    def render(self, payload: dict) -> dict:
        """Render one image-to-video clip; return base64 mp4 + GPU seconds used."""
        import base64
        import io
        import time

        import torch
        from diffusers.utils import export_to_video
        from PIL import Image

        started = time.time()
        img_bytes = base64.b64decode(payload["image_b64"])
        image_in = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        width = int(payload.get("width", 480))
        height = int(payload.get("height", 832))
        image_in = image_in.resize((width, height))

        num_frames = int(payload.get("num_frames", 97))   # 8*12 + 1
        seed = int(payload.get("seed", 0))
        generator = torch.Generator(device="cuda").manual_seed(seed)

        result = self.pipe(
            image=image_in,
            prompt=payload.get("prompt", ""),
            negative_prompt=payload.get(
                "negative", "blurry, distorted, watermark, text, extra fingers"
            ),
            width=width,
            height=height,
            num_frames=num_frames,
            generator=generator,
        )
        frames = result.frames[0]

        out_path = "/tmp/clip.mp4"
        export_to_video(frames, out_path, fps=int(payload.get("fps", 24)))
        with open(out_path, "rb") as fh:
            video_b64 = base64.b64encode(fh.read()).decode("ascii")

        return {"video_b64": video_b64, "compute_seconds": round(time.time() - started, 2)}


@app.function(image=image, secrets=[secret])
@modal.asgi_app()
def web():
    """Thin submit/poll HTTP layer over the GPU class (mirrors VideoGenProvider)."""
    from fastapi import FastAPI, Header, HTTPException
    from fastapi.responses import JSONResponse

    api = FastAPI()
    expected = os.environ.get("AUTOUGC_LTX_TOKEN", "")

    def _auth(token: str) -> None:
        # Constant-ish check; if no token configured, allow (dev only).
        if expected and token != expected:
            raise HTTPException(status_code=401, detail="bad or missing X-LTX-Token")

    @api.get("/health")
    def health() -> dict:
        return {"ok": True, "model": LTX_MODEL_ID, "gpu": LTX_GPU}

    @api.post("/submit")
    def submit(payload: dict, x_ltx_token: str = Header(default="")) -> dict:
        _auth(x_ltx_token)
        if "image_b64" not in payload:
            raise HTTPException(status_code=422, detail="image_b64 is required")
        call = LTX().render.spawn(payload)
        return {"call_id": call.object_id}

    @api.get("/result/{call_id}")
    def result(call_id: str, x_ltx_token: str = Header(default="")):
        _auth(x_ltx_token)
        call = modal.FunctionCall.from_id(call_id)
        try:
            out = call.get(timeout=0)
        except TimeoutError:
            return JSONResponse(status_code=202, content={"status": "processing"})
        return {"status": "ready", **out}

    return api
