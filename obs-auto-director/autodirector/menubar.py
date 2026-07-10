"""Optional macOS menu-bar shell (requires: pip install rumps).

Shows a status dot and Start/Stop control around the same engine loop the
CLI runs. Kept deliberately thin: all real behavior lives in app.py and
is covered by the test suite; this file is only glue for the menu bar.
"""

from __future__ import annotations

import sys
import threading

try:
    import rumps
except ImportError:  # pragma: no cover
    rumps = None


def main(config_path: str) -> int:  # pragma: no cover - UI shell
    if rumps is None:
        print("menu-bar mode needs rumps:  pip install rumps", file=sys.stderr)
        return 1

    from .app import build_and_run

    class App(rumps.App):
        def __init__(self):
            super().__init__("🎬", quit_button="Quit AutoDirector")
            self.menu = ["Status: starting", None]
            self._thread = None
            self._start()

        def _start(self):
            self._thread = threading.Thread(
                target=build_and_run, args=(config_path,), daemon=True)
            self._thread.start()
            self.menu["Status: starting"].title = "Status: running"

    App().run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1]))
