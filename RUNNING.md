# Running AutoUGC-TH

A locally-run, single-operator content factory: one product URL → a post-ready,
TikTok-Shop-compliant Thai short video, with exactly one human approval gate.
Everything runs on your machine via Docker Compose; the only outbound traffic is to the
third-party AI/posting APIs you configure (and **none** in `DRY_RUN` mode).

> **On a Mac?** For a guided, one-command install see **[ONBOARDING.md](ONBOARDING.md)**
> (`make install` handles Homebrew, Docker, `.env`, build, and start for you). The rest
> of this file is the platform-agnostic reference.

## Prerequisites

- Docker + Docker Compose
- (For local dev without Docker) Python 3.11+

## First run

```bash
cp .env.example .env        # then fill in API keys + avatar/voice IDs
docker compose up -d --build   # or: make up
```

Mac users can skip the manual steps above and run `make install` (see ONBOARDING.md).

Services and ports:

| Service   | URL / port                       | Purpose                                   |
|-----------|----------------------------------|-------------------------------------------|
| frontend  | http://localhost:3000            | Operator UI (placeholder until SPA ships) |
| api       | http://localhost:8000            | REST + WebSocket; OpenAPI docs at `/docs` |
| postgres  | localhost:5432                   | Canonical state (debug only)              |
| redis     | localhost:6379                   | Celery broker + result backend            |
| minio     | http://localhost:9000 (API)      | Media storage                             |
| minio UI  | http://localhost:9001            | Bucket inspection console                 |

Check readiness: http://localhost:8000/health — reports DRY_RUN, DB status, provider
mode (fake/real), and which modules mounted.

## Bootstrap (idempotent, on first start)

The intended first-run bootstrap (owned partly by later modules) is:

1. `alembic upgrade head` — apply DB migrations. Run manually with `make migrate`
   (i.e. `docker compose run --rm api alembic upgrade head`).
2. Ensure the MinIO media bucket exists.
3. Seed the singleton `Avatar` + `VoiceProfile` rows from `HEYGEN_AVATAR_ID` /
   `ELEVENLABS_VOICE_ID`.
4. Prompt (once, in the UI) to upload the signed **consent document** → `ConsentRecord`;
   generation is blocked until present.
5. Health-check every configured provider.

> This P0 foundation ships steps that don't need business-logic modules (migrations,
> health, schema). Steps 2–4 are wired by the setup/generation/compliance modules.

Then open http://localhost:3000 and paste a product URL.

## DRY_RUN — the $0 rehearsal

`DRY_RUN=true` (the default in `.env.example`) routes **every** provider through a
deterministic Fake: no network, no spend, stable outputs. Use it to exercise the whole
pipeline for free and in CI. Set `DRY_RUN=false` only once real provider adapters are
registered and you intend to spend.

The per-video spend ceiling is `PER_VIDEO_COST_BUDGET_USD` (default `5.00`, target ~$3);
a projected breach fails the job with `failure_reason=budget_exceeded` rather than
overspending.

## Local dev without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# DATABASE_URL empty in .env => SQLite fallback (autougc_local.sqlite3)
DRY_RUN=true uvicorn app.main:app --reload
```

## Make targets

```bash
make up        # build + start the full stack
make down      # stop (volumes preserved)
make migrate   # alembic upgrade head (in the api container)
make test      # pytest in the api container
make dryrun    # pytest locally, DRY_RUN=true, $0
make logs      # tail service logs
```

## Persistence

`docker compose down && up` preserves the DB (`pgdata`), media (`mediadata`),
avatar/voice identities, and all historical jobs/posts. `docker compose down -v` wipes
volumes — only do that to reset.

## For module developers

See `app/modules/README.md` for the plug-in convention and `docs/CONTRACTS.md` for the
authoritative entity/field names, state machine, adapter interfaces, and API contract.
