#!/bin/bash
#
# Installer for wav2mp3 on macOS (Apple Silicon — M1/M2/M3/M4).
# Installs Homebrew's ffmpeg if needed, then puts wav2mp3 on your PATH.

set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$SRC_DIR/wav2mp3"

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m==> %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[31mError: %s\033[0m\n' "$*" >&2; exit 1; }

[ -f "$SCRIPT" ] || die "wav2mp3 not found next to this installer"
[ "$(uname -s)" = "Darwin" ] || warn "not macOS — installing anyway"

# ---------------------------------------------------------------- ffmpeg --

if command -v ffmpeg >/dev/null 2>&1; then
	say "ffmpeg already installed ($(ffmpeg -version | head -1 | cut -d' ' -f3))"
else
	command -v brew >/dev/null 2>&1 || die \
		"Homebrew is required. Install it from https://brew.sh then re-run this script."
	say "Installing ffmpeg via Homebrew (this takes a few minutes)…"
	brew install ffmpeg
fi

ffmpeg -hide_banner -encoders 2>/dev/null | grep -q ' libmp3lame ' \
	|| die "this ffmpeg build lacks libmp3lame. Try: brew reinstall ffmpeg"

# ------------------------------------------------------------ place on PATH --

# Prefer the Homebrew bin dir already on PATH; otherwise use ~/.local/bin.
TARGET_DIR=""
for d in /opt/homebrew/bin /usr/local/bin; do
	if [ -d "$d" ] && [ -w "$d" ]; then TARGET_DIR="$d"; break; fi
done
if [ -z "$TARGET_DIR" ]; then
	TARGET_DIR="$HOME/.local/bin"
	mkdir -p "$TARGET_DIR"
fi

chmod +x "$SCRIPT"
ln -sf "$SCRIPT" "$TARGET_DIR/wav2mp3"
say "Linked $TARGET_DIR/wav2mp3 -> $SCRIPT"

case ":$PATH:" in
	*":$TARGET_DIR:"*) ;;
	*)
		warn "$TARGET_DIR is not on your PATH. Add it with:"
		printf '\n    echo '\''export PATH="%s:$PATH"'\'' >> ~/.zshrc && source ~/.zshrc\n\n' "$TARGET_DIR"
		;;
esac

say "Done. Try:  wav2mp3 --help"
