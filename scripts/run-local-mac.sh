#!/usr/bin/env bash
# Run AutoUGC-TH locally on a Mac WITHOUT Docker — ideal for an older Intel Mac
# (macOS Monterey and up) where Docker Desktop / Colima won't install cleanly.
#
# It installs the only three system pieces (Python 3.11, Redis, ffmpeg) via
# Homebrew, creates a virtualenv, writes a starter .env (SQLite fallback, DRY_RUN
# on so nothing spends), and launches the web app + the Celery worker together.
#
#   bash scripts/run-local-mac.sh
#
# Ctrl-C stops both processes. Re-run any time; it reuses what's already set up.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!! \033[0m %s\n' "$*"; }

# --- 1. Homebrew --------------------------------------------------------------
if ! command -v brew >/dev/null 2>&1; then
  warn "Homebrew not found. Install it first from https://brew.sh, then re-run."
  exit 1
fi

# --- 2. System deps (idempotent) ---------------------------------------------
# Detect tools that already exist (any install, not just brew) so we never
# rebuild them. On old macOS, brew compiles from source (slow / can fail), so we
# fetch a PREBUILT ffmpeg instead of building it.
say "Checking Python 3.11, ffmpeg (Redis is optional)..."
command -v python3.11   >/dev/null 2>&1 || brew install python@3.11
# Redis is OPTIONAL and we never try to install it (Homebrew rate-limits/hangs on
# old macOS). If it's already present we use it; otherwise the built-in file queue.
command -v redis-server >/dev/null 2>&1 \
  || warn "No Redis installed — using the built-in file queue (nothing to install)."

if ! command -v ffmpeg >/dev/null 2>&1; then
  say "Installing a prebuilt ffmpeg (no compiling)..."
  ok=0
  for tool in ffmpeg ffprobe; do
    if curl -fsSL "https://evermeet.cx/ffmpeg/getrelease/$tool/zip" -o "/tmp/$tool.zip" \
       && unzip -o -q "/tmp/$tool.zip" -d /tmp; then
      sudo mv "/tmp/$tool" /usr/local/bin/ && sudo chmod +x "/usr/local/bin/$tool" && ok=1
    fi
  done
  if [ "$ok" != "1" ]; then
    warn "prebuilt ffmpeg download failed — falling back to Homebrew (slow, may take 20-40 min)"
    brew install ffmpeg
  fi
fi

PYBIN="$(command -v python3.11 || echo python3.11)"

# --- 3. Redis (optional) — else use the built-in file queue -------------------
REDIS_OK=0
if command -v redis-server >/dev/null 2>&1; then
  if ! redis-cli ping >/dev/null 2>&1; then
    say "Starting Redis..."
    brew services start redis >/dev/null 2>&1 || redis-server --daemonize yes >/dev/null 2>&1 || true
    sleep 1
  fi
  redis-cli ping >/dev/null 2>&1 && REDIS_OK=1
fi
[ "$REDIS_OK" = 1 ] && say "Redis is up." || say "No Redis — using the built-in file queue (zero setup)."

# --- 4. Virtualenv + deps -----------------------------------------------------
if [ ! -d .venv ]; then
  say "Creating virtualenv (.venv)..."
  "$PYBIN" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
say "Installing Python dependencies (progress shown; --prefer-binary avoids slow source builds)..."
python -m pip install --upgrade pip
python -m pip install --prefer-binary -r requirements.txt

# --- 5. .env + broker selection ----------------------------------------------
FRESH_ENV=0
if [ ! -f .env ]; then cp .env.example .env; FRESH_ENV=1; fi

# Replace an existing KEY= line (or append) — keeps re-runs idempotent.
set_env() {
  local k="$1" v="$2"
  grep -vE "^${k}=" .env > .env.tmp 2>/dev/null || true
  mv .env.tmp .env
  printf '%s=%s\n' "$k" "$v" >> .env
}

set_env DATABASE_URL ""                    # empty => local SQLite
set_env MEDIA_ROOT "$ROOT/.media"
if [ "$REDIS_OK" = 1 ]; then
  set_env CELERY_BROKER_URL "redis://localhost:6379/0"
  set_env CELERY_RESULT_BACKEND "redis://localhost:6379/1"
else
  set_env CELERY_BROKER_URL "filesystem://"
  set_env CELERY_RESULT_BACKEND "db+sqlite:///./celery_results.sqlite3"
  set_env CELERY_BROKER_DIR "$ROOT/.broker"
fi
[ "$FRESH_ENV" = 1 ] && set_env DRY_RUN "true"   # first run: safe fake mode
mkdir -p "$ROOT/.media" "$ROOT/.broker/queue" "$ROOT/.broker/processed"

# --- 6. Migrate the DB --------------------------------------------------------
say "Applying database migrations..."
alembic upgrade head >/dev/null 2>&1 || warn "alembic upgrade skipped/failed (ok on first SQLite run if tables auto-create)."

# --- 7. Launch web + worker ---------------------------------------------------
say "Starting the app. Web UI at http://localhost:8000  (Ctrl-C to stop both)."
cleanup() { kill "${WORKER_PID:-}" "${WEB_PID:-}" >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM

celery -A app.core.queue worker --loglevel=info &
WORKER_PID=$!
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
WEB_PID=$!
wait $WEB_PID
