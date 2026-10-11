#!/usr/bin/env bash
# Thai TikTok Studio — one-command setup on a free Oracle Cloud "Always Free" Ubuntu server.
#   sudo bash oracle-setup.sh
# Optional env: STUDIO_PASSWORD, DOMAIN (default <ip>.sslip.io), REPO_URL, BRANCH
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/greenlad24/skills.git}"
BRANCH="${BRANCH:-claude/wizardly-thompson-w6jjr8}"
APP_USER=studio
APP_HOME=/home/$APP_USER
APP_DIR=$APP_HOME/app/thai-tiktok-studio
PORT=8765

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo:  sudo bash $0"; exit 1; }

if [ -z "${STUDIO_PASSWORD:-}" ]; then
  read -r -s -p "Choose a password for the website: " STUDIO_PASSWORD </dev/tty; echo
  [ -n "$STUDIO_PASSWORD" ] || { echo "A password is required."; exit 1; }
fi

echo "▶ Installing system packages…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git curl ffmpeg fonts-noto-color-emoji \
  debian-keyring debian-archive-keyring apt-transport-https gnupg netfilter-persistent iptables-persistent

echo "▶ Installing Caddy (automatic free HTTPS)…"
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y && apt-get install -y caddy
fi

echo "▶ Creating the app user and downloading the app…"
id -u $APP_USER >/dev/null 2>&1 || useradd -m -s /bin/bash $APP_USER
if [ -d "$APP_HOME/app/.git" ]; then
  sudo -u $APP_USER git -C "$APP_HOME/app" fetch --depth 1 origin "$BRANCH"
  sudo -u $APP_USER git -C "$APP_HOME/app" checkout -B "$BRANCH" FETCH_HEAD
else
  sudo -u $APP_USER git clone --depth 1 -b "$BRANCH" "$REPO_URL" "$APP_HOME/app"
fi

echo "▶ Installing Python components…"
sudo -u $APP_USER python3 -m venv "$APP_DIR/.venv"
sudo -u $APP_USER "$APP_DIR/.venv/bin/pip" install -q --upgrade pip
sudo -u $APP_USER "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "▶ Installing Claude Code (for 'your Claude account' mode)…"
sudo -u $APP_USER bash -c 'curl -fsSL https://claude.ai/install.sh | bash' || echo "  (Claude Code install failed — other AI modes still work)"

PUBLIC_IP=$(curl -fsS https://api.ipify.org || hostname -I | awk '{print $1}')
DOMAIN="${DOMAIN:-$(echo "$PUBLIC_IP" | tr . -).sslip.io}"

echo "▶ Writing configuration…"
umask 077
cat > /etc/thai-tiktok-studio.env <<ENV
TTS_STUDIO_SERVER=1
TTS_STUDIO_PASSWORD=$STUDIO_PASSWORD
TTS_STUDIO_HOST=127.0.0.1
TTS_STUDIO_PORT=$PORT
TTS_STUDIO_PUBLIC_URL=https://$DOMAIN
TTS_STUDIO_HOME=$APP_HOME/ThaiTikTokStudio
PATH=$APP_HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
ENV
umask 022

cat > /etc/systemd/system/thai-tiktok-studio.service <<UNIT
[Unit]
Description=Thai TikTok Studio
After=network-online.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=/etc/thai-tiktok-studio.env
ExecStart=$APP_DIR/.venv/bin/python -m studio.app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/caddy/Caddyfile <<CADDY
$DOMAIN {
  encode gzip
  request_body {
    max_size 50GB
  }
  reverse_proxy 127.0.0.1:$PORT {
    transport http {
      read_timeout 1h
      write_timeout 1h
    }
  }
}
CADDY

echo "▶ Opening the web ports in the server firewall…"
for p in 80 443; do
  if ! iptables -C INPUT -p tcp --dport $p -j ACCEPT 2>/dev/null; then
    # Oracle's Ubuntu image ends INPUT with a REJECT rule — insert right before it
    POS=$(iptables -L INPUT --line-numbers -n | awk '/REJECT/ {print $1; exit}')
    if [ -n "$POS" ]; then iptables -I INPUT "$POS" -p tcp --dport $p -j ACCEPT
    else iptables -A INPUT -p tcp --dport $p -j ACCEPT; fi
  fi
done
netfilter-persistent save >/dev/null 2>&1 || true

systemctl daemon-reload
systemctl enable --now thai-tiktok-studio
systemctl restart caddy

echo ""
echo "✅ Done!  Open:  https://$DOMAIN"
echo "   (If it doesn't load: in the Oracle console add Ingress rules for TCP 80 and 443 — see DEPLOY.md step 3.)"
echo "   Connect your Claude account:  sudo -u $APP_USER $APP_HOME/.local/bin/claude setup-token"
echo "   then paste the token in the website's ⚙ Settings."
