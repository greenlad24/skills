"""4A — the viral re-cut *planning* engine (pure, testable).

MoviePy-style bookkeeping that computes an EDL: hook-first ordering, librosa beat
detection + cut-sync (BPM->frames), PacingTemplate fitting (sub-2.5s hard ceiling),
payoff speed-ramps, and 9:16 normalization mode selection. The *render* is a raw
FFmpeg filtergraph (see ``filtergraph.py`` / ``render.py``); this module only decides
frame-exact cut boundaries.

librosa / auto-editor are imported lazily inside the functions that need them so the
math (which is the load-bearing, tested part) imports with zero heavy deps.
"""

from __future__ import annotations

from .types import EDL, JobSpec, NormalizeMode, SceneSpec, Shot

DEFAULT_BPM = 100.0


# --------------------------------------------------------------------------- #
# 1. Hook-first ordering (§4A.1)
# --------------------------------------------------------------------------- #
def hook_first(scenes: list[SceneSpec]) -> list[SceneSpec]:
    """Promote the single ``is_hook`` scene to position 0; preserve the rest's order.

    Invariant (validated upstream by ``validate_scenes``): exactly one hook.
    """
    hook = next(s for s in scenes if s.is_hook)
    rest = [s for s in scenes if not s.is_hook]
    return [hook, *rest]


def validate_scenes(scenes: list[SceneSpec]) -> None:
    """Enforce the §4D.4 pre-render invariants. Raises ValueError on violation."""
    if not scenes:
        raise ValueError("no scenes to render")
    hooks = [s for s in scenes if s.is_hook]
    if len(hooks) != 1:
        raise ValueError(
            f"exactly one is_hook scene required, found {len(hooks)} "
            f"(scene ids: {[s.id for s in hooks]})"
        )


# --------------------------------------------------------------------------- #
# 2. Beat detection + cut-sync (§4A.2) — the BPM->frames math
# --------------------------------------------------------------------------- #
def frames_per_beat(bpm: float, fps: int = 30) -> float:
    """seconds_per_beat = 60/bpm; frames_per_beat = fps * 60 / bpm."""
    if bpm <= 0:
        raise ValueError("bpm must be > 0")
    return fps * 60.0 / bpm


def synth_beat_grid(bpm: float, n: int, fps: int = 30) -> list[float]:
    """Synthesize an even beat grid (used when there is no music bed, §4A.2)."""
    spb = 60.0 / bpm
    return [k * spb for k in range(max(1, n))]


def detect_beats(
    music_path: str | None,
    bpm_hint: float | None,
    approx_duration_s: float,
    fps: int = 30,
) -> tuple[float, list[float]]:
    """Return ``(bpm, beat_times)``.

    With a music bed, use ``librosa.beat.beat_track``. Without one (or on empty/short
    detection, §4D.4), synthesize a grid from ``bpm_hint`` (or ``DEFAULT_BPM``).
    """
    if music_path:
        try:
            import librosa  # lazy: heavy dep, only needed for real renders

            y, sr = librosa.load(music_path, sr=44100, mono=True)
            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
            beat_times = librosa.frames_to_time(beat_frames, sr=sr)
            beat_list = [float(t) for t in beat_times]
            bpm = float(tempo)
            if beat_list:  # non-empty detection wins
                return bpm, beat_list
        except Exception:  # noqa: BLE001 — fall back to a synthetic grid (§4D.4)
            pass

    bpm = float(bpm_hint or DEFAULT_BPM)
    n = max(1, int(approx_duration_s / (60.0 / bpm)) + 2)
    return bpm, synth_beat_grid(bpm, n, fps)


def snap_to_beat_frame(cut_time_s: float, beat_times: list[float], fps: int = 30) -> int:
    """Nearest beat, then quantize to an integer video frame (§4A.2).

    Cut boundaries are stored as *frame indices* so FFmpeg trims are frame-exact.
    """
    if not beat_times:
        return round(cut_time_s * fps)
    nearest_beat_s = min(beat_times, key=lambda b: abs(b - cut_time_s))
    return round(nearest_beat_s * fps)


# --------------------------------------------------------------------------- #
# 3. Apply the PacingTemplate (§4A.3)
# --------------------------------------------------------------------------- #
def _frame_deltas_to_ms(frames: list[int], fps: int = 30) -> list[float]:
    """Per-shot durations (ms) from cumulative out-point frame indices."""
    out: list[float] = []
    prev = 0
    for f in frames:
        out.append((f - prev) * 1000.0 / fps)
        prev = f
    return out


def _cumulative_frames_from_ms(durations_ms: list[float], fps: int = 30) -> list[int]:
    frames: list[int] = []
    acc_ms = 0.0
    for d in durations_ms:
        acc_ms += d
        frames.append(round(acc_ms / 1000.0 * fps))
    return frames


def fit_pacing(
    n_shots: int,
    per_shot_ms: list[int],
    beat_times: list[float],
    max_avg_cut_ms: int = 2500,
    fps: int = 30,
) -> list[int]:
    """Distribute shot slots, snap each boundary to a beat frame, enforce sub-2.5s avg.

    Returns cumulative *out-point* frame indices (one per shot). Acceptance (§4A.3 /
    T-2): ``mean(per_shot_duration) < max_avg_cut_ms``.
    """
    if n_shots <= 0:
        return []
    # Take/repeat per_shot_ms up to n_shots (default to the avg ceiling if too short).
    targets = list(per_shot_ms[:n_shots])
    if len(targets) < n_shots:
        fill = per_shot_ms[-1] if per_shot_ms else max_avg_cut_ms
        targets += [fill] * (n_shots - len(targets))

    frames = [
        snap_to_beat_frame(sum(targets[: i + 1]) / 1000.0, beat_times, fps)
        for i in range(n_shots)
    ]
    frames = _monotonic(frames, fps)
    durations_ms = _frame_deltas_to_ms(frames, fps)
    avg = sum(durations_ms) / len(durations_ms)

    if avg > max_avg_cut_ms:
        scale = max_avg_cut_ms / avg
        # Scale below the ceiling with a safety margin, then re-snap to beats.
        durations_ms = [d * scale * 0.98 for d in durations_ms]
        frames = _cumulative_frames_from_ms(durations_ms, fps)
        frames = [snap_to_beat_frame(f / fps, beat_times, fps) for f in frames]
        frames = _monotonic(frames, fps)
        # If snapping pushed the average back to/over the ceiling (coarse beat grids
        # quantize to multiples that can re-inflate the mean), fall back to the unsnapped
        # scaled grid (still frame-aligned) so acceptance T-2 (mean < ceiling) holds.
        if sum(_frame_deltas_to_ms(frames, fps)) / len(frames) >= max_avg_cut_ms:
            frames = _cumulative_frames_from_ms(durations_ms, fps)
            frames = _monotonic(frames, fps)
    return frames


def _monotonic(frames: list[int], fps: int) -> list[int]:
    """Ensure strictly increasing out-points (min 1 frame per shot)."""
    out: list[int] = []
    prev = 0
    for f in frames:
        f = max(f, prev + 1)
        out.append(f)
        prev = f
    return out


# --------------------------------------------------------------------------- #
# 4. Speed ramps on payoff moments (§4A.4)
# --------------------------------------------------------------------------- #
def ramp_setpts_factor(ramp_factor: float) -> float:
    """Video PTS multiplier for a speed-up of ``ramp_factor`` (e.g. 1.6x -> 0.625)."""
    if ramp_factor <= 0:
        raise ValueError("ramp_factor must be > 0")
    return 1.0 / ramp_factor


def atempo_chain(ramp_factor: float) -> list[float]:
    """Decompose a tempo change into a chain of atempo factors each within [0.5, 2.0].

    A single ``atempo`` accepts 0.5–2.0; factor 3.2 -> [2.0, 1.6] (§4A.4).
    """
    if ramp_factor <= 0:
        raise ValueError("ramp_factor must be > 0")
    factors: list[float] = []
    remaining = ramp_factor
    # speed-ups
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    # slow-downs
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    factors.append(round(remaining, 6))
    return factors


# --------------------------------------------------------------------------- #
# 5. 9:16 normalization mode selection (§4A.5)
# --------------------------------------------------------------------------- #
def normalize_mode(scene: SceneSpec) -> NormalizeMode:
    """crop-cover for avatar + lifestyle B-roll; blurred-pad for ``no_crop`` packshots."""
    return "blurred_pad" if scene.no_crop else "crop_cover"


# --------------------------------------------------------------------------- #
# Assemble the EDL (§4A.1–4A.5)
# --------------------------------------------------------------------------- #
def build_edl(job: JobSpec) -> EDL:
    """Hook-first reorder -> beat detect -> pacing fit -> payoff ramps -> normalize.

    Produces a frame-exact ``EDL``; the audio EDL mirrors the video EDL (each shot
    carries its clean-VO slice ``vo_start_ms/vo_end_ms``).
    """
    validate_scenes(job.scenes)
    ordered = hook_first(job.scenes)
    fps = job.fps

    # Approx pre-fit duration (sum of per-shot template slots) drives the beat grid length.
    approx_ms = sum(job.pacing.per_shot_ms[: len(ordered)]) or (len(ordered) * 2000)
    bpm, beat_times = detect_beats(
        job.music_path, job.pacing.bpm_hint, approx_ms / 1000.0, fps
    )

    out_frames = fit_pacing(
        len(ordered),
        job.pacing.per_shot_ms,
        beat_times,
        job.pacing.max_avg_cut_ms,
        fps,
    )

    shots: list[Shot] = []
    prev_frame = 0
    for i, (scene, out_f) in enumerate(zip(ordered, out_frames)):
        ramp = job.pacing.ramp_factor if scene.is_payoff else 1.0
        if scene.is_payoff:
            # A ramped shot plays faster -> occupies fewer timeline frames. Recompute
            # its out-point and re-snap to the next beat frame (§4A.4).
            timeline_frames = round((out_f - prev_frame) / ramp)
            out_f = snap_to_beat_frame(
                (prev_frame + timeline_frames) / fps, beat_times, fps
            )
            out_f = max(out_f, prev_frame + 1)

        timeline_dur_frames = out_f - prev_frame
        # Source seconds consumed = timeline seconds * ramp (faster shot eats more source).
        src_dur_s = (timeline_dur_frames / fps) * ramp
        shots.append(
            Shot(
                scene_id=scene.id,
                input_index=i,
                source_path=scene.asset_path,
                kind=scene.kind,
                normalize=normalize_mode(scene),
                is_hook=scene.is_hook,
                is_payoff=scene.is_payoff,
                start_frame=prev_frame,
                end_frame=out_f,
                src_in_s=0.0,
                src_out_s=round(src_dur_s, 4),
                vo_start_ms=scene.vo_start_ms,
                vo_end_ms=scene.vo_end_ms,
                ramp_factor=ramp,
            )
        )
        prev_frame = out_f

    return EDL(
        job_id=job.id,
        fps=fps,
        shots=shots,
        bpm=bpm,
        beat_times=beat_times,
        music_path=job.music_path,
        vo_path=job.vo_path,
    )
