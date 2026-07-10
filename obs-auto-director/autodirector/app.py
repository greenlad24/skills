"""AutoDirector application: wiring, engines, and CLI.

Engines are dependency-injected (capture, OBS client, tagger) so the full
pipeline — audio -> DSP -> switcher -> director -> OBS — is testable
end-to-end with synthetic audio and a fake OBS.

Fail-safe rules (docs/ARCHITECTURE.md): if capture stalls or OBS drops,
the engine freezes cuts and reports status; it never guesses.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Dict, List, Optional

import numpy as np

from .core import (LevelVAD, LiveConfig, LiveDirector, PodcastConfig,
                   PodcastDirector, SpeakerCfg, EvidenceSwitcher,
                   SwitcherConfig, apply_crosstalk_gate, min_shot_factor)
from .chain import AIReviewer, ChainConfig, SpeakerMeter, VoiceChain
from .classify import AudioTagger, fuse_vocal_confidence
from .dsp import CalibrationResult, Frontend, PitchPrior, VocalPresence

log = logging.getLogger("autodirector")


# ---------------------------------------------------------------------------
# Live mode
# ---------------------------------------------------------------------------

class LiveEngine:
    """Single mixed feed -> vocal confidence -> switcher -> LiveDirector."""

    def __init__(self, cfg: dict, obs, capture,
                 tagger: Optional[AudioTagger] = None,
                 on_cut=None):
        self.cfg = cfg
        self.obs = obs
        self.capture = capture
        self.tagger = tagger
        self.on_cut = on_cut
        self.frontend = Frontend()
        cal = self._load_calibration(cfg.get("calibration_file"))
        prior = self._load_prior(cfg.get("calibration_file"))
        self.vocal = VocalPresence(calibration=cal, pitch_prior=prior,
                                   bias=float(cfg.get("sensitivity_bias", 0.0)))
        dwell_mult = cal.dwell_multiplier if cal else 1.0
        self.switcher = EvidenceSwitcher(SwitcherConfig(
            dwell_s={"VOCAL": float(cfg.get("vocal_in_dwell_s", 0.5)),
                     "INSTRUMENTAL": float(cfg.get("vocal_out_dwell_s", 2.5))},
            dwell_multiplier=dwell_mult))
        self.director = LiveDirector(LiveConfig(
            singer_scene=cfg["singer_scene"],
            instrumental_scenes=list(cfg.get("instrumental_scenes", [])),
        ))
        self._tags = None
        self._pending_scene_sync: List[str] = []
        self.status = "starting"

    # -- calibration ---------------------------------------------------
    @staticmethod
    def _load_calibration(path) -> Optional[CalibrationResult]:
        if not path:
            return None
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return None
        with open(path) as f:
            d = json.load(f)
        return CalibrationResult(w=np.array(d["w"]), b=d["b"],
                                 d_prime=d["d_prime"],
                                 dwell_multiplier=d.get("dwell_multiplier", 1.0))

    @staticmethod
    def _load_prior(path) -> Optional[PitchPrior]:
        if not path:
            return None
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return None
        with open(path) as f:
            d = json.load(f)
        if "f0_lo" in d and d["f0_lo"]:
            return PitchPrior(d["f0_lo"], d["f0_hi"])
        return None

    def note_external_scene(self, name: str) -> None:
        self._pending_scene_sync.append(name)

    # -- one processing step -------------------------------------------
    def step(self) -> List:
        """Process buffered audio; returns cuts made this step."""
        pcm = self.capture.read()
        cuts = []
        if pcm is None:
            if not self.capture.alive():
                self.status = "no audio — cuts frozen"
            return cuts
        self.status = "running"
        tags = self.tagger.update(pcm, self.capture.audio_clock) \
            if self.tagger else None
        if tags is not None:
            self._tags = tags
        for hop in self.frontend.process(pcm):
            while self._pending_scene_sync:
                self.director.pace.sync(hop.t, self._pending_scene_sync.pop(0))
            conf = self.vocal.update(hop)
            conf = fuse_vocal_confidence(conf, self._tags)
            ev = self.switcher.update(hop.t, {"VOCAL": conf,
                                              "INSTRUMENTAL": 1.0 - conf})
            if ev:
                self.director.pace.min_shot_factor = \
                    min_shot_factor(ev.commit_conf)
            # Vocal evidence building but not yet confirmed: hold the
            # rotation rather than cutting a beat before the entrance.
            # 0.35 sits well above calibrated instrumental confidence but
            # fires early in a genuine vocal rise; a spurious hold only
            # delays a rotation by ~0.6s, which is invisible.
            if (self.switcher.state != "VOCAL"
                    and self.switcher.smoothed.get("VOCAL", 0.0) >= 0.35):
                self.director.defer_rotation(hop.t)
            cut = self.director.update(hop.t,
                                       self.switcher.state == "VOCAL",
                                       energy_db=hop.rms_db)
            if cut:
                cuts.append(cut)
                self._emit(cut)
        return cuts

    def _emit(self, cut) -> None:
        ok = self.obs.set_current_scene(cut.scene)
        log.info("CUT -> %-20s (%s)%s", cut.scene, cut.reason,
                 "" if ok else "  [OBS DOWN — not applied]")
        if self.on_cut:
            self.on_cut(cut, ok)


# ---------------------------------------------------------------------------
# Podcast mode
# ---------------------------------------------------------------------------

class PodcastSpeaker:
    """Everything one speaker owns: capture channel, DSP, VAD, meter, chain."""

    def __init__(self, cfg: dict, obs, capture, channel: Optional[int]):
        self.name = cfg["name"]
        self.capture = capture
        self.channel = channel
        self.frontend = Frontend()
        self.vad = LevelVAD(margin_db=float(cfg.get("sensitivity_db", 8.0)),
                            attack_s=0.15, release_s=0.35)
        self.meter = SpeakerMeter()
        self.obs_source = cfg.get("obs_source", "")
        self.chain = VoiceChain(obs, self.obs_source) \
            if self.obs_source else None
        self.level_db = -90.0
        self.talking = False


class PodcastEngine:
    """Per-speaker mics -> VADs -> PodcastDirector; adaptive chains + AI."""

    def __init__(self, cfg: dict, obs, captures: Dict[str, object],
                 tagger: Optional[AudioTagger] = None, on_cut=None,
                 ai_transport=None):
        self.cfg = cfg
        self.obs = obs
        self.on_cut = on_cut
        self.tagger = tagger
        self.speakers: List[PodcastSpeaker] = []
        for sp_cfg in cfg["speakers"]:
            cap = captures[sp_cfg["capture"]]
            self.speakers.append(PodcastSpeaker(
                sp_cfg, obs, cap, sp_cfg.get("channel")))
        self.director = PodcastDirector(PodcastConfig(
            speakers=[SpeakerCfg(s["name"], s["medium_scene"],
                                 s.get("closeup_scene") or s["medium_scene"])
                      for s in cfg["speakers"]],
            wide_scene=cfg.get("wide_scene", ""),
        ))
        chain_cfg = cfg.get("voice_chain", {})
        self.chain_enabled = bool(chain_cfg.get("enabled", True))
        self._last_adapt = 0.0
        ai_cfg = cfg.get("ai_review", {})
        api_key = os.environ.get(ai_cfg.get("api_key_env",
                                            "ANTHROPIC_API_KEY"), "")
        chains = {s.name: s.chain for s in self.speakers if s.chain}
        self.reviewer = None
        if ai_cfg.get("enabled") and chains and api_key:
            self.reviewer = AIReviewer(
                api_key, chains,
                model=ai_cfg.get("model", "claude-haiku-4-5-20251001"),
                interval_s=float(ai_cfg.get("interval_s", 180.0)),
                audit_path=os.path.expanduser(
                    ai_cfg.get("audit_log",
                               "~/.autodirector/ai_audit.jsonl")),
                transport=ai_transport)
        self._pending_scene_sync: List[str] = []
        self._tags = None
        self.status = "starting"

    def note_external_scene(self, name: str) -> None:
        self._pending_scene_sync.append(name)

    def step(self) -> List:
        cuts = []
        # 1. Drain each speaker's audio into hops; update VAD + meter.
        clock = 0.0
        stalled = False
        per_speaker_hops = []
        for sp in self.speakers:
            pcm = sp.capture.read()
            clock = max(clock, sp.capture.audio_clock)
            if pcm is None:
                per_speaker_hops.append([])
                if not sp.capture.alive():
                    stalled = True
                continue
            if pcm.ndim == 2 and sp.channel is not None:
                pcm = pcm[:, sp.channel]
            if self.tagger is not None:
                tags = self.tagger.update(pcm, clock)
                if tags is not None:
                    self._tags = tags
            hops = sp.frontend.process(pcm)
            for hop in hops:
                sp.talking = sp.vad.update(hop.t, hop.rms_db)
                sp.level_db = hop.rms_db
                sp.meter.update(hop, sp.talking)
            per_speaker_hops.append(hops)
        if stalled:
            self.status = "no audio — cuts frozen"
            return cuts
        self.status = "running"

        # 2. Director tick (one per step at the shared clock).
        while self._pending_scene_sync:
            self.director.pace.sync(clock, self._pending_scene_sync.pop(0))
        talking = [sp.talking for sp in self.speakers]
        levels = [sp.level_db for sp in self.speakers]
        talking = apply_crosstalk_gate(talking, levels)
        cut = self.director.update(clock, talking, levels)
        if cut:
            cuts.append(cut)
            ok = self.obs.set_current_scene(cut.scene)
            log.info("CUT -> %-20s (%s)%s", cut.scene, cut.reason,
                     "" if ok else "  [OBS DOWN — not applied]")
            if self.on_cut:
                self.on_cut(cut, ok)

        # 3. Adaptive chains (2 s cadence) + AI review when due.
        if self.chain_enabled and (clock - self._last_adapt) >= 2.0:
            self._last_adapt = clock
            for sp in self.speakers:
                if sp.chain:
                    sp.chain.adapt(sp.meter.snapshot(), sp.talking)
            if self.reviewer and self.reviewer.due():
                threading.Thread(target=self._run_review,
                                 daemon=True).start()
        return cuts

    def _run_review(self) -> None:
        snaps = {sp.name: sp.meter.snapshot() for sp in self.speakers}
        noise = {}
        if self._tags is not None:
            noise = {k: v for k, v in self._tags.groups.items()
                     if k.startswith("noise_") and v > 0.15}
        try:
            self.reviewer.review(snaps, noise)
        except Exception:
            log.exception("AI review failed")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_config(path: str) -> dict:
    with open(os.path.expanduser(path)) as f:
        return json.load(f)


def build_and_run(config_path: str, dry_run: bool = False) -> None:
    from .io.capture import AudioCapture
    from .io.obsws import OBSClient

    cfg = load_config(config_path)
    mode = cfg.get("mode", "live")

    engine_holder = {}

    def on_scene_changed(name: str) -> None:
        eng = engine_holder.get("engine")
        if eng:
            eng.note_external_scene(name)

    class DryOBS:
        state = "dry-run"
        def set_current_scene(self, name):
            return True
        def __getattr__(self, item):
            return lambda *a, **k: None

    obs_cfg = cfg.get("obs", {})
    if dry_run:
        obs = DryOBS()
    else:
        obs = OBSClient(host=obs_cfg.get("host", "127.0.0.1"),
                        port=int(obs_cfg.get("port", 4455)),
                        password=obs_cfg.get("password", ""),
                        on_scene_changed=on_scene_changed)
        obs.start()

    cls_cfg = cfg.get("classifier", {})
    tagger = AudioTagger(cls_cfg.get("model"), cls_cfg.get("class_map"))

    if mode == "live":
        lcfg = cfg["live"]
        capture = AudioCapture(device=lcfg.get("device"),
                               channels=int(lcfg.get("channels", 1)))
        capture.start()
        engine = LiveEngine(lcfg, obs, capture, tagger=tagger)
    else:
        pcfg = cfg["podcast"]
        captures = {}
        for sp in pcfg["speakers"]:
            key = sp["capture"] = sp.get("capture") or sp["device"]
            if key not in captures:
                captures[key] = AudioCapture(
                    device=sp["device"],
                    channels=int(sp.get("device_channels", 1)))
                captures[key].start()
        engine = PodcastEngine(pcfg, obs, captures, tagger=tagger)
    engine_holder["engine"] = engine

    log.info("AutoDirector running (%s mode). Ctrl-C to stop.", mode)
    try:
        while True:
            engine.step()
            time.sleep(0.05)
    except KeyboardInterrupt:
        log.info("stopping.")
    finally:
        if not dry_run:
            obs.stop()


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="[%(name)s] %(message)s")
    p = argparse.ArgumentParser(
        prog="autodirector",
        description="Automatic scene director for OBS (live show / podcast).")
    sub = p.add_subparsers(dest="cmd")

    runp = sub.add_parser("run", help="run the director")
    runp.add_argument("--config", required=True)
    runp.add_argument("--dry-run", action="store_true",
                      help="print cuts without touching OBS")

    sub.add_parser("devices", help="list audio input devices")

    calp = sub.add_parser("calibrate", help="run the calibration wizard")
    calp.add_argument("--config", required=True)

    args = p.parse_args(argv)
    if args.cmd == "run":
        build_and_run(args.config, dry_run=args.dry_run)
    elif args.cmd == "devices":
        from .io.capture import AudioCapture
        print(AudioCapture.list_devices())
    elif args.cmd == "calibrate":
        from .calibrate import wizard
        wizard(args.config)
    else:
        p.print_help()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
