#!/usr/bin/env bash
# Build AutoDirector.pkg — a double-clickable macOS installer that puts
# AutoDirector.app into /Applications.
#
# Run ON A MAC from the repo root:
#   ./scripts/build_pkg.sh
# Output: dist/AutoDirector.pkg
#
# Signing & notarization (optional, recommended for distribution):
#   export APP_SIGN_ID="Developer ID Application: Your Name (TEAMID)"
#   export PKG_SIGN_ID="Developer ID Installer: Your Name (TEAMID)"
#   export NOTARY_PROFILE="your-notarytool-keychain-profile"
# Unset -> unsigned build (fine for your own machine; right-click → Open).
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="2.0.0"
IDENTIFIER="io.autodirector.app"

echo "==> Installing build deps"
python3 -m pip install --quiet pyinstaller .

echo "==> Building AutoDirector.app with PyInstaller"
rm -rf build dist
pyinstaller --noconfirm --windowed --name AutoDirector \
  --osx-bundle-identifier "$IDENTIFIER" \
  --collect-all sounddevice \
  --hidden-import websockets \
  packaging/launch.py

APP="dist/AutoDirector.app"
PLIST="$APP/Contents/Info.plist"

echo "==> Patching Info.plist"
/usr/libexec/PlistBuddy -c \
  "Add :NSMicrophoneUsageDescription string 'AutoDirector listens to your show audio to direct scene switching and manage voice processing. Audio never leaves this Mac.'" \
  "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c \
  "Add :LSMinimumSystemVersion string '12.0'" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c \
  "Set :CFBundleShortVersionString $VERSION" "$PLIST" 2>/dev/null || true

if [[ -n "${APP_SIGN_ID:-}" ]]; then
  echo "==> Codesigning app"
  codesign --deep --force --options runtime --sign "$APP_SIGN_ID" "$APP"
fi

echo "==> Building component package"
mkdir -p build/pkgroot/Applications
cp -R "$APP" build/pkgroot/Applications/
pkgbuild --root build/pkgroot \
  --identifier "$IDENTIFIER" --version "$VERSION" \
  --install-location / \
  build/AutoDirector-component.pkg

echo "==> Building distributable installer"
mkdir -p build/resources
cat > build/resources/welcome.txt <<'EOF'
AutoDirector — an automatic scene director for OBS Studio.

This installs AutoDirector.app into /Applications.

After installing:
 1. In OBS: Tools -> WebSocket Server Settings -> Enable
 2. Launch AutoDirector — the Control Room opens in your browser
 3. Follow Setup, then (live mode) run the 20-second calibration
EOF
cat > build/distribution.xml <<EOF
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
  <title>AutoDirector</title>
  <welcome file="welcome.txt" mime-type="text/plain"/>
  <options customize="never" require-scripts="false" rootVolumeOnly="true"/>
  <pkg-ref id="$IDENTIFIER" version="$VERSION">AutoDirector-component.pkg</pkg-ref>
  <choices-outline><line choice="default"/></choices-outline>
  <choice id="default" title="AutoDirector">
    <pkg-ref id="$IDENTIFIER"/>
  </choice>
</installer-gui-script>
EOF

SIGN_ARGS=()
[[ -n "${PKG_SIGN_ID:-}" ]] && SIGN_ARGS=(--sign "$PKG_SIGN_ID")
productbuild --distribution build/distribution.xml \
  --package-path build --resources build/resources \
  "${SIGN_ARGS[@]}" dist/AutoDirector.pkg

if [[ -n "${NOTARY_PROFILE:-}" ]]; then
  echo "==> Notarizing"
  xcrun notarytool submit dist/AutoDirector.pkg \
    --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple dist/AutoDirector.pkg
fi

echo
echo "Done: dist/AutoDirector.pkg"
[[ -z "${APP_SIGN_ID:-}" ]] && echo \
  "(unsigned — on first launch use right-click → Open, or sign & notarize)"
