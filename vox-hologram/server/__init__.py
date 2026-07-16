"""VOX backend package — FastAPI server for the local hologram librarian.

Modules:
- config:      env/config resolution and capability detection
- llm:         OpenAI-compatible streaming chat client (Ollama / llama.cpp)
- tts:         Piper text-to-speech wrapper (-> WAV bytes)
- stt:         whisper.cpp speech-to-text wrapper (optional)
- app:         FastAPI routes, static hosting, SSE
- personality: Vox persona / system prompt (fixed creative asset)
"""

from __future__ import annotations

__all__ = ["config", "llm", "tts", "stt", "app", "personality"]
