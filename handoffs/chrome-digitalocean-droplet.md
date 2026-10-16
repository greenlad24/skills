# Handoff: create the VibeNation build server on DigitalOcean

You are Claude in Chrome, working in the user's DigitalOcean account (already logged in).
Your job: fill in the "Create Droplet" form for ONE always-on build server, then STOP and hand back to the user before anything is purchased.

## Hard rules
- Do NOT click the final **Create Droplet** button. Stop on the review screen and tell the user the exact monthly price shown.
- Do NOT enter, view or change any payment / billing details.
- Do NOT create a GPU droplet, a database, Spaces or anything else. One droplet only.
- If a setting below is not available, or the price differs from ~$28/mo by more than $6, stop and report what you see instead of picking an alternative.
- If DigitalOcean asks for a password for the droplet, do not set one. SSH key only (see step 7).

## Steps
1. Go to https://cloud.digitalocean.com/droplets/new (or **Create → Droplets**).
2. **Region:** Singapore → datacenter **SGP1**.
3. **Image:** OS → **Ubuntu** → **24.04 (LTS) x64**.
4. **Droplet type:** **Basic**.
5. **CPU options:** **Premium AMD** (NVMe SSD).
6. **Size:** **2 vCPU · 4 GB RAM · 80 GB NVMe SSD** (Premium AMD, slug `s-2vcpu-4gb-amd`). Expected price ≈ $28/month — read the actual price on the page.
7. **Authentication:** **SSH Key**.
   - If a key is already listed in the account, tick it and tell the user its name.
   - If no key exists, click **New SSH Key**, then STOP and ask the user to paste their public key (the contents of `~/.ssh/id_ed25519.pub`). Never invent or generate a key yourself.
8. **Additional options:**
   - ✅ **Monitoring** (free).
   - ✅ **IPv6** (free).
   - **Backups:** turn ON, **weekly** (≈ +20% ≈ $5–6/month). If the user said no backups, leave off.
9. **Quantity:** 1.
10. **Hostname:** `vibenation-build`
11. **Tags:** `vibenation`, `build`
12. **Project:** the default project is fine (or create/choose `VibeNation` if offered).
13. Scroll to the summary. STOP. Report back to the user:
    - region, image, plan (vCPU / RAM / disk), backups on/off,
    - the **exact monthly and hourly total** shown,
    - the SSH key selected.
    Then wait for the user to say "create it" — and even then, let the user click **Create Droplet** themselves unless they explicitly tell you to click it.

## After the droplet exists (only if the user asks)
- Open the droplet page and report its **public IPv4 address**.
- Do not change firewalls, DNS or anything else.

## Context (for your understanding only)
This server will run Claude Code 24/7 (Remote Control mode) and host the VibeNation web app (an AI-run live-music streaming studio). A separate GPU show server (RTX 4000 Ada, TOR1) will be created later, automatically, per show — not now.
