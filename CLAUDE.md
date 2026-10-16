# VibeNation — project brief for Claude

VibeNation is a web app that runs a live music show and streams it, with Claude running everything automatically. The first band using it is a live funk/soul/R&B cover band streaming as **Music Live Love** (YouTube: @MusicLiveLove).

## Read these first
- `research_notes/Broadcast studio web app UX/00_user_design_decisions.md` — **the user's decisions. They override everything else.**
- `reports/Broadcast studio web app UX.md` — app UX/UI design report.
- `reports/Live mix chain YouTube sources.md` — live mix processing chain, YouTube-verified presets per channel (latest).
- `reports/Live broadcast mix processing chain.md` — first mix report (server DSP stack, transport, A/V sync).
- `research_notes/Live broadcast mix processing chain/00_sunrise_jam_rig_from_prior_session.md` — the band's real 16-channel list and rules.
- `designs/vibenation-canvas/` — the design source (Show, Mixer, Effects rack, Go Live, Break slate, Phone camera). Live canvas: https://claude.ai/artifact/Uw6pZ9yqBy2EWcbRvBoBaZ

## Hard rules (never break)
- Never mention Thailand, Koh Samui, islands or any location anywhere (titles, descriptions, tags, thumbnails, slates, app).
- Never mention "Sunrise Jam" in the app or anything public. The product name is **VibeNation** (one word, capital V and N).
- On air = **blue**. Errors = **red** only. Warnings = amber. Claude/AI = lilac.
- Claude runs the show in AUTO. No "manual mode" button: any control a human touches is held by the human for the rest of the stream; Claude only steps in on it for emergencies (feedback, clipping, dead signal).
- Claude never touches preamp gain on the mixer.
- No community/Skool link in descriptions.

## Architecture (agreed)
- **Venue:** Midas MR18 → USB (Analog tap, raw preamp, 16 ch, 48 kHz) → old Windows laptop that only *transmits* (SRT/JackTrip). Phones: Android native app + iPhone Safari page, landscape only, 1080p60, WebRTC, WB/exposure locked per stream, UI in a drawer, nothing over the picture.
- **Build server (this machine):** DigitalOcean Premium AMD 2 vCPU / 4 GB, Ubuntu 24.04, runs Claude Code 24/7 (Remote Control), hosts the web app, creates/destroys the show server via the DigitalOcean API.
- **Show server (per show, not yet created):** DigitalOcean GPU droplet RTX 4000 Ada (TOR1), ~$0.76/h. Real-time mixing (Carla + LSP/x42 plugins, JACK), mastering to −16 LUFS / −1 dBTP, compositing, encodes: 16:9 1080p60 (YouTube 9 Mbps; Twitch/Facebook 6 Mbps) + 9:16 720×1280 (TikTok/Instagram, Claude auto-reframe: Auto / Close-up / Band view). Verify NVENC on first boot.
- **AI:** Claude (user's Max plan via Claude Code, not API) = director + mixer, acting every 1–3 min or on alerts; a deterministic controller does fast moves within bounds. Hosted audio listener: Gemini Live (cheapest). On-server classifiers for instruments/roles/solos/feedback. Post-show learning updates the mix and a versioned director playbook.
- **Multistream:** YouTube, Twitch, Facebook (OAuth), TikTok, Instagram (stream keys; Instagram key changes every show). Auto title/SEO description/tags per platform; thumbnails via OpenAI GPT Image API from a live frame.

## Working style
- The user is non-technical-friendly but decisive: give a recommendation, keep answers short, confirm before spending money or anything irreversible.
- Commit and push work to the current branch; never push to other branches without permission.
