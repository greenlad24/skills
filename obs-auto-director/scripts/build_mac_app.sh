#!/usr/bin/env bash
# Build a standalone macOS binary of AutoDirector with PyInstaller.
#
# Produces dist/autodirector — a single-file executable that needs no
# Python install on the target machine. Run from the repo root:
#   ./scripts/build_mac_app.sh
#
# For distribution beyond your own machine, sign and notarize:
#   codesign --deep --force --options runtime \
#     --sign "Developer ID Application: YOUR NAME (TEAMID)" dist/autodirector
#   xcrun notarytool submit dist/autodirector --keychain-profile default --wait
#
# The binary needs microphone permission; when embedding in a .app bundle,
# include NSMicrophoneUsageDescription in Info.plist.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pip install --quiet pyinstaller '.[mixer]'
pyinstaller --onefile --name autodirector \
  --collect-all sounddevice \
  --hidden-import websockets \
  --hidden-import rtmidi \
  autodirector/app.py

echo
echo "Built: dist/autodirector"
echo "Try:   ./dist/autodirector devices"
