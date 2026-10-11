#!/bin/bash
# Thai TikTok Studio.app — launcher. First run installs everything; later runs open in seconds.
CONTENTS="$(cd "$(dirname "$0")/.." && pwd)"
APP_SRC="$CONTENTS/Resources/app"
SUPPORT="$HOME/Library/Application Support/ThaiTikTokStudio"
LOG="$HOME/Library/Logs/ThaiTikTokStudio.log"
mkdir -p "$SUPPORT" "$HOME/Library/Logs"
exec >>"$LOG" 2>&1
echo "=== start $(date)"

say_note() { osascript -e "display notification \"$1\" with title \"Thai TikTok Studio\"" >/dev/null 2>&1; }
say_alert() { osascript -e "display dialog \"$1\" with title \"Thai TikTok Studio\" buttons {\"OK\"} default button 1 with icon caution" >/dev/null 2>&1; }

find_python() {
  for c in python3.13 python3.12 python3.11 python3.10 \
           /Library/Frameworks/Python.framework/Versions/3.1[0-9]/bin/python3 \
           /usr/local/bin/python3 /opt/homebrew/bin/python3 /usr/bin/python3; do
    p=$(command -v "$c" 2>/dev/null) || continue
    if "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      echo "$p"; return 0
    fi
  done
  return 1
}

PY=$(find_python)
if [ -z "$PY" ]; then
  ANSWER=$(osascript -e 'button returned of (display dialog "ต้องติดตั้ง Python ก่อน (ครั้งเดียว ประมาณ 2 นาที)\n\nPython is needed once. Install now?" with title "Thai TikTok Studio" buttons {"ยกเลิก / Cancel", "ติดตั้ง / Install"} default button 2)' 2>/dev/null)
  case "$ANSWER" in
    ติดตั้ง*)
      PKG="python-3.12.10-macos11.pkg"
      say_note "กำลังดาวน์โหลด Python…"
      if curl -fL -o "/tmp/$PKG" "https://www.python.org/ftp/python/3.12.10/$PKG"; then
        open "/tmp/$PKG"
        say_alert "ติดตั้ง Python ตามขั้นตอนให้เสร็จ แล้วเปิดแอปนี้อีกครั้ง\n\nFinish the Python installer, then open this app again."
      else
        say_alert "ดาวน์โหลดไม่สำเร็จ — ตรวจสอบอินเทอร์เน็ต\n\nDownload failed — check the internet connection."
      fi ;;
  esac
  exit 0
fi

VENV="$SUPPORT/venv"
if [ ! -x "$VENV/bin/python" ]; then
  "$PY" -m venv "$VENV" || { say_alert "ตั้งค่าไม่สำเร็จ (venv)\nSetup failed."; exit 1; }
fi

REQ="$APP_SRC/requirements-mac.txt"
if ! cmp -s "$REQ" "$SUPPORT/.deps_stamp"; then
  say_note "กำลังติดตั้งครั้งแรก… ใช้เวลาไม่กี่นาที (First-time setup, a few minutes)"
  "$VENV/bin/python" -m pip install -q --upgrade pip
  if "$VENV/bin/python" -m pip install -q -r "$REQ"; then
    cp "$REQ" "$SUPPORT/.deps_stamp"
  else
    say_alert "ติดตั้งไม่สำเร็จ — ตรวจสอบอินเทอร์เน็ตแล้วเปิดแอปอีกครั้ง\n\nInstall failed — check the internet and open the app again.\nLog: ~/Library/Logs/ThaiTikTokStudio.log"
    exit 1
  fi
fi

# Claude Code (for "your Claude account" mode) needs macOS 13+; install quietly in the background.
MAJOR=$(sw_vers -productVersion 2>/dev/null | cut -d. -f1)
if [ "${MAJOR:-0}" -ge 13 ] && ! command -v claude >/dev/null && [ ! -x "$HOME/.local/bin/claude" ]; then
  (curl -fsSL https://claude.ai/install.sh | bash) >/dev/null 2>&1 &
fi
export PATH="$HOME/.local/bin:$PATH"

export TTS_STUDIO_ICON="$CONTENTS/Resources/AppIcon.png"
cd "$APP_SRC" || exit 1
exec "$VENV/bin/python" -m studio.desktop
