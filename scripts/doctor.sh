#!/usr/bin/env bash
#
# AutoUGC-TH — preflight & health doctor.
#   bash scripts/doctor.sh   (or: make doctor)
#
# Read-only. Prints a ✓/✗ status line for every prerequisite and running service,
# then a bottom-line verdict. Never changes anything.

set -uo pipefail

if [[ -t 1 ]]; then
  BOLD=$(printf '\033[1m'); DIM=$(printf '\033[2m'); RED=$(printf '\033[31m')
  GRN=$(printf '\033[32m'); YLW=$(printf '\033[33m'); RST=$(printf '\033[0m')
else
  BOLD=""; DIM=""; RED=""; GRN=""; YLW=""; RST=""
fi

PASS=0; FAIL=0; WARN=0
pass() { printf '  %s✓%s %s\n' "$GRN" "$RST" "$*"; PASS=$((PASS+1)); }
fail() { printf '  %s✗%s %s\n' "$RED" "$RST" "$*"; FAIL=$((FAIL+1)); }
warn() { printf '  %s!%s %s\n' "$YLW" "$RST" "$*"; WARN=$((WARN+1)); }
head() { printf '\n%s%s%s\n' "$BOLD" "$*" "$RST"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

printf '%sAutoUGC-TH doctor%s  %s(%s)%s\n' "$BOLD" "$RST" "$DIM" "$REPO_ROOT" "$RST"

head "System"
if [[ "$(uname -s)" == "Darwin" ]]; then pass "macOS ($(sw_vers -productVersion 2>/dev/null || echo '?'))"
else warn "Not macOS — this doctor targets Mac (the stack still runs on Linux via docker compose)"; fi
command -v brew >/dev/null 2>&1 && pass "Homebrew" || warn "Homebrew not installed"

head "Docker"
if command -v docker >/dev/null 2>&1; then pass "docker CLI ($(docker --version 2>/dev/null))"
else fail "docker CLI not found — run: bash scripts/install-mac.sh"; fi
if docker info >/dev/null 2>&1; then pass "Docker engine running"
else fail "Docker engine not running — open Docker Desktop"; fi
docker compose version >/dev/null 2>&1 && pass "Docker Compose v2" || fail "Docker Compose v2 missing"

head "Configuration"
if [[ -f .env ]]; then
  pass ".env present"
  dry=$(grep -E '^DRY_RUN=' .env | tail -1 | cut -d= -f2)
  if [[ -z "$dry" || "${dry,,}" == "true" ]]; then
    warn "DRY_RUN=${dry:-unset(defaults true)} → FREE fake mode (no real videos). Run 'make keys' to go live."
  else
    pass "DRY_RUN=false → live mode (real providers will be billed)"
    for k in ANTHROPIC_API_KEY FAL_API_KEY ELEVENLABS_API_KEY HEYGEN_API_KEY APIFY_API_KEY POSTPEER_API_KEY; do
      v=$(grep -E "^$k=" .env | tail -1 | cut -d= -f2-)
      [[ -n "$v" ]] && pass "$k set" || warn "$k empty (that provider will fail in live mode)"
    done
  fi
else
  fail ".env missing — run: cp .env.example .env  (or bash scripts/install-mac.sh)"
fi

head "Ports (should be free before first start, or owned by our containers)"
for p in 3000 8000 5432 6379 9000; do
  if lsof -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then info_owner=$(lsof -nP -iTCP:"$p" -sTCP:LISTEN 2>/dev/null | awk 'NR==2{print $1}')
    warn "port $p in use (${info_owner:-unknown}) — ours if the stack is up, else a conflict"
  else pass "port $p free"; fi
done

head "Running services"
if docker compose ps >/dev/null 2>&1; then
  running=$(docker compose ps --services --filter status=running 2>/dev/null | tr '\n' ' ')
  if [[ -n "${running// }" ]]; then pass "up: $running"
  else warn "no services running — start with: make start"; fi
else warn "compose project not started"; fi

if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
  pass "API /health OK"
  curl -fsS http://localhost:8000/health 2>/dev/null | sed 's/^/    /' || true
else
  warn "API /health not responding (not started, or still booting)"
fi

head "Summary"
printf '  %s%d passed%s   %s%d warnings%s   %s%d failed%s\n' \
  "$GRN" "$PASS" "$RST" "$YLW" "$WARN" "$RST" "$RED" "$FAIL" "$RST"
if [[ "$FAIL" -gt 0 ]]; then
  printf '  %s→ Fix the ✗ items, then re-run: bash scripts/install-mac.sh%s\n' "$DIM" "$RST"
  exit 1
fi
printf '  %s→ Looks good. Open http://localhost:3000%s\n' "$DIM" "$RST"
