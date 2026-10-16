# VibeNation

Live show + multistream studio, run by Claude. See `../CLAUDE.md` for the brief and hard rules.

| Path | What |
|---|---|
| `apps/web` | Web app (React + Vite + TypeScript) |
| `apps/server` | API + live WebSocket (Fastify, TypeScript) |
| `packages/shared` | Shared types, channel list, colour tokens |
| `services/audio` | Mix engine + analysis (JACK/Carla, Python) |
| `apps/android` | Android camera app (Kotlin) |
| `apps/venue-sender` | Windows MR18 → SRT sender |
| `infra` | Build server + show server setup |

```bash
pnpm install
pnpm dev          # web on :5173 (proxies to server on :8080)
pnpm build && pnpm start   # serves the built web app from the server on :8080
```
