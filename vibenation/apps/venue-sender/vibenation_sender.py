"""VibeNation venue sender: MR18 (USB, 16 channels, 48 kHz, raw "Analog" tap) -> SRT -> show server.

Runs on the venue laptop. It only captures and transmits - no processing - so the laptop
can be old. Audio leaves as uncompressed 24-bit PCM in Matroska over SRT (lost packets are
re-sent within the latency window). It reconnects forever and never needs a keyboard.

usage (Windows, from the packaged exe or with Python):
  vibenation_sender.exe                     # uses sender.ini next to the program
  vibenation_sender.exe --list              # list audio devices
  python vibenation_sender.py --test-file show.wav   # send a 16-channel WAV instead (testing)

sender.ini:
  [sender]
  server = show.jeeznews.com   ; or the show server's IP
  port = 9000
  device = X-AIR             ; part of the ASIO device name (MR18 shows as "X AIR ASIO Driver" / "XR18")
  channels = 16
  latency_ms = 500
  passphrase = ...           ; must match VN_VENUE_PASSPHRASE on the show server (10-79 chars)
"""

from __future__ import annotations

import argparse
import configparser
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

SR = 48000
BLOCK = 1024


def here(*p: str) -> str:
    base = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
    return os.path.join(base, *p)


def find_ffmpeg() -> str:
    local = here('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
    return local if os.path.exists(local) else (shutil.which('ffmpeg') or 'ffmpeg')


def srt_url(cfg: dict) -> str:
    url = f"srt://{cfg['server']}:{cfg['port']}?mode=caller&latency={int(cfg['latency_ms']) * 1000}&transtype=live&connect_timeout=5000"
    if cfg.get('passphrase'):
        url += f"&passphrase={cfg['passphrase']}&pbkeylen=16"
    return url


def start_ffmpeg(cfg: dict, channels: int) -> subprocess.Popen:
    """Raw float32 PCM on stdin -> 24-bit PCM in Matroska -> SRT."""
    return subprocess.Popen(
        [find_ffmpeg(), '-hide_banner', '-loglevel', 'warning', '-f', 'f32le', '-ar', str(SR), '-ac', str(channels), '-i', '-',
         '-c:a', 'pcm_s24le', '-f', 'matroska', '-live', '1', '-flush_packets', '1', srt_url(cfg)],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE,
    )


NO_ANSWER = ('No answer from the show server. Check: the address in sender.ini, the laptop internet, '
             'and that the show server is switched on in the VibeNation app.')
# ffmpeg/SRT messages -> plain words for whoever is watching the laptop.
FRIENDLY = [
    ('Incorrect passphrase', 'REFUSED: the passphrase in sender.ini does not match the show server.'),
    ('Password required', 'REFUSED: the show server needs a passphrase - put it in sender.ini.'),
    ('unexpected', 'REFUSED: the show server needs a passphrase - put it in sender.ini.'),
    ('Connection setup failure', NO_ANSWER),
    ('Failed to resolve', 'Cannot find the show server address in sender.ini. Check it for typos and check the internet.'),
    ('Name or service not known', 'Cannot find the show server address in sender.ini. Check it for typos and check the internet.'),
    ('No such host', 'Cannot find the show server address in sender.ini. Check it for typos and check the internet.'),
]
QUIET = ('Guessed Channel Layout', 'Error opening output', 'Input/output error', 'processAsyncConnectRequest', 'processConnectResponse')


def watch_ffmpeg(pipe, secret: str, state: dict) -> None:
    for raw in iter(pipe.readline, b''):
        line = raw.decode(errors='replace').strip()
        if secret:
            line = line.replace(secret, '***')
        line = re.sub(r'srt://\S+', 'srt://(show server)', line)
        msg = next((m for k, m in FRIENDLY if k.lower() in line.lower()), None)
        if msg:
            if msg != state.get('reason'):
                print(msg, flush=True)
            state['reason'] = msg
        elif line and not any(q in line for q in QUIET):
            print('ffmpeg:', line, flush=True)


def send_loop(cfg: dict, source) -> None:
    """source() yields float32 (BLOCK, channels) numpy arrays forever."""
    channels = int(cfg['channels'])
    state: dict = {}
    while True:
        print(f"Connecting to {cfg['server']}:{cfg['port']} ...", flush=True)
        try:
            ff = start_ffmpeg(cfg, channels)
        except OSError as e:
            print(f'Cannot start ffmpeg ({e}). Run setup.bat again.', flush=True)
            time.sleep(5)
            continue
        threading.Thread(target=watch_ffmpeg, args=(ff.stderr, cfg.get('passphrase', ''), state), daemon=True).start()
        sent = 0
        t0 = t_start = time.time()
        connected = False
        try:
            for block in source():
                ff.stdin.write(block.astype('<f4').tobytes())
                sent += len(block)
                if ff.poll() is not None:
                    break
                if not connected and time.time() - t_start > 7:  # still running past the 5 s connect timeout
                    connected = True
                    state.pop('reason', None)
                    print(f'CONNECTED - sending {channels} channels to the show server. Leave this window open.', flush=True)
                if time.time() - t0 > 30:
                    print(f"Sending {channels} ch - {sent / SR / (time.time() - t0) * 100:.0f}% realtime", flush=True)
                    sent, t0 = 0, time.time()
        except (BrokenPipeError, OSError):
            pass
        except Exception as e:  # e.g. the sound card vanished: say so and keep trying
            print(f'PROBLEM: {e}', flush=True)
            time.sleep(3)
        try:
            ff.kill()
        except OSError:
            pass
        time.sleep(0.3)  # let the error text arrive
        if not connected and not state.get('reason'):
            state['reason'] = NO_ANSWER
            print(NO_ANSWER, flush=True)
        print(('Connection lost' if connected else 'Could not connect') + ' - retrying in 2 s', flush=True)
        time.sleep(2)


def import_sd():
    """sounddevice with ASIO: its Windows wheel ships an ASIO-enabled PortAudio, used only if
    SD_ENABLE_ASIO is set before the import."""
    os.environ.setdefault('SD_ENABLE_ASIO', '1')
    import sounddevice as sd
    return sd


# Preferred Windows audio systems, best first. MME/DirectSound usually only offer 2 channels.
HOSTAPI_RANK = ['ASIO', 'Windows WASAPI', 'Windows WDM-KS', 'Windows DirectSound', 'MME']
# Names the MR18 / X-USB driver shows up under, tried after the device= setting.
MR18_NAMES = ['x-air', 'x air', 'x-usb', 'xusb', 'xr18', 'mr18', 'behringer', 'midas']


def pick_devices(sd, want: str, channels: int):
    """All inputs with enough channels whose name matches, best audio system first."""
    devs = sd.query_devices()
    apis = [a['name'] for a in sd.query_hostapis()]

    def rank(i: int) -> int:
        api = apis[devs[i]['hostapi']]
        return HOSTAPI_RANK.index(api) if api in HOSTAPI_RANK else len(HOSTAPI_RANK)

    names = [n for n in [want.lower().strip()] + MR18_NAMES if n]
    hits = [i for i, d in enumerate(devs) if d['max_input_channels'] >= channels and any(n in d['name'].lower() for n in names)]
    return sorted(hits, key=rank), apis


def list_devices() -> None:
    sd = import_sd()
    apis = [a['name'] for a in sd.query_hostapis()]
    print('Audio inputs (number  name  [audio system]  channels):')
    for i, d in enumerate(sd.query_devices()):
        if d['max_input_channels'] > 0:
            print(f"  {i:3d}  {d['name']}  [{apis[d['hostapi']]}]  {d['max_input_channels']} in")
    print('Audio systems available:', ', '.join(apis))


def device_source(cfg: dict):
    sd = import_sd()
    channels = int(cfg['channels'])
    cands, apis = pick_devices(sd, cfg['device'], channels)
    if not cands:
        list_devices()
        sys.exit(f"\nNo input with {channels} channels matching '{cfg['device']}'. Is the MR18 plugged in by USB and switched on, "
                 'and the X-USB driver installed? Then run this again.')
    q: queue.Queue = queue.Queue(maxsize=200)

    def cb(indata, frames, _t, status):
        if status:
            print('audio status:', status, flush=True)
        try:
            q.put_nowait(indata.copy())
        except queue.Full:
            pass  # network stalled: drop rather than block the audio thread

    def open_stream():
        # ASIO first; if that driver will not open (e.g. busy in another program), the X-USB
        # driver's WASAPI / WDM-KS multichannel device is the fallback.
        for dev in cands:
            d = sd.query_devices(dev)
            try:
                st = sd.InputStream(device=dev, channels=channels, samplerate=SR, blocksize=BLOCK, dtype='float32', callback=cb, latency='high')
                st.start()
                print(f"Capturing from: {d['name']} [{apis[d['hostapi']]}]", flush=True)
                return st
            except Exception as e:  # sd.PortAudioError and friends
                print(f"Could not open {d['name']} [{apis[d['hostapi']]}]: {e}", flush=True)
        raise RuntimeError('No MR18 audio device would open at 48 kHz. Close other audio programs, check the driver is at 48 kHz, replug the USB.')

    def gen():
        while not q.empty():  # stale audio from before a reconnect would only add delay
            q.get_nowait()
        st = open_stream()
        try:
            while True:
                yield q.get()
        finally:
            st.close()
    return gen


def file_source(path: str, cfg: dict):
    import numpy as np
    import soundfile as sf

    channels = int(cfg['channels'])

    def gen():
        while True:
            with sf.SoundFile(path) as f:
                t_next = time.time()
                while True:
                    x = f.read(BLOCK, dtype='float32', always_2d=True)
                    if len(x) < BLOCK:
                        break
                    if x.shape[1] < channels:
                        x = np.pad(x, ((0, 0), (0, channels - x.shape[1])))
                    yield x[:, :channels]
                    t_next += BLOCK / SR
                    time.sleep(max(0.0, t_next - time.time()))  # real time
    return gen


def stems_source(folder: str, cfg: dict, start_s: float = 0.0):
    """16 mono stems (the Studio One export) played in real time - for end-to-end tests."""
    import numpy as np
    import soundfile as sf
    names = ['KICK', 'SNARE', 'OVERHEAD', 'DI 1', 'GTR AMP', 'PIANO L', 'PIANO L 2', 'GTR DI', 'VOCAL CENTRE', 'VOCAL PIANO',
             'CONGOS', 'BASS', 'UTILITY 3', 'DI 2', 'SAXOPHONE', 'HARMONICA']

    def gen():
        files = [sf.SoundFile(os.path.join(folder, f'{n}.wav')) for n in names]
        for f in files:
            f.seek(int(start_s * SR))
        t_next = time.time()
        while True:
            x = np.stack([f.read(BLOCK, dtype='float32') for f in files], axis=1)
            if len(x) < BLOCK:
                for f in files:
                    f.seek(0)
                continue
            yield x
            t_next += BLOCK / SR
            time.sleep(max(0.0, t_next - time.time()))
    return gen


def main() -> None:
    ap = argparse.ArgumentParser(description='VibeNation venue sender')
    ap.add_argument('--list', action='store_true', help='list audio devices')
    ap.add_argument('--config', default=here('sender.ini'))
    ap.add_argument('--server')
    ap.add_argument('--port')
    ap.add_argument('--passphrase', help='override the passphrase in sender.ini')
    ap.add_argument('--test-file', help='send a multichannel WAV instead of the mixer')
    ap.add_argument('--test-stems', help='send a folder of 16 mono stems instead of the mixer')
    ap.add_argument('--start', type=float, default=0.0, help='start position (s) for --test-stems')
    args = ap.parse_args()

    if args.list:
        list_devices()
        return

    cp = configparser.ConfigParser(inline_comment_prefixes=(';', '#'))
    cp.read(args.config)
    cfg = {'server': 'app.jeeznews.com', 'port': '9000', 'device': 'X-AIR', 'channels': '16', 'latency_ms': '500', **(dict(cp['sender']) if cp.has_section('sender') else {})}
    if args.server:
        cfg['server'] = args.server
    if args.port:
        cfg['port'] = args.port
    if args.passphrase is not None:
        cfg['passphrase'] = args.passphrase
    cfg['passphrase'] = cfg.get('passphrase', '').strip().strip('"').strip("'")
    if not cfg['passphrase']:
        print('WARNING: no passphrase in sender.ini - the audio is sent UNENCRYPTED and the show server will refuse it if it has one.', flush=True)
    elif not 10 <= len(cfg['passphrase']) <= 79:
        sys.exit('The passphrase in sender.ini must be 10 to 79 characters long.')
    if cfg['server'].strip().upper() == 'SHOW-SERVER-IP':
        sys.exit('Open sender.ini and replace SHOW-SERVER-IP with the show server address (ask Claude in VibeNation for it).')
    src = stems_source(args.test_stems, cfg, args.start) if args.test_stems else file_source(args.test_file, cfg) if args.test_file else device_source(cfg)
    print('VibeNation venue sender - close this window to stop sending.', flush=True)
    threading.Thread(target=send_loop, args=(cfg, src), daemon=True).start()
    while True:
        time.sleep(3600)


if __name__ == '__main__':
    main()
