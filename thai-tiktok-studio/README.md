# Thai TikTok Studio

Two tools in one local Mac app, built for Thai TikTok Shop / affiliate product videos:

1. **Planner (Tool 1)** — paste a product **name, link or screenshot**. It scrapes the product, researches the product and its niche on the web, and writes **5 ranked viral Thai scripts**. Each script comes with a **Thai shot list** (what to film, how, and how long) and an exact **edit plan** (cuts, timing, captions, motion graphics).
2. **Auto-editor (Tool 2)** — drop all your clips and **your narration** into it and it renders **finished 9:16 videos**. Every video gets your own voice synced line by line, burned-in white Thai captions, animated stickers and text in 5 animation styles, a "กดตะกร้า" (tap the basket) arrow, zoom punch-ins, flashes and ducked background music. No sound effects. Prices are never shown in graphics.
   **The editor never calls an AI.** It follows the edit plan from Tool 1, so editing is free and unlimited.

Everything runs on your Mac. Nothing is uploaded anywhere, except the product research and script request sent to Claude or ChatGPT.

**Want it as a website instead (free)?** See **[DEPLOY.md](DEPLOY.md)**: a free Oracle Cloud server with 200 GB of storage, password-protected, usable from any phone or computer.

---

## Mac app (easiest)
1. Download **[ThaiTikTokStudio-mac.zip](releases/ThaiTikTokStudio-mac.zip)** and unzip it.
2. Drag **Thai TikTok Studio** into **Applications**.
3. The first time only: right-click the app → **Open** → **Open** (it isn't from the App Store).
4. The first launch sets itself up in 2–5 minutes. It installs Python if needed, with Thai/English dialogs. After that it opens in seconds, in its own window.

**Clips from an Android phone (or iPhone):** in tab 2, press **📱 ส่งไฟล์จากมือถือ** ("send files from phone") and scan the QR code with the phone. The phone must be on the same Wi‑Fi. Pick clips or narration from the gallery and they upload straight into the product at full original quality. The link is secret, works for 12 hours, and only reaches that one product's upload page.

Log file: `~/Library/Logs/ThaiTikTokStudio.log`. To rebuild the app after code changes, run `python mac/build_app.py`.

## Install & start from source (macOS 12+, Intel or Apple Silicon)

1. Get this folder onto the Mac: `git clone` the repo, or download the ZIP from GitHub and unzip it.
2. Double-click **`start.command`**.
   - If macOS blocks it: right-click → **Open** → **Open**. Or run `bash start.command` in Terminal.
   - First run: if Python 3.10+ is missing, the official installer downloads and opens. Finish it, then double-click `start.command` again.
   - The first run then installs everything (a few minutes). Later starts take seconds.
3. Your browser opens **http://127.0.0.1:8765**. Keep the Terminal window open while you work; close it to quit.

**Voice-over = your own voice** (default). Optional: to use a computer Thai voice instead, install **Kanya** (System Settings → Accessibility → Spoken Content → System Voice → *Manage Voices…* → Thai; older macOS: System Preferences), then pick "Computer Thai voice" in ⚙ Settings.

## Choose how scripts are written (⚙ Settings)

| Mode | Cost | What you do |
|---|---|---|
| **Your Claude account** (default) | Included in your Claude plan (Pro/Max/Team) | Run `claude setup-token` in Terminal and paste the token. Uses Claude Code in headless mode (needs macOS 13+, or use the website version). |
| **Claude API** | API usage only (a few cents–~$1 per product) | Paste an Anthropic API key. Runs `claude-opus-5-5` with live web search. |
| **ChatGPT** | API usage only | Paste an OpenAI API key (model configurable, default `gpt-5`). |
| **Free copy/paste** | $0 | The app builds one big prompt. Paste it into chatgpt.com or claude.ai with web search on, then paste the JSON answer back. |

## Workflow

**Tab 1 · Scripts & shot lists**
- Research summary: features, pain points, objections, niche trends, competitor hooks, compliance notes, sources.
- 5 videos, each with:
  - Rank and a virality score (7-criteria rubric)
  - Format and hook type
  - The full Thai script
  - The shot list
  - A compliance check that flags risky claims such as รักษา (treat), 100%, ดีที่สุด (the best), ถูกที่สุด (the cheapest) and การันตี (guarantee)
- **🖨 Filming pack (Thai)** is a printable page for the person filming.
- **Edit plan** lets you change any spoken line, caption, duration or graphic text, then save.

**Film.** Shoot vertical (9:16), in the order of the shot list. **No need to rename anything.** If you retake a shot, the last take is used.

**Record your narration.** For each voice-over video, read its lines (listed in the filming pack under 🎙) in one take, with a short pause between lines. It can be a video or an audio recording, e.g. you filming yourself on the phone.

**Tab 2 · Auto-edit videos**
1. **Drop all clips.** They're matched to shots by recording time (taken from the files' own metadata) and by type: talking clips go to talking shots, B-roll to B-roll, photos to photo shots. Background music (any audio file) is detected automatically.
2. **Drop your narration** in its own area. Its sound is extracted, split into lines at your pauses, and each line is placed exactly on its beat, with long pauses tightened. Narrations are assigned to videos in recording order, and you can change that.
3. **Check the matching.** Change any clip if needed.
4. **Pick an animation style** per video (bouncy, punchy, smooth, playful, minimal). 🎲 *New variation* re-rolls the motion within a style. *Versions per video* renders 2–5 versions with different styles for A/B tests.
5. **Render.** Finished MP4s (1080×1920, 30 fps, H.264/AAC) appear in the app and in the project's `renders` folder.

### What the editor does automatically
- **Cutting:** reframes any clip to 9:16, picks the part of the clip the plan asks for (start/middle/end), and adjusts speed. Short clips are stretched slightly, then frozen.
- **Talking clips:** silences are detected and removed as jump cuts, with alternating punch-ins.
- **Voice-over:** your narration is split into lines and each beat is timed to your voice, so captions and picture never drift. Optional: a computer Thai voice instead.
- **Motion graphics (19 types, ranked by how common they are in viral Thai TikTok Shop videos):**
  - Text: hook titles, word-highlighted captions, keyword pops, reaction text, speech bubbles, lower thirds
  - Deals and urgency: discount starbursts ("ลด 50%"), urgency banners. Prices are never shown in graphics; amounts like ฿199 or "199 บาท" are removed automatically.
  - Calls to action: the กดตะกร้า (tap the basket) pill, with an arrow pointing at the basket
  - Pointers and lists: arrows, ✅ checklists, numbered reasons, spec cards
  - Trust and proof: trust badges, star ratings, TikTok-style comment-reply cards
  - Comparisons: before/after labels, VS splits
  - Emoji stickers
  - All text is white and stays inside TikTok's safe zone.
- **5 animation styles** with different entrances (pop, drop-bounce, stamp, zoom-out, wipe, fade-up, swing, spin), exits and loops.
- **Camera effects:** punch-in, shake, flash, slow zoom, progress bar.
- **Missing shots** become labelled placeholder cards, so you can preview before you've filmed everything.

**Import your own top-video dataset.** In ⚙ Settings, import a CSV of top performers, e.g. your *Products & inspiration* sheet exported as CSV. The top 25 Thai videos, with their openers, shot mix and viewer notes, become live examples for every script.

## Where things are saved
`~/ThaiTikTokStudio/`
- `settings.json`
- `custom_examples.md`
- `projects/<product>/`
  - `plan.json`: the edit plan
  - `filming_pack.html`, `scripts.txt`, `research.md`
  - `footage/`, `narration/`, `renders/`

## Customize
- **`studio/frameworks/script_framework.md`:** formats, hooks, CTAs, pacing, compliance and the scoring rubric that the AI follows.
- **`studio/frameworks/motion_framework.md`:** the ranked motion-design elements and the density rules.
- **`studio/frameworks/compliance_th.json`:** the words the claim check flags.

Edit these text files and the next run uses them. No code changes needed.

## Tips
- iPhone: turn **HDR video off** (Settings → Camera → Record Video) or use *Most Compatible*. HDR clips can look washed out after export.
- **Quick draft** renders fast at lower quality for checking timing. Use **Render** for the final version.
- A 30-second video renders in roughly 1–3 minutes on a 2015 MacBook.

## Development
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q        # 20+ tests incl. full renders
.venv/bin/python -m studio.app       # dev server on :8765
```
Architecture: `studio/plan_schema.py` defines the edit-plan contract, which is the only thing Tool 1 and Tool 2 share. `studio/editor/` runs on ffmpeg (bundled via `imageio-ffmpeg`), with Pillow + libraqm for correct Thai text shaping and numpy for audio mixing.
