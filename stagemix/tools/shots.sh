#!/usr/bin/env bash
# Screenshots of the real app, on a real (virtual) tablet.
#
# The app cannot show itself without sixteen channels of live meter off
# a console, so every UI change until now shipped unseen. `--ez demo
# true` drives the whole screen from a synthetic band — see
# DemoStage.kt, which cannot reach a mixer — and this takes the picture.
set -euo pipefail
APK=${1:-StageMix.apk}
OUT=${2:-shots}
mkdir -p "$OUT"

adb wait-for-device
adb install -r "$APK"
# a console is landscape, and it never rotates
adb shell settings put system accelerometer_rotation 0
adb shell settings put system user_rotation 1
adb shell settings put system screen_off_timeout 1800000

shot () {   # shot <name> <tab> <mixing>
  adb shell am start -S -n com.stagemix.app/.MainActivity \
    --ez demo true --ez mixing "$3" --ei tab "$2" >/dev/null
  sleep 7
  adb exec-out screencap -p > "$OUT/$1.png"
  echo "  $1.png  $(stat -c%s "$OUT/$1.png") bytes"
}

shot mixer      0 true
shot monitors   1 true
shot log        2 true
shot setup      3 true
shot watching   0 false
echo "screenshots in $OUT:"
ls -la "$OUT"
