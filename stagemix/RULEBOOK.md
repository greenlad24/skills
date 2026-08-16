# The rulebook

Everything the operator has specified about how this band's mix should
sound — out front and in each monitor — collected in one place, in
their own words wherever possible. **This file is the source of truth.**
Where the code and this file disagree, the code is wrong.

It exists because the rules arrived across many conversations, and an
autopilot that has drifted from them is worse than no autopilot: it is
confidently wrong in a room full of people.

---

## 0 · The absolute constraints

These are not preferences. They override everything below.

1. **Never add gain, by any route.**
   > "messing with gain WILL cause feedback problems on the stage that
   > the app will find hard to resolve — I want this app to be precise
   > and never cause problems"

   Not the preamp, not EQ boosts, not compressor makeup. And note that
   on an X-Air the aux sends tap the channel **after** EQ and dynamics,
   so any processing boost lands in all six wedges at full value. The
   processing path is cut-only, enforced in code rather than trusted.

2. **The same argument applies to EQ.** EQ is permitted — *"I'm ok
   about the app doing EQ"* — but only as cuts.

3. **The app has the mixer's IP and nothing else.** No internet, ever.

4. **Nothing may move a bus master.** How loud a wedge is belongs to
   the person standing in front of it.

5. **Between songs it does nothing at all** — no rebalancing, no EQ,
   no compression, no monitor moves.
   > "In between songs - I don't want the app to do rebalancing or
   > EQ/Compression - only when the band is playing"

   The one exception is **ringing out a live feedback**: a howl between
   songs is real and unbearable, and §4 requires it be fixed as fast as
   possible. A ring-out is a narrow cut on the microphone in the loop,
   not rebalancing or voicing, so it is allowed to act whenever the
   stage is actually howling. Nothing else runs between songs.

6. **And when the band IS playing, it only acts when it is needed:**
   > "1. Solo happening (Sax, guitar, harmonica)
   >  2. A new instrument has entered that was not there before"

7. **A hand always wins.** If the engineer moves something, adopt their
   level as the new truth, hold off that channel, and learn from the
   direction they moved it. Never fight a hand.

---

## 1 · The rig — facts, not guesses

| Channel | What it is | Rule |
|---|---|---|
| 1 | **Kick** | always. never re-identified |
| 2 | **Snare** | always. never re-identified |
| DI 1 | **acoustic guitar** | the singer plays it |
| Bass DI | **bass** | in the pyramid |
| DI 2 | **bass** | *also* the bass — both are the bass |
| 11 | usually **conga**, sometimes a **third vocal** | must tolerate both |
| 15 | usually **saxophone**, sometimes a **flute** | must tolerate both |
| 16 | usually **harmonica**, sometimes a **backing vocal** | must tolerate both |

> "The first and second channels will always be Kick and Snare mics."
> "Bass DI and DI 2 are very important (both are the bass - in the
> pyramid) ... both of these channels will also stay always in their
> current positions."
> "channel 11 - usually a conga but sometimes a third vocal"
> "channel 15 - saxophone most of the time and sometimes flute.
>  channel 16 - harmonica most of the time, sometimes a back vocal."

### The three channels that change instrument

Channels **11, 15 and 16** are the ones that are not a fixed fact. Each
carries one thing most of the night and something quite different for a
song or two, and the app has to be right in **both** states without
being told:

| Channel | Usually | Sometimes | What changes when it does |
|---|---|---|---|
| 11 | conga (PERCUSSION) | third vocal (VOCAL) | joins the vocals; becomes a held role |
| 15 | saxophone (COLOR) | flute (COLOR) | same role, very different spectrum — a flute is quiet, breathy and high, and must not be mistaken for silence or for a cymbal |
| 16 | harmonica (COLOR) | backing vocal (BACKING_VOCAL) | becomes a held role, and stops being solo-eligible |

Consequences that follow from this and are not optional:

- **A wrong guess must cost a couple of dB, not a song.** These three
  are exactly why the app may only move the channels that are not the
  fixed shape of the mix.
- **Telling it is one tap**, and telling it must also undo whatever it
  did while it was wrong.
- **Sax and harmonica are named solo instruments** (§0.6): when either
  steps up it gets featured and then eased back. A flute does the same
  job on the same channel and must be featured the same way.
- **When 11 or 16 is being a voice, it is a held role** — the app does
  not ride it, and it belongs with the vocals in every monitor ladder.

---

## 2 · Out front — how the mix should sound

- **Foundation:** kick + bass (Bass DI *and* DI 2) hold the bottom.
- **The lead vocal sits on top of everything.** This is the single
  relationship the whole engine exists to defend: if LEAD is above
  BAND, the mix is working.
- **Lead-follow between the vocal mics** — whoever is carrying the song
  is the lead, and it can change during the night.
- **Everything else laddered underneath**, by role.
- **A solo is featured** — sax, flute, guitar, harmonica **and the
  piano** step up and are held up for the duration, then eased back.

  > "the piano can also do solos."

  The piano is **two channels** (Piano L and Piano R, a stereo pair),
  so a piano solo has to lift **both halves by the same amount**.
  Lifting only the one that crossed the threshold pulls the image hard
  to one side for the length of the solo, which is worse than not
  lifting it at all. The same applies to anything else paired.
- **The foundation and the lead vocal are a deliberate pair, not a
  contest.** The lead vocal sits on top of every *accompaniment*
  channel; the kick and bass (the low-end *group*) are the exception —
  their combined level sits with the lead by design, because that is
  what makes a mix feel full rather than thin. "On top of everything"
  is about the accompaniment, not about beating the kick drum in
  isolation.
- **A new instrument arriving** is listened to before being placed.
- **Held roles stay where the operator put them:** VOCAL,
  BACKING_VOCAL, FOUNDATION, PERCUSSION. The app's authority is the
  window −12 dB to +6 dB around the fader position at takeover, with a
  hard ceiling of +2 dB above it in absolute terms.
- **KEEP means keep.** Once a balance is adopted, only the source
  genuinely moving, a solo, or an instrument arriving changes anything.

---

## 3 · The monitors — how each position should sound

Five positions. Whether each is a floor wedge or in-ears starts from its
name but is the operator's to set per monitor (see the toggle below) —
the drummer in particular swaps between the two.

The generalisation the code encodes: **an in-ear wants that player's
own instrument on top of a complete mix; a wedge wants that player's
own instrument on top of a partial one, with the drum kit left out**,
because the kit is three feet away and arrives over the top of the
stage anyway. Putting it in the wedge as well only spends gain before
feedback. In-ears seal the ears off from the room, so they need
everything, kit included.

**"No drums" means the KIT, not all percussion.** The congas are across
the stage, they are part of "the rest" in most wedges, and the bass
player explicitly wants them.

### Bus 1 — CENTRE, the singer's wedge
> "it's the singer monitor, it needs vocals at high volume (but not
> feedbacking volume), no drums, DI1 (It's what we use for acoustic
> guitar) at good volume, all of the rest balanced at lower volumes."

- vocals **high** — but never at feedbacking volume
- **no kit**
- **DI 1** (acoustic guitar) at good volume
- everything else balanced, lower

### Bus 2 — the guitarist's wedge, labelled "PIANO MON"
> "Guitar monitor (which is called piano monitor - bus 2) should have
> guitar at higher volume, vocals, no drums, and all the rest balanced
> at lower volumes."

- guitar **higher**
- vocals present
- **no kit**
- everything else balanced, lower

*(The name is a trap: this wedge is called "piano monitor" and is the
guitarist's. No amount of listening would work that out — it has to be
read off the name the engineer typed.)*

### The bass player's wedge
> "Bass monitor - bass and congas a little bit on top, all the rest
> balanced (without drums) at lower volumes."

- bass on top, **congas a little on top too**
- **no kit**
- everything else balanced, lower

### Bus 3 — the drummer's monitor (in-ears **or** a floor wedge)
> "in-ears need a balanced mix with the current playing instruments
> above - for drums in-ear is the drums"

**When it is in-ears:**
- the **whole kit** on top — the kick included, above the snare, not
  a rung under it (the kick's *role* is FOUNDATION, but in the
  drummer's ears it is part of the kit, and the kit is the point)
- a balanced mix of whatever is currently playing underneath

**When the drummer has no in-ears — a floor wedge instead:**
> "sometimes the drums monitor is not in-ears - in that case where the
> drummer doesn't have in-ears there should be a balance of the
> instruments (piano, DI1, Bass DI a little more, DI2 a little more,
> Guitar Amp, drums, Vocals on top, low harmonica, Saxophone lower)"

- the band **in front of** the kit, **vocals on top** — not the
  kit-first mix an in-ear wants
- the two bass DIs (Bass DI, DI2) a **little more** than the rest
- piano, DI1, the guitar amp and the drums balanced in the middle (the
  kit is present here, unlike every other floor wedge, because it is the
  drummer's own and they asked for it)
- the horns **low** — harmonica low, saxophone lower

### The in-ears / wedge toggle
> "there should be a toggle switch for each monitor (in-ears or not)"

- **Every monitor has a per-bus toggle: IN-EARS or WEDGE**, on the
  MONITORS tab. It starts from what the monitor's name implies (an "IEM"
  is in-ears) and the operator has the final word — the drummer swaps
  between the two between gigs, and the mix each wants is very different.
- The choice is **remembered across nights** and survives a console
  rename. Flipping it changes the balance the app aims that monitor at
  (kit-on-top for in-ears, band-with-vocals-on-top for a floor wedge);
  it still only *balances* the wedge, cut-first, and only when monitor
  keeping is on.

### Bus 6 — the second in-ears (piano + bass)
> "for bus 6 (piano + bass) it's the piano and DI2"

- **piano** and **DI 2** on top
- a balanced mix underneath

### How the app is allowed to act on any of them
> "the app can do rebalancing to the monitors but in a different way it
> does on the outside. It needs to understand the current balance of
> each monitor separately and then adjust it slightly based on the
> position of it (and what is happening - for example if the sound
> engineer is changing that balance) understand what's happening and go
> with it rather then fight it."

and later, plainly:

> "monitors will rebalance slightly not much"

Which means, concretely:

- **The ladder is a SHAPE.** Only the gaps between its rungs are the
  app's business. Its absolute height — how loud the wedge is — is the
  musician's, always.
- **To make something louder, turn something else down.** A monitor mix
  is a ratio, and raising a send spends gain before feedback on the
  loudest open microphone in the room. Cutting its neighbours produces
  the identical ratio and spends none. Balancing the monitors and never
  causing feedback are only compatible in that order.
- **A send that is OFF is a routing decision, not a balance error** —
  and a cut may never take a send *to* the off floor: the app does not
  un-route what the engineer chose to route.
- Slightly: one small move per bus at a time (0.7 dB), bounded hard
  over a whole night (at most 6 dB of cut, 1.5 dB of raise on any one
  send), nothing between songs, and nothing at all on a wedge that is
  already close enough.
- **Re-Balance is "act now", not "act differently."** Pressing it does
  a pass immediately instead of waiting for the throttle — but at the
  same small step, and no single send moves more than once per press.
- **Monitor keeping is a choice, and it defaults OFF.** A wedge is in a
  musician's ears and is not reversible in one tap the way a main
  fader is, so the app does not touch the wedges unless the operator
  turns keeping on for a night they are watching.

---

## 4 · Feedback

> "I want the app to avoid creating feedbacks and fix feedbacks as fast
> as it can."

**Avoid:** cut-preferred everywhere; never raise a microphone that has
been in a ring; no raising anywhere on the stage for several minutes
after a howl; no gain, ever, by any route.

**Fix:** find *which* microphone the loop is in — every open mic hears
a howl, but the one in the loop hears it far louder — and put a narrow
cut on that channel, so one move fixes the wedge, the side-fill and the
mains at once. Fast, but never faster than it can actually know: the
early exit needs most of the stage measured (not a handful of
channels) before it calls a culprit, because a wrong cut damages an
innocent channel *and* stops the app finding the real one.

The four frequencies this rig has actually produced: **196, 160, 226
and 3377 Hz.**

**And the processing must never make feedback more likely.** The
starting chain and the tone doctor read the desk at takeover and:
- never *lower* a high-pass the engineer set (that un-cuts the low end
  — it adds gain where a low ring lives);
- never flatten an EQ band the engineer is *cutting* (that erases a
  ring-out — it adds gain at the very frequency they tamed);
- never add gain by any route — not the preamp, not an EQ boost, not
  compressor makeup — and stay entirely quiet between songs.

---

## 5 · What the app must always tell the operator

> "In any case there's an error - it should be shown as well. All types
> of errors (not mixing is also an error) - it should tell what should
> be done to fix it"

- **Not mixing is a fault**, in fault colours, first in the list. Three
  entire shows went by in watching mode with nothing on screen saying
  so. That must never be possible again.
- Every message carries the thing to press. A fault without a remedy is
  just bad news.
- **Progress is shown at all times**, including a bar. When there is no
  countdown to run, the bar carries how much of the mix is where it
  should be — a number that moves all night, so a still bar means
  stopped rather than settled.
- **The bar tells the truth about whether the app is mixing.** When it
  is watching, frozen, muted, or has lost the mixer, the bar says so in
  amber and never shows the green "finding the balance" fill. A
  reassuring bar over a stopped app is the same lie as a blank panel — it
  was the one surface that could read as working while nothing was being
  sent, and it must not.

> "the auto mix should be on by default - when the app is opened it
> should connect automatically (if available) to the mixer and start
> mixing"

- **No control may be silently dead.** A key that does nothing and says
  nothing is the same failure as three shows in watching mode. If a
  control is pressed before there is anything to act on, it says so —
  on screen and in the log. FREEZE and MIX change the truth the instant
  they are pressed, with or without a live service behind them, because
  they are the panic controls.
- **The status-bar line tells the truth.** MIXING, SHADOW, FROZEN,
  WAITING, NO MIXER — refreshed whenever any of them changes, because it
  is the only thing visible when the app is in the background, and it
  once read "MIXING" for a whole show that was not.
- **The log records everything the app does and everything it tells
  you.** Every fader move with its reason, every processing write
  decoded to dB and Hz, every wedge move, every ring-out, every
  override, every mode change, and the fault stream the operator saw. A
  decision is never dropped, even when a bulk log is trimmed.
- **All of the monitor data is in the log.** The complete picture of
  every wedge — its in-ears/wedge type and every channel's send in dB,
  with where the app wants each one when keeping is on — is written at
  takeover and then on a cadence while the band plays, so the whole
  night's monitor state can be read back, not just a snapshot of the
  loudest few at the start. Like the other decisions, it is never
  dropped.
