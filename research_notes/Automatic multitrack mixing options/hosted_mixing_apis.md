# Hosted APIs and services for automatic multitrack mixing (from stems)

Researched 18 Oct 2026. Official pages were used where they loaded. Third-party or vendor-marketing claims are flagged. Several services in the brief (BandLab, Moozix, Waves Online Mastering, sonible, iZotope SDK, Mixea) could not be verified within the tool budget; see the Gaps sections.

## 1. Which services accept 16 stems + a reference track and return per-stem settings or a mix?

### Takeaway
Only **RoEx Tonn API** is a verified, self-serve, documented developer API that takes 2–32 stems and returns a mix, processed stems, and/or per-stem settings (gain, pan, 6-band EQ, compressor). It has **no reference-track input for mixing**, and reference-matched mastering is listed as "Coming Soon". Music.AI resells RoEx mixing. Every other "stem mixing" product found (Cryo Mix, RoEx Automix web app, MixingMusic AI) is a consumer web app with no public mixing API. LANDR, Masterchannel, Dolby and Cryo Mix's white-label offer are **stereo mastering only**.

### Cited Findings
**RoEx Tonn API (tonn-portal.roexaudio.com)**
- Base URL `https://tonn.roexaudio.com`, auth via `X-API-Key` header. Multitrack mixing takes **2–32 tracks** per request in WAV/AIFF/FLAC (no MP3), **up to 8 min per track via the API (10 min in the C++ SDK)**. Mastering is limited to 10 min. Rate limit is 100 requests/min per key. Typical processing time is **under 60 s for mastering and 2–5 min for a multitrack mix** — [Tonn portal](https://tonn-portal.roexaudio.com/)
- Endpoints: `/mixpreview`, `/retrievepreviewmix`, `/retrievefinalmix`, `/masteringpreview`, `/retrievepreviewmaster`, `/retrievefinalmaster`, `/mixanalysis`, `/mixenhancepreview`, `/mixenhance`, `/retrieveenhancedtrack`, `/audio-cleanup`, `/upload`, plus `/postprod/*` (dialogue enhancement, delivery mastering, loudness check). The portal also lists `/separate`, `/retrievestems` and `/recombine` — [OpenAPI spec](https://tonn-portal.roexaudio.com/openapi.json); [Tonn portal](https://tonn-portal.roexaudio.com/)
- `/mixpreview` request: `trackData[]`, where each track has `trackURL`, `instrumentGroup`, `presenceSetting`, `panPreference` and `reverbPreference`. The request also takes `musicalStyle`, `returnStems` (default false), `sampleRate` (44100 or **48000**) and an optional `webhookURL` — [OpenAPI spec](https://tonn-portal.roexaudio.com/openapi.json)
- Settings model, as accepted by `/retrievefinalmix` per track and returned as `mix_output_settings`:
  - `gainDb`
  - `panning_settings.panning_angle` (−60…+60)
  - `eq_settings` with `band_1`…`band_6`, each having gain ±12 dB, q 0.1–10 and centre_freq 20–20000 Hz
  - `compression_settings` with threshold −60…0 dB, ratio 1–20, attack 0.1–100 ms and release 1–1000 ms

  FX settings come back when `retrieveFXSettings` is true, which costs credits. Because `/retrievefinalmix` accepts edited per-track settings, you can tweak the settings and re-render — [OpenAPI spec](https://tonn-portal.roexaudio.com/openapi.json)
- The FAQ describes a "settings-only" mode that returns gain/pan/EQ/compression for use in your own pipeline — [Tonn portal](https://tonn-portal.roexaudio.com/). The pricing page lists "Settings Only" as a separate product — [Pricing](https://tonn-portal.roexaudio.com/pricing)
- **Reference track:** no reference parameter appears in the visible API spec for mixing or mastering — [OpenAPI spec](https://tonn-portal.roexaudio.com/openapi.json). The getting-started page lists mastering "Match to Reference Track" as **(Coming Soon)** — [Getting started](https://tonn-portal.roexaudio.com/docs/getting-started). The only reference claim is "Pro only" in a competitor's table, and it refers to RoEx's consumer Automix web app, not the API — [Cryo Mix blog, 30 Apr 2026 (competitor)](https://cryo-mix.com/blog/posts/ai-mixing-and-mastering-in-2026-what-each-platform-actually-does-and-what-it-doesnt)
- A Python client exists (`roex-python` on PyPI) — [PyPI](https://pypi.org/project/roex-python/); [Getting started](https://tonn-portal.roexaudio.com/docs/getting-started)
- Older RoEx material cited 16 tracks (Mar 2025) and 8 tracks (Automix launch), so the current 2–32 figure supersedes both — [RoEx search summary / pricing](https://tonn-portal.roexaudio.com/pricing); [Music Week](https://www.musicweek.com/digital/read/tech-start-up-roex-unveils-ai-powered-music-mixing-tool-automix/088623)
- How it works: per RoEx, the model picks "volume, EQ, DRC, Panning, and Reverb based on the sonic characteristics of each submitted track/stem, their interplay, and the musical style". The product began as a PhD project at Queen Mary University of London — [RoEx: how Automix works](https://www.roexaudio.com/blog/how-roex-automix-works-under-the-hood); [Music Week](https://www.musicweek.com/digital/read/tech-start-up-roex-unveils-ai-powered-music-mixing-tool-automix/088623)

**Music.AI (formerly Moises API)**
- The modules page lists **"ROEX" AI multitrack mixing as a third-party module** alongside Music.AI's own stem separation — [Music.AI modules](https://music.ai/modules/)
- Pricing page, pay-as-you-go per audio minute:
  - "AI Stereo mixer (By RoEx)" $1.20/min ($1.14 on Professional)
  - "AI Mastering" $0.20/min
  - "Reference mastering" $0.02/min (a reference-matched *mastering* module, not mixing)
  - Audio mixer $0.005/min (likely a plain summing utility; unverified)

  — [Music.AI pricing](https://music.ai/pricing/)
- Masterchannel says Music.ai is one of its integration partners, so Music.AI's "AI Mastering" may be Masterchannel. This is unconfirmed — [Masterchannel blog](https://blog.masterchannel.ai/what-music-platforms-have-integrated-ai-mastering-from-masterchannel)

**Cryo Mix (cryo-mix.com)**
- Consumer web app with up to 32 stems, WAV/MP3/FLAC, up to 15 min, 44.1/48 kHz export, and reference tracks (Creator tier+). Relaunched Jan 2026 with a conversational assistant ("Nova") — [Cryo Mix blog (vendor)](https://cryo-mix.com/blog/posts/ai-mixing-and-mastering-in-2026-what-each-platform-actually-does-and-what-it-doesnt); [AI Music Preneur / roundup](https://music.loop.fans/ai/best-ai-mixing-and-mastering-tools)
- Its white-label "API and iframe" offer covers **AI mastering**, not stem mixing (directory listing and co-founder post; no public docs found). Developer contact: jannik@cryo-mix.com — [musictechnology.uk listing](https://musictechnology.uk/member/cryomix/)
- Per-stem "mix reports" log every processing decision (third-party review) — [callin.io](https://callin.io/ai-tools/cryo-mix/)

**LANDR**
- Has a Mastering API (stereo). Reported features are a GraphQL playground, OAuth, webhooks and a sandbox, per a competitor page. No published pricing: sales-quoted, no free tier, "from $2.50/track" according to an aggregator. All of this is **unverified** — [nemovideo (third-party)](https://nemovideo.com/alternative/landr); [CostBench (aggregator)](https://costbench.com/software/ai-music-apis/landr-api/)
- No stem mixing; reference mastering is a consumer feature — [Cryo Mix comparison (competitor)](https://cryo-mix.com/blog/posts/ai-mixing-and-mastering-in-2026-what-each-platform-actually-does-and-what-it-doesnt)

**Masterchannel**
- Stereo mastering via a licensing/white-label API, public since 2023. Integrated with Music.ai, amuse, Groover, GYROstream and TuneCore. It uses reinforcement learning. Partner contact: support@masterchannel.ai — [Masterchannel blog](https://blog.masterchannel.ai/what-music-platforms-have-integrated-ai-mastering-from-masterchannel); [Masterchannel history](https://blog.masterchannel.ai/how-masterchannel-as-a-mastering-service-has-evolved/)
- No stem mixing and no reference matching, per a competitor table — [Cryo Mix comparison](https://cryo-mix.com/blog/posts/ai-mixing-and-mastering-in-2026-what-each-platform-actually-does-and-what-it-doesnt)

**Dolby.io Music Mastering API**
- Launched Oct 2021, GA Mar 2022 — [Dolby news](https://news.dolby.com/en-WW/203113-dolby-upgrades-dolby-io-introduces-transcoding-music-mastering-and-more-to-developer-platform/); [Dolby changelog](https://docs.dolby.io/media-apis/changelog/2022-03-14-read-more)
- **Status in Oct 2026:** the Music Mastering guide URL now **301-redirects to `optiview.dolby.com/docs/`**, Dolby's streaming platform. The last Media API notice found is maintenance in Mar 2024 — [docs.dolby.io guide (redirect observed)](https://docs.dolby.io/media/docs/music-mastering-api-guide); [Dolby status](https://status.dolby.io/incidents/nq5zkfqxwt92). A third-party directory says Dolby.io consolidated into OptiView — [API Evangelist](https://providers.apievangelist.com/providers/dolby-io/)

**MixingMusic AI**
- Web app with up to 12 stems and genre presets. No API found — [mixingmusic.ai](https://mixingmusic.ai/en)

**Wondera**
- Markets an "AI auto-mixing API" ("send the stems, and our AI will balance, EQ, and master them", with custom parameters). The page returned 403 to us and there are no docs, pricing or launch date. This is **vendor marketing only** — [Wondera](https://wondera.ai/tools/en/ai-auto-mixing-api-platform)

**Sonetra AI Mixer (github.com/CryonicsX/Sonetra-AI-Mixer)**
- **Not a multitrack mixer.** It is a DJ-style song blender (beat/key detection, beat-matched transitions, crossfades). MIT license, 4 commits, README "Last Updated: January 2025", "not ready for production", 24 stars, no documented API — [GitHub repo](https://github.com/CryonicsX/Sonetra-AI-Mixer)
- The same account's other pinned repos are Spotify fake-stream bots, a Discord spammer, a Gmail account creator and a captcha solver. Treat it as untrustworthy — [GitHub CryonicsX](https://github.com/CryonicsX)

### Inferences
- For 16 stems + a reference track, no verified hosted API does both. RoEx takes the 16 stems and returns settings; reference matching would have to happen in our own pipeline (e.g. Music.AI "Reference mastering" on the stereo bus, or our own matching EQ).
- RoEx's settings schema is plain gain / pan angle / 6 parametric EQ bands / one compressor per track, which maps directly to LSP/x42 plugins in Carla. Settings-only is therefore the useful mode for us.
- RoEx offers `instrumentGroup`, `presenceSetting`, `panPreference` and `reverbPreference` as per-track inputs. These are hints we can drive from our channel list. Note that RoEx's mix includes reverb decisions, but the returned settings schema has no reverb field (only gain/pan/EQ/comp were seen in the spec).

### Gaps
- RoEx enum values for `instrumentGroup`, `presenceSetting` and `musicalStyle` were not captured (the spec is 148 kB; only the first 100 kB was read).
- Whether Music.AI's "AI Stereo mixer (By RoEx)" takes multitrack stems or is a stereo mix-enhance product is unclear from the pricing page.
- No public mixing API was found for BandLab/Cakewalk, Moozix, Waves Online Mastering (consumer stereo mastering) or Mixea. These were not verified in this pass.

## 2. Exact costs to mix ~20 songs/month; free credits

### Takeaway
RoEx: 20 songs cost about **$20–25/month in settings-only mode**, **$40–50 for full rendered mixes**, and adding a RoEx master is +$35–44. Previews are free. Prepaid credits last 12 months with no subscription. Music.AI's RoEx mixer is per minute, so 20 × 5-min songs is about $120. There is no meaningful free tier for multitrack mixing anywhere.

### Cited Findings
- RoEx credit packs: Small $10 = 1,000 credits ($0.010/credit), Medium $45 = 5,000, Large $80 = 10,000 ($0.008/credit). Credits are valid 12 months, non-refundable, with no subscription and optional auto top-up — [RoEx pricing](https://tonn-portal.roexaudio.com/pricing)
- RoEx per-song costs:
  - Mix full track 250 credits ($2.50 / $2.00)
  - **Mix settings only 125 credits ($1.25 / $1.00)**
  - Processed stems 50 credits ($0.50 / $0.40)
  - Mastering full track 220 credits ($2.20 / $1.76)
  - Mix analysis 10 credits ($0.10 / $0.08)
  - Mix enhance 250 credits
  - Stem separation 75 credits
  - 30 s previews free while the balance is positive

  — [RoEx pricing](https://tonn-portal.roexaudio.com/pricing)
- Free credits conflict: the portal home says "approved accounts start with 1,000 credits" — [Tonn portal](https://tonn-portal.roexaudio.com/); the pricing page lists no free signup credits — [RoEx pricing](https://tonn-portal.roexaudio.com/pricing)
- RoEx enterprise: custom pricing for more than 500 mixes/masters per month — [RoEx (search summary of pricing page)](https://tonn-portal.roexaudio.com/pricing)
- Music.AI: pay-as-you-go plan at $0 with 48 h storage and 2 concurrent jobs. Professional is $25/month with $25 credit ("limited offer"). AI Stereo mixer (RoEx) $1.20/min, AI Mastering $0.20/min, Reference mastering $0.02/min — [Music.AI pricing](https://music.ai/pricing/)
- Consumer prices for comparison (vendor/competitor sources):
  - Cryo Mix: Essential $19/month (5 credits), Creator $24/month (10), Pro $39/month (30)
  - RoEx Automix web app: from $5.99/credit or Pro $14.99/month (16 channels free, 32 on Pro)

  — [Cryo Mix comparison](https://cryo-mix.com/blog/posts/ai-mixing-and-mastering-in-2026-what-each-platform-actually-does-and-what-it-doesnt)

### Inferences
- Calculations:
  - 20 settings-only mixes × 125 = 2,500 credits/month, which is $25 at the Small rate or $20 at the Large rate
  - 20 full mixes = 5,000 credits, which is $40–50
  - A $80 Large pack covers about 80 settings-only mixes, i.e. 4 months at 20/month
- Live use is not one call per song, but if Claude asked RoEx for fresh settings on, say, a 5-min snapshot per set change, a 3-hour show with ~10 calls would cost about $10–12.50.
- The 8-min per-track API limit means a live show would have to be sent in short chunks.

### Gaps
- No verified free or research/non-commercial access for RoEx. Its portal says applicants need a commercial use case.
- No public pricing for LANDR API, Masterchannel API or Cryo Mix white-label.

## 3. Terms: commercial use of outputs, data retention, training on our audio

### Takeaway
RoEx claims no ownership of our content or outputs, but its API is commercial-only and grants itself rights to listen to and modify our audio "for … improving our Services". It does not explicitly rule out training. Music.AI explicitly does **not** train on customer content without opt-in, but its license is for "internal business" use, and it may keep anonymized data indefinitely.

### Cited Findings
- RoEx API Terms:
  - §5 "RoEx does not claim any ownership rights in your submitted Content and Output"
  - §5 RoEx may "host, share, listen to, and modify your Content and Output for the purpose of fulfilling and improving our Services"
  - §4 forbids *us* from using the Services to "train artificial intelligence"
  - §2 limited, revocable, non-transferable license; returned data may be displayed only in our own app/site
  - No retention period stated

  — [RoEx API Terms](https://tonn-portal.roexaudio.com/api-terms)
- RoEx: direct-upload "Files are automatically cleaned up after processing" — [Getting started](https://tonn-portal.roexaudio.com/docs/getting-started). The API is "for commercial use only; applicants need a clearly defined commercial use case" — [Tonn portal](https://tonn-portal.roexaudio.com/)
- Music.AI Terms:
  - §7(c) the license "DOES NOT INCLUDE ANY RIGHTS FOR US TO USE YOUR CUSTOMER CONTENT TO TRAIN OR FINE-TUNE ARTIFICIAL INTELLIGENCE" without written authorization or opt-in
  - §7(a) may use content "to improve or develop our products and services"
  - §7(d) Music.AI owns derived "Usage Data"
  - §4(d) use "solely for your own internal business or individual purpose"
  - §4(e) no competing product, no training on outputs
  - §7(b) may delete content at any time and may retain "indefinitely in anonymized form"
  - The ownership wording for outputs is garbled

  — [Music.AI Terms](https://music.ai/terms/)

### Inferences
- Streaming a RoEx-mixed show publicly appears compatible with RoEx's terms (we keep rights in the output). Music.AI's "internal business purpose" wording is ambiguous for public broadcast output and should be confirmed with sales.
- For privacy, RoEx's "improving our Services" clause means we should assume our stems could be listened to and used internally. Ask RoEx for written no-training confirmation if that matters.

### Gaps
- Not checked: RoEx privacy policy / Security & Data Handling page, LANDR/Masterchannel API terms.

## 4. Anything that runs locally or in real time

### Takeaway
**The RoEx Tonn C++ SDK** is the only verified local engine. It does 2–32-track mixing that returns settings and stems, plus mastering, on Linux x86_64/macOS/Windows, fully offline. However, the current page calls it "offline, deterministic processing", not real-time, and licensing is by quote only. Every hosted API found is offline/batch only (minutes per song). Plugin "assistants" (iZotope Neutron, sonible smart:) run locally but are DAW plugins without a published automation API.

### Cited Findings
- RoEx SDK:
  - Mixing 2–32 tracks with automatic gain/pan/EQ/compression, settings export, processed stems and style presets
  - Mastering with LUFS target, multiband, limiting
  - "Offline, deterministic processing"
  - macOS arm64/x86_64, Windows x64, **Linux x86_64**; C++17 + CMake
  - Licensed per feature (`MIXING`, `MASTERING`, `POST_PRODUCTION`); commercial license and evaluation license on request via info@roexaudio.com; no published price

  — [RoEx SDK page](https://tonn-portal.roexaudio.com/sdk)
- The June 2025 early-access announcement claimed "low-latency" and "built for real-time or batch workflows", running "fully offline". This conflicts with the current page's "offline" framing — [RoEx SDK early access blog](https://www.roexaudio.com/blog/roex-sdk-automated-multitrack-mixing-early-access)
- iZotope licenses its algorithms "as a plugin or SDK" for embedded/mobile/game use (general background, secondary source). Neutron's Mix/Track Assistant recommends starting points inside the plugin — [Wikipedia: iZotope](https://wikipedia.com/wiki/Izotope); [Sound On Sound](https://www.soundonsound.com/node/4914770)
- sonible smart:EQ 4 / smart:filter balances spectra across tracks and buses (retail description); no API found — [Music Store listing](https://www.musicstore.com/en_OE/EUR/Sonible-smart-EQ-4-License-Code/art-PCM0017947-000)

### Inferences
- The realistic use for VibeNation is **offline "settings snapshots"**. Record 1–5 min of the 16 raw channels at soundcheck or per line-up change, send them to RoEx settings-only (2–5 min turnaround), and have the deterministic controller apply the returned gain/pan/EQ/comp to Carla smoothly. This fits the "unnoticeable moves on line-up changes" preference. It is not a real-time mixer.
- The RoEx C++ SDK on the Linux show server would remove upload latency and per-call cost, but it needs a negotiated license. Worth an email if the hosted settings prove good.
- Dolby's API is effectively gone and LANDR/Masterchannel are stereo mastering only, so none of them helps with stem mixing.

### Gaps
- Not verified: actual SDK latency/CPU figures, whether it can run on short rolling windows, and whether the SDK has a Linux ARM build.
- No independent quality evaluation of RoEx (or any API) was found; all quality claims are vendor-sourced. A blind A/B on the band's 4 Apr 2026 stems would be the way to judge.
- sonible and iZotope: no developer/SDK pages were fetched. Plugin-hosting either in Carla on Linux is unlikely (both are Windows/macOS plugins); unverified.
