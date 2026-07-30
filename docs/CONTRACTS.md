# AutoUGC-TH — Foundation Contracts (single source of truth for module agents)

This is the authoritative reference for anyone building a module. It reconciles the
spec's cross-section naming notes into **final canonical names** and documents the four
shared contracts: the data model, the job state machine, the adapter interfaces, and the
REST/WS API. If code and this doc ever disagree, the code in `app/core/` wins — file an
issue with the foundation owner rather than forking core.

Import everything from `app.core.*`. Never edit `app/core/` or `app/main.py`.

---

## 1. Reconciliation decisions (README §6 integration notes)

The spec was authored in parallel; §1's ER model is canonical for names, and later
sections' extra fields are **added**, not renamed. Final decisions:

| Item | Decision |
|---|---|
| **`CostLedgerEntry`** | Class name is `CostLedgerEntry` (per README §6 / §3); DB table is `cost_ledger` (§1 `COST_LEDGER`). Merges §3's per-call fields: `scene_id`, `model`, `kind`, `attempt`, `is_reroll`. Append-only. |
| **`ConsentRecord`** | §1 base fields canonical: `consenter_name`, `consent_type`, `document_key`, `consented_at`. §3's `subject_name` **==** `consenter_name` (use `consenter_name`). §6 compliance fields added: `subject_is_operator`, `identity_verified`, `identity_verification_ref`, `biometric_explicit_consent`, `voice_licensed`, `scope`, `term`, `revocable`, `revoked`, `revoked_at`, `takedown_contact`, `source_clip_sha256`, `signature_ref`, `ruleset_version`. |
| **`Post`** | §1 names canonical: `posting_provider`, `external_post_id`, `post_url`, `ai_disclosure_set`, `product_tag_attached`, `status`, `posted_at`. §5 extension fields added: `variant_group_id`, `account_ref`, `provider_post_id`, `tiktok_publish_id`, `tiktok_video_id`, `visibility`, `fail_reason`, `disclose_commercial`, `disclose_your_brand`, `disclose_branded_content`, `is_ai_generated`, `shop_tag_status`, `shop_tagged_at`, `deep_link`, `scheduled_at`, `latest_score`, `latest_metrics_at`. (`posted_at` is the canonical publish timestamp; §5's `published_at` maps to it.) |
| **`PerformanceRecord`** | §1 names canonical: `captured_at`, `views`, `likes`, `comments`, `shares`, `ctr`, `conversion`, `is_winner`. §5 additions: `source`, `favorites`, `avg_watch_time_s`, `full_video_watch_rate`, `reach`, `profile_visits`, `product_clicks`, `orders`, `gmv`, `commission`, `score`. |
| **`SwipeSource`, `SwipeVideo`** | New entities from §2, ratified. `SwipeVideo.transcript_id` / `scene_data_id` are opaque IDs (the `Transcript`/`SceneAnalysis` tables are owned by the research module, not core). All mined rows carry `signal_type="engagement_proxy"`. |
| **`GenAttempt`** | New entity from §3. One row per external generation call. `UNIQUE(idempotency_key)` and `UNIQUE(request_id)` back the no-double-charge / result-once rules. |
| **`VideoJob` cost fields** | Canonical `cost_budget_usd` + `cost_accrued_usd` (§1). §3's `total_cost_usd` maps to `cost_accrued_usd`. |
| **Job cost budget env** | `PER_VIDEO_COST_BUDGET_USD` (default 5.00) seeds `VideoJob.cost_budget_usd`. |
| **Templates** | `FormulaTemplate` / `HookTemplate` / `PacingTemplate` keep §1's `win_score` and add §2's `proxy_score`, `operator_win_score`, `signal_type` (honesty contract: proxy ≠ real sales). |

### Canonical entities (18)

`Product`, `VideoJob`, `Script`, `Scene`, `MediaAsset`, `Avatar`, `VoiceProfile`,
`FormulaTemplate`, `HookTemplate`, `PacingTemplate`, `Post`, `PerformanceRecord`,
`ComplianceRecord`, `ConsentRecord`, `CostLedgerEntry`, `GenAttempt`, `SwipeSource`,
`SwipeVideo`.

Defined in `app/core/models.py`. Every table has `id` (UUID PK), `created_at`,
`updated_at`. Field names above are verbatim — use them exactly.

---

## 2. Job state machine (`app/core/state_machine.py`)

`JobState` values (verbatim):

```
QUEUED · RESEARCHING · SCRIPTING · GENERATING · EDITING · CAPTIONING ·
AWAITING_APPROVAL · POSTING · POSTED · FAILED · REJECTED · CANCELLED
```

Allowed transitions:

| From | To |
|---|---|
| `QUEUED` | `RESEARCHING`, `CANCELLED` |
| `RESEARCHING` | `SCRIPTING`, `FAILED` |
| `SCRIPTING` | `GENERATING`, `FAILED` |
| `GENERATING` | `EDITING`, `FAILED` |
| `EDITING` | `CAPTIONING`, `FAILED` |
| `CAPTIONING` | `AWAITING_APPROVAL`, `FAILED` |
| `AWAITING_APPROVAL` | `POSTING`, `EDITING`, `REJECTED`, `CANCELLED` — **human-only** |
| `POSTING` | `POSTED`, `FAILED` |
| `FAILED` | `QUEUED` (manual retry, resumes from `last_completed_stage`) |
| `POSTED` / `REJECTED` / `CANCELLED` | terminal |

**Rules for modules:**
- Change state **only** via `transition(job, new_state)`. Never assign `job.state`.
- Illegal edges raise `IllegalTransitionError`.
- `AWAITING_APPROVAL` is a **durable pause** — it holds no worker/connection. The only
  way out is a human decision: call `transition(job, target, by_human=True)`. A worker
  calling without `by_human=True` will (correctly) raise.
- On stage success, set `job.last_completed_stage` so a retry can resume cheaply.

---

## 3. Adapter interfaces (`app/core/adapters/base.py`)

Every external call goes through a Protocol; the **only** place vendor SDKs are imported.
All billable methods take an `idempotency_key` and return a `ProviderResult`.

```python
@dataclass
class ProviderResult:
    ok: bool
    data: dict
    cost_usd: float
    usage: dict                 # tokens / seconds / credits
    provider_job_id: str | None = None   # set for async submit
    error: str | None = None
```

Interfaces (signatures verbatim):

```python
LLMProvider.complete(*, prompt, system, model, max_tokens, idempotency_key) -> ProviderResult
ScraperProvider.scrape_product(*, url, idempotency_key) -> ProviderResult
ScraperProvider.mine_top_videos(*, query, market, limit, idempotency_key) -> ProviderResult
TTSProvider.synthesize(*, text, voice_id, language, model, idempotency_key) -> ProviderResult
AvatarProvider.submit_talking_head(*, avatar_id, audio_key, script_text, aspect, idempotency_key) -> ProviderResult
AvatarProvider.poll(*, provider_job_id) -> ProviderResult
VideoGenProvider.generate_hero_image(*, prompt, refs, idempotency_key) -> ProviderResult
VideoGenProvider.submit_image_to_video(*, image_key, prompt, model, seconds, aspect, idempotency_key) -> ProviderResult
VideoGenProvider.poll(*, provider_job_id) -> ProviderResult
PostingProvider.publish(*, video_key, caption, platform, ai_disclosure, schedule_at, idempotency_key) -> ProviderResult
PostingProvider.fetch_metrics(*, external_post_id) -> ProviderResult
```

**Selection (`app/core/adapters/registry.py`):**
- Call `registry.get_<capability>_provider()` — never construct providers directly.
- `DRY_RUN=true` → deterministic **Fake** (`fakes.py`), $0, no network. This is how the
  pipeline runs for free in CI and rehearsal.
- `DRY_RUN=false` → the real provider registered for the configured `*_PROVIDER` env var.
  Register a real vendor adapter with:
  `registry.register_real("videogen", "fal", FalVideoGenProvider)`.
- **Idempotency key** convention: `f"{job_id}:{stage}:{asset_role}:{attempt_input_hash}"`
  (generation uses `f"{video_job_id}:{scene_id}:{kind}:{attempt}"`).
- Persist `provider_job_id` on the `MediaAsset`/`GenAttempt` **before** polling, so a
  worker crash re-attaches via `poll()` instead of resubmitting (no double-billing).
- Write a `CostLedgerEntry` for every billable call in the **same transaction** that
  bumps `VideoJob.cost_accrued_usd`. Check the budget guard before spending.

---

## 4. Module convention (`app/modules/README.md`)

A module = a package `app/modules/<name>/` with:
- `router.py` exposing `router: APIRouter` (auto-mounted by `app.main.load_modules()`),
- `tasks.py` with Celery tasks (auto-discovered by `app.core.queue`),
- optional `requirements.txt` fragment (concatenated + installed by the Dockerfile),
- `__init__.py`.

Rules: import only from `app.core.*`; never edit core/main; all external calls via the
registry; drive state only via `transition()`; unique router `prefix`; namespaced task
`name=`. The core jobs router enqueues these task names as the pipeline advances —
own the matching one:

| Stage | Task name |
|---|---|
| research | `research.run` |
| generation | `generation.run` |
| editing | `editing.run` |
| posting | `posting.run` |

See `app/modules/_example/` for a working stub.

---

## 5. REST / WebSocket API contract (§7A.10)

Base: `http://localhost:8000/api`. JSON throughout. Optional `X-App-Password` header
when `APP_PASSWORD` is set. `Idempotency-Key` accepted on mutating job endpoints.

**Core jobs (skeleton implemented in `app/main.py`; stages fill behavior):**

| Method | Path | Purpose | Response |
|---|---|---|---|
| `POST` | `/api/jobs` | Create job `{product_url, seed_set?, avatar_id?, duration_s?}` | `201 {job_id, state:"QUEUED"}` |
| `GET` | `/api/jobs` | List (dashboard) `?state=&limit=&cursor=` | `{jobs:[JobSummary], cursor}` |
| `GET` | `/api/jobs/{id}` | Full job incl. script, flagged_claims, compliance | `Job` |
| `PATCH` | `/api/jobs/{id}/caption` | Save caption/hashtags | `{ok}` |
| `POST` | `/api/jobs/{id}/approve` | Gate → `POSTING`. **409 if compliance not all-green.** | `{state:"POSTING"}` |
| `POST` | `/api/jobs/{id}/reroll` | `{stage:"script\|voice\|broll\|recut", note?}` → `EDITING` | `{state, from_stage}` |
| `POST` | `/api/jobs/{id}/reject` | Terminal reject | `{state:"REJECTED"}` |
| `POST` | `/api/jobs/{id}/tagged` | Mark TikTok-Shop product tag done | `{tagged:true}` |
| `POST` | `/api/jobs/{id}/retry` | Re-run a `FAILED` job from last good stage | `{state}` |

> The foundation ships `POST /api/jobs`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/approve`,
> `POST /api/jobs/{id}/reroll`. The remaining job endpoints and all Setup / Library /
> Analytics / Settings endpoints (§7A.10) are owned by their respective modules and mount
> under their own router prefixes.

**Setup** (`/api/setup/*`), **Library** (`/api/library/*`), **Analytics**
(`/api/analytics/*`), **Settings** (`/api/settings/*`) — full table in spec §7A.10; owned
by the frontend/setup, research, and posting/winner-loop modules.

`Job` payload shape (see `app/core/schemas.py`):
`id, state, product, progress, cost, created_at, video_url, script, flagged_claims[],
compliance:{items:[{id,label,pass,reason}], all_green:bool}, caption, hashtags[],
post:{tiktok_url, deep_link, tagged}`.

**WebSocket `/ws/jobs`** (owned by the frontend/orchestration module; event envelopes
are pre-defined in `app/core/schemas.py`). Client → server:
`{op:"subscribe", job_ids:[…]}` / `{op:"subscribe_all"}`. Server → client events (all
carry `job_id`, `ts`):

```jsonc
{ "type":"state",    "state":"GENERATING", "prev":"SCRIPTING" }
{ "type":"progress", "stage":"generating", "pct":52, "cost":1.40 }
{ "type":"artifact", "kind":"script|first_frame|hook|product_facts", "ref":"…" }
{ "type":"awaiting_approval" }
{ "type":"cost",     "job":2.90, "day":18.40, "guard":"OK|WARN|STOP" }
{ "type":"error",    "stage":"mining", "message":"scrape 404", "retryable":true }
{ "type":"posted",   "tiktok_url":"…", "deep_link":"…" }
```

**Compliance is a hard gate:** `POST /api/jobs/{id}/approve` must be **409** unless the
compliance checklist is all-green (no override in v1). The compliance module enforces the
checklist; the foundation enforces the state-machine legality of the transition.
