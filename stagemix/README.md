# StageMix AI 🎚️

The **FOH autopilot** for the Midas M18 / MR18 (X-Air family), on an
Android tablet next to Mixing Station. It **leads the main mix all
night** — no soundcheck ritual required — and **never touches the six
monitor buses**: monitors stay 100 % human, in Mixing Station, always.

## The deal: it leads the mains, you own the monitors

- The only mixer parameter the engine can write is the **channel fader**
  (`/ch/NN/mix/fader` — the mains path). Bus sends have no
  representation in the engine at all; "never mix the monitors" is an
  architectural invariant with its own test, not a setting.
- Keep monitor sends **pre-fader** (the console default) and the
  autopilot's fader moves never reach the wedges.
- Flip **MIXING** on and it takes over: the current fader positions
  become its authority bounds (−12 … +6 dB around them, absolute fader
  ceiling +2 dB), it listens for ~20 seconds, then it mixes.
- **Hand back the mains** restores the exact takeover faders in one tap.

## How it leads without a soundcheck

The engine carries a built-in **balance pyramid** for the band and
steers each channel's *contribution to the mains* toward it,
cross-adaptively, using the console's pre-fader meters (20×/second,
fully offline on the mixer's own Wi-Fi). The heights are **group**
targets — what the room hears from the three drum channels together,
not from each one — so a rig with one bass and a rig with three get
the same mix:

```
      MAIN VOCAL     on top, always  (+1 over the whole kick+bass GROUP)
        CONGAS · SNARE · OVERHEADS                    (−6)
   SOLO GTR · SAX · HARMONICA                         (−6)
           PIANO / KEYS  (low-mid bed)                (−7)
   RHYTHM GTR · second electric · BACKING VOCAL       (−8)
   ▂▄█  KICK + BASS DI + DI2 SYNTH BASS  █▄▂  dominant foundation (0)
```

Each group's target is shared out across however many of its channels
are actually playing, so the two piano channels sit 3 dB lower each
than a single piano would — and together they land exactly where the
pyramid asks. Read as per-channel heights, those same numbers used to
put the four foundation channels 8 dB over the singer.

Pre-fader metering means it hears the true sources regardless of its
own moves: contribution ≈ source loudness + fader, and every fader is
steered so contributions sit at their pyramid heights relative to the
live kick+bass anchor. The band swelling together moves the anchor —
ratios intact, nothing re-mixed. A hot solo guitar gets seated; a
buried vocal gets lifted (bounded); the foundation stays dominant.

**The foundation is balanced against itself, too.** Kick, bass DI, bass
mic and synth bass are levelled against each other, so a kick channel
gained 10 dB low is pulled back up instead of the whole band quietly
following it down all night. The group's *overall* level answers only
to drift **relative to the rest of the band**: a band that plays a
whole song quieter is playing a ballad, and 11.9 of its 12 dB reaches
the audience untouched; a drummer whose kick alone runs hot gets
seated.

**A player who steps up keeps it.** When one channel rises well over
its own level of a few seconds ago while the rest of the band has not,
that is a solo, not drift — the engine leaves that fader alone for up
to 90 seconds. A 40-second sax feature used to end 4 dB quieter than
the player played it, and leave them under-mixed for half a minute
afterwards; now the whole step reaches the room and they rejoin the
balance within a couple of seconds.

## Built for the open stage

The place and the players change all night — the engine follows the
**ensemble**, not a fixed band:

- **Singer + acoustic guitar open the night** (guitar on Guitar DI or
  ch 11/13): with no rhythm section, the anchor cascades to the
  accompaniment — the voice sits on top of the guitar at the right
  gap, just the two of them, mixed like a duo should be.
- **Piano/vocal duet** (both ch 9 and 10 on mic): a genuine duet is
  detected (both mics strongly on) and BOTH voices sit near the top
  together instead of one being tucked to backing height.
- **A drummer joins — no bass player**: the lineup change is detected
  within seconds, logged, and the **piano covers the low end** — its
  pyramid height rises and the Channel Doctor lifts its low EQ band
  toward the rail, filling the missing bass frequencies.
- **The bass player arrives 5 minutes later**: detected, the piano
  hands the low end back (EQ returns to neutral, height returns), the
  foundation takes the anchor, full-band pyramid engages — all through
  the fast lane, all logged.

Every lineup change opens the fast lane so the new balance settles in
seconds, not minutes — and the same bounds, budgets and freezes hold
through all of it.

## It proves itself, listens to you, and improves every night

**Audition it (shadow mode):** take over the mains without flipping
MIXING on and it watches, decides, and logs every move it *would*
make — touching nothing. Judge it for a set before trusting it.

**MIX HEALTH, live:** the console header shows how it's actually
doing — % of time the lead vocal sits on top, % of channels at their
pyramid height, and how many times a human had to out-mix it. Not a
feeling; a number — and an honest one: the vocal is scored against the
**power sum** of the band, which is what the room hears. Scored against
the band's *average* channel, a vocal sitting 10 dB under the band as a
whole reported "on top 99 % of the night".

**Three kinds of feedback it recognizes:**
1. **Your faders are feedback.** Grab any fader (here or in Mixing
   Station) while it's mixing: it instantly adopts your position as
   the new baseline, keeps its hands off that channel for 2 minutes —
   and *learns a small bounded lesson* from the disagreement. A move
   has to be bigger than the wire's own noise (0.25 dB) to count, and
   the app remembers every fader it wrote, so a console that echoes
   parameter changes back can never be mistaken for a person.
2. **The feedback bar:** 👍 "Sounds great" or one-tap chips — vocal
   louder/softer, more/less guitar, more/less piano, more low end,
   less percussion, softer sax/harp. Each nudges its built-in taste
   (bounded ±3 dB per role) and is logged in plain language.
3. **The room's feedback:** a howl recognizer runs on the console's
   RTA. Telling a howl from your harmonica, sax, organ or a held vocal
   note is the whole problem — all of them are narrow, parked, loud
   peaks — so it uses two discriminators: instruments have **harmonic
   partners** at 2f and 3f (feedback, a single room resonance, does
   not), and a howl **grows** ≥12 dB at a fixed frequency even when the
   band's level masks it. On detection:
   it freezes all boosts instantly and shows the frequency to notch.
   And a **harshness guard** watches every mic and guitar for shrill
   2–6 kHz energy towering over the channel's own body — easing that
   channel's high-mids down (cut-only, max 2 dB) until it passes.
   Cymbals and kick click are exempt by design.

**It continues from last night.** Everything it learns — feedback
chips and override lessons — is saved on the tablet and reloaded at
the next connect, and each night's health summary is kept: the console
greets you with "NIGHT 12 · learned: vocal +2 · guitars −1" and last
night's score. Every night starts where the last one ended, bounded
so ten bad taps can never push any taste past ±3 dB.

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
| Channel faders → the MAIN mix | **All 6 monitor buses — ever** |
| Idle-channel easing + fast rejoin | Main LR master fader |
| Vocal-priority ducking (cut-only, in the mains) | Preamp/headamp gain |
| Channel Doctor: EQ band gains ±2 dB, comp threshold ±4 dB (from takeover settings) | EQ freq/Q/type, comp ratio/attack/release, FX, routing |

### The Channel Doctor (per-channel EQ + compression)

Each channel is tended **separately**, using the console's own senses:

- The M18's 100-band RTA is round-robined across active channels
  (~3 s each). Each channel's live spectrum is folded into 4 bands
  matching its 4-band EQ; when a band drifts >2.5 dB from its
  soundcheck reference, that band's **gain** is corrected — max ±2 dB
  from your soundcheck EQ, 0.25 dB steps, boosts wait for the global
  safety gate. Frequencies, Q, filter types: never touched.
- Compressor **thresholds** can be eased to restore the gain-reduction
  profile each compressor had at takeover — **off by default**: that
  feature rides on an unverified assumption about which console meter
  field carries gain reduction, and automating on an unverified index
  is how a wrong field walks a threshold to its rail. Flip it on
  (`compTendingEnabled`) once the layout is confirmed on the M18. EQ
  tending, which uses the verified RTA, is always available (singer backs off the mic →
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
- ±2 dB deadband — musical dynamics are not drift. It is hysteresis,
  not a stopping line: once a fader starts moving it converges, so the
  resting position does not depend on which side it came from.
- The boost budget is what the ROOM hears: the limit is how much louder
  the engine's lifts have actually made the mains (3 dB), not the
  arithmetic sum of the offsets. Six dB on a harmonica sitting 30 dB
  down costs almost nothing; six dB on the kick costs the lot.
- Automatic freeze on: input near clip, meter dropout, sudden broadband
  change (song start/stop), operator FREEZE, watchdog veto.
- One-tap **Revert to soundcheck**. Per-channel locks.

## Show flow

1. Tablet on the M18's Wi-Fi. Open StageMix — it finds the mixer and
   reads your channel names by itself.
2. Rough the faders in anywhere sane (or don't — the bounds protect
   you either way). Mix your monitors in Mixing Station as usual.
3. Flip **MIXING** on. It takes over the mains, listens ~20 s, then
   leads the night: pyramid balance, lead-vocal follow between Vocal
   Center / Vocal Piano / channel 11, singer-register adaptation,
   idle easing, duck-the-band-not-the-vocal, freeze-on-anything-odd.
4. Your monitors never move unless you move them. **Hand back the
   mains** any time.

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
- Verify `/-stat/rta/source` numbering on the M18 (the app sends it
  0-based and the console never confirms; if the enum is 1-based the
  Channel Doctor would be reading the neighbouring channel's spectrum).
- Probe whether the console honours `/xremotenfb`. It is not ACKed, so
  a firmware that ignores it is indistinguishable from one that does
  not — the echo filter makes both safe, but a positive check would be
  better than a safety net.
