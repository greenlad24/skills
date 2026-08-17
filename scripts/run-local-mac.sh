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
say "Checking Python 3.11, Redis, ffmpeg..."
command -v python3.11   >/dev/null 2>&1 || brew install python@3.11
command -v redis-server >/dev/null 2>&1 || brew install redis

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

# --- 3. Redis running ---------------------------------------------------------
if ! redis-cli ping >/dev/null 2>&1; then
  say "Starting Redis..."
  brew services start redis >/dev/null 2>&1 || (redis-server --daemonize yes >/dev/null 2>&1 || true)
  sleep 1
fi
redis-cli ping >/dev/null 2>&1 && say "Redis is up." || warn "Redis not responding; the worker may fail to start."

# --- 4. Virtualenv + deps -----------------------------------------------------
if [ ! -d .venv ]; then
  say "Creating virtualenv (.venv)..."
  "$PYBIN" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
say "Installing Python dependencies..."
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

# --- 5. Starter .env ----------------------------------------------------------
if [ ! -f .env ]; then
  say "Writing a starter .env (SQLite, DRY_RUN on, local Redis)..."
  cp .env.example .env
  # Point Celery/Redis at the local brew Redis and use the SQLite fallback.
  {
    echo ""
    echo "# --- local-mac overrides (written by scripts/run-local-mac.sh) ---"
    echo "DATABASE_URL="
    echo "REDIS_URL=redis://localhost:6379/0"
    echo "CELERY_BROKER_URL=redis://localhost:6379/0"
    echo "CELERY_RESULT_BACKEND=redis://localhost:6379/1"
    echo "MEDIA_ROOT=$ROOT/.media"
    echo "DRY_RUN=true"
  } >> .env
  mkdir -p "$ROOT/.media"
  warn "Starter .env created with DRY_RUN=true (no spend). Edit it to add keys and"
  warn "set VIDEOGEN_PROVIDER=ltx_modal, TTS_PROVIDER=google_tts, POSTING_PROVIDER=tiktok, DRY_RUN=false when ready."
fi

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
