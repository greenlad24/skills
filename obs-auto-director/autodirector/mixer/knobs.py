"""Param knobs: slight, railed tweaks to VST parameters INSIDE the DAW.

Mechanism: Studio One's Control Link (Cubase: Generic Remote / MIDI
Remote) maps any plugin parameter to a MIDI CC on a chosen device. We
expose a dedicated virtual port — "AutoDirector Params" — and the user
maps, once, the handful of parameters they want tweakable ("Vox Comp
Threshold" -> CC1, "Vox Reverb Send" -> CC2, ...). That mapping step is
the consent boundary: unmapped parameters cannot be touched, period.

Movement discipline (this is for *slight* tweaks, by design):
* every knob is a Rail measured in ticks of the 0-127 CC range,
  clamped to +-16 ticks (~12%) from its soundcheck position
* the AI may request at most +-6 ticks per review
* moves are slewed 1 tick per control tick (~2 ticks/second)
* per-knob freeze locks, full audit log — same rules as faders

Two CC modes per knob:
* "absolute": we send baseline_cc + offset (default baseline 64 —
  park the mapped parameter mid-travel at soundcheck)
* "relative": we send binary-offset increments (64+d) for maps
  configured as relative encoders in the DAW
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional

from ..chain.rails import Rail

log = logging.getLogger("autodirector.knobs")

MAX_TICKS_PER_REVIEW = 6
TOTAL_TICKS_CLAMP = 16


class ParamKnobs:
    def __init__(self, knobs_cfg: List[dict],
                 port_factory: Optional[Callable] = None,
                 port_name: str = "AutoDirector Params"):
        self.available = False
        self.error: Optional[str] = None
        self._port = None
        self.knobs: Dict[str, dict] = {}
        for k in knobs_cfg:
            name = k.get("name")
            if not name or "cc" not in k:
                continue
            self.knobs[name] = {
                "cc": int(k["cc"]),
                "channel": int(k.get("channel", 0)),
                "mode": k.get("mode", "absolute"),
                "baseline_cc": int(k.get("baseline_cc", 64)),
                "rail": Rail(f"knob:{name}", 0.0,
                             lo=-TOTAL_TICKS_CLAMP, hi=TOTAL_TICKS_CLAMP,
                             max_step=1.0),
                "target": 0.0,
            }
        if not self.knobs:
            return
        try:
            from .mcu import MidiPort
            factory = port_factory or MidiPort
            self._port = factory(port_name, lambda *a: None)
            self.available = True
        except Exception as e:
            self.error = str(e)
            log.warning("param-knob port unavailable (%s) — VST tweaks "
                        "disabled, everything else continues", e)

    # ------------------------------------------------------------------
    def _send_cc(self, channel: int, cc: int, value: int) -> None:
        value = max(0, min(127, int(value)))
        # A CC is a 3-byte message; reuse the port's raw sender.
        out = getattr(self._port, "_out", None)
        if out is not None:
            out.send_message([0xB0 | (channel & 0x0F), cc & 0x7F, value])
        elif hasattr(self._port, "send_cc"):  # test fakes
            self._port.send_cc(channel, cc, value)

    def nudge(self, name: str, ticks: float) -> float:
        """Bounded target move (AI path). Returns applied delta in ticks."""
        k = self.knobs.get(name)
        if k is None or not self.available or k["rail"].frozen:
            return 0.0
        ticks = max(-MAX_TICKS_PER_REVIEW,
                    min(MAX_TICKS_PER_REVIEW, float(ticks)))
        before = k["target"]
        k["target"] = k["rail"].clamp(before + ticks)
        return k["target"] - before

    def freeze(self, name: str, frozen: bool = True) -> bool:
        k = self.knobs.get(name)
        if k is None:
            return False
        k["rail"].frozen = frozen
        return True

    def control_tick(self) -> None:
        """Slew each knob one tick toward its target (~called every 0.5s)."""
        if not self.available:
            return
        for name, k in self.knobs.items():
            rail = k["rail"]
            if rail.frozen or abs(k["target"] - rail.value) < 0.5:
                continue
            step = 1.0 if k["target"] > rail.value else -1.0
            rail.value = rail.clamp(rail.value + step)
            if k["mode"] == "relative":
                self._send_cc(k["channel"], k["cc"], 64 + int(step))
            else:
                self._send_cc(k["channel"], k["cc"],
                              k["baseline_cc"] + int(round(rail.value)))

    def reset_baseline(self) -> None:
        """Soundcheck: current DAW positions become zero-offset."""
        for k in self.knobs.values():
            k["rail"].value = 0.0
            k["target"] = 0.0

    def ui_state(self) -> list:
        return [{"name": name, "offset_ticks": round(k["rail"].value, 0),
                 "target_ticks": round(k["target"], 0),
                 "frozen": k["rail"].frozen, "mode": k["mode"]}
                for name, k in self.knobs.items()]

    def report(self) -> dict:
        return {name: {"offset_ticks": round(k["rail"].value, 0),
                       "frozen": k["rail"].frozen}
                for name, k in self.knobs.items()}

    def close(self) -> None:
        if self._port is not None:
            try:
                self._port.close()
            except Exception:
                pass
