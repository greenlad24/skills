# VOX — HTTP/WS API Contract

Every component builds against this. Backend implements it; frontend consumes it.
Base URL: `http://localhost:8008` (configurable via `VOX_PORT`).

## Static

### `GET /`
Serves `web/index.html`. All of `web/` is served as static files under `/` (so
`web/js/app.js` is reachable at `/js/app.js`, `web/css/hologram.css` at
`/css/hologram.css`, `web/assets/portrait.png` at `/assets/portrait.png`).

---

## `GET /api/config`
Returns runtime capabilities so the frontend can adapt.

```json
{
  "model": "llama3.2:3b",
  "llm_ready": true,
  "tts_ready": true,
  "stt_ready": false,
  "web_ready": true,
  "voice": "en_US-amy-medium",
  "portrait_url": "/assets/portrait.png",
  "portrait_present": true,
  "face_box": [0.36, 0.05, 0.28, 0.17],
  "name": "Vox"
}
```
- `web_ready`: internet reachable AND the web feature is enabled (`VOX_WEB` != "0").
  When false, the frontend hides web controls and Vox answers from local knowledge only.
- `face_box`: `[x, y, w, h]` normalized (0..1) rectangle locating Vox's **head**
  within the (possibly full-body) portrait, so the lip-sync/blink target the face.
  Backend reads `VOX_FACE_BOX` (default suits a full-body figure with head at
  top-center); for a head-and-shoulders shot use `1,1` sizing, e.g. `0,0,1,1`.
`*_ready` flags let the UI degrade gracefully (hide mic if `stt_ready:false`, show
a text-only banner if `tts_ready:false`, use placeholder face if
`portrait_present:false`).

---

## `POST /api/chat`  → **Server-Sent Events**
Request:
```json
{ "message": "Who are you?",
  "history": [ {"role":"user","content":"..."}, {"role":"assistant","content":"..."} ] }
```
Response: `Content-Type: text/event-stream`. Emit token deltas as they arrive
from the LLM, then a final done event:
```
data: {"type":"token","text":"I"}
data: {"type":"token","text":" am"}
data: {"type":"token","text":" Vox"}
data: {"type":"done","text":"I am Vox, a compendium of all human knowledge."}
```
On error: `data: {"type":"error","message":"..."}` then close.
`history` excludes the system prompt (backend injects the Vox persona itself).

**Panel frames (v2 — the floating holographic source/web cards).** When
`web_ready` and the turn warrants it, the backend performs a live web search,
fetches the top results, GROUNDS Vox's spoken answer on their snippets, and
emits `panel` frames interleaved with tokens so cards materialize beside Vox as
he speaks (exactly like the film's "AUTHORS — WELLS, H.G." / "SCIENCE FICTION —
FILM" cards):
```
data: {"type":"panel","panel":{
  "id":"p1",
  "kind":"source",                 // "source" | "reader" | "image"
  "title":"The Time Machine (2002 film) — Wikipedia",
  "url":"https://en.wikipedia.org/wiki/The_Time_Machine_(2002_film)",
  "snippet":"A 2002 American science fiction film ...",
  "image":"https://.../poster.jpg",   // optional thumbnail / og:image
  "source":"wikipedia.org"
}}
```
- `kind:"source"` = compact citation card (title, snippet, thumbnail, link).
- `kind:"reader"` = expanded card with cleaned page `text` + `images` (from `/api/fetch`).
- `kind:"image"` = an image tile (`image` = url, `title` = caption).
Panels are advisory UI; a client MAY ignore them. Tokens and panels may arrive in
any order; render panels as they come. Offline / `web_ready:false`: no panel frames.

---

## `POST /api/tts`  → **audio/wav**
Request: `{ "text": "I am Vox." }`
Response: `200` with body = WAV bytes (`Content-Type: audio/wav`), synthesized by
Piper. If TTS unavailable: `503` with `{"error":"tts_unavailable"}`.
The frontend plays this WAV and derives lip-sync from its live amplitude — the
backend does **not** compute visemes.

---

## `POST /api/stt`  → **json** *(optional; only if `stt_ready`)*
Request: `multipart/form-data` with field `audio` = a WAV/webm blob from the mic.
Response: `{ "text": "who are you" }`. If unavailable: `503`
`{"error":"stt_unavailable"}`.

---

## `POST /api/search`  → **json** *(v2; only if `web_ready`)*
Request: `{ "query": "time machine 2002 movie", "count": 4 }`
Response: `{ "results": [ {"title":..., "url":..., "snippet":..., "source":"host.com"} ] }`
Backend implementation: dependency-free web search (e.g. DuckDuckGo lite/HTML)
via `httpx` + stdlib `html.parser`. If disabled/offline: `503 {"error":"web_unavailable"}`.

---

## `POST /api/fetch`  → **json** *(v2; only if `web_ready`)*
Request: `{ "url": "https://en.wikipedia.org/wiki/The_Time_Machine" }`
Response (a "reader" panel payload):
```json
{ "url":"...", "title":"...", "text":"cleaned main text ...",
  "images":["https://...","https://..."], "image":"https://og-image...",
  "source":"en.wikipedia.org", "allow_iframe": false }
```
`allow_iframe` is a best-effort heuristic from `X-Frame-Options` / CSP so the
frontend knows whether it may embed the live page in an `<iframe>` vs. render the
cleaned reader view. `httpx` + stdlib parsing only. Offline/disabled: `503`.

---

## Conventions
- All JSON is UTF-8. CORS may be open to `localhost` for dev.
- No authentication (local single-user app).
- Long LLM replies must stream (SSE) so the face can start "thinking" immediately.
- Frontend must never assume a capability without checking `/api/config` first.
