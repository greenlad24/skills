# wav2mp3

A command-line WAV → MP3 converter for macOS, built for a fresh Apple Silicon
Mac (M4 and friends). It wraps `ffmpeg` + `libmp3lame` with defaults you'd
otherwise have to look up every time, encodes files in parallel across all CPU
cores, and quietly handles the WAV formats that MP3 can't store as-is.

## Install

```bash
git clone <this-repo> && cd skills/wav2mp3
./install.sh
```

The installer checks for `ffmpeg` (installing it via Homebrew if missing),
verifies the build has the MP3 encoder, and symlinks `wav2mp3` onto your PATH.

Doing it by hand instead:

```bash
brew install ffmpeg
chmod +x wav2mp3
ln -s "$PWD/wav2mp3" /opt/homebrew/bin/wav2mp3   # Apple Silicon Homebrew prefix
```

If you don't have Homebrew yet, get it from [brew.sh](https://brew.sh) — on a
new Mac Mini it's a one-liner and takes a couple of minutes.

## Usage

```bash
wav2mp3 track.wav                        # → track.mp3, right beside the original
wav2mp3 ~/Music/Session                  # whole folder, recursively, in place
wav2mp3 -q high -o ~/Desktop/mp3 *.wav   # V0 quality into a separate folder
wav2mp3 -q 320k album.wav                # constant bitrate instead of VBR
wav2mp3 -n ~/Recordings                  # dry run — show the plan, convert nothing
```

### Options

| Option | Effect |
| --- | --- |
| `-o, --output DIR` | Write MP3s to `DIR` instead of beside each source |
| `-q, --quality Q` | `high`, `standard` (default), `small`, or a bitrate like `320k` |
| `-j, --jobs N` | Files encoded at once (default: one per CPU core) |
| `-f, --force` | Overwrite existing MP3s (they're skipped otherwise) |
| `-n, --dry-run` | Print what would happen and stop |
| `-R, --no-recursive` | Don't descend into sub-folders |
| `-F, --flatten` | Put every MP3 directly in `--output`, no sub-folders |
| `-v, --verbose` | Show the ffmpeg command and its output |
| `--no-color` | Plain output, for logs and pipes |

### Quality presets

| Preset | Encoder setting | Typical rate | Use for |
| --- | --- | --- | --- |
| `high` | `-V0` | ~245 kbps | Archiving, mastering references |
| `standard` | `-V2` | ~190 kbps | Music — transparent to nearly everyone |
| `small` | `-V5` | ~130 kbps | Voice, podcasts, phone playback |
| `320k` etc. | CBR | exactly that | Hardware/DJ gear that wants fixed bitrate |

Variable bitrate is the default because it gives better quality per megabyte
than CBR at the same average. Reach for CBR only when something downstream
demands it.

## What it handles for you

- **Sample rates above 48 kHz.** MP3 can't store 96 or 192 kHz, and ffmpeg
  errors out if you don't say what to do. `wav2mp3` resamples to the nearest
  supported rate and tells you: `192000 Hz → 48000 Hz`.
- **More than two channels.** A 5.1 WAV is downmixed to stereo rather than
  failing.
- **Tags.** Title, artist, album and friends carry across as ID3v2.3 — the
  version the Music app and most car stereos actually read.
- **Interruptions.** Each file encodes to a `.part` temp file that's only moved
  into place on success, so a Ctrl-C never leaves a half-written MP3 that looks
  like a finished one.
- **Re-runs.** Existing MP3s are skipped, so pointing it at a big folder again
  only converts what's new. `--force` overrides that.

Source WAVs are never modified or deleted. Deleting originals is deliberately
not an option — check the MP3s, then remove the WAVs yourself.

The exit code is `0` when everything converted, `1` if any file failed, so it
drops straight into a script or a `launchd` job.

## Finder Quick Action (optional)

To convert WAVs by right-clicking them in Finder:

1. Open **Automator** → **New** → **Quick Action**.
2. Set *Workflow receives current* to **files or folders** in **Finder**.
3. Add a **Run Shell Script** action, set *Shell* to `/bin/bash` and
   *Pass input* to **as arguments**.
4. Use this as the script body:

   ```bash
   export PATH="/opt/homebrew/bin:$PATH"
   /opt/homebrew/bin/wav2mp3 --no-color "$@"
   ```

5. Save it as **Convert to MP3**. It now appears under the Quick Actions
   section of the Finder right-click menu.

## Notes on performance

Encoding is single-threaded per file, so throughput comes from running several
at once — the default job count matches your core count (10 on the base M4), which
saturates the machine on a folder of files. A single large file won't go faster
than one core can encode it; that's a limit of the MP3 format, not the tool.

## Requirements

- macOS (tested against the system `bash` 3.2, so no Homebrew bash needed)
- `ffmpeg` with `libmp3lame` — the standard Homebrew build has it

It also runs fine on Linux; nothing but the installer's Homebrew step is
macOS-specific.
