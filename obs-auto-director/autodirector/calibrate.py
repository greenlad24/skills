"""Calibration wizard (terminal): teaches the vocal detector your mix.

Live mode needs ~30 seconds of your actual material:
  1. ~10 s of the band playing WITHOUT vocals
  2. ~10 s WITH the main singer singing
  3. optional ~15 s of the main singer alone (enrolls the pitch prior)

Results (LDA weights, d', dwell multiplier, pitch range) are stored as
JSON at live.calibration_file. A weak separation (d' < 1.5) is reported
honestly and automatically stretches switcher dwell times.
"""

from __future__ import annotations

import json
import os
import time

import numpy as np

from .app import load_config
from .dsp import Calibrator, Frontend, PitchPrior, VocalPresence


def _record_phase(capture, seconds: float, label: str):
    print(f"\n>>> {label}")
    print(f"    Recording {seconds:.0f}s — press Enter to start...")
    input()
    fe = Frontend()
    det = VocalPresence()
    feats, hops = [], []
    start = capture.audio_clock
    while capture.audio_clock - start < seconds:
        pcm = capture.read()
        if pcm is None:
            time.sleep(0.02)
            continue
        for hop in fe.process(pcm):
            det.update(hop)
            f = det.features()
            if f is not None:
                feats.append(f)
            hops.append(hop)
    print("    done.")
    return feats, hops


def wizard(config_path: str) -> None:
    from .io.capture import AudioCapture

    cfg = load_config(config_path)
    lcfg = cfg["live"]
    out_path = os.path.expanduser(
        lcfg.get("calibration_file", "~/.autodirector/live_cal.json"))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    capture = AudioCapture(device=lcfg.get("device"),
                           channels=int(lcfg.get("channels", 1)))
    capture.start()
    print("AutoDirector calibration — live mode")
    print(f"Input device: {lcfg.get('device') or '(default)'}")

    cal = Calibrator()
    feats_i, _ = _record_phase(
        capture, 10, "Phase 1/3: play ~10s WITHOUT vocals (instrumental)")
    for f in feats_i:
        cal.collect(f, vocal=False)
    feats_v, _ = _record_phase(
        capture, 10, "Phase 2/3: play ~10s WITH the main singer singing")
    for f in feats_v:
        cal.collect(f, vocal=True)

    result = cal.finish()
    if result is None:
        print("Not enough material captured — check the device and retry.")
        capture.stop()
        return

    prior = None
    ans = input("\nPhase 3/3 (optional): enroll the MAIN singer's pitch "
                "range from ~15s of solo voice? [y/N] ").strip().lower()
    if ans == "y":
        _, hops = _record_phase(capture, 15,
                                "Main singer alone (talk/sing freely)")
        prior = PitchPrior.enroll([h.f0_hz for h in hops])
        if prior is None:
            print("    could not extract a stable pitch range — skipped.")
    capture.stop()

    data = {"w": [float(x) for x in result.w], "b": result.b,
            "d_prime": result.d_prime,
            "dwell_multiplier": result.dwell_multiplier,
            "f0_lo": prior.f0_lo if prior else None,
            "f0_hi": prior.f0_hi if prior else None}
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nSaved calibration to {out_path}")
    print(f"Separation quality d' = {result.d_prime:.2f}"
          + (" — GOOD" if not result.weak else
             " — WEAK: this mix is hard for the detector. Switching will"
             f" be {result.dwell_multiplier:.1f}x more deliberate. Consider"
             " re-running with more representative material."))
