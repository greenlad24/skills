# StageMix AI 🎚️

An **on-stage auto mix engineer** for the Midas M18 / MR18 (and the
Behringer X-Air family), running on an Android tablet — right next to
Mixing Station.

It watches the mixer's own channel meters and, when the balance drifts
from your soundcheck (the guitarist turns up, the singer fatigues), it
nudges the **monitor sends** back toward the mix you approved — slowly,
within hard feedback-safe limits, with every move logged and reversible.

## Why it talks to the mixer directly (not to Mixing Station)

Mixing Station's control APIs exist **only in its desktop version** —
the Android app exposes nothing another app can call (verified from the
official docs). So StageMix speaks the mixer's native X-Air OSC protocol
over UDP port 10024, the same protocol Mixing Station itself uses. Both
apps are just clients of the M18: move a fader in Mixing Station and
StageMix sees it; StageMix nudges a send and Mixing Station's screen
follows. Nothing is ever in anyone's way.

## What it automates — and what it never touches

| Automated (bounded) | Never touched |
|---|---|
| Bus send levels (monitor wedges) | Main LR mix |
| Idle-channel easing (−6 dB after 60 s silence, restore on return) | Preamp/headamp gain |
| Vocal-priority ducking (cuts the band in the singer's wedge) | EQ, dynamics, FX |
| | Anything not in your soundcheck snapshot |

The rails, from live-sound research (see `docs/ARCHITECTURE.md`):

- **Soundcheck snapshot is the constitution** — corrections only move
  *toward* it, never away.
- Clamp: **snapshot −9 dB … +3 dB** per send (stays inside a standard
  6 dB ring-out margin even with two paths rising).
- Boosts **creep** (1 dB per 3 s, max 3 dB total upward per wedge);
  cuts act fast (3 dB/s). Vocal priority is **cut-only**.
- ±2 dB deadband — musical dynamics are not drift.
- Automatic freeze on: input near clip, meter dropout, sudden broadband
  change (song start/stop), operator FREEZE, watchdog veto.
- One-tap **Revert to soundcheck**. Per-channel locks.

## Show flow

1. Tablet on the mixer's network (wired-router Wi-Fi beats the M18's
   internal 2.4 GHz AP — standard advice for any X-Air rig).
2. Ring out the wedges as usual, build the mixes in Mixing Station.
3. StageMix → Connect → **Soundcheck snapshot** (it reads the current
   send levels off the console as the reference).
4. Flip **MIXING** on. Watch the engine log; freeze anything you'd
   rather own.

## Building

- `./gradlew :engine:test` — the whole mix engine is a pure-JVM Kotlin
  module with scenario tests (no Android SDK needed).
- `./gradlew :app:assembleRelease` — needs the Android SDK; CI does this
  on every push and attaches **StageMix.apk** to the `stagemix-latest`
  release.

### Signing note

The APK is signed with the checked-in convenience keystore
(`keystore/stagemix.keystore`) so that every build installs as an update
over the previous one. That's fine for sideloading onto your own
tablets. If you ever distribute more widely, generate a private
keystore and point the build at it with `STAGEMIX_KEYSTORE`,
`STAGEMIX_KS_PASS`, `STAGEMIX_KEY_ALIAS`, `STAGEMIX_KEY_PASS`
(e.g. from GitHub secrets) — devices with the old key's app installed
will need a one-time uninstall/reinstall.

## Roadmap

- Feedback watchdog v2: tablet-mic howl detection (persistence +
  magnitude-slope tests) and round-robin RTA over `/meters/4`, wired to
  the engine's existing veto input.
- Per-wedge config UI (choose managed buses, vocal owner per wedge,
  roles) — v1 manages Bus 1–6 with names read from the console.
- Optional Claude review layer (like AutoDirector's) when the tablet
  has internet.
