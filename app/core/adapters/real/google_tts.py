"""Thai voiceover via Google Cloud Text-to-Speech — the near-free `TTSProvider` (§1.6).

Google Cloud TTS has a generous monthly free tier (1M chars for Neural2/WaveNet,
4M for Standard voices). At ~500 Thai characters per script and 90 videos/month
(~45k chars) you sit comfortably inside the free tier — so Thai narration costs
effectively $0. Set:

    TTS_PROVIDER=google_tts
    GOOGLE_TTS_API_KEY=<your key>            # console.cloud.google.com → Text-to-Speech API

Contract mapping (identical shape to FakeTTSProvider):
  * synthesize → POSTs text to the v1 text:synthesize endpoint, decodes the base64
    MP3 into MEDIA_ROOT/tts, and returns audio_key + duration_sec.

Duration: measured exactly with ffprobe when ffmpeg is installed (it is in the
Docker image and the mac local-run script), else estimated from character count so
the pipeline always gets a usable number.
"""

from __future__ import annotations

import base64
import hashlib
import shutil
import subprocess
from pathlib import Path

import httpx

from app.core.adapters.base import ProviderResult
from app.core.adapters.registry import register_real
from app.core.config import settings

_ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"


def _probe_duration(path: Path) -> float | None:
    """Exact audio duration via ffprobe, or None if ffmpeg isn't available."""
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=20,
        )
        return round(float(out.stdout.strip()), 2)
    except (ValueError, OSError, subprocess.SubprocessError):
        return None


class GoogleTTSProvider:
    """Near-free Thai `TTSProvider` backed by Google Cloud Text-to-Speech."""

    provider_name = "google-tts"

    def __init__(self) -> None:
        if not settings.GOOGLE_TTS_API_KEY:
            raise RuntimeError(
                "GOOGLE_TTS_API_KEY is not set. Create a Text-to-Speech API key in the "
                "Google Cloud console, or set DRY_RUN=true for the fake provider."
            )
        self._key = settings.GOOGLE_TTS_API_KEY
        self._default_voice = settings.GOOGLE_TTS_VOICE
        self._default_lang = settings.GOOGLE_TTS_LANGUAGE
        self._usd_per_million = float(settings.GOOGLE_TTS_USD_PER_MILLION)
        self._sec_per_char = float(settings.GOOGLE_TTS_SEC_PER_CHAR)

    def synthesize(
        self, *, text: str, voice_id: str, language: str, model: str, idempotency_key: str
    ) -> ProviderResult:
        if not text.strip():
            return ProviderResult(ok=False, error="google_tts: empty text")

        language_code = language or self._default_lang
        voice_name = voice_id or self._default_voice
        body = {
            "input": {"text": text},
            "voice": {"languageCode": language_code, "name": voice_name},
            "audioConfig": {"audioEncoding": "MP3"},
        }
        try:
            with httpx.Client(timeout=60) as c:
                r = c.post(_ENDPOINT, params={"key": self._key}, json=body)
                r.raise_for_status()
                audio_b64 = r.json()["audioContent"]
        except httpx.HTTPError as exc:
            return ProviderResult(ok=False, error=f"google_tts http error: {exc}")
        except (KeyError, ValueError) as exc:
            return ProviderResult(ok=False, error=f"google_tts bad response: {exc}")

        try:
            audio_key = self._save_audio(audio_b64, idempotency_key)
        except (ValueError, OSError) as exc:
            return ProviderResult(ok=False, error=f"google_tts save error: {exc}")

        chars = len(text)
        duration = _probe_duration(Path(audio_key))
        if duration is None:
            duration = round(chars * self._sec_per_char, 2)   # fallback estimate
        cost = round(chars / 1_000_000 * self._usd_per_million, 6)

        return ProviderResult(
            ok=True,
            data={"audio_key": audio_key, "duration_sec": duration, "mime_type": "audio/mpeg"},
            cost_usd=cost,                       # 0 inside the free tier (default rate 0)
            usage={"characters": chars, "seconds": duration},
        )

    # -- helpers ------------------------------------------------------------- #

    def _save_audio(self, audio_b64: str, idempotency_key: str) -> str:
        data = base64.b64decode(audio_b64)
        out_dir = Path(settings.MEDIA_ROOT) / "tts"
        out_dir.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]
        out_path = out_dir / f"{name}.mp3"
        out_path.write_bytes(data)
        return str(out_path)


# Selected when TTS_PROVIDER=google_tts and DRY_RUN=false.
register_real("tts", "google_tts", GoogleTTSProvider)
