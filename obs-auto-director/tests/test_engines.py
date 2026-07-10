"""End-to-end engine tests: synthetic audio through the real pipeline
(frontend -> detectors -> EvidenceSwitcher -> directors -> fake OBS)."""

import json

import numpy as np
import pytest

from autodirector.app import LiveEngine, PodcastEngine
from autodirector.dsp import Calibrator, Frontend, VocalPresence

from synthaudio import SR, mix, synth_instrumental, synth_vocal


class FakeCapture:
    def __init__(self, audio, chunk=4800):
        self.audio = audio
        self.chunk = chunk
        self.pos = 0
        self.samples_captured = 0
        self.samplerate = SR

    def read(self):
        if self.pos >= len(self.audio):
            return None
        chunk = self.audio[self.pos:self.pos + self.chunk]
        self.pos += len(chunk)
        self.samples_captured += len(chunk)
        return chunk

    def alive(self, timeout_s=0.5):
        return self.pos < len(self.audio)

    @property
    def audio_clock(self):
        return self.samples_captured / float(SR)


class FakeSceneOBS:
    state = "connected"

    def __init__(self):
        self.scene_calls = []
        self.filters = {}
        self.settings_calls = []

    def set_current_scene(self, name):
        self.scene_calls.append(name)
        return True

    # filter API (podcast chains)
    def get_filters(self, source):
        return list(self.filters.get(source, []))

    def create_filter(self, source, name, kind, settings):
        self.filters.setdefault(source, []).append(
            {"filterName": name, "filterKind": kind})
        return True

    def set_filter_settings(self, source, name, settings, overlay=True):
        self.settings_calls.append((source, name, settings))
        return True

    def set_filter_index(self, source, name, index):
        return True


def make_calibration_file(tmp_path):
    """Run the real Calibrator on synthetic material, save like the wizard."""
    cal = Calibrator()
    det = VocalPresence()
    fe = Frontend()
    for hop_audio, vocal in (
            (synth_instrumental(10.0, seed=51), False),
            (mix(synth_instrumental(10.0, seed=52), synth_vocal(10.0, seed=53),
                 gains=[0.7, 1.0]), True)):
        det_local = VocalPresence()
        fe_local = Frontend()
        for start in range(0, len(hop_audio), 4800):
            for hop in fe_local.process(hop_audio[start:start + 4800]):
                det_local.update(hop)
                cal.collect(det_local.features(), vocal=vocal)
    result = cal.finish()
    assert result is not None and result.d_prime >= 1.5
    path = tmp_path / "live_cal.json"
    path.write_text(json.dumps({
        "w": [float(x) for x in result.w], "b": result.b,
        "d_prime": result.d_prime,
        "dwell_multiplier": result.dwell_multiplier,
        "f0_lo": None, "f0_hi": None}))
    return str(path)


class TestLiveEngineEndToEnd:
    def test_full_song_direction(self, tmp_path):
        cal_file = make_calibration_file(tmp_path)
        song = np.concatenate([
            synth_instrumental(8.0, seed=61),
            mix(synth_instrumental(8.0, seed=62), synth_vocal(8.0, seed=63),
                gains=[0.7, 1.0]),
            synth_instrumental(8.0, seed=64),
        ])
        obs = FakeSceneOBS()
        engine = LiveEngine(
            {"singer_scene": "Singer",
             "instrumental_scenes": ["Wide", "Guitar", "Drums"],
             "calibration_file": cal_file},
            obs, FakeCapture(song))
        cuts = []
        while True:
            got = [(engine.capture.audio_clock, c) for c in engine.step()]
            cuts.extend(got)
            if engine.capture.pos >= len(song):
                break

        scenes = [c.scene for _, c in cuts]
        assert "Singer" in scenes, f"never cut to singer: {scenes}"
        # singer cut lands within a couple seconds of the vocals (t=8)
        t_singer = next(t for t, c in cuts if c.scene == "Singer")
        assert 8.0 <= t_singer <= 11.5, f"singer cut at {t_singer:.1f}s"
        # after vocals end (t=16), we eventually go back to instrumentals
        post = [c.scene for t, c in cuts if t > 17.0]
        assert any(s != "Singer" for s in post), \
            "must return to instrumental shots after the vocals"
        # relaxed switching: a 24s song should not produce a cut storm
        assert len(cuts) <= 8, f"too many cuts ({len(cuts)}): {scenes}"
        # no burned cut right before a vocal entrance (rotation deferral)
        for i, (t, c) in enumerate(cuts):
            if c.scene == "Singer" and i > 0:
                assert (t - cuts[i - 1][0]) > 0.8, \
                    f"cut {cuts[i-1][1].scene} burned {t - cuts[i-1][0]:.2f}s " \
                    "before the singer entrance"
        # every cut the director made reached OBS
        assert obs.scene_calls == scenes

    def test_engine_freezes_without_audio(self, tmp_path):
        obs = FakeSceneOBS()
        engine = LiveEngine({"singer_scene": "S",
                             "instrumental_scenes": ["W"]},
                            obs, FakeCapture(np.zeros(0)))
        assert engine.step() == []
        assert "frozen" in engine.status
        assert obs.scene_calls == []


class TestPodcastEngineEndToEnd:
    def make_engine(self, anna_audio, ben_audio, obs=None):
        obs = obs or FakeSceneOBS()
        captures = {"capA": FakeCapture(anna_audio),
                    "capB": FakeCapture(ben_audio)}
        cfg = {
            "speakers": [
                {"name": "Anna", "capture": "capA", "obs_source": "Mic A",
                 "medium_scene": "Anna Medium", "closeup_scene": "Anna Close"},
                {"name": "Ben", "capture": "capB", "obs_source": "Mic B",
                 "medium_scene": "Ben Medium", "closeup_scene": "Ben Close"},
            ],
            "wide_scene": "Two Shot",
            "voice_chain": {"enabled": True},
            "ai_review": {"enabled": False},
        }
        return PodcastEngine(cfg, obs, captures), obs

    def test_follows_speakers_and_builds_chains(self):
        quiet = 0.0005
        rng = np.random.default_rng(9)

        def noise(sec):
            return rng.normal(0, quiet, int(sec * SR))

        anna = np.concatenate([synth_vocal(8.0, f0=130.0, seed=71) * 0.5,
                               noise(10.0)])
        ben = np.concatenate([noise(9.5),
                              synth_vocal(8.5, f0=210.0, seed=72) * 0.5])
        engine, obs = self.make_engine(anna, ben)
        cuts = []
        for _ in range(10000):
            for c in engine.step():
                cuts.append((max(sp.capture.audio_clock
                                 for sp in engine.speakers), c))
            if all(sp.capture.pos >= len(sp.capture.audio)
                   for sp in engine.speakers):
                break

        scenes = [c.scene for _, c in cuts]
        assert scenes and scenes[0] == "Anna Medium"
        assert "Ben Medium" in scenes
        t_ben = next(t for t, c in cuts if c.scene == "Ben Medium")
        assert 10.0 <= t_ben <= 13.5, f"Ben cut at {t_ben:.1f}s"
        # adaptive chains were created on both speaker sources
        assert any(f["filterName"].startswith("AD:")
                   for f in obs.filters.get("Mic A", []))
        assert any(f["filterName"].startswith("AD:")
                   for f in obs.filters.get("Mic B", []))
