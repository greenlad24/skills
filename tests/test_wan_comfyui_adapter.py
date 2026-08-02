"""Unit tests for the free Wan/ComfyUI video adapter (no network, no GPU).

We monkeypatch httpx.Client with a tiny fake that mimics the ComfyUI HTTP API
(/upload/image, /prompt, /history/{id}, /view) so the full submit -> poll ->
download flow is exercised deterministically.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.adapters.real import wan_comfyui as mod
from app.core.config import settings


# --- pure helpers ----------------------------------------------------------- #

def test_substitute_tokens_keep_native_types():
    graph = {"n": {"inputs": {"length": "__FRAMES__", "text": "hi __PROMPT__"}}}
    out = mod._substitute(graph, {"__FRAMES__": 48, "__PROMPT__": "cordless"})
    assert out["n"]["inputs"]["length"] == 48                # whole-value → int
    assert out["n"]["inputs"]["text"] == "hi cordless"       # inline → substring


def test_find_output_prefers_video_file():
    outputs = {
        "40": {"gifs": [{"filename": "autougc_broll_0001.mp4", "subfolder": "", "type": "output"}]},
        "22": {"images": [{"filename": "preview.png"}]},
    }
    ref = mod.WanComfyUIVideoProvider._find_output(outputs)
    assert ref["filename"] == "autougc_broll_0001.mp4"


# --- adapter flow with a fake ComfyUI HTTP client --------------------------- #

class _Resp:
    def __init__(self, *, json_data=None, content=b""):
        self._json = json_data
        self.content = content
    def raise_for_status(self): pass
    def json(self): return self._json


class _FakeClient:
    """Stands in for httpx.Client; routes by path. Shared state via class attrs."""
    posted_prompt = None

    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False

    def post(self, path, **kw):
        if path == "/upload/image":
            return _Resp(json_data={"name": "prod.png", "type": "input"})
        if path == "/prompt":
            _FakeClient.posted_prompt = kw.get("json", {}).get("prompt")
            return _Resp(json_data={"prompt_id": "pid-123", "number": 1})
        raise AssertionError(f"unexpected POST {path}")

    def get(self, path, **kw):
        if path == "/history/pid-123":
            return _Resp(json_data={"pid-123": {
                "status": {"completed": True, "status_str": "success"},
                "outputs": {"40": {"gifs": [
                    {"filename": "autougc_broll_0001.mp4", "subfolder": "", "type": "output"}]}},
            }})
        if path == "/view":
            return _Resp(content=b"FAKEMP4BYTES")
        raise AssertionError(f"unexpected GET {path}")


@pytest.fixture
def wan(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "COMFYUI_URL", "http://fake-comfyui:8188", raising=False)
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path), raising=False)
    monkeypatch.setattr(mod.httpx, "Client", _FakeClient)
    # A product image on disk to upload.
    img = tmp_path / "product.png"
    img.write_bytes(b"PNGDATA")
    prov = mod.WanComfyUIVideoProvider()
    return prov, str(img), tmp_path


def test_hero_image_passthrough_is_free(wan):
    prov, img, _ = wan
    res = prov.generate_hero_image(prompt="pink tray", refs=[img], idempotency_key="k")
    assert res.ok and res.cost_usd == 0.0
    assert res.data["image_key"] == img          # real product photo passed through


def test_hero_requires_a_ref(wan):
    prov, _, _ = wan
    res = prov.generate_hero_image(prompt="x", refs=[], idempotency_key="k")
    assert res.ok is False and "reference image" in (res.error or "")


def test_submit_then_poll_downloads_video(wan):
    prov, img, tmp_path = wan
    sub = prov.submit_image_to_video(
        image_key=img, prompt="flex the tray", model="wan", seconds=3.0,
        aspect="9:16", idempotency_key="idem-1",
    )
    assert sub.ok and sub.provider_job_id == "pid-123"
    assert sub.cost_usd == 0.0                    # free
    assert sub.usage["frames"] == 48              # 3s * 16fps
    # The workflow placeholders were substituted before submission.
    graph = _FakeClient.posted_prompt
    assert graph["10"]["inputs"]["image"] == "prod.png"
    assert graph["20"]["inputs"]["length"] == 48
    assert graph["20"]["inputs"]["width"] == 480 and graph["20"]["inputs"]["height"] == 832

    poll = prov.poll(provider_job_id="pid-123")
    assert poll.ok and poll.data["status"] == "ready"
    out = Path(poll.data["video_key"])
    assert out.exists() and out.read_bytes() == b"FAKEMP4BYTES"


def test_poll_before_ready_reports_processing(monkeypatch, wan):
    prov, _, _ = wan

    class _Pending(_FakeClient):
        def get(self, path, **kw):
            if path.startswith("/history/"):
                return _Resp(json_data={})        # not in history yet
            return super().get(path, **kw)

    monkeypatch.setattr(mod.httpx, "Client", _Pending)
    poll = prov.poll(provider_job_id="pid-123")
    assert poll.ok and poll.data["status"] == "processing"


def test_missing_url_raises(monkeypatch):
    monkeypatch.setattr(settings, "COMFYUI_URL", "", raising=False)
    with pytest.raises(RuntimeError):
        mod.WanComfyUIVideoProvider()
