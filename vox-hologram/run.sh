#!/usr/bin/env bash
#
# VOX — launcher. Activates the venv, exports sensible VOX_* defaults, checks the
# local LLM server is reachable, starts the FastAPI app, and opens your browser.
#
# Anything you export yourself before running wins over these defaults, e.g.:
#   VOX_PORT=9000 VOX_LLM_MODEL=qwen2.5:3b ./run.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

CYAN=""; GREEN=""; YELLOW=""; BOLD=""; RESET=""
if [ -t 1 ]; then
  CYAN="$(printf '\033[36m')"; GREEN="$(printf '\033[32m')"
  YELLOW="$(printf '\033[33m')"; BOLD="$(printf '\033[1m')"; RESET="$(printf '\033[0m')"
fi

# --- Virtualenv -------------------------------------------------------------
if [ ! -f "$REPO_DIR/.venv/bin/activate" ]; then
  printf '%sNo virtualenv found. Run ./setup.sh first.%s\n' "$YELLOW" "$RESET" >&2
  exit 1
fi
# shellcheck disable=SC1091
. "$REPO_DIR/.venv/bin/activate"

# --- Runtime defaults saved by setup.sh (only sets VOX_* that are unset) -----
if [ -f "$REPO_DIR/.vox.env" ]; then
  # shellcheck disable=SC1091
  . "$REPO_DIR/.vox.env"
fi

# --- Export defaults for anything still unset -------------------------------
: "${VOX_PORT:=8008}"
: "${VOX_LLM_BASE_URL:=http://localhost:11434/v1}"   # Ollama; llama.cpp = :8080/v1
: "${VOX_LLM_MODEL:=llama3.2:3b}"
: "${VOX_LLM_API_KEY:=ollama}"
: "${VOX_PIPER_BIN:=piper}"
: "${VOX_PIPER_VOICE:=$REPO_DIR/voices/en_US-amy-medium.onnx}"
: "${VOX_WHISPER_BIN:=whisper-cli}"
: "${VOX_WHISPER_MODEL:=$REPO_DIR/models/ggml-base.en.bin}"
export VOX_PORT VOX_LLM_BASE_URL VOX_LLM_MODEL VOX_LLM_API_KEY \
       VOX_PIPER_BIN VOX_PIPER_VOICE VOX_WHISPER_BIN VOX_WHISPER_MODEL

# --- Check the LLM server is reachable --------------------------------------
# The backend talks to an OpenAI-compatible endpoint; /models is a cheap probe.
llm_hint() {
  if printf '%s' "$VOX_LLM_BASE_URL" | grep -q '8080'; then
    printf '   %sllama-server -m %s/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf --port 8080%s\n' \
      "$CYAN" "$REPO_DIR" "$RESET"
    printf '   (or:  %sllama-server -hf bartowski/Llama-3.2-3B-Instruct-GGUF --port 8080%s )\n' "$CYAN" "$RESET"
  else
    printf '   %sollama serve%s   (and once:  %sollama pull %s%s )\n' \
      "$CYAN" "$RESET" "$CYAN" "$VOX_LLM_MODEL" "$RESET"
  fi
}

printf '%sVOX%s → LLM at %s (model %s)\n' "$BOLD" "$RESET" "$VOX_LLM_BASE_URL" "$VOX_LLM_MODEL"
if command -v curl >/dev/null 2>&1; then
  if curl -fsS --max-time 3 "$VOX_LLM_BASE_URL/models" >/dev/null 2>&1; then
    printf '%s✓ LLM server is reachable.%s\n' "$GREEN" "$RESET"
  else
    printf '%s! LLM server not reachable at %s%s\n' "$YELLOW" "$VOX_LLM_BASE_URL" "$RESET"
    printf '  Start it in another terminal, then reload the page:\n'
    llm_hint
    printf '  (Starting VOX anyway — the UI will show a "brain offline" state.)\n'
  fi
else
  printf '%s! curl not found — skipping LLM reachability check.%s\n' "$YELLOW" "$RESET"
fi

# --- Open the browser shortly after the server binds ------------------------
URL="http://localhost:$VOX_PORT"
if command -v open >/dev/null 2>&1; then
  ( sleep 2; open "$URL" >/dev/null 2>&1 || true ) &
elif command -v xdg-open >/dev/null 2>&1; then
  ( sleep 2; xdg-open "$URL" >/dev/null 2>&1 || true ) &
fi

printf '\n%sStarting VOX on %s%s  (Ctrl-C to stop)\n\n' "$BOLD" "$URL" "$RESET"

# module path server.app, instance `app` — run from REPO_DIR so `server` imports.
exec uvicorn server.app:app --host 0.0.0.0 --port "$VOX_PORT"
