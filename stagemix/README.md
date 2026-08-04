# StageMix AI 🎚️

The **FOH autopilot** for the Midas M18 / MR18 (X-Air family), on an
Android tablet next to Mixing Station. It **leads the main mix all
night** — no soundcheck ritual required — and **never touches the six
monitor buses**: monitors stay 100 % human, in Mixing Station, always.

## KEEP the balance you made, or LEAD from scratch

The app has two jobs and you pick which one it is doing.

**KEEP** (the default) takes the balance already on the desk as the
plan and defends it. It holds each channel's *contribution* — source
plus fader — where you put it: the singer leans into the mic and gets
3 dB louder, the fader comes down 3 dB; they back off, it goes back up.
Nothing else moves unless somebody solos or an instrument arrives that
was not there. `✓ Keep this balance` re-adopts whatever is on the desk
right now.

**LEAD** derives a balance from the built-in pyramid, for when there is
no human mix to preserve. `↻ Find a new balance` switches to it until
the mix comes to rest, then keeps what it arrives at.

Why the default changed: on a real night, twenty-one minutes of LEAD
moved the faders 1558 dB in total, spent 16 % of its time with a
channel pinned at an authority rail and 40 % with the band pinned at
the duck's, and still had the vocal on top less than half the time.
That is not a mix being refined, it is a controller that cannot reach
its setpoint. The same operator built the mix they wanted by hand in
about a minute. KEEP over the same band and the same length of time
moves the desk about a tenth as far.

## The deal: it leads the mains, you own the monitors

- The only parameter the **balancing** engine can write is the **channel
  fader** (`/ch/NN/mix/fader` — the mains path). Everything the engine
  decides about level goes out through that one address.
- Channel *processing* — the high-pass, the EQ, the compressor, and the
  reverb send — is written once per instrument by the
  [starting chain](#the-starting-chain-set-once) and by the Channel
  Doctor. Those are channel strips and FX sends, never an aux send:
  sends 1–6 feed the wedges and the in-ears and are refused outright by
  a whitelist (`isSafeAddress`) with a test whose only job is to try to
  get an aux send past it. "Never mix the monitors" is an architectural
  invariant, not a setting.
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
| Channel Doctor: EQ band gains ±2 dB, comp threshold ±4 dB (from takeover settings) | Aux sends 1–6, routing, channel mute/ON |
| Starting chain, once per identified instrument: HPF, EQ, compressor, reverb send | Anything on a channel the engineer has since moved by hand |

One shared setting is not a mix parameter but is worth knowing about:
to give the Channel Doctor a per-channel spectrum the app repoints the
console's **RTA source** (`/-stat/rta/source`) every ~3 seconds. That
setting is global to the console, so X AIR Edit or Mixing Station open
on the analyzer page will see it moving. Turn DOCTOR off and it stops.

### What it cannot hear, and what to do about it

A hundred-bin RTA cannot tell a saxophone from a singer. Both are a
moving melody in the 400 Hz–5 kHz band with nothing underneath — which
is exactly what makes both of them work as the line over a band — and
no amount of cleverness with the numbers the console provides will
separate them. On a rig where the channel labelled SAXOPHONE is a
singer and the one labelled UTILITY 3 is the saxophone, neither the
ears nor the labels will ever sort it out.

**Tap the instrument line on a channel strip** (right-click on the
bench) and say what it is. It is pinned — the listener keeps forming an
opinion and never acts on that channel again — and remembered against
the *console's name* for the channel, so it holds tomorrow night, and
follows the name if the band re-patches.

### The starting chain, set once

Once the app has *heard* what is on a channel — not read it off the
label — it sets that channel up the way an engineer would at
soundcheck, and then leaves it alone:

| | |
|---|---|
| **When** | the first time the AUDIO is confident (not the channel name), and again only if the instrument changes or the sound on the socket genuinely changes and stays changed for half a minute |
| **What** | channel high-pass, one or two EQ moves, compressor threshold/ratio/attack/release/makeup, and a reverb send |
| **Reverb** | voices, kit, keys, horns and lead guitar. Never the kick, never the bass, never a DI, never a talkback mic — reverb on the low end is how a room turns to mud |
| **Never** | a parameter the engineer has moved since. That one is theirs; a re-treat skips it rather than argues |

After that it is balance work only, which is the whole point: an
autopilot that keeps re-EQing is worse than one that never EQs at all.

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

## The show log — test it tonight, read it tomorrow

Every night is written to a plain text file on the tablet as it
happens, with no network of any kind. It is meant to be read the
morning after by someone who is not standing in front of the mixer:

| tag | what it records |
|---|---|
| `HEAD` | the rig: mixer, channels, roles, pyramid targets, limits, what it learned on previous nights |
| `TAKE` | the fader positions that became the authority bounds |
| `LVL` | every 5 s, per channel: source level heard, 3 s level, fader, our offset, duck, contribution, **where the pyramid wanted it**, and flags (silent / room-tone / idle / feature-hold / locked / yours / lead) |
| `MIX` | every 5 s: the anchor and who forms it, mix health, how much the boosts have added, any hold |
| `DEC` | every decision, with its reason in plain language |
| `FADER` | every fader write |
| `EQ` | every EQ band move, with how far that band had drifted from your soundcheck tone |
| `COMP` | every compressor threshold move, with the gain reduction it is chasing |
| `TONE` | every 30 s, per channel: live 4-band tone shape, drift from soundcheck, our EQ correction, harshness, gain reduction, detected singer register |
| `HOWL` | feedback suspected / cleared, with the frequency |
| `NET` | connect, meter loss, partial takeover |
| `USER` | everything you did — MIXING, FREEZE, locks, feedback chips, fader grabs |
| `SUM` | once a minute: the state of the mix in one line |

It is grep-friendly on purpose — `grep ' FADER ' show.log` is the
night's fader moves, `grep ' DEC ' show.log` is the reasoning.

### Exporting it

**⤴ EXPORT LOG** in the console opens the Android share sheet with the
whole log attached, so it goes to WhatsApp, mail or Drive in one tap.
The file is staged as `.txt` because that is what WhatsApp accepts as a
document. **short version** shares a one-screen digest instead — the
rig, what you did, what the network did, how many decisions of each
kind, fader moves per channel, and the final balance table — small
enough to paste straight into a chat.

Both work while the tablet is still on the M18's Wi-Fi with no
internet: the share hands the file to WhatsApp, which sends it the
moment the tablet is back on a normal network. The files also sit at
`Android/data/com.stagemix/files/logs/` over USB. The last ten nights
are kept.

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
5. At the end of the night, **⤴ EXPORT LOG** → WhatsApp.

## Testing it against a night you already recorded

If the desk has been recording to a DAW over USB, that session is 16
tracks of the same sources the console meters — so the engine can be run
over it as if the band were on stage right now. Same engine, same
Channel Doctor, same show log; the only thing simulated is the clock.

```
java -jar stagemix-replay.jar "/path/to/the session's audio files"
```

Point it at the folder holding the per-track WAVs (in Studio One that is
the song's `Media` folder — no export needed) or at a single
multichannel WAV. Channel numbers come from a leading number in the file
name; the names set the roles the same way the console's channel names
do live.

Useful flags:

| flag | what it does |
|---|---|
| `--render` | also write `<take>_autopilot.wav` — the mix the engine would have made — and `<take>_flat.wav` at the takeover faders, so you can A/B them |
| `--start 600 --length 900` | replay 15 minutes from ten minutes in |
| `--fader -8` | start from a different takeover position |
| `--shadow` | decide and log everything, but leave the rendered mix flat |
| `--capture night.smcap` | write a **meter tape** (below) |

### The bench: a virtual M18 on a Mac

Better than replaying: **make the tablet mix a recorded night for real.**

**Installing it on a Mac:** download **VirtualM18-AppleSilicon.dmg**
from the `stagemix-latest` release, drag *Virtual M18* to Applications
and open it. It carries its own Java runtime — nothing else to install.

It is not signed by Apple (notarizing needs a paid Developer account),
so macOS blocks the first launch with *"Apple could not verify…"*. On
Sequoia the old right-click → Open bypass is gone; use either:

```
xattr -dr com.apple.quarantine "/Applications/Virtual M18.app"
```

or **System Settings → Privacy & Security → Open Anyway** (the button
appears only after the first blocked attempt). macOS will also ask to
allow incoming connections: say yes, or the tablet cannot reach it.

**Testing with no tablet in the room:** press **AUTOPILOT on this Mac**.
A second window opens — the tablet's console screen: mode and hold
reason, MIX HEALTH, the feedback chips, a strip per channel with its
role, level, correction and doctor moves, and the running decision log.
Take over the mains from there, or with the bench's **MIXING** button. The autopilot runs on the Mac and talks to the console
over real UDP — the same `StageEngine`, `ToneDoctor`, howl watchdog and
show log the tablet runs, so the whole path is exercised rather than
shortcut in-process. Its log lands in `~/StageMix/logs/`. The transport
loop is a port of the Android service rather than the same code, so a
bug living only in that service still needs the tablet to find.

There is a window. Along the top: **PLAY**, **START** (rewind), **MUTE
SPEAKERS** and **Choose folder…**; below that, one strip per channel.
Click any strip to put a file on that channel — so channels can be
loaded one at a time, or the whole folder at once.

Or from a terminal, with the jar and any Java 17:

```
java -jar virtual-m18.jar "/path/to/the night's channels"
```

The app connects, reads the channel names, takes over the faders and
starts mixing — and **the faders it writes are applied to the audio
coming out of the speakers**, so you hear its mix while you watch it
work on the tablet. Nothing in the app is modified or aware of this: it
is talking OSC to something that answers exactly as the console does —
same addresses, the same meter banks at the console's own 50 ms cadence,
the same 1024-step fader quantization, the same 10-second subscription
timeout.

Files are matched to channels by a leading number (`09 Vocal Center.mp3`
is channel 9). WAV, MP3 and AIFF all work and they need not share a
format or sample rate. Names become the console's channel names, which
is also what sets the roles.

The window shows, per channel: what the desk is hearing pre-fader, what
the room is hearing after the tablet's fader, and where the tablet has
put that fader — so every move is visible within a frame and audible
immediately.

**The three things a recording cannot contain**, modelled so they can be
tested indoors:

- **ROOM LOOP** — the PA back into the open mics. One resonance: every
  open mic hears the mains, attenuated by distance from the boxes and by
  wherever its fader is now; above unity gain it rings up, below it
  decays. The tone is injected *before* metering, so the meters see it,
  the RTA sees a narrow peak climbing, and it comes out of the speakers.
  **PROVOKE FEEDBACK** opens the loop 10 dB for six seconds, as if
  someone walked a mic into the boxes. Without this the howl watchdog —
  the most consequential safety feature in the app — cannot be tested at
  all on a recording, because the engine's own moves can never change
  what a fixed recording hears.
- **Gain reduction** — a compressor and gate model reading the *same*
  threshold the console holds, so `/meters/6` carries real numbers and
  the Channel Doctor's compressor tending has a loop to close. The bench
  used to send zeros.
- **DROP WI-FI 8s** and `--loss <pct>` — the radio failing, so the
  engine's meter-timeout freeze and its recovery actually run.

| flag | why |
|---|---|
| `--room` | room loop on from the start |
| `--loss 5` | drop 5 % of the console's packets |
| `--start 600` | begin ten minutes in |
| `--echo` | behave like firmware that reflects parameter changes back to the sender — the case that used to make the app freeze every channel. Worth one run. |
| `--no-quantize` | perfect faders instead of the console's 1024 steps |
| `--headless` | no window |

### The meter tape — sending a night without sending the audio

A recorded night is tens of gigabytes. The engine never sees any of it:
its entire input is sixteen levels twenty times a second plus a 100-bin
spectrum of one channel at a time. Written at half-dB resolution that is
**about a megabyte for a three-hour night**, and it drives the engine to
the same place the audio does — a round-trip test asserts every channel
lands within 0.75 dB of the audio replay.

```
java -jar stagemix-replay.jar "/path/to/audio" --capture night.smcap
```

`night.smcap` can then be replayed anywhere — the audio never leaves the
machine it was recorded on:

```
java -jar stagemix-replay.jar night.smcap
```

`stagemix-replay.jar` is attached to the `stagemix-latest` release next
to the APK, and needs nothing but Java 17.

## Building

- `./gradlew :engine:test` — the whole mix engine is a pure-JVM Kotlin
  module with scenario tests (no Android SDK needed).
- `./gradlew :replay:test` — the offline replay tool (also pure JVM).
- `./gradlew :replay:fatJar` — builds `stagemix-replay.jar`.
- `./gradlew :virtualm18:test` / `:virtualm18:fatJar` — the bench console.
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
