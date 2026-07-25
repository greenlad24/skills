# WhatsApp Cloud Scheduler — Build Contract (authoritative)

A self-hosted service that schedules WhatsApp messages. Two entry points:
1. **PWA web app** (works on iPhone/Android/desktop, installable).
2. **In-chat commands** — type `/schedule …` in any real WhatsApp chat and the
   linked server schedules it.

Two interchangeable send back-ends selected by env `WA_PROVIDER`:
- `personal` → **whatsapp-web.js** (QR-linked device; message any contact, free text).
- `business` → **WhatsApp Business Cloud API** (official; token-based).

## Hard rules for every agent
- **CommonJS only** (`require` / `module.exports`). Node **>= 18** (use global `fetch`, no node-fetch).
- **Do NOT run `npm install`, `npm test`, or any network/build command.** Validate JS syntax only with `node --check <file>`. The integrator installs deps and runs tests.
- **Create only the files assigned to your role.** Never edit another role's files.
- Match every shared contract below **exactly** (export names, API paths, JSON shapes, env names). These are the integration seams.
- Timezone: all wall-clock scheduling is in the **server's local time** (`TZ` env). Functions take an explicit `now` argument so they're testable.

## Data model — a scheduled message record
Stored as a JSON array in `data/messages.json`.
```js
{
  id: string,            // e.g. "m_<base36>"
  to: string,            // normalized digits, no '+', e.g. "447911123456"
  toDisplay: string,     // what the user typed
  text: string,
  when: number,          // epoch ms, send time
  status: "pending" | "sent" | "failed" | "canceled",
  provider: "personal" | "business",
  source: "web" | "chat",
  createdAt: number,
  sentAt?: number,
  failedAt?: number,
  error?: string
}
```

## server/schedule-logic.js — pure, dependency-free brain (Backend-core owns)
Export (CommonJS) exactly these:
- `isWeekend(date) -> boolean` — Sat(6) or Sun(0).
- `nextMonday(now, hour = 9, minute = 0) -> Date` — the upcoming Monday at that time strictly after `now` (if today is Monday and time already passed, next week; if today Monday and time still ahead, today).
- `suggestSendTime(now) -> { isWeekend: boolean, suggested: Date, defaultSend: Date, reason: string }` — `defaultSend` = now + 1h rounded up to next 5 min. If weekend, `suggested` = `nextMonday(now,9,0)` and `reason` explains it; else `suggested` = `defaultSend`, `reason` = "".
- `normalizePhone(input) -> { ok: boolean, value?: string, error?: string }` — strip `+`, spaces, dashes, parens; keep digits; require 8–15 digits; `value` = digits only.
- `toChatId(digits) -> string` — `\`${digits}@c.us\``.
- `parseWhen(input, now) -> Date | null` — parse human time. MUST support: `in <n> m|min|mins|h|hr|hour|hours|d|day|days`; `tomorrow [at] <time>`; `today [at] <time>`; weekday names `mon..sun` / full names, optional `[at] <time>` (next strict future occurrence); ISO-ish `YYYY-MM-DD[ T]HH:MM`. `<time>` accepts `9`, `9am`, `9:30am`, `21:00`, `0900`. If only a day is given, default time **09:00**. Return `null` if unparseable.
- `validateSchedule({ to, text, when }, now) -> { ok: boolean, errors: string[] }` — non-empty text, valid phone, `when` is a finite number strictly in the future.
- `parseChatCommand(body, now, opts = {}) -> { ok: boolean, error?: string, to?: string, toDisplay?: string, text?: string, when?: number }` — parse a chat command. Trigger words (case-insensitive) at start: `/schedule`, `/sched`, `/s`. Grammar: `<trigger> <when...> [to <number>] : <message>`. The colon separates schedule-spec from message. If `to <number>` is present, use it (via `normalizePhone`); otherwise use `opts.defaultChatNumber` (the chat the command was typed in). `when?` is epoch ms parsed via `parseWhen`. Return `ok:false` with a helpful `error` on any problem.

Also provide `test/schedule-logic.test.js` (node:test) covering: weekend→Monday, `nextMonday` edge cases, `parseWhen` for each supported form, `normalizePhone`, and `parseChatCommand` happy + error paths. Use fixed `now` values (e.g. a known Saturday and a known Wednesday) — never call `Date.now()` inside assertions.

## server/store.js — persistence (Backend-core owns)
JSON file at `data/messages.json`, created if missing. Atomic writes (write temp then `rename`), serialized through an internal promise mutex so concurrent writes don't corrupt. Export:
- `all() -> Promise<record[]>`
- `get(id) -> Promise<record|undefined>`
- `insert(record) -> Promise<record>`
- `update(id, patch) -> Promise<record|undefined>`
- `remove(id) -> Promise<boolean>`
- `makeId() -> string` (`"m_" + base36 time + random`)
Data dir path from env `DATA_DIR` (default `./data`).

## server/scheduler.js — the tick loop (Backend-core owns)
Export `start({ store, send, intervalMs = 15000 }) -> { stop() }`. Every tick: load `all()`, pick `status==="pending" && when <= Date.now()` not already in-flight; mark in-flight (in-memory Set); `await send(record)`; on success `update(id,{status:"sent",sentAt:Date.now()})`; on throw `update(id,{status:"failed",error:String(e.message||e),failedAt:Date.now()})`; always clear in-flight. `send(record)` is injected by index.js.

## server/providers/ — send back-ends (Provider agent owns)
`server/providers/index.js` exports `getProvider(env) -> provider` choosing by `env.WA_PROVIDER` (default `"personal"`). Every provider implements:
- `name: "personal" | "business"`
- `init() -> Promise<void>`
- `getStatus() -> { provider, connected: boolean, qr: string|null, me: string|null }` — `qr` is a data-URL PNG (personal, when awaiting scan) else null.
- `sendMessage(to, text) -> Promise<void>` — `to` = normalized digits; throw on failure.
- `onInboundCommand(handler)` — register `handler({ body, fromChatNumber }) -> Promise<string|null>`; provider invokes it for inbound command messages and, if a non-null string is returned, sends it back as a reply in that chat. Business provider may no-op this (document that inbound needs a webhook).

`personal.js` (whatsapp-web.js): `LocalAuth` with `dataPath` = `${DATA_DIR}/wwebjs_auth`. Puppeteer opts: `headless:true`, `args:['--no-sandbox','--disable-setuid-sandbox']`, and `executablePath: env.WA_CHROME_PATH` when set. Render `qr` events to a data-URL via the `qrcode` package; also print to terminal via `qrcode-terminal`. On `ready` set connected + `me`. On `message_create` where `msg.fromMe` and body trims to start with a trigger (`/schedule`,`/sched`,`/s` — case-insensitive), compute `fromChatNumber` from the chat id digits and call the handler; reply with its return value.

`business.js` (Cloud API): env `WA_PHONE_NUMBER_ID`, `WA_ACCESS_TOKEN`, `WA_API_VERSION` (default `v21.0`). `sendMessage` → `POST https://graph.facebook.com/{ver}/{phoneId}/messages` with bearer token, body `{ messaging_product:"whatsapp", recipient_type:"individual", to, type:"text", text:{ body:text, preview_url:false } }`; throw on non-2xx with response text. `getStatus` connected = both env present. `onInboundCommand` = no-op (comment: requires webhook receiver).

## server/index.js — Express server + REST API (Server+Frontend agent owns)
- Load env (`process.env`; a tiny inline `.env` reader is fine — do NOT add dotenv dep). Pick provider via `getProvider(process.env)`, `await provider.init()`.
- Create store; `scheduler.start({ store, send: (rec) => provider.sendMessage(rec.to, rec.text) })`.
- Register inbound handler:
  `provider.onInboundCommand(async ({ body, fromChatNumber }) => { parse via parseChatCommand(body, Date.now(), { defaultChatNumber: fromChatNumber }); if !ok return "⚠️ " + error; insert record {source:"chat",provider:provider.name,status:"pending",...}; return "✅ Scheduled for " + new Date(when).toLocaleString(); })`.
- **Optional auth**: if `env.API_TOKEN` is set, require header `Authorization: Bearer <token>` on all `/api/*` routes (401 otherwise). `GET /api/status` must still reveal only `{ authRequired:true }` shape enough for the UI to prompt — simplest: allow `/api/status` to return `{ authRequired:true, connected:false }` without token, protect the rest.
- Serve `public/` as static. Listen on `env.PORT||3000`, host `env.HOST||"0.0.0.0"`.
- **JSON API (all responses JSON):**
  - `GET /api/status` → `{ provider, connected, qr, me, authRequired }`
  - `GET /api/suggest` → `{ isWeekend, suggested:ISO, defaultSend:ISO, reason }` (from `suggestSendTime(new Date())`)
  - `GET /api/messages` → `{ messages: record[] }`
  - `POST /api/messages` body `{ to, text, when }` (`when` = ISO string or epoch ms) → validate via `normalizePhone` + `validateSchedule`; on ok insert `{source:"web",provider,status:"pending"}` and 201 `{ message }`; on error 400 `{ error }`.
  - `POST /api/messages/:id/send-now` → set `when=Date.now()` so the next tick fires it (or send immediately); return `{ message }`.
  - `POST /api/messages/:id/cancel` → set `status:"canceled"`; `{ message }`.
  - `DELETE /api/messages/:id` → `{ ok:true }`.

## public/ — PWA front-end (Server+Frontend agent owns)
Vanilla HTML/CSS/JS, no build step, no external CDNs. Files: `index.html`, `app.js`, `styles.css`, `manifest.webmanifest`, `sw.js`. Icons already exist at `public/icons/icon{16,48,128}.png`.
Behavior:
- On load call `GET /api/status`. If `authRequired` and no stored token, prompt for token (store in `localStorage`, send as `Authorization` header on all calls). If provider `personal` and `!connected`, show the **QR** (`status.qr`) with "Scan in WhatsApp → Linked devices"; poll `/api/status` every 3s until connected. If connected, show composer + list.
- Composer: recipient (tel, hint "international format e.g. +44…"), message textarea, `datetime-local`. Prefill datetime from `GET /api/suggest`. If `isWeekend`, show a banner with the `reason` and a **"Use Monday"** button that sets the datetime to `suggested`. Buttons **Schedule** (POST) and **Send now** (POST then send-now).
- List: `GET /api/messages` every 5s, newest send-time first; show to/text/when/status badge; **Cancel**/**Send now**/**Remove** actions. Style should echo WhatsApp (green `#00a884`), responsive, dark-mode aware. Must be installable: link `manifest.webmanifest`, register `sw.js` (cache app shell).

## Packaging (Packaging agent owns)
- `package.json`: `type:"commonjs"`, engines node>=18, scripts `start`/`dev`(`node --watch server/index.js`)/`test`(`node --test`), deps: `express`, `whatsapp-web.js`, `qrcode`, `qrcode-terminal`. No dotenv.
- `.env.example`: `PORT, HOST, TZ, DATA_DIR, WA_PROVIDER, WA_CHROME_PATH, API_TOKEN, WA_PHONE_NUMBER_ID, WA_ACCESS_TOKEN, WA_API_VERSION` with comments.
- `Dockerfile`: `node:20-slim`, install chromium + libs for puppeteer, `ENV PUPPETEER_SKIP_DOWNLOAD=true WA_CHROME_PATH=/usr/bin/chromium`, copy, `npm ci --omit=dev` (note: runtime only), expose PORT, `CMD ["node","server/index.js"]`.
- `docker-compose.yml`: one service, env-file `.env`, volume `./data:/app/data`, port mapping, restart unless-stopped.
- `.dockerignore` (node_modules, data), `.gitignore` (node_modules, data, .env).
- `README.md`: what it is; the personal-vs-business tradeoff and **ToS/ban warning** for personal; setup (env, `npm install`, `npm start`), Docker deploy to their server IP, scanning the QR, using the **web app**, using **in-chat `/schedule` commands** with examples, the weekend→Monday behavior, and security note about `API_TOKEN` on a public IP.

## Integration seams summary (so nothing drifts)
- `parseChatCommand`, `parseWhen`, `normalizePhone`, `validateSchedule`, `suggestSendTime` live in `schedule-logic.js` and are imported by `index.js` (and indirectly drive chat + web).
- Provider contract is the only coupling between send back-ends and the rest.
- API JSON shapes above are the only coupling between server and front-end.
