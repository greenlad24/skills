"""Unit tests for the TikTok Content Posting API adapter (no network)."""

from __future__ import annotations

import pytest

from app.core.adapters.real import tiktok_posting as mod
from app.core.config import settings


class _Resp:
    def __init__(self, *, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}
    def raise_for_status(self):
        if self.status_code >= 400:
            raise mod.httpx.HTTPStatusError("err", request=None, response=None)
    def json(self):
        return self._json


class _FakeClient:
    """Routes the creator_info / init / status calls; records the init body + PUT."""
    calls: list = []
    put_headers = None
    privacy_options = ["PUBLIC_TO_EVERYONE", "SELF_ONLY"]

    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False

    def post(self, path, **kw):
        _FakeClient.calls.append((path, kw.get("json")))
        if path.endswith("/creator_info/query/"):
            return _Resp(json_data={"data": {"privacy_level_options": _FakeClient.privacy_options}})
        if path.endswith("/video/init/"):
            return _Resp(json_data={"data": {"publish_id": "pub-999", "upload_url": "https://upload.tiktok/xyz"}})
        if path.endswith("/status/fetch/"):
            return _Resp(json_data={"data": {"status": "PROCESSING_DOWNLOAD"}})
        raise AssertionError(f"unexpected POST {path}")

    def put(self, url, **kw):
        _FakeClient.put_headers = kw.get("headers")
        return _Resp()


@pytest.fixture
def tt(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "TIKTOK_ACCESS_TOKEN", "tok-abc", raising=False)
    monkeypatch.setattr(settings, "TIKTOK_API_BASE", "https://open.tiktokapis.com", raising=False)
    monkeypatch.setattr(settings, "TIKTOK_POSTING_MODE", "direct", raising=False)
    monkeypatch.setattr(settings, "TIKTOK_PRIVACY_LEVEL", "", raising=False)
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path), raising=False)
    monkeypatch.setattr(mod.httpx, "Client", _FakeClient)
    _FakeClient.calls = []
    _FakeClient.put_headers = None
    _FakeClient.privacy_options = ["PUBLIC_TO_EVERYONE", "SELF_ONLY"]
    vid = tmp_path / "clip.mp4"
    vid.write_bytes(b"MP4BYTES")
    return str(vid)


def _paths():
    return [p for p, _ in _FakeClient.calls]


def test_direct_publish_sets_aigc_and_uploads(tt):
    prov = mod.TikTokPostingProvider()
    res = prov.publish(
        video_key=tt, caption="รีวิวสินค้า #fyp", platform="tiktok",
        ai_disclosure=True, schedule_at=None, idempotency_key="k1",
    )
    assert res.ok and res.cost_usd == 0.0
    assert res.data["external_post_id"] == "pub-999"
    assert res.data["ai_disclosure_set"] is True
    # creator_info was queried, then init carried is_aigc + a real privacy level.
    assert any(p.endswith("/creator_info/query/") for p in _paths())
    init_body = next(b for p, b in _FakeClient.calls if p.endswith("/video/init/"))
    assert init_body["post_info"]["is_aigc"] is True
    assert init_body["post_info"]["privacy_level"] == "PUBLIC_TO_EVERYONE"
    assert init_body["source_info"]["video_size"] == len(b"MP4BYTES")
    # The video bytes were PUT with a correct content range.
    assert _FakeClient.put_headers["Content-Type"] == "video/mp4"
    assert _FakeClient.put_headers["Content-Range"] == "bytes 0-7/8"


def test_explicit_privacy_skips_creator_info(tt, monkeypatch):
    monkeypatch.setattr(settings, "TIKTOK_PRIVACY_LEVEL", "SELF_ONLY", raising=False)
    prov = mod.TikTokPostingProvider()
    prov.publish(video_key=tt, caption="c", platform="tiktok",
                 ai_disclosure=False, schedule_at=None, idempotency_key="k2")
    assert not any(p.endswith("/creator_info/query/") for p in _paths())
    init_body = next(b for p, b in _FakeClient.calls if p.endswith("/video/init/"))
    assert init_body["post_info"]["privacy_level"] == "SELF_ONLY"
    assert init_body["post_info"]["is_aigc"] is False


def test_inbox_mode_uses_inbox_endpoint_without_post_info(tt, monkeypatch):
    monkeypatch.setattr(settings, "TIKTOK_POSTING_MODE", "inbox", raising=False)
    prov = mod.TikTokPostingProvider()
    res = prov.publish(video_key=tt, caption="c", platform="tiktok",
                       ai_disclosure=True, schedule_at=None, idempotency_key="k3")
    assert res.ok
    assert any(p.endswith("/inbox/video/init/") for p in _paths())
    init_body = next(b for p, b in _FakeClient.calls if p.endswith("/inbox/video/init/"))
    assert "post_info" not in init_body


def test_schedule_at_is_recorded_not_honored(tt):
    prov = mod.TikTokPostingProvider()
    res = prov.publish(video_key=tt, caption="c", platform="tiktok",
                       ai_disclosure=False, schedule_at="2026-09-01T10:00:00Z",
                       idempotency_key="k4")
    assert res.data["schedule_ignored"] == "2026-09-01T10:00:00Z"


def test_fetch_metrics_reports_unsupported(tt):
    prov = mod.TikTokPostingProvider()
    res = prov.fetch_metrics(external_post_id="pub-999")
    assert res.ok is False
    assert res.data["publish_status"] == "PROCESSING_DOWNLOAD"
    assert "metrics" in (res.error or "").lower()


def test_missing_token_raises(monkeypatch):
    monkeypatch.setattr(settings, "TIKTOK_ACCESS_TOKEN", "", raising=False)
    with pytest.raises(RuntimeError):
        mod.TikTokPostingProvider()
