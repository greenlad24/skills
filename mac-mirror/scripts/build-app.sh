#!/bin/bash
# Builds DroidMirror.app for Intel Macs (x86_64, macOS 11+) into mac-mirror/build/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x Tools/adb || ! -f Tools/scrcpy-server ]]; then
  echo "Tools/adb or Tools/scrcpy-server missing — running scripts/setup.sh first"
  "$ROOT/scripts/setup.sh"
fi

ARCH="${ARCH:-x86_64}"
mkdir -p "$ROOT/build"
BIN="$ROOT/build/DroidMirror"

# Compile with swiftc directly: this works with just the Command Line Tools installed
# (SwiftPM's `swift build` needs full Xcode for xctest).
echo "==> swiftc (release, $ARCH)"
xcrun swiftc -O \
  -target "$ARCH-apple-macos11.0" \
  -module-name DroidMirror \
  -framework AppKit -framework AVFoundation -framework CoreMedia -framework QuartzCore \
  Sources/DroidMirror/*.swift \
  -o "$BIN"

APP="$ROOT/build/DroidMirror.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/DroidMirror"
cp Resources/Info.plist "$APP/Contents/Info.plist"
cp Tools/adb "$APP/Contents/Resources/adb"
cp Tools/scrcpy-server "$APP/Contents/Resources/scrcpy-server"
echo -n "APPL????" > "$APP/Contents/PkgInfo"

echo "==> codesign (ad hoc)"
codesign --force --deep --sign - "$APP"

echo "==> Built $APP"
echo "    open \"$APP\""
