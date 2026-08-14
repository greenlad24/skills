# Vibration Poster Studio

A local poster designer + social scheduler for **Vibration**, the live music bar.
Runs entirely on your own computer — no server, no deployment. Your API keys and
all images stay in the app's `data/` folder on your machine.

Every week you build five posters (Tuesday → Saturday):

1. **Performers** — upload the photo(s) of the singer/band/objects for the day. Faces are
   preserved with high input fidelity.
2. **Style** — pick one of your signature Vibration looks (extracted from your own past
   posters), or type a keyword and search **Pinterest** for fresh style references, or upload
   your own reference image.
3. **Details** — headline, genre line, time line, what's special, and any words that *must*
   appear on the poster (spelling is reproduced exactly).
4. **Generate & pick** — the app generates **3 art-directed variations** (Faithful /
   Recomposed / Type-forward) with OpenAI `gpt-image-1` at the highest quality, portrait
   format. Click your favourite to crown it the winner.
5. **Captions & schedule** — captions for Instagram and Facebook are written **in your own
   voice** (teach it once via 🎙 Voice → paste your past captions). Then, from the Week
   overview, one click schedules the whole week to Instagram + Facebook — each poster goes
   out on its own day at your chosen time. Scheduling works through **Buffer (free plan)**
   by default, or **Postiz** if you prefer (switch in Settings).

---

## One-time setup (Windows)

> The app opens a **built-in setup wizard** on first launch that walks through all of this
> interactively (reopen anytime with 🧭 Setup). **SETUP.md** in this folder is the full
> step-by-step manual with click paths and troubleshooting.

1. Install **Node.js LTS** from <https://nodejs.org> (just click Next-Next-Finish).
2. Double-click **`start.bat`** in this folder. Your browser opens the studio at
   `http://localhost:5713`. (No `npm install` needed — the app has zero dependencies.)
3. Open **⚙ Settings** in the app and fill in:
   - **OpenAI API key** — from <https://platform.openai.com/api-keys>. Your OpenAI
     *organization must be verified* to use `gpt-image-1` (Settings → Organization → Verify).
   - **Buffer (free)** — create an account at <https://buffer.com> and connect your
     Instagram account (must be an Instagram *professional/business* account linked to your
     Facebook page — free to switch in the Instagram app) and your Facebook page. The free
     plan includes 3 channels. Then generate an API key under **Buffer → Settings → API**.
     Note: Buffer's public API is currently in beta.
   - **Cloudinary (free, needed for Buffer)** — Buffer downloads images from a URL, so the
     app publishes each winning poster through a free Cloudinary account: sign up at
     <https://cloudinary.com>, then Settings → Upload → Upload presets → *Add upload preset*
     → Signing mode **Unsigned** → Save. Put your **cloud name** and **preset name** in the
     app's settings. (Free tier is ~25GB/month; a week of posters is ~15MB.)
   - Or pick **Postiz** in the Settings dropdown instead — get an API key in Postiz under
     Settings → Public API. Works with Postiz cloud or self-hosted (set the base URL to
     `https://your-postiz-domain/api/public/v1`). Postiz accepts direct uploads, so no
     Cloudinary is needed.
   - Either way, click **"Load my channels"** in the app's settings and press
     "→ Instagram" / "→ Facebook" next to the right ones.
   - Upload your **circular V logo** (transparent PNG is best) — it is attached to every
     generation so the badge comes out exact.
4. Open **🎙 Voice**, paste 5–15 of your favourite past captions separated by `---`, and click
   **Learn my voice**.

That's it. Every following week is just: upload photos → pick styles → type details →
generate → pick → schedule.

## Costs to expect

- `gpt-image-1` at *high* quality, portrait: roughly **$0.25 per image → ~$0.75 per day,
  ~$3.75 per full week** (3 variations × 5 days). Drop "Poster quality" to *medium* in
  Settings while experimenting, and switch to *high* for the final runs.
- Captions cost fractions of a cent.

## Notes & troubleshooting

- **Instagram cropping** — posters are generated at 1024×1536 (2:3). The design prompt keeps
  all text inside the central 4:5 safe area, so Instagram's crop never cuts your copy.
- **Pinterest search** uses Pinterest's public endpoints from your machine; if Pinterest
  changes something and search fails, you can always upload a reference image or paste any
  image URL instead — generation quality is identical.
- **Buffer scheduling** uses their GraphQL API (<https://developers.buffer.com>) with a
  personal API key: posts are created with `mode: customScheduled` and `dueAt` set to your
  per-day post time, so Buffer publishes them automatically. Instagram direct scheduling
  requires an Instagram professional account.
- **Postiz scheduling** uses the public API (`/integrations`, `/upload`, `/posts`) with your
  key in the `Authorization` header; its create-post endpoint is rate-limited (~90
  requests/hour) — a full week is only ~10 requests. Docs: <https://docs.postiz.com/public-api>.
- **Where is everything stored?** `data/db.json` (settings, weeks, captions) and
  `data/files/` (all images). Back up that folder and you've backed up everything. It is
  git-ignored, so keys never end up in the repository.
- The generated posters keep their full prompt in `data/db.json`, so you can inspect what
  was asked and iterate.

## Project layout

```
server.js            zero-dependency HTTP server (Node 18+)
lib/prompt.js        the brand system + style presets + 3 creative takes
lib/openaiClient.js  gpt-image-1 generation, caption/voice models
lib/pinterest.js     keyword → style reference search
lib/buffer.js        Instagram/Facebook scheduling via Buffer (GraphQL API)
lib/imagehost.js     free public image hosting (Cloudinary) for Buffer posts
lib/postiz.js        alternative scheduler: Postiz (direct upload, no Cloudinary)
public/              the studio UI
assets/style-presets your past posters, used as style anchors
```
