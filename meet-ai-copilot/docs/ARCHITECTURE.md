# Architecture

## File map

```
manifest.json                 MV3 manifest (permissions, content scripts, worker)
background/
  service-worker.js           ES-module worker: runs Claude calls, streams tokens
lib/
  claude-client.js            Messages API client (gate + streaming answer)
content/                      Injected into meet.google.com (isolated world)
  state.js                    Shared namespace, settings, rolling transcript
  transcript-capture.js       Reads Meet live captions via MutationObserver
  question-detector.js        Local, free pre-filter
  overlay.js                  Floating suggestion panel (draggable, private)
  overlay.css                 Panel styling (scoped under #mc-root)
  main.js                     Orchestrator: capture → filter → worker → overlay
popup/                        Toolbar quick settings
options/                      Full settings page
icons/                        16/32/48/128 PNGs
```

## Contexts and why the key is safe

Three JS execution contexts, isolated from each other:

- **Page content scripts** (`content/*`) run in Meet's tab but in an *isolated
  world* — they can read the DOM but share no variables with Meet's own scripts.
  They never see the API key.
- **Background service worker** (`background/service-worker.js`) is a separate
  context. It holds the only code that talks to `api.anthropic.com`. The API key is
  read from `chrome.storage.local` (forwarded by the content script per request)
  and used only here.
- **Popup / options** are their own pages; they only read/write settings.

Content scripts talk to the worker over a `chrome.runtime` **Port** (`main.js` ⇄
`service-worker.js`), multiplexed by `reqId`, so answer tokens can stream back
incrementally.

## Data flow, request by request

1. `transcript-capture.js` finalizes an utterance → `MC.onUtterance(utt)`.
2. `main.js` runs `question-detector.evaluate()`. If it returns nothing, stop
   (no API cost). Otherwise apply the debounce (`minSecondsBetweenCalls`; direct
   questions bypass it).
3. `main.js` opens a card in the overlay and posts `{type:'suggest', reqId, kind,
   question, transcript, settings}` to the worker.
4. Worker: for non-direct questions with the gate on, call `runGate()` (Haiku,
   `max_tokens:5`, returns RESPOND/SKIP). SKIP → `gate_declined`, card removed.
5. Worker calls `streamAnswer()` (answer model, streamed), posting `delta` events
   as tokens arrive, then `done`.
6. Overlay renders the streaming answer in the card.

Manual "Ask" from the panel skips detection and the gate entirely.

## Caption capture algorithm

Meet rewrites caption text in place as a person speaks and swaps the whole caption
region when captions are toggled or the language changes. The capture layer:

- **Anchors on `div[role="region"][tabindex="0"]`** (stable across redesigns and
  languages; present even when CC is visually off), with heuristic fallbacks.
- Observes `{childList, subtree, characterData}` and coalesces bursts (120 ms).
- Treats the **last leaf caption block** as the active utterance.
- **Replaces** the growing line rather than appending (the core de-dup move).
- **Finalizes** an utterance on speaker change, block change, a sudden text-length
  drop (Meet's ~30-min line reset), or 2 s of silence.
- **Re-attaches every 2 s** — the single most important reliability fix, since Meet
  silently detaches the region on CC/language changes.
- Optionally clicks Meet's CC button (matched by its Material-symbols ligature
  `closed_caption_off`, not a class name) when captions are off.

Nothing here records audio; it reads text Meet already renders. That's what makes
the transcript free.

## Cost model

Confirmed against the Claude API pricing (July 2026):

| Model | Input $/MTok | Output $/MTok | Role |
|---|---|---|---|
| Haiku 4.5 | $1.00 | $5.00 | gate (RESPOND/SKIP) |
| Sonnet 5 | $2.00* | $10.00* | answers (default) |
| Opus 4.8 | $5.00 | $25.00 | optional high quality |
| Fable 5 | $10.00 | $50.00 | optional max capability |

\*Sonnet 5 introductory pricing through 2026-08-31.

Savings stack: free captions → local filter drops ~70% of lines → Haiku gate blocks
marginal cases → cached system prompt + small `max_tokens` + streaming. Net ≈
$1.50–$2.00 per 30-minute meeting at ~8–10 questions.

## Optional: tab-audio capture (not enabled)

When captions aren't available or you want higher-fidelity ASR, MV3 supports
capturing the tab audio via `chrome.tabCapture.getMediaStreamId()` in the worker
(Chrome 116+) consumed by an **offscreen document** (`getUserMedia` isn't allowed in
the worker). The remote participants' audio comes from the tab stream; your own mic
is a separate `getUserMedia({audio:true})`. Note: tab capture **mutes the tab** for
you unless you reconnect the stream to an `AudioContext.destination`. You'd then feed
audio to an ASR (on-device or cloud) and lose Meet's free speaker labels. This path
costs money and compute, so it's documented but off by default — captions are the
primary source.

To add it: `"permissions": ["offscreen","tabCapture"]`, an `offscreen.html`, and a
`start-recording` message from the worker with the `streamId`.

## Extending

- **New trigger types:** edit `question-detector.js` (`evaluate`) — it's pure and
  free to run.
- **Prompt/voice tuning:** `lib/claude-client.js` (`answerSystem`, `gateSystem`).
- **Different models:** add options in `popup.html` / `options.html`; IDs flow
  through unchanged. `thinkingFor()` in the client already branches so latency
  stays low where the model allows disabling thinking.
- **Transcript caching:** the biggest remaining optimization is caching the
  transcript prefix (not just the system prompt) by chunking it into stable
  segments with `cache_control` breakpoints; see `shared/prompt-caching.md` in the
  Claude API skill for the pattern.
```
