# AutoUGC-TH — Session Handoff

**Branch:** `claude/tiktok-faceless-ai-video-93okea` (repo `greenlad24/skills`)
**Last updated:** 2026-08-18
**Runs on:** the operator's local Mac (2015 Intel, macOS 12) — no Docker, no Redis, no Node needed.

> This file is the context bridge between the remote (cloud) Claude Code session that
> built most of this and a **local** Claude Code session running on the Mac. The local
> session can do the one thing the remote one can't: **run the app, deploy to Modal, and
> read Modal-side logs.** Start there.

---

## What this project is

A locally-run web app that turns a **Thai product** into a **faceless Thai-language
TikTok-Shop review video**, fully generated (no stock footage, no avatar). Budget
~300฿/month. Flow:

```
product title (TH)  →  SocialCrawl (TikTok Shop TH search: title + image + THB price)
                    →  Anthropic (Thai script, claim-safe)
                    →  Google Cloud TTS (Thai voice-over)
                    →  LTX-2.5 on Modal (image-to-video b-roll clips)
                    →  editing / captioning  →  approval  →  TikTok Content Posting API
```

## The approved stack (do not swap without asking the operator)

| Capability | Provider | Env selector | Notes |
|---|---|---|---|
| LLM | Anthropic | `LLM_PROVIDER=anthropic` | models: `claude-sonnet-5`, `claude-haiku-4-5` |
| Scraper | **SocialCrawl** | `SCRAPER_PROVIDER=socialcrawl` | TH search only (by-URL endpoints are US-only) |
| TTS | Google Cloud TTS | `TTS_PROVIDER=google_tts` | Thai Neural2 voice, free tier |
| Video | **LTX-2.5 on Modal** | `VIDEOGEN_PROVIDER=ltx_modal` | serverless GPU, scales to zero |
| Posting | TikTok Content Posting API | `POSTING_PROVIDER=tiktok` | inbox/direct modes |

Apify + Firecrawl scraper adapters still exist but are **not** the default (SocialCrawl
replaced them — Apify's TikTok-Shop actors were too slow/flaky on residential proxies).

---

## STATUS: what works vs. what's blocked

**Working end-to-end (verified in a live run):**
- ✅ SocialCrawl TH search returns the exact product (title, THB price, images)
- ✅ High-res product image (ByteImg CDN template rewritten `:400:400` → `:1080:1080`)
- ✅ Anthropic Thai script (200), claim gate passes
- ✅ Google Cloud TTS Thai voice-over (200)
- ✅ Modal LTX `/submit` accepted (200), clips begin rendering

**The one remaining blocker — video render never reported `ready`:**
In the last live run, **every `/result` poll returned `202` (still rendering)** for the
whole run; the pipeline's poll loop gave up, treated each clip as failed, rerolled, and
after 3 rerolls × 4 scenes the job halted at the operator gate
(`reason: "N scene(s) never reached READY"`, `reroll_rate: 3.0`).

**Fixes already pushed for this (need apply + verify):**
1. `service.run_generation` now paces the poll at **5 s** and waits up to **~10 min/clip**
   (`POLL_MAX_ATTEMPTS 60 → 120`); it returns the instant a render reports ready.
   (Fakes/tests still pass `poll_sleep=0.0`, so they stay instant.)
2. `deploy/modal_ltx.py` `scaledown_window 120 → 600` so the ~5 clips of one job reuse a
   **warm** container (only the first cold-starts). **Requires `modal deploy`.**

A clip that reaches `ready` passes QA automatically (product-similarity defaults ≥0.86 >
0.85 threshold), so if the render simply completes, the whole job should finish.

---

## ▶️ IMMEDIATE NEXT STEPS (do these first, in order)

```bash
# 1. Get the latest fixes
git pull origin claude/tiktok-faceless-ai-video-93okea

# 2. Redeploy the Modal app (picks up the longer warm window)
modal deploy deploy/modal_ltx.py

# 3. Restart the app (Ctrl-C the running one first)
bash scripts/run-local-mac.sh

# 4. Start a NEW video in the UI (http://localhost:8000) with the Thai product title.
```

**Then confirm slow-vs-failing** — this is the key diagnostic the remote session could NOT do:

```bash
# Watch Modal-side render logs while the job runs
modal app logs autougc-ltx        # (app name is the one deploy/modal_ltx.py defines)

# OR test a single render end-to-end by hand:
#   POST <MODAL_LTX_URL>/submit  with a small image_b64  → returns {"call_id": ...}
#   GET  <MODAL_LTX_URL>/result/<call_id>  repeatedly     → 202 … then 200 (ready) or 200 {"status":"failed"}
# (send header  X-LTX-Token: <MODAL_LTX_TOKEN from .env>  if a token is set)
```

**Report the first `/result` that returns `200`:**
- `200 {"status":"ready", ...}` → render works, just slow → the poll fix is enough. Watch the
  job advance GENERATING → EDITING → CAPTIONING → AWAITING_APPROVAL.
- `200 {"status":"failed", "error": ...}` → render is genuinely broken on Modal (OOM,
  model load, bad frame count). Fix Modal-side: check GPU size (`LTX_GPU`, currently A10G),
  `num_frames`, model id (`Lightricks/LTX-Video-0.9.7-distilled`), and the `modal app logs`
  traceback.

Expect the **first** video to take ~10–15 min (cold start + model load); later videos are
faster with the warm container.

---

## How to run locally

`bash scripts/run-local-mac.sh` — idempotent. It:
- ensures Python 3.11 + a prebuilt ffmpeg (no compiling), Redis optional,
- writes/updates `.env` from `.env.example` on first run,
- uses a **filesystem Celery broker** (no Redis) when Redis isn't present,
- serves the **prebuilt** `frontend/dist` from FastAPI (no Node needed),
- launches uvicorn (web, :8000) **and** the Celery worker together.

**Two-process gotcha:** web and worker are separate processes. Keys saved via the web
onboarding are written to `.env` and applied to the web process; the worker re-reads
`.env` **per task** (Celery `task_prerun` → `config.reload_settings_from_dotenv()`), so it
picks them up without a restart.

---

## Architecture map (key files)

- `app/main.py` — FastAPI app; jobs router; `/api/products` catalog; SPA serving;
  `/ws/jobs` WebSocket; startup SQLite schema + column patch.
- `app/core/config.py` — all settings + `reload_settings_from_dotenv()`.
- `app/core/queue.py` — Celery app; filesystem broker; `task_prerun` env reload.
- `app/core/adapters/` — provider protocol (`base.py`), registry (`registry.py`),
  fakes (`fakes.py`), and `real/`:
  - `real/socialcrawl.py` — TH search → product mapping + hi-res image rewrite
  - `real/anthropic_llm.py`, `real/google_tts.py`, `real/ltx_modal.py`, `real/tiktok_posting.py`
  - `real/apify.py` — alternative scraper (not default)
- `app/modules/research/` — research stage; `product/` adapters + domain router; `tasks.py`
  (uses the SocialCrawl search seed; skips re-scrape for already-scraped products).
- `app/modules/generation/` — the render pipeline:
  - `pipeline.py` — hero image + b-roll i2v + QA/reroll loop + `_poll_until_ready`
  - `service.py` — `run_generation` (sets the poll cadence)
  - `qa.py` — product-consistency similarity gate
  - `constants.py` — `POLL_MAX_ATTEMPTS`, `POLL_INTERVAL_SEC`, `MAX_REROLLS`, thresholds
- `app/modules/onboarding/` — setup wizard API; `env_store.py` (whitelist, never wipes a
  key on blank submit); `service.py` (key-gated status, pins approved stack on finish).
- `deploy/modal_ltx.py` — the Modal app hosting LTX-2.5 (`modal deploy` to update).
- `frontend/` — React app; **`frontend/dist` is committed** (rebuild with `npm run build`
  in `frontend/` if you change `frontend/src`, then commit the new dist).
- `scripts/run-local-mac.sh` — the local launcher.

## Product reuse (already built)

Scrapes are saved with a stable `Product.external_product_id`. `GET /api/products` lists
saved products; `POST /api/jobs` with `reuse_product_id` makes another video for a saved
product and **skips the paid scrape** (research detects it's already scraped).

## Onboarding gate

The setup wizard is forced whenever a **required** key is missing — Anthropic, Google TTS,
SocialCrawl, or the Modal video URL — even after first-run. **TikTok posting is optional**
(only needed at the posting stage). `DRY_RUN=true` (fakes) needs no keys. The wizard opens
on the first unfilled step and shows "✓ set" for already-configured keys; leaving a field
blank keeps the saved value.

---

## Secrets / config notes

- All secrets live only in the operator's local `.env` (git-ignored). **Never commit `.env`
  or echo a key** into code, logs, commits, or this file.
- Required to run live: `ANTHROPIC_API_KEY`, `GOOGLE_TTS_API_KEY`, `SOCIALCRAWL_API_KEY`,
  `MODAL_LTX_URL` (+ optional `MODAL_LTX_TOKEN`). Optional: `TIKTOK_ACCESS_TOKEN`.
- Useful tunables: `SOCIALCRAWL_REGION` (default `TH`), `SOCIALCRAWL_IMAGE_SIZE`
  (default `1080`, `0` disables the hi-res rewrite), `LTX_GPU`, `MODAL_LTX_TIMEOUT_SECONDS`.

## Working conventions

- Develop only on `claude/tiktok-faceless-ai-video-93okea`; commit + push there.
- Run tests with `python -m pytest app/ -q` (all pass as of this handoff).
- Do not open a PR unless the operator asks.
