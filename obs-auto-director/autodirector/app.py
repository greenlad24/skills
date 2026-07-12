"""AutoDirector application: engines, runtime, and CLI.

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
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .core import (LevelVAD, LiveConfig, LiveDirector, PodcastConfig,
                   PodcastDirector, SpeakerCfg, EvidenceSwitcher,
                   SwitcherConfig, apply_crosstalk_gate, min_shot_factor)
from .chain import AIReviewer, ChainConfig, SpeakerMeter, VoiceChain
from .classify import AudioTagger, fuse_vocal_confidence
from .dsp import (CalibrationResult, Calibrator, Frontend, PitchPrior,
                  VocalPresence)

log = logging.getLogger("autodirector")

DEFAULT_CONFIG_PATH = "~/.autodirector/config.json"

DEFAULT_CONFIG = {
    "obs": {"host": "127.0.0.1", "port": 4455, "password": ""},
    "mode": "live",
    "ui": {"port": 8787, "open_browser": True},
    "live": {
        "device": None, "channels": 1,
        "singer_scene": "", "instrumental_scenes": [],
        "calibration_file": "~/.autodirector/live_cal.json",
        "sensitivity_bias": 0.0,
    },
    "podcast": {
        "speakers": [],
        "wide_scene": "",
        "voice_chain": {"enabled": True, "target_speech_db": -20.0},
        "ai_review": {"enabled": False,
                      "api_key_env": "ANTHROPIC_API_KEY",
                      "model": "claude-haiku-4-5-20251001",
                      "interval_s": 180,
                      "audit_log": "~/.autodirector/ai_audit.jsonl"},
    },
    "classifier": {"model": "", "class_map": ""},
}


# ---------------------------------------------------------------------------
# Live mode
# ---------------------------------------------------------------------------

class LiveEngine:
    """Single mixed feed -> vocal confidence -> switcher -> LiveDirector."""

    mode = "live"

    def __init__(self, cfg: dict, obs, capture,
                 tagger: Optional[AudioTagger] = None,
                 on_cut=None):
        self.cfg = cfg
        self.obs = obs
        self.capture = capture
        self.tagger = tagger
        self.on_cut = on_cut
        self.frontend = Frontend()
        self.cal = self._load_calibration(cfg.get("calibration_file"))
        prior = self._load_prior(cfg.get("calibration_file"))
        self.vocal = VocalPresence(calibration=self.cal, pitch_prior=prior,
                                   bias=float(cfg.get("sensitivity_bias", 0.0)))
        dwell_mult = self.cal.dwell_multiplier if self.cal else 1.0
        self.switcher = EvidenceSwitcher(SwitcherConfig(
            dwell_s={"VOCAL": float(cfg.get("vocal_in_dwell_s", 0.5)),
                     "INSTRUMENTAL": float(cfg.get("vocal_out_dwell_s", 2.5))},
            dwell_multiplier=dwell_mult))
        self.director = LiveDirector(LiveConfig(
            singer_scene=cfg.get("singer_scene", ""),
            instrumental_scenes=list(cfg.get("instrumental_scenes", [])),
        ))
        self.active = True
        self.cuts: deque = deque(maxlen=80)
        self.current_scene: Optional[str] = None
        self.vocal_conf = 0.0
        # Ground truth from the Mix Engineer's lead-vocal stem (when the
        # mixer module runs): overrides mixed-feed inference entirely.
        self.stem_vocal_hint: Optional[bool] = None
        self._tags = None
        self._pending_scene_sync: List[str] = []
        self.status = "starting"
        # In-UI calibration session
        self._calibrator: Optional[Calibrator] = None
        self._cal_phase: Optional[str] = None
        self._cal_phase_end = 0.0
        self._cal_counts = (0, 0)

    # -- calibration persistence ----------------------------------------
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
        if d.get("f0_lo"):
            return PitchPrior(d["f0_lo"], d["f0_hi"])
        return None

    # -- in-UI calibration session ----------------------------------------
    def calibration_start_phase(self, phase: str,
                                seconds: float = 10.0) -> None:
        assert phase in ("instrumental", "vocal")
        if self._calibrator is None:
            self._calibrator = Calibrator()
        self._cal_phase = phase
        self._cal_phase_end = self.capture.audio_clock + seconds

    def calibration_state(self) -> dict:
        i, v = self._calibrator.sample_counts() if self._calibrator else (0, 0)
        remaining = max(0.0, self._cal_phase_end - self.capture.audio_clock) \
            if self._cal_phase else 0.0
        return {"session": self._calibrator is not None,
                "phase": self._cal_phase, "remaining_s": round(remaining, 1),
                "instrumental_samples": i, "vocal_samples": v,
                "calibrated": self.cal is not None,
                "d_prime": round(self.cal.d_prime, 2) if self.cal else None}

    def calibration_finish(self) -> dict:
        if self._calibrator is None:
            return {"ok": False, "error": "no calibration session"}
        result = self._calibrator.finish()
        if result is None:
            return {"ok": False,
                    "error": "not enough material — record both phases"}
        path = os.path.expanduser(
            self.cfg.get("calibration_file",
                         "~/.autodirector/live_cal.json"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        prior = self._load_prior(self.cfg.get("calibration_file"))
        with open(path, "w") as f:
            json.dump({"w": [float(x) for x in result.w], "b": result.b,
                       "d_prime": result.d_prime,
                       "dwell_multiplier": result.dwell_multiplier,
                       "f0_lo": prior.f0_lo if prior else None,
                       "f0_hi": prior.f0_hi if prior else None}, f, indent=2)
        self.cal = result
        self.vocal = VocalPresence(
            calibration=result, pitch_prior=prior,
            bias=float(self.cfg.get("sensitivity_bias", 0.0)))
        self.switcher.cfg.dwell_multiplier = result.dwell_multiplier
        self._calibrator = None
        self._cal_phase = None
        return {"ok": True, "d_prime": round(result.d_prime, 2),
                "weak": result.weak}

    def calibration_cancel(self) -> None:
        self._calibrator = None
        self._cal_phase = None

    # -- runtime ---------------------------------------------------------
    def note_external_scene(self, name: str) -> None:
        self._pending_scene_sync.append(name)
        self.current_scene = name

    def step(self) -> List:
        pcm = self.capture.read()
        cuts = []
        if pcm is None:
            if not self.capture.alive():
                self.status = "no audio — cuts frozen"
            return cuts
        self.status = "running" if self.active else "paused"
        tags = self.tagger.update(pcm, self.capture.audio_clock) \
            if self.tagger else None
        if tags is not None:
            self._tags = tags
        for hop in self.frontend.process(pcm):
            while self._pending_scene_sync:
                self.director.pace.sync(hop.t, self._pending_scene_sync.pop(0))
            conf = self.vocal.update(hop)
            conf = fuse_vocal_confidence(conf, self._tags)
            if self.stem_vocal_hint is not None:
                # The lead-vocal stem is a directly observed signal —
                # near-ground-truth, so it wins over mix inference.
                conf = 0.92 if self.stem_vocal_hint else 0.08
            self.vocal_conf = conf
            if self._cal_phase is not None:
                feats = self.vocal.features()
                self._calibrator.collect(feats, self._cal_phase == "vocal")
                if hop.t >= self._cal_phase_end:
                    self._cal_phase = None
            ev = self.switcher.update(hop.t, {"VOCAL": conf,
                                              "INSTRUMENTAL": 1.0 - conf})
            if ev:
                self.director.pace.min_shot_factor = \
                    min_shot_factor(ev.commit_conf)
            if (self.switcher.state != "VOCAL"
                    and self.switcher.smoothed.get("VOCAL", 0.0) >= 0.35):
                self.director.defer_rotation(hop.t)
            if not self.active:
                continue
            cut = self.director.update(hop.t,
                                       self.switcher.state == "VOCAL",
                                       energy_db=hop.rms_db)
            if cut:
                cuts.append(cut)
                self._emit(hop.t, cut)
        return cuts

    def _emit(self, t: float, cut) -> None:
        ok = self.obs.set_current_scene(cut.scene)
        self.current_scene = cut.scene
        self.cuts.appendleft({"t": round(t, 2), "scene": cut.scene,
                              "reason": cut.reason,
                              "priority": cut.priority, "applied": ok})
        log.info("CUT -> %-20s (%s)%s", cut.scene, cut.reason,
                 "" if ok else "  [OBS DOWN — not applied]")
        if self.on_cut:
            self.on_cut(cut, ok)

    def ui_state(self) -> dict:
        return {
            "mode": "live",
            "status": self.status,
            "active": self.active,
            "audio_alive": self.capture.alive(),
            "clock": round(self.capture.audio_clock, 1),
            "current_scene": self.current_scene,
            "cuts": list(self.cuts)[:50],
            "live": {
                "vocal_conf": round(self.vocal_conf, 3),
                "state": self.switcher.state or "—",
                "singer_scene": self.director.cfg.singer_scene,
                "instrumental_scenes": self.director.cfg.instrumental_scenes,
                "calibration": self.calibration_state(),
            },
        }


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
        if self.obs_source:
            from .chain.fastloop import ChainConfig as _CC
            self.chain = VoiceChain(obs, self.obs_source, _CC(
                native_filters=bool(cfg.get("native_filters", True))))
        else:
            self.chain = None
        self.level_db = -90.0
        self.talking = False


class PodcastEngine:
    """Per-speaker mics -> VADs -> PodcastDirector; adaptive chains + AI."""

    mode = "podcast"

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
        self.active = True
        self.cuts: deque = deque(maxlen=80)
        self.ai_log: deque = deque(maxlen=40)
        self.current_scene: Optional[str] = None
        self._pending_scene_sync: List[str] = []
        self._tags = None
        self.status = "starting"

    def note_external_scene(self, name: str) -> None:
        self._pending_scene_sync.append(name)
        self.current_scene = name

    def freeze_param(self, speaker: str, param: str, frozen: bool) -> bool:
        for sp in self.speakers:
            if sp.name == speaker and sp.chain:
                sp.chain.freeze(param, frozen)
                return True
        return False

    def step(self) -> List:
        cuts = []
        clock = 0.0
        stalled = False
        for sp in self.speakers:
            pcm = sp.capture.read()
            clock = max(clock, sp.capture.audio_clock)
            if pcm is None:
                if not sp.capture.alive():
                    stalled = True
                continue
            if pcm.ndim == 2 and sp.channel is not None:
                pcm = pcm[:, sp.channel]
            if self.tagger is not None:
                tags = self.tagger.update(pcm, clock)
                if tags is not None:
                    self._tags = tags
            for hop in sp.frontend.process(pcm):
                sp.talking = sp.vad.update(hop.t, hop.rms_db)
                sp.level_db = hop.rms_db
                sp.meter.update(hop, sp.talking)
        if stalled:
            self.status = "no audio — cuts frozen"
            return cuts
        self.status = "running" if self.active else "paused"

        while self._pending_scene_sync:
            self.director.pace.sync(clock, self._pending_scene_sync.pop(0))
        talking = [sp.talking for sp in self.speakers]
        levels = [sp.level_db for sp in self.speakers]
        talking = apply_crosstalk_gate(talking, levels)
        if self.active:
            cut = self.director.update(clock, talking, levels)
            if cut:
                cuts.append(cut)
                ok = self.obs.set_current_scene(cut.scene)
                self.current_scene = cut.scene
                self.cuts.appendleft({"t": round(clock, 2),
                                      "scene": cut.scene,
                                      "reason": cut.reason,
                                      "priority": cut.priority,
                                      "applied": ok})
                log.info("CUT -> %-20s (%s)%s", cut.scene, cut.reason,
                         "" if ok else "  [OBS DOWN — not applied]")
                if self.on_cut:
                    self.on_cut(cut, ok)

        if self.chain_enabled and (clock - self._last_adapt) >= 2.0:
            self._last_adapt = clock
            for sp in self.speakers:
                if sp.chain:
                    sp.chain.adapt(sp.meter.snapshot(), sp.talking)
            if self.reviewer and self.reviewer.claim():
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
            applied = self.reviewer.review(snaps, noise)
            for entry in applied:
                self.ai_log.appendleft(entry)
        except Exception:
            log.exception("AI review failed")

    def ui_state(self) -> dict:
        holder = self.director.holder
        speakers = []
        for i, sp in enumerate(self.speakers):
            snap = sp.meter.snapshot()
            chain_state = None
            if sp.chain:
                chain_state = {
                    "rails": {p: round(r.value, 1)
                              for p, r in sp.chain.rails.items()},
                    "bounds": {p: [r.lo, r.hi]
                               for p, r in sp.chain.rails.items()},
                    "frozen": [p for p, r in sp.chain.rails.items()
                               if r.frozen],
                }
            speakers.append({
                "name": sp.name,
                "talking": bool(sp.talking),
                "has_floor": holder == i,
                "level_db": round(max(sp.level_db, -90.0), 1),
                "floor_db": round(sp.vad.floor_db, 1),
                "speech_db": round(snap.speech_db, 1),
                "chain": chain_state,
            })
        return {
            "mode": "podcast",
            "status": self.status,
            "active": self.active,
            "audio_alive": all(sp.capture.alive() for sp in self.speakers),
            "clock": round(max((sp.capture.audio_clock
                                for sp in self.speakers), default=0.0), 1),
            "current_scene": self.current_scene,
            "cuts": list(self.cuts)[:50],
            "podcast": {
                "speakers": speakers,
                "shot": self.director.shot,
                "wide": self.director.wide,
                "ai_enabled": self.reviewer is not None,
                "ai_log": list(self.ai_log)[:20],
            },
        }


# ---------------------------------------------------------------------------
# Runtime: config + OBS + engine lifecycle (supports live rebuild from UI)
# ---------------------------------------------------------------------------

class _DryOBS:
    state = "dry-run"

    def set_current_scene(self, name):
        return True

    def get_scene_names(self):
        return []

    def __getattr__(self, item):
        return lambda *a, **k: None


class Runtime:
    """Owns config, the OBS client, captures, and the current engine.

    The Control Room UI drives this object: pause/resume, calibration,
    config save + live rebuild.
    """

    def __init__(self, config_path: str, dry_run: bool = False):
        self.config_path = os.path.expanduser(config_path)
        self.dry_run = dry_run
        self.cfg = self._load_or_create()
        self.obs = None
        self.engine = None
        self.mixer = None
        self.captures: Dict[str, object] = {}
        self.error: Optional[str] = None
        self._lock = threading.RLock()

    # -- config ------------------------------------------------------------
    def _load_or_create(self) -> dict:
        if os.path.exists(self.config_path):
            with open(self.config_path) as f:
                return json.load(f)
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        os.makedirs(os.path.dirname(self.config_path) or ".", exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(cfg, f, indent=2)
        return cfg

    def save_config(self, new_cfg: dict) -> dict:
        with self._lock:
            self.cfg = new_cfg
            with open(self.config_path, "w") as f:
                json.dump(new_cfg, f, indent=2)
            ok, err = self.rebuild()
            return {"saved": True, "engine_ok": ok, "error": err}

    # -- lifecycle -----------------------------------------------------------
    def _stop_engine(self) -> None:
        for cap in self.captures.values():
            try:
                cap.stop()
            except Exception:
                pass
        self.captures = {}
        self.engine = None
        if self.mixer is not None:
            try:
                self.mixer.close()
            except Exception:
                pass
            self.mixer = None

    def rebuild(self) -> tuple:
        """(Re)build OBS client + engine from current config."""
        with self._lock:
            self._stop_engine()
            self.error = None
            try:
                self._ensure_obs()
                self._build_engine()
                return True, None
            except Exception as e:
                self.error = str(e)
                log.warning("engine not running: %s", e)
                return False, str(e)

    def _ensure_obs(self) -> None:
        if self.dry_run:
            self.obs = _DryOBS()
            return
        from .io.obsws import OBSClient
        obs_cfg = self.cfg.get("obs", {})
        if self.obs is not None:
            self.obs.stop()
        self.obs = OBSClient(host=obs_cfg.get("host", "127.0.0.1"),
                             port=int(obs_cfg.get("port", 4455)),
                             password=obs_cfg.get("password", ""),
                             on_scene_changed=self._on_scene_changed)
        self.obs.start()

    def _on_scene_changed(self, name: str) -> None:
        eng = self.engine
        if eng:
            eng.note_external_scene(name)

    def _build_engine(self) -> None:
        """Build into locals and commit atomically at the end — a partial
        failure must never leave a half-installed engine running while
        the UI reports an error."""
        from .io.capture import AudioCapture
        cfg = self.cfg
        cls_cfg = cfg.get("classifier", {})
        tagger = AudioTagger(
            os.path.expanduser(cls_cfg.get("model") or "") or None,
            os.path.expanduser(cls_cfg.get("class_map") or "") or None)
        mode = cfg.get("mode", "live")
        captures: Dict[str, object] = {}
        engine = None
        mixer = None
        try:
            if mode == "live":
                lcfg = cfg.get("live", {})
                if not lcfg.get("singer_scene"):
                    raise ValueError("setup needed: pick a singer scene")
                capture = AudioCapture(device=lcfg.get("device"),
                                       channels=int(lcfg.get("channels", 1)),
                                       loopback=bool(lcfg.get("loopback")))
                capture.start()
                captures["live"] = capture
                engine = LiveEngine(lcfg, self.obs, capture, tagger=tagger)
                mcfg = lcfg.get("mixer", {})
                if mcfg.get("enabled"):
                    from .mixer import MixEngineer
                    # capture_channels 2 = stereo program-mix analysis
                    # (fully automatic mixing without stems); 16 = stems.
                    mix_cap = AudioCapture(
                        device=mcfg.get("device"),
                        channels=int(mcfg.get("capture_channels",
                                              mcfg.get("channels", 16))),
                        loopback=bool(mcfg.get("loopback")))
                    mix_cap.start()
                    captures["mixer"] = mix_cap
                    ai_cfg = mcfg.get("ai_review", {})
                    mixer = MixEngineer(
                        mcfg, obs=self.obs,
                        api_key=os.environ.get(
                            ai_cfg.get("api_key_env",
                                       "ANTHROPIC_API_KEY"), ""))
            else:
                pcfg = cfg.get("podcast", {})
                if not pcfg.get("speakers"):
                    raise ValueError("setup needed: add speakers")
                for sp in pcfg["speakers"]:
                    key = sp["capture"] = sp.get("capture") or sp.get("device")
                    if key not in captures:
                        captures[key] = AudioCapture(
                            device=sp.get("device"),
                            channels=int(sp.get("device_channels", 1)))
                        captures[key].start()
                engine = PodcastEngine(pcfg, self.obs, captures,
                                       tagger=tagger)
        except Exception:
            for cap in captures.values():
                try:
                    cap.stop()
                except Exception:
                    pass
            raise
        self.captures = captures
        self.engine = engine
        self.mixer = mixer

    def step(self) -> None:
        with self._lock:  # never race a UI-triggered rebuild
            mixer = self.mixer
            eng = self.engine
            if mixer is not None:
                try:
                    cap = self.captures.get("mixer")
                    pcm = cap.read() if cap else None
                    if pcm is not None:
                        mixer.process(pcm, cap.audio_clock)
                        mixer.control_tick(cap.audio_clock)
                    if mixer.try_claim_review():
                        threading.Thread(target=mixer.review,
                                         daemon=True).start()
                    if eng is not None and hasattr(eng, "stem_vocal_hint"):
                        # A stalled stem capture must never pin the
                        # director: the hint is only ground truth while
                        # the mixer is actually hearing audio.
                        eng.stem_vocal_hint = mixer.vocal_activity() \
                            if (cap is not None and cap.alive()) else None
                except Exception:
                    log.exception("mixer step failed")
            if eng is not None:
                try:
                    eng.step()
                except Exception:
                    log.exception("engine step failed")

    def shutdown(self) -> None:
        with self._lock:
            self._stop_engine()
            if self.obs is not None and not self.dry_run:
                self.obs.stop()

    # -- UI state ------------------------------------------------------------
    def ui_state(self) -> dict:
        eng = self.engine
        state = eng.ui_state() if eng else {
            "mode": "setup", "status": self.error or "needs configuration",
            "active": False, "audio_alive": False, "clock": 0.0,
            "current_scene": None, "cuts": []}
        state["obs_state"] = getattr(self.obs, "state", "down") \
            if self.obs else "down"
        state["config_mode"] = self.cfg.get("mode", "live")
        state["error"] = self.error
        if self.mixer is not None:
            state["mixer"] = self.mixer.ui_state()
        return state


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_config(path: str) -> dict:
    with open(os.path.expanduser(path)) as f:
        return json.load(f)


def _run_loop(runtime: "Runtime", ui: bool, open_browser: bool) -> None:
    server = None
    if ui:
        from .ui.server import ControlRoomServer
        port = int(runtime.cfg.get("ui", {}).get("port", 8787))
        server = ControlRoomServer(runtime, port=port)
        server.start()
        url = f"http://127.0.0.1:{server.port}"
        log.info("Control Room: %s", url)
        if open_browser:
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception:
                pass
    try:
        while True:
            runtime.step()
            time.sleep(0.05)
    except KeyboardInterrupt:
        log.info("stopping.")
    finally:
        if server:
            server.stop()
        runtime.shutdown()


def build_and_run(config_path: str, dry_run: bool = False,
                  ui: bool = True, open_browser: Optional[bool] = None) -> None:
    runtime = Runtime(config_path, dry_run=dry_run)
    runtime.rebuild()
    if open_browser is None:
        open_browser = bool(runtime.cfg.get("ui", {}).get(
            "open_browser", True))
    _run_loop(runtime, ui=ui, open_browser=open_browser)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="[%(name)s] %(message)s")
    p = argparse.ArgumentParser(
        prog="autodirector",
        description="Automatic scene director for OBS (live show / podcast).")
    sub = p.add_subparsers(dest="cmd")

    appp = sub.add_parser("app", help="run with the Control Room UI "
                                      "(default config location)")
    appp.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    appp.add_argument("--no-browser", action="store_true")

    runp = sub.add_parser("run", help="run the director")
    runp.add_argument("--config", required=True)
    runp.add_argument("--dry-run", action="store_true",
                      help="print cuts without touching OBS")
    runp.add_argument("--no-ui", action="store_true")

    sub.add_parser("devices", help="list audio input devices")

    calp = sub.add_parser("calibrate", help="run the calibration wizard")
    calp.add_argument("--config", required=True)

    args = p.parse_args(argv)
    if args.cmd == "app" or args.cmd is None:
        cfg_path = getattr(args, "config", DEFAULT_CONFIG_PATH)
        build_and_run(cfg_path, ui=True,
                      open_browser=not getattr(args, "no_browser", False))
    elif args.cmd == "run":
        build_and_run(args.config, dry_run=args.dry_run,
                      ui=not args.no_ui)
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
