"""Media/ML tool interfaces with DRY_RUN stubs + config-guarded real paths (§2B.2/§2B.5).

Each heavy dependency (yt-dlp, ffmpeg, Thonburian Whisper, Thai OCR, PySceneDetect) sits
behind a small Protocol so the pipeline is testable and never blocks on model downloads:

  * `get_media_tools()` returns STUB implementations unless `config.use_real_ml()` — the
    stubs are deterministic, network-free, and produce plausible Thai VO/OSD/scene data.
  * Real implementations lazy-import their dep inside the method so importing this module
    (and py_compile) works with none of them installed.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Protocol

from .. import config


# --------------------------------------------------------------------------- #
# Data shapes
# --------------------------------------------------------------------------- #
@dataclass
class VoSegment:
    t_start: float
    t_end: float
    text: str


@dataclass
class OsdEvent:
    t_start: float
    t_end: float
    text: str
    bbox: list[float] = field(default_factory=list)


@dataclass
class Scene:
    idx: int
    start: float
    end: float

    @property
    def dur(self) -> float:
        return round(self.end - self.start, 3)


def _seed(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:8], 16)


# --------------------------------------------------------------------------- #
# Protocols
# --------------------------------------------------------------------------- #
class VideoDownloader(Protocol):
    def download(self, url: str, tiktok_id: str) -> str: ...           # → local mp4 path


class Transcriber(Protocol):
    def transcribe(self, audio_or_video_path: str) -> list[VoSegment]: ...


class OcrEngine(Protocol):
    def read_frames(self, video_path: str, duration_s: float) -> list[OsdEvent]: ...


class SceneDetector(Protocol):
    def detect(self, video_path: str) -> list[Scene]: ...


# --------------------------------------------------------------------------- #
# Stubs (deterministic, network-free — DRY_RUN default)
# --------------------------------------------------------------------------- #
class StubDownloader:
    def download(self, url: str, tiktok_id: str) -> str:
        d = os.path.join(config.MEDIA_ROOT, config.SWIPE_VIDEO_DIR, tiktok_id)
        return os.path.join(d, "video.mp4")  # path only; no bytes written in stub


class StubTranscriber:
    """Canned Thai VO segments — a mini problem→demo→proof→CTA spoken track."""

    def transcribe(self, audio_or_video_path: str) -> list[VoSegment]:
        return [
            VoSegment(0.3, 3.2, "เมื่อก่อนหน้าฉันเป็นสิวหนักมาก"),
            VoSegment(3.2, 6.0, "จนได้ลองตัวนี้แล้วชีวิตเปลี่ยนไปเลย"),
            VoSegment(6.0, 12.0, "ทาแค่เช้าเย็นผิวก็ดูดีขึ้นจริง"),
            VoSegment(12.0, 18.0, "ใช้มา 7 วันเห็นผลชัดเจน หน้าใสขึ้นมาก"),
            VoSegment(18.0, 24.0, "ใครที่ผิวโทรมต้องลอง ปักตะกร้าเลย"),
        ]


class StubOcr:
    """Canned on-screen (OSD) Thai captions — hook + before/after + CTA."""

    def read_frames(self, video_path: str, duration_s: float) -> list[OsdEvent]:
        return [
            OsdEvent(0.0, 1.4, "ผิวโทรมมาก?", [0.1, 0.1, 0.9, 0.3]),
            OsdEvent(3.4, 6.0, "ก่อน / หลัง 7 วัน", [0.1, 0.7, 0.9, 0.9]),
            OsdEvent(18.0, 24.0, "ปักตะกร้า", [0.3, 0.8, 0.7, 0.95]),
        ]


class StubSceneDetector:
    """Deterministic pseudo-cut list derived from the video path hash."""

    def detect(self, video_path: str) -> list[Scene]:
        base = _seed(video_path) % 5  # 0..4 jitter
        bounds = [0.0, 1.5, 4.0 + base * 0.1, 9.0, 14.0, 20.0, 27.0 + base * 0.2]
        scenes = []
        for i in range(len(bounds) - 1):
            scenes.append(Scene(idx=i, start=round(bounds[i], 2), end=round(bounds[i + 1], 2)))
        return scenes


# --------------------------------------------------------------------------- #
# Real implementations (lazy imports; only used when config.use_real_ml())
# --------------------------------------------------------------------------- #
class YtDlpDownloader:
    def download(self, url: str, tiktok_id: str) -> str:
        import yt_dlp  # type: ignore

        out_dir = os.path.join(config.MEDIA_ROOT, config.SWIPE_VIDEO_DIR, tiktok_id)
        os.makedirs(out_dir, exist_ok=True)
        out_tmpl = os.path.join(out_dir, "video.%(ext)s")
        opts = {"outtmpl": out_tmpl, "format": "mp4/bestvideo+bestaudio", "quiet": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)


class ThonburianWhisper:
    """Thai-fine-tuned Whisper (biodatlab/whisper-th-medium-combined) via faster-whisper."""

    def __init__(self, model_name: str = "biodatlab/whisper-th-medium-combined") -> None:
        self.model_name = model_name

    def _extract_audio(self, video_path: str) -> str:
        import subprocess

        wav = os.path.splitext(video_path)[0] + ".16k.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-ac", "1", "-ar", "16000", wav],
            check=True, capture_output=True,
        )
        return wav

    def transcribe(self, audio_or_video_path: str) -> list[VoSegment]:
        from faster_whisper import WhisperModel  # type: ignore

        path = audio_or_video_path
        if not path.endswith(".wav"):
            path = self._extract_audio(path)
        model = WhisperModel(self.model_name)
        segments, _ = model.transcribe(path, language="th", word_timestamps=False)
        return [VoSegment(float(s.start), float(s.end), s.text.strip()) for s in segments]


class VisionOcr:
    """Thai-capable OCR over sampled frames. Concrete engine wiring is deployment-
    specific; this is the seam. Left to raise if invoked without a configured engine."""

    def read_frames(self, video_path: str, duration_s: float) -> list[OsdEvent]:
        raise NotImplementedError(
            "Configure a Thai OCR engine (e.g. easyocr/typhoon-ocr) before enabling real OCR."
        )


class PySceneDetectDetector:
    def detect(self, video_path: str) -> list[Scene]:
        from scenedetect import ContentDetector, detect  # type: ignore

        raw = detect(video_path, ContentDetector(threshold=27.0))
        return [
            Scene(idx=i, start=float(s.get_seconds()), end=float(e.get_seconds()))
            for i, (s, e) in enumerate(raw)
        ]


@dataclass
class MediaTools:
    downloader: VideoDownloader
    transcriber: Transcriber
    ocr: OcrEngine
    scenes: SceneDetector


def get_media_tools() -> MediaTools:
    """Real tools when `config.use_real_ml()`, else deterministic stubs."""
    if config.use_real_ml():
        return MediaTools(
            downloader=YtDlpDownloader(),
            transcriber=ThonburianWhisper(),
            ocr=VisionOcr(),
            scenes=PySceneDetectDetector(),
        )
    return MediaTools(
        downloader=StubDownloader(),
        transcriber=StubTranscriber(),
        ocr=StubOcr(),
        scenes=StubSceneDetector(),
    )
