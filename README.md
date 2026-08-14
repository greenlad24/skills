# Vibration menu

The Vibration menu book, plus a password-protected editor for its text.

The public menu is the original single-file design, unchanged: a cover screen
with the gold wordmark, five section cards, then full-screen swipeable pages —
hero photography, eyebrow, italic name, story / build / serve, and the THB price,
with back covers and two-column list pages.

Changing a price takes a few seconds on a phone and goes live immediately. No
rebuild, no redeploy.

## Routes

| Route              | Access        | What it is                                  |
| ------------------ | ------------- | ------------------------------------------- |
| `/`                | Public        | The menu book                               |
| `/admin`           | Password      | The text editor                             |
| `/api/menu`        | Public        | Menu JSON, fetched by the menu              |
| `/api/admin/login` | Public (POST) | Exchanges the password for a session cookie |
| `/api/admin/menu`  | Session       | Reads the menu and saves edits              |
| `/api/admin/upload`| Session       | Uploads a poster, returns its URL           |
| `/api/admin/extract`| Session      | Reads event details off an uploaded poster  |
| `/api/img/:key`    | Public        | Serves an uploaded image                    |

## Live Shows

A `Live Shows` card sits above Food on the cover screen. It opens a scrollable
schedule — eyebrow, month heading, one card per event (date, name, genre), then
the weekly entertainment block and a footer line. Tapping an event opens its own
page: the poster, then title, date, genre and description, swipeable between
events exactly like the menu pages.

Unlike the menu, Live Shows is **fully editable**: events and weekly slots can be
added, renamed, reordered and deleted, and posters are uploaded from the editor.

Uploads go to Netlify Blobs and are served from `/api/img/<hash>`. The key is a
SHA-256 of the bytes, so re-uploading the same image reuses it and the URL can be
cached forever. The type is sniffed from the file's magic bytes rather than
trusted from the client, and only JPEG, PNG and WebP under 8MB are accepted.

### Adding a month of posters at once

**Live Shows** has a drop zone: drag in a week's or a month's posters, or tap it
to pick them. Each poster is uploaded, then read for the act, date and genre, and
becomes a draft event you review before saving. A poster that can't be read still
becomes an event with its poster attached — you just fill in the fields. Dropping
anywhere else on the page is ignored rather than opening the file, so unsaved
edits survive a near miss.

Reading the poster is a Groq vision call with a JSON schema, so the response is
always the right shape, and it runs on Groq's free tier. Without `GROQ_API_KEY`
the endpoint reports itself unconfigured: the batch add still works, minus the
auto-fill. There is no second provider and no paid fallback — a poster Groq
cannot read is one you fill in yourself.

The model is `qwen/qwen3.6-27b`, the one Groq documents for image input. Groq
retires image model IDs, so the code carries two further names and falls through
to them rather than going dark until someone redeploys; `GROQ_MODEL` pins one and
skips the list. Whether the model accepts a JSON schema is worked out once and
remembered, so only the first poster of a batch can pay for finding out, and the
free tier's rate limit is retried once — a month of posters goes through in one
pass. Posters small enough are sent inline; larger ones are sent as an
`/api/img` URL, which Groq accepts up to 20 MB.

Facts are transcribed, never invented — an act, a date or a genre that is not on
the poster comes back empty. The description is the exception: that is written
rather than read, as copy meant to make someone want to come, built only from
what the poster actually shows.

Dates are taken as printed. "SAT 22 AUG", "22/08", "August 22nd" all resolve, and
a date with no year resolves forward rather than into the past. A poster naming
only a weekday — "FREESTYLE FRIDAY, 9PM–LATE" — is a weekly night: it is dated to
the coming Friday and marked **Weekly**, which means it rolls on to next week
instead of dropping off the schedule. The switch is on the event screen, so any
show can be made recurring by hand.

A run has its own panel rather than a toast: a bar showing how far along it is,
and a line per poster saying what happened to that one — uploading, reading,
waiting out a rate limit with the seconds counted, then either what was found
(act, date, and whether it repeats) or why it could not be read, in Groq's own
words. The log stays on screen after the run until you close it, since the whole
point is being able to read back what happened while you were not watching.

## What the editor can change

**In the menu, text and visibility.** Photography, layout, fonts, the number of
pages, entry types and page order are fixed. **Live Shows is fully editable**,
including images.

- **Cover** — tagline and footer
- **Sections** — title and subtitle
- **Item pages** — eyebrow, name, story, build, serve, price
- **Back covers** — kicker, quote, attribution, fine print
- **List pages** — eyebrow, title, category headings, and each row's name, price
  and size

The editor navigates like the app: a list of sections, each tapping through to
its own page rather than expanding in place.

### Showing and hiding

Every section, every page and every line on a list carries a **Shown / Hidden**
switch. Hiding is not deleting: the page stays in the editor, dimmed, and one tap
puts it back — which is what "the snapper is off tonight" actually needs.

Hidden things are removed from `/api/menu` itself, so they never reach a diner's
browser. A category whose lines are all hidden disappears rather than printing a
heading over nothing, and a section whose pages are all hidden disappears rather
than opening an empty book. Live Shows has the same switch.

The menu restriction is enforced on the server, not just hidden in the UI. `applyTextEdits()`
walks the *stored* menu and copies across only whitelisted text fields plus the
visibility flag, so a malformed or hostile payload cannot add, remove or reorder
pages, change an entry type, or point an image somewhere else. Anything omitted
keeps its current value.

Prices are free text — `160`, `240<span class="bar">|</span>1100` and
`Chicken 120 / Shrimp 150` all work. `THB` is added by the page.

Nothing saves until you press **Save**. If someone else saved while you had the
menu open, your save is refused rather than silently overwriting them.

## How the password protection works

Netlify's built-in site password would lock out diners too, so protection is
scoped to the editor:

- `ADMIN_PASSWORD` is a Netlify environment variable, never in the repo.
- `/api/admin/login` compares it in constant time and sets an HTTP-only,
  `Secure`, `SameSite=Strict` cookie signed with HMAC-SHA256. Sessions last 12h.
- Every `/api/admin/*` request revalidates signature and expiry; writes also
  require an `X-Requested-With` header a cross-site post cannot set.
- 10 failed logins from one IP locks it out for 15 minutes.

The `/admin` HTML is a static shell containing no menu data, and is `noindex`.

With `SESSION_SECRET` unset the signing key is derived from the password, so
changing the password invalidates every existing session.

## Setup

| Variable         | Required | Notes                                    |
| ---------------- | -------- | ---------------------------------------- |
| `ADMIN_PASSWORD` | Yes      | The editor password                      |
| `SESSION_SECRET` | No       | Cookie signing key; `openssl rand -hex 32` |
| `GROQ_API_KEY`   | No       | Reads posters automatically, on Groq's free tier |
| `GROQ_MODEL`     | No       | Pins one Groq vision model instead of auto-picking |

Set `ADMIN_PASSWORD` with **all** scopes. Setting it scoped to `functions` alone
has repeatedly failed to persist through the Netlify MCP connector.

## Storage, and moving hosts

Every read and write goes through `netlify/lib/blobs.mjs` — three named stores
(menu, images, login attempts) behind four calls: `getJSON`, `setJSON`,
`getFile`, `putFile`. Nothing above that module mentions a host, and the
contract deals in `Uint8Array` rather than `Buffer` so it stays true on a
runtime with no Node globals.

Blobs is a service, not a setting, so no environment variable can repoint it at
Cloudflare KV or anywhere else. Rewriting that one file can. What would still
need doing on a move: `netlify.toml`'s headers become the new host's equivalent,
and the daily prune's `schedule` becomes its cron trigger.

## Images

The original inlined every photo as base64, so the page shipped 3.8 MB before it
could render. They are now real files in `public/img` referenced by path —
identical output, but cached properly and small enough that the editor loads and
saves in a moment rather than moving megabytes.

Rendering was verified by screenshotting the original file and this build at the
same viewport: the PNGs are byte-identical on both the cover and an item page.

## Local development

```bash
npm install
cp .env.example .env    # fill in ADMIN_PASSWORD
npx netlify dev
```

## Fallback

If the Blobs store is empty or unreachable, `/api/menu` serves the menu bundled
in `netlify/lib/seed.mjs`. Once saved from `/admin`, the stored copy always wins.
