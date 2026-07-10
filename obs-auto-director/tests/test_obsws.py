"""OBSClient integration test against an in-process fake obs-websocket v5
server: Hello/Identify auth, requests, events, and fail-safe behavior."""

import asyncio
import base64
import hashlib
import json
import socket
import threading
import time

import pytest

from autodirector.io.obsws import OBSClient, _auth_string

PASSWORD = "sup3rsecret"
SALT = "c2FsdA=="
CHALLENGE = "Y2hhbGxlbmdl"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class FakeOBSServer:
    """Minimal obs-websocket v5: auth handshake + a few request types."""

    def __init__(self, port):
        self.port = port
        self.scene_calls = []
        self.auth_ok = None
        self.loop = None
        self._client_ws = None
        self._server = None
        self._started = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        assert self._started.wait(5.0), "fake OBS server failed to start"

    def stop(self):
        if self.loop and self.loop.is_running():
            async def _shutdown():
                if self._server is not None:
                    self._server.close()
                if self._client_ws is not None:
                    await self._client_ws.close()
            try:
                asyncio.run_coroutine_threadsafe(
                    _shutdown(), self.loop).result(3.0)
            except Exception:
                pass
            self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=3.0)

    def push_scene_event(self, name):
        async def _send():
            if self._client_ws:
                await self._client_ws.send(json.dumps({
                    "op": 5, "d": {"eventType": "CurrentProgramSceneChanged",
                                   "eventIntent": 4,
                                   "eventData": {"sceneName": name}}}))
        asyncio.run_coroutine_threadsafe(_send(), self.loop).result(3.0)

    def _run(self):
        import websockets
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        async def handler(ws):
            self._client_ws = ws
            await ws.send(json.dumps({"op": 0, "d": {
                "obsWebSocketVersion": "5.4.0", "rpcVersion": 1,
                "authentication": {"challenge": CHALLENGE, "salt": SALT}}}))
            ident = json.loads(await ws.recv())
            expected = _auth_string(PASSWORD, SALT, CHALLENGE)
            self.auth_ok = ident["d"].get("authentication") == expected
            if not self.auth_ok:
                await ws.close(code=4009)
                return
            await ws.send(json.dumps({"op": 2, "d": {
                "negotiatedRpcVersion": 1}}))
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("op") != 6:
                    continue
                d = msg["d"]
                resp = {"requestType": d["requestType"],
                        "requestId": d["requestId"],
                        "requestStatus": {"result": True, "code": 100}}
                if d["requestType"] == "SetCurrentProgramScene":
                    self.scene_calls.append(
                        d["requestData"]["sceneName"])
                elif d["requestType"] == "GetSceneList":
                    resp["responseData"] = {"scenes": [
                        {"sceneName": "Singer"}, {"sceneName": "Wide"}]}
                await ws.send(json.dumps({"op": 7, "d": resp}))

        async def main():
            self._server = await websockets.serve(handler, "127.0.0.1",
                                                  self.port)
            self._started.set()
            await asyncio.Future()

        try:
            self.loop.run_until_complete(main())
        except RuntimeError:
            pass  # loop.stop()
        finally:
            self.loop.close()


def wait_for(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


class TestOBSClient:
    def test_auth_requests_events_and_failsafe(self):
        port = free_port()
        server = FakeOBSServer(port)
        server.start()
        scene_events = []
        client = OBSClient(host="127.0.0.1", port=port, password=PASSWORD,
                           on_scene_changed=scene_events.append)
        client.start()
        try:
            assert wait_for(lambda: client.state == "connected"), \
                "client must connect and authenticate"
            assert server.auth_ok is True

            assert client.set_current_scene("Singer")
            assert server.scene_calls == ["Singer"]
            assert client.get_scene_names() == ["Singer", "Wide"]

            server.push_scene_event("Wide")
            assert wait_for(lambda: scene_events == ["Wide"])

            # fail-safe: server dies -> calls become no-ops, state -> down
            server.stop()
            assert wait_for(lambda: client.state != "connected")
            assert client.set_current_scene("Singer") is False
        finally:
            client.stop()

    def test_wrong_password_never_connects(self):
        port = free_port()
        server = FakeOBSServer(port)
        server.start()
        client = OBSClient(host="127.0.0.1", port=port, password="wrong")
        client.start()
        try:
            time.sleep(1.0)
            assert client.state != "connected"
            assert server.auth_ok is False
            assert client.set_current_scene("Singer") is False
        finally:
            client.stop()
            server.stop()
