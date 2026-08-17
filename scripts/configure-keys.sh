#!/usr/bin/env bash
#
# AutoUGC-TH — interactive provider-key setup.
#   bash scripts/configure-keys.sh   (or: make keys)
#
# Fills the provider API keys in .env and optionally switches OFF DRY_RUN so the
# app makes real (billed) calls. Input is hidden; blank input keeps the current
# value. Nothing is printed to the screen or logs. Requires python3 (ships with macOS).

set -euo pipefail

if [[ -t 1 ]]; then
  BOLD=$(printf '\033[1m'); DIM=$(printf '\033[2m'); GRN=$(printf '\033[32m')
  YLW=$(printf '\033[33m'); BLU=$(printf '\033[34m'); RST=$(printf '\033[0m')
else BOLD=""; DIM=""; GRN=""; YLW=""; BLU=""; RST=""; fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
ENV_FILE="$REPO_ROOT/.env"

command -v python3 >/dev/null 2>&1 || { echo "python3 is required (ships with macOS)."; exit 1; }
[[ -f "$ENV_FILE" ]] || cp .env.example .env

# set_key KEY VALUE — upsert KEY=VALUE in .env without touching other lines.
# Value passed via env var so any characters (/, +, =) are handled safely.
set_key() {
  KEY="$1" VALUE="$2" python3 - "$ENV_FILE" <<'PY'
import os, sys
path = sys.argv[1]
key, value = os.environ["KEY"], os.environ["VALUE"]
lines = open(path, encoding="utf-8").read().splitlines()
out, found = [], False
for line in lines:
    if line.startswith(key + "="):
        out.append(f"{key}={value}"); found = True
    else:
        out.append(line)
if not found:
    out.append(f"{key}={value}")
open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
PY
}

get_key() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- ; }
mask()    { local v="$1"; [[ -z "$v" ]] && { echo "${DIM}(empty)${RST}"; return; }
           printf '%s…%s (set)' "${v:0:3}" "$GRN$RST"; }

printf '%sAutoUGC-TH — provider keys%s\n' "$BOLD" "$RST"
printf '%sEnter a key to set it, or press Enter to keep the current value. Input is hidden.%s\n' "$DIM" "$RST"

# key label|where-to-get  (the single approved stack; the in-app wizard does this too)
PROVIDERS=(
  "ANTHROPIC_API_KEY|LLM (research, scripts, claim gate)|console.anthropic.com"
  "GOOGLE_TTS_API_KEY|Thai voiceover (Google Cloud TTS, free tier)|console.cloud.google.com → Text-to-Speech"
  "MODAL_LTX_URL|Video (LTX-2.5 on Modal — URL from 'modal deploy')|deploy/modal_ltx.py"
  "MODAL_LTX_TOKEN|Shared secret for the Modal endpoint|matches AUTOUGC_LTX_TOKEN"
  "TIKTOK_ACCESS_TOKEN|Auto-posting to TikTok (Content Posting API)|developers.tiktok.com"
  "FIRECRAWL_API_KEY|Product/market page scraping|firecrawl.dev"
)

for entry in "${PROVIDERS[@]}"; do
  IFS='|' read -r key label where <<<"$entry"
  cur="$(get_key "$key")"
  printf '\n%s%s%s  %s%s%s\n' "$BOLD" "$key" "$RST" "$DIM" "$label" "$RST"
  printf '  current: %s   %sget it: %s%s\n' "$(mask "$cur")" "$DIM" "$where" "$RST"
  printf '  new value: '
  read -rs newval || true
  printf '\n'
  if [[ -n "$newval" ]]; then set_key "$key" "$newval"; printf '  %s✓ saved%s\n' "$GRN" "$RST"; fi
done

# Reused-forever identities (created once via the in-app Setup Wizard; can be pasted here too).
printf '\n%sReused identities%s %s(optional — usually set by the in-app Setup Wizard)%s\n' "$BOLD" "$RST" "$DIM" "$RST"
for key in HEYGEN_AVATAR_ID ELEVENLABS_VOICE_ID; do
  cur="$(get_key "$key")"
  printf '  %s%s%s current: %s\n' "$BOLD" "$key" "$RST" "$(mask "$cur")"
  printf '    new value (Enter to skip): '
  read -r newval || true
  [[ -n "$newval" ]] && { set_key "$key" "$newval"; printf '    %s✓ saved%s\n' "$GRN" "$RST"; }
done

# DRY_RUN toggle
cur_dry="$(get_key DRY_RUN)"
printf '\n%sRun mode%s\n' "$BOLD" "$RST"
printf '  DRY_RUN is currently %s%s%s ' "$YLW" "$cur_dry" "$RST"
if [[ "${cur_dry,,}" == "true" ]]; then
  printf '(FREE fake mode — no real videos, no charges)\n'
  printf '  Switch to LIVE mode now? Real providers WILL be billed. [y/N] '
  read -r ans || true
  if [[ "${ans,,}" == "y" || "${ans,,}" == "yes" ]]; then
    set_key DRY_RUN false
    printf '  %s✓ DRY_RUN=false — live mode%s\n' "$GRN" "$RST"
  else
    printf '  %skept DRY_RUN=true (free mode)%s\n' "$DIM" "$RST"
  fi
else
  printf '(LIVE — real providers billed). Set back to free mode? [y/N] '
  read -r ans || true
  [[ "${ans,,}" == "y" || "${ans,,}" == "yes" ]] && { set_key DRY_RUN true; printf '  %s✓ DRY_RUN=true (free)%s\n' "$GRN" "$RST"; }
fi

printf '\n%sSaved to .env.%s Apply changes with: %smake restart%s\n' "$GRN" "$RST" "$BLU" "$RST"
printf '%sTip: run %smake doctor%s to verify keys and health.%s\n' "$DIM" "$RST$DIM" "$DIM" "$RST"
