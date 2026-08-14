# Vibration Poster Studio — Step-by-Step Setup (Windows)

> 💡 The app shows this same guide as a **built-in setup wizard** the first time you open
> it (and anytime via the **🧭 Setup** button) — you can follow it there and paste keys as
> you go. This file is the offline reference with extra detail.

Follow these once, top to bottom. After that, your weekly routine is just:
upload photos → pick styles → type details → generate → pick → schedule.

---

## Part 1 — Install Node.js (5 min)

Node.js is the engine that runs the app. No coding involved.

1. Go to <https://nodejs.org>
2. Click the big green **LTS** download button.
3. Run the downloaded installer. Click **Next** on every screen (defaults are fine) → **Install** → **Finish**.

## Part 2 — Install the app (2 min)

1. Unzip **vibration-poster-studio.zip** to a permanent folder, e.g. `C:\VibrationStudio`.
   (Right-click the zip → **Extract All…** → choose the folder.)
2. Open the folder and double-click **`start.bat`**.
   - A black console window opens — **leave it open**, that's the app running.
   - Your browser opens `http://localhost:5713` with the studio.
   - If Windows shows a "SmartScreen" or firewall prompt, click **More info → Run anyway** /
     **Allow**. The app only listens on your own computer.
3. To stop the app, close the black window. To start it again, double-click `start.bat`.

> Everything you create is saved in the `data` folder next to `start.bat`.
> Copy that folder somewhere safe = full backup.

## Part 3 — Image engine key (OpenAI GPT Image 2) (10 min)

GPT Image 2 is the default engine — it's the class of model the original posters were made
with (exact faces from your photos, clean stylized typography), at ~$0.03–0.06 per image
(a full week ≈ $1–3):

1. Sign up / log in at <https://platform.openai.com>.
2. **Billing:** gear icon → Billing → add a payment method and ~$5 of credit.
3. **Verify your organization:** Settings → Organization → Verification → follow the ID
   check. Required for image models — without it generation fails.
4. **Create the key:** <https://platform.openai.com/api-keys> → Create new secret key →
   copy the `sk-…` key.

> **Want a $0 option?** Switch the engine to **Cloudflare Workers AI** in Settings — every
> free Cloudflare account gets 10,000 AI neurons/day (Account ID from the dashboard URL,
> API token via profile → API Tokens → "Workers AI" template). Honest expectation: it's
> draft quality — faces come out similar-but-not-identical and stylized text often needs
> retries. Good for exploring layouts, not for finals.
> Other alternatives in Settings: Gemini nano-banana (~$0.04/img) and Segmind (~$0.04/img,
> $10 min top-up). A free Gemini key (<https://aistudio.google.com/apikey>) also writes
> captions at $0 if you skip OpenAI entirely.

## Part 4 — Prepare Instagram & Facebook (10 min)

Automatic posting only works with an Instagram **professional** account linked to a
Facebook **Page**. Both are free.

1. **Facebook Page**: if the bar doesn't have one yet — on Facebook, Menu → **Pages** →
   **Create new Page**, name it (e.g. "Vibration"), done.
2. **Instagram professional account**: in the Instagram app → your profile → menu (≡) →
   **Settings and activity** → **Account type and tools** → **Switch to professional
   account** → choose **Business**. Nothing changes visually except you get insights.
3. **Link them**: Instagram profile → **Edit profile** → **Page** → connect your Facebook
   Page (or on Facebook: Page → Settings → **Linked accounts** → Instagram → Connect).

## Part 5 — Buffer account (does the actual posting) (10 min)

1. Go to <https://buffer.com> → **Get started for free** → sign up.
   The free plan includes 3 connected channels — you need 2.
2. Connect your channels: **Channels** → **Connect channel**:
   - **Instagram** → follow the login flow → pick your professional account.
   - **Facebook** → **Page** → pick the bar's Page.
3. Get your API key: click your avatar (top right) → **Settings** → **API** (sometimes
   under "Beta features") → **Generate API key** → copy it.

## Part 6 — Cloudinary account (free image hosting for Buffer) (5 min)

Buffer downloads each poster from a web address, so the app needs a place to put the image.
A free Cloudinary account handles this invisibly.

1. Go to <https://cloudinary.com> → **Sign up for free** (no card needed).
2. After login, note your **Cloud name** — it's shown on the dashboard (a short word like
   `dq2abcxyz`).
3. Create an *unsigned upload preset*:
   - Click the gear icon (**Settings**) → **Upload** tab → scroll to **Upload presets** →
     **Add upload preset**.
   - Set **Signing mode** to **Unsigned**. Leave everything else as-is → **Save**.
   - Note the preset's **name** (e.g. `ml_default` or the one you created).

## Part 7 — Configure the app (5 min)

Back in the studio (`http://localhost:5713`):

1. Click **⚙ Settings** (top right) and fill in:
   - **Image engine** → Google Gemini, and paste the **Gemini API key** from Part 3.
   - **Scheduling service** → Buffer, and the **Buffer API key** from Part 5.
   - **Cloudinary cloud name** + **Cloudinary upload preset** → from Part 6.
   - **Default post time** → when each day's post should go live (e.g. 17:00).
   - If you deployed to Netlify: set **Bar's UTC offset** (e.g. `+07:00`) so post times mean
     your local time.
2. Click **Load my channels** → your Instagram and Facebook appear → click
   **→ Instagram** next to the Instagram channel and **→ Facebook** next to the Page.
3. **Upload your logo**: in the "Brand logo" section, upload your circular V logo
   (a PNG with transparent background works best). This makes the badge on every
   generated poster come out exact.
4. Click **Save settings**.

## Part 8 — Teach it your caption voice (5 min, once)

1. Click **🎙 Voice** (top right).
2. Open your Instagram and copy 5–15 of your favorite past captions.
3. Paste them into the box, separated by a line with just `---` between captions.
4. Click **Learn my voice**. From now on all captions are written in your style.

## Part 9 — Your first week (the fun part)

1. The app opens on the upcoming week (Tue–Sat). Use ‹ › at the top to change weeks.
2. Click a day tab, then work down the numbered steps:
   1. **Performers** — upload the singer/band photos for that day.
   2. **Style** — click one of your signature looks, or type a keyword (e.g.
      "vintage jazz poster gold") and press **Search Pinterest**, then click a result
      to use it as the style reference.
   3. **Details** — headline (artist name), genre line, time line, what's special,
      and any words that must appear.
   4. **Generate & pick** — press **✨ Generate 3 variations** (takes 1–3 minutes —
      you can switch to another day meanwhile). Click **Pick this one** on your favorite.
      Not happy? Change details/style and generate again — old ones stay below.
   5. **Captions** — press **📝 Write captions**, tweak the text if you like.
3. Repeat for all five days.
4. Go to **Week overview** → check all days show ✓ → press **📅 Schedule all ready days**.
5. Verify in Buffer (Publishing → Queue) that all 10 posts sit at the right dates/times.
   Done — they'll post automatically, even if your PC is off.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Browser shows "can't connect to localhost:5713" | The black console window isn't running — double-click `start.bat`. |
| Cloudflare generation fails with a quota/neuron error | You used the day's 10,000 free neurons — they reset at 00:00 UTC. Switch to the klein 4B model for cheap drafts, or wait for the reset. |
| Cloudflare posters misspell a word | FLUX models are good-not-perfect at stylized text — regenerate that variation (each retry is free), or switch the model to FLUX.2 dev, or use the Gemini engine (~$0.04/img) for headline-critical posters. |
| OpenAI engine fails with "organization must be verified" | platform.openai.com → Settings → Organization → Verification, wait ~15 min, retry. |
| OpenAI engine fails with "billing / quota" | Add credit on the OpenAI Billing page. |
| Pinterest search returns nothing | Pinterest occasionally blocks anonymous search — press **⬆ upload reference** instead and use any saved image; results are identical. |
| "Image hosting is not configured" when scheduling | Fill in the two Cloudinary fields (Part 6) in Settings. |
| Buffer error mentioning Instagram permissions | Make sure Instagram is a *professional* account linked to your Facebook Page (Part 4), then reconnect the channel in Buffer. |
| Posts didn't publish at the time set | Check the post inside Buffer → it shows the exact reason (e.g. Instagram disconnected — reconnect the channel). |
| Want to move to a new PC | Install Node, copy the whole app folder (including `data`), double-click `start.bat`. |
