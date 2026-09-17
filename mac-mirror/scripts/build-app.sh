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
echo "==> swift build (release, $ARCH)"
swift build -c release --arch "$ARCH"

BIN="$(swift build -c release --arch "$ARCH" --show-bin-path)/DroidMirror"
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
