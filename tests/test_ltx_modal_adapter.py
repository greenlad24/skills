"""Unit tests for the serverless LTX-2.5 / Modal video adapter (no network, no GPU).

We monkeypatch httpx.Client with a tiny fake that mimics the Modal web app's
submit/poll contract (POST /submit, GET /result/{id}) so the full submit -> poll
-> save flow is exercised deterministically.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from app.core.adapters.real import ltx_modal as mod
from app.core.config import settings


# --- pure helpers ----------------------------------------------------------- #

def test_snap_frames_is_valid_ltx_length():
    # (num_frames - 1) must be divisible by 8.
    for seconds in (1, 2, 3.0, 4, 5.5):
        n = mod._snap_frames(seconds, 24)
        assert (n - 1) % 8 == 0 and n >= 9


def test_snap_frames_scales_with_seconds():
    assert mod._snap_frames(4, 24) > mod._snap_frames(2, 24)


# --- adapter flow with a fake Modal HTTP client ----------------------------- #

_FAKE_MP4 = b"FAKEMP4BYTES"


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
    """Stands in for httpx.Client; routes by path. Shared state via class attrs."""
    posted_payload = None
    result_ready = True   # flip to False to simulate a still-rendering poll

    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False

    def post(self, path, **kw):
        if path == "/submit":
            _FakeClient.posted_payload = kw.get("json", {})
            return _Resp(json_data={"call_id": "fc-123"})
        raise AssertionError(f"unexpected POST {path}")

    def get(self, path, **kw):
        if path.startswith("/result/"):
            if not _FakeClient.result_ready:
                return _Resp(status_code=202, json_data={"status": "processing"})
            return _Resp(json_data={
                "status": "ready",
                "video_b64": base64.b64encode(_FAKE_MP4).decode("ascii"),
                "compute_seconds": 90.0,
            })
        raise AssertionError(f"unexpected GET {path}")


@pytest.fixture
def ltx(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "MODAL_LTX_URL", "https://fake--autougc-ltx-web.modal.run", raising=False)
    monkeypatch.setattr(settings, "MODAL_LTX_TOKEN", "secret-token", raising=False)
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "MODAL_GPU_USD_PER_SEC", 0.000306, raising=False)
    monkeypatch.setattr(settings, "MODAL_LTX_EST_SECONDS_PER_CLIP", 90.0, raising=False)
    monkeypatch.setattr(mod.httpx, "Client", _FakeClient)
    _FakeClient.result_ready = True
    img = tmp_path / "product.png"
    img.write_bytes(b"PNGDATA")
    prov = mod.LTXModalVideoProvider()
    return prov, str(img), tmp_path


def test_hero_image_passthrough_is_free(ltx):
    prov, img, _ = ltx
    res = prov.generate_hero_image(prompt="pink tray", refs=[img], idempotency_key="k")
    assert res.ok and res.cost_usd == 0.0
    assert res.data["image_key"] == img          # real product photo passed through


def test_hero_requires_a_ref(ltx):
    prov, _, _ = ltx
    res = prov.generate_hero_image(prompt="x", refs=[], idempotency_key="k")
    assert res.ok is False and "reference image" in (res.error or "")


def test_submit_encodes_image_and_snaps_frames(ltx):
    prov, img, _ = ltx
    sub = prov.submit_image_to_video(
        image_key=img, prompt="flex the tray", model="ltx-2.5", seconds=4.0,
        aspect="9:16", idempotency_key="idem-1",
    )
    assert sub.ok and sub.provider_job_id == "fc-123"
    # Cost is billed at submit (pipeline convention) from the render-time estimate.
    assert sub.cost_usd == pytest.approx(90.0 * 0.000306, rel=1e-6)
    payload = _FakeClient.posted_payload
    # Image was base64-encoded and 9:16 mapped to 480x832.
    assert base64.b64decode(payload["image_b64"]) == b"PNGDATA"
    assert payload["width"] == 480 and payload["height"] == 832
    assert (payload["num_frames"] - 1) % 8 == 0


def test_poll_ready_saves_video_and_records_cost(ltx):
    prov, img, tmp_path = ltx
    sub = prov.submit_image_to_video(
        image_key=img, prompt="p", model="ltx-2.5", seconds=4.0,
        aspect="9:16", idempotency_key="idem-1",
    )
    poll = prov.poll(provider_job_id=sub.provider_job_id)
    assert poll.ok and poll.data["status"] == "ready"
    out = Path(poll.data["video_key"])
    assert out.exists() and out.read_bytes() == _FAKE_MP4
    # Poll does not double-charge; it reports the ACTUAL compute cost in usage.
    assert poll.cost_usd == 0.0
    assert poll.usage["compute_seconds"] == 90.0
    assert poll.usage["actual_usd"] == pytest.approx(90.0 * 0.000306, rel=1e-6)


def test_poll_before_ready_reports_processing(ltx):
    prov, _, _ = ltx
    _FakeClient.result_ready = False
    poll = prov.poll(provider_job_id="fc-123")
    assert poll.ok and poll.data["status"] == "processing"


def test_missing_url_raises(monkeypatch):
    monkeypatch.setattr(settings, "MODAL_LTX_URL", "", raising=False)
    with pytest.raises(RuntimeError):
        mod.LTXModalVideoProvider()
