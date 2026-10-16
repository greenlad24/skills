# Design decisions made by the user (override research conventions)

- ON AIR / live = BLUE (program tile border, camera tally on phones, "LIVE" stream badge). Not red.
- ERRORS = RED (critical alerts, failures, disconnects). Red is reserved for problems only.
- Preview / next shot = GREEN (unchanged).
- Warnings = AMBER/YELLOW.
- Sidebar with all processes, collapsible to an icon rail.
- iPhone cameras: Safari web page; Android: native app. White balance/exposure locked per stream.
- Break screen: "We'll be back in…" countdown, default 15:00.
- Output 1080p60.

## Autonomy (user decision)
- The AI RUNS THE SHOW. Default mode = AUTO for everything (director, mixer, breaks, go-live/end, health recovery, post-show learning, server start/stop). Humans are observers who can override; manual/assist modes exist only as fallbacks.
- UI is therefore primarily a "watch + override" dashboard: show what the AI is doing and why (sidebar), with one always-visible "take manual control" button.

## Go-live (user decision)
- Default: the user TAPS a "Go Live" button (after the AI's pre-flight checks pass). Everything else stays automatic.
- The app connects automatically to the band's YouTube channel (OAuth) and checks for scheduled live streams (YouTube scheduled broadcasts). If one is scheduled, it binds the stream to that broadcast and STARTS IT AUTOMATICALLY at the scheduled time (rare case). Otherwise it creates the broadcast when the user taps Go Live.

## Name (user decision)
- The app is called "VibeNation" (one word, capital V and N). NO mention of "Sunrise Jam" anywhere in the app or its design docs. The band/show name, logo and colours on stream graphics are user settings (generic placeholders in designs). VibeNation has its own identity, not a band-derived "sunrise" brand.

## Override model (user decision, supersedes "take manual control")
- NO manual-control button. Engineer mode is the DEFAULT view.
- Any manual change (fader, EQ, cut, etc.) overrides the AI on that control for the REST OF THE STREAM. The AI only touches a human-held control if something radical happens (feedback, clipping, dead signal / emergency).
- Manual camera cuts are respected; the AI keeps directing from the shot the human picked.

## Program only, click-to-cut (user decision)
- No preview/next monitor and no Veto/Cut/Mix buttons. The Show screen has ONE picture: the live program.
- Clicking any camera tile puts it on air immediately; the AI keeps directing from the picked shot.
- The AI's next-shot reasoning lives in the sidebar ("Director is thinking") / backend, not as on-screen controls.
- Green "preview" colour is therefore no longer used on the Show screen.

## Phones (user decision)
- All phones broadcast HORIZONTALLY (landscape) only.
- The phone camera screen shows the FULL 16:9 image edge to edge with NOTHING overlaid, so each camera can be framed exactly; tally/status/locks live in the spare strip beside the image. Framing guides off by default.

## Visual direction
- "Warm studio glass": warm near-black with ember ambient glow, frosted-glass panels, 18–24 px radii, LED-segment meters, real fader caps, lilac gradient-edged Claude thinking card. Type: Sora / DM Sans / JetBrains Mono.
- Phone camera UI lives in a slide-out DRAWER (right edge). Closed: only the full image, a blue tally line in the left side bar and a small handle with a status dot. Open: ON AIR, camera name, WB/exposure, battery, temperature, Wi-Fi, bitrate, guides, hold-to-unlock.

## Auto YouTube package (user decision)
- At pre-flight Claude writes a click-optimised TITLE (plus ranked alternatives), an SEO DESCRIPTION (keywords, location, line-up, chapters added live as songs change) and TAGS.
- A THUMBNAIL is generated with OpenAI's GPT Image from a real live camera frame + title text, and attached to the live broadcast automatically (YouTube API thumbnails.set; needs a channel verified for custom thumbnails).
- All attached automatically at go-live; user can edit. Requires an OpenAI API key (ChatGPT plan does not cover API).

## Channel & location (user decision)
- YouTube channel: @MusicLiveLove ("Music Live Love").
- NEVER mention Thailand, Koh Samui, islands or any location — not in titles, descriptions, tags, thumbnails, slates or the app.
- Title style follows the channel: "Song – Artist | Live <Genre> Cover Band Arrangement (Not AI)"; live streams: "LIVE: Funk & Soul Cover Band — … | Real Musicians (Not AI)".

## Patterns adopted from user-supplied references (Boss RC-505, Dribbble audio-mixing search)
- Each channel in its own recessed "bay"; channel colour identity carried by a glowing numbered ring (RC-505).
- LCD-style display for the selected channel: big number + name + state (RC-505).
- Per-strip EQ/CMP/GT lamps that light when active; Solo/Mute on every strip; dB readout box; layer tabs (All 16 / CH 1–8 / CH 9–16 / Buses / FX returns); FINE fader mode (Audio Mixing Console Tablet App).
- Number-key shortcuts on camera tiles; stream health (Mbps, fps, CPU, dropped) in the top bar (Live Streaming Control Platform, 197 / 145k).
- From SplitEQ (user reference): numbered, colour-coded EQ bands with translucent per-band shapes over the analyser; FREQ/GAIN/Q table aligned under the curve; A (before) / B (Claude) compare; Pre/Post analyser toggle.
- From the A/B studio app (user reference): arc-ring knobs for dynamics and sends; glowing lock icon under faders held by the user; Claude change cards styled as a purple "magic edit" pop-over with action bar (time, before/after, undo, amount). (Show timeline was tried and REMOVED from the Show screen by the user; chapters are still generated automatically in the backend. A song timeline may live on a future after-show screen.)
- From viewer-side streaming references (user supplied): sidebar gets a Claude | Live chat tab switch; Claude reads YouTube chat only to FLAG song requests and shout-outs for the band (it never posts); likes shown next to viewers; one slate with three modes — Starting soon (countdown) / Break (15:00) / Thanks for watching (subscribe call). Related-videos / recent-streams grids are viewer features and are not used.
- Descriptions include NO community/Skool link (community closed). Only the subscribe link for @MusicLiveLove.

## Multistreaming (user decision)
- Stream simultaneously to YouTube, Twitch, Facebook, TikTok and Instagram. Each platform has its own CONNECT button on the Go Live screen (OAuth for YouTube/Twitch/Facebook; stream key for TikTok/Instagram).
- Two outputs: 16:9 1080p60 (YouTube ~9 Mbps; Twitch/Facebook ~6 Mbps, separate encode) and 9:16 vertical (TikTok 1080×1920, Instagram 720×1280) that Claude auto-reframes from the landscape cameras to follow the action.
- Constraints: TikTok needs LIVE access (~1,000 followers) and a stream key; Instagram needs a professional account and issues a new key per broadcast; Facebook streams to the Page. Claude writes a title/caption per platform. Chat from all platforms is merged in the sidebar with platform badges; Claude only flags requests/shout-outs.

## Effects (user decision)
- Engineer view channel panel has an EFFECTS section with Easy | Detailed tabs. Easy = six big macro knobs per channel: Compression, Reverb, Delay, Warmth, Presence, Width (each drives several parameters). Detailed = threshold/ratio/attack/release/sends + de-esser, saturation, gate.
- Effects rack screen: Reverb A (plate, vocals/horns), Reverb B (room, drums/percussion), tempo-synced Delay (follows detected BPM, ducks under vocal), Doubler/Chorus (keys/guitar, mono-safe). Each with presets, 4 knobs (e.g., decay, pre-delay, tone, mix), on/off and the list of channels sending to it.
- Every EQ display shows a LIVE spectrum (real-time analyser) of that channel: mini spectrum under the EQ curve on every strip, and a full live spectrum behind the bands in the selected-channel EQ.
