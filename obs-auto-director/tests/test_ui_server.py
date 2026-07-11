"""Control Room server tests: state, controls, config save, and a full
UI-driven calibration session against a real LiveEngine."""

import json
import urllib.request

import numpy as np
import pytest

from autodirector.app import LiveEngine, PodcastEngine, Runtime
from autodirector.ui.server import ControlRoomServer

from synthaudio import SR, mix, synth_instrumental, synth_vocal
from test_engines import FakeSceneOBS


class StreamCapture:
    """FakeCapture that can be fed more audio mid-test."""

    def __init__(self):
        self.buf = []
        self.samples_captured = 0

    def feed(self, audio):
        self.buf.append(audio)

    def read(self):
        if not self.buf:
            return None
        chunk = self.buf.pop(0)
        self.samples_captured += len(chunk)
        return chunk

    def alive(self, timeout_s=0.5):
        return True

    def stop(self):
        pass

    @property
    def audio_clock(self):
        return self.samples_captured / float(SR)


def http(method, url, body=None):
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(body).encode() if body
                                 is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode()) \
                if "json" in r.headers.get("Content-Type", "") \
                else r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


@pytest.fixture
def runtime(tmp_path):
    rt = Runtime(str(tmp_path / "config.json"), dry_run=True)
    yield rt
    rt.shutdown()


@pytest.fixture
def server(runtime):
    srv = ControlRoomServer(runtime, port=0)
    srv.start()
    yield srv, runtime, f"http://127.0.0.1:{srv.port}"
    srv.stop()


class TestControlRoom:
    def test_serves_page_and_setup_state(self, server):
        srv, rt, base = server
        code, page = http("GET", base + "/")
        assert code == 200 and "AutoDirector" in page and "Control Room" in page
        rt.rebuild()  # default config -> setup needed
        code, state = http("GET", base + "/api/state")
        assert code == 200 and state["mode"] == "setup"
        assert "setup needed" in (state["error"] or "")
        code, _ = http("POST", base + "/api/active", {"active": False})
        assert code == 409  # no engine yet

    def test_config_roundtrip(self, server, tmp_path):
        srv, rt, base = server
        code, cfg = http("GET", base + "/api/config")
        assert code == 200 and cfg["mode"] == "live"
        cfg["mode"] = "podcast"
        code, result = http("POST", base + "/api/config", cfg)
        assert code == 200 and result["saved"] is True
        # engine can't start (no speakers) but the config persisted
        assert result["engine_ok"] is False
        code, cfg2 = http("GET", base + "/api/config")
        assert cfg2["mode"] == "podcast"
        on_disk = json.loads(open(rt.config_path).read())
        assert on_disk["mode"] == "podcast"

    def test_live_state_active_toggle_and_calibration_flow(
            self, server, tmp_path):
        srv, rt, base = server
        cap = StreamCapture()
        engine = LiveEngine(
            {"singer_scene": "Singer", "instrumental_scenes": ["Wide"],
             "calibration_file": str(tmp_path / "cal.json")},
            FakeSceneOBS(), cap)
        rt.engine = engine

        code, state = http("GET", base + "/api/state")
        assert state["mode"] == "live"
        assert state["live"]["calibration"]["calibrated"] is False

        # pause / resume through the API
        code, r = http("POST", base + "/api/active", {"active": False})
        assert r["active"] is False and engine.active is False
        http("POST", base + "/api/active", {"active": True})
        assert engine.active is True

        # ---- calibration session driven exactly like the UI drives it ----
        def run_audio(audio):
            for s in range(0, len(audio), 4800):
                cap.feed(audio[s:s + 4800])
                engine.step()

        code, st = http("POST", base + "/api/calibration",
                        {"action": "start_instrumental"})
        assert st["phase"] == "instrumental"
        run_audio(synth_instrumental(11.0, seed=81))
        code, st = http("GET", base + "/api/state")
        calst = st["live"]["calibration"]
        assert calst["phase"] is None  # phase auto-completed
        assert calst["instrumental_samples"] > 100

        http("POST", base + "/api/calibration", {"action": "start_vocal"})
        run_audio(mix(synth_instrumental(11.0, seed=82),
                      synth_vocal(11.0, seed=83), gains=[0.7, 1.0]))
        code, result = http("POST", base + "/api/calibration",
                            {"action": "finish"})
        assert result["ok"] is True
        assert result["d_prime"] >= 1.5
        assert (tmp_path / "cal.json").exists()
        code, st = http("GET", base + "/api/state")
        assert st["live"]["calibration"]["calibrated"] is True

    def test_podcast_freeze_endpoint(self, server):
        srv, rt, base = server
        obs = FakeSceneOBS()
        cap = StreamCapture()
        engine = PodcastEngine(
            {"speakers": [
                {"name": "Anna", "capture": "c", "obs_source": "Mic A",
                 "medium_scene": "Anna Medium"}],
             "ai_review": {"enabled": False}},
            obs, {"c": cap})
        rt.engine = engine
        code, r = http("POST", base + "/api/freeze",
                       {"speaker": "Anna", "param": "eq_high",
                        "frozen": True})
        assert code == 200 and r["ok"] is True
        assert engine.speakers[0].chain.rails["eq_high"].frozen is True
        code, state = http("GET", base + "/api/state")
        assert "eq_high" in \
            state["podcast"]["speakers"][0]["chain"]["frozen"]
        code, r = http("POST", base + "/api/freeze",
                       {"speaker": "Nobody", "param": "eq_high"})
        assert code == 404

    def test_scenes_and_devices_endpoints(self, server):
        srv, rt, base = server
        code, sc = http("GET", base + "/api/scenes")
        assert code == 200 and "scenes" in sc
        code, dev = http("GET", base + "/api/devices")
        assert code == 200 and isinstance(dev["devices"], list)
