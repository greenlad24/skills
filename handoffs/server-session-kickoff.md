You are the VibeNation build session, running 24/7 on our DigitalOcean build server (`vibenation-build`, Ubuntu 24.04, 2 vCPU / 4 GB, user `vibe`, project in `~/vibenation`, git branch `claude/eloquent-bell-ytm4si` of `greenlad24/skills`). You run under Remote Control on my Claude Max plan, not the API.

## 1. Get the full context first
Run `git pull`, then read `CLAUDE.md` and every file it lists, in full:
- research_notes/Broadcast studio web app UX/00_user_design_decisions.md (my decisions; they override everything)
- reports/Broadcast studio web app UX.md
- reports/Live mix chain YouTube sources.md
- reports/Live broadcast mix processing chain.md
- research_notes/Live broadcast mix processing chain/00_sunrise_jam_rig_from_prior_session.md
- designs/vibenation-canvas/ (the approved screen designs; live canvas: https://claude.ai/artifact/Uw6pZ9yqBy2EWcbRvBoBaZ)

Then reply with a 10-line summary of the plan so I can confirm you have it right.

## 2. What's done
- Research: live mix chain (per-channel presets for the band's 16 channels, buses, effects, −16 LUFS master), app UX, Dribbble/YouTube references.
- Designs approved: Show screen, Mixing station (Engineer default, Easy/Detailed effects, live spectrum EQ), Effects rack, Pre-flight/Destinations/Go Live, Starting soon/Break/Thanks slate, Android camera app (landscape, drawer UI).
- This build server is set up with Claude Code + Remote Control. Nothing else is installed or bought yet.

## 3. Your first job (after the summary)
Propose the build plan as milestones, smallest useful thing first. My suggested order — challenge it if you see a better one:
1. **Repo + stack:** create a clean `vibenation/` app folder in this repo (monorepo: web app, server services, Android app, venue sender). Pick the stack and explain why in 5 lines.
2. **Web app shell:** the VibeNation UI from the designs (Show, Mix, Effects rack, Go Live) running on this server with fake/demo data, reachable in my browser behind a login.
3. **Audio path end-to-end on this server:** a test 16-channel multitrack file played in → real-time mix engine (JACK + Carla + LSP/x42) → master at −16 LUFS → listenable stream in the web app, with live meters and spectrum.
4. **Claude mixer loop** (bounded controller + Claude decisions every 1–3 min + "held by you" rule).
5. **Phones:** iPhone Safari camera page + Android app (landscape, locked WB/exposure, drawer UI), WebRTC to the server.
6. **Director + compositing + YouTube go-live** (then Twitch/Facebook, then TikTok/Instagram, then vertical output).
7. **GPU show server automation** (create/destroy the RTX 4000 Ada droplet per show via the DigitalOcean API; verify NVENC first).
8. **Venue laptop sender** (Windows, MR18 USB → SRT), then a private rehearsal stream.

## 4. Rules
- Follow the hard rules in CLAUDE.md exactly (no locations ever, no "Sunrise Jam", VibeNation spelling, colours, no manual-mode button, never touch preamp gain).
- Ask me before spending money, creating cloud resources, opening ports to the internet, or anything irreversible. API keys/secrets go in `.env` files that are never committed.
- This server is small (2 vCPU / 4 GB): no heavy video encoding here; keep that for the GPU show server. Resize only with my OK.
- Commit and push working steps to `claude/eloquent-bell-ytm4si`. Keep answers short and give me a recommendation, not a menu.

Start with step 1 (pull + read + 10-line summary).
