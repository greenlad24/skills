# StageMix AI — Architecture & Research Synthesis

Four research agents investigated the control plane, the platform, and
the mixing science before a line of code was written. This document is
the synthesis; each claim traces to the agents' cited sources.

## 1. Control plane decision: direct X-Air OSC, not Mixing Station

The original plan was to control the Mixing Station app. Two agents
independently verified from the official docs that **Mixing Station's
REST/WebSocket/OSC APIs exist only in the desktop version** — the
Android app exposes no local API. (Its API is otherwise good: JSON
WebSocket, `/console/data/subscribe` with wildcard paths, metering at
client-chosen intervals — it remains a viable *optional* backend if a
laptop runs MS Desktop as a bridge.)

The M18/MR18 itself speaks the **X-Air OSC dialect on UDP 10024**
(Midas M-Air ≡ Behringer X-Air at protocol level; the official
"AIR-Series OSC Documentation" ships under both brands):

- Set send: `/ch/NN/mix/MM/level` (float 0–1, Maillot's piecewise
  fader law maps to dB; anchors: 0.75→0 dB, 0.5→−10, 0.25→−30).
- `/xremote` / `/xremotenfb` registers for change notifications
  (~10 s timeout → renew every 5 s; `nfb` = don't echo our own writes).
- Meters: `/meters ,s /meters/1` → ~20 Hz blobs; **X-Air blob format
  is little-endian int32 count + int16 values, dB × 256** (not the
  X32's float32 — a documented cross-client bug source).
- `/meters/1` carries the 16 input channels (pre) — our sensing bank.
- Multi-client is the protocol's normal mode: every registered client
  receives every change, which is exactly how Mixing Station, M AIR,
  and StageMix coexist and stay in sync. The famous "4 clients" limit
  is only the internal Wi-Fi AP radio; use a proper router.
- Discovery: broadcast `/xinfo` → mixer replies [IP, name, model, fw].

## 2. Platform: native Kotlin + Jetpack Compose

- PWAs cannot open UDP sockets at all; React Native's UDP libs are
  thinly maintained; Flutter's OSC package is dead (~5 years). Every
  hard requirement here — DatagramSocket, foreground service
  (`connectedDevice` type), `PARTIAL_WAKE_LOCK`,
  `WIFI_MODE_FULL_LOW_LATENCY`, keep-screen-on — is a first-class
  Android API.
- minSdk 29 (Android 10): unlocks the low-latency Wi-Fi mode and drops
  only pre-2019 devices. targetSdk 35.
- OSC is hand-rolled (~150 lines, fully unit-tested): the dialect uses
  only i/f/s/b types, no bundles, and needs a custom meter-blob decoder
  anyway.
- Show reliability: screen on + charger connected sidesteps Doze
  entirely; foreground service + wake/Wi-Fi locks cover the rest; the
  in-app checklist covers Samsung's "sleeping apps" killer.
- The engine is a **pure-JVM Kotlin module** (`:engine`) with scenario
  tests, runnable without the Android SDK — same testing philosophy as
  AutoDirector's Python core.

## 3. The mixing science: why this engine is corrective, not creative

- Dugan gain sharing — the canonical "automixer" — is a **speech**
  technology protecting gain-before-feedback with intermittent,
  one-at-a-time sources. On a band (continuous, simultaneous, bleed
  everywhere) it produces nonsense; industry sources say so plainly.
- The validated approach for music (QMUL intelligent-music-production
  line: Perez-Gonzalez & Reiss 2009; Mansbridge, Finn & Reiss 2012) is
  **target-loudness balancing with an activity gate and smoothing** —
  drive levels toward a reference balance, only while channels are
  active, slowly.
- Our reference balance is not a model's opinion — it's the
  **soundcheck snapshot** the engineer approved. The engine is a
  stagehand that puts things back where they were left.
- Feedback physics dictates the asymmetry: every automated dB of boost
  spends a dB of ring-out margin (standard practice keeps ~6 dB); open
  paths compound (+3 dB loop gain per doubling — NOM rule); and howl
  looks like *signal* on a level meter, so a naive corrector would
  reward it. Hence: boost cap +3 dB, creeping boost rate, per-bus
  upward budget, cut-only vocal priority, and freeze-on-anomaly, with
  an external watchdog input that can veto all upward motion.
- Meters at 20 Hz can detect activity, dead channels, and slow drift;
  they **cannot** detect feedback pitch or masking. Those need the
  RTA (`/meters/4`, 100 bins) or the tablet mic — both wired into the
  roadmap as the watchdog's sensors, feeding the veto that already
  exists in the engine.
- The M18's own Dugan-style automix (`/ch/NN/automix/group|weight`,
  X/Y groups) is the right tool for **talk mics between songs**; the
  app can orchestrate it rather than reimplementing gain sharing.

## 4. Fail-safe posture

Identical philosophy to AutoDirector: the mixer holds the last human
mix if the app dies — StageMix keeps nothing open, sends only bounded
absolute values derived from the snapshot, and freezes itself the
moment its senses (meters) go stale. The operator can always out-run
the machine: FREEZE ALL, per-channel locks, one-tap revert.

## 5. Module map

```
stagemix/
  engine/                  pure JVM — no Android imports
    Osc.kt                 OSC 1.0 codec (i/f/s/b, tested)
    FaderLaw.kt            float<->dB piecewise law
    Meters.kt              X-Air meter blob decoder (LE int16 /256)
    StageEngine.kt         snapshot-anchored corrective engine + rails
    src/test/…             22 scenario/codec tests
  app/                     Android (Compose, minSdk 29)
    MixerService.kt        FGS: UDP socket, keep-alives, engine loop
    AppState.kt            StateFlows shared service <-> UI, config prefs
    MainActivity.kt / ui/  console UI: strips, VU, locks, engine log
  keystore/                convenience signing key (see README)
```
