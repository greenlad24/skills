import json

import numpy as np

from autodirector.chain import (AIReviewer, ChainConfig, Rail, SpeakerMeter,
                                VoiceChain)
from autodirector.chain.fastloop import (F_COMP, F_EQ, F_EXPANDER, F_GAIN,
                                         F_LIMIT, F_SUPPRESS)
from autodirector.chain.measure import Snapshot
from autodirector.dsp.frontend import HopFeatures


class FakeOBS:
    """Records filter operations; simulates an OBS with a user VST filter."""

    def __init__(self):
        self.filters = {"Mic A": [
            {"filterName": "My Fancy VST", "filterKind": "vst_filter"},
        ]}
        self.settings_calls = []
        self.volume_calls = []
        self.down = False

    def set_input_volume(self, name, volume_db):
        if self.down:
            return False
        self.volume_calls.append((name, round(volume_db, 2)))
        return True

    def get_filters(self, source):
        if self.down:
            return None
        return list(self.filters.get(source, []))

    def create_filter(self, source, name, kind, settings):
        if self.down:
            return False
        self.filters.setdefault(source, []).append(
            {"filterName": name, "filterKind": kind,
             "filterSettings": dict(settings)})
        return True

    def set_filter_settings(self, source, name, settings, overlay=True):
        if self.down:
            return False
        self.settings_calls.append((source, name, dict(settings)))
        for f in self.filters.get(source, []):
            if f["filterName"] == name:
                f.setdefault("filterSettings", {}).update(settings)
        return True

    def set_filter_index(self, source, name, index):
        if self.down:
            return False
        fl = self.filters.get(source, [])
        for i, f in enumerate(fl):
            if f["filterName"] == name:
                fl.insert(max(0, min(index, len(fl) - 1)), fl.pop(i))
                return True
        return False


def hop(rms=-30.0, tilt=-14.0):
    return HopFeatures(t=0.0, rms_db=rms, flux=0.1, centroid_hz=1000.0,
                       tilt_db=tilt, band_db={"lf": -30, "vocal": -25,
                                              "presence": -30, "hf": -44},
                       logmel=np.zeros(40), f0_hz=120.0, voicing=0.8)


class TestRail:
    def test_clamp_and_slew(self):
        r = Rail("x", 0.0, lo=-4.0, hi=4.0, max_step=0.5)
        assert r.step_toward(10.0)
        assert r.value == 0.5          # one step only
        for _ in range(20):
            r.step_toward(10.0)
        assert r.value == 4.0          # hard clamp

    def test_frozen_rail_never_moves(self):
        r = Rail("x", 1.0, lo=-4.0, hi=4.0, max_step=0.5, frozen=True)
        assert not r.step_toward(4.0)
        assert r.nudge(2.0) == 0.0
        assert r.value == 1.0

    def test_nudge_bounded(self):
        r = Rail("x", 0.0, lo=-4.0, hi=4.0, max_step=0.5)
        assert r.nudge(3.0) == 0.5     # slew-limited
        assert r.nudge(-9.0) == -0.5


class TestVoiceChain:
    def test_ensure_creates_ad_filters_and_keeps_vst(self):
        obs = FakeOBS()
        chain = VoiceChain(obs, "Mic A")
        assert chain.ensure_filters()
        names = [f["filterName"] for f in obs.filters["Mic A"]]
        for f in (F_SUPPRESS, F_EXPANDER, F_GAIN, F_COMP, F_EQ, F_LIMIT):
            assert f in names
        assert "My Fancy VST" in names
        # suppression + expander lead; VST sits before the output stages
        assert names.index(F_SUPPRESS) == 0
        assert names.index(F_EXPANDER) == 1
        assert names.index("My Fancy VST") < names.index(F_GAIN)

    def test_expander_follows_floor_only_when_silent(self):
        obs = FakeOBS()
        chain = VoiceChain(obs, "Mic A")
        chain.ensure_filters()
        snap = Snapshot(floor_db=-48.0, speech_db=-22.0, peak_db=-14.0)
        moved = chain.adapt(snap, speaking_now=True)
        assert "expander_threshold" not in moved, \
            "gate must not move mid-sentence"
        moved = chain.adapt(snap, speaking_now=False)
        assert "expander_threshold" in moved

    def test_gain_stages_toward_target(self):
        obs = FakeOBS()
        chain = VoiceChain(obs, "Mic A", ChainConfig(target_speech_db=-20.0))
        chain.ensure_filters()
        snap = Snapshot(floor_db=-55.0, speech_db=-30.0, peak_db=-22.0)
        for _ in range(40):
            chain.adapt(snap, speaking_now=False)
        # needs +10 dB; slew 0.5/tick -> reaches it, then stops moving
        assert abs(chain.rails["gain_db"].value - 10.0) < 0.01
        assert chain.adapt(snap, speaking_now=False).get("gain_db") is None

    def test_eq_corrects_tilt_within_rails(self):
        obs = FakeOBS()
        chain = VoiceChain(obs, "Mic A", ChainConfig(target_tilt_db=-14.0))
        chain.ensure_filters()
        boomy = Snapshot(floor_db=-55.0, speech_db=-20.0, peak_db=-12.0,
                         tilt_db=-26.0)  # way too dark
        for _ in range(60):
            chain.adapt(boomy, speaking_now=False)
        assert chain.rails["eq_high"].value > 0.5
        assert chain.rails["eq_low"].value < -0.5
        assert chain.rails["eq_high"].value <= 4.0  # rail ceiling

    def test_eq_deadband_stops_chasing(self):
        obs = FakeOBS()
        chain = VoiceChain(obs, "Mic A", ChainConfig(target_tilt_db=-14.0,
                                                     eq_deadband_db=3.0))
        chain.ensure_filters()
        close_enough = Snapshot(floor_db=-55.0, speech_db=-20.0,
                                peak_db=-12.0, tilt_db=-15.5)
        moved = chain.adapt(close_enough, speaking_now=False)
        assert "eq_high" not in moved and "eq_low" not in moved

    def test_one_missing_filter_does_not_brick_the_chain(self):
        # If a single filter kind can't be created (OBS rename, platform
        # quirk), the rest of the chain must keep adapting.
        obs = FakeOBS()
        real_create = obs.create_filter

        def create(source, name, kind, settings):
            if kind == "basic_eq_filter":
                return False  # pretend this OBS has no EQ
            return real_create(source, name, kind, settings)

        obs.create_filter = create
        chain = VoiceChain(obs, "Mic A")
        assert chain.ensure_filters() is True, \
            "core chain must come up without the optional EQ"
        snap = Snapshot(floor_db=-50.0, speech_db=-30.0, peak_db=-22.0,
                        tilt_db=-30.0)  # tilt would normally trigger EQ
        moved = chain.adapt(snap, speaking_now=False)
        assert "gain_db" in moved, "gain must still adapt"
        assert "eq_high" not in moved and "eq_low" not in moved, \
            "missing EQ must be skipped, not retried into oblivion"

    def test_vst_mode_rides_volume_and_touches_nothing_else(self):
        # User runs VST plugins in OBS: we must create NO native filters
        # and automate only the input volume.
        obs = FakeOBS()
        chain = VoiceChain(obs, "Mic A",
                           ChainConfig(target_speech_db=-20.0,
                                       native_filters=False))
        snap = Snapshot(floor_db=-55.0, speech_db=-26.0, peak_db=-18.0,
                        tilt_db=-30.0)
        for _ in range(20):
            chain.adapt(snap, speaking_now=False)
        names = [f["filterName"] for f in obs.filters["Mic A"]]
        assert names == ["My Fancy VST"], \
            f"VST mode must not add filters, found {names}"
        assert obs.settings_calls == []
        assert obs.volume_calls, "gain staging must ride input volume"
        assert obs.volume_calls[-1][1] == 6.0  # reached the +6 target
        # tonal/dynamics rails are frozen against the AI too
        assert chain.nudge("eq_high", 2.0) == 0.0
        assert chain.nudge("comp_threshold", 2.0) == 0.0

    def test_fail_safe_when_obs_down(self):
        obs = FakeOBS()
        obs.down = True
        chain = VoiceChain(obs, "Mic A")
        snap = Snapshot(floor_db=-50.0, speech_db=-25.0, peak_db=-18.0)
        assert chain.adapt(snap, speaking_now=False) == {}


class TestSpeakerMeter:
    def test_measures_floor_and_speech_separately(self):
        m = SpeakerMeter()
        for _ in range(200):
            m.update(hop(rms=-52.0), active=False)
        for _ in range(200):
            m.update(hop(rms=-21.0), active=True)
        s = m.snapshot()
        assert -55.0 < s.floor_db < -49.0
        assert -23.0 < s.speech_db < -19.0
        assert 0.4 < s.talk_ratio < 0.6

    def test_gate_chatter_detected(self):
        m = SpeakerMeter()
        for i in range(400):
            m.update(hop(rms=-30.0), active=(i % 4 < 2))  # flip constantly
        assert m.snapshot().gate_chatter_per_min > 60


class TestAIReviewer:
    def make(self, response_text, tmp_path=None):
        obs = FakeOBS()
        chain = VoiceChain(obs, "Mic A")
        chain.ensure_filters()
        calls = {}

        def transport(api_key, model, payload):
            calls["payload"] = payload
            return response_text

        audit = str(tmp_path / "audit.jsonl") if tmp_path else None
        rev = AIReviewer("key-123", {"Anna": chain}, transport=transport,
                         audit_path=audit)
        return rev, chain, calls

    def test_applies_valid_adjustments_through_rails(self, tmp_path):
        resp = json.dumps({"adjustments": [
            {"speaker": "Anna", "param": "gain_db", "delta": 2.0,
             "reason": "Anna is 2 dB under target"},
            {"speaker": "Anna", "param": "gain_db", "delta": 99.0,
             "reason": "absurd — must be clamped"},
            {"speaker": "Nobody", "param": "gain_db", "delta": 1.0,
             "reason": "unknown speaker — dropped"},
            {"speaker": "Anna", "param": "sneaky_param", "delta": 1.0,
             "reason": "unknown param — dropped"},
        ], "notes": "ok"})
        rev, chain, calls = self.make(resp, tmp_path)
        applied = rev.review({"Anna": Snapshot(floor_db=-50)}, now=1000.0)
        assert len(applied) == 2
        # slew rail (0.5 max step) bounds even the sane request
        assert all(abs(a["applied"]) <= 0.5 for a in applied)
        # audit written
        lines = (tmp_path / "audit.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["speaker"] == "Anna"
        # report contained measurements + current settings
        report = json.loads(calls["payload"]["messages"][0]["content"])
        assert "Anna" in report["speakers"]
        assert "current_settings" in report["speakers"]["Anna"]

    def test_garbage_response_is_harmless(self):
        rev, chain, _ = self.make("I think you should turn it up to 11!!")
        before = chain.rails["gain_db"].value
        assert rev.review({"Anna": Snapshot()}, now=0.0) == []
        assert chain.rails["gain_db"].value == before

    def test_frozen_param_resists_ai(self):
        resp = json.dumps({"adjustments": [
            {"speaker": "Anna", "param": "eq_high", "delta": 2.0,
             "reason": "brighten"}]})
        rev, chain, _ = self.make(resp)
        chain.freeze("eq_high")
        applied = rev.review({"Anna": Snapshot()}, now=0.0)
        assert applied[0]["applied"] == 0.0
        assert chain.rails["eq_high"].value == 0.0

    def test_transport_failure_is_graceful(self):
        obs = FakeOBS()
        chain = VoiceChain(obs, "Mic A")

        def bad_transport(*a):
            raise OSError("no network")

        rev = AIReviewer("key", {"Anna": chain}, transport=bad_transport)
        assert rev.review({"Anna": Snapshot()}, now=0.0) == []

    def test_due_respects_interval_and_missing_key(self):
        obs = FakeOBS()
        chain = VoiceChain(obs, "Mic A")
        rev = AIReviewer("", {"Anna": chain}, interval_s=180.0)
        assert not rev.due(now=1e9)  # no key -> never due
        rev2 = AIReviewer("k", {"Anna": chain}, interval_s=180.0)
        assert rev2.due(now=1000.0)
        rev2.review({"Anna": Snapshot()}, now=1000.0)
        assert not rev2.due(now=1100.0)
        assert rev2.due(now=1200.0)


class TestClassifierFusion:
    def test_fusion_identity_without_model(self):
        from autodirector.classify import AudioTagger, fuse_vocal_confidence
        tagger = AudioTagger(model_path="/nonexistent/model.onnx")
        assert not tagger.enabled
        assert tagger.update(np.zeros(48000), 0.0) is None
        assert fuse_vocal_confidence(0.7, None) == 0.7

    def test_fusion_blends_singing_evidence(self):
        from autodirector.classify import TagScores, fuse_vocal_confidence
        strong_sing = TagScores(t=0, groups={"singing": 0.9, "speech": 0.1})
        no_sing = TagScores(t=0, groups={"singing": 0.05, "speech": 0.05})
        assert fuse_vocal_confidence(0.5, strong_sing) > 0.55
        assert fuse_vocal_confidence(0.5, no_sing) < 0.45
        # classifier cannot overrule strong DSP evidence on its own
        assert fuse_vocal_confidence(0.9, no_sing) > 0.6
