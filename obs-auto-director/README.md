# OBS AutoDirector 🎬

An automatic scene director for OBS Studio. It does one thing well: **switch
between your OBS scenes the way a human director would**, driven by what it
hears on your audio sources.

It ships as a single-file OBS **script plugin** (`obs_auto_director.py`) —
no extra app to run, no virtual audio cables, no websocket setup. It meters
your OBS audio sources directly and cuts the program scene from inside OBS.

## The two modes

### 🎤 Live show mode

For live music. Point it at the **vocal mic** source:

- The moment vocals come in, it makes a **priority cut to the singer scene**
  and holds it — pauses between sung lines don't shake it off.
- When the phrase ends it **lingers a beat** (like a real director riding the
  moment), then starts rotating through your **instrumental scenes**
  (wide / guitar / drums / keys …).
- Instrumental shot lengths are **humanized** — jittered around your base
  interval so it never feels like a metronome — and optionally **paced by the
  energy of the music** (louder sections cut faster, quiet ones breathe).
- The first shot after vocals end pulls out to the **first scene in your
  list** (put your wide there — that's the cut that reads best).
- During very long vocal sections it can take a brief tasteful **cutaway**
  and come right back to the singer.

### 🎙 Podcast mode

For two-person shows where each speaker has their own mic and **two scenes:
a medium and a close-up**:

- Follows the **active speaker** using each speaker's own mic level, with an
  adaptive noise floor and a crosstalk gate so mic bleed doesn't fool it.
- A speaker **keeps the floor through natural pauses** (default 1.2 s), and
  "mm-hm" **backchannel never steals the shot**. A sustained interruption
  does — after it proves itself (default 1.6 s of overlap).
- A floor change lands on the new speaker's **medium** shot. Hold the floor
  and the director **pushes in to the close-up** — waiting for a natural
  micro-pause to cut on when it can — then **relaxes back to medium** after a
  while for variety.
- Sudden **emphasis** (a speaker getting noticeably louder than their own
  baseline) earns an early push-in.
- A rapid back-and-forth exchange cuts to your **wide two-shot** until the
  exchange settles, then returns to whoever holds the floor.

Everything above is enforced by a pacing engine: a **minimum shot length**
guards against flicker, and only genuinely urgent cuts (vocals coming in, a
clean speaker handoff) are allowed to jump the queue.

---

## Install on macOS

1. **Install Python 3** (3.10–3.12). Either the
   [python.org installer](https://www.python.org/downloads/macos/) or
   Homebrew:

   ```bash
   brew install python@3.11
   ```

2. **Tell OBS where Python is**: OBS → *Tools → Scripts → Python Settings*
   tab, and browse to the Python installation, e.g.

   - python.org install: `/Library/Frameworks/Python.framework/Versions/3.11`
   - Homebrew (Apple Silicon): `/opt/homebrew/opt/python@3.11/Frameworks/Python.framework/Versions/3.11`
   - Homebrew (Intel): `/usr/local/opt/python@3.11/Frameworks/Python.framework/Versions/3.11`

3. **Add the script**: *Scripts* tab → **+** → select `obs_auto_director.py`.

The script uses only the Python standard library — nothing to `pip install`.

## Set up your scenes

**Live show mode**

| Setting | What to pick |
|---|---|
| Vocal mic | The singer's mic **audio source** |
| Singer scene | The scene with the singer camera |
| Instrumental scenes | One scene name per line; **put the wide shot first** |
| Energy source (optional) | A band/music mix source — enables energy-aware pacing |

**Podcast mode**

| Setting | What to pick |
|---|---|
| Speaker 1 / 2 mic | Each speaker's own **audio source** |
| Medium scene (each) | That speaker's medium shot |
| Close-up scene (each) | That speaker's close-up (optional — falls back to medium) |
| Wide / two-shot (optional) | Used during rapid exchanges |

Then check **Active** and start talking / playing. Every cut is logged with
its reasoning in the script log (*Script Log* button), e.g.:

```
[AutoDirector] CUT -> Ben Medium   (Ben takes the floor)
[AutoDirector] CUT -> Anna Close   (Anna holding forth — close-up)
[AutoDirector] CUT -> Two Shot     (rapid exchange — going wide)
```

### Grab the wheel any time

Bind the **“AutoDirector: toggle”** hotkey (OBS → *Settings → Hotkeys*) to
pause/resume the director instantly for manual control.

## Tuning guide

Start with the defaults — they're set for natural, professional pacing.

| Feels like… | Try |
|---|---|
| It cuts to the singer too late | Lower *“Cut to singer after vocals for”* (attack) |
| It bails off the singer between sung lines | Raise *“Treat as instrumental after silence of”* (release) |
| It misses quiet vocals / triggers on stage bleed | Lower / raise *Vocal sensitivity* |
| Instrumental cutting feels frantic / sleepy | Raise / lower *Instrumental shot length* |
| Podcast cuts on every little pause | Raise *“keeps floor through pauses up to”* |
| Close-ups come too eagerly / never | Raise / lower *“Push to close-up after holding floor”* |
| Any mode flickers between scenes | Raise *Minimum shot length* |

## Try it without OBS

The directing brain is pure Python, so you can watch it direct a scripted
show offline:

```bash
python3 demo.py live      # a song: intro / verses / solo / outro
python3 demo.py podcast   # a conversation with interruptions & rapid exchange
```

And run the test suite:

```bash
pip3 install pytest
python3 -m pytest tests/
```

## Troubleshooting

- **My mic doesn't appear in the dropdown** — only sources with audio are
  listed. If you just added the source, close and reopen the Scripts dialog.
- **No cuts happen** — check *Active* is on, open the Script Log; the script
  tells you if a scene name can't be found or a mode is missing settings.
- **“Python Settings” won't accept my install** — OBS needs the framework
  folder (the path ending in `/Versions/3.11`), not the `python3` binary.
  On Apple Silicon make sure OBS and Python are both arm64.
- **Two mics in one room trigger each other** — the crosstalk gate handles
  most bleed; if needed, raise *Speech sensitivity* a couple of dB.

## How it works

`obs_auto_director.py` is split in two halves:

- **Directing core** (pure Python, no OBS imports): a `LevelVAD` voice
  activity detector with an adaptive noise floor, a `PacingEngine` that
  enforces minimum shot lengths and priority cuts, and the two directors —
  `LiveDirector` (vocal/instrumental state machine) and `PodcastDirector`
  (floor-holding, shot escalation, rapid-exchange logic). This half is fully
  unit-tested (`tests/`).
- **OBS glue**: attaches an `obs_volmeter` to each configured audio source,
  ticks the director every 50 ms, and cuts the program scene through the
  OBS frontend API. It stays in sync with manual cuts you make.

## Roadmap

- **Visual cues** for podcast mode (face/mouth activity from the camera
  feeds) fused with the audio signal.
- Content-aware close-ups (lightweight on-device speech emotion/keyword
  cues).
- 3+ speakers, and per-speaker shot preferences.
- Beat-aligned cutting in live mode (cut on the downbeat).

## License

MIT
