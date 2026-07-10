"""
OBS AutoDirector — an automatic scene director for OBS Studio.

One job, done well: switch between your OBS scenes the way a human director
would, driven by what it hears on your audio sources.

Modes
-----
* Live show  — keeps the program on the singer while there are vocals, and
  rotates through your instrumental scenes (wide / guitar / drums / ...)
  during instrumental sections, with pacing that follows the energy of
  the music.
* Podcast    — follows the active speaker using each speaker's own mic,
  holds through natural pauses, ignores "mm-hm" backchannel, and chooses
  between each speaker's MEDIUM and CLOSE-UP shots (pushing in when
  someone holds forth or gets emphatic, relaxing back out for variety,
  and going to a wide two-shot during rapid exchanges).

Install (macOS)
---------------
1. Install Python 3 (python.org installer or `brew install python@3.11`).
2. OBS -> Tools -> Scripts -> "Python Settings" tab -> point OBS at that
   Python installation.
3. "Scripts" tab -> "+" -> pick this file. Configure and check "Active".

The script uses only the Python standard library — nothing to pip install.

Everything above the "OBS GLUE" marker is pure logic with no OBS
dependency, so it can be unit-tested and simulated offline (see tests/
and demo.py in the repository).
"""

from __future__ import annotations

import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional

try:  # Present when running inside OBS; absent under pytest / demo.
    import obspython as obs  # type: ignore
except ImportError:  # pragma: no cover - exercised only outside OBS
    obs = None

__version__ = "0.2.0"

NEG_INF_DB = -90.0


# ===========================================================================
# Directing core (pure logic — no OBS imports)
# ===========================================================================

@dataclass
class Cut:
    """A committed scene change, with the director's reasoning."""
    scene: str
    reason: str
    priority: bool = False


class PacingEngine:
    """Enforces professional pacing on cut requests.

    * never re-cuts to the scene we are already on
    * enforces a minimum shot duration, unless the cut is marked priority
      (e.g. vocals just came in — that cut must not wait)
    """

    def __init__(self, min_shot_s: float = 2.5, override_hold_s: float = 8.0):
        self.min_shot_s = min_shot_s
        self.override_hold_s = override_hold_s
        self.scene: Optional[str] = None
        self.last_cut_t = -1e9
        self.external_hold_until = -1e9

    def sync(self, t: float, scene: Optional[str]) -> None:
        """Tell the engine what is actually on program. A scene we did not
        cut to ourselves is a manual override: respect it — restart the
        shot clock and hold off non-priority cuts for a while instead of
        stomping the operator's cut on the next tick."""
        if scene and scene != self.scene:
            self.scene = scene
            self.last_cut_t = t
            self.external_hold_until = t + self.override_hold_s

    def request(self, t: float, scene: str, reason: str,
                priority: bool = False) -> Optional[Cut]:
        if not scene or scene == self.scene:
            return None
        if not priority and t < self.external_hold_until:
            return None
        if not priority and (t - self.last_cut_t) < self.min_shot_s:
            return None
        self.scene = scene
        self.last_cut_t = t
        return Cut(scene, reason, priority)


class LevelVAD:
    """Voice/vocal activity detection from a level meter (dB).

    Tracks an adaptive noise floor (fast downward, slow upward, and never
    while the signal is hot) and applies attack/release times so the
    activity flag is stable rather than fluttering with every syllable.
    """

    def __init__(self, margin_db: float = 8.0, attack_s: float = 0.25,
                 release_s: float = 2.5, floor_db: float = -60.0):
        self.margin_db = margin_db
        self.attack_s = attack_s
        self.release_s = release_s
        self.floor_db = floor_db
        self.active = False
        self._hot_since: Optional[float] = None
        self._last_hot_t = -1e9

    def update(self, t: float, level_db: float) -> bool:
        level_db = max(level_db if level_db == level_db else NEG_INF_DB,
                       NEG_INF_DB)  # NaN/-inf guard

        # Muted / disconnected input is "no signal", not "a very quiet room":
        # learning a floor from it would poison the detector (floor collapses
        # to -90, then ordinary room tone reads as hot forever).
        if level_db <= NEG_INF_DB + 1.0:
            hot = False
        else:
            hot = level_db >= self.floor_db + self.margin_db
            # Adapt the noise floor using the pre-update floor.
            if level_db < self.floor_db:
                self.floor_db += 0.3 * (level_db - self.floor_db)
            elif not hot:
                self.floor_db += 0.005 * (level_db - self.floor_db)
            else:
                # Bounded recovery so a poisoned (too-low) floor can climb
                # back even if the signal never drops below it again. The
                # target keeps 6 dB of headroom under the hot threshold, so
                # recovery can never turn the current signal not-hot.
                target = level_db - self.margin_db - 6.0
                if self.floor_db < target:
                    self.floor_db += 0.002 * (target - self.floor_db)
            self.floor_db = min(self.floor_db, -25.0)

        if hot:
            if self._hot_since is None:
                self._hot_since = t
            self._last_hot_t = t
            if not self.active and (t - self._hot_since) >= self.attack_s:
                self.active = True
        else:
            self._hot_since = None
            if self.active and (t - self._last_hot_t) >= self.release_s:
                self.active = False
        return self.active

    def resync(self, t: float) -> None:
        """Restart timers after a time discontinuity (stall, pause/resume),
        so the gap is not counted as attack or release time."""
        self._hot_since = None
        if self.active:
            self._last_hot_t = t


def apply_crosstalk_gate(talking: List[bool], levels: List[float],
                         gate_db: float = 6.0) -> List[bool]:
    """Suppress mic bleed: if several mics read hot at once, only mics within
    gate_db of the loudest are treated as genuinely talking."""
    if sum(talking) < 2 or not levels:
        return talking
    loudest = max(lvl for talk, lvl in zip(talking, levels) if talk)
    return [talk and lvl >= loudest - gate_db
            for talk, lvl in zip(talking, levels)]


# ---------------------------------------------------------------------------
# Live show mode
# ---------------------------------------------------------------------------

@dataclass
class LiveConfig:
    singer_scene: str
    instrumental_scenes: List[str] = field(default_factory=list)
    min_shot_s: float = 3.0
    post_vocal_hold_s: float = 1.6   # linger on singer after the phrase ends
    cut_interval_s: float = 7.0      # base instrumental shot length
    cut_jitter: float = 0.35         # +/- fraction of interval (feels human)
    cutaway_every_s: float = 25.0    # brief cutaway during long vocals; 0=off
    cutaway_len_s: float = 3.0
    energy_pacing: bool = True       # louder sections -> faster cutting


class LiveDirector:
    """Directs a live music show.

    Vocals in  -> priority cut to the singer, and hold.
    Vocals out -> linger a beat (post_vocal_hold), then rotate through the
                  instrumental scenes. The first instrumental cut prefers
                  the first scene in the list (put your wide shot there —
                  after a vocal phrase, pulling out wide reads best).
    Long vocal -> optional short cutaway, then back to the singer.
    """

    def __init__(self, cfg: LiveConfig, rng: Optional[random.Random] = None):
        self.cfg = cfg
        self.rng = rng or random.Random()
        self.pace = PacingEngine(cfg.min_shot_s)
        self.vocal = False
        self._vocal_start = 0.0
        self._cutaway_ref = 0.0        # last time we were "fresh" on singer
        self._cutaway_end: Optional[float] = None
        self._next_rotate_t: Optional[float] = None
        self._fresh_instrumental = True
        self._energy_ema: Optional[float] = None
        self._energy_dev = 3.0

    # -- energy tracking ----------------------------------------------------
    def _note_energy(self, level_db: float) -> None:
        if level_db <= NEG_INF_DB:
            return
        if self._energy_ema is None:
            self._energy_ema = level_db
            return
        diff = level_db - self._energy_ema
        self._energy_ema += 0.01 * diff
        self._energy_dev += 0.01 * (abs(diff) - self._energy_dev)

    def _shot_len(self) -> float:
        base = self.cfg.cut_interval_s
        jit = self.cfg.cut_jitter
        length = base * self.rng.uniform(1.0 - jit, 1.0 + jit)
        if (self.cfg.energy_pacing and self._energy_ema is not None
                and self._last_energy > NEG_INF_DB):
            # Louder-than-usual sections cut faster, quiet ones slower.
            z = (self._last_energy - self._energy_ema) / max(self._energy_dev, 1.5)
            length *= min(max(1.0 - 0.15 * z, 0.6), 1.4)
        return max(length, self.cfg.min_shot_s)

    def _pick_instrumental(self) -> Optional[str]:
        scenes = [s for s in self.cfg.instrumental_scenes if s]
        if not scenes:
            return None
        if self._fresh_instrumental and scenes[0] != self.pace.scene:
            return scenes[0]
        options = [s for s in scenes if s != self.pace.scene] or scenes
        return self.rng.choice(options)

    # -- main tick ----------------------------------------------------------
    def update(self, t: float, vocal_active: bool,
               energy_db: Optional[float] = None) -> Optional[Cut]:
        self._last_energy = energy_db if energy_db is not None else NEG_INF_DB
        if energy_db is not None:
            self._note_energy(energy_db)

        if vocal_active and not self.vocal:
            self.vocal = True
            self._vocal_start = t
            self._cutaway_ref = t
            self._cutaway_end = None
            self._next_rotate_t = None
            return self.pace.request(t, self.cfg.singer_scene,
                                     "vocals in — cut to singer",
                                     priority=True)
        if self.vocal and not vocal_active:
            self.vocal = False
            self._fresh_instrumental = True
            self._next_rotate_t = t + self.cfg.post_vocal_hold_s
            self._cutaway_end = None

        if self.vocal:
            return self._update_vocal(t)
        return self._update_instrumental(t)

    def _update_vocal(self, t: float) -> Optional[Cut]:
        cfg = self.cfg
        if self._cutaway_end is not None:
            if t >= self._cutaway_end:
                self._cutaway_end = None
                self._cutaway_ref = t
                return self.pace.request(t, cfg.singer_scene,
                                         "back to singer", priority=True)
            return None  # riding out the cutaway
        if (cfg.cutaway_every_s > 0 and cfg.instrumental_scenes
                and (t - self._cutaway_ref) >= cfg.cutaway_every_s):
            scene = self._pick_instrumental()
            if scene:
                cut = self.pace.request(t, scene, "cutaway during long vocal")
                if cut:
                    self._cutaway_end = t + cfg.cutaway_len_s
                    return cut
        return self.pace.request(t, cfg.singer_scene, "hold singer")

    def _update_instrumental(self, t: float) -> Optional[Cut]:
        if not self.cfg.instrumental_scenes:
            return None
        if t < self.pace.external_hold_until:
            # Operator cut manually: let their shot ride, resume rotation
            # only after the hold expires.
            self._next_rotate_t = max(self._next_rotate_t or 0.0,
                                      self.pace.external_hold_until)
            return None
        if self._next_rotate_t is None:  # engaged mid-instrumental
            self._next_rotate_t = t
        if t < self._next_rotate_t:
            return None
        scene = self._pick_instrumental()
        if not scene:
            return None
        cut = self.pace.request(t, scene, "instrumental — next shot")
        if cut or scene == self.pace.scene:
            self._fresh_instrumental = False
            self._next_rotate_t = t + self._shot_len()
        return cut


# ---------------------------------------------------------------------------
# Podcast mode
# ---------------------------------------------------------------------------

@dataclass
class SpeakerCfg:
    name: str
    medium_scene: str
    closeup_scene: str


@dataclass
class PodcastConfig:
    speakers: List[SpeakerCfg] = field(default_factory=list)
    wide_scene: str = ""              # optional two-shot
    min_shot_s: float = 2.6
    pause_tolerance_s: float = 1.2    # holder keeps floor through short pauses
    backchannel_max_s: float = 0.9    # "mm-hm" never steals the floor
    interrupt_commit_s: float = 1.6   # sustained overlap steals the floor
    closeup_after_s: float = 10.0     # push in once someone holds forth
    closeup_grace_s: float = 3.0      # wait up to this for a natural beat
    closeup_max_s: float = 25.0       # then relax back out for variety
    emphasis_db: float = 6.0          # sudden loudness => earlier close-up
    emphasis_hold_s: float = 1.0
    park_after_s: float = 6.0         # dead air: release floor, rest on wide
    utter_debounce_s: float = 0.3     # a blip this short continues an utterance
    rapid_window_s: float = 10.0      # N floor changes in this window ...
    rapid_cuts: int = 3               # ... sends us to the wide shot
    rapid_calm_s: float = 6.0


class _SpeakerState:
    def __init__(self) -> None:
        self.talking = False
        self.utter_start = 0.0
        self.last_talk_t = -1e9
        self.level_ema: Optional[float] = None
        self.talk_accum = 0.0
        self.emph_since: Optional[float] = None


class PodcastDirector:
    """Directs a two-person (or N-person) conversation.

    Floor logic: the current speaker keeps the floor through pauses shorter
    than pause_tolerance; short interjections never steal it; a sustained
    interruption does. Shot logic: a floor change lands on the new
    speaker's MEDIUM; hold the floor and we push to the CLOSE-UP — on a
    natural micro-pause when possible — then relax back to medium after a
    while. A flurry of floor changes cuts to the wide two-shot until the
    exchange settles.
    """

    def __init__(self, cfg: PodcastConfig):
        self.cfg = cfg
        self.pace = PacingEngine(cfg.min_shot_s)
        self.speakers = [_SpeakerState() for _ in cfg.speakers]
        self.holder: Optional[int] = None
        self.floor_since = 0.0
        self.shot = "medium"          # "medium" | "close"
        self.shot_since = 0.0
        self.wide = False
        self.changes: deque = deque(maxlen=16)
        self._pending = ("", False)   # (reason, priority) for the next cut
        self._dt = 0.05
        self._last_t: Optional[float] = None

    # -- helpers ------------------------------------------------------------
    def _silence_for(self, t: float, i: int) -> float:
        return t - self.speakers[i].last_talk_t

    def _utter_len(self, t: float, i: int) -> float:
        st = self.speakers[i]
        return (t - st.utter_start) if st.talking else 0.0

    def _take_floor(self, t: float, i: int, reason: str, priority: bool) -> None:
        self.holder = i
        self.floor_since = t
        self.shot = "medium"
        self.shot_since = t
        self.changes.append(t)
        self._note_transition(reason, priority)

    def _note_transition(self, reason: str, priority: bool) -> None:
        self._pending = (reason, priority)

    # -- main tick ----------------------------------------------------------
    def update(self, t: float, talking: List[bool],
               levels: Optional[List[float]] = None) -> Optional[Cut]:
        cfg = self.cfg
        if self._last_t is not None:
            raw_dt = t - self._last_t
            if raw_dt > 0.5:
                # Time discontinuity (UI stall, pause/resume): the gap must
                # not be counted as utterance length or holder silence —
                # otherwise a fused pre/post-gap backchannel reads as a long
                # interruption and steals the floor.
                self._dt = 0.25
                for st in self.speakers:
                    if st.talking:
                        st.utter_start = t
                if self.holder is not None:
                    self.speakers[self.holder].last_talk_t = t
            else:
                self._dt = max(raw_dt, 1e-3)
        self._last_t = t

        # 1. Bookkeeping per speaker.
        for i, st in enumerate(self.speakers):
            talk = talking[i] if i < len(talking) else False
            if talk and not st.talking:
                # Debounced: a sub-utter_debounce_s dropout (detector
                # flicker) continues the same utterance rather than
                # restarting the interrupt-commit clock.
                if (t - st.last_talk_t) >= cfg.utter_debounce_s:
                    st.utter_start = t
            st.talking = talk
            if talk:
                st.last_talk_t = t
                st.talk_accum += self._dt
                if levels and i < len(levels) and levels[i] > NEG_INF_DB:
                    lvl = levels[i]
                    if st.level_ema is None:
                        st.level_ema = lvl
                    else:
                        st.level_ema += 0.005 * (lvl - st.level_ema)

        # 2. Floor logic.
        if self.holder is None:
            candidates = [i for i, st in enumerate(self.speakers) if st.talking]
            if candidates:
                first = max(candidates, key=lambda i: self._utter_len(t, i))
                self._take_floor(t, first,
                                 f"{cfg.speakers[first].name} opens",
                                 priority=True)
        else:
            h = self.holder
            challengers = [
                i for i, st in enumerate(self.speakers)
                if i != h and st.talking
                and self._utter_len(t, i) >= cfg.backchannel_max_s
            ]
            if challengers:
                c = max(challengers, key=lambda i: self._utter_len(t, i))
                holder_silent = self._silence_for(t, h)
                if holder_silent >= cfg.pause_tolerance_s:
                    self._take_floor(t, c,
                                     f"{cfg.speakers[c].name} takes the floor",
                                     priority=True)
                elif (self._utter_len(t, c) >= cfg.interrupt_commit_s
                      and (t - self.floor_since) >= cfg.interrupt_commit_s):
                    # The overlap must also outlast the last floor change,
                    # so a fresh holder can't be instantly stolen from by a
                    # challenger whose utterance merely started earlier.
                    self._take_floor(t, c,
                                     f"{cfg.speakers[c].name} interrupts",
                                     priority=False)

        # 2b. Dead air: nobody talking and the holder silent for a while —
        # release the floor and rest on the wide (if any) rather than
        # eventually pushing in on a silent face.
        if (self.holder is not None
                and not any(s.talking for s in self.speakers)
                and (t - self.speakers[self.holder].last_talk_t)
                >= cfg.park_after_s):
            self.holder = None
            self.wide = False
            self.changes.clear()
            self._pending = ("", False)
            if cfg.wide_scene:
                return self.pace.request(t, cfg.wide_scene,
                                         "dead air — resting on wide")
            return None

        if self.holder is None:
            return None
        h = self.holder
        st = self.speakers[h]
        sp = cfg.speakers[h]

        # 3. Rapid-exchange wide shot.
        if cfg.wide_scene:
            recent = [c for c in self.changes if t - c <= cfg.rapid_window_s]
            if not self.wide and len(recent) >= cfg.rapid_cuts:
                self.wide = True
                self._note_transition("rapid exchange — going wide", True)
            elif self.wide and self.changes and \
                    (t - self.changes[-1]) >= cfg.rapid_calm_s:
                self.wide = False
                self.shot = "medium"
                self.shot_since = t
                self.changes.clear()  # settled: stale changes must not
                                      # immediately re-trigger the wide
                self._note_transition(
                    f"exchange settled — back to {sp.name}", False)

        # 4. Shot escalation (only when not wide).
        if not self.wide:
            emphatic = False
            if (levels and h < len(levels) and st.level_ema is not None
                    and st.talk_accum > 3.0 and st.talking
                    and levels[h] > st.level_ema + cfg.emphasis_db):
                if st.emph_since is None:
                    st.emph_since = t
                emphatic = (t - st.emph_since) >= cfg.emphasis_hold_s
            else:
                st.emph_since = None

            if self.shot == "medium":
                held = t - self.shot_since
                # Push-ins require a holder who is actually holding forth —
                # dead air must not read as a "micro-pause to cut on".
                recently_active = (t - st.last_talk_t) < 2.0
                if emphatic:
                    self.shot = "close"
                    self.shot_since = t
                    self._note_transition(
                        f"{sp.name} gets emphatic — push in", False)
                elif held >= cfg.closeup_after_s and recently_active and (
                        not st.talking  # micro-pause: a natural beat to cut on
                        or held >= cfg.closeup_after_s + cfg.closeup_grace_s):
                    self.shot = "close"
                    self.shot_since = t
                    self._note_transition(
                        f"{sp.name} holding forth — close-up", False)
            elif self.shot == "close":
                if (t - self.shot_since) >= cfg.closeup_max_s:
                    self.shot = "medium"
                    self.shot_since = t
                    self._note_transition("variety — back to medium", False)

        # 5. Resolve desired scene and request the cut.
        if self.wide:
            desired = cfg.wide_scene
        else:
            desired = sp.closeup_scene if self.shot == "close" else sp.medium_scene
        reason, priority = self._pending
        cut = self.pace.request(t, desired, reason or "shot sync", priority)
        if cut:
            self._pending = ("", False)
        return cut


# ===========================================================================
# OBS GLUE — everything below runs only inside OBS Studio
# ===========================================================================

TICK_MS = 50


class _Meter:
    """Wraps an obs_volmeter attached to a named source; stores latest dB."""

    def __init__(self, source_name: str):
        self.name = source_name
        self.level = NEG_INF_DB
        self.attached = False
        self._retry_t = 0.0
        self.volmeter = obs.obs_volmeter_create(obs.OBS_FADER_LOG)

        def _cb(data, magnitude, peak, input_peak):
            try:
                mag = magnitude
                if hasattr(mag, "__len__") and len(mag):
                    val = max(mag)
                else:
                    val = float(mag)
                if val != val:  # NaN
                    val = NEG_INF_DB
                self.level = max(val, NEG_INF_DB)
            except Exception:
                self.level = NEG_INF_DB

        self._cb = _cb  # keep a reference — GC'd callbacks crash OBS scripts
        obs.obs_volmeter_add_callback(self.volmeter, self._cb, None)
        self.ensure_attached(0.0)

    def ensure_attached(self, t: float) -> None:
        if self.attached or (t - self._retry_t) < 2.0:
            return
        self._retry_t = t
        src = obs.obs_get_source_by_name(self.name)
        if src:
            obs.obs_volmeter_attach_source(self.volmeter, src)
            obs.obs_source_release(src)
            self.attached = True

    def destroy(self) -> None:
        try:
            obs.obs_volmeter_remove_callback(self.volmeter, self._cb, None)
        except Exception:
            pass
        obs.obs_volmeter_destroy(self.volmeter)


class _G:
    """Script-global state."""
    mode = "live"
    active = True
    log_cuts = True
    director = None            # LiveDirector | PodcastDirector
    meters: dict = {}          # source name -> _Meter
    vads: list = []            # LevelVAD per monitored source
    meter_order: list = []     # source names, in vads order
    energy_meter = None        # optional _Meter (live mode)
    hotkey_id = None
    missing_scenes: set = set()
    settings = None
    last_tick_t = None


G = _G()


def _log(msg: str) -> None:
    print(f"[AutoDirector] {msg}")


def _current_scene_name() -> Optional[str]:
    src = obs.obs_frontend_get_current_scene()
    if not src:
        return None
    name = obs.obs_source_get_name(src)
    obs.obs_source_release(src)
    return name


def _set_scene(name: str) -> bool:
    src = obs.obs_get_source_by_name(name)
    if not src:
        if name not in G.missing_scenes:
            G.missing_scenes.add(name)
            _log(f"scene not found: '{name}' — check the script settings")
        return False
    obs.obs_frontend_set_current_scene(src)
    obs.obs_source_release(src)
    return True


def _get_string_list(settings, name: str) -> List[str]:
    out: List[str] = []
    arr = obs.obs_data_get_array(settings, name)
    if arr:
        for i in range(obs.obs_data_array_count(arr)):
            item = obs.obs_data_array_item(arr, i)
            val = obs.obs_data_get_string(item, "value")
            if val:
                out.append(val)
            obs.obs_data_release(item)
        obs.obs_data_array_release(arr)
    return out


def _destroy_meters() -> None:
    for m in G.meters.values():
        m.destroy()
    G.meters = {}
    G.vads = []
    G.meter_order = []
    G.energy_meter = None


def _meter_for(source_name: str) -> Optional["_Meter"]:
    if not source_name:
        return None
    if source_name not in G.meters:
        G.meters[source_name] = _Meter(source_name)
    return G.meters[source_name]


def _rebuild(settings) -> None:
    """(Re)create the director + meters from current script settings."""
    _destroy_meters()
    G.missing_scenes = set()
    G.mode = obs.obs_data_get_string(settings, "mode")
    G.active = obs.obs_data_get_bool(settings, "active")
    G.log_cuts = obs.obs_data_get_bool(settings, "log_cuts")

    if G.mode == "podcast":
        speakers, order = [], []
        for n in (1, 2):
            src = obs.obs_data_get_string(settings, f"pod_src{n}")
            med = obs.obs_data_get_string(settings, f"pod_med{n}")
            clo = obs.obs_data_get_string(settings, f"pod_close{n}")
            if src and med:
                speakers.append(SpeakerCfg(
                    name=src, medium_scene=med, closeup_scene=clo or med))
                order.append(src)
        cfg = PodcastConfig(
            speakers=speakers,
            wide_scene=obs.obs_data_get_string(settings, "pod_wide"),
            min_shot_s=obs.obs_data_get_double(settings, "pod_min_shot_s"),
            pause_tolerance_s=obs.obs_data_get_double(settings, "pod_pause_s"),
            closeup_after_s=obs.obs_data_get_double(settings, "pod_closeup_after_s"),
            closeup_max_s=obs.obs_data_get_double(settings, "pod_closeup_max_s"),
        )
        G.director = PodcastDirector(cfg) if speakers else None
        margin = obs.obs_data_get_double(settings, "pod_sensitivity_db")
        for name in order:
            _meter_for(name)
            G.vads.append(LevelVAD(margin_db=margin, attack_s=0.15,
                                   release_s=0.35))
        G.meter_order = order
        if G.director is None:
            _log("podcast mode: select a mic source and a medium scene "
                 "for at least one speaker")
    else:
        vocal_src = obs.obs_data_get_string(settings, "live_vocal_source")
        singer = obs.obs_data_get_string(settings, "live_singer_scene")
        cfg = LiveConfig(
            singer_scene=singer,
            instrumental_scenes=_get_string_list(settings, "live_instrumentals"),
            min_shot_s=obs.obs_data_get_double(settings, "live_min_shot_s"),
            post_vocal_hold_s=obs.obs_data_get_double(settings, "live_hold_ms") / 1000.0,
            cut_interval_s=obs.obs_data_get_double(settings, "live_interval_s"),
            cutaway_every_s=obs.obs_data_get_double(settings, "live_cutaway_s"),
        )
        G.director = LiveDirector(cfg) if (vocal_src and singer) else None
        if vocal_src:
            _meter_for(vocal_src)
            G.vads.append(LevelVAD(
                margin_db=obs.obs_data_get_double(settings, "live_sensitivity_db"),
                attack_s=obs.obs_data_get_double(settings, "live_attack_ms") / 1000.0,
                release_s=obs.obs_data_get_double(settings, "live_release_ms") / 1000.0,
            ))
            G.meter_order = [vocal_src]
        energy_src = obs.obs_data_get_string(settings, "live_energy_source")
        if energy_src:
            G.energy_meter = _meter_for(energy_src)
        if G.director is None:
            _log("live mode: select the vocal mic source and the singer scene")


def _tick() -> None:
    if not G.active or G.director is None:
        return
    t = time.monotonic()
    if G.last_tick_t is not None and (t - G.last_tick_t) > 0.5:
        for vad in G.vads:
            vad.resync(t)  # a UI stall must not count as attack/release time
    G.last_tick_t = t
    for m in G.meters.values():
        m.ensure_attached(t)

    # Keep the pacing engine in sync with reality (manual cuts, transitions).
    G.director.pace.sync(t, _current_scene_name())

    levels = [G.meters[name].level if name in G.meters else NEG_INF_DB
              for name in G.meter_order]
    talking = [vad.update(t, lvl) for vad, lvl in zip(G.vads, levels)]

    if isinstance(G.director, PodcastDirector):
        talking = apply_crosstalk_gate(talking, levels)
        cut = G.director.update(t, talking, levels)
    else:
        vocal = talking[0] if talking else False
        energy = G.energy_meter.level if G.energy_meter else None
        cut = G.director.update(t, vocal, energy)

    if cut:
        if _set_scene(cut.scene) and G.log_cuts:
            _log(f"CUT -> {cut.scene}   ({cut.reason})")


def _on_toggle_hotkey(pressed: bool) -> None:
    if not pressed:
        return
    G.active = not G.active
    _log(f"{'ACTIVE' if G.active else 'paused'} (hotkey)")
    if G.settings is not None:
        obs.obs_data_set_bool(G.settings, "active", G.active)


# --------------------------- OBS script API --------------------------------

def script_description():
    return (
        "<b>AutoDirector</b> v" + __version__ +
        "<br/>Automatic scene switching, directed by your audio."
        "<br/><br/><b>Live show</b>: singer cam while there are vocals, "
        "rotating instrumental shots otherwise."
        "<br/><b>Podcast</b>: follows the active speaker; picks medium vs. "
        "close-up like a director would."
        "<br/><br/>Tip: bind the <i>AutoDirector: toggle</i> hotkey "
        "(Settings → Hotkeys) to grab manual control instantly."
    )


def script_defaults(settings):
    obs.obs_data_set_default_string(settings, "mode", "live")
    obs.obs_data_set_default_bool(settings, "active", True)
    obs.obs_data_set_default_bool(settings, "log_cuts", True)
    # live
    obs.obs_data_set_default_double(settings, "live_sensitivity_db", 8.0)
    obs.obs_data_set_default_double(settings, "live_attack_ms", 250.0)
    obs.obs_data_set_default_double(settings, "live_release_ms", 2300.0)
    obs.obs_data_set_default_double(settings, "live_hold_ms", 1600.0)
    obs.obs_data_set_default_double(settings, "live_interval_s", 7.0)
    obs.obs_data_set_default_double(settings, "live_min_shot_s", 3.0)
    obs.obs_data_set_default_double(settings, "live_cutaway_s", 25.0)
    # podcast
    obs.obs_data_set_default_double(settings, "pod_sensitivity_db", 8.0)
    obs.obs_data_set_default_double(settings, "pod_min_shot_s", 2.6)
    obs.obs_data_set_default_double(settings, "pod_pause_s", 1.2)
    obs.obs_data_set_default_double(settings, "pod_closeup_after_s", 10.0)
    obs.obs_data_set_default_double(settings, "pod_closeup_max_s", 25.0)


def _audio_source_names() -> List[str]:
    names = []
    sources = obs.obs_enum_sources()
    if sources:
        for s in sources:
            if obs.obs_source_get_output_flags(s) & obs.OBS_SOURCE_AUDIO:
                names.append(obs.obs_source_get_name(s))
        obs.source_list_release(sources)
    return sorted(names)


def _add_scene_list(props, name: str, label: str, optional: bool = False):
    p = obs.obs_properties_add_list(props, name, label,
                                    obs.OBS_COMBO_TYPE_LIST,
                                    obs.OBS_COMBO_FORMAT_STRING)
    if optional:
        obs.obs_property_list_add_string(p, "(none)", "")
    for scene in (obs.obs_frontend_get_scene_names() or []):
        obs.obs_property_list_add_string(p, scene, scene)
    return p


def _add_source_list(props, name: str, label: str, optional: bool = False):
    p = obs.obs_properties_add_list(props, name, label,
                                    obs.OBS_COMBO_TYPE_LIST,
                                    obs.OBS_COMBO_FORMAT_STRING)
    if optional:
        obs.obs_property_list_add_string(p, "(none)", "")
    for src in _audio_source_names():
        obs.obs_property_list_add_string(p, src, src)
    return p


def _on_mode_changed(props, prop, settings):
    mode = obs.obs_data_get_string(settings, "mode")
    obs.obs_property_set_visible(
        obs.obs_properties_get(props, "grp_live"), mode == "live")
    obs.obs_property_set_visible(
        obs.obs_properties_get(props, "grp_podcast"), mode == "podcast")
    return True


def script_properties():
    props = obs.obs_properties_create()

    obs.obs_properties_add_bool(props, "active", "Active (directing)")
    mode = obs.obs_properties_add_list(props, "mode", "Mode",
                                       obs.OBS_COMBO_TYPE_LIST,
                                       obs.OBS_COMBO_FORMAT_STRING)
    obs.obs_property_list_add_string(mode, "Live show", "live")
    obs.obs_property_list_add_string(mode, "Podcast", "podcast")
    obs.obs_property_set_modified_callback(mode, _on_mode_changed)

    # ---- live group ----
    lp = obs.obs_properties_create()
    _add_source_list(lp, "live_vocal_source", "Vocal mic (audio source)")
    _add_scene_list(lp, "live_singer_scene", "Singer scene")
    obs.obs_properties_add_editable_list(
        lp, "live_instrumentals", "Instrumental scenes (first = wide)",
        obs.OBS_EDITABLE_LIST_TYPE_STRINGS, None, None)
    _add_source_list(lp, "live_energy_source",
                     "Energy source for pacing (e.g. band mix)", optional=True)
    obs.obs_properties_add_float_slider(
        lp, "live_sensitivity_db", "Vocal sensitivity (dB over noise floor)",
        3.0, 24.0, 0.5)
    obs.obs_properties_add_float_slider(
        lp, "live_attack_ms", "Cut to singer after vocals for (ms)",
        100.0, 800.0, 10.0)
    obs.obs_properties_add_float_slider(
        lp, "live_release_ms", "Treat as instrumental after silence of (ms)",
        800.0, 5000.0, 50.0)
    obs.obs_properties_add_float_slider(
        lp, "live_hold_ms", "Linger on singer after phrase ends (ms)",
        0.0, 4000.0, 50.0)
    obs.obs_properties_add_float_slider(
        lp, "live_interval_s", "Instrumental shot length (s)", 3.0, 20.0, 0.5)
    obs.obs_properties_add_float_slider(
        lp, "live_min_shot_s", "Minimum shot length (s)", 2.0, 8.0, 0.25)
    obs.obs_properties_add_float_slider(
        lp, "live_cutaway_s", "Cutaway during long vocals every (s, 0 = never)",
        0.0, 90.0, 1.0)
    obs.obs_properties_add_group(props, "grp_live", "Live show",
                                 obs.OBS_GROUP_NORMAL, lp)

    # ---- podcast group ----
    pp = obs.obs_properties_create()
    for n, label in ((1, "Speaker 1"), (2, "Speaker 2")):
        _add_source_list(pp, f"pod_src{n}", f"{label} mic (audio source)")
        _add_scene_list(pp, f"pod_med{n}", f"{label} — medium scene")
        _add_scene_list(pp, f"pod_close{n}", f"{label} — close-up scene",
                        optional=True)
    _add_scene_list(pp, "pod_wide", "Wide / two-shot scene", optional=True)
    obs.obs_properties_add_float_slider(
        pp, "pod_sensitivity_db", "Speech sensitivity (dB over noise floor)",
        3.0, 24.0, 0.5)
    obs.obs_properties_add_float_slider(
        pp, "pod_min_shot_s", "Minimum shot length (s)", 1.5, 8.0, 0.1)
    obs.obs_properties_add_float_slider(
        pp, "pod_pause_s", "Speaker keeps floor through pauses up to (s)",
        0.4, 3.0, 0.1)
    obs.obs_properties_add_float_slider(
        pp, "pod_closeup_after_s", "Push to close-up after holding floor (s)",
        4.0, 40.0, 0.5)
    obs.obs_properties_add_float_slider(
        pp, "pod_closeup_max_s", "Relax close-up back to medium after (s)",
        8.0, 90.0, 1.0)
    obs.obs_properties_add_group(props, "grp_podcast", "Podcast",
                                 obs.OBS_GROUP_NORMAL, pp)

    obs.obs_properties_add_bool(props, "log_cuts",
                                "Log every cut in the script log")
    return props


def script_update(settings):
    G.settings = settings
    _rebuild(settings)


def script_load(settings):
    G.settings = settings
    G.hotkey_id = obs.obs_hotkey_register_frontend(
        "autodirector.toggle", "AutoDirector: toggle", _on_toggle_hotkey)
    arr = obs.obs_data_get_array(settings, "autodirector.toggle.hotkey")
    obs.obs_hotkey_load(G.hotkey_id, arr)
    obs.obs_data_array_release(arr)
    obs.timer_add(_tick, TICK_MS)
    _log(f"loaded v{__version__}")


def script_save(settings):
    if G.hotkey_id is not None:
        arr = obs.obs_hotkey_save(G.hotkey_id)
        obs.obs_data_set_array(settings, "autodirector.toggle.hotkey", arr)
        obs.obs_data_array_release(arr)


def script_unload():
    try:
        obs.timer_remove(_tick)
    except Exception:
        pass
    _destroy_meters()
