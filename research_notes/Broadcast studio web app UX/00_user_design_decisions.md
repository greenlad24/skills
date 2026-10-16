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
