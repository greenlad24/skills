#!/usr/bin/env bash
#
# VOX — download the default voice + models.
#
#   * Piper voice  en_US-amy-medium  (.onnx + .onnx.json)  -> vox-hologram/voices/
#   * whisper model ggml-base.en.bin                        -> vox-hologram/models/  (optional STT)
#   * LLM model, depending on runtime:
#       - ollama  :  ollama pull llama3.2:3b
#       - llamacpp:  fetch a small instruct GGUF            -> vox-hologram/models/
#
# Usage:
#   ./scripts/download_models.sh [ollama|llamacpp]
#   (also honours the VOX_RUNTIME env var; defaults to ollama)
#
# Every download is guarded — existing files are skipped, so this is safe to
# re-run. Missing/failed OPTIONAL downloads only warn; they never abort.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VOICES_DIR="$REPO_DIR/voices"
MODELS_DIR="$REPO_DIR/models"

RUNTIME="${1:-${VOX_RUNTIME:-ollama}}"

CYAN=""; GREEN=""; YELLOW=""; BOLD=""; RESET=""
if [ -t 1 ]; then
  CYAN="$(printf '\033[36m')"; GREEN="$(printf '\033[32m')"
  YELLOW="$(printf '\033[33m')"; BOLD="$(printf '\033[1m')"; RESET="$(printf '\033[0m')"
fi
info() { printf '   %s\n' "$1"; }
ok()   { printf '   %s✓%s %s\n' "$GREEN" "$RESET" "$1"; }
warn() { printf '   %s!%s %s\n' "$YELLOW" "$RESET" "$1"; }
sec()  { printf '\n%s%s%s\n' "$BOLD" "$1" "$RESET"; }

mkdir -p "$VOICES_DIR" "$MODELS_DIR"

# fetch <url> <dest> <label> <required:0|1>
# Downloads to a temp file then moves into place; skips if dest already exists.
fetch() {
  url="$1"; dest="$2"; label="$3"; required="${4:-0}"
  if [ -f "$dest" ] && [ -s "$dest" ]; then
    ok "$label already present ($(basename "$dest"))"
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then
    warn "curl not found — cannot download $label."
    [ "$required" = "1" ] && return 1 || return 0
  fi
  info "Downloading ${label}..."
  info "  from $url"
  tmp="$dest.partial"
  if curl -fL --retry 3 --retry-delay 2 -o "$tmp" "$url"; then
    mv "$tmp" "$dest"
    ok "$label -> $(basename "$dest")"
  else
    rm -f "$tmp"
    if [ "$required" = "1" ]; then
      warn "Failed to download $label (required for that feature)."
      return 1
    else
      warn "Failed to download $label (optional) — skipping."
      return 0
    fi
  fi
}

# ---------------------------------------------------------------------------
sec "Piper voice — en_US-amy-medium (TTS)"
# ---------------------------------------------------------------------------
# Official voice files live in the rhasspy/piper-voices repo on Hugging Face.
PIPER_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium"
fetch "$PIPER_BASE/en_US-amy-medium.onnx" \
      "$VOICES_DIR/en_US-amy-medium.onnx" "Piper voice model" 0 || true
fetch "$PIPER_BASE/en_US-amy-medium.onnx.json" \
      "$VOICES_DIR/en_US-amy-medium.onnx.json" "Piper voice config" 0 || true

# ---------------------------------------------------------------------------
sec "whisper.cpp model — ggml-base.en.bin (STT, OPTIONAL)"
# ---------------------------------------------------------------------------
# Official GGML models are published in the ggerganov/whisper.cpp HF repo.
fetch "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin" \
      "$MODELS_DIR/ggml-base.en.bin" "whisper base.en model" 0 || true

# ---------------------------------------------------------------------------
sec "LLM model — runtime: $RUNTIME"
# ---------------------------------------------------------------------------
if [ "$RUNTIME" = "ollama" ]; then
  if command -v ollama >/dev/null 2>&1; then
    MODEL="${VOX_LLM_MODEL:-llama3.2:3b}"
    info "Pulling '$MODEL' with Ollama (this can take a few minutes)…"
    if ollama pull "$MODEL"; then
      ok "Ollama model '$MODEL' ready."
    else
      warn "ollama pull failed. Is the Ollama daemon running? Try: ollama serve"
    fi
  else
    warn "ollama not installed — skipping model pull."
    warn "Later:  ollama pull ${VOX_LLM_MODEL:-llama3.2:3b}"
  fi
else
  # llama.cpp path: fetch a small quantized Llama-3.2-3B-Instruct GGUF.
  # bartowski's quants are a widely-used, redistributable source of GGUFs.
  # NOTE: if the download 404s, the HF repo may require accepting terms in a
  # browser first, or a newer quant filename — see the repo page:
  #   https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF
  GGUF_URL="https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
  GGUF_DEST="$MODELS_DIR/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
  fetch "$GGUF_URL" "$GGUF_DEST" "Llama-3.2-3B-Instruct GGUF (Q4_K_M)" 0 || true
  if [ -f "$GGUF_DEST" ]; then
    info "Start it with:"
    info "  ${CYAN}llama-server -m $GGUF_DEST --port 8080${RESET}"
  else
    info "Alternatively let llama-server fetch a model itself (needs internet once):"
    info "  ${CYAN}llama-server -hf bartowski/Llama-3.2-3B-Instruct-GGUF --port 8080${RESET}"
  fi
fi

printf '\n%s✓ Download step done.%s Voices in %s/, models in %s/.\n' \
  "$GREEN" "$RESET" "voices" "models"
