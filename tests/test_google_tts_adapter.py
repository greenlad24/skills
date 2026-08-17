"""Unit tests for the Google Cloud TTS (Thai) adapter (no network)."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from app.core.adapters.real import google_tts as mod
from app.core.config import settings

_FAKE_MP3 = b"ID3FAKEMP3AUDIO"


class _Resp:
    def __init__(self, *, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data
    def raise_for_status(self):
        if self.status_code >= 400:
            raise mod.httpx.HTTPStatusError("err", request=None, response=None)
    def json(self):
        return self._json


class _FakeClient:
    posted = None

    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False

    def post(self, url, **kw):
        _FakeClient.posted = {"url": url, "params": kw.get("params"), "json": kw.get("json")}
        return _Resp(json_data={"audioContent": base64.b64encode(_FAKE_MP3).decode("ascii")})


@pytest.fixture
def tts(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "GOOGLE_TTS_API_KEY", "key-123", raising=False)
    monkeypatch.setattr(settings, "GOOGLE_TTS_VOICE", "th-TH-Neural2-C", raising=False)
    monkeypatch.setattr(settings, "GOOGLE_TTS_LANGUAGE", "th-TH", raising=False)
    monkeypatch.setattr(settings, "GOOGLE_TTS_USD_PER_MILLION", 0.0, raising=False)
    monkeypatch.setattr(settings, "GOOGLE_TTS_SEC_PER_CHAR", 0.08, raising=False)
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path), raising=False)
    monkeypatch.setattr(mod.httpx, "Client", _FakeClient)
    # Force the estimate path so the test doesn't depend on a system ffprobe.
    monkeypatch.setattr(mod, "_probe_duration", lambda p: None)
    return mod.GoogleTTSProvider(), tmp_path


def test_synthesize_saves_mp3_and_reports_free(tts):
    prov, tmp_path = tts
    res = prov.synthesize(
        text="สวัสดีค่ะ", voice_id="", language="", model="", idempotency_key="k1",
    )
    assert res.ok and res.cost_usd == 0.0
    out = Path(res.data["audio_key"])
    assert out.exists() and out.read_bytes() == _FAKE_MP3
    assert res.data["mime_type"] == "audio/mpeg"
    assert res.usage["characters"] == len("สวัสดีค่ะ")


def test_synthesize_uses_request_defaults_and_key(tts):
    prov, _ = tts
    prov.synthesize(text="hello", voice_id="", language="", model="", idempotency_key="k2")
    posted = _FakeClient.posted
    assert posted["params"] == {"key": "key-123"}
    assert posted["json"]["voice"] == {"languageCode": "th-TH", "name": "th-TH-Neural2-C"}
    assert posted["json"]["audioConfig"]["audioEncoding"] == "MP3"


def test_voice_and_language_overrides(tts):
    prov, _ = tts
    prov.synthesize(text="hi", voice_id="th-TH-Standard-A", language="th-TH",
                    model="", idempotency_key="k3")
    assert _FakeClient.posted["json"]["voice"]["name"] == "th-TH-Standard-A"


def test_duration_estimate_when_no_ffprobe(tts):
    prov, _ = tts
    res = prov.synthesize(text="abcde", voice_id="", language="", model="", idempotency_key="k4")
    assert res.data["duration_sec"] == pytest.approx(5 * 0.08, rel=1e-6)


def test_empty_text_errors(tts):
    prov, _ = tts
    res = prov.synthesize(text="   ", voice_id="", language="", model="", idempotency_key="k5")
    assert res.ok is False and "empty" in (res.error or "")


def test_missing_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_TTS_API_KEY", "", raising=False)
    with pytest.raises(RuntimeError):
        mod.GoogleTTSProvider()
