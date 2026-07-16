#!/usr/bin/env bash
#
# VOX — one-shot installer for a fully local AI hologram librarian.
# Target: macOS 11.7 Big Sur, Intel CPU (no Apple Silicon / no Metal).
#
# What this does (idempotent — safe to re-run):
#   1. Detects your OS / arch / macOS version.
#   2. Ensures Homebrew + a modern python3.
#   3. Creates a Python virtualenv in vox-hologram/.venv and installs deps.
#   4. Installs an LLM runtime:
#        - macOS < 12  -> llama.cpp  (llama-server, OpenAI API on :8080)   [Big Sur]
#        - macOS >= 12 -> Ollama     (ollama serve, OpenAI API on :11434)
#      (override with:  VOX_RUNTIME=llamacpp  ./setup.sh   or  VOX_RUNTIME=ollama)
#   5. Installs Piper (TTS) and whisper.cpp (STT, OPTIONAL).
#   6. Downloads the default voice + models via scripts/download_models.sh.
#
# Optional pieces (Piper voice / whisper) NEVER hard-fail the script.
# Required pieces (python venv, pip install) DO fail the script.

set -euo pipefail

# --- Locations --------------------------------------------------------------
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_DIR/.venv"
VOX_ENV_FILE="$REPO_DIR/.vox.env"

# --- Pretty output ----------------------------------------------------------
BOLD=""; DIM=""; CYAN=""; GREEN=""; YELLOW=""; RED=""; RESET=""
if [ -t 1 ]; then
  BOLD="$(printf '\033[1m')"; DIM="$(printf '\033[2m')"
  CYAN="$(printf '\033[36m')"; GREEN="$(printf '\033[32m')"
  YELLOW="$(printf '\033[33m')"; RED="$(printf '\033[31m')"; RESET="$(printf '\033[0m')"
fi
section() { printf '\n%s%s== %s ==%s\n' "$BOLD" "$CYAN" "$1" "$RESET"; }
info()    { printf '   %s\n' "$1"; }
ok()      { printf '   %s✓%s %s\n' "$GREEN" "$RESET" "$1"; }
warn()    { printf '   %s!%s %s\n' "$YELLOW" "$RESET" "$1"; }
die()     { printf '\n%s✗ %s%s\n' "$RED" "$1" "$RESET" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

cat <<'BANNER'

  ██╗   ██╗ ██████╗ ██╗  ██╗
  ██║   ██║██╔═══██╗╚██╗██╔╝   Local hologram librarian
  ██║   ██║██║   ██║ ╚███╔╝    Intel Mac · macOS Big Sur · 100% offline
  ╚██╗ ██╔╝██║   ██║ ██╔██╗
   ╚████╔╝ ╚██████╔╝██╔╝ ██╗
    ╚═══╝   ╚═════╝ ╚═╝  ╚═╝

BANNER

# ---------------------------------------------------------------------------
section "1/6  System check"
# ---------------------------------------------------------------------------
OS="$(uname -s)"
ARCH="$(uname -m)"
MACOS_VER=""
MACOS_MAJOR=0

if [ "$OS" != "Darwin" ]; then
  warn "This installer targets macOS. Detected: $OS ($ARCH)."
  warn "It may still work on Linux for development, but the macOS-only bits"
  warn "(Homebrew casks, 'open', prebuilt binaries) will be skipped/likely fail."
else
  MACOS_VER="$(sw_vers -productVersion 2>/dev/null || echo '0')"
  MACOS_MAJOR="$(printf '%s' "$MACOS_VER" | cut -d. -f1)"
  ok "macOS $MACOS_VER on $ARCH"
  if [ "$ARCH" = "arm64" ]; then
    info "Apple Silicon detected — VOX will run, though it was tuned for Intel."
  fi
fi

# Choose the LLM runtime. User override wins; otherwise pick by macOS version.
#   Big Sur (11) and older cannot run the modern Ollama.app -> llama.cpp.
VOX_RUNTIME="${VOX_RUNTIME:-}"
if [ -z "$VOX_RUNTIME" ]; then
  if [ "$OS" = "Darwin" ] && [ "$MACOS_MAJOR" -ge 12 ] 2>/dev/null; then
    VOX_RUNTIME="ollama"
  else
    VOX_RUNTIME="llamacpp"
  fi
fi
case "$VOX_RUNTIME" in
  ollama|llamacpp) ;;
  *) die "VOX_RUNTIME must be 'ollama' or 'llamacpp' (got '$VOX_RUNTIME')." ;;
esac
info "LLM runtime: ${BOLD}$VOX_RUNTIME${RESET}  (set VOX_RUNTIME=ollama|llamacpp to override)"
if [ "$VOX_RUNTIME" = "ollama" ] && [ "$MACOS_MAJOR" -lt 12 ] 2>/dev/null && [ "$OS" = "Darwin" ]; then
  warn "You forced Ollama on macOS < 12. The modern Ollama likely will NOT run"
  warn "on Big Sur. If 'ollama serve' fails, re-run with VOX_RUNTIME=llamacpp."
fi

# ---------------------------------------------------------------------------
section "2/6  Homebrew"
# ---------------------------------------------------------------------------
# Homebrew lives at /usr/local on Intel, /opt/homebrew on Apple Silicon.
if ! have brew; then
  for CANDIDATE in /usr/local/bin/brew /opt/homebrew/bin/brew; do
    if [ -x "$CANDIDATE" ]; then eval "$("$CANDIDATE" shellenv)"; break; fi
  done
fi

if have brew; then
  ok "Homebrew found: $(command -v brew)"
else
  if [ "$OS" != "Darwin" ]; then
    warn "Homebrew not found and not on macOS — skipping brew-based installs."
  else
    warn "Homebrew is not installed. It is required to install the runtimes."
    printf '   Install Homebrew now? [y/N] '
    read -r REPLY || REPLY=""
    if [ "$REPLY" = "y" ] || [ "$REPLY" = "Y" ]; then
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
      for CANDIDATE in /usr/local/bin/brew /opt/homebrew/bin/brew; do
        if [ -x "$CANDIDATE" ]; then eval "$("$CANDIDATE" shellenv)"; break; fi
      done
      have brew && ok "Homebrew installed." || die "Homebrew install did not complete."
    else
      warn "Skipping Homebrew. Install it yourself: https://brew.sh"
    fi
  fi
fi

# ---------------------------------------------------------------------------
section "3/6  Python + virtualenv (REQUIRED)"
# ---------------------------------------------------------------------------
PYTHON_BIN=""
for CAND in python3.11 python3.10 python3.9 python3.8 python3; do
  if have "$CAND"; then PYTHON_BIN="$CAND"; break; fi
done

if [ -z "$PYTHON_BIN" ]; then
  if have brew; then
    info "Installing python@3.11 via Homebrew…"
    brew install python@3.11 || die "Failed to install python@3.11."
    PYTHON_BIN="$(brew --prefix)/bin/python3.11"
  else
    die "No python3 found and no Homebrew to install it. Install Python 3.8+ first."
  fi
fi

# Enforce Python 3.8+.
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,8) else 1)'; then
  if have brew; then
    warn "$("$PYTHON_BIN" --version) is too old (need 3.8+). Installing python@3.11…"
    brew install python@3.11 || die "Failed to install python@3.11."
    PYTHON_BIN="$(brew --prefix)/bin/python3.11"
  else
    die "Python 3.8+ required. Found: $("$PYTHON_BIN" --version 2>&1)."
  fi
fi
ok "Using $("$PYTHON_BIN" --version 2>&1) ($PYTHON_BIN)"

if [ ! -d "$VENV_DIR" ]; then
  info "Creating virtualenv at .venv…"
  "$PYTHON_BIN" -m venv "$VENV_DIR" || die "Could not create the virtualenv."
else
  ok "Virtualenv already exists (.venv)"
fi

# shellcheck disable=SC1091
. "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip >/dev/null 2>&1 || warn "pip self-upgrade skipped."

info "Installing Python dependencies (requirements.txt)…"
python -m pip install -r "$REPO_DIR/requirements.txt" || die "pip install failed (REQUIRED)."
ok "Python dependencies installed."

# ---------------------------------------------------------------------------
section "4/6  LLM runtime ($VOX_RUNTIME)"
# ---------------------------------------------------------------------------
LLM_BASE_URL=""
if [ "$VOX_RUNTIME" = "ollama" ]; then
  LLM_BASE_URL="http://localhost:11434/v1"
  if have ollama; then
    ok "Ollama already installed: $(command -v ollama)"
  elif have brew; then
    info "Installing Ollama via Homebrew…"
    brew install ollama || warn "Ollama install failed. On Big Sur this is expected — retry with VOX_RUNTIME=llamacpp."
    have ollama && ok "Ollama installed." || warn "Ollama not on PATH after install."
  else
    warn "No Homebrew — install Ollama manually from https://ollama.com/download"
  fi
else
  LLM_BASE_URL="http://localhost:8080/v1"
  # Homebrew's llama.cpp formula provides 'llama-server'.
  if have llama-server; then
    ok "llama.cpp already installed: $(command -v llama-server)"
  elif have brew; then
    info "Installing llama.cpp via Homebrew (provides llama-server)…"
    brew install llama.cpp || warn "llama.cpp install failed — see README for source-build instructions."
    have llama-server && ok "llama.cpp installed." || warn "llama-server not on PATH after install."
  else
    warn "No Homebrew — build llama.cpp from source: https://github.com/ggml-org/llama.cpp"
  fi
fi

# ---------------------------------------------------------------------------
section "5/6  Voice (Piper) + Ears (whisper.cpp, OPTIONAL)"
# ---------------------------------------------------------------------------
# Piper TTS: the pip package 'piper-tts' ships an onnxruntime-backed CLI that
# works on Intel macOS wheels — the most reliable path across macOS versions.
# (A prebuilt Piper binary from the rhasspy/piper releases also works; see README.)
PIPER_BIN="piper"
if have piper; then
  ok "Piper already available: $(command -v piper)"
else
  info "Installing Piper TTS into the virtualenv (pip install piper-tts)…"
  if python -m pip install piper-tts >/dev/null 2>&1; then
    ok "Piper installed (venv). VOX_PIPER_BIN=piper"
  else
    warn "pip install piper-tts failed. VOX still runs text-only."
    warn "Alternative: download a prebuilt Piper macOS binary from"
    warn "  https://github.com/rhasspy/piper/releases  and set VOX_PIPER_BIN to it."
  fi
fi

# whisper.cpp STT is OPTIONAL — the app works text-only without it.
if have whisper-cli; then
  ok "whisper.cpp already available: $(command -v whisper-cli)"
elif have brew; then
  info "Installing whisper.cpp via Homebrew (provides whisper-cli)… [optional]"
  if brew install whisper-cpp >/dev/null 2>&1; then
    ok "whisper.cpp installed."
  else
    warn "whisper.cpp install failed — STT stays disabled, text input still works."
  fi
else
  warn "No Homebrew — skipping whisper.cpp. STT is optional; text input always works."
fi

# ---------------------------------------------------------------------------
section "6/6  Download voice + models"
# ---------------------------------------------------------------------------
# Never hard-fail the whole installer if optional downloads stumble.
if VOX_RUNTIME="$VOX_RUNTIME" bash "$REPO_DIR/scripts/download_models.sh" "$VOX_RUNTIME"; then
  ok "Model download step finished."
else
  warn "Some downloads did not complete. Re-run: ./scripts/download_models.sh $VOX_RUNTIME"
fi

# ---------------------------------------------------------------------------
# Persist the chosen runtime defaults so run.sh knows how to reach the LLM.
# Uses ':=' so anything you export yourself always wins over these defaults.
# ---------------------------------------------------------------------------
cat > "$VOX_ENV_FILE" <<EOF
# Written by setup.sh — chosen LLM runtime defaults for run.sh.
# Edit freely, or override by exporting VOX_* before ./run.sh.
: "\${VOX_RUNTIME:=$VOX_RUNTIME}"
: "\${VOX_LLM_BASE_URL:=$LLM_BASE_URL}"
export VOX_RUNTIME VOX_LLM_BASE_URL
EOF
ok "Saved runtime defaults to .vox.env"

# ---------------------------------------------------------------------------
printf '\n%s%s✓ Setup complete!%s\n\n' "$BOLD" "$GREEN" "$RESET"
printf '%sNext steps:%s\n' "$BOLD" "$RESET"
cat <<EOF
  1. Add your face:  copy a portrait to
        ${BOLD}web/assets/portrait.png${RESET}
     (a square, well-lit head-and-shoulders shot works best — see portrait/README.md).
     No portrait? VOX still launches with a stylized placeholder face.

  2. Start the LLM server (in a separate terminal, keep it running):
EOF
if [ "$VOX_RUNTIME" = "ollama" ]; then
  cat <<EOF
        ${CYAN}ollama serve${RESET}
     (first time only, in yet another terminal: ${CYAN}ollama pull llama3.2:3b${RESET})
EOF
else
  cat <<EOF
        ${CYAN}llama-server -m vox-hologram/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf --port 8080${RESET}
     (or let llama-server fetch a model itself: ${CYAN}llama-server -hf ... --port 8080${RESET})
EOF
fi
cat <<EOF

  3. Launch VOX:
        ${BOLD}./run.sh${RESET}
     It will open ${CYAN}http://localhost:8008${RESET} in your browser.

Enjoy your hologram librarian.
EOF
