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
#
# Some Macs end up with an SDK newer than their Swift compiler (e.g. Command Line Tools 12.5.1
# next to a leftover MacOSX12.1.sdk). Try the default SDK first, then every other installed
# macOS SDK, oldest first, until one compiles. Override with SDK=/path/to/MacOSX11.3.sdk.
compile_with_sdk() {
  local sdk="$1"
  echo "==> swiftc (release, $ARCH, SDK: ${sdk:-default})"
  local sdk_args=()
  [[ -n "$sdk" ]] && sdk_args=(-sdk "$sdk")
  xcrun swiftc -O \
    -target "$ARCH-apple-macos11.0" \
    -module-name DroidMirror \
    "${sdk_args[@]}" \
    -framework AppKit -framework AVFoundation -framework CoreMedia -framework QuartzCore \
    Sources/DroidMirror/*.swift \
    -o "$BIN"
}

if [[ -n "${SDK:-}" ]]; then
  compile_with_sdk "$SDK"
else
  candidates=("")
  DEV_DIR="$(xcode-select -p 2>/dev/null || echo /Library/Developer/CommandLineTools)"
  for dir in "$DEV_DIR/SDKs" "$DEV_DIR/Platforms/MacOSX.platform/Developer/SDKs" /Library/Developer/CommandLineTools/SDKs; do
    [[ -d "$dir" ]] || continue
    while IFS= read -r sdk; do
      [[ -L "$sdk" ]] && continue          # skip the MacOSX.sdk symlink (that is the default)
      candidates+=("$sdk")
    done < <(ls -d "$dir"/MacOSX*.sdk 2>/dev/null | sort -V)
  done
  built=0
  for sdk in "${candidates[@]}"; do
    if compile_with_sdk "$sdk"; then built=1; break; fi
    echo "!! build failed with SDK '${sdk:-default}', trying the next one…" >&2
  done
  if [[ $built -ne 1 ]]; then
    echo "!! Could not compile with any installed SDK. Your Swift compiler and SDK versions do not match." >&2
    echo "   Fix: install 'Command Line Tools for Xcode 13.2.1' from https://developer.apple.com/download/all/" >&2
    exit 1
  fi
fi

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
