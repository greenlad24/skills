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
  "voice": "en_US-amy-medium",
  "portrait_url": "/assets/portrait.png",
  "portrait_present": true,
  "name": "Vox"
}
```
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

## Conventions
- All JSON is UTF-8. CORS may be open to `localhost` for dev.
- No authentication (local single-user app).
- Long LLM replies must stream (SSE) so the face can start "thinking" immediately.
- Frontend must never assume a capability without checking `/api/config` first.
