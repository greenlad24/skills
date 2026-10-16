# Infra

- Build server: this machine (DigitalOcean, Ubuntu 24.04). Hosts the web app and Claude Code.
- Web access (milestone 2): `app.jeeznews.com` → Caddy (auto HTTPS) → server on 127.0.0.1:8080.
  Ports 80/443 stay closed until approved.
- Show server (milestone 6): GPU droplet created/destroyed per show via the DigitalOcean API.
