#!/usr/bin/env bash
#
# AutoUGC-TH — one-command macOS installer.
#
#   curl -fsSL .../install-mac.sh | bash      # or, from a clone:
#   bash scripts/install-mac.sh
#
# What it does (idempotent — safe to re-run):
#   1. Verifies macOS + installs Homebrew if missing
#   2. Installs Docker Desktop (via Homebrew cask) and waits for the engine
#   3. Creates .env from .env.example (keeps DRY_RUN=true → first run is FREE)
#   4. Builds + starts the full stack (api, worker, postgres, redis, minio, frontend)
#   5. Applies DB migrations, health-checks the API, opens the app in your browser
#
# It never asks for an API key — the app boots in DRY_RUN ($0, no network) and you
# add real keys later with `make keys` or the in-app Setup Wizard.

set -euo pipefail

# --------------------------------------------------------------------------- #
# Pretty output
# --------------------------------------------------------------------------- #
if [[ -t 1 ]]; then
  BOLD=$(printf '\033[1m'); DIM=$(printf '\033[2m'); RED=$(printf '\033[31m')
  GRN=$(printf '\033[32m'); YLW=$(printf '\033[33m'); BLU=$(printf '\033[34m')
  RST=$(printf '\033[0m')
else
  BOLD=""; DIM=""; RED=""; GRN=""; YLW=""; BLU=""; RST=""
fi
step()  { printf '\n%s==>%s %s%s\n' "$BLU$BOLD" "$RST$BOLD" "$*" "$RST"; }
ok()    { printf '  %s✓%s %s\n' "$GRN" "$RST" "$*"; }
info()  { printf '  %s•%s %s\n' "$DIM" "$RST" "$*"; }
warn()  { printf '  %s!%s %s\n' "$YLW" "$RST" "$*"; }
die()   { printf '\n%serror:%s %s\n' "$RED$BOLD" "$RST" "$*" >&2; exit 1; }

# Resolve repo root (the parent of this script's dir), so the script works from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

API_URL="http://localhost:8000"
APP_URL="http://localhost:3000"

printf '%s\n' "${BOLD}AutoUGC-TH — macOS installer${RST}"
printf '%s\n' "${DIM}Repo: $REPO_ROOT${RST}"

# --------------------------------------------------------------------------- #
# 1. macOS + Homebrew
# --------------------------------------------------------------------------- #
step "Checking macOS and Homebrew"
[[ "$(uname -s)" == "Darwin" ]] || die "This installer is for macOS. On Linux, use: docker compose up -d --build"

if command -v brew >/dev/null 2>&1; then
  ok "Homebrew present ($(brew --version | head -1))"
else
  warn "Homebrew not found — installing (you may be prompted for your password)…"
  NONINTERACTIVE=1 /bin/bash -c \
    "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  ok "Homebrew installed"
fi

# Make brew available in this shell (Apple Silicon vs Intel prefixes).
if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [[ -x /usr/local/bin/brew ]]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi
command -v brew >/dev/null 2>&1 || die "Homebrew installed but not on PATH. Open a new terminal and re-run."

# --------------------------------------------------------------------------- #
# 2. Container engine
#    Docker Desktop needs macOS 13+. Older Macs (e.g. a 2015 model, which tops out
#    at macOS 12 Monterey) get Colima — a lightweight Docker-compatible engine that
#    runs well on older Intel hardware. If an engine is already running, we use it.
# --------------------------------------------------------------------------- #
step "Checking the container engine"

_wait_for_engine() {
  printf '  %swaiting for the container engine%s' "$DIM" "$RST"
  for _ in $(seq 1 90); do
    if docker info >/dev/null 2>&1; then printf '\n'; return 0; fi
    printf '.'; sleep 2
  done
  printf '\n'; return 1
}

if docker info >/dev/null 2>&1; then
  ok "A container engine is already running"
else
  macos_major="$(sw_vers -productVersion 2>/dev/null | cut -d. -f1)"; macos_major="${macos_major:-0}"

  if command -v colima >/dev/null 2>&1; then
    info "Starting Colima…"
    colima start --cpu 2 --memory 4 --disk 30 || warn "colima start reported an issue; continuing to health check…"
  elif [[ "$macos_major" -ge 13 ]]; then
    info "macOS $macos_major → using Docker Desktop"
    command -v docker >/dev/null 2>&1 || brew install --cask docker \
      || die "Docker Desktop install failed. Install it manually from docker.com."
    open -a Docker || warn "Could not auto-open Docker Desktop — launch it from Applications."
  else
    warn "macOS $macos_major detected — Docker Desktop needs macOS 13+. Using Colima (lightweight engine)."
    brew install colima docker docker-compose \
      || die "Colima install failed. See ONBOARDING.md → 'Older Macs'."
    # Make 'docker compose' (v2 plugin) available for the brew docker-compose binary.
    mkdir -p "$HOME/.docker/cli-plugins"
    ln -sfn "$(brew --prefix)/bin/docker-compose" "$HOME/.docker/cli-plugins/docker-compose" 2>/dev/null || true
    info "Starting Colima (first boot downloads a small Linux VM)…"
    colima start --cpu 2 --memory 4 --disk 30 || die "colima start failed. Try: colima start --cpu 2 --memory 4"
  fi

  _wait_for_engine || die "Container engine did not come up. If on an old Mac, run 'colima start' manually, then re-run."
fi
ok "Container engine running ($(docker --version 2>/dev/null))"

docker compose version >/dev/null 2>&1 || die "Docker Compose v2 not available. See ONBOARDING.md → 'Older Macs'."
ok "Docker Compose available"

# --------------------------------------------------------------------------- #
# 3. Environment file
# --------------------------------------------------------------------------- #
step "Configuring environment"
if [[ -f .env ]]; then
  ok ".env already exists (left untouched)"
else
  cp .env.example .env
  ok "Created .env from .env.example"
  info "DRY_RUN=true → the app runs FREE with no API keys. Add keys later with 'make keys'."
fi

# --------------------------------------------------------------------------- #
# 4. Build + start
# --------------------------------------------------------------------------- #
step "Building and starting the stack (first build downloads images — a few minutes)"
docker compose up -d --build
ok "Containers started"

# --------------------------------------------------------------------------- #
# 5. Migrate + health-check
# --------------------------------------------------------------------------- #
step "Applying database migrations"
if docker compose run --rm api alembic upgrade head >/dev/null 2>&1; then
  ok "Migrations applied"
else
  warn "Migrations skipped/failed (fine on a fresh P0 scaffold — tables are created on boot)."
fi

step "Waiting for the API to become healthy"
printf '  %spinging %s/health%s' "$DIM" "$API_URL" "$RST"
healthy=""
for _ in $(seq 1 60); do
  if curl -fsS "$API_URL/health" >/dev/null 2>&1; then healthy="yes"; break; fi
  printf '.'; sleep 2
done
printf '\n'
if [[ -n "$healthy" ]]; then
  ok "API healthy at $API_URL"
else
  warn "API not healthy yet. Check logs with: make logs"
fi

# --------------------------------------------------------------------------- #
# Done
# --------------------------------------------------------------------------- #
step "Done"
ok "Opening the app…"
open "$APP_URL" 2>/dev/null || true

cat <<EOF

${BOLD}AutoUGC-TH is running.${RST}

  App (UI)      ${BLU}$APP_URL${RST}       ← finish setup in the in-app wizard
  API docs      ${BLU}$API_URL/docs${RST}
  Health        ${BLU}$API_URL/health${RST}

${BOLD}Next steps${RST}
  ${DIM}# It's running in DRY_RUN now — the whole pipeline works for \$0, no keys needed.${RST}
  make keys      ${DIM}# add real provider API keys and switch off DRY_RUN when ready to spend${RST}
  make doctor    ${DIM}# re-check everything is healthy${RST}
  make logs      ${DIM}# watch what it's doing${RST}
  make stop      ${DIM}# stop it (your data + jobs are preserved)${RST}

EOF
