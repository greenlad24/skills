"""The Mix Engineer: AI-reviewed live rebalancing of a Studio One mix.

Signal topology (docs/ARCHITECTURE.md):
- Studio One pre-mixes 16 channels and feeds OBS directly (broadcast).
- Each S1 channel ALSO has a post-fader send -> BlackHole 16ch, which
  AutoDirector captures: every stem is heard exactly as it contributes
  to the broadcast mix (strip processing + fader included).
- Channel names arrive automatically over the MCU scribble-strip wire,
  so the AI reasons about instruments by name ("Kick", "Lead Vox").
- Fader rides go back into Studio One via MCU (mcu.py); the subtle
  EQ/compression "sweetening" layer is applied to the program feed in
  OBS (program.py) — per-channel plugin internals in S1 stay untouched
  and unjudged.

Two loops, same philosophy as the voice chain:
* FAST (deterministic, every ~0.5 s): slews each fader toward its
  target at <= 1 dB/s and lets the program chain make its slow, gentle
  corrections. It never invents balance moves.
* SLOW (AI, every couple of minutes): Claude reviews the per-stem
  measurements — loudness vs. soundcheck (with our own fader offsets
  compensated out, so "the band drifted" and "we moved it" are
  distinguishable), vocal masking, dead channels, program tone — and
  proposes bounded deltas with reasons.

FREEZE MIX stops all movement instantly. If AutoDirector dies, faders
stay exactly where they are.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Callable, Dict, List, Optional

from ..chain.rails import Rail
from .degraded import StereoMixAnalyzer
from .knobs import ParamKnobs
from .mcu import MCUFaders
from .program import ProgramChain
from .stems import StemAnalyzer, StemConfig, infer_role

log = logging.getLogger("autodirector.mixer")

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_DELTA_PER_REVIEW = 3.0
MASTER_PARAMS = ("master_eq_low", "master_eq_high",
                 "master_comp_threshold", "master_volume")

STEREO_MIX_PROMPT = """You are a broadcast A2 audio engineer riding faders
on a live band streaming to YouTube. You hear ONLY the stereo program
mix (no per-channel stems), so act with extra restraint.

You receive: vocal confidence, a vocal masking proxy in dB (positive =
the band crowds the lead vocal's 2-5 kHz region; estimated by comparing
vocal-in vs instrumental-only moments), side-channel presence energy
(lead vocals are center-panned, so side energy is band crowd), program
loudness/tilt/crest vs the soundcheck reference, and the fader map with
instrument names.

Respond with ONLY a JSON object:
{"adjustments": [{"stem": str, "delta_db": float, "reason": str}, ...],
 "master": [{"param": str, "delta": float, "reason": str}, ...],
 "notes": str}
Rules: the LEAD VOCAL fader only, max ±1.5 dB, and only on clear
sustained masking evidence; named instrument-group trims max ±1.0 dB
and only when masking is strongly positive AND side presence is high;
master params (master_eq_low, master_eq_high, master_comp_threshold,
master_volume) for clear sustained tonal/loudness drift. If
plugin_knobs are listed (DAW plugin parameters the user mapped for you),
you may add "knobs": [{"name": str, "delta_ticks": int, "reason": str}]
— max ±6 ticks of 127, SLIGHT tweaks only, on strong evidence. When in
doubt: empty lists — an untouched mix beats a wrongly touched one."""

MIX_SYSTEM_PROMPT = """You are a broadcast A2 audio engineer riding faders
on a live band that streams to YouTube. The band is pre-mixed in a DAW;
you make it sit right over a long show.

You receive per-stem measurements keyed by instrument name: loudness
while active (dB FS), source_drift_db (level change at the source since
soundcheck, our own fader moves already compensated out),
fader_offset_db (what we have already applied, clamped to ±6),
activity, presence-band energy, dead flags — plus vocal_masking_db
(positive = the band is crowding the lead vocal where it lives) and
program-bus tone/loudness with its current sweetening settings.

Respond with ONLY a JSON object:
{"adjustments": [{"stem": str, "delta_db": float, "reason": str}, ...],
 "master": [{"param": str, "delta": float, "reason": str}, ...],
 "notes": str}
Stem deltas: max ±3 dB per review. Master params: master_eq_low,
master_eq_high (±3 total), master_comp_threshold, master_volume. If
plugin_knobs are listed (DAW plugin parameters the user mapped for
you), you may add "knobs": [{"name": str, "delta_ticks": int,
"reason": str}] — max ±6 ticks of 127, SLIGHT tweaks only, on strong
evidence. Recommend nothing when
the mix is fine — an empty answer is a good answer. Priorities:
(1) the LEAD VOCAL sits on top: fix positive masking by lifting the
vocal and/or trimming the crowding stems slightly; (2) undo source
drift so the balance returns to soundcheck; (3) program tone: only
clear, sustained imbalance; (4) mention dead channels in notes — never
mute, a human decides that."""


class MixEngineer:
    def __init__(self, cfg: dict, obs=None,
                 port_factory: Optional[Callable] = None,
                 ai_transport: Optional[Callable] = None,
                 api_key: Optional[str] = None):
        self.n = int(cfg.get("channels", 16))
        stems = []
        by_channel = {int(s["channel"]): s for s in cfg.get("stems", [])}
        for ch in range(self.n):
            s = by_channel.get(ch, {})
            name = s.get("name", f"Ch {ch + 1}")
            stems.append(StemConfig(
                channel=ch, name=name,
                role=s.get("role") or infer_role(name)))
        self.analyzer = StemAnalyzer(stems)
        # Stereo mode: no stems available (capture is the program mix
        # itself). Fader strips/names still exist over MCU; analysis
        # comes from StereoMixAnalyzer and automatic moves run on
        # tighter, role-limited rails.
        self.stereo_mode = (int(cfg.get("capture_channels",
                                        cfg.get("channels", 16))) <= 2
                            or cfg.get("analysis_mode") == "stereo")
        self.degraded = StereoMixAnalyzer() if self.stereo_mode else None
        self.auto_baseline_s = float(cfg.get("auto_baseline_s", 45.0))
        self.faders = MCUFaders(n_channels=self.n,
                                port_factory=port_factory)
        # Slight VST tweaks inside the DAW, via Control-Link-mapped CCs.
        self.knobs = ParamKnobs(cfg.get("knobs", []),
                                port_factory=port_factory)
        self.rails: Dict[int, Rail] = {
            ch: Rail(f"fader:{ch}", 0.0, lo=-6.0, hi=6.0, max_step=0.5)
            for ch in range(self.n)}  # 0.5 dB per 0.5 s tick = 1 dB/s
        self.targets: Dict[int, float] = {ch: 0.0 for ch in range(self.n)}
        self.reference: Dict[int, float] = {}
        self.master_channels = list(cfg.get("master_channels", []))
        prog_source = cfg.get("program_source", "")
        if obs is not None and prog_source:
            from .program import ProgramConfig
            pc = ProgramConfig(native_filters=bool(
                cfg.get("program_native_filters", True)))
            self.program = ProgramChain(obs, prog_source, pc)
        else:
            self.program = None
        # Control mode: "auto" moves faders over MCU; "advisory" posts
        # recommendations in the Control Room for the human to apply —
        # the zero-install tier (no loopMIDI/virtual ports needed). Auto
        # degrades to advisory automatically when MIDI is unavailable.
        self.control_mode = cfg.get("control_mode", "auto")
        self.frozen_all = False
        self.baselined = False
        self.ai_log: List[dict] = []
        self._last_control = 0.0
        self._last_program = 0.0
        self._last_review = 0.0
        ai_cfg = cfg.get("ai_review", {})
        self.ai_enabled = bool(ai_cfg.get("enabled", True)) and bool(api_key)
        self._api_key = api_key or ""
        self._model = ai_cfg.get("model", DEFAULT_MODEL)
        self._interval = float(ai_cfg.get("interval_s", 120.0))
        self._audit_path = ai_cfg.get("audit_log")
        self._transport = ai_transport
        self._review_lock = threading.Lock()

    # -- audio ingest --------------------------------------------------------
    def process(self, pcm, clock: float) -> None:
        if self.stereo_mode:
            self.degraded.process(pcm, clock)
            self._sync_names()
            if self.program is not None and self.degraded._loud is not None:
                self.program.note_master(
                    self.degraded._loud, self.degraded._tilt or 0.0)
            return
        self.analyzer.process(pcm, clock)
        self._sync_names()
        if self.program is not None and self.master_channels \
                and pcm.ndim == 2:
            import numpy as np
            chans = [c for c in self.master_channels if c < pcm.shape[1]]
            if chans:
                mono = pcm[:, chans].mean(axis=1)
                rms = float(np.sqrt(np.mean(mono ** 2)))
                rms_db = 20.0 * np.log10(rms + 1e-9)
                # cheap tilt proxy from the analyzer's own master stem if
                # present; otherwise level-only adaptation
                self.program.note_master(rms_db, self._master_tilt())

    def _master_tilt(self) -> float:
        snaps = self.analyzer.snapshots()
        vals = [s.presence_db for s in snaps.values()
                if s.active and s.presence_db > -85.0]
        return float(sum(vals) / len(vals)) if vals else 0.0

    def _sync_names(self) -> None:
        """Adopt channel names discovered on the MCU scribble strips."""
        for ch, name in enumerate(self.faders.names):
            if name and ch < len(self.analyzer.stems):
                stem = self.analyzer.stems[ch]
                if stem.name != name and stem.name == f"Ch {ch + 1}":
                    stem.name = name
                    stem.role = stem.role or infer_role(name)

    def vocal_activity(self) -> Optional[bool]:
        if self.stereo_mode:
            # The stereo mix is the same feed the director already
            # analyzes — no false "ground truth" from here.
            return None
        return self.analyzer.vocal_activity()

    @property
    def advisory(self) -> bool:
        return self.control_mode == "advisory" or not self.faders.available

    # -- soundcheck ------------------------------------------------------------
    def snapshot_baseline(self) -> dict:
        heard = self.faders.snapshot_baseline()
        self.reference = {}
        if self.stereo_mode:
            self.degraded.set_reference()
        else:
            snaps = self.analyzer.snapshots()
            for stem in self.analyzer.stems:
                s = snaps.get(stem.name)
                if s and s.loud_db > -85.0:
                    self.reference[stem.channel] = s.loud_db
        for ch in self.targets:
            self.targets[ch] = 0.0
            self.rails[ch].value = 0.0
        self.knobs.reset_baseline()
        self.baselined = True
        return {"faders_heard": heard,
                "stems_referenced": len(self.reference)}

    # -- fast loop ----------------------------------------------------------------
    def control_tick(self, clock: float) -> None:
        if self.frozen_all:
            return
        # Completely automatic operation: take the soundcheck snapshot
        # ourselves once the band has been audibly playing for a while
        # and nobody pressed the button.
        if (not self.baselined and self.auto_baseline_s > 0
                and self.stereo_mode
                and self.degraded.active_seconds >= self.auto_baseline_s):
            info = self.snapshot_baseline()
            log.info("auto soundcheck snapshot taken (%s)", info)
        if self.baselined and (clock - self._last_control) >= 0.5:
            self._last_control = clock
            for ch, rail in self.rails.items():
                if rail.frozen:
                    continue
                target = self.targets.get(ch, 0.0)
                if abs(target - rail.value) >= 1e-3:
                    rail.step_toward(target)
                    self.faders.set_rel_db(ch, rail.value)
            self.knobs.control_tick()  # same 0.5s cadence: ~2 ticks/s
        if self.program is not None and \
                (clock - self._last_program) >= 5.0:
            self._last_program = clock
            self.program.adapt()

    # -- controls ---------------------------------------------------------------
    def freeze_all(self, frozen: bool) -> None:
        self.frozen_all = frozen
        log.info("MIX %s", "FROZEN" if frozen else "unfrozen")

    def freeze_stem(self, channel: int, frozen: bool) -> bool:
        rail = self.rails.get(channel)
        if rail is None:
            return False
        rail.frozen = frozen
        return True

    def nudge(self, channel: int, delta: float) -> float:
        rail = self.rails.get(channel)
        if rail is None or rail.frozen or self.frozen_all:
            return 0.0
        before = self.targets.get(channel, 0.0)
        delta = max(-MAX_DELTA_PER_REVIEW, min(MAX_DELTA_PER_REVIEW, delta))
        self.targets[channel] = rail.clamp(before + delta)
        return self.targets[channel] - before

    def _channel_by_name(self, name: str) -> Optional[int]:
        for s in self.analyzer.stems:
            if s.name.lower() == name.lower():
                return s.channel
        return None

    # -- slow loop -------------------------------------------------------------
    def review_due(self, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        return (self.ai_enabled and self.baselined and not self.frozen_all
                and (now - self._last_review) >= self._interval)

    def try_claim_review(self, now: Optional[float] = None) -> bool:
        """Atomically claim the next review slot BEFORE spawning the
        review thread — a 50ms poll loop must never double-spawn while
        the previous thread is still reaching its own timestamp write."""
        now = time.time() if now is None else now
        with self._review_lock:
            if not self.review_due(now):
                return False
            self._last_review = now
            return True

    def _role_of(self, channel: int) -> str:
        for s in self.analyzer.stems:
            if s.channel == channel:
                return s.role
        return ""

    def _stereo_max_delta(self, channel: int) -> float:
        return 1.5 if self._role_of(channel) == "lead_vocal" else 1.0

    def build_report(self) -> dict:
        if self.stereo_mode:
            return {
                "analysis_mode": "stereo",
                "program": self.degraded.measurements(),
                "fader_map": {s.name: {"role": s.role,
                                       "offset_db": round(
                                           self.targets.get(s.channel, 0.0),
                                           1),
                                       "frozen": self.rails[s.channel].frozen}
                              for s in self.analyzer.stems
                              if s.name and not s.name.startswith("Ch ")},
                "program_bus": self.program.measurements()
                if self.program is not None else None,
                "plugin_knobs": self.knobs.report() or None,
            }
        snaps = self.analyzer.snapshots()
        stems = {}
        for stem in self.analyzer.stems:
            s = snaps.get(stem.name)
            if s is None:
                continue
            offset = round(self.targets.get(stem.channel, 0.0), 1)
            drift = None
            if stem.channel in self.reference and s.loud_db > -85.0:
                # post-fader listening hears our own rides; subtract them
                # so drift describes the SOURCE, not us.
                drift = round(s.loud_db - self.reference[stem.channel]
                              - offset, 1)
            stems[stem.name] = {
                "role": stem.role, "active": s.active,
                "loud_db": s.loud_db, "source_drift_db": drift,
                "fader_offset_db": offset,
                "activity_ratio": s.activity_ratio,
                "presence_db": s.presence_db, "dead": s.dead,
                "frozen": self.rails[stem.channel].frozen,
            }
        masking = self.analyzer.masking_score()
        report = {"stems": stems,
                  "vocal_masking_db": round(masking, 1)
                  if masking is not None else None}
        if self.program is not None:
            report["program_bus"] = self.program.measurements()
        if self.knobs.knobs:
            report["plugin_knobs"] = self.knobs.report()
        return report

    def review(self, now: Optional[float] = None) -> List[dict]:
        with self._review_lock:
            now = time.time() if now is None else now
            self._last_review = now
            report = self.build_report()
            try:
                transport = self._transport
                if transport is None:
                    from ..chain.ai_review import _default_transport
                    transport = _default_transport
                text = transport(self._api_key, self._model, {
                    "model": self._model, "max_tokens": 1024,
                    "system": STEREO_MIX_PROMPT if self.stereo_mode
                    else MIX_SYSTEM_PROMPT,
                    "messages": [{"role": "user",
                                  "content": json.dumps(report)}]})
            except Exception as e:
                log.warning("mix review skipped (transport failed: %s)", e)
                return []
            stem_adj, master_adj, knob_adj = self._parse(text)
            applied = []
            for adj in stem_adj:
                ch = self._channel_by_name(adj["stem"])
                if ch is None:
                    continue
                # Stereo mode: tighter, role-limited automatic rails —
                # a mix-level analysis earns smaller moves than stems do.
                limit = self._stereo_max_delta(ch) if self.stereo_mode \
                    else MAX_DELTA_PER_REVIEW
                delta = max(-limit, min(limit, adj["delta_db"]))
                if self.advisory:
                    # Recommend, don't move — the human rides the fader.
                    applied.append({"t": now, "stem": adj["stem"],
                                    "requested": adj["delta_db"],
                                    "applied": 0.0, "suggested": delta,
                                    "advisory": True,
                                    "reason": adj.get("reason", "")})
                    continue
                got = self.nudge(ch, delta)
                applied.append({"t": now, "stem": adj["stem"],
                                "requested": adj["delta_db"],
                                "applied": got,
                                "reason": adj.get("reason", "")})
            if self.program is not None:
                for adj in master_adj:
                    if adj["param"] not in MASTER_PARAMS:
                        continue
                    got = self.program.nudge(
                        adj["param"],
                        max(-MAX_DELTA_PER_REVIEW,
                            min(MAX_DELTA_PER_REVIEW, adj["delta"])))
                    applied.append({"t": now, "stem": "PROGRAM",
                                    "param": adj["param"],
                                    "requested": adj["delta"],
                                    "applied": got,
                                    "reason": adj.get("reason", "")})
            for adj in knob_adj:
                if adj["name"] not in self.knobs.knobs:
                    continue
                if self.advisory or not self.knobs.available:
                    from .knobs import MAX_TICKS_PER_REVIEW
                    sug = max(-MAX_TICKS_PER_REVIEW,
                              min(MAX_TICKS_PER_REVIEW, adj["delta_ticks"]))
                    applied.append({"t": now, "stem": adj["name"],
                                    "param": "knob",
                                    "requested": adj["delta_ticks"],
                                    "applied": 0.0, "advisory": True,
                                    "suggested": sug,
                                    "reason": adj.get("reason", "")})
                    continue
                got = self.knobs.nudge(adj["name"], adj["delta_ticks"])
                applied.append({"t": now, "stem": adj["name"],
                                "param": "knob",
                                "requested": adj["delta_ticks"],
                                "applied": got,
                                "reason": adj.get("reason", "")})
            for entry in applied:
                self.ai_log.insert(0, entry)
                self._audit(entry)
            del self.ai_log[40:]
            return applied

    @staticmethod
    def _parse(text: str) -> tuple:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return [], [], []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return [], [], []
        stems, master, knobs = [], [], []
        for adj in data.get("adjustments", []):
            if isinstance(adj, dict) and {"stem", "delta_db"} <= set(adj):
                try:
                    adj["delta_db"] = float(adj["delta_db"])
                    stems.append(adj)
                except (TypeError, ValueError):
                    pass
        for adj in data.get("master", []):
            if isinstance(adj, dict) and {"param", "delta"} <= set(adj):
                try:
                    adj["delta"] = float(adj["delta"])
                    master.append(adj)
                except (TypeError, ValueError):
                    pass
        for adj in data.get("knobs", []):
            if isinstance(adj, dict) and {"name", "delta_ticks"} <= set(adj):
                try:
                    adj["delta_ticks"] = float(adj["delta_ticks"])
                    knobs.append(adj)
                except (TypeError, ValueError):
                    pass
        return stems, master, knobs

    def _audit(self, entry: dict) -> None:
        log.info("MIX adjust: %s %+0.1f dB (%s)", entry.get("stem"),
                 entry.get("applied", 0.0), entry.get("reason", ""))
        if not self._audit_path:
            return
        try:
            with open(self._audit_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as e:
            log.warning("mix audit write failed: %s", e)

    # -- UI -----------------------------------------------------------------------
    def ui_state(self) -> dict:
        snaps = self.analyzer.snapshots()
        masking = self.degraded.masking_db() if self.stereo_mode \
            else self.analyzer.masking_score()
        stems_ui = []
        for stem in self.analyzer.stems:
            s = snaps.get(stem.name)
            if s is None:
                continue
            stems_ui.append({
                "channel": stem.channel, "name": stem.name,
                "role": stem.role, "active": s.active,
                "level_db": s.level_db, "dead": s.dead,
                "fader_db": round(self.rails[stem.channel].value, 1),
                "target_db": round(self.targets.get(stem.channel, 0.0), 1),
                "frozen": self.rails[stem.channel].frozen,
            })
        return {
            "midi_available": self.faders.available,
            "midi_error": self.faders.error,
            "daw_heard": self.faders.heard_from_daw(),
            "control_mode": "advisory" if self.advisory else "auto",
            "analysis_mode": "stereo" if self.stereo_mode else "stems",
            "baselined": self.baselined,
            "frozen_all": self.frozen_all,
            "ai_enabled": self.ai_enabled,
            "vocal_masking_db": round(masking, 1)
            if masking is not None else None,
            "program": self.program.measurements()
            if self.program is not None else None,
            "stems": stems_ui,
            "knobs": self.knobs.ui_state(),
            "ai_log": self.ai_log[:20],
        }

    def freeze_knob(self, name: str, frozen: bool) -> bool:
        return self.knobs.freeze(name, frozen)

    def close(self) -> None:
        self.faders.close()
        self.knobs.close()
