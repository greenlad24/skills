"""AI engineer review — the slow judgment loop over the adaptive chain.

Every few minutes the app packages what an engineer would read off their
meters (per-speaker Snapshots, current rail values, classifier noise
labels) into JSON and asks Claude to review it as a broadcast audio
engineer. The model returns bounded adjustment deltas with rationale;
they are applied through the same Rails as the fast loop — the AI
recommends, the rails decide what is allowed to move.

Degrades gracefully: no API key / no network -> the fast loop continues
alone. Every applied adjustment is appended to an audit log (JSONL) so
the operator can see exactly what was done to their sound and freeze any
parameter they disagree with.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict
from typing import Callable, Dict, List, Optional

log = logging.getLogger("autodirector.ai")

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
ALLOWED_PARAMS = ("expander_threshold", "gain_db", "comp_threshold",
                  "eq_low", "eq_high")
MAX_DELTA = 3.0  # dB per review, before the rails clamp further

SYSTEM_PROMPT = """You are a broadcast audio engineer reviewing live meter
measurements for a podcast. For each speaker you get: room noise floor,
speech level and peaks (dB FS), spectral tilt (high minus low band, dB;
around -14 is a natural voice), crest factor, expander-gate chatter rate,
clipping events, current processing values, and background-noise labels
from an audio classifier.

Respond with ONLY a JSON object:
{"adjustments": [{"speaker": str, "param": str, "delta": float,
                  "reason": str}, ...], "notes": str}
Allowed params: expander_threshold, gain_db, comp_threshold, eq_low,
eq_high. Deltas are in dB, max ±3 per review. Recommend nothing when the
sound is fine — an empty adjustments list is a good answer. Prioritize:
gate chatter (raise expander_threshold), loudness mismatch between
speakers (gain_db), clipping (gain_db down), tonal imbalance (eq_*)."""


def _default_transport(api_key: str, model: str, payload: dict,
                       timeout: float = 30.0) -> str:
    import urllib.request
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json",
                 "x-api-key": api_key,
                 "anthropic-version": "2023-06-01"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    return "".join(b.get("text", "") for b in data.get("content", []))


class AIReviewer:
    """Periodic Claude review of the voice chains.

    `transport(api_key, model, payload) -> response text` is injectable
    for tests; the default uses urllib against the Anthropic API.
    """

    def __init__(self, api_key: str, chains: Dict[str, object],
                 model: str = DEFAULT_MODEL,
                 interval_s: float = 180.0,
                 audit_path: Optional[str] = None,
                 transport: Optional[Callable] = None):
        self.api_key = api_key
        self.chains = chains          # speaker name -> VoiceChain
        self.model = model
        self.interval_s = interval_s
        self.audit_path = audit_path
        self.transport = transport or _default_transport
        self._last_review_t = 0.0

    # ------------------------------------------------------------------
    def due(self, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        return bool(self.api_key) and \
            (now - self._last_review_t) >= self.interval_s

    def claim(self, now: Optional[float] = None) -> bool:
        """Atomically claim the next review slot before spawning a
        thread, so a fast poll loop cannot double-spawn reviews."""
        now = time.time() if now is None else now
        if not self.due(now):
            return False
        self._last_review_t = now
        return True

    def build_report(self, snapshots: Dict[str, object],
                     noise_labels: Optional[Dict[str, float]] = None) -> dict:
        speakers = {}
        for name, snap in snapshots.items():
            chain = self.chains.get(name)
            speakers[name] = {
                "measurements": asdict(snap) if hasattr(snap, "__dataclass_fields__") else dict(snap),
                "current_settings": {p: r.value for p, r in
                                     chain.rails.items()} if chain else {},
                "frozen_params": [p for p, r in chain.rails.items()
                                  if r.frozen] if chain else [],
            }
        return {"speakers": speakers,
                "background_noise": noise_labels or {}}

    # ------------------------------------------------------------------
    def review(self, snapshots: Dict[str, object],
               noise_labels: Optional[Dict[str, float]] = None,
               now: Optional[float] = None) -> List[dict]:
        """Run one review; returns the list of APPLIED adjustments."""
        now = time.time() if now is None else now
        self._last_review_t = now
        report = self.build_report(snapshots, noise_labels)
        try:
            text = self.transport(self.api_key, self.model, {
                "model": self.model,
                "max_tokens": 1024,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user",
                              "content": json.dumps(report)}],
            })
        except Exception as e:
            log.warning("AI review skipped (transport failed: %s)", e)
            return []
        adjustments = self._parse(text)
        applied = []
        for adj in adjustments:
            chain = self.chains.get(adj["speaker"])
            if chain is None or adj["param"] not in ALLOWED_PARAMS:
                continue
            delta = max(-MAX_DELTA, min(MAX_DELTA, float(adj["delta"])))
            got = chain.nudge(adj["param"], delta)
            entry = {"t": now, "speaker": adj["speaker"],
                     "param": adj["param"], "requested": adj["delta"],
                     "applied": got, "reason": adj.get("reason", "")}
            applied.append(entry)
            self._audit(entry)
        return applied

    @staticmethod
    def _parse(text: str) -> List[dict]:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
        out = []
        for adj in data.get("adjustments", []):
            if not isinstance(adj, dict):
                continue
            if {"speaker", "param", "delta"} <= set(adj):
                try:
                    adj["delta"] = float(adj["delta"])
                except (TypeError, ValueError):
                    continue
                out.append(adj)
        return out

    def _audit(self, entry: dict) -> None:
        log.info("AI adjust: %(speaker)s %(param)s %(applied)+.1f dB "
                 "(%(reason)s)", entry)
        if not self.audit_path:
            return
        try:
            with open(self.audit_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as e:
            log.warning("audit log write failed: %s", e)
