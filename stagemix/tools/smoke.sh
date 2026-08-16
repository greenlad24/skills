#!/usr/bin/env bash
# Does the APK actually work?
#
# The engine has three hundred unit tests and none of them can tell you
# that the app launches, that a tab draws, that a key is reachable with
# a thumb, or that the thing does not throw the moment it is opened on
# a tablet with no mixer in the room. That gap is exactly where this
# project has lost time before: code that was correct and an app that
# was not doing anything.
#
# So this installs the real release APK on a real (virtual) tablet,
# drives every feature through the UI, reads back what is on the screen
# via the accessibility tree, and fails loudly if a claim the app makes
# is not on the glass. It also watches logcat the whole time: any
# FATAL EXCEPTION anywhere fails the run, even if the assertions pass.
set -uo pipefail
APK=${1:-StageMix.apk}
PKG=com.stagemix.app
ACT=$PKG/.MainActivity
FAILED=0
STEP=""

say  () { echo "  · $*"; }
step () { STEP="$1"; echo; echo "== $1"; }
bad  () { echo "  !! FAIL [$STEP] $*"; FAILED=1; }

adb wait-for-device
adb install -r "$APK" >/dev/null || { echo "install failed"; exit 1; }
adb shell settings put system accelerometer_rotation 0
adb shell settings put system user_rotation 0
adb shell settings put system screen_off_timeout 1800000
for s in window_animation_scale transition_animation_scale \
         animator_duration_scale; do
  adb shell settings put global $s 0.0
done
adb logcat -c

# ---------------------------------------------------------------- helpers

# The screen, as text. Compose publishes its text into the
# accessibility tree, so this is the closest thing to "what a person
# can actually read", and far more honest than a screenshot nobody
# looks at.
screen () {
  adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1
  adb shell cat /sdcard/ui.xml 2>/dev/null \
    | tr '>' '>\n' | grep -o 'text="[^"]*"' | sed 's/text="//;s/"$//' \
    | grep -v '^$'
}

# launch the demo on a given tab, in a given mode
open_demo () {   # open_demo <tab> <mixing>
  adb shell am start -S -n "$ACT" \
    --ez demo true --ez mixing "$2" --ei tab "$1" >/dev/null
  sleep 6
}

want () {        # want <what it is> <string...>
  local label="$1"; shift
  local ui; ui=$(screen)
  local missing=()
  for s in "$@"; do
    grep -qiF -- "$s" <<<"$ui" || missing+=("$s")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    bad "$label — not on screen: ${missing[*]}"
    echo "     screen was:"; sed 's/^/       /' <<<"$ui" | head -40
  else
    say "$label ✓"
  fi
}

wantnot () {     # wantnot <what it is> <string>
  local ui; ui=$(screen)
  if grep -qiF -- "$2" <<<"$ui"; then bad "$1 — '$2' should not be shown"
  else say "$1 ✓"; fi
}

# tap the middle of the first node whose text matches
tap () {         # tap <text>
  adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1
  local b
  b=$(adb shell cat /sdcard/ui.xml 2>/dev/null | tr '>' '>\n' \
      | grep -F "text=\"$1\"" | grep -o 'bounds="[^"]*"' | head -1 \
      | grep -o '[0-9]\+')
  if [ -z "$b" ]; then bad "cannot find '$1' to tap"; return 1; fi
  local x1 y1 x2 y2
  read -r x1 y1 x2 y2 <<<"$(echo $b)"
  adb shell input tap $(( (x1 + x2) / 2 )) $(( (y1 + y2) / 2 ))
  sleep 3
}

crashes () {
  adb logcat -d -b crash 2>/dev/null | grep -c "FATAL EXCEPTION" || true
}

# ================================================================ 1. it opens
step "1 · it launches with no mixer in the room, and says so"
adb shell am start -S -n "$ACT" >/dev/null
sleep 9
# Auto-start is on by default, so with no console on the network this
# must land in a stated, explained state — never a blank screen and
# never a crash. Both wordings are legitimate: still searching, or
# given up and asking.
ui=$(screen)
if grep -qiE "looking for the mixer|not connected|no mixer|connect" <<<"$ui"
then say "says what is happening with no console ✓"
else bad "launched with no mixer and said nothing useful"
     sed 's/^/       /' <<<"$ui" | head -30; fi
[ "$(crashes)" = "0" ] || bad "crashed on cold launch with no mixer"

# ============================================================== 2. the rack
step "2 · MIXER — the rack, meters, and the app's travel per channel"
open_demo 0 true
want "channel strips and their instruments" \
  "DRUM KICK" "BASS DI" "VOCAL CEN" "HARMONI" "LEAD"
want "the transport, including the new REBAL key" \
  "MIX" "FREEZE" "KEEP" "Re-Balance" "UNDO"
want "all five tabs" "MIXER" "MONITORS" "STATUS" "LOG" "SETUP"
want "the state word and the master meters" "MIXING" "LEAD" "BAND"
want "a ring-out notch drawn on the channel it is on" "196 Hz"

# =========================================================== 3. progress bar
step "3 · the progress bar is there when nothing is wrong"
want "what it is doing, with a figure" \
  "Holding the balance you kept" "channels sitting where they should be"
[ "$(crashes)" = "0" ] || bad "crashed on the mixer tab"

# ============================================================= 4. monitors
step "4 · MONITORS — the wedges, by position"
open_demo 1 true
want "every monitor on the stage, named and typed" \
  "CENTER MON" "PIANO MON" "DRUM IEM" "BASS MON" "IN EAR 2"
# the monitors tab is a MIXER now: it names the wedge kind, states
# whether keeping is on, and shows per-send state (a channel not routed
# to a wedge reads NOT SENT)
want "the wedge read as a mixer" "read only" "NOT SENT"

# =============================================== 5. errors, with the remedy
step "5 · STATUS — every fault carries the thing to do about it"
open_demo 2 true
want "the panel is titled as advice, not as an error list" \
  "WHAT IS WRONG, AND WHAT TO DO"
# with the demo mixing and healthy, the honest answer is "nothing" —
# and it must SAY that rather than going blank, which is the entire
# lesson of the three nights
want "it says so when nothing is wrong" "Everything is working"

step "5b · NOT MIXING is a fault, in fault colours, on every tab"
open_demo 0 false
want "the rack says it is not sending" "WATCHING ONLY" "WOULD"
want "and the fault line says it too, with what to press" \
  "NOT MIXING" "Tap MIX"
open_demo 2 false
want "and it is top of the status list" "NOT MIXING"

# ================================================================== 6. log
step "6 · LOG — the night in sentences"
open_demo 3 true
want "decisions in the operator's language" \
  "WHAT IT HAS DONE" "TAKEOVER" "OVERRIDE"

# ================================================================ 7. setup
step "7 · SETUP — the switches that decide what it does unasked"
open_demo 4 true
want "auto-start and monitor keeping are both offered" \
  "AUTO-START" "KEEP MONITORS" "EQ + COMP"
want "and the health figures" "VOCAL ON TOP" "OUT-MIXED"

# ====================================================== 8. the keys work
step "8 · the transport keys actually do something"

# Tap a key, then poll the screen for a word for up to ~8s. The demo's
# state flips in the click handler, but a fresh-launched Compose tree
# can take a moment to settle and redraw, so a single 3s read is
# racy — poll instead of asserting once.
tap_then () {   # tap_then <key> <expected word> <label>
  tap "$1" || { bad "cannot tap $1"; return; }
  for _ in 1 2 3 4 5 6; do
    grep -qiF -- "$3" <<<"$(screen)" && { say "$2 ✓"; return; }
    sleep 1.3
  done
  bad "$2 — '$3' never appeared after tapping $1"
  sed 's/^/       /' <<<"$(screen)" | head -30
}

open_demo 0 true
tap_then "MIX" "MIX hands the mains back" "WATCHING ONLY"
open_demo 0 true
tap_then "FREEZE" "FREEZE holds everything" "FROZEN"
open_demo 0 true
tap "Re-Balance" >/dev/null 2>&1 || bad "Re-Balance not tappable"
sleep 2
[ "$(crashes)" = "0" ] || bad "crashed pressing a transport key"

# =========================================================== 9. still alive
step "9 · nothing fell over anywhere"
n=$(crashes)
if [ "$n" != "0" ]; then
  bad "$n fatal exception(s)"
  adb logcat -d -b crash | tail -60
else
  say "no fatal exceptions in the whole run ✓"
fi
# and an ANR is a frozen screen at a gig, which is as bad as a crash
if adb logcat -d | grep -q "ANR in $PKG"; then
  bad "the app stopped responding"
  adb logcat -d | grep -A5 "ANR in $PKG" | head -20
else
  say "no ANR ✓"
fi

echo
if [ "$FAILED" = "0" ]; then echo "SMOKE PASSED"; else echo "SMOKE FAILED"; fi
exit $FAILED
