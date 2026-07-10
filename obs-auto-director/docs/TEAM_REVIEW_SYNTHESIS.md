# OBS AutoDirector v2 — Final Engineering Plan

Synthesized from: OBS API research (verified), architecture critique, DSP design, verified code findings, and test strategy. All platform facts below were independently verified against primary sources (obs-studio source, obs-websocket protocol.md, BlackHole docs); where reports disagreed, the resolution is stated inline.

---

## 1. ARCHITECTURE DECISION

**Winner: Option C — a standalone macOS menu-bar app (Python) that captures the mixed PCM feed via `sounddevice`, runs the DSP/directing pipeline in its own process, and drives OBS over obs-websocket v5. The obspython script is retired.**

Grounds (all verified):

- **obspython cannot get PCM. Ever.** `obs_source_add_audio_capture_callback` / `obs_add_raw_audio_callback` have no hand-written SWIG wrappers in `obs-scripting-python.c`; the only ctypes workaround yields volmeter levels, not samples. A dB scalar from one mixed channel cannot distinguish vocals from a guitar solo or Anna from Ben. Option A (pure script) fails the gating requirement — not a tuning problem, a wall.
- **obs-websocket v5 gives us everything the glue layer did** — `SetCurrentProgramScene`, `CurrentProgramSceneChanged` (for manual-cut sync), `GetSceneList` (scene-name validation) — bundled with every OBS ≥ 28, enabled with one checkbox + password.
- **Audio in:** prefer opening **the same CoreAudio input device OBS uses** (CoreAudio allows shared input clients — zero extra install for the common band-mixer/interface case). Documented fallback for in-OBS-only mixes: OBS Monitoring Device → **BlackHole 2ch** (signed, notarized .pkg). Both paths verified.

Explicit conflict resolutions:

- **Overruled: DSP designer's suggestion to keep the OBS script "as a thin fallback."** The architecture critique's Option-B analysis is decisive: a script shell that only calls `obs_frontend_set_current_scene` preserves the project's worst install burden (OBS↔Python framework dance) and adds a silent-stale-IPC failure mode, to duplicate what the websocket does in one line. One codebase, one process. The script gets a deprecation note, nothing more.
- **Overruled: architecture critique's separately named `ConfidenceGate`.** It is the same component as the DSP designer's fully specified `EvidenceSwitcher`; we adopt the latter (name, spec, and constants — §2.4).
- **Adjusted: dependency list.** Drop `scipy` from the DSP designer's list until a concrete need appears — every specified operation (STFT, mel, YIN-lite, diagonal Gaussians) is plain numpy. Ship: `numpy`, `sounddevice`, `obsws-python`.
- **Deferred, not chosen: native C++ plugin (D1).** It is the escape hatch if Python real-time behavior or install size ever becomes the bottleneck; it forfeits the tested Python core today for no requirement we have.

**Fail-safe posture (non-negotiable):** if the analyzer dies, the device unplugs, or the websocket drops — the app does *nothing*. OBS is untouched; the show continues under manual control. Menu-bar status dot (green/amber/red), auto-reconnect with backoff.

---

## 2. V2 FEATURE DESIGN

Adopt the DSP designer's proposal in full, with the adjustments noted. The verified platform facts confirm its prerequisite (sidecar PCM capture) exactly.

### 2.0 Common DSP front-end
48 kHz mono downmix; Hann STFT **N=2048, hop=512** (~94 fps); per hop: magnitude spectrum, 40-band log-mel, RMS dB, spectral flux, centroid, band energies (LF <200 Hz, vocal 200–4000, presence 2–5 k, HF >6 k); **YIN-lite** F0 (70–1000 Hz) on 40 ms frames. Pure numpy, <5% of one core. All analyzers emit **confidences in [0,1]**; booleans are minted only by the `EvidenceSwitcher`. Director time `t` comes from the **audio stream clock**, not `time.monotonic()`.

### 2.1 Vocal-in-mix detection (live mode)
Calibrated diagonal-LDA over 5–8 features (pitch salience 100–800 Hz, F0 continuity + vibrato 4–8 Hz / 20–120 cents, syllabic envelope modulation 2–8 Hz on the 200–4000 Hz band, presence-band flux 1–4 kHz, harmonic-to-residual ratio), learned from a **10 s instrumental + 10 s vocal calibration wizard** exactly as specified (w, b, scale from class centroids; sigmoid + user bias; EMA τ=0.25 s). **d′ < 1.5 ⇒ warn user and auto-multiply switcher dwells up to 1.5×.** Expected phrase-level accuracy 90–95% on typical mixes, honestly degraded (~70–80%) on screamed vocals / vocal-range solos — the switcher's dwell + hold-current-shot bias makes those misses read as directing choices. Four UI knobs only: sensitivity bias, vocals-in dwell, vocals-out dwell, Recalibrate.

### 2.2 Main vs. backing vocals
**Adopt the policy, not the classifier: vocals present → main-singer scene, always.** Robust per-voice separation on one mixed channel is infeasible without an ML separation stack — we do not promise it. Enrolled main-singer pitch prior (15 s solo at calibration) **modulates confidence only, never vetoes and never triggers a cut to anyone else.** Two-concurrent-salient-F0 flag optionally enables a duet→**wide/duo scene** cut after >4 s (off by default). Backing-only sections landing on the singer scene is a documented aesthetic miss, revisited in v3 with an optional ONNX separation model.

### 2.3 Podcast speaker attribution (2 speakers, one mix)
15 s enrollment per speaker → diagonal-Gaussian model over `[log F0, 12 mel-cepstra, centroid, tilt]`; runtime Mahalanobis → tempered softmax (T=2.0) → 1.0 s ring buffer, ≥0.4 s speech to attribute, **0.7 s contrary-evidence hangover**. Overlap detection (poor fit to both / multi-F0 / pinned posterior) ⇒ **freeze attribution, holder keeps floor**; sustained overlap then clean flip = interruption (matches existing director semantics). `max(P) < 0.65 for > 2.5 s` ⇒ `UNKNOWN` ⇒ hold shot or cut wide. Surface a confusability warning at enrollment. Adapter feeds the existing `PodcastDirector.update(t, talking, levels)`; **`apply_crosstalk_gate` is deleted** (meaningless on one channel).

### 2.4 `EvidenceSwitcher` (requirement 3)
Adopt the pseudocode and constants table verbatim: EMA τ 0.25 s; enter/exit **0.65/0.40**; dwells — vocals-in **0.5 s**, vocals-out **2.5 s**, speaker change **0.8 s**, →wide 1.0 s; cooldown **3.0 s**; priority override ≥0.85 conf sustained ≥1.5 s; return penalty **1.5× within 20 s**; confidence-weighted min-shot extension `min(1 + (1−commit_conf), 2)`; calibration-aware dwell multiplier ≤1.5×. **Raise `min_shot_s`: live 3.0→4.0, podcast 2.6→3.5.** Directors stay untouched; only adapters and two defaults change.

---

## 3. CONFIRMED BUGS (all six independently verified; fixes are the verifier-corrected versions — the reviewer's original fixes were wrong or incomplete in three cases)

**Fix now — these classes ship in v2:**

1. **`LevelVAD` floor collapse on −inf/muted input latches `active` forever** (lines 110–132). Fix (corrected): treat `level_db <= NEG_INF_DB + 1.0` as no-signal — skip floor adaptation *and* hot evaluation; add a slow bounded upward floor drift even while hot so a poisoned floor recovers. **Overruled: the reviewer's `max(floor_db, −75)` clamp** — verifier proved a −75 floor still latches on −55 dB room tone; it's a supplement at best. (LevelVAD survives in v2 as the speech-VAD gate and a classifier feature, so this fix is not optional.)

2. **`PacingEngine.sync()` doesn't reset `last_cut_t`; directors stomp manual cuts within 50 ms** (lines 76–89, 261, 479). Fix (corrected — `sync` currently has no time param): change to `sync(self, t, scene)`; on external scene change set `last_cut_t = t` **and** `external_hold_until = t + override_hold_s`, with `request()` rejecting non-priority cuts during the hold; `LiveDirector._update_instrumental` pushes `_next_rotate_t` forward on external cuts. In v2 the observed scene comes from `CurrentProgramSceneChanged`.

3. **Duration-by-timestamp logic breaks across tick gaps / pause-resume — fused backchannels cause spurious priority floor steals** (`PodcastDirector.update` 367–417). Fix (corrected trace applies): on `raw_dt > 0.5 s`, treat as discontinuity — clamp `_dt` to ≤0.25 s, reset `utter_start = t` for still-talking speakers, floor `holder_silent` at 0; add `LevelVAD.resync(t)`; clear `_last_t` on resume. dt-scale the EMA coefficients (`alpha = 1 − exp(−dt/τ)`) as low-priority hardening.

4. **`utter_start` reset on any single off-tick makes `interrupt_commit_s` unreachable on real fluctuating levels** (crosstalk gate + bookkeeping 373–379). The gate itself dies in v2, but the bookkeeping bug remains lethal with noisy diarization output. Fix: debounce — only reset `utter_start` after ≥0.3 s of non-talking. (The `EvidenceSwitcher`'s leaky integrator provides the same protection upstream; fix both — defense in depth.)

5. **Holder never relinquished + "micro-pause" close-up clause satisfied by dead air — push-in on a silent speaker** (453–471). Fix: gate escalation on recent activity (`t − st.last_talk_t < ~2 s`) or track floor-hold as accumulated talking time; after prolonged silence (>5 s) park the holder and cut wide if configured.

**Fix by deletion — glue-layer bugs, mooted by v2 (no v1.1 maintenance release will be shipped; README gets a deprecation note):**

6. **`script_update` full rebuild wipes all state per slider notch**, and **`_Meter` never re-attaches after source delete/re-add** (frozen hot level latches the VAD). Both confirmed, both live entirely below the OBS GLUE marker, which v2 deletes. Note the verifier's correction for the record: the *rename* half of the `_Meter` finding was wrong (volmeters follow the source object, not the name); only delete/re-add reproduces. The v2 equivalents are designed in from the start: config changes mutate tunables in place, and capture-device liveness is watchdogged (no callback in 0.5 s ⇒ level decays to −∞ ⇒ amber status, cuts freeze).

---

## 4. TEST PLAN (adopted from the test strategy, three overrules)

**Layered boundaries:** synthetic-WAV fixtures with ground-truth JSON test the DSP layer; scripted feature streams (`tests/fixtures/shows/*.jsonl`) test switcher+directors; WAV-replay end-to-end for regression. Fixture generator (`tests/fixtures/gen_fixtures.py`) as specified: instrumental-with-guitar-solo, verse-vocals, lead-plus-backing, duet-swap, two-voice podcast, noisy-room — deterministic, generated at session start.

**Property tests (Hypothesis), adopted with one amendment:**
- P1 (min-shot except priority), P3 (≤10 cuts per sliding 60 s under *any* input), P4 (scenes ⊆ configured, no self-recut), P5 (crash fuzz incl. NaN), P6 (dt-invariance 20/50/100 ms within ±0.2 s) — adopted verbatim.
- **P2 amended — overruling the test strategist's absolute version:** "no A→B→A within 8 s *including priority*" is wrong as an invariant — a singer genuinely resuming 4 s into an instrumental break *must* get a priority cut back; that's correct directing, not flicker. Amended P2: no A→B→A within 8 s via non-priority cuts; priority returns must have met the priority bar (conf ≥0.85 sustained ≥1.5 s). The flap-attack test (P3) still bounds worst-case rate.

**Overruled: test #6 (`test_retarget_requires_sustained_dominance`, duet_swap → re-target to backing singer).** V2's design (§2.2) never retargets to a backing voice — there is no backing-singer scene. Repurposed: `duet_swap.wav` must produce **zero** cuts off the main singer by default, and at most one cut to the duo/wide scene when that option is enabled.

**Overruled: the `fake_obspython.py` glue-test investment.** The glue is deleted; that effort moves to (a) a fake obs-websocket server fixture (assert `SetCurrentProgramScene` calls, exercise disconnect/reconnect/scene-validation), and (b) capture-path tests feeding WAVs through the real ring buffer + front-end.

**Adopted as-is:** soak/regression harness (`metrics.py`: cuts/min bands, flicker score = 0, coverage ≥90%, zero non-priority sub-min-shot cuts; 30–60 min shows starting at t=1e6), dt-robustness tests (which pin bug fixes #3), VAD-pathology tests (pin fix #1 — the existing `test_handles_neg_inf_and_nan` is known-insufficient), config-extremes tests, main-singer-lock tests #4–5, mixed-VAD tests #7–8 (guitar-solo false-positive <2%). Priority order: P1–P3 + config extremes first (they fail against today's `PacingEngine` and drive the switcher), then mixed-VAD, then soak.

---

## 5. IMPLEMENTATION PLAN

### File layout (new package; current single file dissolves into it)

```
autodirector/
  core/pacing.py      PacingEngine, Cut          — PORTED + fix #2
  core/vad.py         LevelVAD                    — PORTED + fix #1 (demoted to feature/gate)
  core/live.py        LiveDirector, LiveConfig    — PORTED verbatim (+ rotate-timer part of fix #2)
  core/podcast.py     PodcastDirector, PodcastConfig — PORTED + fixes #3, #4, #5; crosstalk gate DELETED
  core/switcher.py    EvidenceSwitcher            — NEW (§2.4)
  dsp/frontend.py     STFT/mel/flux/YIN, ring buffer — NEW
  dsp/vocal.py        VocalPresence + LDA calibration — NEW
  dsp/diarize.py      enrollment, attribution, overlap — NEW
  io/capture.py       sounddevice callback → lock-free ring buffer, liveness watchdog — NEW
  io/obsws.py         obsws-python wrapper: reconnect, scene validation, program-scene events — NEW
  app.py              wiring, adapters (conf → switcher → director → obsws), menu bar — NEW
  calibrate.py        wizards: device pick + clap test, 10s+10s vocal, 15s enrollment — NEW
demo.py               extended: replays WAVs through the real DSP chain
tests/                current 36 tests ported + plan §4
```

**Reused:** `PacingEngine`, `Cut`, `LiveDirector`+config, `PodcastDirector`+config (interfaces `update(t, vocal_active, energy_db)` / `update(t, talking, levels)` are already source-agnostic), all 36 director/pacing tests, `demo.py` skeleton. **Rewritten:** sensing (volmeter → PCM DSP), control (frontend API → websocket). **Deleted:** all ~400 lines below the OBS GLUE marker, `apply_crosstalk_gate`, the stdlib-only install docs.

### Ordered steps

1. **Fix core bugs #1–#5 in place with pinning tests** (VAD pathology, sync/manual-override, dt-gap, debounce, silent-close-up). Do this first so the port carries clean code and the old suite proves no behavior regressed.
2. **Restructure into the package**; port core + tests; keep `demo.py` green.
3. **`EvidenceSwitcher`** + Hypothesis properties P1–P6 (amended P2) + config-extremes tests. This alone delivers requirement 3 and gates everything downstream.
4. **DSP front-end + fixture generator + mixed-VAD tests** (#7–8 must pass on synthetic fixtures before touching real audio).
5. **`VocalPresence` + calibration + live adapter**; main-singer-lock tests #4–6 (as amended).
6. **Podcast diarization + enrollment + podcast adapter**; overlap-freeze and UNKNOWN→wide tests.
7. **IO layer**: capture (shared-input-device first, BlackHole fallback documented) and obsws (fake-server tests, fail-safe-on-disconnect); wire `CurrentProgramSceneChanged` → `pace.sync(t, scene)`.
8. **Soak/regression harness** + multi-hour WAV replays on the exact production pipeline; CI baselines.
9. **Packaging**: PyInstaller menu-bar .app, codesign + notarize in CI from day one, `NSMicrophoneUsageDescription`, arm64+Intel, clean-VM smoke test per release; first-run wizard (device dropdown, live meter, clap test, refuse-to-arm-without-signal, websocket pairing with screenshots).

### Explicitly deferred (v3+)
True main/backing discrimination via optional ONNX vocal-separation model; duet/harmony scene automation beyond the single wide-cut option; overlap-robust diarization and 3+ speakers; mid-show auto-recalibration drift tracking; per-mic emphasis push-in reconstruction (accepted regression — close-ups still trigger on floor-hold time); optional Silero-class VAD upgrade bundled in-app; native plugin (D1) only if Python real-time behavior ever fails the soak tests.

**Accepted regressions, stated honestly:** vocals-in latency ~0.25 s → ~0.8–1.0 s (the price of one channel; a cut 1 s into a phrase still reads correctly); backing-only sections hold the singer scene; per-mic emphasis cue lost.