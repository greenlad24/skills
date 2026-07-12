"""Mix Engineer tests: role inference, MCU protocol (fake MIDI), stem
analysis on synthetic multichannel audio, rails/slew, AI review, and
the program sweetening chain."""

import json

import numpy as np
import pytest

from autodirector.mixer import (MCUFaders, MixEngineer, ProgramChain,
                                StemAnalyzer, StemConfig, infer_role)
from autodirector.mixer.mcu import FADER_MAX, UNITS_PER_DB, parse_lcd_sysex

from synthaudio import SR, synth_instrumental, synth_lead_guitar, synth_vocal
from test_chain import FakeOBS


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------

class FakePort:
    """Records outgoing pitch bends; lets tests inject DAW echoes/LCD."""
    instances = []

    def __init__(self, name, on_pitchbend, on_lcd=None):
        self.name = name
        self.on_pb = on_pitchbend
        self.on_lcd = on_lcd
        self.sent = []
        self.ccs = []
        FakePort.instances.append(self)

    def send_pitchbend(self, strip, value):
        self.sent.append((strip, int(value)))

    def send_cc(self, channel, cc, value):
        self.ccs.append((channel, cc, int(value)))

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _reset_ports():
    FakePort.instances = []
    yield


def multich(dur_s, tracks):
    """Build (n, 16) audio: tracks is {channel: mono_array}."""
    n = int(dur_s * SR)
    out = np.zeros((n, 16))
    for ch, sig in tracks.items():
        out[:len(sig), ch] = sig[:n]
    return out


# ---------------------------------------------------------------------------
class TestRoleInference:
    def test_common_names(self):
        assert infer_role("Lead Vox") == "lead_vocal"
        assert infer_role("Vox") == "lead_vocal"
        assert infer_role("BGV 1") == "backing_vocal"
        assert infer_role("Kick") == "drums"
        assert infer_role("Gtr L") == "guitar"
        assert infer_role("Bass DI") == "bass"
        assert infer_role("Keys") == "keys"
        assert infer_role("Talkback") == ""


class TestMCU:
    def test_lcd_sysex_names_channels(self):
        faders = MCUFaders(n_channels=16, port_factory=FakePort)
        # DAW writes "Kick   Snare  " to strips 0-1 of port 1
        msg = [0xF0, 0x00, 0x00, 0x66, 0x14, 0x12, 0x00] + \
              [ord(c) for c in "Kick   Snare  "] + [0xF7]
        parsed = parse_lcd_sysex(msg)
        assert parsed == (0, "Kick   Snare  ")
        FakePort.instances[0].on_lcd(*parsed)
        assert faders.names[0] == "Kick"
        assert faders.names[1] == "Snare"
        # port 2 strip 0 -> channel 8
        FakePort.instances[1].on_lcd(0, "Lead Vo")
        assert faders.names[8] == "Lead Vo"

    def test_fader_echo_baseline_and_relative_move(self):
        faders = MCUFaders(n_channels=16, port_factory=FakePort)
        # DAW echoes fader positions (user wiggles / handshake)
        FakePort.instances[0].on_pb(2, 9000)    # channel 2
        FakePort.instances[1].on_pb(0, 8000)    # channel 8
        assert faders.heard_from_daw()
        heard = faders.snapshot_baseline()
        assert heard == 2
        assert faders.set_rel_db(2, 3.0)
        strip, val = FakePort.instances[0].sent[-1]
        assert strip == 2
        assert val == int(9000 + 3.0 * UNITS_PER_DB)
        assert faders.set_rel_db(8, -2.0)
        strip, val = FakePort.instances[1].sent[-1]
        assert strip == 0 and val == int(8000 - 2.0 * UNITS_PER_DB)

    def test_lcd_nonprintables_keep_cell_alignment(self):
        # 0x00 padding inside a cell must not shift later names between
        # strips (names route AI fader moves — smearing is dangerous).
        faders = MCUFaders(n_channels=16, port_factory=FakePort)
        payload = [ord(c) for c in "Kick"] + [0x00, 0x00, 0x00] + \
                  [ord(c) for c in "Snare  "]
        msg = [0xF0, 0x00, 0x00, 0x66, 0x14, 0x12, 0x00] + payload + [0xF7]
        off, text = parse_lcd_sysex(msg)
        FakePort.instances[0].on_lcd(off, text)
        assert faders.names[0] == "Kick"
        assert faders.names[1] == "Snare"

    def test_daw_heard_ignores_our_own_echo(self):
        # loopMIDI-style loopback echoes our sends; only a value we did
        # not transmit proves the DAW is wired.
        faders = MCUFaders(n_channels=8, port_factory=FakePort)
        faders.snapshot_baseline()
        faders.set_rel_db(0, 2.0)
        strip, sent_val = FakePort.instances[0].sent[-1]
        FakePort.instances[0].on_pb(0, sent_val)   # our own echo
        assert faders.heard_from_daw() is False
        FakePort.instances[0].on_pb(0, sent_val + 40)  # a real DAW move
        assert faders.heard_from_daw() is True

    def test_positions_clamped_to_fader_range(self):
        faders = MCUFaders(n_channels=8, port_factory=FakePort)
        FakePort.instances[0].on_pb(0, FADER_MAX - 10)
        faders.snapshot_baseline()
        faders.set_rel_db(0, 6.0)
        _, val = FakePort.instances[0].sent[-1]
        assert 0 <= val <= FADER_MAX


class TestStemAnalyzer:
    def make(self):
        stems = [StemConfig(0, "Lead Vox", "lead_vocal"),
                 StemConfig(1, "Gtr L", "guitar"),
                 StemConfig(2, "Keys", "keys")]
        return StemAnalyzer(stems)

    def feed(self, an, audio, start_clock=0.0):
        for s in range(0, len(audio), 4800):
            an.process(audio[s:s + 4800], start_clock + s / SR)

    def test_vocal_activity_ground_truth(self):
        an = self.make()
        # band plays, nobody sings
        audio = multich(4.0, {1: synth_lead_guitar(4.0) * 0.4,
                              2: synth_instrumental(4.0) * 0.4})
        self.feed(an, audio)
        assert an.vocal_activity() is False
        # singer comes in
        audio = multich(4.0, {0: synth_vocal(4.0) * 0.4,
                              1: synth_lead_guitar(4.0, seed=5) * 0.4,
                              2: synth_instrumental(4.0, seed=6) * 0.4})
        self.feed(an, audio, start_clock=4.0)
        assert an.vocal_activity() is True

    def test_masking_score_reacts_to_loud_band(self):
        an = self.make()
        quiet_band = multich(6.0, {0: synth_vocal(6.0) * 0.5,
                                   1: synth_lead_guitar(6.0) * 0.05})
        self.feed(an, quiet_band)
        low_mask = an.masking_score()
        an2 = self.make()
        loud_band = multich(6.0, {0: synth_vocal(6.0) * 0.1,
                                  1: synth_lead_guitar(6.0) * 0.8})
        self.feed(an2, loud_band)
        high_mask = an2.masking_score()
        assert low_mask is not None and high_mask is not None
        assert high_mask > low_mask + 6.0

    def test_dead_channel_detection(self):
        an = self.make()
        audio = multich(40.0, {1: synth_lead_guitar(40.0) * 0.4,
                               2: synth_instrumental(40.0) * 0.4})
        self.feed(an, audio)
        snaps = an.snapshots()
        assert snaps["Lead Vox"].dead is True
        assert snaps["Gtr L"].dead is False


class TestMixEngineer:
    def make(self, transport=None, obs=None):
        cfg = {"channels": 16, "program_source": "S1 Mix",
               "master_channels": [14, 15],
               "stems": [{"channel": 0, "name": "Lead Vox"},
                         {"channel": 1, "name": "Gtr L"}],
               "ai_review": {"enabled": True, "interval_s": 60}}
        return MixEngineer(cfg, obs=obs or FakeOBS(),
                           port_factory=FakePort,
                           ai_transport=transport, api_key="k")

    def prime(self, eng, vocal_gain=0.4, gtr_gain=0.4, dur=6.0, clock=0.0):
        audio = multich(dur, {0: synth_vocal(dur) * vocal_gain,
                              1: synth_lead_guitar(dur) * gtr_gain})
        for s in range(0, len(audio), 4800):
            eng.process(audio[s:s + 4800], clock + s / SR)
        return clock + dur

    def test_roles_inferred_from_config_names(self):
        eng = self.make()
        assert eng.analyzer.stems[0].role == "lead_vocal"
        assert eng.analyzer.stems[1].role == "guitar"

    def test_control_tick_slews_toward_target(self):
        eng = self.make()
        FakePort.instances[0].on_pb(0, 9000)
        clock = self.prime(eng)
        eng.snapshot_baseline()
        assert eng.nudge(0, 2.0) == 2.0
        # 0.5 dB per 0.5s tick -> needs 4 ticks to reach +2
        for i in range(4):
            eng.control_tick(clock + 0.5 * (i + 1) + 0.01)
        assert abs(eng.rails[0].value - 2.0) < 1e-6
        sent = FakePort.instances[0].sent
        assert len(sent) == 4
        deltas = [abs(b[1] - a[1]) for a, b in zip(sent, sent[1:])]
        assert all(d <= 0.5 * UNITS_PER_DB + 1 for d in deltas), \
            "fader must move in slewed steps, never jump"

    def test_freeze_all_stops_movement(self):
        eng = self.make()
        FakePort.instances[0].on_pb(0, 9000)
        clock = self.prime(eng)
        eng.snapshot_baseline()
        eng.nudge(0, 2.0)
        eng.freeze_all(True)
        eng.control_tick(clock + 1.0)
        assert FakePort.instances[0].sent == []
        assert eng.nudge(0, 1.0) == 0.0, "nudges rejected while frozen"

    def test_report_compensates_own_fader_moves(self):
        eng = self.make()
        clock = self.prime(eng, vocal_gain=0.4)
        eng.snapshot_baseline()
        # we lift the vocal +2 (target only — pretend it was applied)
        eng.nudge(0, 2.0)
        report = eng.build_report()
        vox = report["stems"]["Lead Vox"]
        assert vox["fader_offset_db"] == 2.0
        # source didn't change, so drift ~= -offset compensation ~= -2
        assert vox["source_drift_db"] is not None
        assert abs(vox["source_drift_db"] + 2.0) < 1.5

    def test_ai_review_applies_stem_and_master_deltas(self, tmp_path):
        resp = json.dumps({
            "adjustments": [
                {"stem": "Lead Vox", "delta_db": 1.5,
                 "reason": "vocal masked by guitars"},
                {"stem": "Gtr L", "delta_db": -9.0,
                 "reason": "absurd — must clamp to 3"},
                {"stem": "Nobody", "delta_db": 1.0, "reason": "dropped"},
            ],
            "master": [
                {"param": "master_eq_high", "delta": 1.0,
                 "reason": "mix a touch dark"},
                {"param": "sneaky", "delta": 5.0, "reason": "dropped"},
            ]})
        calls = {}

        def transport(key, model, payload):
            calls["payload"] = payload
            return resp

        obs = FakeOBS()
        obs.filters["S1 Mix"] = []
        eng = self.make(transport=transport, obs=obs)
        clock = self.prime(eng)
        eng.snapshot_baseline()
        applied = eng.review(now=1000.0)
        by = {(a.get("stem"), a.get("param")): a for a in applied}
        assert by[("Lead Vox", None)]["applied"] == 1.5
        assert by[("Gtr L", None)]["applied"] == -3.0  # clamped
        assert ("Nobody", None) not in by
        assert by[("PROGRAM", "master_eq_high")]["applied"] > 0
        # report sent to the AI used instrument names + masking
        sent = json.loads(calls["payload"]["messages"][0]["content"])
        assert "Lead Vox" in sent["stems"]
        assert "vocal_masking_db" in sent
        assert "program_bus" in sent

    def test_claim_review_is_single_shot(self):
        # a 50ms poll loop must not double-spawn review threads
        eng = self.make(transport=lambda *a: "{}")
        self.prime(eng)
        eng.snapshot_baseline()
        assert eng.try_claim_review(now=1000.0) is True
        assert eng.try_claim_review(now=1000.05) is False
        assert eng.try_claim_review(now=1000.0 + eng._interval + 1) is True

    def test_review_not_due_without_baseline_or_when_frozen(self):
        eng = self.make(transport=lambda *a: "{}")
        assert not eng.review_due(now=1e9), "no baseline -> no reviews"
        self.prime(eng)
        eng.snapshot_baseline()
        assert eng.review_due(now=1e9)
        eng.freeze_all(True)
        assert not eng.review_due(now=1e9)

    def test_lcd_names_flow_into_stems(self):
        cfg = {"channels": 16, "stems": [], "ai_review": {"enabled": False}}
        eng = MixEngineer(cfg, obs=FakeOBS(), port_factory=FakePort)
        FakePort.instances[0].on_lcd(0, "Kick   Vox    ")
        eng.process(np.zeros((512, 16)), 0.0)
        assert eng.analyzer.stems[0].name == "Kick"
        assert eng.analyzer.stems[0].role == "drums"
        assert eng.analyzer.stems[1].name == "Vox"
        assert eng.analyzer.stems[1].role == "lead_vocal"


class BrokenPortFactory:
    """Simulates a platform where virtual MIDI ports can't be created."""

    def __init__(self, *a, **k):
        raise RuntimeError("no virtual MIDI on this platform")


class TestAdvisoryMode:
    def make(self, transport, control_mode=None, ports=BrokenPortFactory):
        cfg = {"channels": 16, "program_source": "S1 Mix",
               "stems": [{"channel": 0, "name": "Lead Vox"},
                         {"channel": 1, "name": "Gtr L"}],
               "ai_review": {"enabled": True, "interval_s": 60}}
        if control_mode:
            cfg["control_mode"] = control_mode
        obs = FakeOBS()
        obs.filters["S1 Mix"] = []
        return MixEngineer(cfg, obs=obs, port_factory=ports,
                           ai_transport=transport, api_key="k")

    RESP = json.dumps({
        "adjustments": [{"stem": "Lead Vox", "delta_db": 2.0,
                         "reason": "vocal buried"}],
        "master": [{"param": "master_eq_high", "delta": 0.5,
                    "reason": "dull mix"}]})

    def prime(self, eng):
        audio = multich(6.0, {0: synth_vocal(6.0) * 0.4,
                              1: synth_lead_guitar(6.0) * 0.4})
        for s in range(0, len(audio), 4800):
            eng.process(audio[s:s + 4800], s / SR)
        eng.snapshot_baseline()

    def test_no_midi_falls_back_to_advisory(self):
        eng = self.make(lambda *a: self.RESP)
        assert eng.faders.available is False
        assert eng.advisory is True
        self.prime(eng)
        applied = eng.review(now=100.0)
        stem = next(a for a in applied if a["stem"] == "Lead Vox")
        assert stem["advisory"] is True and stem["suggested"] == 2.0
        assert stem["applied"] == 0.0
        assert eng.targets[0] == 0.0, "advisory must never move targets"
        # OBS-side program sweetening still applies (zero-install path)
        master = next(a for a in applied if a["stem"] == "PROGRAM")
        assert master["applied"] > 0

    def test_forced_advisory_with_working_midi(self):
        eng = self.make(lambda *a: self.RESP, control_mode="advisory",
                        ports=FakePort)
        assert eng.faders.available is True
        assert eng.advisory is True
        self.prime(eng)
        applied = eng.review(now=100.0)
        stem = next(a for a in applied if a["stem"] == "Lead Vox")
        assert stem["advisory"] is True
        assert all(not p.sent for p in FakePort.instances), \
            "advisory must never send MIDI"

    def test_ui_reports_control_mode(self):
        eng = self.make(lambda *a: "{}")
        assert eng.ui_state()["control_mode"] == "advisory"


class TestStereoMode:
    """Fully automatic mixing from the stereo program mix (no stems) —
    the macOS <=12 / no-special-interface path."""

    RESP = json.dumps({
        "adjustments": [
            {"stem": "Lead Vox", "delta_db": 3.0, "reason": "masked"},
            {"stem": "Gtr L", "delta_db": -3.0, "reason": "crowding"},
        ],
        "master": [{"param": "master_eq_high", "delta": 0.5,
                    "reason": "dull"}]})

    def make(self, transport, auto_baseline=4.0):
        cfg = {"channels": 16, "capture_channels": 2,
               "program_source": "S1 Mix",
               "auto_baseline_s": auto_baseline,
               "stems": [{"channel": 0, "name": "Lead Vox"},
                         {"channel": 2, "name": "Gtr L"}],
               "ai_review": {"enabled": True, "interval_s": 60}}
        obs = FakeOBS()
        obs.filters["S1 Mix"] = []
        return MixEngineer(cfg, obs=obs, port_factory=FakePort,
                           ai_transport=transport, api_key="k")

    def feed(self, eng, mono, start=0.0):
        stereo = np.stack([mono, mono], axis=1)
        for s in range(0, len(stereo), 4800):
            eng.process(stereo[s:s + 4800], start + s / SR)
        return start + len(mono) / SR

    def test_stereo_mode_detected_and_no_false_ground_truth(self):
        eng = self.make(lambda *a: "{}")
        assert eng.stereo_mode is True
        assert eng.vocal_activity() is None, \
            "stereo mix must not masquerade as stem ground truth"

    def test_auto_baseline_kicks_in(self):
        eng = self.make(lambda *a: "{}")
        assert eng.baselined is False
        clock = self.feed(eng, synth_instrumental(6.0, seed=91) * 0.5)
        eng.control_tick(clock)
        assert eng.baselined is True, \
            "completely-automatic mode must soundcheck itself"

    def test_masking_estimate_from_program_mix(self):
        eng = self.make(lambda *a: "{}")
        # vocal-forward section, then instrumental-only section
        clock = self.feed(eng, synth_vocal(6.0, seed=92) * 0.5)
        self.feed(eng, synth_instrumental(6.0, seed=93) * 0.5, start=clock)
        m = eng.degraded.masking_db()
        assert m is not None, "needs both vocal-in and band-only evidence"
        report = eng.build_report()
        assert report["analysis_mode"] == "stereo"
        assert "Lead Vox" in report["fader_map"]

    def test_review_clamps_by_role_and_moves_faders(self):
        calls = {}

        def transport(key, model, payload):
            calls["payload"] = payload
            return self.RESP

        eng = self.make(transport)
        FakePort.instances[0].on_pb(0, 9000)
        clock = self.feed(eng, synth_vocal(6.0, seed=94) * 0.5)
        eng.control_tick(clock)  # auto-baseline
        assert eng.baselined
        applied = eng.review(now=500.0)
        by = {a["stem"]: a for a in applied}
        assert by["Lead Vox"]["applied"] == 1.5   # vocal rail: +-1.5
        assert by["Gtr L"]["applied"] == -1.0     # instrument rail: +-1.0
        assert by["PROGRAM"]["applied"] > 0       # master sweetening auto
        sent = json.loads(calls["payload"]["messages"][0]["content"])
        assert sent["analysis_mode"] == "stereo"
        assert calls["payload"]["system"].startswith(
            "You are a broadcast A2 audio engineer riding faders\n"
            "on a live band streaming to YouTube. You hear ONLY")


class TestProgramChain:
    def test_creates_filters_and_corrects_tilt_gently(self):
        obs = FakeOBS()
        obs.filters["S1 Mix"] = []
        chain = ProgramChain(obs, "S1 Mix")
        assert chain.ensure_filters()
        names = [f["filterName"] for f in obs.filters["S1 Mix"]]
        assert "AD: Program EQ" in names and "AD: Program Limiter" in names
        for _ in range(200):
            chain.note_master(-18.0, -26.0)  # way too dark
        for _ in range(30):
            chain.adapt()
        assert chain.rails["master_eq_high"].value > 0.5
        assert chain.rails["master_eq_high"].value <= 3.0  # rail ceiling

    def test_missing_eq_degrades_gracefully(self):
        obs = FakeOBS()
        obs.filters["S1 Mix"] = []
        real_create = obs.create_filter

        def create(source, name, kind, settings):
            if kind == "basic_eq_filter":
                return False
            return real_create(source, name, kind, settings)

        obs.create_filter = create
        chain = ProgramChain(obs, "S1 Mix")
        assert chain.ensure_filters() is True, \
            "comp+limiter present -> chain must run without EQ"
        for _ in range(200):
            chain.note_master(-18.0, -26.0)
        moved = chain.adapt()
        assert "master_eq_high" not in moved and \
            "master_eq_low" not in moved

    def test_vst_mode_program_volume_ride_only(self):
        from autodirector.mixer.program import ProgramConfig
        obs = FakeOBS()
        obs.filters["S1 Mix"] = []
        obs.volume_calls = []
        obs.set_input_volume = \
            lambda name, db: obs.volume_calls.append((name, round(db, 2))) \
            or True
        chain = ProgramChain(obs, "S1 Mix",
                             ProgramConfig(target_loud_db=-16.0,
                                           native_filters=False))
        for _ in range(400):
            chain.note_master(-20.0, -12.0)  # 4 dB under target
        for _ in range(30):
            chain.adapt()
        assert obs.filters["S1 Mix"] == [], "VST mode must add no filters"
        assert obs.volume_calls, "loudness must ride input volume"
        assert 3.5 <= obs.volume_calls[-1][1] <= 4.5
        assert chain.nudge("master_eq_high", 1.0) == 0.0  # frozen in VST mode
        assert chain.nudge("master_volume", 0.25) != 0.0

    def test_deadband_leaves_good_mix_alone(self):
        obs = FakeOBS()
        obs.filters["S1 Mix"] = []
        chain = ProgramChain(obs, "S1 Mix")
        chain.ensure_filters()
        for _ in range(200):
            chain.note_master(-16.0, -11.0)  # close to target
        moved = chain.adapt()
        assert "master_eq_high" not in moved and "master_eq_low" not in moved


class TestDirectorStemHint:
    def test_hint_overrides_mix_inference(self, tmp_path):
        from autodirector.app import LiveEngine
        from test_engines import FakeCapture, FakeSceneOBS
        instrumental = synth_instrumental(8.0)
        obs = FakeSceneOBS()
        eng = LiveEngine({"singer_scene": "Singer",
                          "instrumental_scenes": ["Wide"]},
                         obs, FakeCapture(instrumental))
        eng.stem_vocal_hint = True  # lead stem says: singing
        while eng.capture.pos < len(instrumental):
            eng.step()
        assert "Singer" in obs.scene_calls, \
            "stem ground truth must drive the director even when the " \
            "mix inference disagrees"

class TestParamKnobs:
    """Slight VST tweaks inside the DAW via Control-Link-mapped CCs."""

    def make(self, mode="absolute", baseline_cc=64):
        from autodirector.mixer.knobs import ParamKnobs
        knobs = ParamKnobs(
            [{"cc": 1, "name": "Vox Comp Threshold",
              "mode": mode, "baseline_cc": baseline_cc},
             {"cc": 2, "name": "Vox Reverb Send", "mode": mode}],
            port_factory=FakePort)
        port = next(p for p in FakePort.instances
                    if p.name == "AutoDirector Params")
        return knobs, port

    def test_absolute_mode_slews_one_tick_per_control_tick(self):
        knobs, port = self.make()
        assert knobs.nudge("Vox Comp Threshold", 3) == 3.0
        for _ in range(5):  # more ticks than needed — must stop at target
            knobs.control_tick()
        assert [v for (_, cc, v) in port.ccs if cc == 1] == [65, 66, 67], \
            "one tick per control tick, parked at baseline+3"

    def test_relative_mode_sends_binary_offset_increments(self):
        knobs, port = self.make(mode="relative")
        knobs.nudge("Vox Reverb Send", -2)
        for _ in range(4):
            knobs.control_tick()
        assert [v for (_, cc, v) in port.ccs if cc == 2] == [63, 63], \
            "relative maps get 64-1 per downward tick, nothing after"

    def test_per_review_and_total_clamps(self):
        knobs, port = self.make()
        assert knobs.nudge("Vox Comp Threshold", 40) == 6.0, \
            "a single review is capped at +-6 ticks"
        assert knobs.nudge("Vox Comp Threshold", 6) == 6.0
        assert knobs.nudge("Vox Comp Threshold", 6) == 4.0, \
            "lifetime travel clamps at +-16 ticks from soundcheck"
        for _ in range(30):
            knobs.control_tick()
        vals = [v for (_, cc, v) in port.ccs if cc == 1]
        assert len(vals) == 16 and vals[-1] == 64 + 16

    def test_freeze_blocks_nudges_and_movement(self):
        knobs, port = self.make()
        knobs.nudge("Vox Comp Threshold", 3)
        assert knobs.freeze("Vox Comp Threshold") is True
        knobs.control_tick()
        assert port.ccs == [], "frozen knob must not emit CCs"
        assert knobs.nudge("Vox Comp Threshold", 2) == 0.0
        assert knobs.freeze("Nope") is False

    def test_unmapped_knob_is_untouchable(self):
        knobs, port = self.make()
        assert knobs.nudge("Master Limiter Ceiling", 6) == 0.0
        knobs.control_tick()
        assert port.ccs == []

    def test_reset_baseline_re_zeros_travel(self):
        knobs, port = self.make()
        knobs.nudge("Vox Comp Threshold", 6)
        for _ in range(10):
            knobs.control_tick()
        knobs.reset_baseline()
        assert knobs.nudge("Vox Comp Threshold", 6) == 6.0, \
            "soundcheck resets the +-16 travel budget"
        state = {k["name"]: k for k in knobs.ui_state()}
        assert state["Vox Comp Threshold"]["offset_ticks"] == 0

    def test_no_config_means_unavailable_and_inert(self):
        from autodirector.mixer.knobs import ParamKnobs
        knobs = ParamKnobs([], port_factory=FakePort)
        assert knobs.available is False
        assert knobs.nudge("anything", 3) == 0.0
        knobs.control_tick()  # must not raise
        assert knobs.report() == {}

    def test_broken_port_degrades_gracefully(self):
        from autodirector.mixer.knobs import ParamKnobs
        knobs = ParamKnobs([{"cc": 1, "name": "Vox Comp Threshold"}],
                           port_factory=BrokenPortFactory)
        assert knobs.available is False and knobs.error
        assert knobs.nudge("Vox Comp Threshold", 3) == 0.0
        knobs.control_tick()  # must not raise


class TestEngineerKnobs:
    """AI review path: knob deltas from the model reach the DAW railed."""

    RESP = json.dumps({
        "adjustments": [],
        "knobs": [
            {"name": "Vox Comp Threshold", "delta_ticks": 3,
             "reason": "vocal peaks poking out"},
            {"name": "Vox Comp Threshold_TYPO", "delta_ticks": 3,
             "reason": "unmapped — dropped"},
            {"name": "Vox Reverb Send", "delta_ticks": 40,
             "reason": "absurd — clamps to 6"},
        ]})

    def make(self, ports=FakePort):
        cfg = {"channels": 16, "program_source": "S1 Mix",
               "stems": [{"channel": 0, "name": "Lead Vox"},
                         {"channel": 1, "name": "Gtr L"}],
               "knobs": [{"cc": 1, "name": "Vox Comp Threshold"},
                         {"cc": 2, "name": "Vox Reverb Send"}],
               "ai_review": {"enabled": True, "interval_s": 60}}
        obs = FakeOBS()
        obs.filters["S1 Mix"] = []
        return MixEngineer(cfg, obs=obs, port_factory=ports,
                           ai_transport=lambda *a: self.RESP, api_key="k")

    def prime(self, eng):
        audio = multich(6.0, {0: synth_vocal(6.0) * 0.4,
                              1: synth_lead_guitar(6.0) * 0.4})
        for s in range(0, len(audio), 4800):
            eng.process(audio[s:s + 4800], s / SR)
        eng.snapshot_baseline()

    def test_review_applies_railed_knob_deltas_then_slews(self):
        eng = self.make()
        self.prime(eng)
        applied = eng.review(now=1000.0)
        knob = {a["stem"]: a for a in applied if a.get("param") == "knob"}
        assert knob["Vox Comp Threshold"]["applied"] == 3.0
        assert knob["Vox Reverb Send"]["applied"] == 6.0  # clamped
        assert "Vox Comp Threshold_TYPO" not in knob
        port = next(p for p in FakePort.instances
                    if p.name == "AutoDirector Params")
        assert port.ccs == [], "review only sets targets — no CC jump"
        for i in range(8):
            eng.control_tick(1000.0 + 0.5 * (i + 1) + 0.01)
        cc1 = [v for (_, cc, v) in port.ccs if cc == 1]
        assert cc1 == [65, 66, 67], "slewed one tick per 0.5s"

    def test_prompt_lists_mapped_knobs(self):
        seen = {}

        def transport(key, model, payload):
            seen["payload"] = payload
            return "{}"

        eng = self.make()
        eng._transport = transport
        self.prime(eng)
        eng.review(now=1000.0)
        report = json.loads(seen["payload"]["messages"][0]["content"])
        assert "Vox Comp Threshold" in report["plugin_knobs"]

    def test_advisory_mode_suggests_but_never_sends(self):
        eng = self.make(ports=BrokenPortFactory)
        assert eng.advisory is True
        self.prime(eng)
        applied = eng.review(now=1000.0)
        knob = {a["stem"]: a for a in applied if a.get("param") == "knob"}
        assert knob["Vox Comp Threshold"]["advisory"] is True
        assert knob["Vox Comp Threshold"]["applied"] == 0.0
        assert knob["Vox Comp Threshold"]["suggested"] == 3.0
        eng.control_tick(1000.6)
        assert FakePort.instances == [], "no ports were ever opened"

    def test_freeze_knob_endpoint_path(self):
        eng = self.make()
        assert eng.freeze_knob("Vox Comp Threshold", True) is True
        assert eng.freeze_knob("Nope", True) is False
        state = {k["name"]: k for k in eng.ui_state()["knobs"]}
        assert state["Vox Comp Threshold"]["frozen"] is True
