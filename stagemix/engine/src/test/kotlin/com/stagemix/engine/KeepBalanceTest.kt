package com.stagemix.engine

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * KEEP: defend the balance that is on the desk.
 *
 * From a real night's log, twenty-one minutes of the pyramid leading a
 * live band:
 *
 *   · 1558 dB of fader travel — about 74 dB a minute across the desk;
 *   · 16 % of all measurements with a channel's offset pinned at one of
 *     its authority rails, and 40 % with the band held at the duck's;
 *   · the same channel "settling" at −12 dB and at +6 dB within a
 *     minute of each other;
 *   · and after all that, the vocal on top less than half the time.
 *
 * The operator switched it off and built the balance they wanted in
 * about a minute. What they then asked for is this file: keep THAT, and
 * "when a volume of a singer become louder the fader should come lower,
 * and vice versa when the signal is weaker the fader should come up."
 *
 * Which is one idea: hold each channel's CONTRIBUTION — source plus
 * fader — where the human put it. Holding the FADER still is not
 * holding a balance; holding the sum still is what a hand on the desk
 * does all night.
 */
class KeepBalanceTest {

    private val rig = defaultRigProfile()
    private val BASE = -10f

    private class Run(val e: StageEngine, val base: Float = -10f) {
        var t = 0.0
        private var next = 1.0
        val writes = ArrayList<Pair<Double, FaderWrite>>()
        private val rnd = java.util.Random(20260805L)
        private var walk = FloatArray(0)
        private var buf = FloatArray(0)

        /**
         * Real instruments move, and the engine rightly treats a source
         * whose level never changes as hum rather than music. A fixture
         * of dead-flat tones therefore has every channel judged "not an
         * instrument" after ninety seconds, which is not a scenario any
         * of these tests mean to be running.
         */
        private fun live(s: FloatArray): FloatArray {
            if (walk.size != s.size) {
                walk = FloatArray(s.size); buf = FloatArray(s.size)
            }
            for (i in s.indices) {
                if (s[i] <= -60f) { buf[i] = s[i]; walk[i] = 0f; continue }
                walk[i] += -0.05f * walk[i] + rnd.nextGaussian().toFloat() * 0.5f
                buf[i] = s[i] + walk[i]
            }
            return buf
        }

        fun run(sec: Double, src: (Double) -> FloatArray) {
            val end = t + sec - 1e-9
            while (t < end) {
                e.onMeters(live(src(t)), t)
                if (t >= next - 1e-9) {
                    for (w in e.tick(t)) writes.add(t to w)
                    next += 1.0
                }
                t += 0.05
            }
        }
        fun start(src: FloatArray, faders: Map<Int, Float>? = null) {
            run(5.0) { src }
            e.takeover(faders ?: (0 until 16).associateWith { base }, t)
        }
        /**
         * Where the fader actually is. Not `base + offset`: an operator
         * override REPLACES the baseline, so measuring against the
         * takeover position reports the engine's move and silently
         * discards the human's.
         */
        fun fader(i: Int) = (e.state[i]?.baselineDb ?: base) + e.offsetDb(i)
        /** total fader travel per channel since [t0] */
        fun travel(t0: Double): FloatArray {
            val last = FloatArray(16) { Float.NaN }
            val out = FloatArray(16)
            for ((tt, w) in writes) {
                if (tt <= t0) { last[w.channel] = w.levelDb; continue }
                if (!last[w.channel].isNaN())
                    out[w.channel] += abs(w.levelDb - last[w.channel])
                last[w.channel] = w.levelDb
            }
            return out
        }
    }

    private fun engine(s: EngineSettings = EngineSettings()) =
        StageEngine(rig, s)

    private fun silence() = FloatArray(16) { -80f }

    /** the rig from the night the log came from, roughly */
    private fun band() = silence().also {
        it[0] = -18f;  it[1] = -20f;  it[2] = -26f;  it[3] = -22f
        it[4] = -19f;  it[5] = -24f;  it[6] = -24f;  it[7] = -21f
        it[8] = -23f;  it[11] = -17f; it[12] = -29f; it[14] = -20f
    }

    // ------------------------------------------------------------------
    @Test fun `the balance on the desk is the one that gets kept`() {
        val e = engine()
        val r = Run(e)
        // a mix somebody made: not flat, deliberately uneven
        val desk = mapOf(0 to -6f, 1 to -12f, 2 to -14f, 3 to -8f,
            4 to -11f, 5 to -15f, 6 to -15f, 7 to -13f, 8 to -3f,
            9 to -20f, 10 to -20f, 11 to -7f, 12 to -16f, 13 to -20f,
            14 to -12f, 15 to -20f)
        val src = band()
        r.start(src, desk)
        r.run(60.0) { src }
        assertTrue(e.balanceAdopted, "the balance must be adopted once heard")

        val at = (0 until 16).associateWith { BASE + e.offsetDb(it) }
        r.run(400.0) { src }
        for (i in 0 until 16) {
            val moved = abs((BASE + e.offsetDb(i)) - at.getValue(i))
            assertTrue(moved < 1.5f,
                "channel ${i + 1} was moved $moved dB away from the balance " +
                "the operator made, on a band that did not change")
        }
    }

    @Test fun `the voices and the rhythm section do not move at all`() {
        // "do not move the singing faders, and do not move the bass and
        // the kick drum + snare + overhead channels after a balance has
        // been made."
        //
        // Every one of those is a channel whose level IS the shape of
        // the mix. Moving any of them re-draws the picture rather than
        // correcting anything inside it.
        val e = engine()
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(90.0) { src }
        val held = listOf(0, 1, 2, 3, 8, 11, 12).associateWith { r.fader(it) }

        // the singer leans in six dB, the drummer digs in, the bass
        // player stands on their pedal
        val loud = band().also {
            it[8] = -17f; it[0] = -12f; it[1] = -14f
            it[2] = -20f; it[11] = -11f; it[12] = -23f
        }
        r.run(300.0) { loud }
        for ((ch, was) in held)
            assertTrue(abs(r.fader(ch) - was) < 0.5f,
                "channel ${ch + 1} moved ${r.fader(ch) - was} dB — the " +
                "voices and the rhythm section are the operator's")
    }

    @Test fun `following a singer's level is one setting away`() {
        // The rule above supersedes an earlier request — "when a singer
        // becomes louder the fader should come lower" — and the
        // mechanism is still there, so this proves the claim rather
        // than leaving it as a comment.
        val e = engine(EngineSettings(holdRoles = setOf(Role.FOUNDATION)))
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(90.0) { src }
        val settled = r.fader(8)

        val loud = band().also { it[8] = -17f }
        r.run(150.0) { loud }
        val down = r.fader(8)
        assertTrue(down < settled - 3f,
            "with the voices out of holdRoles the ride follows them: " +
            "$settled -> $down")

        val soft = band().also { it[8] = -29f }
        r.run(200.0) { soft }
        assertTrue(r.fader(8) > down + 4f,
            "and back up when they step off the mic: $down -> ${r.fader(8)}")
    }

    @Test fun `what is held is the contribution, not the fader`() {
        // On a channel that IS ridden — the guitar amp. Holding a fader
        // still is not holding a balance: the player stands on their
        // pedal and takes over the room. Holding the sum still is what a
        // hand on the desk does.
        val e = engine()
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(90.0) { src }
        val plan = src[4] + r.fader(4)

        val loud = band().also { it[4] = -13f }
        r.run(200.0) { loud }
        val now = loud[4] + r.fader(4)
        assertTrue(abs(now - plan) < 2.5f,
            "the channel's contribution to the mains is what must stay " +
            "put: was $plan, now $now")
    }

    @Test fun `ordinary playing dynamics move nothing at all`() {
        val e = engine()
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(90.0) { src }
        val mark = r.t
        r.run(400.0) { src }        // Run gives it a real player's wander
        val moved = r.travel(mark)
        val total = moved.sum()
        assertTrue(total < 25f,
            "a band playing the same song moved the desk $total dB — the " +
            "deadband is not holding: ${moved.toList()}")
    }

    @Test fun `KEEP moves the faders far less than LEAD does`() {
        // The headline number from the night, as a test. Same band, same
        // wander, same length; the only difference is the mode.
        fun travelOf(mode: BalanceMode): Float {
            val e = StageEngine(rig, EngineSettings(mode = mode))
            val r = Run(e)
            val src = band()
            r.start(src)
            r.run(90.0) { src }
            val mark = r.t
            r.run(600.0) { src }        // Run already gives it a player's wander
            return r.travel(mark).sum()
        }
        val keep = travelOf(BalanceMode.KEEP)
        val lead = travelOf(BalanceMode.LEAD)
        println("fader travel over ten minutes: KEEP $keep dB, LEAD $lead dB")
        assertTrue(keep < lead * 0.5f,
            "KEEP must be the quiet one: KEEP $keep dB vs LEAD $lead dB")
    }

    // ------------------------------------------------------------------
    @Test fun `a gap between songs mutes nothing and re-places nothing`() {
        val e = engine()
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(120.0) { src }
        val at = (0 until 16).associateWith { e.offsetDb(it) }

        // Channels that were never plugged in have already been muted
        // by now, and rightly — that is not what this test is about.
        val mutedBefore = e.decisions.count { it.kind == "held-down" }

        // the song ends: everybody stops for most of a minute
        r.run(50.0) { silence() }
        assertTrue(e.betweenSongs, "a silent stage is a gap, not a mass exit")
        assertTrue(e.decisions.count { it.kind == "held-down" } == mutedBefore,
            "nothing may be muted because the band stopped playing: " +
            e.decisions.filter { it.kind == "held-down" }.drop(mutedBefore)
                .map { it.reason })

        // and the next song starts
        r.run(120.0) { src }
        for (i in 0 until 16) {
            val moved = abs(e.offsetDb(i) - at.getValue(i))
            assertTrue(moved < 2f,
                "channel ${i + 1} moved $moved dB across a gap between " +
                "songs — the balance did not survive the applause")
        }
    }

    @Test fun `a player sitting out a song is not muted, and not moved`() {
        // In KEEP, going quiet is not a reason to pull a fader. A silent
        // channel is already contributing nothing; taking it forty dB
        // down achieves exactly that and leaves forty dB to undo when
        // the player comes back. On the night this came from, the kick
        // was muted and restored twice and the congas once, and each one
        // cost the balance more than it saved.
        val e = engine()
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(120.0) { src }
        val at = r.fader(4)
        val gone = band().also { it[4] = -80f }   // the guitar amp sits out
        r.run(120.0) { gone }
        assertTrue(!e.betweenSongs, "the band is still playing")
        assertTrue(e.decisions.none { it.kind == "held-down" && it.channel == 4 },
            "a planned channel going quiet is not a departure")
        assertTrue(abs(r.fader(4) - at) < 1f,
            "and its fader stays where the operator left it: " +
            "$at -> ${r.fader(4)}")
    }

    @Test fun `in LEAD a channel that stops really has left the mix`() {
        // The rule above is about defending a human's mix. When the
        // engine is deriving one, a source that has gone genuinely
        // changes what the others should be doing.
        val e = engine(LEAD)
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(120.0) { src }
        r.run(80.0) { band().also { it[4] = -80f } }
        assertTrue(e.decisions.any { it.kind == "held-down" && it.channel == 4 })
    }

    @Test fun `nothing moves between songs`() {
        val e = engine()
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(120.0) { src }
        val mark = r.t
        r.run(60.0) { silence() }
        assertTrue(e.betweenSongs)
        assertTrue(r.writes.none { it.first > mark },
            "the engine writes nothing at all while the band is not " +
            "playing: ${r.writes.filter { it.first > mark }.take(4)}")
    }

    @Test fun `a small stage is never mistaken for a gap`() {
        // On a duo, "two channels playing" is a completely normal song.
        // An absolute count got this wrong and left a ground loop in the
        // mix all night.
        val e = engine()
        val r = Run(e)
        val duo = silence().also { it[8] = -22f; it[7] = -24f }
        r.start(duo)
        r.run(120.0) { duo }
        assertTrue(!e.betweenSongs,
            "a singer and a guitar is a duo, not a gap between songs")
    }

    // ------------------------------------------------------------------
    @Test fun `a solo still lifts the fader in KEEP`() {
        val e = engine()
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(120.0) { src }
        val before = r.fader(14)
        val solo = band().also { it[14] = -12f }
        r.run(40.0) { solo }
        assertTrue(r.fader(14) > before,
            "a sax stepping out must still get its lift: " +
            "$before -> ${r.fader(14)}")
    }

    @Test fun `an instrument arriving is placed, and then kept too`() {
        val e = engine()
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(120.0) { src }
        assertTrue(e.state[15]!!.planContrib == null,
            "a channel that was silent when the balance was made has " +
            "nothing to preserve")

        val withHarp = band().also { it[15] = -26f }
        r.run(200.0) { withHarp }
        val st = e.state[15]!!
        assertTrue(st.planContrib != null,
            "once it has found a place, that place becomes its plan")
        // and from then on it is ridden like everything else — though
        // not instantly, and the order matters. Six dB in one step is
        // a player stepping out, so the feature hold gives them their
        // ninety seconds FIRST; only once that expires, and the level
        // has stayed up rather than being a solo, does the ride settle
        // it back down. Waiting only two minutes here measured the
        // feature and called it a failure to ride.
        val at = r.fader(15)
        val louder = band().also { it[15] = -20f }
        r.run(120.0) { louder }
        assertTrue(r.fader(15) > at,
            "a sudden six dB is a feature before it is anything else: " +
            "$at -> ${r.fader(15)}")
        r.run(200.0) { louder }
        assertTrue(r.fader(15) < at - 2f,
            "and once the feature is over, a level that stayed up is " +
            "ridden like everything else: $at -> ${r.fader(15)}")
    }

    @Test fun `the ride is bounded, so a preamp change is not chased to a rail`() {
        val e = engine()
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(120.0) { src }
        val at = r.fader(4)
        // somebody turns the guitar amp's gain knob up twenty dB
        val huge = band().also { it[4] = +1f }
        r.run(300.0) { huge }
        val moved = at - r.fader(4)
        assertTrue(moved <= e.settings.rideBandDb + 0.5f,
            "the ride may not chase a gain change beyond its band: " +
            "moved $moved dB")
        assertTrue(moved > 4f, "but it must do most of what it can")
    }

    // ------------------------------------------------------------------
    @Test fun `rebalance re-derives, then adopts the balance it arrives at`() {
        val e = engine()
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(120.0) { src }
        assertTrue(e.balanceAdopted)

        e.rebalance(r.t)
        assertTrue(!e.balanceAdopted, "the old plan is thrown away")
        assertTrue(e.state.values.all { it.planContrib == null })
        // it must not simply re-adopt the same faders on the next tick
        r.run(2.0) { src }
        assertTrue(!e.balanceAdopted,
            "re-adopting immediately would make REBALANCE do nothing")

        r.run(400.0) { src }
        assertTrue(e.balanceAdopted,
            "once the pyramid has found a balance, that becomes the plan")
    }

    // ------------------------------------------------------------------
    @Test fun `a lift during a solo is not adopted as the new balance`() {
        // "GTR amp went up (I did) when it had a solo."
        //
        // A correction and a solo ride look identical at the fader and
        // mean opposite things. Adopt a solo ride as the balance and the
        // player is left six dB up for the rest of the night — which the
        // operator then has to come back and undo, and on the night this
        // came from they did exactly that, four times on the saxophone
        // and five on the guitar.
        val e = engine()
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(120.0) { src }
        val settled = r.fader(4)

        // the guitarist steps out, and the operator rides them up
        val solo = band().also { it[4] = -11f }
        r.run(10.0) { solo }
        e.operatorOverride(4, r.fader(4) + 6f, r.t)
        r.run(3.0) { solo }
        assertTrue(e.decisions.any { it.kind == "soloride" && it.channel == 4 },
            "a hand going up on a channel that is stepping out is a solo " +
            "ride, not a new balance: " +
            e.decisions.filter { it.channel == 4 }.map { it.kind })
        assertTrue(r.fader(4) > settled + 4f, "and the lift stands")

        // the solo ends and the fader comes home on its own
        r.run(400.0) { src }
        assertTrue(abs(r.fader(4) - settled) < 2.5f,
            "when the player steps back the lift must come back too: " +
            "$settled -> ${r.fader(4)}")
    }

    @Test fun `a correction on a steady channel IS adopted`() {
        // The other half. Nothing is stepping out; the operator has
        // simply decided the channel belongs somewhere else.
        val e = engine()
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(120.0) { src }
        val want = r.fader(4) - 6f
        e.operatorOverride(4, want, r.t)
        r.run(3.0) { src }
        assertTrue(e.decisions.none { it.kind == "soloride" && it.channel == 4 },
            "a steady channel is not soloing")
        r.run(300.0) { src }
        assertTrue(abs(r.fader(4) - want) < 2f,
            "the level the operator chose is where it stays: " +
            "wanted $want, got ${r.fader(4)}")
    }

    @Test fun `a channel the operator rides is remembered as a soloist`() {
        // "Utility 3 is saxophone." The app could not have known that —
        // the label says nothing at all and a horn and a voice are the
        // same thing to a spectrum. But a hand going up every time that
        // channel steps out is a demonstration, and demonstrations are
        // worth learning from.
        val rig = listOf(
            ChannelConfig(0, "KICK", Role.FOUNDATION),
            ChannelConfig(1, "BASS", Role.FOUNDATION),
            ChannelConfig(2, "VOCAL CENTRE", Role.VOCAL),
            ChannelConfig(3, "PIANO", Role.KEYS),
            ChannelConfig(4, "UTILITY 3", Role.INSTRUMENT))
        val e = StageEngine(rig)
        val r = Run(e)
        fun src() = FloatArray(5).also {
            it[0] = -18f; it[1] = -17f; it[2] = -21f; it[3] = -24f
            it[4] = -26f }
        r.run(5.0) { src() }
        e.takeover((0 until 5).associateWith { -10f }, r.t)
        r.run(120.0) { src() }
        assertTrue(!e.isSoloist(e.state[4]!!),
            "an unclassified channel does not take solos by default")

        val solo = src().also { it[4] = -18f }
        r.run(10.0) { solo }
        e.operatorOverride(4, -10f + e.offsetDb(4) + 5f, r.t)
        r.run(3.0) { solo }
        assertTrue(e.isSoloist(e.state[4]!!),
            "one demonstration is enough to learn it")
        assertTrue(e.soloistNames.contains("utility 3"),
            "and it is remembered by the console's name for the channel: " +
            e.soloistNames)
    }

    @Test fun `a human move is adopted and then defended`() {
        val e = engine()
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(120.0) { src }
        // the operator pulls the congas down: they were far too loud
        val want = r.fader(12) - 6f
        e.operatorOverride(12, want, r.t)
        r.run(200.0) { src }
        assertTrue(abs(r.fader(12) - want) < 2f,
            "the level the operator chose must be where it stays: " +
            "wanted $want, got ${r.fader(12)}")
    }
}
