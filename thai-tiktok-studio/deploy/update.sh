#!/usr/bin/env bash
# Pull the latest version and restart.   sudo bash update.sh
set -euo pipefail
APP_HOME=/home/studio
BRANCH="${BRANCH:-claude/wizardly-thompson-w6jjr8}"
sudo -u studio git -C "$APP_HOME/app" fetch --depth 1 origin "$BRANCH"
sudo -u studio git -C "$APP_HOME/app" checkout -B "$BRANCH" FETCH_HEAD
sudo -u studio "$APP_HOME/app/thai-tiktok-studio/.venv/bin/pip" install -q -r "$APP_HOME/app/thai-tiktok-studio/requirements.txt"
systemctl restart thai-tiktok-studio
echo "✅ Updated."
