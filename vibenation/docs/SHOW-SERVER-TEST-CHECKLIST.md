# Show server: checklist before every show

The show server costs money **while it exists** (powered off still bills; only *destroy* stops it).
Start it from **Go Live → Show server** (asks the cost, auto-off after 3/5/8 h), or Claude runs `infra/showserver/showserver.py create`.

Status as of 17 Oct 2026, after two rehearsals. ✅ done · ❌ to do · ⏳ tonight

## Which server
- ✅ **CPU-Optimized c-16** (16 dedicated vCPU, $0.50/h), region **BLR1** (nearest the build server, so less internet for phones and venue audio).
  Rehearsal: 3 cameras + 16-channel venue feed + 3 encodes at 1080p30 used ~2.7 of 16 cores, 0 dropped frames, 0 audio dropouts.
  `create --size c-16 --image ubuntu-24-04-x64 --regions blr1,lon1 --ttl <min>` (the video profile becomes `cpu` automatically).
- ❌ **Never a shared-CPU droplet:** the 4-vCPU Basic rehearsal had 61% CPU steal and audio dropouts.
- ➖ GPU RTX 4000 Ada (8 vCPU + NVENC, $0.76/h, profile `gpu` 1080p60): sold out all day 17 Oct; NVENC still unproven.

## A. Before creating anything (free)
### Money and safety
- ✅ DigitalOcean token in `.env` (600); read-only checks pass.
- ✅ Region fallback; a full region refuses at no cost.
- ✅ Auto-destroy: `vn-ttl-<min>` tag + `vibenation-showserver-reaper` timer (every 5 min).
- ✅ The build server's `.env` stays here; the show server gets a filtered `.env` (`PORT`, `VN_*`, `LIVEKIT_*`, `GEMINI_*`).

### Topology (tonight)
- ✅ Phones → LiveKit on the **build server** (app.jeeznews.com, HTTPS). The show server's video service subscribes over the internet (`LIVEKIT_URL=wss://app.jeeznews.com`; Caddy forwards `/rtc*` and `/twirp/*`).
- ✅ Venue laptop → SRT **with passphrase** → show server UDP 9000 → audio engine (switches to the venue feed by itself).
- ✅ Web app (build server) → **SSH tunnel** → show server engines (audio :18091, video :18092). `create` connects; `destroy` disconnects.
- ✅ The tuned mix (`data/mix_state.json`) is copied to the show server.

### Software on the show server
- ✅ Audio packages pinned (`services/audio/requirements.txt`); Python 3.12 checked.
- ✅ Video service installed + `video-check.txt`; two start-up bugs fixed (appsinks `async=false`, compositors `start-time-selection=first`).
- ✅ Every camera at full resolution (sharp cuts); phones send video only. The stream's audio comes only from the mixer.

### Mix ready
- ✅ Listener (Gemini 3.8 Flash, billing on): verdicts every 20 s, matching the engine's vocal detection. It handles events only, not levels.
- ✅ Claude's mixer judges only music that is playing; the drums are always in its report.
- ✅ Arrangement follower: lead/backing vocals, solos, auto-mute (vocal mics: 5 min).
- ⏳ **Listening pass by the user** on the real band tonight (soundcheck).

## B. Tonight (in this order)
1. ⏳ **Venue laptop:** Apps → Venue laptop (MR18) → download → `setup.bat` (early: the ffmpeg download can take 20 min) → put the show server IP in `sender.ini` → `run.bat` → "CONNECTED".
2. ⏳ **YouTube:** Keys → Client ID + secret (the **!** guide) → Go Live → Connect YouTube. Check live streaming is enabled on the channel.
3. ⏳ **Start the show server** (Go Live), about 15 min before soundcheck. Note the IP for `sender.ini`.
4. ⏳ **Soundcheck:** the band plays; the engine re-measures trims; listen on phone and headphones.
5. ⏳ **Private test stream** first (Go Live → "Start a private test stream"), then go live.

## C. After every show
- Stop the show server (Go Live), or `showserver.py destroy`. Then `status` shows "No show server running".
- Check the DigitalOcean dashboard for no `vibenation-show` droplet.
- Report the time used and the cost.
