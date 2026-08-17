"""Onboarding logic: compute setup status and live-test each approved provider.

The approved stack has exactly three things to configure:
  * keys   — Anthropic (LLM for research + scripting) + Google Cloud TTS (Thai voice)
             + SocialCrawl (TikTok Shop TH search → product title, image, THB price)
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
        and bool(settings.SOCIALCRAWL_API_KEY)
    )
    video_ok = bool(settings.MODAL_LTX_URL)
    tiktok_ok = bool(settings.TIKTOK_ACCESS_TOKEN)
    steps = {"keys": keys_ok, "video": video_ok, "tiktok": tiktok_ok}
    # The pipeline can't run without the keys + a video engine, so the wizard is
    # forced whenever either is missing — even after first-run onboarding (e.g. a key
    # was removed). TikTok posting is only needed at the posting stage, so it stays
    # optional for this gate. DRY_RUN (fakes) needs no real keys.
    required_ok = keys_ok and video_ok
    complete = bool(settings.DRY_RUN) or required_ok
    # Per-field presence so the wizard can show "already set" and only ask for what's
    # missing (values are never returned — just whether each is configured).
    configured = {
        "ANTHROPIC_API_KEY": bool(settings.ANTHROPIC_API_KEY),
        "GOOGLE_TTS_API_KEY": bool(settings.GOOGLE_TTS_API_KEY),
        "SOCIALCRAWL_API_KEY": bool(settings.SOCIALCRAWL_API_KEY),
        "MODAL_LTX_URL": bool(settings.MODAL_LTX_URL),
        "MODAL_LTX_TOKEN": bool(settings.MODAL_LTX_TOKEN),
        "TIKTOK_ACCESS_TOKEN": bool(settings.TIKTOK_ACCESS_TOKEN),
    }
    return {
        "complete": complete,
        "steps": steps,
        "configured": configured,
        "dry_run": settings.DRY_RUN,
        "onboarded": bool(settings.ONBOARDED),
    }


# The single approved provider stack — pinned so a stale .env (e.g. a leftover
# SCRAPER_PROVIDER=firecrawl) can't silently route to a provider with no real adapter.
_APPROVED_STACK = {
    "LLM_PROVIDER": "anthropic",
    "SCRAPER_PROVIDER": "socialcrawl",
    "TTS_PROVIDER": "google_tts",
    "VIDEOGEN_PROVIDER": "ltx_modal",
    "POSTING_PROVIDER": "tiktok",
}


def save(values: dict[str, str]) -> dict:
    """Persist whitelisted keys to .env + live settings; report the outcome.

    Adding the SocialCrawl key also selects it as the scraper, so configuring the
    key is all it takes to use it (correcting an older .env that pinned firecrawl).
    """
    vals = dict(values)
    if str(vals.get("SOCIALCRAWL_API_KEY", "")).strip() and "SCRAPER_PROVIDER" not in vals:
        vals["SCRAPER_PROVIDER"] = "socialcrawl"
    result = env_store.save(vals)
    result["restart_required"] = False   # apply_live updates the running process
    return result


def mark_complete() -> dict:
    """Flip the app out of first-run: pin the approved stack, ONBOARDED, DRY_RUN off."""
    env_store.save({"ONBOARDED": "true", "DRY_RUN": "false", **_APPROVED_STACK})
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
    if not settings.SOCIALCRAWL_API_KEY:
        return False, "SOCIALCRAWL_API_KEY is not set"
    # Free auth check: read the credit balance (spends no search credits).
    base = settings.SOCIALCRAWL_BASE.rstrip("/")
    with httpx.Client(timeout=30, headers={"x-api-key": settings.SOCIALCRAWL_API_KEY}) as c:
        r = c.get(f"{base}/credits/balance")
    if r.status_code == 200:
        return True, None
    if r.status_code in (401, 403):
        return False, "SocialCrawl key rejected (check the key in your dashboard)"
    return False, f"SocialCrawl /credits/balance returned {r.status_code}"


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
