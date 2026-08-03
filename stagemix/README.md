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

## Fully automatic, fully offline

The tablet lives on the **M18's own Wi-Fi** — no internet, no venue
network. StageMix is built for exactly that: on launch it **finds the
mixer itself** (broadcast discovery on the mixer's AP), reconnects
through Wi-Fi hiccups automatically (the engine freezes while meters
are stale and resumes when packets flow again), and every algorithm —
level engine and Channel Doctor — runs 100 % locally on the tablet.
Nothing phones home; nothing needs the internet, ever. Running on the
same tablet as Mixing Station also costs **zero extra Wi-Fi clients**
on the M18's 4-client AP limit — one device, two apps.

## The balance ladder — a good-sounding mix, held at all times

StageMix understands the band as a pyramid and keeps every layer in
its place, using the ratios **you** set at soundcheck:

```
        MAIN VOCAL          on top, always
      BACKING VOCAL         in the mix, under the lead
   SOLO GTR · SAX · HARMONICA   featured lines
      RHYTHM GTR (when present) · CONGAS
           PIANO / KEYS
   ▂▄█  KICK + BASS / SYNTH BASS  █▄▂   dominant foundation
```

Roles are read automatically from your console's channel names
("Kick", "SynBass", "Piano", "Rhythm Gtr", "Solo Gtr", "Sax",
"Harmonica", "Congas", "BVox", "Lead Vox"). Corrections are
**relational**: each layer is held to its soundcheck ratio against the
live kick+bass anchor. So the whole band swelling together in an
encore is *not* drift — nothing moves; but a rhythm guitar creeping up
over the piano, a backing vocal starting to compete with the lead, or
the sax getting buried during a feature is pulled back to its place —
slowly, within the same ±3/−9 dB rails. If the foundation sags, it's
lifted (capped), and the layers above ease down with it so the
foundation stays dominant either way.

## Responsive in the moment — offline

Perception is real time: the console streams its meters 20×/second and
its RTA continuously, all on the mixer's own Wi-Fi, no internet ever.
The engine understands *what changed* and reacts on the right clock:

- **The song moves to another mic** (Vocal Center → Vocal Piano → the
  channel-11 mic, even mid-song): lead-follow notices within seconds,
  gives the singing mic the **top of the pyramid**, tucks the others to
  the backing height, and re-aims the vocal-priority ducking at the new
  lead. Hysteresis stops it flapping on shared choruses.
- **A different singer takes the mic**: register detection (male vs
  female fundamental, from the vocal channel's RTA) makes the Channel
  Doctor **adopt the new voice's sound as its own reference** instead
  of "correcting" it toward the previous singer — and it remembers each
  singer's reference for when they return.
- **A silent channel wakes up** (overheads plugged in, harmonica after
  five songs): a **fast lane** (≈2 dB/s) restores it to its
  soundcheck-approved level, because targets the human approved are
  safe at speed. Only movement *beyond* the soundcheck ever creeps.
- Cuts were always fast (3 dB/s); ducking reacts within a couple of
  seconds; freezes are instant.

## The band, channel by channel

This rig ships as the built-in default profile (console names refine it
automatically): Kick (1) and Bass DI (12) + DI2 synth bass (14) are the
foundation; Snare (2), Overheads (3, usually dark), Congas (11/13) the
percussion layer; Piano stereo (6+7) in the low-mids behind the singer;
Guitar Amp (5) as the solo guitar, Guitar DI (8) as the second
electric; Vocal Center (9) the lead, Vocal Piano (10) the second
singer, channel 11 doubling as third voice; Sax/Flute (15) and
Harmonica (16) as featured color. Reverbs/FX stay yours — set them at
soundcheck; the engine balances and the doctor holds tone, it never
redesigns the sound.

## What it automates — and what it never touches

| Automated (bounded) | Never touched |
|---|---|
| Bus send levels (monitor wedges) | Main LR mix |
| Idle-channel easing (−6 dB after 60 s silence, restore on return) | Preamp/headamp gain |
| Vocal-priority ducking (cuts the band in the singer's wedge) | EQ band freq/Q/type, comp ratio/attack/release |
| Channel Doctor: per-channel EQ band **gains** (±2 dB from soundcheck, RTA-measured) | FX, routing, phantom, anything not snapshotted |
| Channel Doctor: comp **threshold** (±4 dB, restores soundcheck GR profile) | |

### The Channel Doctor (per-channel EQ + compression)

Each channel is tended **separately**, using the console's own senses:

- The M18's 100-band RTA is round-robined across active channels
  (~3 s each). Each channel's live spectrum is folded into 4 bands
  matching its 4-band EQ; when a band drifts >2.5 dB from its
  soundcheck reference, that band's **gain** is corrected — max ±2 dB
  from your soundcheck EQ, 0.25 dB steps, boosts wait for the global
  safety gate. Frequencies, Q, filter types: never touched.
- Compressor **thresholds** are eased to restore the gain-reduction
  profile each compressor had at soundcheck (singer backs off the mic →
  comp stops catching → threshold eases down; max ±4 dB). Channels
  whose comp wasn't really working at soundcheck are left alone, and
  implausible meter telemetry is discarded before it can move anything.
- The DOCTOR switch in the header turns all of it off in one tap;
  per-channel locks and Revert-to-soundcheck cover it too.

It's not a mastering engineer — it keeps every channel sounding the
way it did when **you** signed off at soundcheck.

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
  magnitude-slope tests) wired to the engine's existing veto input.
- Per-wedge config UI (choose managed buses, vocal owner per wedge,
  roles) — v1 manages Bus 1–6 with names read from the console.
- Mixing Station **desktop** bridge (optional): MS on a computer on the
  mixer's network exposes a real API (WebSocket + OSC — desktop only);
  the `MsMeters` decoder is already in the engine. Not needed for the
  offline tablet rig — direct OSC does everything locally.
- Verify `/meters/6` dynamics-bank layout against firmware (comp GR
  indices are an assumption, defensively sanity-gated until then).
