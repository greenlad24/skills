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
- The app is called "Vibe Nation". (Sunrise Jam is the band/show; Vibe Nation is the product.)
