# AutoUGC-TH — Frontend

Single-operator local web UI for the AutoUGC-TH pipeline. React 18 + TypeScript + Vite,
TanStack Query (server cache) + Zustand (UI state) + one multiplexed WebSocket for live job
state. Implements all seven screens from spec §7A.

## Quick start (dev)

```bash
cd frontend
npm install
npm run dev          # Vite dev server on http://localhost:3000
```

The dev server proxies `/api` and `/ws` to `http://localhost:8000` (the FastAPI backend),
so there are no CORS issues. Bring the backend up with `docker compose up` from the repo
root — until it's running, every screen degrades gracefully (empty states / "backend
unavailable", never a crash).

## Backend base URL configuration

By default the app talks to the **same origin** it's served from: `/api` for REST and
`/ws/jobs` for the socket. In dev, Vite's proxy forwards those to `localhost:8000`; in the
Docker image, nginx proxies them to the `api` service.

Override only if the API lives elsewhere. Copy `.env.example` → `.env`:

| Var | Purpose | Default |
|---|---|---|
| `VITE_API_BASE` | REST origin, e.g. `http://192.168.1.20:8000` | same-origin `/api` |
| `VITE_WS_BASE`  | WS origin, e.g. `ws://192.168.1.20:8000` | derived from page origin |
| `VITE_APP_PASSWORD` | Sent as `X-App-Password` header (and WS query param) when the backend sets `APP_PASSWORD` | empty |
| `VITE_API_TARGET` / `VITE_WS_TARGET` | Dev-only Vite proxy targets | `http://localhost:8000` / `ws://localhost:8000` |

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Dev server with HMR on :3000 |
| `npm run build` | Type-check (`tsc -b`) + production build to `dist/` |
| `npm run preview` | Serve the built `dist/` on :3000 |
| `npm run typecheck` | Types only, no emit |

## Docker

```bash
docker build -t autougc-frontend ./frontend
docker run -p 3000:80 autougc-frontend
```

The image is a node build → nginx static serve. `nginx.conf` proxies `/api` and `/ws` to
the `api` service; integration wires the service into the root `docker-compose.yml`
separately (this module owns only `frontend/`).

## Architecture

```
src/
  api/
    types.ts     TS mirror of app/core/schemas.py + the §7A.10 REST/WS contract
    client.ts    one typed fetch client, one function per documented endpoint
    ws.ts        single multiplexed WebSocket (/ws/jobs), auto-reconnect + resubscribe
    queries.ts   TanStack Query hooks — the single server-cache source of truth
  hooks/
    useJobStream.ts   folds every WS event into the Query cache + cost header chip
  store/
    uiStore.ts   Zustand — local UI state only (cost chip, wizard step, caption draft, toast)
  components/    Header, Layout, StateBadge, ProgressBar, Modal, EmptyState
  pages/
    SetupWizard.tsx  Screen 1 — 6-step first-run wizard
    Dashboard.tsx    Screen 2 — job list, state badges, cost, approval-pinned rows
    NewVideo.tsx     Screen 3 — URL form + WS live-progress stepper
    Approval.tsx     Screen 4 — the compliance-gated approval screen (core UX)
    Library.tsx      Screen 5 — swipe library + templates + proxy caveat
    Analytics.tsx    Screen 6 — winner dashboard + template leaderboards
    Settings.tsx     Screen 7 — providers / budget / compliance / claims / seeds / account
```

### State model (§7A.9)

- **Server state → TanStack Query.** All entity data is fetched and cached by Query.
- **Real-time → one WebSocket.** `useGlobalJobStream()` (mounted at the app root) subscribes
  to all jobs and calls `queryClient.setQueryData` for each event, so the dashboard and
  progress views update live without polling. Per-screen `useJobStream(jobId)` surfaces
  artifacts/errors for the live-progress and approval views.
- **Polling fallback.** If the socket drops, the jobs query keeps a 15s refetch interval so
  the UI stays correct until reconnect.
- **UI state → Zustand.** Only ephemeral things: the live cost chip, wizard step, unsaved
  caption draft, toast.

### Compliance hard gate (§7A.4)

The Approve button is physically `disabled` until `job.compliance.all_green`. If the backend
still rejects (`POST /api/jobs/{id}/approve` → **409**), the client shows the block toast and
does not advance. No override in v1.
