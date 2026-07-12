# Mac mini M4 + Studio One 7 + OBS — verified setup path

The exact click-path for the recommended rig. Total time: ~20 minutes
once, then every show is: open three apps, press play.

## 0. One-time installs

1. **OBS Studio** (30+, Apple Silicon build) — obsproject.com
2. **Studio One 7** (native Apple Silicon)
3. **AutoDirector** — `AutoDirector-apple-silicon.pkg` from the
   [latest-build release](https://github.com/greenlad24/skills/releases/tag/autodirector-latest).
   Right-click → Open the first time (unsigned build). Grant microphone
   access when macOS asks.

## 1. OBS (2 minutes)

- *Tools → WebSocket Server Settings* → **Enable**, copy the password.
- Build your scenes (singer / wide / instruments — or the podcast shots).
- Audio: add the feed that carries the Studio One mix (see §3).
  On macOS 13+ OBS's own **"macOS Audio Capture"** source can grab
  Studio One's audio directly for the *broadcast* side.

## 2. Studio One 7 (5 minutes)

1. Launch **AutoDirector first** — its two MIDI ports
   ("AutoDirector MCU 1" / "AutoDirector MCU 2") exist while it runs.
2. Studio One → *Preferences → External Devices → Add…*
   - **Mackie → Control** — Receive From / Send To: `AutoDirector MCU 1`
   - **Mackie → Control XT** — Receive From / Send To: `AutoDirector MCU 2`
3. That's 16 fader strips under software control. Wiggle any S1 fader
   once — the Control Room's MIDI pill turns green (wiring confirmed).
4. Channel names appear in AutoDirector automatically (scribble-strip
   protocol); name your S1 channels normally ("Lead Vox", "Kick", ...).

## 3. The mix feed AutoDirector listens to (pick one)

| Your setup | Route |
|---|---|
| Audio interface with loopback (RME/MOTU: full stems; Focusrite/PreSonus: stereo) | S1 outputs → interface; AutoDirector + OBS capture the loopback input. Zero installs. |
| Plain interface, stereo analysis (the default) | Install **BlackHole 2ch** (free, 2 min): S1 main out (or a post-fader stereo send) → BlackHole; OBS *and* AutoDirector both open BlackHole (macOS input devices are multi-client). |
| 16-channel stems | **BlackHole 16ch** + per-channel post-fader sends (or RME/MOTU routing) → full per-stem Mix Engineer. |

Set the device in AutoDirector's Setup drawer (`mixer.device`), with
`capture_channels: 2` for stereo analysis or `16` for stems.

## 4. First run

1. Open AutoDirector → Control Room appears → Setup drawer: paste the
   OBS password → **Test connection** (should report your scene count) →
   pick scenes/devices → Save & apply.
2. **Live mode:** run the 20-second calibration (10 s band only, 10 s
   with the singer) — or skip it; the generic detector works, just less
   sharply.
3. Soundcheck: play for ~45 s. AutoDirector snapshots the baseline
   itself (or press *Soundcheck snapshot*).
4. Flip **DIRECTING** on. Done — it cuts the show, rides the mix, and
   sweetens the program feed until you turn it off.

## 5. Unattended-show checklist (do once, before show night)

- System Settings → Displays/Energy: **prevent sleep**, no screen saver
  interruptions to capture.
- Notifications: **Do Not Disturb** scheduled over show time.
- Software Update: automatic updates **off** on show days.
- Wired Ethernet; router on the same UPS as the Mac if possible.
- OBS: *Settings → Advanced → automatically reconnect* on.
- One full-length rehearsal: 3 hours, real session, real stream to an
  unlisted destination. Watch the Control Room log once, then trust it.

## What "smooth" looks like on an M4

Measured expectations: AutoDirector's DSP uses <5% of one core;
OBS 1080p via the hardware encoder ~10-15%; a 16-channel S1 session
with sensible plugins 20-40%. Total well under half the machine,
silent, cold. The fail-safe rule stands at every layer: if anything in
AutoDirector ever hiccups, OBS keeps streaming and Studio One keeps
playing exactly where they were.
