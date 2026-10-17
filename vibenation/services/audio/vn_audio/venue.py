"""Receives the venue feed (16 channels from the MR18, sent by the venue laptop over SRT)
and plays it into JACK as client 'vn_venue', ready to replace the test recording.

ffmpeg listens on SRT (retransmission, ~500 ms latency window) and decodes to 32-bit
float PCM; a reader thread fills a buffer; the JACK callback takes one block at a time.
The MR18's clock and the server's clock drift apart (~50 ppm = half a second over three
hours), so a slow control loop nudges a libsamplerate ratio to keep the buffer at its
target fill — no clicks, no drift.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from collections import deque

import jack
import numpy as np
import samplerate

log = logging.getLogger('vn_audio.venue')
CHANNELS = 16
TARGET_FILL_S = 0.25  # buffer kept between network and JACK
REC_DIR = os.environ.get('VN_MULTITRACK_DIR', os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'multitrack'))
REC_FILE_S = 3600     # a new file every hour (and on every reconnect)
ENV_FILE = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')  # vibenation/.env (also /opt/vibenation/.env)


def venue_passphrase() -> str:
    """VN_VENUE_PASSPHRASE from the environment, else from vibenation/.env (the systemd unit has no EnvironmentFile)."""
    v = os.environ.get('VN_VENUE_PASSPHRASE', '').strip()
    if not v and os.path.exists(ENV_FILE):
        try:
            for line in open(ENV_FILE):
                k, _, val = line.strip().partition('=')
                if k.strip() == 'VN_VENUE_PASSPHRASE':
                    v = val.strip().strip('"').strip("'")
        except OSError:
            pass
    if v and not 10 <= len(v) <= 79:
        log.error('VN_VENUE_PASSPHRASE must be 10-79 characters; venue feed NOT encrypted')
        return ''
    return v


class Multitrack:
    """Records the raw venue feed (all 16 channels, exactly as received) so a show can be remixed
    afterwards: one mono 192 kb/s MP3 per channel (about 1.3 GB an hour for all 16), in a folder per
    take (venue-YYYYMMDD-HHMMSS/ch01-kick.mp3 ...). One ffmpeg encodes them all; a writer thread feeds
    it, so the live audio never waits on the disk."""

    NAMES = ('kick', 'snare', 'overheads', 'acoustic-di', 'guitar-amp', 'piano-l', 'piano-r', 'guitar-di',
             'vocal-centre', 'vocal-piano', 'congas-1', 'bass-di', 'congas-2', 'synth-bass', 'saxophone', 'harmonica')

    def __init__(self, sr: int, folder: str = REC_DIR):
        self.sr, self.folder = sr, folder
        self.q: deque = deque(maxlen=3000)  # ~60 s of 20 ms chunks if the disk stalls
        self.ev = threading.Event()
        self.proc: subprocess.Popen | None = None
        self.opened = 0.0
        self.path: str | None = None
        self.frames = 0
        self.error: str | None = None
        self.new_take = True
        threading.Thread(target=self._writer, name='multitrack', daemon=True).start()

    def push(self, x: np.ndarray) -> None:
        self.q.append(x)
        self.ev.set()

    def cut(self) -> None:
        """Next audio starts a new take (the feed dropped)."""
        self.new_take = True

    def _close(self) -> None:
        if self.proc is not None:
            try:
                self.proc.stdin.close()
                self.proc.wait(10)
            except Exception:  # noqa: BLE001
                self.proc.kill()
            self.proc = None

    def _open(self) -> None:
        self._close()
        self.path = os.path.join(self.folder, time.strftime('venue-%Y%m%d-%H%M%S'))
        os.makedirs(self.path, exist_ok=True)
        split = ''.join(f'[s{i}]' for i in range(CHANNELS))
        graph = f'[0:a]asplit={CHANNELS}{split};' + ';'.join(f'[s{i}]pan=mono|c0=c{i}[a{i}]' for i in range(CHANNELS))
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'f32le', '-ar', str(self.sr), '-ac', str(CHANNELS), '-i', '-',
               '-filter_complex', graph]
        for i in range(CHANNELS):
            cmd += ['-map', f'[a{i}]', '-c:a', 'libmp3lame', '-b:a', '192k', os.path.join(self.path, f'ch{i + 1:02d}-{self.NAMES[i]}.mp3')]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.opened = time.time()
        self.new_take = False
        log.info('multitrack: recording %s', self.path)

    def _writer(self) -> None:
        while True:
            self.ev.wait(1.0)
            self.ev.clear()
            while self.q:
                x = self.q.popleft()
                try:
                    if self.proc is None or self.proc.poll() is not None or self.new_take or time.time() - self.opened > REC_FILE_S:
                        self._open()
                    self.proc.stdin.write(np.ascontiguousarray(x, dtype=np.float32).tobytes())
                    self.frames += len(x)
                    self.error = None
                except Exception as e:  # noqa: BLE001 - a full disk must never touch the live audio
                    if self.error != str(e):
                        log.warning('multitrack: %s', e)
                    self.error = str(e)
                    self.proc = None

    def status(self) -> dict:
        return {'take': os.path.basename(self.path) if self.path else None, 'minutes': round(self.frames / self.sr / 60, 1), 'error': self.error}


class VenueReceiver:
    def __init__(self, port: int = 9000, latency_ms: int = 500, client_name: str = 'vn_venue', passphrase: str | None = None):
        self.port = port
        self.latency_ms = latency_ms
        self.passphrase = venue_passphrase() if passphrase is None else passphrase
        if not self.passphrase:
            log.warning('VN_VENUE_PASSPHRASE not set: venue feed on port %d is NOT encrypted and anyone can connect', port)
        self.client = jack.Client(client_name, no_start_server=True)
        self.sr = self.client.samplerate
        self.block = self.client.blocksize
        self.outs = [self.client.outports.register(f'out_{n}') for n in range(1, CHANNELS + 1)]
        self.buf: deque[np.ndarray] = deque()
        self.buffered = 0  # frames in self.buf
        self.lock = threading.Lock()
        self.ratio = 1.0
        self.resampler = samplerate.Resampler('sinc_fastest', channels=CHANNELS)
        self.connected = False
        self.last_data = 0.0
        self.underruns = 0
        self.sender: str | None = None
        self.rec = Multitrack(self.sr) if os.environ.get('VN_MULTITRACK', '1') != '0' else None
        self.client.set_process_callback(self._process)
        self.client.activate()
        threading.Thread(target=self._run, name='venue-srt', daemon=True).start()

    @property
    def port_names(self) -> list[str]:
        return [p.name for p in self.outs]

    def _process(self, frames: int) -> None:
        with self.lock:
            if self.buffered < frames:
                for p in self.outs:
                    p.get_array().fill(0)
                if self.connected:
                    self.underruns += 1
                return
            out = np.empty((frames, CHANNELS), dtype=np.float32)
            got = 0
            while got < frames:
                head = self.buf[0]
                take = min(frames - got, len(head))
                out[got:got + take] = head[:take]
                if take == len(head):
                    self.buf.popleft()
                else:
                    self.buf[0] = head[take:]
                got += take
            self.buffered -= frames
        for i, p in enumerate(self.outs):
            p.get_array()[:] = out[:, i]

    def _run(self) -> None:
        url = f'srt://0.0.0.0:{self.port}?mode=listener&latency={self.latency_ms * 1000}&transtype=live'
        if self.passphrase:  # a sender without (or with a wrong) passphrase is refused at the handshake
            url += f'&passphrase={self.passphrase}&pbkeylen=16'
        while True:
            proc = subprocess.Popen(
                ['ffmpeg', '-loglevel', 'error', '-probesize', '32', '-analyzeduration', '0', '-fflags', 'nobuffer', '-i', url, '-vn', '-f', 'f32le', '-ac', str(CHANNELS), '-ar', str(self.sr), '-'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            assert proc.stdout and proc.stderr
            threading.Thread(target=self._log_stderr, args=(proc.stderr,), daemon=True).start()
            chunk_bytes = 4 * CHANNELS * 960  # 20 ms
            while True:
                raw = proc.stdout.read(chunk_bytes)
                if not raw:
                    break
                x = np.frombuffer(raw, dtype=np.float32).reshape(-1, CHANNELS)
                if not self.connected:
                    log.info('venue feed connected')
                self.connected = True
                self.last_data = time.time()
                if self.rec is not None:
                    self.rec.push(x)
                self._push(x)
            proc.wait()
            if self.connected:
                log.warning('venue feed lost; listening again')
            if self.rec is not None:
                self.rec.cut()
            self.connected = False
            with self.lock:
                self.buf.clear()
                self.buffered = 0
            time.sleep(0.5)

    def _log_stderr(self, pipe) -> None:
        # ffmpeg echoes the SRT URL in its errors; keep the passphrase out of the logs.
        for line in iter(pipe.readline, b''):
            msg = line.decode(errors='replace').rstrip()
            if self.passphrase:
                msg = msg.replace(self.passphrase, '***')
            if msg:
                log.warning('venue ffmpeg: %s', msg)

    def _push(self, x: np.ndarray) -> None:
        # Drift control: steer the resample ratio so the buffer sits at TARGET_FILL_S.
        err = (self.buffered / self.sr) - TARGET_FILL_S
        self.ratio = float(np.clip(1.0 - err * 0.002, 0.9995, 1.0005))  # at most ±500 ppm
        y = self.resampler.process(x, self.ratio, end_of_input=False).astype(np.float32)
        with self.lock:
            self.buf.append(y)
            self.buffered += len(y)
            # A backlog (burst on connect, or after a network stall) would add delay that the
            # ±500 ppm drift loop needs ~25 min per second to remove: drop the oldest audio
            # down to the target in one go instead.
            excess = self.buffered - int(self.sr * TARGET_FILL_S)
            if excess > self.sr * 0.3:
                while excess > 0 and self.buf:
                    head = self.buf[0]
                    if len(head) <= excess:
                        self.buf.popleft()
                        excess -= len(head)
                        self.buffered -= len(head)
                    else:
                        self.buf[0] = head[excess:]
                        self.buffered -= excess
                        excess = 0

    def status(self) -> dict:
        return {
            'connected': self.connected and time.time() - self.last_data < 2,
            'bufferMs': round(self.buffered / self.sr * 1000),
            'driftPpm': round((self.ratio - 1.0) * 1e6),
            'underruns': self.underruns,
            'port': self.port,
            'encrypted': bool(self.passphrase),
            'recording': self.rec.status() if self.rec is not None else None,
        }
