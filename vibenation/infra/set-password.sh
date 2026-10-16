#!/usr/bin/env bash
# Change the VibeNation web login. Prompts for the name and new password (hidden),
# writes them to .env, signs everyone out and restarts the app.
set -euo pipefail
ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"
touch "$ENV_FILE" && chmod 600 "$ENV_FILE"

read -rp "Login name [band]: " NAME
NAME="${NAME:-band}"
read -rsp "New password (min 10 characters): " PW1; echo
read -rsp "Type it again: " PW2; echo
[ "$PW1" = "$PW2" ] || { echo "Passwords don't match. Nothing changed."; exit 1; }
[ "${#PW1}" -ge 10 ] || { echo "Too short. Nothing changed."; exit 1; }

NAME="$NAME" PW="$PW1" SECRET="$(openssl rand -hex 32)" python3 - "$ENV_FILE" <<'EOF'
import os, sys
path = sys.argv[1]
want = {'VN_ADMIN_USER': os.environ['NAME'], 'VN_ADMIN_PASSWORD': os.environ['PW'], 'VN_SESSION_SECRET': os.environ['SECRET']}
lines = [l for l in open(path).read().splitlines() if l.split('=', 1)[0] not in want]
lines += [f'{k}={v}' for k, v in want.items()]
open(path, 'w').write('\n'.join(lines) + '\n')
EOF

systemctl restart vibenation
echo "Done. Log in at https://app.jeeznews.com as '$NAME' with your new password."
