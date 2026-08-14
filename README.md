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

## What the editor can change

**In the menu, text only.** Photography, layout, fonts, the number of pages,
entry types and page order are fixed. **Live Shows is fully editable**, including
images.

- **Cover** — tagline and footer
- **Sections** — title and subtitle
- **Item pages** — eyebrow, name, story, build, serve, price
- **Back covers** — kicker, quote, attribution, fine print
- **List pages** — eyebrow, title, category headings, and each row's name, price
  and size

The editor navigates like the app: a list of sections, each tapping through to
its own page rather than expanding in place.

The menu restriction is enforced on the server, not just hidden in the UI. `applyTextEdits()`
walks the *stored* menu and copies across only whitelisted text fields, so a
malformed or hostile payload cannot add, remove or reorder pages, change an entry
type, or point an image somewhere else. Anything omitted keeps its current value.

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

Set `ADMIN_PASSWORD` with **all** scopes. Setting it scoped to `functions` alone
has repeatedly failed to persist through the Netlify MCP connector.

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
