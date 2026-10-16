"""Plays a 16-channel show recording into JACK as if it were the venue feed.

Used for testing and rehearsals until the venue sender (SRT from the MR18) is live.
A reader thread streams blocks from the 16 mono WAVs into a queue; the JACK process
callback only copies ready-made blocks, so disk reads never block audio.
"""

from __future__ import annotations

import os
import queue
import threading
import time

import jack
import numpy as np
import soundfile as sf

# MR18 channel order -> file stem in the Studio One export.
CHANNEL_FILES = {
    1: 'KICK', 2: 'SNARE', 3: 'OVERHEAD', 4: 'DI 1', 5: 'GTR AMP', 6: 'PIANO L', 7: 'PIANO L 2',
    8: 'GTR DI', 9: 'VOCAL CENTRE', 10: 'VOCAL PIANO', 11: 'CONGOS', 12: 'BASS', 13: 'UTILITY 3',
    14: 'DI 2', 15: 'SAXOPHONE', 16: 'HARMONICA',
}


def find_sets(folder: str) -> dict[str, dict[int, str]]:
    """Return {'Set 1': {ch: path}, 'Set 2': {...}} for files named NAME.wav / NAME(2).wav."""
    sets: dict[str, dict[int, str]] = {}
    for suffix, label in (('', 'Set 1'), ('(2)', 'Set 2'), ('(3)', 'Set 3')):
        files = {ch: os.path.join(folder, f'{stem}{suffix}.wav') for ch, stem in CHANNEL_FILES.items()}
        if all(os.path.exists(p) for p in files.values()):
            sets[label] = files
    return sets


class StemPlayer:
    def __init__(self, folder: str, client_name: str = 'vn_player'):
        self.folder = folder
        self.sets = find_sets(folder)
        self.set_name = next(iter(self.sets), None)
        self.client = jack.Client(client_name, no_start_server=True)
        self.block = self.client.blocksize
        self.outs = [self.client.outports.register(f'out_{n}') for n in range(1, 17)]
        self.q: queue.Queue[np.ndarray] = queue.Queue(maxsize=int(2 * self.client.samplerate / self.block))
        self.playing = False
        self.position = 0  # frames read from disk
        self.length = 0
        self.played = 0  # frames sent to JACK
        self._seek: int | None = 0
        self._lock = threading.Lock()
        self._files: list[sf.SoundFile] = []
        self.client.set_process_callback(self._process)
        threading.Thread(target=self._reader, name='stem-reader', daemon=True).start()
        self.client.activate()

    @property
    def port_names(self) -> list[str]:
        return [p.name for p in self.outs]

    # JACK thread: copy one block or output silence.
    def _process(self, frames: int) -> None:
        blk = None
        if self.playing:
            try:
                blk = self.q.get_nowait()
            except queue.Empty:
                blk = None
        if blk is None or blk.shape[0] != frames:
            for p in self.outs:
                p.get_array().fill(0)
            return
        for i, p in enumerate(self.outs):
            p.get_array()[:] = blk[:, i]
        self.played += frames

    def _open(self) -> None:
        for f in self._files:
            f.close()
        files = self.sets.get(self.set_name or '', {})
        self._files = [sf.SoundFile(files[n]) for n in range(1, 17)] if files else []
        self.length = min((f.frames for f in self._files), default=0)

    def _reader(self) -> None:
        while True:
            with self._lock:
                seek = self._seek
                self._seek = None
            if seek is not None:
                self._open()
                while not self.q.empty():
                    self.q.get_nowait()
                for f in self._files:
                    f.seek(min(seek, self.length))
                self.position = self.played = min(seek, self.length)
            if not self._files or self.position >= self.length:
                if self._files and self.position >= self.length:
                    self.seek(0)  # loop the set
                time.sleep(0.05)
                continue
            n = self.block * 8
            data = np.zeros((n, 16), dtype=np.float32)
            got = n
            for i, f in enumerate(self._files):
                chunk = f.read(n, dtype='float32', always_2d=False)
                got = min(got, len(chunk))
                data[: len(chunk), i] = chunk
            self.position += got
            for k in range(0, got - self.block + 1, self.block):
                self.q.put(data[k : k + self.block].copy())  # blocks when ~2 s are buffered

    # ---------- control ----------

    def play(self) -> None:
        self.playing = True

    def pause(self) -> None:
        self.playing = False

    def seek(self, frame: int) -> None:
        with self._lock:
            self._seek = max(0, int(frame))

    def load(self, set_name: str) -> None:
        if set_name in self.sets:
            self.set_name = set_name
            self.seek(0)

    def status(self) -> dict:
        sr = self.client.samplerate
        return {
            'source': 'recording',
            'name': os.path.basename(self.folder.rstrip('/')),
            'sets': list(self.sets),
            'set': self.set_name,
            'playing': self.playing,
            'position': round(self.played / sr, 1),
            'length': round(self.length / sr, 1),
        }
