# VibeNation venue sender

## Tonight: set up in 15-30 minutes

You need: the venue laptop (Windows 10/11, 64-bit), the MR18 with its USB cable, a **wired** internet cable,
and the show server address (Claude gives it to you in VibeNation; it looks like `159.203.10.20`).

1. **Download** `vibenation-venue-sender.zip` from VibeNation → **Apps** → *Venue laptop (MR18)*.
   Right-click it → **Extract All…** → put the folder on the Desktop. (Do not run it from inside the zip.)
2. **Python 3.12** (skip if already installed): download
   https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe, run it, and on the first screen
   **tick "Add python.exe to PATH"** at the bottom, then click **Install Now**.
3. **MR18 driver** (skip if already installed): install the Behringer **X-USB / X AIR ASIO driver**
   from behringer.com (search "X-USB driver"). Restart the laptop if it asks.
   In **X AIR Edit**: In/Out → **USB Sends** → tap **Analog**. Sample rate **48 kHz**. Never touch preamp gain here.
4. **Plug in** the MR18 by USB and the laptop by network cable. Plug the laptop charger in.
5. In the folder, double-click **setup.bat**. If Windows says "Windows protected your PC", click
   **More info → Run anyway**. Wait (up to 20 minutes; it downloads ffmpeg, about 100 MB).
   You should see `[1/4]` … `[4/4]`, a list of sound cards with a line containing **X-AIR** or **X-USB**
   and **16 in** (or more), and **SETUP DONE**.
6. Open **sender.ini** (double-click, it opens in Notepad). Replace `SHOW-SERVER-IP` with the show server
   address. Leave everything else. Save (Ctrl+S) and close.
7. Double-click **run.bat**. Within ~10 seconds you should see
   **CONNECTED - sending 16 channels to the show server.** In VibeNation the header switches to **VENUE**.
   Leave the window open for the whole show (minimise it if you like). Closing it stops the sound.

**If it fails** (the window always stays open so you can read it):

| You see | Do this |
|---|---|
| `Python 3.12 is not installed, or not on PATH` | Do step 2 again; make sure "Add python.exe to PATH" is ticked. Then setup.bat again. |
| `No input with 16 channels matching 'X-AIR'` | MR18 not seen: check USB cable and power, install the driver (step 3), try another USB port, run setup.bat again. If the list shows the MR18 under another name, type part of that name after `device =` in sender.ini. |
| `Open sender.ini and replace SHOW-SERVER-IP` | Do step 6. |
| `No answer from the show server` | Check the address in sender.ini, the internet cable, and that the show server is on in VibeNation. It keeps retrying by itself. |
| `REFUSED: the passphrase ... does not match` | Ask Claude for the passphrase and paste it after `passphrase =` in sender.ini. |
| `Connection lost - retrying` | Internet dropped; it reconnects by itself. If it keeps happening, use the cable, not Wi-Fi. |
| `audio status: input overflow` now and then | The laptop is too busy: close other programs (Studio One recording is fine). |

Take a photo of the window and send it to Claude if anything else appears.

### What the setup does (for whoever helps)
- `setup.bat`: checks 64-bit Windows and Python 3.12, makes a private `.venv`, installs
  sounddevice 0.5.1 / soundfile 0.12.1 / numpy 2.1.3, downloads ffmpeg from gyan.dev (the *essentials*
  build includes libsrt; GitHub BtbN build as fallback) and checks it has SRT.
- `run.bat`: runs `vibenation_sender.py` with sender.ini; `run.bat --list` lists the sound cards.
- **ASIO**: sounddevice's Windows wheel ships a PortAudio with ASIO; the sender enables it
  (`SD_ENABLE_ASIO=1`) before import. It picks the device whose name matches `device =` (then X-AIR / X-USB /
  XR18 / MR18 / Behringer / Midas) with at least 16 inputs, preferring ASIO, then WASAPI, then WDM-KS. If the
  ASIO driver will not open, the X-USB driver's WDM/WASAPI multichannel device is used automatically (or set
  `device =` to its name from `run.bat --list`).
- The passphrase in sender.ini encrypts the audio (AES-128, SRT `pbkeylen=16`) and must match
  `VN_VENUE_PASSPHRASE` in the show server's `.env`. Without it the server refuses the connection.

## Reference

### One-time setup (laptop)
1. **MR18 / X AIR Edit** → In/Out → **USB Sends** → set the default signal tap to **Analog** (applies to all
   channels). On **USB Returns** keep "off analog". Sample rate **48 kHz**. *Never change preamp gain from here.*
2. Install the **Behringer X-AIR USB / ASIO driver** (X-USB). In its control panel select **48 kHz**, buffer 512–1024.
3. Windows: **High performance** power plan, USB selective suspend **off**, sleep **never**.
4. Network: **wired Ethernet**, not Wi-Fi (needs ~25–35 Mbps upload). Check upload speed once.
5. Copy the sender folder to the desktop (see *Tonight* above, or the `.exe` build below).

### Every show
- Plug in the MR18, double-click **run.bat**. The window says *CONNECTED* when it's sending.
- The VibeNation app switches the mix to the venue feed automatically (header shows **VENUE**).
- If the network drops, the sender reconnects by itself; the app shows a red alert after 10 s.

### sender.ini
```ini
[sender]
server = SHOW-SERVER-IP      ; the show server address
port = 9000
device = X-AIR               ; part of the ASIO device name — run with --list to see names
channels = 16
latency_ms = 500             ; SRT re-send window: higher = more robust on bad networks
passphrase = ...             ; = VN_VENUE_PASSPHRASE on the show server (10-79 chars); empty = unencrypted
```

### Build a single-folder .exe instead (optional) (once, on any Windows PC with Python 3.12)
Run `build.bat`. It installs the requirements, downloads a static `ffmpeg.exe` with SRT, and produces
`dist\vibenation-sender\` (a single folder to copy to the venue laptop).

### Test without the mixer
`python vibenation_sender.py --test-stems "C:\path\to\stems" --server <show server> --passphrase <passphrase>` plays a Studio One stem
export (16 mono WAVs) in real time, exactly as if it came from the MR18.
