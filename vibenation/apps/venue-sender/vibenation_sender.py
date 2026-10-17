"""VibeNation venue sender: MR18 (USB, 16 channels, 48 kHz, raw "Analog" tap) -> SRT -> show server.

Runs on the venue laptop. It only captures and transmits — no processing — so the laptop
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
"""

from __future__ import annotations

import argparse
import configparser
import os
import queue
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
    return f"srt://{cfg['server']}:{cfg['port']}?mode=caller&latency={int(cfg['latency_ms']) * 1000}&transtype=live&connect_timeout=5000"


def start_ffmpeg(cfg: dict, channels: int) -> subprocess.Popen:
    """Raw float32 PCM on stdin -> 24-bit PCM in Matroska -> SRT."""
    return subprocess.Popen(
        [find_ffmpeg(), '-hide_banner', '-loglevel', 'warning', '-f', 'f32le', '-ar', str(SR), '-ac', str(channels), '-i', '-',
         '-c:a', 'pcm_s24le', '-f', 'matroska', '-live', '1', '-flush_packets', '1', srt_url(cfg)],
        stdin=subprocess.PIPE,
    )


def send_loop(cfg: dict, source) -> None:
    """source() yields float32 (BLOCK, channels) numpy arrays forever."""
    channels = int(cfg['channels'])
    while True:
        print(f"Connecting to {cfg['server']}:{cfg['port']} …", flush=True)
        ff = start_ffmpeg(cfg, channels)
        sent = 0
        t0 = time.time()
        try:
            for block in source():
                ff.stdin.write(block.astype('<f4').tobytes())
                sent += len(block)
                if time.time() - t0 > 10:
                    print(f"Sending {channels} ch · {sent / SR / (time.time() - t0) * 100:.0f}% realtime", flush=True)
                    sent, t0 = 0, time.time()
                if ff.poll() is not None:
                    break
        except (BrokenPipeError, OSError):
            pass
        try:
            ff.kill()
        except OSError:
            pass
        print('Connection lost — retrying in 2 s', flush=True)
        time.sleep(2)


def device_source(cfg: dict):
    import numpy as np
    import sounddevice as sd

    channels = int(cfg['channels'])
    want = cfg['device'].lower()
    dev = next((i for i, d in enumerate(sd.query_devices()) if want in d['name'].lower() and d['max_input_channels'] >= channels), None)
    if dev is None:
        sys.exit(f"No input device matching '{cfg['device']}' with {channels} channels. Run with --list.")
    print(f"Capturing from: {sd.query_devices(dev)['name']}", flush=True)
    q: queue.Queue = queue.Queue(maxsize=200)

    def cb(indata, frames, _t, status):
        if status:
            print('audio status:', status, flush=True)
        try:
            q.put_nowait(indata.copy())
        except queue.Full:
            pass  # network stalled: drop rather than block the audio thread

    def gen():
        with sd.InputStream(device=dev, channels=channels, samplerate=SR, blocksize=BLOCK, dtype='float32', callback=cb, latency='high'):
            while True:
                yield q.get()
    _ = np
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
    """16 mono stems (the Studio One export) played in real time — for end-to-end tests."""
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
    ap.add_argument('--test-file', help='send a multichannel WAV instead of the mixer')
    ap.add_argument('--test-stems', help='send a folder of 16 mono stems instead of the mixer')
    ap.add_argument('--start', type=float, default=0.0, help='start position (s) for --test-stems')
    args = ap.parse_args()

    if args.list:
        import sounddevice as sd
        print(sd.query_devices())
        return

    cp = configparser.ConfigParser(inline_comment_prefixes=(';', '#'))
    cp.read(args.config)
    cfg = {'server': 'app.jeeznews.com', 'port': '9000', 'device': 'X-AIR', 'channels': '16', 'latency_ms': '500', **(dict(cp['sender']) if cp.has_section('sender') else {})}
    if args.server:
        cfg['server'] = args.server
    src = stems_source(args.test_stems, cfg, args.start) if args.test_stems else file_source(args.test_file, cfg) if args.test_file else device_source(cfg)
    print('VibeNation venue sender — close this window to stop sending.', flush=True)
    threading.Thread(target=send_loop, args=(cfg, src), daemon=True).start()
    while True:
        time.sleep(3600)


if __name__ == '__main__':
    main()
