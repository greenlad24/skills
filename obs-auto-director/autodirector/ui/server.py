"""Control Room server: a local web UI for AutoDirector.

Serves a single self-contained page (no external assets, works offline)
plus a small JSON API the page polls. Bound to 127.0.0.1 only — this is
an operator console, not a network service.
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from .html import CONTROL_ROOM_HTML

log = logging.getLogger("autodirector.ui")


class ControlRoomServer:
    def __init__(self, runtime, port: int = 8787, host: str = "127.0.0.1"):
        self.runtime = runtime
        self.host = host
        self.port = port
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    def start(self) -> None:
        handler = self._make_handler()
        # If the port is taken (another instance, another app), walk up a
        # few ports rather than dying.
        last_err = None
        for port in range(self.port, self.port + 10):
            try:
                self._httpd = ThreadingHTTPServer((self.host, port), handler)
                self.port = self._httpd.server_address[1]
                break
            except OSError as e:
                last_err = e
            if port == 0:  # ephemeral request that still failed
                break
        if self._httpd is None:
            raise last_err
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        daemon=True, name="control-room")
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    # ------------------------------------------------------------------
    def _make_handler(self):
        runtime = self.runtime

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # quiet
                log.debug(fmt, *args)

            # -- helpers ------------------------------------------------
            def _send(self, code: int, body: bytes,
                      ctype: str = "application/json") -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, obj, code: int = 200) -> None:
                self._send(code, json.dumps(obj).encode())

            def _body(self) -> dict:
                n = int(self.headers.get("Content-Length") or 0)
                if n == 0:
                    return {}
                try:
                    return json.loads(self.rfile.read(n).decode())
                except json.JSONDecodeError:
                    return {}

            # -- GET ------------------------------------------------------
            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    self._send(200, CONTROL_ROOM_HTML.encode(),
                               "text/html; charset=utf-8")
                elif self.path == "/api/state":
                    self._json(runtime.ui_state())
                elif self.path == "/api/config":
                    self._json(runtime.cfg)
                elif self.path == "/api/scenes":
                    obs = runtime.obs
                    scenes = obs.get_scene_names() if obs else []
                    self._json({"scenes": scenes or [],
                                "obs_state": getattr(obs, "state", "down")})
                elif self.path == "/api/devices":
                    self._json({"devices": self._devices()})
                else:
                    self._json({"error": "not found"}, 404)

            @staticmethod
            def _devices():
                try:
                    import sounddevice as sd
                    return [
                        {"name": d["name"], "inputs": d["max_input_channels"]}
                        for d in sd.query_devices()
                        if d.get("max_input_channels", 0) > 0]
                except Exception as e:
                    log.debug("device listing unavailable: %s", e)
                    return []

            # -- POST ---------------------------------------------------
            def do_POST(self):
                body = self._body()
                eng = runtime.engine
                if self.path == "/api/active":
                    if eng is None:
                        return self._json({"error": "engine not running"}, 409)
                    eng.active = bool(body.get("active", True))
                    return self._json({"active": eng.active})
                if self.path == "/api/config":
                    result = runtime.save_config(body)
                    return self._json(result)
                if self.path == "/api/calibration":
                    if eng is None or eng.mode != "live":
                        return self._json(
                            {"error": "live engine not running"}, 409)
                    action = body.get("action")
                    if action == "start_instrumental":
                        eng.calibration_start_phase("instrumental")
                        return self._json(eng.calibration_state())
                    if action == "start_vocal":
                        eng.calibration_start_phase("vocal")
                        return self._json(eng.calibration_state())
                    if action == "finish":
                        return self._json(eng.calibration_finish())
                    if action == "cancel":
                        eng.calibration_cancel()
                        return self._json({"ok": True})
                    return self._json({"error": "unknown action"}, 400)
                if self.path == "/api/freeze":
                    if eng is None or eng.mode != "podcast":
                        return self._json(
                            {"error": "podcast engine not running"}, 409)
                    ok = eng.freeze_param(body.get("speaker", ""),
                                          body.get("param", ""),
                                          bool(body.get("frozen", True)))
                    return self._json({"ok": ok}, 200 if ok else 404)
                return self._json({"error": "not found"}, 404)

        return Handler
