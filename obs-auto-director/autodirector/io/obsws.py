"""obs-websocket v5 client: scene control, scene events, and filter control.

Design goals (docs/ARCHITECTURE.md):
- FAIL-SAFE: when the connection is down, every control call becomes a
  logged no-op. OBS is never left in a weird state; the show continues
  under manual control.
- Auto-reconnect with exponential backoff.
- Thread-friendly: the asyncio loop runs on a background thread; public
  methods are safe to call from the analyzer thread.

Implements the v5 protocol directly over `websockets` (Hello/Identify
with SHA256 challenge auth, Request/RequestResponse, Event).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import itertools
import json
import logging
import threading
from typing import Callable, Optional

log = logging.getLogger("autodirector.obsws")

OP_HELLO, OP_IDENTIFY, OP_IDENTIFIED, OP_REIDENTIFY = 0, 1, 2, 3
OP_EVENT, OP_REQUEST, OP_RESPONSE = 5, 6, 7
EVENT_SUB_GENERAL_AND_SCENES = 1 | (1 << 2)


def _auth_string(password: str, salt: str, challenge: str) -> str:
    secret = base64.b64encode(
        hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(
        hashlib.sha256((secret + challenge).encode()).digest()).decode()


class OBSClient:
    """Background-threaded obs-websocket v5 client."""

    def __init__(self, host: str = "127.0.0.1", port: int = 4455,
                 password: str = "",
                 on_scene_changed: Optional[Callable[[str], None]] = None,
                 on_state: Optional[Callable[[str], None]] = None):
        self.url = f"ws://{host}:{port}"
        self.password = password
        self.on_scene_changed = on_scene_changed
        self.on_state = on_state
        self.state = "down"           # down | connecting | connected
        self._ws = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._req_id = itertools.count(1)
        self._pending: dict = {}

    # -- lifecycle -----------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="obsws")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._loop is not None:
            self._loop.call_soon_threadsafe(lambda: None)
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    def _set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            log.info("obs-websocket: %s", state)
            if self.on_state:
                try:
                    self.on_state(state)
                except Exception:
                    pass

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect_forever())
        finally:
            self._loop.close()

    async def _connect_forever(self) -> None:
        import websockets
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._set_state("connecting")
                async with websockets.connect(
                        self.url, max_size=8 * 1024 * 1024) as ws:
                    self._ws = ws
                    await self._identify(ws)
                    self._set_state("connected")
                    backoff = 1.0
                    await self._read_loop(ws)
            except Exception as e:
                log.debug("obsws connection error: %s", e)
            finally:
                self._ws = None
                self._fail_pending()
                self._set_state("down")
            if self._stop.is_set():
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 15.0)

    async def _identify(self, ws) -> None:
        hello = json.loads(await ws.recv())
        assert hello.get("op") == OP_HELLO
        d = {"rpcVersion": 1,
             "eventSubscriptions": EVENT_SUB_GENERAL_AND_SCENES}
        auth = hello["d"].get("authentication")
        if auth:
            d["authentication"] = _auth_string(
                self.password, auth["salt"], auth["challenge"])
        await ws.send(json.dumps({"op": OP_IDENTIFY, "d": d}))
        identified = json.loads(await ws.recv())
        if identified.get("op") != OP_IDENTIFIED:
            raise ConnectionError(f"identify failed: {identified}")

    async def _read_loop(self, ws) -> None:
        async for raw in ws:
            msg = json.loads(raw)
            op, d = msg.get("op"), msg.get("d", {})
            if op == OP_RESPONSE:
                fut = self._pending.pop(d.get("requestId"), None)
                if fut is not None and not fut.done():
                    fut.set_result(d)
            elif op == OP_EVENT:
                self._handle_event(d)
            if self._stop.is_set():
                return

    def _handle_event(self, d: dict) -> None:
        if d.get("eventType") == "CurrentProgramSceneChanged":
            name = d.get("eventData", {}).get("sceneName")
            if name and self.on_scene_changed:
                try:
                    self.on_scene_changed(name)
                except Exception:
                    log.exception("scene-changed callback failed")

    def _fail_pending(self) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_result(None)
        self._pending.clear()

    # -- requests --------------------------------------------------------
    async def _send_request(self, req_type: str, data: dict):
        ws = self._ws
        if ws is None:
            return None
        rid = str(next(self._req_id))
        fut = asyncio.get_event_loop().create_future()
        self._pending[rid] = fut
        await ws.send(json.dumps({"op": OP_REQUEST, "d": {
            "requestType": req_type, "requestId": rid,
            "requestData": data}}))
        try:
            return await asyncio.wait_for(fut, timeout=5.0)
        except asyncio.TimeoutError:
            self._pending.pop(rid, None)
            return None

    def request(self, req_type: str, data: Optional[dict] = None,
                timeout: float = 5.0) -> Optional[dict]:
        """Thread-safe synchronous request. Returns responseData dict, or
        None when down/failed (fail-safe: callers treat None as no-op)."""
        if self.state != "connected" or self._loop is None:
            return None
        try:
            fut = asyncio.run_coroutine_threadsafe(
                self._send_request(req_type, data or {}), self._loop)
            resp = fut.result(timeout=timeout + 1.0)
        except Exception:
            return None
        if not resp:
            return None
        status = resp.get("requestStatus", {})
        if not status.get("result"):
            log.debug("request %s failed: %s", req_type, status)
            return None
        return resp.get("responseData", {}) or {}

    # -- convenience API ---------------------------------------------------
    def set_current_scene(self, name: str) -> bool:
        return self.request("SetCurrentProgramScene",
                            {"sceneName": name}) is not None

    def get_scene_names(self) -> list:
        data = self.request("GetSceneList") or {}
        return [s.get("sceneName") for s in data.get("scenes", [])]

    def get_current_scene(self) -> Optional[str]:
        data = self.request("GetCurrentProgramScene") or {}
        return data.get("currentProgramSceneName") or data.get("sceneName")

    def get_input_names(self) -> list:
        data = self.request("GetInputList") or {}
        return [i.get("inputName") for i in data.get("inputs", [])]

    def set_input_volume(self, name: str, volume_db: float) -> bool:
        """Ride an input's volume — the VST-safe control: works no matter
        what filter chain (VST or native) the user runs on the source."""
        return self.request("SetInputVolume", {
            "inputName": name, "inputVolumeDb": float(volume_db)}) is not None

    # filters (adaptive voice chain)
    def get_filters(self, source: str) -> list:
        data = self.request("GetSourceFilterList",
                            {"sourceName": source}) or {}
        return data.get("filters", [])

    def create_filter(self, source: str, name: str, kind: str,
                      settings: dict) -> bool:
        return self.request("CreateSourceFilter", {
            "sourceName": source, "filterName": name,
            "filterKind": kind, "filterSettings": settings}) is not None

    def set_filter_settings(self, source: str, name: str,
                            settings: dict, overlay: bool = True) -> bool:
        return self.request("SetSourceFilterSettings", {
            "sourceName": source, "filterName": name,
            "filterSettings": settings, "overlay": overlay}) is not None

    def set_filter_enabled(self, source: str, name: str,
                           enabled: bool) -> bool:
        return self.request("SetSourceFilterEnabled", {
            "sourceName": source, "filterName": name,
            "filterEnabled": enabled}) is not None

    def set_filter_index(self, source: str, name: str, index: int) -> bool:
        return self.request("SetSourceFilterIndex", {
            "sourceName": source, "filterName": name,
            "filterIndex": index}) is not None
