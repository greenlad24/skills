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


class VenueReceiver:
    def __init__(self, port: int = 9000, latency_ms: int = 500, client_name: str = 'vn_venue'):
        self.port = port
        self.latency_ms = latency_ms
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
        while True:
            proc = subprocess.Popen(
                ['ffmpeg', '-loglevel', 'error', '-i', url, '-vn', '-f', 'f32le', '-ac', str(CHANNELS), '-ar', str(self.sr), '-'],
                stdout=subprocess.PIPE,
            )
            assert proc.stdout
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
                self._push(x)
            proc.wait()
            if self.connected:
                log.warning('venue feed lost; listening again')
            self.connected = False
            with self.lock:
                self.buf.clear()
                self.buffered = 0
            time.sleep(0.5)

    def _push(self, x: np.ndarray) -> None:
        # Drift control: steer the resample ratio so the buffer sits at TARGET_FILL_S.
        err = (self.buffered / self.sr) - TARGET_FILL_S
        self.ratio = float(np.clip(1.0 - err * 0.002, 0.9995, 1.0005))  # at most ±500 ppm
        y = self.resampler.process(x, self.ratio, end_of_input=False).astype(np.float32)
        with self.lock:
            if self.buffered > self.sr * 2:  # something stalled: drop the backlog
                self.buf.clear()
                self.buffered = 0
            self.buf.append(y)
            self.buffered += len(y)

    def status(self) -> dict:
        return {
            'connected': self.connected and time.time() - self.last_data < 2,
            'bufferMs': round(self.buffered / self.sr * 1000),
            'driftPpm': round((self.ratio - 1.0) * 1e6),
            'underruns': self.underruns,
            'port': self.port,
        }
