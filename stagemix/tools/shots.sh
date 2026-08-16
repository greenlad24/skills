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

# A console is landscape and never rotates. The activity is already
# locked to landscape in the manifest, and a tablet's NATURAL
# orientation is landscape — so the right thing here is to pin the
# display to natural (0) and stop it turning. Forcing user_rotation 1
# turns a landscape tablet into portrait, which is how the first batch
# of these came out sideways and skewed: screencap caught the rotation
# animation still running.
adb shell settings put system accelerometer_rotation 0
adb shell settings put system user_rotation 0
adb shell settings put system screen_off_timeout 1800000
# and no animation means no half-drawn frame to photograph
for s in window_animation_scale transition_animation_scale \
         animator_duration_scale; do
  adb shell settings put global $s 0.0
done
adb shell wm dismiss-keyguard >/dev/null 2>&1 || true

# Assert it, don't hope for it. The framebuffer stays 2560x1800 even
# when the display is turned, so the PNG's own dimensions prove
# nothing — the rotation does. 0 is natural, which on a tablet is
# landscape, which is the only way this app is ever used.
rot=$(adb shell settings get system user_rotation | tr -d '\r')
if [ "$rot" != "0" ]; then
  echo "!! display rotation is $rot, not 0 — shots would come out sideways"
  exit 1
fi

shot () {   # shot <name> <tab> <mixing>
  adb shell am start -S -n com.stagemix.app/.MainActivity \
    --ez demo true --ez mixing "$3" --ei tab "$2" >/dev/null
  sleep 7
  adb exec-out screencap -p > "$OUT/$1.png"
  read -r w h < <(python3 -c "
import struct
d = open('$OUT/$1.png','rb').read(24)
print(*struct.unpack('>II', d[16:24]))")
  echo "  $1.png  ${w}x${h}  $(stat -c%s "$OUT/$1.png") bytes"
}

# the two panic states, driven straight in through the demo intent so
# the amber "not mixing" bar and the FROZEN / WAITING header are on the
# glass for the picture (the keys that produce them cannot be tapped
# reliably headless — see smoke.sh step 8)
shot_state () {   # shot_state <name> <mixing> <frozen> <muted>
  adb shell am start -S -n com.stagemix.app/.MainActivity \
    --ez demo true --ez mixing "$2" --ez frozen "$3" --ez muted "$4" \
    --ei tab 0 >/dev/null
  sleep 7
  adb exec-out screencap -p > "$OUT/$1.png"
  echo "  $1.png  $(stat -c%s "$OUT/$1.png") bytes"
}

shot mixer      0 true
shot monitors   1 true
shot status     2 true
shot log        3 true
shot setup      4 true
shot watching   0 false
shot_state frozen  true true  false
shot_state waiting true false true
echo "screenshots in $OUT:"
ls -la "$OUT"
