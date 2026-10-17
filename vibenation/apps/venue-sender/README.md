# VibeNation venue sender

The old Windows laptop at the venue only **captures and transmits**: 16 channels from the Midas MR18 over USB
(raw preamp "Analog" tap, 48 kHz) → uncompressed 24-bit PCM → SRT → the show server. No processing happens here.
Studio One can keep recording a local backup at the same time.

## One-time setup (laptop)
1. **MR18 / X AIR Edit** → In/Out → **USB Sends** → set the default signal tap to **Analog** (applies to all
   channels). On **USB Returns** keep "off analog". Sample rate **48 kHz**. *Never change preamp gain from here.*
2. Install the **Behringer X-AIR USB / ASIO driver** (X-USB). In its control panel select **48 kHz**, buffer 512–1024.
3. Windows: **High performance** power plan, USB selective suspend **off**, sleep **never**.
4. Network: **wired Ethernet**, not Wi-Fi (needs ~25–35 Mbps upload). Check upload speed once.
5. Copy the `vibenation-sender` folder (the `.exe`, `ffmpeg.exe` and `sender.ini`) to the desktop.

## Every show
- Plug in the MR18, double-click **VibeNation Sender**. The window says *Sending 16 ch* when it's connected.
- The VibeNation app switches the mix to the venue feed automatically (header shows **VENUE**).
- If the network drops, the sender reconnects by itself; the app shows a red alert after 10 s.

## sender.ini
```ini
[sender]
server = show.jeeznews.com   ; the show server (or its IP)
port = 9000
device = X-AIR               ; part of the ASIO device name — run with --list to see names
channels = 16
latency_ms = 500             ; SRT re-send window: higher = more robust on bad networks
```

## Build the Windows program (once, on any Windows PC with Python 3.12)
Run `build.bat`. It installs the requirements, downloads a static `ffmpeg.exe` with SRT, and produces
`dist\vibenation-sender\` (a single folder to copy to the venue laptop).

## Test without the mixer
`python vibenation_sender.py --test-stems "C:\path\to\stems" --server <show server>` plays a Studio One stem
export (16 mono WAVs) in real time, exactly as if it came from the MR18.
