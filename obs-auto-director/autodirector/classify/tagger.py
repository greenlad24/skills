"""Local audio-tagging classifier (YAMNet-class) — the always-on ears.

Contributes three things (docs/ARCHITECTURE.md §5):
- singing / speech / music scores fused into live-mode vocal detection
- background-noise identification (hum, fan, traffic, typing, ...) for the
  adaptive voice chain and the AI review reports
- named evidence for the AI reviewer instead of raw spectra

The model is an ONNX export of YAMNet (AudioSet, 521 classes, ~4 MB) run
via onnxruntime at 16 kHz. Both the runtime and the model file are
OPTIONAL: without them the tagger reports itself disabled and every
consumer degrades gracefully (pure-DSP behavior). Fetch the model with
scripts/fetch_models.sh.
"""

from __future__ import annotations

import csv
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

log = logging.getLogger("autodirector.classify")

MODEL_SR = 16000
WINDOW_S = 0.975          # YAMNet's native window
GROUPS = {
    "singing": ["Singing", "Female singing", "Male singing", "Child singing",
                "Choir", "Yodeling", "Chant", "Rapping", "Humming"],
    "speech": ["Speech", "Conversation", "Narration, monologue",
               "Speech synthesizer", "Child speech, kid speaking"],
    "music": ["Music", "Musical instrument", "Guitar", "Drum", "Drum kit",
              "Piano", "Bass guitar", "Electric guitar", "Synthesizer",
              "Violin, fiddle", "Trumpet", "Saxophone"],
    "noise_hum": ["Hum", "Mains hum", "Buzz"],
    "noise_fan": ["Fan", "Air conditioning", "Mechanical fan"],
    "noise_traffic": ["Traffic noise, roadway noise", "Vehicle", "Car",
                      "Truck", "Motorcycle", "Siren"],
    "noise_typing": ["Typing", "Computer keyboard", "Mouse click"],
    "noise_crowd": ["Crowd", "Applause", "Cheering", "Chatter"],
}


@dataclass
class TagScores:
    t: float
    groups: Dict[str, float] = field(default_factory=dict)

    def top_noise(self) -> Optional[str]:
        noise = {k: v for k, v in self.groups.items()
                 if k.startswith("noise_") and v > 0.2}
        if not noise:
            return None
        return max(noise, key=noise.get)


class AudioTagger:
    """Streaming wrapper: feed 48 kHz PCM, get grouped scores ~1x/second.

    Disabled (self.enabled == False) when onnxruntime or the model file is
    missing — update() then always returns None and fusion is skipped.
    """

    def __init__(self, model_path: Optional[str] = None,
                 class_map_path: Optional[str] = None):
        self.enabled = False
        self._session = None
        self._class_names: List[str] = []
        self._group_idx: Dict[str, List[int]] = {}
        self._buf = np.zeros(0, dtype=np.float32)
        self._t = 0.0
        model_path = model_path or os.environ.get("AUTODIRECTOR_YAMNET", "")
        class_map_path = class_map_path or os.environ.get(
            "AUTODIRECTOR_YAMNET_CLASSMAP", "")
        if model_path and os.path.exists(model_path):
            try:
                import onnxruntime  # type: ignore
                self._session = onnxruntime.InferenceSession(
                    model_path, providers=["CPUExecutionProvider"])
                self._load_class_map(class_map_path)
                self.enabled = True
                log.info("audio tagger enabled (%s)", model_path)
            except Exception as e:  # pragma: no cover - env specific
                log.warning("audio tagger disabled: %s", e)

    def _load_class_map(self, path: str) -> None:
        if path and os.path.exists(path):
            with open(path, newline="") as f:
                rows = list(csv.reader(f))
            # AudioSet class map CSV: index, mid, display_name
            self._class_names = [r[2] for r in rows[1:]]
        if self._class_names:
            lower = [c.lower() for c in self._class_names]
            for group, names in GROUPS.items():
                idx = [lower.index(n.lower()) for n in names
                       if n.lower() in lower]
                self._group_idx[group] = idx

    # ------------------------------------------------------------------
    @staticmethod
    def _resample_to_16k(pcm48: np.ndarray) -> np.ndarray:
        # 48k -> 16k is an exact 3:1 decimation; box-filter then take
        # every 3rd sample (adequate anti-aliasing for classification).
        n = len(pcm48) - (len(pcm48) % 3)
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        x = pcm48[:n].reshape(-1, 3).mean(axis=1)
        return x.astype(np.float32)

    def update(self, pcm48: np.ndarray, t: float) -> Optional[TagScores]:
        """Feed 48 kHz mono PCM; returns TagScores when a window completes."""
        if not self.enabled:
            return None
        if pcm48.ndim == 2:
            pcm48 = pcm48.mean(axis=1)
        self._buf = np.concatenate([self._buf,
                                    self._resample_to_16k(pcm48)])
        need = int(WINDOW_S * MODEL_SR)
        if len(self._buf) < need:
            return None
        window, self._buf = self._buf[:need], self._buf[need:]
        try:
            scores = self._infer(window)
        except Exception as e:  # pragma: no cover - runtime specific
            log.warning("tagger inference failed, disabling: %s", e)
            self.enabled = False
            return None
        groups = {}
        for group, idx in self._group_idx.items():
            groups[group] = float(np.max(scores[idx])) if idx else 0.0
        return TagScores(t=t, groups=groups)

    def _infer(self, window: np.ndarray) -> np.ndarray:
        inp = self._session.get_inputs()[0]
        out = self._session.run(None, {inp.name: window})
        scores = np.asarray(out[0])
        if scores.ndim == 2:  # (frames, classes) -> mean over frames
            scores = scores.mean(axis=0)
        return scores


def fuse_vocal_confidence(dsp_conf: float,
                          tags: Optional[TagScores]) -> float:
    """Blend the DSP vocal confidence with classifier singing evidence.

    With no classifier available this is the identity. With one, the
    classifier contributes 30% — enough to rescue borderline DSP calls,
    never enough to overrule strong DSP evidence on its own.
    """
    if tags is None:
        return dsp_conf
    singing = tags.groups.get("singing", 0.0)
    speech = tags.groups.get("speech", 0.0)
    classifier_vote = max(singing, 0.6 * speech)
    return float(np.clip(0.7 * dsp_conf + 0.3 * classifier_vote, 0.0, 1.0))
