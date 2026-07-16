# VOX — Your Local Hologram Librarian

> *"I am Vox. I contain all the knowledge of humankind."*

VOX is a fully **local, offline, free & open-source** AI hologram librarian that
lives in your browser. Ask it anything and a flickering cyan hologram of a face —
**your** face — answers aloud, its lips moving in real time to the sound of its
own voice.

It is a love letter to **Vox 114**, the holographic library assistant from the
2002 film *The Time Machine* — itself adapted from **H. G. Wells' 1895 novel**.
Where Wells imagined a traveller meeting the far future, and the film imagined a
librarian who had outlived humanity, VOX lets you build a tiny, personal version
of that idea that runs entirely on your own computer. No cloud. No API keys. No
subscriptions. Nothing leaves your machine.

This is a **personal / fan project**. You supply your own face image; VOX supplies
the glow.

---

## v2: full-body Vox + holographic sources

VOX v2 leans even harder into the film's library scene. Instead of a floating head,
you now get a **full-body standing Vox** projected on a pedestal — a translucent,
flickering figure of *your* likeness. As Vox speaks, **floating holographic panels**
materialize in the air beside him: compact **source cards** (title, snippet,
thumbnail, link), expanded **reader cards** with a page's cleaned text and images,
and standalone **image tiles** — echoing the film's "AUTHORS — WELLS, H.G." and
"SCIENCE FICTION — FILM" cards drifting around Vox 114.

Those panels come from an **optional web layer**. Here is the boundary, stated
plainly:

- **The brain (LLM) is 100% local and offline.** It never phones home. All of Vox's
  reasoning and speech run on your own CPU, exactly as in v1.
- **The optional *sources* feature is the only thing that touches the internet** —
  and only to **search** the web and **fetch** the pages it cites, like Vox
  consulting the library's records. Those pages ground his answer and become the
  floating cards.
- **With no internet — or with `VOX_WEB=0` — everything still runs.** Vox simply
  answers from the local model's own knowledge, with no panels. Nothing about the
  core experience depends on being online.

The web layer uses only `httpx` and Python's standard library, so it adds **no new
dependencies** — the four-package install is unchanged.

---

## Hardware target

VOX is built and tuned for the modest end of the hardware spectrum:

- **Intel Mac** (x86_64 — *not* Apple Silicon)
- **macOS 11.7 Big Sur** (no Metal LLM acceleration)
- Everything runs on **CPU** and stays responsive enough to hold a conversation.

It will also run on newer/faster Macs (and works on Apple Silicon), but every
design decision favors the Intel Big Sur machine above.

---

## Quickstart (4 steps)

```bash
# 1. Install everything (Homebrew, Python venv, LLM runtime, Piper, whisper, models)
./setup.sh

# 2. Add your face  (a full-body photo on a plain/dark background, or a
#    head-and-shoulders shot — see "Adding / replacing your face" below)
cp ~/Pictures/me.png web/assets/portrait.png
#    No portrait? VOX launches with a stylized standing-figure placeholder.

# 3. Start the LLM "brain" in a separate terminal and leave it running:
#      macOS 12+ (Ollama):     ollama serve
#      Big Sur / Intel (llama.cpp):
#        llama-server -m models/Llama-3.2-3B-Instruct-Q4_K_M.gguf --port 8080

# 4. Launch VOX
./run.sh                     # opens http://localhost:8008 in your browser
```

That's it. Talk to your hologram.

---

## Architecture (the four pillars)

VOX is deliberately built from small, CPU-friendly, swappable parts. The face
does **no** neural video — lip-sync is derived in the browser from the live audio
amplitude, which is why it stays fast on an Intel CPU.

| Pillar         | Tool                                   | Role                                              |
|----------------|----------------------------------------|---------------------------------------------------|
| Brain (LLM)    | **Ollama** *or* **llama.cpp**          | OpenAI-compatible chat API, streamed over SSE     |
| Voice (TTS)    | **Piper**                              | Fast neural text-to-speech, CPU, prebuilt binary  |
| Ears (STT)     | **whisper.cpp** *(optional)*           | Push-to-talk speech-to-text; text input always works |
| Face           | **Browser hologram** (this app)        | WebGL/CSS holographic shader + audio-driven mouth |

```
you ──▶ POST /api/chat (SSE) ──▶ LLM (Ollama / llama.cpp) ──▶ streamed reply
reply ─▶ POST /api/tts ──▶ Piper ──▶ WAV ──▶ browser plays it
browser: AnalyserNode reads amplitude ──▶ mouth openness ──▶ hologram render
(optional) mic ─▶ POST /api/stt ─▶ whisper.cpp ─▶ text ─▶ back to chat
```

The LLM layer is **pluggable** because both Ollama and llama.cpp expose an
OpenAI-compatible endpoint. VOX just points at a base URL.

### Why two LLM runtimes?

**The modern Ollama app requires a newer macOS than 11.7 and likely will not run
on Intel Big Sur.** So VOX treats **llama.cpp** as a first-class path:

- **macOS < 12 (Big Sur, your target):** use **llama.cpp**.
  `brew install llama.cpp` gives you `llama-server`, an OpenAI-compatible server
  on `http://localhost:8080/v1`. `setup.sh` picks this automatically.
- **macOS ≥ 12:** the **Ollama** path is fine.
  `brew install ollama` → `ollama serve` → API on `http://localhost:11434/v1`.

`setup.sh` detects your macOS version and chooses for you, but you can force
either one:

```bash
VOX_RUNTIME=llamacpp ./setup.sh     # force llama.cpp
VOX_RUNTIME=ollama   ./setup.sh     # force Ollama
```

---

## Adding / replacing your face

VOX composites your photo under the holographic shader. Whichever kind of photo you
use, it goes in the **same place** — **`web/assets/portrait.png`** (JPG/WEBP also
work: `portrait.jpg`, `portrait.jpeg`, `portrait.webp`) — and you reload the browser
tab to apply it. The only difference is the `VOX_FACE_BOX` value, which tells VOX
where the **head** sits so lip-sync and blinking land on the face:

- **Full-body photo** (best for the v2 standing figure): a full figure on a **plain
  or dark background**, head near the **top-center** of the frame. **Keep the default
  `VOX_FACE_BOX`** — it already expects the head at the top of a full-body portrait.
- **Head-and-shoulders photo** (classic bust, like v1): a square-ish, front-facing,
  well-lit crop that fills the frame. Set **`VOX_FACE_BOX=0,0,1,1`** so VOX treats the
  whole image as the face.

```bash
# Full-body portrait — default face box, nothing to set
./run.sh

# Head-and-shoulders portrait — whole image is the face
VOX_FACE_BOX=0,0,1,1 ./run.sh
```

If no portrait is present, VOX ships a built-in stylized **standing-figure**
placeholder so the app still runs on first launch. See **`portrait/README.md`** for
tips on getting the best hologram effect.

---

## Changing the model or voice (environment variables)

Everything is configured through `VOX_*` environment variables. Export any of
them before `./run.sh` and your value wins over the defaults. `run.sh` also
reads `.vox.env` (written by `setup.sh`) for the runtime it chose.

| Variable            | Default                                         | What it does |
|---------------------|-------------------------------------------------|--------------|
| `VOX_PORT`          | `8008`                                           | Web app port |
| `VOX_LLM_BASE_URL`  | `http://localhost:11434/v1` (Ollama) / `http://localhost:8080/v1` (llama.cpp) | OpenAI-compatible LLM endpoint |
| `VOX_LLM_MODEL`     | `llama3.2:3b`                                     | Model tag / name to request |
| `VOX_LLM_API_KEY`   | `ollama`                                         | Bearer token (local servers ignore it) |
| `VOX_PIPER_BIN`     | `piper`                                          | Piper executable (name or path) |
| `VOX_PIPER_VOICE`   | `voices/en_US-amy-medium.onnx`                   | Piper voice model (`.onnx`) |
| `VOX_WHISPER_BIN`   | `whisper-cli`                                    | whisper.cpp executable |
| `VOX_WHISPER_MODEL` | `models/ggml-base.en.bin`                        | whisper GGML model |
| `VOX_WEB`           | `1`                                              | Web sources layer: `1` = search/fetch pages to ground answers and show floating panels; `0` = pure-local, no panels |
| `VOX_FACE_BOX`      | *(suits a full-body portrait)*                   | Normalized head box `"x,y,w,h"` (0..1) locating the face for lip-sync/blink; use `"0,0,1,1"` for a head-and-shoulders photo |

Voice and whisper paths are resolved relative to the VOX repo root when left at
their defaults. The web layer (`VOX_WEB`) uses only `httpx` + the Python standard
library — it installs **nothing new**. Even with `VOX_WEB=1`, if there is no
internet the app runs fully offline and simply skips the panels.

### Examples

```bash
# Use a faster, smaller model for snappier replies
VOX_LLM_MODEL=llama3.2:1b ./run.sh

# Point at a llama.cpp server explicitly
VOX_LLM_BASE_URL=http://localhost:8080/v1 VOX_LLM_MODEL=Llama-3.2-3B-Instruct-Q4_K_M ./run.sh

# Use a different Piper voice you downloaded into voices/
VOX_PIPER_VOICE="$PWD/voices/en_US-ryan-high.onnx" ./run.sh

# Run on a different port
VOX_PORT=9000 ./run.sh

# Turn OFF the web sources layer — pure local, no panels, faster turns
VOX_WEB=0 ./run.sh

# Head-and-shoulders portrait: treat the whole image as the face
VOX_FACE_BOX=0,0,1,1 ./run.sh

# Full-body portrait uses the default face box — no VOX_FACE_BOX needed
```

To try a different Piper voice, browse
[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) and drop the
matching `.onnx` **and** `.onnx.json` into `voices/`.

---

## How the source panels work (v2)

When the web layer is on (`VOX_WEB=1`) and the internet is reachable, each turn
plays out like Vox consulting the library:

1. **Vox searches.** The backend runs a live web search for your question (via
   DuckDuckGo) and fetches the top results.
2. **Vox grounds his answer.** Those page snippets are fed to the **local** LLM so
   his spoken reply is anchored to real sources — the model still runs entirely on
   your Mac; only the search/fetch touched the network.
3. **Cards materialize.** As Vox narrates, **source cards** float in beside him —
   title, snippet, thumbnail, and a link — just like the film's drifting library
   panels. Vox cites what he used.
4. **Click a source to open a reader view.** Selecting a card expands it into a
   **reader panel** with the page's cleaned main text and images. When the site
   permits embedding, the **live page loads in an iframe**; when it refuses (many
   sites send `X-Frame-Options` / CSP to block framing), VOX shows the **cleaned
   reader view** instead, so the content still appears.

The whole feature is optional and advisory. Offline, or with `VOX_WEB=0`, no panels
appear and Vox answers from the local model alone.

---

## Troubleshooting

**Ollama won't install / won't run on Big Sur.**
Expected — the modern Ollama needs a newer macOS. Switch to the llama.cpp path:
```bash
VOX_RUNTIME=llamacpp ./setup.sh
brew install llama.cpp
llama-server -m models/Llama-3.2-3B-Instruct-Q4_K_M.gguf --port 8080
```
Then `./run.sh` (it now targets `http://localhost:8080/v1`).

**Replies are slow.**
On an Intel CPU, a 3B model is about the ceiling for comfortable chat. Use a
smaller model:
```bash
VOX_LLM_MODEL=llama3.2:1b ./run.sh        # Ollama
# or download a 1B-Instruct GGUF and point llama-server at it
```
Also close other heavy apps — token generation is CPU-bound.

**"LLM server not reachable."**
The brain is a *separate* process you must start yourself. `run.sh` prints the
exact command. Start it in another terminal and reload the page:
- Ollama: `ollama serve` (and once: `ollama pull llama3.2:3b`)
- llama.cpp: `llama-server -m models/…​.gguf --port 8080`

**No voice / the hologram is silent.**
1. Piper or the voice file may be missing. Re-run `./scripts/download_models.sh`
   and confirm `voices/en_US-amy-medium.onnx` **and** its `.onnx.json` exist, and
   that `piper` is on PATH (or set `VOX_PIPER_BIN`). If pip install failed, grab a
   prebuilt binary from the [Piper releases](https://github.com/rhasspy/piper/releases).
2. **Browser autoplay** may be blocking audio. Click anywhere in the page once
   (a user gesture) and try again — browsers block audio until you interact.

**The microphone button is missing or doesn't work.**
STT is **optional**. The mic only appears when whisper.cpp is installed
(`brew install whisper-cpp` → `whisper-cli`) *and* `models/ggml-base.en.bin`
exists. Even then, **Safari's `MediaRecorder` support is limited** on Big Sur —
if recording misbehaves, try Chrome/Chromium, or just type. Text input always
works, with or without whisper.

**No source panels appear.**
The web layer is optional and degrades silently. Panels are hidden when:
- you are **offline** (no internet — the LLM still answers from local knowledge);
- **`VOX_WEB=0`** is set (pure-local mode by choice);
- a **corporate/proxy firewall** is blocking DuckDuckGo, so search returns nothing.
Confirm you are online, unset `VOX_WEB` (or set `VOX_WEB=1`), and reload. VOX checks
`/api/config` on load and hides the web controls whenever sources are unavailable.

**A page won't embed as a live iframe.**
Expected for many sites. When a page sends `X-Frame-Options` (or a framing CSP), the
browser refuses to embed it, so VOX falls back to the **cleaned reader view** — the
page's main text and images — instead of the live iframe. Nothing is broken; the
content is still shown, just rendered by VOX rather than the origin site.

**The web feature feels slow.**
Grounding adds a **search + page fetch on every turn** before Vox replies, which
costs a little latency on a slow connection. For pure-local speed, turn it off:
```bash
VOX_WEB=0 ./run.sh        # no panels, no network per turn — just the local brain
```
You can leave it off entirely if you only want the offline librarian.

**Homebrew isn't found after installing.**
On Intel Macs Homebrew lives in `/usr/local`; on Apple Silicon `/opt/homebrew`.
Add it to your shell: `eval "$(/usr/local/bin/brew shellenv)"`.

---

## Credits

VOX stands on the shoulders of storytellers and open-source builders:

- **H. G. Wells** — *The Time Machine* (1895 novel), the origin of it all.
- **The Time Machine** (2002 film, dir. Simon Wells) — the **Vox 114** hologram
  librarian that inspired this project.
- **[Piper](https://github.com/rhasspy/piper)** — neural text-to-speech.
- **[whisper.cpp](https://github.com/ggerganov/whisper.cpp)** — CPU speech-to-text.
- **[Ollama](https://ollama.com)** and **[llama.cpp](https://github.com/ggml-org/llama.cpp)** — local LLM runtimes.
- **[FastAPI](https://fastapi.tiangolo.com)** + **[Uvicorn](https://www.uvicorn.org)** — the backend.
- **[DuckDuckGo](https://duckduckgo.com)** — the web search behind the optional v2
  source panels (search/fetch only; the LLM stays local).

VOX is a personal, non-commercial fan project. It is not affiliated with or
endorsed by any rights holder of *The Time Machine*. You provide your own face
image and your own models; VOX just wires them together, locally.
