# Vibration menu

A public menu page plus a password-protected, mobile-first editor for it.

Change a price on your phone, hit Save, and the live menu shows the new price on
the next load. No rebuild and no redeploy — menu content lives in Netlify Blobs,
not in the code.

## Routes

| Route              | Access        | What it is                                    |
| ------------------ | ------------- | --------------------------------------------- |
| `/`                | Public        | The menu diners see                           |
| `/admin`           | Password      | The editor                                    |
| `/api/menu`        | Public        | Menu as JSON, used by the public page          |
| `/api/admin/login` | Public (POST) | Exchanges the password for a session cookie   |
| `/api/admin/menu`  | Session       | Reads and writes the menu                     |

## How the password protection works

Netlify's built-in site password covers the *whole* site, which would lock out
your customers along with everyone else. So protection is scoped to the editor
instead:

- `ADMIN_PASSWORD` is a Netlify environment variable, never stored in the repo.
- `/api/admin/login` compares the submitted password in constant time and, on a
  match, sets an HTTP-only, `Secure`, `SameSite=Strict` session cookie signed
  with HMAC-SHA256. Sessions last 12 hours.
- Every `/api/admin/*` request revalidates that signature and expiry. Writes
  additionally require an `X-Requested-With` header, which a cross-site form
  post cannot set.
- Failed logins are counted per IP in Blobs: 10 failures locks that IP out for
  15 minutes.

The `/admin` HTML itself is a static shell and is served to anyone who asks for
it, but it contains no menu data — every byte of content comes from the
authenticated API. It is also marked `noindex`.

Changing `ADMIN_PASSWORD` invalidates all existing sessions when `SESSION_SECRET`
is unset, since the signing key is then derived from the password.

## Setup

Set these on the Netlify site (Site configuration → Environment variables):

| Variable         | Required | Notes                                             |
| ---------------- | -------- | ------------------------------------------------- |
| `ADMIN_PASSWORD` | Yes      | The editor password                               |
| `SESSION_SECRET` | No       | Cookie signing key; `openssl rand -hex 32`         |

## Editing the menu

Open `/admin`, sign in, and you get every section and item as a card:

- **Price, name, and description** edit in place. Prices are free text, so `14`,
  `9 / 12`, and `market price` all work. A bare number gets the currency symbol
  prefixed automatically on the public page.
- **Available** toggles an item to "Sold out" — it stays listed but struck
  through, which is usually what you want mid-service rather than deleting it.
- **↑ ↓ ✕** reorder and delete sections and items.
- **Paste a menu in** takes a whole menu at once:

  ```
  ## Cocktails
  Old Fashioned | 14 | Bourbon, bitters, orange
  Negroni | 13

  ## Small Plates
  Olives | 5
  ```

  Lines starting with `##` are section headings; everything else is
  `Name | price | description`, with price and description optional. This
  replaces the whole menu, so you are asked to confirm.

Nothing is written until you press **Save**. The bar at the bottom tells you
whether you have unsaved changes, and leaving the page with unsaved edits prompts
first.

If someone else saved the menu from another phone while you had it open, your
save is refused rather than silently overwriting their work, and you are told to
reload.

## Local development

```bash
npm install
cp .env.example .env    # fill in ADMIN_PASSWORD
npx netlify dev
```

## Fallback behaviour

If the Blobs store is empty or unreachable, `/api/menu` serves the bundled
fallback in `netlify/lib/seed.mjs`. That fallback deliberately contains no items
— a menu with placeholder prices on it is worse than one that says it is being
updated. Once you save from `/admin`, the stored menu always wins.
