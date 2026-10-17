# Show server: checklist before every test

The GPU show server costs about **$0.76/hour while it exists** (powered off still bills; only *destroy* stops it).
Claude does not run `showserver.py create` until every item in **A** is ticked and the user has said "go" for this run.

Status as of 17 Oct 2026. ✅ done · ❌ to do · ➖ not needed for the first test

## A. Before creating anything (free)

### Account and money
- ✅ DigitalOcean token in `vibenation/.env` (600, vibe only); read-only API checks pass.
- ✅ No show server already running (`showserver.py status`).
- ✅ Price confirmed from the API: $0.76/h. First test budget: **≤ 1.5 h ≈ $1.15**.
- ✅ Region fallback: tries tor1, nyc2, atl1, ric1, sfo3, mkc1, mem1. A full region refuses at no cost.
- ✅ **Auto-destroy safety net.** Each show server is tagged `vn-ttl-<min>` (`--ttl`, default 120). The `vibenation-showserver-reaper` timer on the build server runs every 5 minutes and destroys any show server past its limit, even if Claude's session or the script has died. For real shows, set `--ttl` to the show length plus 1 hour.

### Secrets
- ✅ **The build server's `.env` stays here.** The rsync skips it; the show server gets a filtered `.env` (only `PORT`, `VN_*`, `LIVEKIT_*`, `GEMINI_*`, mode 600). Tested: the DigitalOcean token, YouTube, OpenAI and other keys are not sent.
- ✅ No GitHub credentials go to the show server (code is pushed over SSH).
- ✅ SSH key: `~/.ssh/vibenation_show` is created and registered on first `create`.

### Code and services the show server needs
- ✅ `provision.sh` and `cloud-init.yaml` pass syntax checks.
- ✅ The show server's unit files drop `User=vibe` and point at `/opt/vibenation` (it has no vibe user).
- ✅ mod-host patched to listen on 127.0.0.1 only.
- ✅ Our LV2 plugins (`/usr/local/lib/lv2`) are copied over.
- ✅ **Audio Python packages:** pinned in `services/audio/requirements.txt` (the build server's versions, including `samplerate` and `ai-edge-litert`), tested in a fresh venv. Provisioning stops early if the GPU image isn't Python 3.12 / Ubuntu 24.04; the image doesn't state its version.
- ❌ **Video service is not set up on the show server:** no venv (`livekit`, `pillow`, `aiohttp` + system GStreamer), no `vibenation-video` service, no fonts check.
- ❌ **LiveKit config:** `provision.sh` expects `/etc/livekit.yaml`, but nothing sends it.
- ❌ **Test audio:** the 4 April stems are not copied over, and `VN_STEMS` still points at `/home/vibe/...`.
- ❌ **Dry run on this server first:** run the video service here with the CPU profile and the fake cameras, so the GPU hour only tests the GPU.

### Mix ready (on this server, before paying for a GPU)
- ❌ **Listener on:** `GEMINI_API_KEY` in `.env`. Without it the listener is off ("off (no Gemini key)") and Claude mixes from the meters only, with no ears.
- ❌ **Listener verdicts flowing:** while the stems play, a verdict (vocal / harsh / low end / solo / balance) arrives every few seconds, and Claude's mixer moves reference them.
- ❌ **Claude calls from the web app work as vibe** (the mixer loop and director). Not yet tested since the move.
- ❌ **Listening pass on the demo:** a full song from the 4 April stems sounds right to the user on phone speakers and headphones (vocal on top, no harshness, bass audible on a phone). Note what's wrong, fix it, and play it again.
- ✅ Loudness target −16 LUFS / −1 dBTP in the mastering chain.

### Network
- ✅ Firewall on the show server: 22, 7881/tcp, 7882/udp, 9000/udp.
- ❌ **Venue feed (9000/udp) has no SRT passphrase.** Before the real venue test, add one or keep 9000 closed. For the first test: keep it closed.
- ➖ DNS `show.jeeznews.com`: only needed for the venue laptop and phones (later test).

## B. The test run (costs money)
1. `showserver.py create --retry 180`: waits for a free GPU, creates, provisions. **Note the start time.**
2. **NVENC:** `nvenc-check.txt` says the 1080p60 test encode is OK. If not, destroy straight away and report.
3. **Audio:** the engine plays the stems at −16 LUFS on the show server (meters move, no xruns in 2 minutes).
4. **Video:** the program output runs at 1080p60 plus 9:16 720×1280 with the fake cameras. Record the GPU/CPU load and dropped frames.
5. **Output:** a private test encode to a local file (no live platform) for 2 minutes, then check its length, fps and bitrate.
6. Write down the results: what passed, what failed, the load figures and how long each step took.

## C. After every test
- `showserver.py destroy`, then `showserver.py status` shows **"No show server running"**.
- Check in the DigitalOcean dashboard that no droplet tagged `vibenation-show` remains.
- Report the actual time used and the cost to the user.
- The auto-destroy timer stays on; with no show server running it does nothing (`journalctl -u vibenation-showserver-reaper`).
