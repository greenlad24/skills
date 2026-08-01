# Installing AutoUGC-TH on a Mac

This gets AutoUGC-TH running on your Mac. The first run works **for free** — the app
starts in **DRY_RUN** mode (every AI provider is a deterministic fake, no network, no
charges), so you can click through the whole pipeline before adding a single API key.

---

## The one-command install

Open **Terminal**, `cd` into this project folder, and run:

```bash
bash scripts/install-mac.sh
```

> **Why not `make install`?** A brand-new Mac doesn't have `make` yet — it comes with
> Apple's Command Line Tools. Running the script directly needs nothing pre-installed.
> The script installs Homebrew (which pulls in the Command Line Tools), so **after this
> first run the `make …` shortcuts below all work** (`make start`, `make keys`, etc.).

This script is **idempotent** (safe to run again) and does:

1. Installs **Homebrew** if you don't have it.
2. Installs **Docker Desktop** and waits for the engine to start.
3. Creates your **`.env`** from `.env.example` (keeps `DRY_RUN=true` → free).
4. **Builds and starts** the whole stack (api, worker, Postgres, Redis, MinIO, web UI).
5. Runs DB migrations, **health-checks** the API, and opens the app in your browser.

First build downloads container images and takes a few minutes. When it's done it opens:

| What | URL |
|---|---|
| **App (the UI you use)** | http://localhost:3000 |
| API docs (OpenAPI) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

> No Terminal? You can also run the script directly: `bash scripts/install-mac.sh`.

---

## What happens after install

The app is now running in **free mode**. Two things are left, both done *inside the app*:

1. Open **http://localhost:3000** and go through the **Setup Wizard** — it walks you
   through creating your reusable avatar + voice, signing the consent record, and
   connecting your TikTok account. (In DRY_RUN these use fakes so you can rehearse.)
2. When you're ready to make **real** videos, add your provider API keys (below).

---

## Going live — adding your API keys

Real videos need accounts with the AI providers. Add the keys interactively:

```bash
make keys
```

It prompts for each key (input hidden; press Enter to skip), then asks whether to switch
off DRY_RUN. Where to get each:

| Key | Used for | Get it at |
|---|---|---|
| `ANTHROPIC_API_KEY` | Script / hook / claim-safety (the "brain") | console.anthropic.com |
| `FAL_API_KEY` | Product b-roll video generation | fal.ai → dashboard → keys |
| `ELEVENLABS_API_KEY` | Thai voiceover | elevenlabs.io → Profile → API Keys |
| `HEYGEN_API_KEY` | Your avatar (digital twin) | app.heygen.com → Settings → API |
| `APIFY_API_KEY` | TikTok / product scraping | console.apify.com → Integrations |
| `POSTPEER_API_KEY` | Auto-posting to TikTok | postpeer.dev |
| `FIRECRAWL_API_KEY` | Generic product-page scraping (optional) | firecrawl.dev |

Then apply the changes:

```bash
make restart
```

> You don't need every key to start. The cheapest useful setup is `ANTHROPIC_API_KEY`
> + `FAL_API_KEY` + `ELEVENLABS_API_KEY`. Anything left blank simply means that provider
> isn't available yet — keep `DRY_RUN=true` until you've added the ones you want.

You can always edit `.env` by hand instead of `make keys`; it's the single source of
truth and is git-ignored (your keys never leave your machine).

---

## Everyday commands

```bash
make doctor    # check prerequisites + services are healthy (run this first if anything's off)
make start     # start it
make stop      # stop it — your data, jobs, avatar & posts are preserved
make restart   # apply .env changes
make status    # container status
make open      # open the app in your browser
make logs      # watch what it's doing
```

---

## Troubleshooting

Run **`make doctor`** first — it prints a ✓/✗ for every prerequisite, port, and service,
plus a bottom-line verdict.

| Symptom | Fix |
|---|---|
| "Docker engine did not start" | Open **Docker Desktop** from Applications, finish its first-run setup, then `make install` again. |
| `qemu-img not found` / `cannot use vmType: 'qemu'` (old/Intel Mac) | Colima needs QEMU: `brew install qemu`, then `colima start --cpu 2 --memory 4 --disk 30`. |
| Browser opens but the page is blank / "can't connect" | Give it ~30s (first boot), then refresh. Check `make logs`. |
| "port 3000 (or 8000/5432) in use" | Another app owns that port. Stop it, or stop this stack with `make stop` and retry. `make doctor` names the conflict. |
| App runs but makes fake videos | You're in DRY_RUN. Run `make keys`, add keys, choose live mode, `make restart`. |
| Want a clean slate | `docker compose down -v` wipes all data/volumes (irreversible), then `make install`. |

---

## Older Macs (e.g. a 2015 model)

Docker Desktop's current versions **require macOS 13+**, and a 2015 Mac tops out at
**macOS Monterey (12)** — so the latest Docker Desktop won't install. That's fine: the
installer automatically detects an older macOS and uses **Colima** instead — a
lightweight, Docker-compatible engine that runs well on older Intel hardware. You don't
have to do anything differently; `bash scripts/install-mac.sh` handles it.

If you ever want to run it by hand:

```bash
brew install colima docker docker-compose qemu   # qemu = the VM backend Colima needs on Intel Macs
colima start --cpu 2 --memory 4 --disk 30     # start the engine (once per login)
docker compose up -d --build                  # start the app
# ... later:
docker compose down                           # stop the app
colima stop                                    # stop the engine
```

**Performance:** everything works, just a little slower. The heavy AI generation runs in
the **cloud** (fal / HeyGen / ElevenLabs), so your Mac only orchestrates and does light
local video assembly — well within a 2015 Mac's reach. Give the engine ~4 GB RAM
(`--memory 4`); 8 GB+ total on the Mac is comfortable. The free **DRY_RUN** first run does
no real processing, so it's snappy.

## What's installed / where things live

- **Everything runs in Docker containers on your Mac** — nothing is installed system-wide
  except Homebrew and Docker Desktop.
- Your data (DB, media, avatar/voice identities, jobs, posts) lives in Docker **volumes**
  and survives `make stop` / `make restart`.
- Secrets live only in **`.env`** (git-ignored). In `DRY_RUN` there is **no outbound
  network traffic at all**; in live mode the only outbound calls are to the provider APIs
  whose keys you entered.

For architecture, the pipeline, and the full spec, see `RUNNING.md`, `spec/README.md`,
and `docs/CONTRACTS.md`.
