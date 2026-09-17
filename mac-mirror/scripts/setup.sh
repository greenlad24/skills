#!/bin/bash
# Downloads the two helper binaries DroidMirror needs into mac-mirror/Tools/:
#   - adb            (from Google's Android platform-tools)
#   - scrcpy-server  (the Android-side capture server from the scrcpy project)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS="$ROOT/Tools"
mkdir -p "$TOOLS"

SCRCPY_VERSION="2.7"
SCRCPY_SERVER_URL="https://github.com/Genymobile/scrcpy/releases/download/v${SCRCPY_VERSION}/scrcpy-server-v${SCRCPY_VERSION}"
SCRCPY_SERVER_SHA256="a23c5659f36c260f105c022d27bcb3eafffa26070e7baa9eda66d01377a1adba"
PLATFORM_TOOLS_URL="https://dl.google.com/android/repository/platform-tools-latest-darwin.zip"

echo "==> Downloading scrcpy-server v${SCRCPY_VERSION}"
curl -fsSL -o "$TOOLS/scrcpy-server" "$SCRCPY_SERVER_URL"
ACTUAL="$(shasum -a 256 "$TOOLS/scrcpy-server" | awk '{print $1}')"
if [[ "$ACTUAL" != "$SCRCPY_SERVER_SHA256" ]]; then
  echo "!! scrcpy-server checksum mismatch" >&2
  echo "   expected $SCRCPY_SERVER_SHA256" >&2
  echo "   got      $ACTUAL" >&2
  rm -f "$TOOLS/scrcpy-server"
  exit 1
fi

if [[ -x "$TOOLS/adb" ]]; then
  echo "==> adb already present in Tools/, skipping download"
else
  echo "==> Downloading Android platform-tools (adb)"
  TMP="$(mktemp -d)"
  curl -fsSL -o "$TMP/platform-tools.zip" "$PLATFORM_TOOLS_URL"
  unzip -q -o "$TMP/platform-tools.zip" -d "$TMP"
  cp "$TMP/platform-tools/adb" "$TOOLS/adb"
  chmod +x "$TOOLS/adb"
  rm -rf "$TMP"
fi

echo "==> Done. Tools:"
ls -la "$TOOLS"
