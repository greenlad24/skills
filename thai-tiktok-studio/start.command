#!/bin/bash
# Thai TikTok Studio — double-click to start (macOS). First run installs everything.
cd "$(dirname "$0")" || exit 1
echo "▶ Thai TikTok Studio"

find_python() {
  for c in python3.13 python3.12 python3.11 python3.10 \
           /Library/Frameworks/Python.framework/Versions/3.1[0-9]/bin/python3 \
           /usr/local/bin/python3 /opt/homebrew/bin/python3 python3; do
    p=$(command -v "$c" 2>/dev/null) || continue
    if "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      echo "$p"; return 0
    fi
  done
  return 1
}

PY=$(find_python)
if [ -z "$PY" ]; then
  echo ""
  echo "Python 3.10+ is needed (one-time install, ~2 minutes)."
  PKG="python-3.12.10-macos11.pkg"
  echo "Downloading the official installer from python.org…"
  curl -fL -o "/tmp/$PKG" "https://www.python.org/ftp/python/3.12.10/$PKG" && open "/tmp/$PKG"
  echo ""
  echo "➜ Finish the Python installer, then double-click start.command again."
  read -r -p "Press Enter to close…"
  exit 0
fi

if [ ! -x .venv/bin/python ]; then
  echo "Setting up (first run only)…"
  "$PY" -m venv .venv || { echo "Could not create the environment."; read -r; exit 1; }
fi

STAMP=".venv/.deps_stamp"
if [ ! -f "$STAMP" ] || ! cmp -s requirements.txt "$STAMP"; then
  echo "Installing components (first run takes a few minutes)…"
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -r requirements.txt || { echo "Install failed — check the internet connection."; read -r; exit 1; }
  cp requirements.txt "$STAMP"
fi

if command -v say >/dev/null && ! say -v '?' | grep -q '^Kanya '; then
  echo ""
  echo "Optional: to use the computer Thai voice instead of your own, install 'Kanya':"
  echo "  System Settings (or System Preferences) → Accessibility → Spoken Content →"
  echo "  System Voice → Manage Voices… → Thai → Kanya"
  echo ""
fi

exec .venv/bin/python -m studio.app
