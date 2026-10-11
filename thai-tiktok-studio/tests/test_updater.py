"""Self-update: a newer published version is downloaded, verified and selected."""

import importlib
import io
import json
import zipfile

import pytest


class Resp:
    def __init__(self, content=b"", js=None, status=200):
        self.content, self._js, self.status_code = content, js, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._js

    headers = {}

    def iter_content(self, n):
        for i in range(0, len(self.content), n):
            yield self.content[i:i + n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _zip(version: str, complete=True) -> bytes:
    buf = io.BytesIO()
    pre = "Thai TikTok Studio.app/Contents/Resources/app/"
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(pre + "VERSION", version)
        if complete:
            z.writestr(pre + "studio/app.py", "# app")
        z.writestr(pre + "../../evil.txt", "nope")
        z.writestr("Thai TikTok Studio.app/Contents/MacOS/launcher", "#!/bin/bash")
    return buf.getvalue()


@pytest.fixture()
def up(tmp_path, monkeypatch):
    monkeypatch.setenv("TTS_STUDIO_SUPPORT", str(tmp_path))
    import studio.updater as updater
    importlib.reload(updater)
    return updater, tmp_path


def test_newer_version_installs(up, monkeypatch):
    updater, d = up
    monkeypatch.setattr(updater, "__version__", "1.1.0")
    calls = iter([Resp(js={"version": "1.2.0", "zip_url": "https://x/z.zip", "notes": "faster"}), Resp(_zip("1.2.0"))])
    monkeypatch.setattr(updater.requests, "get", lambda *a, **k: next(calls))
    st = updater.check_and_download()
    assert st["ready"] == "1.2.0" and not st["error"]
    assert (d / "app-1.2.0" / "studio" / "app.py").exists()
    assert (d / "current.txt").read_text() == "app-1.2.0"
    assert not (d / "evil.txt").exists() and not list(d.rglob("evil.txt"))     # no path escapes


def test_same_or_older_version_does_nothing(up, monkeypatch):
    updater, d = up
    monkeypatch.setattr(updater, "__version__", "1.2.0")
    monkeypatch.setattr(updater.requests, "get", lambda *a, **k: Resp(js={"version": "1.2.0", "zip_url": "z"}))
    assert updater.check_and_download()["ready"] == "" and not (d / "current.txt").exists()


def test_broken_download_is_ignored(up, monkeypatch):
    updater, d = up
    monkeypatch.setattr(updater, "__version__", "1.1.0")
    calls = iter([Resp(js={"version": "1.3.0", "zip_url": "z"}), Resp(_zip("1.3.0", complete=False))])
    monkeypatch.setattr(updater.requests, "get", lambda *a, **k: next(calls))
    st = updater.check_and_download()
    assert st["ready"] == "" and "incomplete" in st["error"] and not (d / "current.txt").exists()


def test_version_compare():
    from studio.updater import vtuple
    assert vtuple("1.10.0") > vtuple("1.9.9") > vtuple("1.9") and vtuple("2") == (2, 0, 0)


def test_build_writes_latest_json(tmp_path, monkeypatch):
    from mac import build_app
    monkeypatch.setattr(build_app, "OUT_DIR", tmp_path)
    out = build_app.build()
    latest = json.loads((tmp_path / "latest.json").read_text())
    from studio import __version__
    assert latest["version"] == __version__ and latest["zip_url"].endswith("ThaiTikTokStudio-mac.zip")
    with zipfile.ZipFile(out) as z:
        assert z.read("Thai TikTok Studio.app/Contents/Resources/app/VERSION").decode() == __version__
