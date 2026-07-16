# VOX — Local Hologram Librarian · Architecture

A fully local, free, open-source **AI hologram librarian** web app, inspired by
"Vox 114" from *The Time Machine* (2002). Runs entirely on the user's own Mac —
no cloud, no API keys, no subscriptions.

## Target machine (hard constraints — design for these)

- **macOS 11.7 Big Sur, Intel CPU** (no Apple Silicon, no Metal LLM acceleration).
- Everything must run on CPU and be responsive enough for conversation.
- Everything must install without a modern Xcode / recent-macOS-only wheels where
  avoidable. Prefer prebuilt binaries and pure-Python deps.

## The three pillars (all local, all free, all open source)

| Concern       | Tool                              | Why it fits Intel Big Sur                          |
|---------------|-----------------------------------|----------------------------------------------------|
| LLM ("brain") | **Ollama** *or* **llama.cpp**     | Both expose an OpenAI-compatible HTTP API on CPU.  |
| Voice (TTS)   | **Piper**                         | Fast neural TTS, runs on CPU, prebuilt macOS binary.|
| Ears (STT)    | **whisper.cpp** *(optional)*      | CPU speech-to-text; push-to-talk. Text input always works. |
| Face          | **Browser hologram** (this app)   | Real-time WebGL/CSS shader + audio-driven lip-sync. No neural video. |

The LLM layer is **pluggable via an OpenAI-compatible endpoint** so it works with
either Ollama (`http://localhost:11434/v1`) or llama.cpp's `llama-server`
(`http://localhost:8080/v1`). Default model target: a small quantized model that
runs on Intel CPU (e.g. `llama3.2:3b` or `qwen2.5:3b`).

## Real-time lip-sync approach (no neural video — critical for Intel)

The face does **not** use SadTalker/Wav2Lip. Instead:

1. Backend synthesizes the reply to a WAV with Piper.
2. Browser plays the WAV through the **Web Audio API**.
3. An `AnalyserNode` reads the live audio amplitude envelope each frame.
4. Amplitude drives **mouth openness**; the portrait is composited under a
   **holographic shader** (cyan glow, scanlines, flicker, chromatic aberration).

This makes lip-sync real-time and essentially free of compute, which is exactly
what an Intel Big Sur machine needs.

## Component ownership (each built by one agent, against `API.md`)

```
vox-hologram/
  ARCHITECTURE.md   ← this file (contract owner: orchestrator)
  API.md            ← the HTTP/WS contract every component obeys (orchestrator)
  README.md         ← setup + troubleshooting for Intel Big Sur   [SETUP agent]
  setup.sh          ← one-shot installer                          [SETUP agent]
  run.sh            ← launcher                                    [SETUP agent]
  requirements.txt  ← python deps                                 [SETUP agent]
  scripts/          ← model/voice/whisper downloaders             [SETUP agent]

  server/           ← FastAPI backend, all Python                 [BACKEND agent]
    app.py          ← routes + static hosting + SSE + STT
    llm.py          ← OpenAI-compatible chat client (Ollama/llama.cpp)
    tts.py          ← Piper wrapper -> WAV
    stt.py          ← whisper.cpp wrapper (optional)
    personality.py  ← Vox system prompt + persona
    config.py       ← env/config resolution

  web/              ← the hologram front-end, no build step       [FRONTEND agent]
    index.html
    css/hologram.css
    js/hologram.js  ← shader + audio-driven mouth
    js/app.js       ← chat, SSE, audio playback, mic
    assets/         ← portrait.png (user drops their face here)
```

## Data flow (one conversational turn)

```
user text ─▶ POST /api/chat (SSE) ─▶ llm.py ─▶ Ollama/llama.cpp
        ◀── streamed tokens ───────────────────────────┘
full reply ─▶ POST /api/tts ─▶ tts.py ─▶ Piper ─▶ WAV
        ◀── audio bytes
browser: play WAV + AnalyserNode amplitude ─▶ mouth openness ─▶ hologram render
(optional) mic ─▶ POST /api/stt ─▶ stt.py ─▶ whisper.cpp ─▶ text ─▶ back to /api/chat
```

## Non-negotiables

- 100% local. No network calls at runtime except to the local LLM server.
- Graceful degradation: if Piper missing → text-only with a clear banner; if
  whisper missing → hide mic, keep text input; if portrait missing → ship a
  built-in stylized placeholder face so the app still runs on first launch.
- No secrets, no API keys anywhere.
