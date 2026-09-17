# DroidMirror

A native macOS app (AppKit + VideoToolbox + AVFoundation, no Electron, no ffmpeg) that mirrors an
Android phone — built for a Samsung Galaxy S20 FE — to an Intel Mac running macOS 11 Big Sur
(11.7.10) over USB, in **landscape**, with **audio**, at **native resolution** and with the lowest
latency the pipeline allows.

It talks directly to the [scrcpy](https://github.com/Genymobile/scrcpy) Android server (v2.7) over
`adb`, so the only things it needs besides itself are `adb` and `scrcpy-server`, both of which the
setup script downloads and bundles into the `.app`.

## What you get

- Landscape mirroring locked on the encoder side (`lock_video_orientation=1`), so the picture is
  horizontal even while the phone is held upright. Switchable in **View** (Landscape / Reversed /
  Portrait / Follow Device).
- Native resolution (`max_size=0` → 2400×1080 on the S20 FE), 20 Mbit/s H.264, uncapped frame rate
  (the phone encodes at its display refresh rate).
- Hardware decoding with VideoToolbox through `AVSampleBufferDisplayLayer`; every frame is flagged
  *display immediately* — no buffering, no clock sync.
- Audio: the phone's output is captured (Android 11+) and streamed as raw 48 kHz stereo PCM (no
  codec on either side); played with `AVAudioEngine`, and anything queued more than ~120 ms ahead
  is dropped so audio stays in step with video.
- Control: mouse = touch (click / drag), scroll wheel & trackpad = scroll, right-click = Back,
  middle-click = Home, keyboard typing → text injection, arrows/Return/Delete/Tab/Esc mapped to
  Android keys. Bottom bar and **Device** menu: Back, Home, Recents, Power, Volume, Notifications,
  Rotate, turn the phone screen off while still mirroring.
- Auto-reconnect when the phone is unplugged and plugged back in.

## Requirements

- Intel Mac, macOS 11.0 or later (tested target: 11.7.10). Build with Xcode 13.x (the last Xcode
  for Big Sur) or its Command Line Tools.
- Samsung S20 FE (or any Android 5+ device; audio needs Android 11+) with **USB debugging** enabled:
  *Settings → About phone → Software information → tap “Build number” 7×*, then
  *Settings → Developer options → USB debugging*.
- A USB cable that carries data (not charge-only).

## Build

```bash
cd mac-mirror
./scripts/setup.sh       # downloads adb + scrcpy-server v2.7 into Tools/ (checks the server's SHA-256)
./scripts/build-app.sh   # swift build -c release --arch x86_64, assembles build/DroidMirror.app
open build/DroidMirror.app
```

For development you can also just `swift run` from `mac-mirror/`; the app finds `Tools/adb` and
`Tools/scrcpy-server` relative to the build directory.

## First run

1. Plug the phone in. On the phone, tap **Allow** on the “Allow USB debugging?” prompt (tick
   *Always allow from this computer*).
2. Launch DroidMirror. It finds the device, pushes the server, and the picture appears within a
   second or two. On Android 11+ a one-time “start recording / casting” system dialog may appear on
   the phone for audio capture — accept it.
3. If Samsung’s USB mode prompt shows up, leave it on *File transfer / Android Auto*; either works
   as long as USB debugging is on.

## Tuning

Defaults live in `SessionConfig` (`Sources/DroidMirror/ScrcpySession.swift`):

| Setting        | Default      | Notes                                                                 |
|----------------|--------------|-----------------------------------------------------------------------|
| `maxSize`      | `0` (native) | Set e.g. `1920` if the Mac struggles to decode 2400×1080 at 120 Hz.   |
| `videoBitRate` | `20_000_000` | Higher = sharper. USB has bandwidth to spare; 8–30 Mbit/s are sane.   |
| `maxFps`       | `0` (uncapped)| `60` lowers phone battery/heat and Mac decode load.                  |
| `orientation`  | `.landscape` | Also switchable at runtime from the View menu.                        |
| `audio`        | `true`       | Toggle from the View menu.                                            |

Audio queue depth is `AudioPlayer.maxQueuedSeconds` (default 0.12 s).

## How it works

```
Mac                                              Phone (USB, adb)
────────────────────────────────────────────     ──────────────────────────────────
adb push scrcpy-server  ───────────────────────► /data/local/tmp/scrcpy-server.jar
adb forward tcp:27183 → localabstract:scrcpy_xx
adb shell app_process … com.genymobile.scrcpy.Server 2.7 …  (server starts)
connect 27183 → video socket   ◄──────────────── dummy byte, device name, codec meta, H.264 frames
connect 27183 → audio socket   ◄──────────────── codec meta, raw PCM packets
connect 27183 → control socket ────────────────► touch / key / text / scroll messages
H.264 Annex-B → AVCC → CMSampleBuffer → AVSampleBufferDisplayLayer (VideoToolbox)
PCM s16le → AVAudioPCMBuffer → AVAudioPlayerNode
```

## Troubleshooting

- **“adb was not found”** – run `scripts/setup.sh`, or set `DROIDMIRROR_ADB=/path/to/adb`.
- **“has not authorised this Mac”** – unlock the phone and tap *Allow* on the USB debugging prompt.
- **No device detected** – try another cable/port; check `Tools/adb devices` lists it as `device`.
  If it shows `offline`, revoke USB debugging authorisations in Developer options and re-plug.
- **No audio** – the status bar says why. Samsung One UI sometimes blocks capture of DRM/protected
  apps; system sounds, YouTube, games work. Also make sure phone media volume isn’t muted.
- **Picture is stretched/black after rotating the phone** – pick an orientation lock in the View
  menu (Landscape is the default), or *Device → Connect* to restart the stream.
- **Stutter at native resolution** – set `maxSize = 1920` or `maxFps = 60` and rebuild.
