# Free product-b-roll video with Wan (open-source, ~$0)

The tool can generate product b-roll with **Wan** — an open-source Chinese image-to-video
model (the free equivalent of Seedance) — running on **ComfyUI** on a **free GPU**, instead
of paying a video API. Cost per video for the generation step drops from ~$1–2 to **$0**
(your GPU / a free tier).

## How it fits

The video step is a swappable adapter (`VideoGenProvider`). The Wan adapter
(`app/core/adapters/real/wan_comfyui.py`) talks to a ComfyUI server you host:

```
VIDEOGEN_PROVIDER=wan_comfyui
COMFYUI_URL=https://<your-comfyui-url>     # a free Kaggle/Colab GPU, or a rented GPU
DRY_RUN=false
```

- **Hero image = your real product photo, passed straight through** — no paid image model,
  no GPU, and more faithful than a generated one.
- **Image-to-video** runs on ComfyUI: the adapter uploads the product photo, fills the
  workflow's placeholders, queues it, polls, and saves the finished clip. Every result
  reports `cost_usd=0.0`, so the per-video budget guard never trips on video.

## Setup (free GPU)

1. Open **`notebooks/wan_comfyui_kaggle.ipynb`** in Kaggle (GPU + Internet on) or Colab.
2. Run the cells — it installs ComfyUI + Wan and prints a public URL like
   `https://xxxx.trycloudflare.com`.
3. Put that URL in `.env` as `COMFYUI_URL`, set `VIDEOGEN_PROVIDER=wan_comfyui` and
   `DRY_RUN=false`, then `make restart`.
4. Keep the notebook tab running while you generate. Free GPUs are time-limited (Kaggle
   ~30h/week); when it stops, re-run the notebook, take the new URL, update `.env`, `make restart`.

## The one thing to get right: the ComfyUI workflow

ComfyUI graphs are install-specific (node ids depend on your exact nodes/models), so the
tool ships a **sample** at `app/core/adapters/real/workflows/wan_i2v_template.json` with
placeholder tokens:

```
__INPUT_IMAGE__  __PROMPT__  __NEGATIVE__  __FRAMES__  __WIDTH__  __HEIGHT__  __SEED__
```

The most reliable path: open the ComfyUI UI (at your tunnel URL), build a working Wan
image-to-video graph once, then **Save (API Format)**, drop those tokens in where the input
image / prompts / length / size / seed go, save the file, and point
`COMFYUI_WORKFLOW_PATH` at it. The adapter substitutes the tokens on every job.

## Going faster later

Free tiers are rate-limited. When you want speed without the limits, run the *same*
ComfyUI on a rented GPU (**RunPod / Vast.ai**, ~$0.20–0.50/hr → dozens of clips/hour →
fractions of a cent per video) and use its URL as `COMFYUI_URL`. Nothing else changes.

## Honest note for a cheap-gadget account

Generated b-roll is now free — but for low-priced products, **real or supplier footage**
(your phone, or the product's own listing media) is still cheaper *and* converts better on
TikTok Shop than any AI video. Use Wan when you genuinely need generated shots; use real
footage when you can.
