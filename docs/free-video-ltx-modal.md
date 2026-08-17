# Cheap serverless video with LTX-2.5 on Modal (~$0/mo, no GPU to babysit)

This is the **recommended** video path: generate all product footage with **LTX-2.5**
(an open image-to-video model, newer than Wan 2.2) running **serverless on Modal**.
It scales to zero between renders, so ~90 videos/month of generation sits inside
Modal's **$30/month free credit** — effectively **$0**, with no GPU pod to start,
stop, or babysit.

## Why this over the alternatives

| Route | Cost/mo (90 videos) | Babysitting |
|---|---|---|
| **LTX-2.5 on Modal (this)** | **~$0–7** (inside $30 free credit) | none — scale-to-zero |
| Self-host rented 3090 + ComfyUI | ~$2–6 | you run/restart the pod |
| Managed API (fal LTX-2.3 Fast) | ~$30–58 | none, but 4–7× the cost |
| All-in SaaS (Higgsfield) | ~$150–200 | none, least control |

Everything else in the pipeline is essentially free: **Thai TTS** on Google Cloud's
free tier (4M chars/mo; you use ~45k), **Thai captions** reuse the script text we
already generate, and **TikTok posting** uses the official Content Posting API.

## How it fits

The video step is a swappable adapter (`VideoGenProvider`). The Modal adapter
(`app/core/adapters/real/ltx_modal.py`) talks to a small web app you deploy once:

```
VIDEOGEN_PROVIDER=ltx_modal
MODAL_LTX_URL=https://<you>--autougc-ltx-web.modal.run
MODAL_LTX_TOKEN=<a long random string>
DRY_RUN=false
```

- **Hero image = your real product photo, passed straight through** — no paid image
  model, and more faithful than a generated one.
- **Image-to-video** runs on Modal: the adapter base64-encodes the product photo,
  POSTs `/submit`, gets a Modal call id, then polls `/result/{id}` until the mp4 is
  ready and saves it to `MEDIA_ROOT/broll`.
- Each render returns its real `compute_seconds`, so the cost ledger records an
  **honest** per-clip number (`compute_seconds × MODAL_GPU_USD_PER_SEC`) even though
  your out-of-pocket is $0 inside the free credit.

## One-time setup

```bash
pip install modal
modal token new                      # authenticate (opens a browser)

# A shared secret so only your app can call the endpoint:
modal secret create autougc-ltx AUTOUGC_LTX_TOKEN=<pick-a-long-random-string>

modal deploy deploy/modal_ltx.py     # prints the web URL
```

Copy the printed `https://…modal.run` URL into `.env` as `MODAL_LTX_URL`, set
`MODAL_LTX_TOKEN` to the **same** random string you used above, set
`VIDEOGEN_PROVIDER=ltx_modal` and `DRY_RUN=false`, then `make restart`.

## The one thing to check after deploy: real render time

The ~$0/mo verdict assumes a 4-second clip renders in ~60–120s on an A10G. **Measure
it once**, because it's the only number that moves the cost:

```bash
curl -s -X POST "$MODAL_LTX_URL/submit" \
  -H "X-LTX-Token: $MODAL_LTX_TOKEN" -H 'content-type: application/json' \
  -d '{"image_b64":"<base64 of a product jpg>","prompt":"slow rotate, studio light","num_frames":97,"width":480,"height":832}'
# -> {"call_id":"fc-..."} ; then poll:
curl -s "$MODAL_LTX_URL/result/fc-..." -H "X-LTX-Token: $MODAL_LTX_TOKEN"
# when ready, note "compute_seconds"
```

At 90s/clip, 360 clips = ~$9.91 of compute → **$0 inside the $30 free credit**. Even
at 120s you're ~$13.22 → still $0. You only start paying above ~2.5–3× your volume.

## The one thing to get right: the model id

The exact LTX-2.5 weights repo may change. `LTX_MODEL_ID` at the top of
`deploy/modal_ltx.py` (or set it in the Modal secret) is the ONE place to update if a
download 404s — the rest is stable. The default targets the current distilled LTX
image-to-video checkpoint; swap it for the confirmed 2.5 weights when you deploy.

## Honest note on fully-generated footage

- **Hero product shots** (rotate, push-in, orbit, product-on-surface) are essentially
  solved — LTX-2.5 produces convincing footage from a single still.
- **Hands operating the product** (gripping, pressing, twisting) is still where open
  models break. Since we're going 100% generated, mitigate with shot discipline: keep
  hands-on beats to ~3s and one action, frame the product **held up to camera** rather
  than actively operated, and start i2v from a clean still where the grip already looks
  right. Plan content around hero shots + "held to camera" beats for the best realism.

## Going hands-off later (optional)

If you'd rather never think about infra, set `VIDEOGEN_PROVIDER` to a managed
endpoint instead (fal hosting LTX-2.3 Fast) — same adapter contract, ~$30–58/mo, no
Modal deploy. This LTX-Modal path stays the cheapest.
