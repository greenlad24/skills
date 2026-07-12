# Zero-install capability matrix (verified 2026-07)

Product requirement: **no additional software or hardware on Windows or
older Macs.** Findings below come from a five-agent research team working
from primary sources (Microsoft/Apple docs and shipping projects); the
full reports live in the session record, key citations inline.

## What works with ZERO installs today (shipped)

| Capability | macOS (any) | Windows |
|---|---|---|
| Directing (live + podcast), calibration | ✅ shared CoreAudio input capture | ✅ WASAPI shared-mode capture |
| Podcast voice chain + AI review | ✅ (native OBS filters via websocket) | ✅ |
| Program-bus sweetening (EQ/glue/limiter in OBS) | ✅ | ✅ |
| Capture of "in-OBS-only"/desktop audio | ❌ ≤ macOS 12 (no API exists) / 🔜 13+ (see roadmap) | ✅ **built-in WASAPI loopback** (bundled `soundcard>=0.4.6`, keep-alive silence, ≥2ch capture) |
| Mix Engineer — **Advisory mode** (AI recommends, you ride the fader) | ✅ | ✅ |
| Mix Engineer — auto faders (MCU) | ✅ (native virtual MIDI ports) | ⚠️ needs loopMIDI **on older Windows only**; native path on Win11 24H2+ (roadmap) |
| 16-ch post-fader stems | via BlackHole (install) or interface loopback (see below) | via interface loopback only |

**Interface loopback counts as zero-install** (hardware you already own):
RME TotalMix (full channel count) and MOTU AVB routing (16+) can return
DAW post-fader sends as capturable inputs; any interface with spare
ADAT I/O can do it with two lightpipes. Focusrite/PreSonus/MOTU Gen5
loopback is stereo-only → Advisory tier.

## Verified platform facts that shape the roadmap

- **Windows 11 24H2/25H2 (Feb 2026 update, KB5077181) ships Windows MIDI
  Services in-box**: apps can create *virtual MIDI devices* that classic
  DAWs (Cubase, Studio One) see as normal ports — the zero-install
  replacement for loopMIDI. The same rollout **broke loopMIDI-class
  drivers on 25H2**, so the native path is the future, not an option.
  Integration: bundle Microsoft's SDK runtime (silent install permitted)
  + a small C++/WinRT shim DLL called from Python. Windows 10 / ≤23H2:
  no in-box path exists; loopMIDI or Advisory mode remain.
- **macOS 13+ can capture app/system audio with no driver** via
  ScreenCaptureKit (stereo; Screen Recording permission). Pure-Python SCK
  audio is a documented dead end — the proven pattern is a small bundled
  Swift helper streaming PCM over stdout (ProcTap/AudioTee pattern).
  **macOS 14.2+** adds Core Audio process taps: audio-only permission,
  and plausibly multichannel (validated to 7.1 elsewhere; 16ch via a
  device-stream tap is credible but must be validated on hardware).
  **macOS ≤12: confirmed impossible** — BlackHole guided install is the
  only path, and the app should say so plainly.
- **WASAPI loopback is blind to ASIO.** Cubase on Windows renders via
  ASIO only, so loopback cannot hear a Cubase feed; it *can* hear
  Studio One in "Windows Audio" mode and anything OBS monitors. Loopback
  channel ceiling is the endpoint mix format (stereo typical, 7.1 max).
- **Unsigned/ad-hoc apps lose macOS capture permissions on every
  update** (TCC identifies by code signature). Developer ID signing +
  notarization becomes necessary the moment SCK/tap capture ships.

## Fully automatic on macOS 11 (Big Sur) — the concrete story

macOS has **native virtual MIDI on every version**, so auto-fader
control works on 11.x with zero installs — Advisory mode was only ever
the Windows no-MIDI fallback. The complete hands-free setup on 11.7:

1. **Directing**: automatic (obs-websocket + shared-device capture).
2. **Mix control**: automatic — MCU virtual ports, DAW binds Mackie
   Control; ±6 dB rails from soundcheck.
3. **Analysis**: `capture_channels: 2` puts the Mix Engineer in
   **stereo-mix mode** — it listens to the same program feed OBS
   broadcasts (whatever already carries S1 → OBS on the rig: an
   existing BlackHole 2ch, interface loopback — CoreAudio devices are
   multi-client, so AutoDirector opens it alongside OBS with nothing
   new installed) and drives faders automatically on tighter,
   role-limited rails: lead vocal ±1.5 dB on masking evidence,
   named instrument trims ±1.0 dB, program sweetening in OBS as usual.
4. **Auto-soundcheck**: if nobody presses "Soundcheck snapshot", the
   engineer takes its own reference after ~45 s of the band audibly
   playing. No buttons required, ever.

The installer's minimum macOS is 11.0.

## Tiers (auto-detected, highest first)

1. **Full stems + auto faders** — 16ch capturable device present
   (interface loopback / BlackHole / future validated process tap) +
   working MIDI path → complete Mix Engineer.
2. **Stems + Advisory** — stems present, no MIDI → analysis-grade
   recommendations, program sweetening auto-applied.
3. **Stereo Advisory** — program mix only (WASAPI loopback / SCK /
   interface stereo loopback) → masking + balance advice from the mix
   (degraded analyzer, roadmap), lead-vocal-only suggestions on tight
   rails; program sweetening auto-applied.
4. **Director-only** — no capture beyond the show feed; all directing
   features, no mix advice.

## Roadmap (ranked)

1. **Windows MIDI Services virtual device** (shim DLL + bundled MS SDK
   runtime): zero-install auto faders on Win11 24H2+.
2. **macOS capture helper** (bundled Swift binary: SCK backend 13+,
   process-tap backend 14.2+): BlackHole-free capture on modern Macs;
   requires Developer ID signing for a sane permission experience.
3. **Degraded stereo advisor** (`mixer/degraded.py`): mid/side +
   harmonic-salience masking estimate, spectral balance vs. soundcheck —
   makes Advisory genuinely useful with nothing but the program mix.
4. **Process-tap multichannel validation** (macOS 14.2+): if 16ch
   device-stream taps hold up on hardware, zero-install stems on Macs.
