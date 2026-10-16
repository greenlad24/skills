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
