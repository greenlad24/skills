"""Mac app entry point: run the studio in its own window (no Terminal, no browser tab).

Started by "Thai TikTok Studio.app". Serves the app on this computer (and the phone
upload pages on Wi-Fi) and shows it in a native window via pywebview. Closing the
window quits. If the native window can't open, the default browser is used instead.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request

from . import config


def _free_port(preferred: int = 8765) -> int:
    for port in (preferred, 0):
        s = socket.socket()
        try:
            s.bind(("0.0.0.0", port))
            return s.getsockname()[1]
        except OSError:
            continue
        finally:
            s.close()
    return preferred


def _brand_mac_app() -> None:
    """Make the Dock / menu bar show our name and icon instead of 'Python'."""
    try:
        from AppKit import NSApplication, NSImage
        from Foundation import NSBundle
        info = NSBundle.mainBundle().localizedInfoDictionary() or NSBundle.mainBundle().infoDictionary()
        if info is not None:
            info["CFBundleName"] = "Thai TikTok Studio"
        icon = os.environ.get("TTS_STUDIO_ICON")
        if icon and os.path.exists(icon):
            NSApplication.sharedApplication().setApplicationIconImage_(NSImage.alloc().initWithContentsOfFile_(icon))
    except Exception:
        pass


def main() -> None:
    port = _free_port(int(os.environ.get("TTS_STUDIO_PORT", "8765")))
    os.environ["TTS_STUDIO_PORT"] = str(port)
    os.environ.setdefault("TTS_STUDIO_HOST", "0.0.0.0")
    from . import app as webapp                      # reads the env above
    webapp.PORT = port
    config.ensure_dirs()
    from . import scheduler
    scheduler.start_worker(config.load_settings)        # hands posts to PostPeer while the app is open
    from . import updater
    updater.start()
    def _fix_old_renders():                              # videos made before 1.9.6 may carry a rotation tag
        try:
            from .editor import render
            render.fix_existing(config.PROJECTS_DIR)
        except Exception:
            pass
    threading.Thread(target=_fix_old_renders, daemon=True).start()
    try:                                                 # Thai marks on stickers need a shaper on most Macs
        from PIL import features
        from .editor import shaper
        shaper.startup_check()                        # crashed while drawing text last time → stay off
        if not features.check("raqm"):
            shaper.ensure(background=True)
    except Exception:
        pass                                      # new versions install themselves

    from werkzeug.serving import make_server
    server = make_server("0.0.0.0", port, webapp.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    for _ in range(100):                             # wait until it answers
        try:
            urllib.request.urlopen(url + "api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.1)

    try:
        import webview
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        _brand_mac_app()
        webview.create_window("Thai TikTok Studio", url, width=1360, height=900, min_size=(960, 640))
        webview.start(private_mode=False)            # blocks until the window is closed
    except Exception as e:                           # no native window → use the browser
        print("Native window unavailable, opening browser:", e, file=sys.stderr)
        import webbrowser
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    server.shutdown()


if __name__ == "__main__":
    main()
