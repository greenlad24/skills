# WhatsApp Cloud Scheduler

A **self-hosted** service for scheduling WhatsApp messages. Compose a message now,
pick a send time, and the server delivers it later — even while your phone is
asleep. Everything runs on **your** machine or server; your data never leaves it.

There are **two ways to schedule a message**:

1. **The web app (installable PWA)** — a small WhatsApp-styled site you open in any
   browser on iPhone, Android, or desktop, and can "Add to Home Screen" so it
   behaves like a native app.
2. **In-chat `/schedule` commands** — type a command like
   `/s tomorrow 18:00: don't forget the milk` directly inside a real WhatsApp
   chat, and the linked server picks it up and schedules it for you.

---

## Providers: `personal` vs `business`

The service can send through one of two back-ends, chosen with the `WA_PROVIDER`
environment variable.

| | `personal` | `business` |
|---|---|---|
| Library / API | `whatsapp-web.js` (WhatsApp Web) | Official WhatsApp **Business Cloud API** |
| How it links | Scan a **QR code** (Linked Devices) | API credentials (token) |
| Who you can message | **Anyone**, free-form text | Within Cloud API rules (templates / 24h window) |
| Cost | Free | Metered by Meta |
| In-chat `/schedule` commands | ✅ Supported | ⚠️ Needs a webhook receiver (inbound is a no-op) |
| Terms of Service | ⚠️ **Against WhatsApp's ToS** | ✅ Sanctioned by Meta |
| Best for | Personal use, testing, low volume | Production, businesses, compliance |

> ### ⚠️ Warning — automating a personal number can get it banned
> The `personal` provider drives WhatsApp Web with an unofficial library.
> **Automating a personal WhatsApp number violates WhatsApp's Terms of Service and
> can get the number permanently banned.** If you use `personal`:
> - Use a **dedicated or secondary number**, never your main one.
> - Keep the **volume low** and the messages human-like.
> - Understand you are accepting the risk. For anything serious, use `business`.

---

## Local setup

Requirements: **Node.js >= 18**.

```bash
# 1. Get the configuration file
cp .env.example .env
#    ...then edit .env (at minimum pick WA_PROVIDER and set TZ)

# 2. Install dependencies
npm install

# 3. Start the server
npm start

# 4. Open the web app
#    http://localhost:3000
```

For development with auto-restart on file changes: `npm run dev`.

### Key environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `3000` | HTTP port |
| `HOST` | `0.0.0.0` | Bind address (`127.0.0.1` for local-only) |
| `TZ` | — | Timezone for all scheduling, e.g. `Europe/London` |
| `DATA_DIR` | `./data` | Where messages + session are stored |
| `WA_PROVIDER` | `personal` | `personal` or `business` |
| `WA_CHROME_PATH` | — | Path to Chromium (optional; set in Docker) |
| `API_TOKEN` | — | Bearer token to protect the API (set on public IPs) |
| `WA_PHONE_NUMBER_ID` | — | *business* — sender Phone Number ID |
| `WA_ACCESS_TOKEN` | — | *business* — access token |
| `WA_API_VERSION` | `v21.0` | *business* — Graph API version |

See `.env.example` for the full, commented list.

---

## Connecting your WhatsApp

### Personal provider (QR)

1. Start the server and open the web app.
2. It shows a **QR code** (the same code is also printed in the terminal).
3. On your phone: **WhatsApp → Settings → Linked Devices → Link a Device**, then
   scan the QR.
4. Once linked, the web app switches to the composer automatically. The session
   is saved under `DATA_DIR`, so you normally only scan once.

### Business provider (Cloud API)

Set these three variables in `.env` (from Meta / Facebook Developers) and restart:

```env
WA_PROVIDER=business
WA_PHONE_NUMBER_ID=your_phone_number_id
WA_ACCESS_TOKEN=your_access_token
WA_API_VERSION=v21.0
```

There is no QR to scan; the app reports connected once both the ID and token are
present.

---

## Deploying to your own server (Docker)

The repo ships a `Dockerfile` (Node 20 + Chromium) and a `docker-compose.yml`.

```bash
cp .env.example .env      # configure first
docker compose up -d      # build + run in the background
```

The compose service:
- builds the image from `.`,
- reads config from `.env`,
- maps port **3000:3000**,
- mounts **`./data`** so your messages and WhatsApp session survive restarts,
- restarts automatically (`unless-stopped`).

### Put it behind HTTPS

Expose the app through a **reverse proxy** (nginx, Caddy, Traefik) that terminates
**TLS/HTTPS** and forwards to the container's port. Installable PWAs and the QR
scan flow work best over HTTPS.

> ### 🔒 Set `API_TOKEN` whenever the port is public
> If the port is reachable from the internet, **anyone who finds it could send
> messages as you**. Set a long random `API_TOKEN` in `.env`. The API then
> requires `Authorization: Bearer <token>` on every `/api/*` call, and the web app
> prompts you for the token on first load (it is stored in your browser).

---

## Using the web app

1. **Recipient** — enter the number in international format, e.g. `+447911123456`.
2. **Message** — type your text.
3. **When** — pick a date and time. The field is pre-filled with a sensible
   suggestion (about an hour from now, rounded to the next 5 minutes).
   - **Weekend suggestion:** if it's currently Saturday or Sunday, a banner
     appears with a **"Use Monday"** button that sets the time to **Monday 09:00**.
4. Choose an action:
   - **Schedule** — queues the message for the chosen time.
   - **Send now** — schedules and fires it on the next tick.
5. **Manage list** — scheduled messages appear newest-first with a status badge
   (`pending`, `sent`, `failed`, `canceled`). Each row offers **Cancel**,
   **Send now**, and **Remove**.

---

## Using in-chat `/schedule` commands

You can also schedule straight from a WhatsApp chat by sending a message **to
yourself** in that conversation (personal provider). Trigger words, case-
insensitive, at the start of the message: **`/schedule`**, **`/sched`**, or
**`/s`**.

**Grammar:**

```
<trigger> <when...> [to <number>] : <message>
```

The **colon** separates the schedule spec from the message text. If you include
`to <number>`, that's the recipient; otherwise the message goes to **the chat you
typed the command in**.

**Examples:**

```
/s monday 9am to +447911123456: Standup
/s tomorrow 18:00: don't forget the milk
/schedule 2026-07-28 09:00 to +44...: Payroll reminder
/sched in 2 hours to +447911123456: Call the plumber
```

The second example (no `to`) schedules the reminder inside the recipient's own
chat. The server replies with a confirmation (`✅ Scheduled for …`) or a helpful
error (`⚠️ …`).

**Supported `when` formats** (all in the server's `TZ`):

| Form | Examples |
|---|---|
| Relative | `in 30 mins`, `in 2 hours`, `in 3 days` |
| Tomorrow / today | `tomorrow 9am`, `today 21:00` |
| Weekday | `mon`, `monday 9:30am`, `fri 0900` (next future occurrence) |
| ISO-ish | `2026-07-28 09:00`, `2026-07-28T09:00` |

Times accept `9`, `9am`, `9:30am`, `21:00`, or `0900`. If you give only a day,
the time defaults to **09:00**.

> Note: in-chat commands are a `personal`-provider feature. The `business`
> provider would need an inbound **webhook** receiver to support them.

---

## How weekend detection works

When you open the composer (or ask the API for a suggestion), the server checks
the current day in its timezone:

- **Weekday** → it suggests roughly **now + 1 hour** (rounded up to the next 5
  minutes).
- **Saturday or Sunday** → it detects the weekend and instead suggests the
  **upcoming Monday at 09:00**, with a short reason so the web app can show the
  "Use Monday" banner.

You can always override the suggestion and pick any future time.

---

## Data storage & keeping the server running

- Scheduled messages are stored as **JSON** (`messages.json`) under `DATA_DIR`
  (default `./data`). With Docker this is bind-mounted to `./data` on the host, so
  it **stays on your server** and survives restarts.
- The personal provider's WhatsApp session also lives under `DATA_DIR`
  (`wwebjs_auth`), so you don't re-scan every time.
- **The server must stay running to send.** A scheduler loop wakes periodically
  and delivers any messages whose time has arrived. If the process is stopped when
  a message is due, it will send as soon as the server is running again and the
  next tick reaches it — so keep the service up (that's what Docker's
  `restart: unless-stopped` is for).
