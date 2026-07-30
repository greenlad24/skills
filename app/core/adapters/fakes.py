"""Deterministic Fake providers for DRY_RUN / tests — zero network, zero spend.

Every Fake:
  * makes NO network calls and incurs NO real cost;
  * returns a deterministic `ProviderResult` derived from its inputs (so the same
    idempotency_key always yields the same fake output);
  * reports a *simulated* `cost_usd` so the cost-ledger/budget machinery can be
    exercised end-to-end for $0.

These back the P5 "$0 dry-run mode" acceptance requirement. Every adapter honors
DRY_RUN by being swapped for its Fake in registry.py.
"""

from __future__ import annotations

import hashlib

from app.core.adapters.base import ProviderResult


def _det_hex(*parts: str) -> str:
    """Deterministic short hash from inputs — used to fabricate stable fake IDs/keys."""
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return h[:16]


class FakeLLMProvider:
    provider_name = "fake-llm"

    def complete(
        self, *, prompt: str, system: str | None, model: str, max_tokens: int,
        idempotency_key: str,
    ) -> ProviderResult:
        digest = _det_hex(model, idempotency_key, prompt[:64])
        return ProviderResult(
            ok=True,
            data={
                "text": f"[FAKE-{model}] deterministic completion {digest}",
                "model": model,
            },
            cost_usd=0.01,
            usage={"input_tokens": len(prompt.split()), "output_tokens": 32},
        )


class FakeScraperProvider:
    provider_name = "fake-scraper"

    def scrape_product(self, *, url: str, idempotency_key: str) -> ProviderResult:
        digest = _det_hex(url, idempotency_key)
        return ProviderResult(
            ok=True,
            data={
                "source_url": url,
                "title": f"Fake Product {digest}",
                "brand": "FakeBrand",
                "price": 199.0,
                "currency": "THB",
                "attributes": {"features": ["fake-feature-1", "fake-feature-2"], "images": []},
            },
            cost_usd=0.005,
            usage={"requests": 1},
        )

    def mine_top_videos(
        self, *, query: str, market: str, limit: int, idempotency_key: str
    ) -> ProviderResult:
        vids = [
            {
                "tiktok_id": _det_hex(query, market, str(i)),
                "url": f"https://tiktok.com/@fake/video/{i}",
                "views": 1_000_000 - i * 1000,
                "signal_type": "engagement_proxy",
            }
            for i in range(min(limit, 5))
        ]
        return ProviderResult(
            ok=True, data={"videos": vids}, cost_usd=0.02, usage={"videos": len(vids)}
        )


class FakeTTSProvider:
    provider_name = "fake-tts"

    def synthesize(
        self, *, text: str, voice_id: str, language: str, model: str, idempotency_key: str
    ) -> ProviderResult:
        digest = _det_hex(voice_id, model, idempotency_key)
        # ~0.06s per character is a stable, plausible fake duration.
        duration = round(len(text) * 0.06, 2)
        return ProviderResult(
            ok=True,
            data={
                "audio_key": f"fake/tts/{digest}.mp3",
                "duration_sec": duration,
                "mime_type": "audio/mpeg",
            },
            cost_usd=0.05,
            usage={"characters": len(text), "seconds": duration},
        )


class FakeAvatarProvider:
    provider_name = "fake-avatar"

    def submit_talking_head(
        self, *, avatar_id: str, audio_key: str, script_text: str, aspect: str,
        idempotency_key: str,
    ) -> ProviderResult:
        job_id = f"fake-avatar-{_det_hex(avatar_id, idempotency_key)}"
        return ProviderResult(
            ok=True,
            data={"status": "processing", "aspect": aspect},
            cost_usd=0.30,
            usage={"seconds": 15},
            provider_job_id=job_id,
        )

    def poll(self, *, provider_job_id: str) -> ProviderResult:
        # Fakes complete immediately and deterministically.
        return ProviderResult(
            ok=True,
            data={
                "status": "ready",
                "video_key": f"fake/avatar/{provider_job_id}.mp4",
                "mime_type": "video/mp4",
            },
            cost_usd=0.0,
            usage={},
            provider_job_id=provider_job_id,
        )


class FakeVideoGenProvider:
    provider_name = "fake-videogen"

    def generate_hero_image(
        self, *, prompt: str, refs: list[str], idempotency_key: str
    ) -> ProviderResult:
        digest = _det_hex(prompt[:64], idempotency_key)
        return ProviderResult(
            ok=True,
            data={
                "image_key": f"fake/hero/{digest}.png",
                "mime_type": "image/png",
                "seed": int(digest[:6], 16),
            },
            cost_usd=0.03,
            usage={"images": 1},
        )

    def submit_image_to_video(
        self, *, image_key: str, prompt: str, model: str, seconds: float, aspect: str,
        idempotency_key: str,
    ) -> ProviderResult:
        job_id = f"fake-i2v-{_det_hex(image_key, model, idempotency_key)}"
        return ProviderResult(
            ok=True,
            data={"status": "processing", "model": model, "seconds": seconds, "aspect": aspect},
            cost_usd=2.28,
            usage={"seconds": seconds},
            provider_job_id=job_id,
        )

    def poll(self, *, provider_job_id: str) -> ProviderResult:
        return ProviderResult(
            ok=True,
            data={
                "status": "ready",
                "video_key": f"fake/broll/{provider_job_id}.mp4",
                "mime_type": "video/mp4",
            },
            cost_usd=0.0,
            usage={},
            provider_job_id=provider_job_id,
        )


class FakePostingProvider:
    provider_name = "fake-posting"

    def publish(
        self, *, video_key: str, caption: str, platform: str, ai_disclosure: bool,
        schedule_at: str | None, idempotency_key: str,
    ) -> ProviderResult:
        post_id = f"fake-post-{_det_hex(video_key, idempotency_key)}"
        return ProviderResult(
            ok=True,
            data={
                "external_post_id": post_id,
                "post_url": f"https://tiktok.com/@operator/video/{post_id}",
                "deep_link": f"tiktok://video/{post_id}",
                "ai_disclosure_set": ai_disclosure,
                "platform": platform,
            },
            cost_usd=0.0,
            usage={},
            provider_job_id=post_id,
        )

    def fetch_metrics(self, *, external_post_id: str) -> ProviderResult:
        seed = int(_det_hex(external_post_id), 16)
        return ProviderResult(
            ok=True,
            data={
                "views": seed % 50000,
                "likes": seed % 5000,
                "comments": seed % 500,
                "shares": seed % 300,
                "source": "fake_analytics",
            },
            cost_usd=0.0,
            usage={},
        )


# Map capability -> Fake class, consumed by registry.py.
FAKE_PROVIDERS = {
    "llm": FakeLLMProvider,
    "scraper": FakeScraperProvider,
    "tts": FakeTTSProvider,
    "avatar": FakeAvatarProvider,
    "videogen": FakeVideoGenProvider,
    "posting": FakePostingProvider,
}
