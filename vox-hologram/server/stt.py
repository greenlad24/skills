"""whisper.cpp speech-to-text wrapper for VOX (optional feature).

Push-to-talk transcription on CPU via whisper.cpp's ``whisper-cli``. This is
strictly optional: if whisper or its model is absent the app still runs (text
input always works) and the endpoint reports ``stt_unavailable``. As with TTS,
the blocking subprocess runs in a worker thread and temp files are cleaned up.

whisper.cpp expects 16 kHz mono 16-bit PCM WAV. The browser is asked to send
WAV; if the incoming audio isn't already in that form we best-effort convert it
with ``ffmpeg`` when available, otherwise we hand the file to whisper as-is.

Public surface:
- ``STTUnavailable``            raised when whisper or its model is missing.
- ``async transcribe(bytes)``   -> recognized text (possibly empty string).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import anyio

from . import config


class STTUnavailable(Exception):
    """Raised when whisper.cpp cannot be run (binary or model absent)."""


def _maybe_convert_to_wav16k(src_path: str) -> str:
    """Return a path to 16 kHz mono WAV. Uses ffmpeg if present; else returns
    ``src_path`` unchanged (whisper.cpp will accept a suitable WAV directly)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return src_path
    fd, wav_path = tempfile.mkstemp(prefix="vox-stt-", suffix=".16k.wav")
    os.close(fd)
    proc = subprocess.run(
        [ffmpeg, "-y", "-i", src_path, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0 or not os.path.getsize(wav_path):
        # Conversion failed; fall back to the original and let whisper try.
        try:
            os.remove(wav_path)
        except OSError:
            pass
        return src_path
    return wav_path


def _run_whisper_sync(audio_bytes: str) -> str:
    """Blocking: write audio to a temp file, run whisper-cli, read the text."""
    model = config.whisper_model()
    src_fd, src_path = tempfile.mkstemp(prefix="vox-stt-in-", suffix=".audio")
    os.close(src_fd)
    temp_paths = [src_path]
    try:
        with open(src_path, "wb") as handle:
            handle.write(audio_bytes)

        wav_path = _maybe_convert_to_wav16k(src_path)
        if wav_path != src_path:
            temp_paths.append(wav_path)

        # whisper-cli writes ``<out_prefix>.txt`` when given -otxt/-of.
        out_prefix = wav_path + ".out"
        txt_path = out_prefix + ".txt"
        temp_paths.append(txt_path)

        cmd = [
            config.whisper_bin(),
            "-m", str(model),
            "-f", wav_path,
            "-otxt",
            "-of", out_prefix,
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", "replace").strip()
            raise STTUnavailable(f"whisper exited {proc.returncode}: {detail}")

        if os.path.isfile(txt_path):
            with open(txt_path, "r", encoding="utf-8", errors="replace") as handle:
                return handle.read().strip()
        # Some builds print the transcript to stdout instead of a file.
        return proc.stdout.decode("utf-8", "replace").strip()
    except FileNotFoundError as exc:
        raise STTUnavailable(str(exc))
    finally:
        for path in temp_paths:
            try:
                os.remove(path)
            except OSError:
                pass


async def transcribe(audio_bytes: bytes) -> str:
    """Transcribe raw ``audio_bytes`` off the event loop.

    Raises ``STTUnavailable`` if STT is not configured/installed.
    """
    if not config.stt_ready():
        raise STTUnavailable("stt_unavailable")
    if not audio_bytes:
        raise STTUnavailable("empty audio")
    return await anyio.to_thread.run_sync(_run_whisper_sync, audio_bytes)
