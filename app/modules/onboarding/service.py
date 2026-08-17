"""Onboarding logic: compute setup status and live-test each approved provider.

The approved stack has exactly three things to configure:
  * keys   — Anthropic (LLM for research + scripting) + Google Cloud TTS (Thai voice)
             + Apify (product/TikTok scraper that returns the product image)
  * video  — LTX-2.5 on Modal (MODAL_LTX_URL [+ token])
  * tiktok — TikTok Content Posting access token
"""

from __future__ import annotations

import time

import httpx

from app.core.config import settings
from app.modules.onboarding import env_store


def compute_status() -> dict:
    """Which setup steps are satisfied, and whether onboarding is complete."""
    keys_ok = (
        bool(settings.ANTHROPIC_API_KEY)
        and bool(settings.GOOGLE_TTS_API_KEY)
        and bool(settings.APIFY_API_KEY)
    )
    video_ok = bool(settings.MODAL_LTX_URL)
    tiktok_ok = bool(settings.TIKTOK_ACCESS_TOKEN)
    steps = {"keys": keys_ok, "video": video_ok, "tiktok": tiktok_ok}
    complete = bool(settings.ONBOARDED) or all(steps.values())
    return {"complete": complete, "steps": steps, "dry_run": settings.DRY_RUN}


def save(values: dict[str, str]) -> dict:
    """Persist whitelisted keys to .env + live settings; report the outcome."""
    result = env_store.save(values)
    result["restart_required"] = False   # apply_live updates the running process
    return result


def mark_complete() -> dict:
    """Flip the app out of first-run: persist ONBOARDED + turn DRY_RUN off (go live)."""
    env_store.save({"ONBOARDED": "true", "DRY_RUN": "false"})
    return {"complete": True}


def test_provider(provider: str) -> dict:
    """Live-test one provider with the currently-saved credentials."""
    t0 = time.monotonic()
    try:
        if provider == "llm":
            ok, err = _test_llm()
        elif provider == "tts":
            ok, err = _test_tts()
        elif provider == "scraper":
            ok, err = _test_scraper()
        elif provider == "video":
            ok, err = _test_video()
        elif provider == "tiktok":
            ok, err = _test_tiktok()
        else:
            return {"ok": False, "error": f"unknown provider {provider!r}"}
    except Exception as exc:  # noqa: BLE001 — any failure is a failed test, not a 500
        return {"ok": False, "error": str(exc)}

    out: dict = {"ok": bool(ok), "latency_ms": int((time.monotonic() - t0) * 1000)}
    if not ok and err:
        out["error"] = err
    return out


# --- per-provider probes ---------------------------------------------------- #

def _test_llm() -> tuple[bool, str | None]:
    from app.core.adapters.real.anthropic_llm import AnthropicLLMProvider

    res = AnthropicLLMProvider().complete(
        prompt="Reply with the single word OK.", system=None,
        model="claude-haiku-4-5", max_tokens=5, idempotency_key="onboarding-llm-test",
    )
    return res.ok, res.error


def _test_tts() -> tuple[bool, str | None]:
    from app.core.adapters.real.google_tts import GoogleTTSProvider

    res = GoogleTTSProvider().synthesize(
        text="ทดสอบ", voice_id="", language="", model="",
        idempotency_key="onboarding-tts-test",
    )
    return res.ok, res.error


def _test_scraper() -> tuple[bool, str | None]:
    if not settings.APIFY_API_KEY:
        return False, "APIFY_API_KEY is not set"
    # Cheap auth check: list the user's actors (no actor run, no credits spent).
    with httpx.Client(timeout=30) as c:
        r = c.get(
            "https://api.apify.com/v2/users/me",
            params={"token": settings.APIFY_API_KEY},
        )
    if r.status_code == 200:
        return True, None
    if r.status_code in (401, 403):
        return False, "Apify token rejected (check the token in your account settings)"
    return False, f"Apify /users/me returned {r.status_code}"


def _test_video() -> tuple[bool, str | None]:
    if not settings.MODAL_LTX_URL:
        return False, "MODAL_LTX_URL is not set"
    headers = {"X-LTX-Token": settings.MODAL_LTX_TOKEN} if settings.MODAL_LTX_TOKEN else {}
    with httpx.Client(timeout=30) as c:
        r = c.get(settings.MODAL_LTX_URL.rstrip("/") + "/health", headers=headers)
    if r.status_code == 200 and (r.json() or {}).get("ok"):
        return True, None
    return False, f"health check returned {r.status_code}"


def _test_tiktok() -> tuple[bool, str | None]:
    if not settings.TIKTOK_ACCESS_TOKEN:
        return False, "TIKTOK_ACCESS_TOKEN is not set"
    base = settings.TIKTOK_API_BASE.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.TIKTOK_ACCESS_TOKEN}"}
    with httpx.Client(timeout=30, headers=headers) as c:
        r = c.post(base + "/v2/post/publish/creator_info/query/")
    if r.status_code == 200:
        return True, None
    if r.status_code in (401, 403):
        return False, "token rejected (check scope: video.publish / video.upload)"
    return False, f"creator_info returned {r.status_code}"
