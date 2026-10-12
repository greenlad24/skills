"""Render a resolved timeline to MP4 with one ffmpeg process.

Video: every segment is trimmed/scaled/cropped/zoomed in ffmpeg, concatenated, then the
motion-graphics layer (rendered here frame by frame with Pillow) is streamed in as raw
RGBA over stdin and composited on top. Audio: clip sound + voice + ducked music (no sound effects).
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import numpy as np
from PIL import Image

from . import audio_io
from .anim import render_element
from .media import ffmpeg_exe, probe
from .timeline import FPS, Resolved

W, H = 1080, 1920


def _even(x: float) -> int:
    return int(round(x / 2)) * 2


def _video_chain(i: int, seg) -> str:
    f = [seg.pre] if seg.pre else []     # black bars off + upright first
    if seg.kind == "video":
        f.append(f"setpts=(PTS-STARTPTS)/{seg.speed:.4f}")
    f.append(f"fps={FPS}")
    eff = seg.effect
    zoom = {"punch_in": 1.15, "punch_shake": 1.15, "shake": 1.06}.get(eff, 1.0)
    f.append(f"scale={_even(W * zoom)}:{_even(H * zoom)}:force_original_aspect_ratio=increase")
    if eff in ("shake", "punch_shake"):
        f.append("crop=1080:1920:x='(iw-ow)/2+if(lt(t,0.32),20*sin(t*85)*(1-t/0.32),0)'"
                 ":y='(ih-oh)/2+if(lt(t,0.32),14*cos(t*70)*(1-t/0.32),0)'")
    else:
        f.append("crop=1080:1920")
    if eff == "slow_zoom":
        frames = max(1, int(seg.dur * FPS))
        f.append(f"zoompan=z='1+0.12*on/{frames}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps={FPS}")
    f.append(f"tpad=stop_mode=clone:stop_duration={seg.dur + 1:.3f}")
    f.append(f"trim=duration={seg.dur:.4f}")
    f.append("setpts=PTS-STARTPTS,format=yuv420p,setsar=1")
    return f"[{i}:v]" + ",".join(f) + f"[v{i}]"


def _audio_chain(i: int, seg) -> str:
    if seg.use_audio:
        f = ["asetpts=PTS-STARTPTS"]
        if abs(seg.speed - 1) > 0.01:
            f.append(f"atempo={seg.speed:.4f}")
        f += ["aresample=48000", "aformat=sample_fmts=fltp:channel_layouts=stereo", "apad",
              f"atrim=duration={seg.dur:.4f}", "asetpts=PTS-STARTPTS"]
        return f"[{i}:a]" + ",".join(f) + f"[a{i}]"
    return f"anullsrc=r=48000:cl=stereo,atrim=duration={seg.dur:.4f},aformat=sample_fmts=fltp[a{i}]"


def _inputs(seg) -> list:
    if seg.kind == "video":
        need = seg.dur * seg.speed + 0.5
        return ["-ss", f"{seg.src_in:.3f}", "-t", f"{need:.3f}", "-i", seg.path]
    if seg.kind == "image":
        return ["-loop", "1", "-framerate", str(FPS), "-t", f"{seg.dur + 0.5:.3f}", "-i", seg.path]
    return ["-f", "lavfi", "-i", f"color=c=0x1c1c1e:s=1080x1920:r={FPS}:d={seg.dur + 0.5:.3f}"]


def _composite(canvas: Image.Image, img: Image.Image, x: int, y: int) -> None:
    """alpha_composite with clipping (elements may hang off-canvas while animating)."""
    sx, sy = max(0, -x), max(0, -y)
    dx, dy = max(0, x), max(0, y)
    w = min(img.width - sx, W - dx)
    h = min(img.height - sy, H - dy)
    if w <= 0 or h <= 0:
        return
    if sx or sy or w < img.width or h < img.height:
        img = img.crop((sx, sy, sx + w, sy + h))
    canvas.alpha_composite(img, (dx, dy))


def overlay_frames(R: Resolved):
    """Yield raw RGBA bytes for every output frame.

    Elements that are not moving are composed once into a cached "static layer"; each
    frame only re-composites the animating elements on a copy of it.
    """
    n = int(round(R.total * FPS))
    blank = bytes(W * H * 4)
    els = R.elements
    static_key, static_img, static_bytes = None, None, blank
    for fi in range(n):
        t = fi / FPS
        active = [e for e in els if e.start <= t < e.end]
        if not active:
            yield blank
            continue
        stat = [e for e in active if e.is_static_at(t)]
        dyn = [e for e in active if not e.is_static_at(t)]
        key = tuple(id(e) for e in stat)
        if key != static_key:
            static_key = key
            static_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            for e in stat:
                r = render_element(e, t)
                if r:
                    _composite(static_img, *r)
            static_bytes = static_img.tobytes() if stat else blank
        if not dyn:
            yield static_bytes
            continue
        canvas = static_img.copy() if stat else Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for e in sorted(dyn, key=lambda el: el.z):
            r = render_element(e, t)
            if r:
                _composite(canvas, *r)
        yield canvas.tobytes()


def build_audio(R: Resolved, out_wav: Path) -> None:
    audio_io.write_wav(out_wav, R.speech)


def render(R: Resolved, out_path: Path, work_dir: Path, music: Path | None = None, settings: dict | None = None,
           progress=None, log=print) -> Path:
    settings = settings or {}
    work_dir.mkdir(parents=True, exist_ok=True)
    fx_wav = work_dir / (out_path.stem + "_voice.wav")
    build_audio(R, fx_wav)

    cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:2"]
    graph = []
    N = len(R.segments)
    for i, seg in enumerate(R.segments):
        cmd += _inputs(seg)
        graph.append(_video_chain(i, seg))
        if seg.use_audio and not probe(seg.path)["has_audio"]:
            seg.use_audio = False
        graph.append(_audio_chain(i, seg))
    ov_i, fx_i = N, N + 1
    cmd += ["-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "pipe:0"]
    cmd += ["-i", str(fx_wav)]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
    cat = "".join(f"[v{i}][a{i}]" for i in range(N))
    graph.append(f"{cat}concat=n={N}:v=1:a=1[bv][ba]")
    base = "bv"
    if R.progress_color:
        c = "0x%02X%02X%02X" % tuple(R.progress_color)
        graph.append(f"[bv]drawbox=x=0:y=145:w=iw:h=10:color=white@0.3:t=fill,"
                     f"drawbox=x=0:y=145:w='iw*t/{R.total:.3f}':h=10:color={c}:t=fill[bvp]")
        base = "bvp"
    graph.append(f"[{base}][{ov_i}:v]overlay=0:0:format=auto,format=yuv420p[vout]")
    graph.append(f"[{fx_i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[fx]")
    graph.append("[ba][fx]amix=inputs=2:normalize=0:duration=first[speech]")
    if music:
        mv = float(settings.get("music_volume", 0.14))
        graph.append(f"[{fx_i + 1}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={mv:.3f}[mus]")
        graph.append("[speech]asplit=2[sp1][sp2]")
        graph.append("[mus][sp2]sidechaincompress=threshold=0.02:ratio=8:attack=15:release=350[duck]")
        graph.append("[sp1][duck]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[aout]")
    else:
        graph.append("[speech]alimiter=limit=0.95[aout]")
    script = work_dir / (out_path.stem + "_graph.txt")
    script.write_text(";\n".join(graph), "utf-8")
    cmd += ["-filter_complex_script", str(script), "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", settings.get("render_preset", "veryfast"),
            "-crf", str(settings.get("render_crf", 20)), "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{R.total:.3f}", str(out_path)]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL)
    err_lines = []
    total_frames = max(1, int(round(R.total * FPS)))

    def read_err():
        for raw in proc.stderr:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("frame=") and progress:
                try:
                    progress(min(1.0, int(line[6:]) / total_frames))
                except ValueError:
                    pass
            elif line and "=" not in line[:20]:
                err_lines.append(line)
    th = threading.Thread(target=read_err, daemon=True)
    th.start()
    try:
        for frame in overlay_frames(R):
            proc.stdin.write(frame)
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    proc.wait()
    th.join(timeout=5)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + " | ".join(err_lines[-6:]))
    info = probe(out_path)
    if (info["width"], info["height"]) != (W, H):   # every video must be vertical 9:16
        raise RuntimeError(f"render came out {info['width']}x{info['height']} instead of {W}x{H}")
    return out_path
