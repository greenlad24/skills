"""4A render — raw FFmpeg filtergraph builders (pure functions).

Every function here returns strings / arg-lists and touches no filesystem, so the
whole render command can be asserted in unit tests without invoking FFmpeg. The final
render is a *single* filtergraph (frame-accuracy + speed, §4A): per-source 9:16
normalization, hard-cut concat, per-shot VO re-slice/ramp, music-bed sidechain ducking,
and a trailing loudnorm to a -14 LUFS master.

Rules encoded here (do not regress):
  * hard cuts only — NO ``xfade`` / dissolves (§4A.7);
  * all branches end at exactly 1080x1920, SAR 1:1, 30 fps (§4A.5);
  * captions/disclosure use ``subtitles`` (libass), NEVER ``drawtext`` (§4B.5).
"""

from __future__ import annotations

from .config import CONFIG, EditingConfig
from .edl import atempo_chain, ramp_setpts_factor
from .types import EDL, Shot


# --------------------------------------------------------------------------- #
# Per-source 9:16 normalization (§4A.5)
# --------------------------------------------------------------------------- #
def crop_cover_chain(w: int, h: int) -> str:
    """Scale to COVER then center-crop the overflow (no bars)."""
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},setsar=1"
    )


def blurred_pad_chain(in_label: str, out_label: str, w: int, h: int) -> str:
    """Scale to FIT then pad with a blurred fill of the same clip (packshots)."""
    return (
        f"[{in_label}]split[{in_label}_main][{in_label}_bg];"
        f"[{in_label}_bg]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},boxblur=40:8[{in_label}_blur];"
        f"[{in_label}_main]scale={w}:{h}:force_original_aspect_ratio=decrease[{in_label}_fg];"
        f"[{in_label}_blur][{in_label}_fg]overlay=(W-w)/2:(H-h)/2,setsar=1[{out_label}]"
    )


def video_shot_chain(shot: Shot, cfg: EditingConfig) -> str:
    """Filtergraph fragment turning source ``[i:v]`` into a normalized ``[v{i}]``."""
    w, h, fps = cfg.render.width, cfg.render.height, cfg.render.fps
    i = shot.input_index
    trim = f"trim={shot.src_in_s}:{shot.src_out_s}"

    # setpts: payoff ramp scales PTS; plain shots just reset STARTPTS.
    if shot.ramp_factor and shot.ramp_factor != 1.0:
        factor = ramp_setpts_factor(shot.ramp_factor)
        setpts = f"setpts={factor:.6g}*(PTS-STARTPTS)"
    else:
        setpts = "setpts=PTS-STARTPTS"

    if shot.normalize == "blurred_pad":
        pre = f"[{i}:v]{trim},{setpts},fps={fps}[p{i}];"
        pad = blurred_pad_chain(f"p{i}", f"v{i}", w, h)
        return pre + pad
    # crop_cover
    return (
        f"[{i}:v]{trim},{setpts},"
        f"{crop_cover_chain(w, h)},fps={fps}[v{i}]"
    )


# --------------------------------------------------------------------------- #
# Hard-cut concat (§4A.7) — concat FILTER, not the demuxer
# --------------------------------------------------------------------------- #
def concat_video(n: int, out_label: str = "vraw") -> str:
    labels = "".join(f"[v{i}]" for i in range(n))
    return f"{labels}concat=n={n}:v=1:a=0[{out_label}]"


# --------------------------------------------------------------------------- #
# Audio EDL: re-slice the clean VO per shot in shipped order, ramp, concat (§4A.1)
# --------------------------------------------------------------------------- #
def audio_shot_chain(shot: Shot, vo_input: int, seq: int) -> str:
    """Slice ``[vo_input:a]`` to this shot's VO span; ramp tempo to match a video ramp."""
    start = shot.vo_start_ms / 1000.0
    end = shot.vo_end_ms / 1000.0
    chain = f"[{vo_input}:a]atrim={start:.4f}:{end:.4f},asetpts=PTS-STARTPTS"
    if shot.ramp_factor and shot.ramp_factor != 1.0:
        for f in atempo_chain(shot.ramp_factor):
            chain += f",atempo={f:.6g}"
    return f"{chain}[a{seq}]"


def concat_audio(n: int, out_label: str = "voraw") -> str:
    labels = "".join(f"[a{i}]" for i in range(n))
    return f"{labels}concat=n={n}:v=0:a=1[{out_label}]"


# --------------------------------------------------------------------------- #
# Music bed + VO sidechain ducking + loudnorm master (§4A.6 / §4A.8)
# --------------------------------------------------------------------------- #
def music_duck_chain(
    music_input: int,
    vo_label: str,
    total_s: float,
    cfg: EditingConfig,
    out_label: str = "aout",
) -> str:
    """Bed at -13 dBFS idle, ducked ~-24 dBFS under speech; master to -14 LUFS."""
    r = cfg.render
    return (
        f"[{music_input}:a]volume=0.22,aloop=loop=-1:size=2e9,"
        f"atrim=0:{total_s:.4f}[bed];"
        f"[bed][{vo_label}]sidechaincompress="
        f"threshold=0.03:ratio=8:attack=5:release=250:makeup=1[duck];"
        f"[duck][{vo_label}]amix=inputs=2:duration=first:weights=1 1,"
        f"dynaudnorm=f=200:g=5,"
        f"loudnorm=I={r.target_lufs}:TP={r.true_peak_dbtp}:LRA={r.lra}[{out_label}]"
    )


def vo_only_master_chain(vo_label: str, cfg: EditingConfig, out_label: str = "aout") -> str:
    """No music bed: normalize the VO straight to the loudness master."""
    r = cfg.render
    return (
        f"[{vo_label}]dynaudnorm=f=200:g=5,"
        f"loudnorm=I={r.target_lufs}:TP={r.true_peak_dbtp}:LRA={r.lra}[{out_label}]"
    )


# --------------------------------------------------------------------------- #
# Whole filtergraph + full ffmpeg command (§4A.8)
# --------------------------------------------------------------------------- #
def build_filter_complex(
    edl: EDL,
    cfg: EditingConfig = CONFIG,
    disclosure_ass: str | None = None,
) -> tuple[str, list[str]]:
    """Return ``(filter_complex, ordered_input_paths)`` for the cut render.

    Inputs are ordered: one per shot (video), then the clean VO, then optional music.
    ``disclosure_ass`` (path) burns the AI-disclosure into the base via libass when the
    module is configured with ``disclosure.in_base = True`` (§4C) — Thai-correct, unlike
    a drawtext plate.
    """
    n = edl.shot_count
    parts: list[str] = []
    inputs: list[str] = [s.source_path for s in edl.shots]

    # --- video: normalize each shot, then hard-cut concat ---
    for shot in edl.shots:
        parts.append(video_shot_chain(shot, cfg))
    parts.append(concat_video(n, "vraw"))

    # video tail: optional disclosure (libass) + pixel format
    vlast = "vraw"
    if disclosure_ass and cfg.disclosure.in_base:
        parts.append(
            f"[vraw]subtitles={_escape_ass_path(disclosure_ass)}"
            f":fontsdir={cfg.caption.fontsdir}[vdisc]"
        )
        vlast = "vdisc"
    parts.append(f"[{vlast}]format={cfg.render.pix_fmt}[vout]")

    # --- audio: VO input index = n, music = n+1 (if present) ---
    vo_input = n
    inputs.append(edl.vo_path)
    for seq, shot in enumerate(edl.shots):
        parts.append(audio_shot_chain(shot, vo_input, seq))
    parts.append(concat_audio(n, "voraw"))

    total_s = edl.total_duration_s()
    if edl.music_path:
        music_input = n + 1
        inputs.append(edl.music_path)
        parts.append(music_duck_chain(music_input, "voraw", total_s, cfg, "aout"))
    else:
        parts.append(vo_only_master_chain("voraw", cfg, "aout"))

    return ";\n".join(parts), inputs


def build_cut_command(
    edl: EDL,
    out_path: str,
    cfg: EditingConfig = CONFIG,
    disclosure_ass: str | None = None,
) -> list[str]:
    """Full ``ffmpeg`` argv for ``output/final.mp4`` (§4A.8)."""
    filter_complex, inputs = build_filter_complex(edl, cfg, disclosure_ass)
    r = cfg.render

    args: list[str] = ["ffmpeg", "-y"]
    for p in inputs:
        args += ["-i", p]
    args += ["-filter_complex", filter_complex]
    args += ["-map", "[vout]", "-map", "[aout]"]
    args += [
        "-r", str(r.fps),
        "-c:v", r.vcodec, "-preset", r.preset, "-crf", str(r.crf),
        "-profile:v", r.profile, "-pix_fmt", r.pix_fmt,
        "-colorspace", r.color, "-color_primaries", r.color, "-color_trc", r.color,
        "-c:a", r.acodec, "-b:a", r.abitrate,
    ]
    if r.deterministic_threads:
        # Pin threads for deterministic, bit-exact re-render (§4D.2 / T-9).
        args += ["-threads", str(r.deterministic_threads),
                 "-x264-params", f"threads={r.deterministic_threads}"]
    if r.faststart:
        args += ["-movflags", "+faststart"]
    args.append(out_path)
    return args


def build_burn_command(
    base_path: str,
    ass_path: str,
    out_path: str,
    cfg: EditingConfig = CONFIG,
) -> list[str]:
    """Second-pass burn of ``captions.ass`` over ``final.mp4`` (§4B.5).

    Uses ``subtitles=`` (libass) — NOT drawtext — and ``-c:a copy`` so re-captioning
    never re-encodes audio, and the cut is not fully re-rendered.
    """
    r = cfg.render
    vf = (
        f"subtitles={_escape_ass_path(ass_path)}"
        f":fontsdir={cfg.caption.fontsdir}"
    )
    args = [
        "ffmpeg", "-y", "-i", base_path,
        "-vf", vf,
        "-c:v", r.vcodec, "-preset", r.preset, "-crf", str(r.crf),
        "-pix_fmt", r.pix_fmt,
        "-c:a", "copy",
    ]
    if r.faststart:
        args += ["-movflags", "+faststart"]
    args.append(out_path)
    return args


def _escape_ass_path(path: str) -> str:
    """Escape a path for use inside an ffmpeg filter value (``subtitles=``)."""
    # Backslashes, colons and single quotes are special in the filter mini-language.
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
