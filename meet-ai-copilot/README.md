# Meet AI Copilot

A private, real-time meeting copilot for **Google Meet**, built as a Chrome
extension (Manifest V3). It reads Meet's own live captions locally, and when a
question is aimed at you — or there's a moment worth adding to — it quietly
drafts a ready-to-say answer with the Claude API and shows it in a floating
panel only you can see.

Think of it as a Granola-style assistant that *actively answers* instead of just
taking notes — without a bot joining the call.

---

## Please read first: consent & recording law

Transcribing a conversation is regulated in many jurisdictions — two-party-consent
US states, GDPR in the EU, and others. This tool runs **locally on your machine**,
captures Meet's on-screen captions (nothing extra is recorded), and adds nothing
the other participants can see. That is not the same as legal cover. **Get consent
where it's required.** The extension is deliberately built as a personal assistant,
not a covert surveillance tool: it doesn't join the call, doesn't upload audio, and
doesn't exfiltrate anything except the transcript text you choose to send to the
Claude API.

---

## How it works (and why it's cheap)

```
Google Meet live captions (free, no speech-to-text bill)
        │  DOM MutationObserver on the caption region
        ▼
Local heuristic filter  ── drops the obvious non-events (no API cost)
        │  a question / hand-off / something you could elaborate on
        ▼
Haiku 4.5 "gate"  ── one cheap word: RESPOND or SKIP  (skipped for direct questions)
        │  RESPOND
        ▼
Sonnet 5 answer  ── streamed, first-person, 1–3 sentences
        │
        ▼
Floating panel in your browser (private to you)
```

Four cost levers, in order of impact:

1. **Captions, not audio.** Meet already transcribes the call. We read that text —
   zero speech-to-text cost. (An optional tab-audio path is described in
   `docs/ARCHITECTURE.md` for when captions aren't available, but it's off by
   default.)
2. **Local pre-filter.** Regex/second-person/hand-off detection throws away most
   lines before any API call.
3. **Two-tier models.** A cheap Haiku pass decides whether the pricier model runs.
   Direct questions to you skip the gate for speed.
4. **Prompt caching + streaming + tight `max_tokens`.** The stable system prompt is
   cached; answers stream so they appear in a few hundred ms.

**Typical spend: ~$1.50–$2.00 per 30-minute meeting** with 8–10 relevant
questions on the recommended Haiku-gate → Sonnet-5-answer setup. Switch the answer
model to Haiku for near-free, or to Opus/Fable for maximum quality.

---

## Install (unpacked)

1. Clone or download this folder.
2. Open `chrome://extensions` in Chrome (v116+).
3. Turn on **Developer mode** (top right).
4. Click **Load unpacked** and select the `meet-ai-copilot/` folder.
5. Click the extension's toolbar icon → paste your **Anthropic API key**
   (from console.anthropic.com) and your **display name in Meet**. Open **More
   settings** to add an "About you" profile — this is what makes the drafted
   answers sound like you and get the facts right.

## Use

1. Join a Google Meet call.
2. Turn on captions (the **CC** button) — or leave "Auto-enable captions" on and the
   extension clicks it for you.
3. The panel docks bottom-right and shows a green dot when it's live. When someone
   asks you something, a suggested answer streams in. Copy it, riff on it, or ignore
   it. You can also type a question into the panel to ask Claude about the meeting
   directly.
4. Toggle the panel with the toolbar icon's **Show / hide panel** button.

---

## Settings

| Setting | What it does |
|---|---|
| API key | Your Anthropic key. Stored in `chrome.storage.local`, this browser only. |
| Your name in Meet | Distinguishes your lines from everyone else's. |
| About you | Context injected into the prompt so answers are accurate and in-voice. |
| Answer model | Sonnet 5 (default), Haiku 4.5, Opus 4.8, or Fable 5. |
| Cheap gate | Haiku decides whether to answer. Big cost saver — leave on. |
| Auto-suggest | Also chime in on things you could elaborate on, not just questions. |
| Auto-enable captions | Clicks Meet's CC button when captions are off. |
| Min seconds between paid calls | Throttles spend; direct questions bypass it. |
| Transcript context | Rolling window of characters sent to Claude. Smaller = cheaper. |

---

## Privacy & data flow

- **Audio is never recorded or uploaded.** Only Meet's caption text is read.
- The transcript text (trimmed to your context window) and your "About you" profile
  are sent **only** to `api.anthropic.com`, and only when a call is actually made.
- The API key lives in `chrome.storage.local` and is used **only** from the
  extension's background service worker — it is never exposed to `meet.google.com`'s
  page scripts.
- Nothing is sent to any third-party server. There is no backend.

---

## Limitations & notes

- Meet changes its DOM often. The capture layer anchors on stable ARIA roles and
  re-attaches every 2 seconds, but a major Meet redesign can still require a tweak
  to `content/transcript-capture.js`.
- Caption quality is Meet's ASR quality — it can lag or drop words under load.
- Speaker attribution comes from Meet's caption labels; set **Your name in Meet**
  exactly as Meet shows it.
- This is a personal-use tool loaded unpacked; it isn't hardened for the Chrome Web
  Store review process.

See `docs/ARCHITECTURE.md` for the full design, the file map, and the optional
tab-audio capture path.
