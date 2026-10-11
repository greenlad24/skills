"""Build "Thai TikTok Studio.app" (and a .zip to download) — runs on any OS.

    python mac/build_app.py      →  releases/ThaiTikTokStudio-mac.zip

The bundle holds a small bash launcher + the app's Python source. On first launch it
creates its own Python environment in ~/Library/Application Support/ThaiTikTokStudio.
"""

from __future__ import annotations

import shutil
import stat
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studio import __version__  # noqa: E402

APP_NAME = "Thai TikTok Studio"
BUNDLE_ID = "com.thaitiktokstudio.app"
OUT_DIR = ROOT / "releases"

PLIST = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>{APP_NAME}</string>
  <key>CFBundleDisplayName</key><string>{APP_NAME}</string>
  <key>CFBundleIdentifier</key><string>{BUNDLE_ID}</string>
  <key>CFBundleVersion</key><string>{__version__}</string>
  <key>CFBundleShortVersionString</key><string>{__version__}</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>launcher</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>10.13</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.video</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSLocalNetworkUsageDescription</key><string>Receive videos from your phone over Wi-Fi.</string>
</dict></plist>
"""


def make_icon(size: int = 1024):
    from PIL import Image, ImageDraw, ImageFilter
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):  # cyan → pink diagonal-ish gradient
        t = y / size
        gd.line([(0, y), (size, y)], fill=(int(37 + (254 - 37) * t), int(244 + (44 - 244) * t), int(238 + (85 - 238) * t), 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([size * 0.08, size * 0.08, size * 0.92, size * 0.92], radius=size * 0.2, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    s = size
    tri = [(s * 0.40, s * 0.30), (s * 0.40, s * 0.70), (s * 0.72, s * 0.50)]
    shadow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).polygon([(x + s * 0.01, y + s * 0.015) for x, y in tri], fill=(0, 0, 0, 110))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(s * 0.012)))
    d.polygon(tri, fill=(255, 255, 255, 255))
    return img


def _copy_source(dst: Path) -> None:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
    shutil.copytree(ROOT / "studio", dst / "studio", ignore=ignore)
    reqs = (ROOT / "requirements.txt").read_text()
    (dst / "requirements-mac.txt").write_text(reqs.rstrip() + "\npywebview>=5.0\n")


def build() -> Path:
    OUT_DIR.mkdir(exist_ok=True)
    stage = OUT_DIR / "_build"
    shutil.rmtree(stage, ignore_errors=True)
    app = stage / f"{APP_NAME}.app"
    (app / "Contents/MacOS").mkdir(parents=True)
    (app / "Contents/Resources").mkdir(parents=True)
    (app / "Contents/Info.plist").write_text(PLIST)
    (app / "Contents/PkgInfo").write_text("APPL????")
    launcher = app / "Contents/MacOS/launcher"
    shutil.copy(ROOT / "mac/launcher.sh", launcher)
    icon = make_icon()
    icon.save(app / "Contents/Resources/AppIcon.icns")
    icon.resize((512, 512)).save(app / "Contents/Resources/AppIcon.png")
    _copy_source(app / "Contents/Resources/app")
    (app / "Contents/Resources/app/VERSION").write_text(__version__)
    (stage / "อ่านก่อน - Read me.txt").write_text(
        "Thai TikTok Studio\n\n"
        "1) ลาก \"Thai TikTok Studio\" ไปไว้ในโฟลเดอร์ Applications\n"
        "2) ครั้งแรก: คลิกขวาที่แอป → Open → Open (เพราะแอปไม่ได้มาจาก App Store)\n"
        "3) ครั้งแรกจะติดตั้งส่วนประกอบเองประมาณ 2–5 นาที (ต้องต่ออินเทอร์เน็ต)\n\n"
        "1) Drag \"Thai TikTok Studio\" into Applications.\n"
        "2) First time: right-click the app → Open → Open (it isn't from the App Store).\n"
        "3) The first launch sets itself up in 2–5 minutes (internet needed).\n", "utf-8")

    out = OUT_DIR / "ThaiTikTokStudio-mac.zip"
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(stage.rglob("*")):
            rel = p.relative_to(stage).as_posix()
            if p.is_dir():
                continue
            info = zipfile.ZipInfo(rel, date_time=(2026, 1, 1, 0, 0, 0))
            mode = 0o755 if p == launcher else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, p.read_bytes())
    shutil.rmtree(stage)
    write_latest(out)
    return out


ZIP_URL = ("https://raw.githubusercontent.com/greenlad24/skills/claude/wizardly-thompson-w6jjr8/"
           "thai-tiktok-studio/releases/ThaiTikTokStudio-mac.zip")


def write_latest(zip_path: Path) -> None:
    """releases/latest.json — what installed apps check to update themselves."""
    import hashlib
    import json
    notes = (ROOT / "releases" / "NOTES.txt")
    (OUT_DIR / "latest.json").write_text(json.dumps({
        "version": __version__,
        "zip_url": ZIP_URL,
        "sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest(),
        "notes": notes.read_text("utf-8").strip() if notes.exists() else "",
    }, ensure_ascii=False, indent=1) + "\n", "utf-8")


if __name__ == "__main__":
    print(build())
