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

# 2. Add your face  (any square, well-lit head-and-shoulders photo)
cp ~/Pictures/me.png web/assets/portrait.png
#    No portrait? VOX launches with a stylized placeholder face.

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

VOX composites your photo under the holographic shader. To set it:

1. Pick a **square**, front-facing, **well-lit** head-and-shoulders photo.
2. Save it as **`web/assets/portrait.png`** (JPG/WEBP also work —
   `portrait.jpg`, `portrait.jpeg`, `portrait.webp`).
3. Reload the browser tab. Done.

If no portrait is present, VOX ships a built-in stylized placeholder face so the
app still runs on first launch. See **`portrait/README.md`** for tips on getting
the best hologram effect.

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

Voice and whisper paths are resolved relative to the VOX repo root when left at
their defaults.

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
```

To try a different Piper voice, browse
[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) and drop the
matching `.onnx` **and** `.onnx.json` into `voices/`.

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

VOX is a personal, non-commercial fan project. It is not affiliated with or
endorsed by any rights holder of *The Time Machine*. You provide your own face
image and your own models; VOX just wires them together, locally.
