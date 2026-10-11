import plistlib
import stat
import zipfile

from mac import build_app


def test_mac_app_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(build_app, "OUT_DIR", tmp_path)
    out = build_app.build()
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        app = "Thai TikTok Studio.app/Contents/"
        assert app + "MacOS/launcher" in names and app + "Resources/AppIcon.icns" in names
        assert app + "Resources/app/studio/app.py" in names
        assert not any("__pycache__" in n for n in names)
        launcher = z.getinfo(app + "MacOS/launcher")
        assert (launcher.external_attr >> 16) & stat.S_IXUSR          # executable bit survives unzip
        plist = plistlib.loads(z.read(app + "Info.plist"))
        assert plist["CFBundleExecutable"] == "launcher" and plist["LSMinimumSystemVersion"] == "10.13"
        reqs = z.read(app + "Resources/app/requirements-mac.txt").decode()
        assert "pywebview" in reqs and "flask" in reqs
        assert z.read(app + "Resources/AppIcon.icns")[:4] == b"icns"
