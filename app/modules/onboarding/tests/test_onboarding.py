"""Tests for the onboarding module: env upsert, live status, provider probes."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.modules.onboarding import env_store, service


@pytest.fixture
def env_file(monkeypatch, tmp_path):
    path = tmp_path / ".env"
    monkeypatch.setenv("AUTOUGC_ENV_FILE", str(path))
    return path


# --- env_store -------------------------------------------------------------- #

def test_upsert_replaces_and_appends(env_file):
    env_file.write_text("ANTHROPIC_API_KEY=old\nUNMANAGED=keep\n", encoding="utf-8")
    env_store.upsert_env({"ANTHROPIC_API_KEY": "new", "GOOGLE_TTS_API_KEY": "g"})
    text = env_file.read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY=new" in text
    assert "UNMANAGED=keep" in text            # untouched
    assert "GOOGLE_TTS_API_KEY=g" in text      # appended
    assert "ANTHROPIC_API_KEY=old" not in text


def test_save_whitelists_and_applies_live(env_file, monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "", raising=False)
    out = env_store.save({"ANTHROPIC_API_KEY": "sk-x", "EVIL_KEY": "nope"})
    assert out["saved"] == ["ANTHROPIC_API_KEY"]
    assert out["ignored"] == ["EVIL_KEY"]
    assert settings.ANTHROPIC_API_KEY == "sk-x"          # live-applied
    assert "EVIL_KEY" not in env_file.read_text(encoding="utf-8")


def test_save_coerces_bool(env_file, monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN", True, raising=False)
    env_store.save({"DRY_RUN": "false"})
    assert settings.DRY_RUN is False


def test_reload_settings_from_dotenv(env_file, monkeypatch):
    # The worker picks up keys saved by the web onboarding by re-reading .env.
    from app.core.config import reload_settings_from_dotenv

    env_file.write_text(
        "GOOGLE_TTS_API_KEY=g-from-env\nSOCIALCRAWL_API_KEY=sc\nDRY_RUN=false\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "GOOGLE_TTS_API_KEY", "", raising=False)
    monkeypatch.setattr(settings, "SOCIALCRAWL_API_KEY", "", raising=False)
    monkeypatch.setattr(settings, "DRY_RUN", True, raising=False)
    reload_settings_from_dotenv()
    assert settings.GOOGLE_TTS_API_KEY == "g-from-env"
    assert settings.SOCIALCRAWL_API_KEY == "sc"
    assert settings.DRY_RUN is False


def test_save_blank_value_keeps_existing_key(env_file, monkeypatch):
    # An empty field must NOT overwrite an already-saved secret (the wizard sends
    # blanks for keys the operator left untouched).
    env_file.write_text("ANTHROPIC_API_KEY=keepme\n", encoding="utf-8")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "keepme", raising=False)
    out = env_store.save({"ANTHROPIC_API_KEY": "  ", "SOCIALCRAWL_API_KEY": "sc-new"})
    assert "ANTHROPIC_API_KEY" in out["skipped_blank"]
    assert out["saved"] == ["SOCIALCRAWL_API_KEY"]
    assert "ANTHROPIC_API_KEY=keepme" in env_file.read_text(encoding="utf-8")
    assert settings.ANTHROPIC_API_KEY == "keepme"        # untouched


# --- status ----------------------------------------------------------------- #

def test_status_reports_missing_then_complete(monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN", False, raising=False)
    monkeypatch.setattr(settings, "ONBOARDED", False, raising=False)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "", raising=False)
    monkeypatch.setattr(settings, "GOOGLE_TTS_API_KEY", "", raising=False)
    monkeypatch.setattr(settings, "SOCIALCRAWL_API_KEY", "", raising=False)
    monkeypatch.setattr(settings, "MODAL_LTX_URL", "", raising=False)
    monkeypatch.setattr(settings, "TIKTOK_ACCESS_TOKEN", "", raising=False)
    st = service.compute_status()
    assert st["complete"] is False
    assert st["steps"] == {"keys": False, "video": False, "tiktok": False}

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "a", raising=False)
    monkeypatch.setattr(settings, "GOOGLE_TTS_API_KEY", "g", raising=False)
    monkeypatch.setattr(settings, "SOCIALCRAWL_API_KEY", "k", raising=False)
    monkeypatch.setattr(settings, "MODAL_LTX_URL", "http://m", raising=False)
    monkeypatch.setattr(settings, "TIKTOK_ACCESS_TOKEN", "t", raising=False)
    st2 = service.compute_status()
    assert st2["steps"] == {"keys": True, "video": True, "tiktok": True}
    assert st2["complete"] is True   # all steps green


def test_dry_run_bypasses_keys(monkeypatch):
    # In DRY_RUN (fakes) no real keys are needed, so the wizard is not forced.
    monkeypatch.setattr(settings, "DRY_RUN", True, raising=False)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "", raising=False)
    assert service.compute_status()["complete"] is True


def test_missing_required_key_forces_wizard_even_if_onboarded(monkeypatch):
    # Live mode: a missing required API re-opens onboarding, ONBOARDED flag notwithstanding.
    monkeypatch.setattr(settings, "DRY_RUN", False, raising=False)
    monkeypatch.setattr(settings, "ONBOARDED", True, raising=False)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "", raising=False)
    monkeypatch.setattr(settings, "GOOGLE_TTS_API_KEY", "g", raising=False)
    monkeypatch.setattr(settings, "SOCIALCRAWL_API_KEY", "s", raising=False)
    monkeypatch.setattr(settings, "MODAL_LTX_URL", "http://m", raising=False)
    assert service.compute_status()["complete"] is False
    # TikTok missing alone does NOT force the wizard (posting-time only).
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "a", raising=False)
    monkeypatch.setattr(settings, "TIKTOK_ACCESS_TOKEN", "", raising=False)
    assert service.compute_status()["complete"] is True


# --- provider probes (no network) ------------------------------------------- #

def test_test_provider_unknown():
    assert service.test_provider("bogus")["ok"] is False


def test_test_video_ok(monkeypatch):
    monkeypatch.setattr(settings, "MODAL_LTX_URL", "http://modal", raising=False)
    monkeypatch.setattr(settings, "MODAL_LTX_TOKEN", "tok", raising=False)

    class _Resp:
        status_code = 200
        def json(self): return {"ok": True, "model": "ltx"}

    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, **kw): return _Resp()

    monkeypatch.setattr(service.httpx, "Client", _Client)
    res = service.test_provider("video")
    assert res["ok"] is True and "latency_ms" in res


def test_test_tiktok_bad_token(monkeypatch):
    monkeypatch.setattr(settings, "TIKTOK_ACCESS_TOKEN", "t", raising=False)
    monkeypatch.setattr(settings, "TIKTOK_API_BASE", "https://open.tiktokapis.com", raising=False)

    class _Resp:
        status_code = 401
        def json(self): return {}

    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, **kw): return _Resp()

    monkeypatch.setattr(service.httpx, "Client", _Client)
    res = service.test_provider("tiktok")
    assert res["ok"] is False and "token" in res["error"].lower()
