# AutoDirector v2 — Architecture Decision

Status: **adopted**. This document reconciles the agent-team engineering review
([TEAM_REVIEW_SYNTHESIS.md](TEAM_REVIEW_SYNTHESIS.md)) with product requirements
that arrived after the review launched. Where the two disagree, this document
wins; each deviation is flagged.

## The decision

**AutoDirector v2 is a standalone macOS menu-bar app (Python) that captures
audio itself and drives OBS over obs-websocket v5. The OBS Python script is
retired.**

Verified grounds (see synthesis §1):

- OBS Python scripting **cannot access raw audio samples** — the capture
  callbacks have no Python bindings, and level meters alone cannot detect
  vocals inside a mixed feed. The single-mixed-channel requirement makes this
  a wall, not a tuning problem.
- obs-websocket v5 (bundled with OBS ≥ 28, one checkbox to enable) provides
  everything the plugin glue did — scene switching, scene-change events for
  manual-cut sync, scene-list validation — **plus the source-filter APIs**
  (`CreateSourceFilter`, `SetSourceFilterSettings`, `SetSourceFilterEnabled`)
  that the adaptive voice chain needs.
- Audio capture on macOS: CoreAudio allows multiple clients on one input
  device, so the app can open the **same interface OBS uses** — no virtual
  cables for the common case. Documented fallback for in-OBS-only mixes:
  OBS Monitoring Device → BlackHole 2ch.

**Fail-safe posture (non-negotiable):** if the analyzer dies, a device
unplugs, or the websocket drops, the app does *nothing* — OBS is untouched
and the show continues under manual control. Menu-bar status dot
(green/amber/red), auto-reconnect with backoff.

## Post-review requirement reconciliation

These product updates arrived after the review launched; they modify the
synthesis as follows:

1. **Podcast mode has per-speaker audio** (each speaker's mic is a separate
   source/device; mics stay always-active so both voices are in the broadcast
   mix regardless of scene). Therefore single-channel speaker diarization
   (synthesis §2.3) is **demoted from core to optional fallback (v3)**. The
   app captures each speaker's mic device directly (CoreAudio shared access),
   which is *better* than the old volmeter approach: per-voice PCM enables
   robust VAD, spectral measurement for auto-EQ, and restores the per-mic
   emphasis push-in cue the synthesis listed as an accepted regression —
   it is no longer regressed.
2. **Live mode remains single-mixed-channel** — synthesis §2.1/§2.2 adopted
   unchanged: calibrated vocal-in-mix detection; *vocals present → main
   singer scene, always* (backing vocals never trigger cuts; optional duet →
   wide after 4 s, off by default).
3. **Relaxed switching** — synthesis §2.4 `EvidenceSwitcher` adopted
   unchanged (evidence accumulation, dwell windows, cooldown, return
   penalty, raised min-shot: live 4.0 s, podcast 3.5 s).
4. **Adaptive voice chain (new scope, not in synthesis):** per-speaker OBS
   filter chain managed over obs-websocket:
   `noise suppression → expander (adaptive threshold) → user VSTs
   (untouched) → adaptive gain/compressor → adaptive 3-band EQ → limiter`.
   Two control loops:
   - **Fast loop (local DSP, always on):** floor-tracked expander threshold
     (moves only during silence), speech-statistics-driven gain/compressor,
     spectral-tilt-driven EQ nudges — all under hard clamps and slew limits.
   - **Slow loop (AI review, periodic):** every few minutes the app packages
     per-speaker measurements (band energies, tilt vs. target curve, crest
     factor, floor character, gate chatter, clipping, loudness match) plus
     local-classifier labels into JSON; Claude API returns bounded
     adjustment deltas + rationale (structured output), applied within the
     same clamps. Requires an API key; degrades gracefully to the fast loop
     offline; every AI adjustment is logged and freezable.
5. **Local audio classifier (new scope):** YAMNet-class tagging model
   (ONNX/TFLite, ~4 MB) in the analyzer — noise identification
   (hum/fan/traffic/typing) for the chain and AI reports, and
   singing/speech/music classes **fused into live-mode vocal detection**.

## Component map

```
autodirector/
  core/       pacing, VAD, directors, EvidenceSwitcher   (pure logic, tested)
  dsp/        STFT front-end, vocal-in-mix, per-speaker voice stats
  classify/   local audio-tagging model (ONNX)
  chain/      adaptive voice chain: fast loop + AI slow loop (Claude API)
  io/         audio capture (ring buffer + watchdog), obs-websocket client
  app.py      menu bar, wiring, adapters
  calibrate.py  wizards: device pick, 10s+10s live calibration, speaker setup
```

Reused from v1: `PacingEngine`, `LiveDirector`, `PodcastDirector`, the
director test suite (36 tests), `demo.py` concept. Deleted: the OBS-script
glue (volmeters, obspython properties UI), `apply_crosstalk_gate`.

## Build order

1. Fix the 5 verified core bugs in place, with pinning tests (synthesis §3).
2. Restructure into the package; port core + tests.
3. `EvidenceSwitcher` + property tests (anti-ping-pong invariants).
4. DSP front-end + synthetic fixtures; vocal-in-mix + calibration (live).
5. Per-speaker capture + podcast adapter (per-source VAD, emphasis cue).
6. obs-websocket IO + fail-safe wiring; menu-bar app shell.
7. Adaptive chain fast loop → local classifier → AI slow loop.
8. Soak harness; packaging (PyInstaller .app, codesign/notarize, first-run
   wizard).

Deferred to v3: single-mic diarization fallback, ONNX vocal-separation for
true main/backing discrimination, 3+ speakers, mid-show auto-recalibration.
