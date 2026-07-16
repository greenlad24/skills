"""Piper text-to-speech wrapper for VOX.

Piper is a fast neural TTS with a prebuilt macOS binary — the right fit for an
Intel Big Sur machine with no GPU. It reads text on stdin and writes a WAV file.
We run it in a worker thread (``anyio.to_thread``) so the synchronous subprocess
never blocks the event loop, and we clean up the temp WAV in every path.

Public surface:
- ``TTSUnavailable``          raised when Piper or the voice model is missing.
- ``async synthesize(text)``  -> WAV bytes.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

import anyio

from . import config


class TTSUnavailable(Exception):
    """Raised when Piper cannot be run (binary or voice model absent)."""


def _run_piper_sync(text: str) -> bytes:
    """Blocking: feed ``text`` to Piper on stdin, return the WAV bytes."""
    voice = config.piper_voice()
    # Write to a NamedTemporaryFile path; Piper writes the WAV, we read it back.
    fd, out_path = tempfile.mkstemp(prefix="vox-tts-", suffix=".wav")
    os.close(fd)
    try:
        cmd = [
            config.piper_bin(),
            "--model", str(voice),
            "--output_file", out_path,
        ]
        proc = subprocess.run(
            cmd,
            input=text.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", "replace").strip()
            raise TTSUnavailable(f"piper exited {proc.returncode}: {detail}")
        with open(out_path, "rb") as handle:
            data = handle.read()
        if not data:
            raise TTSUnavailable("piper produced no audio")
        return data
    except FileNotFoundError as exc:
        # Piper binary not on PATH.
        raise TTSUnavailable(str(exc))
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass


async def synthesize(text: str) -> bytes:
    """Synthesize ``text`` to WAV bytes off the event loop.

    Raises ``TTSUnavailable`` if TTS is not configured/installed.
    """
    if not config.tts_ready():
        raise TTSUnavailable("tts_unavailable")
    clean = (text or "").strip()
    if not clean:
        raise TTSUnavailable("empty text")
    return await anyio.to_thread.run_sync(_run_piper_sync, clean)
