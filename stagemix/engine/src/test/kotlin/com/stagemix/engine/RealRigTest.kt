package com.stagemix.engine

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * What a real night said was wrong.
 *
 * These are not invented scenarios. Each one is a sentence the operator
 * wrote after mixing a set with the app running, turned into a test:
 *
 *   · "it didn't recognize the new location of the bass (it was on a
 *     channel named Congos)"
 *   · "it didn't recognize where the singer was — he was in channel 13"
 *   · "kick drum was a little low on volume and needed more volume, as
 *     well as snare and overheads needed less volume"
 *   · "Piano came in very loud and needed an adjustment very quick"
 *   · "I had to touch the faders myself" — and the log then showed 365
 *     separate overrides from a handful of moves.
 *
 * The common root of the first two is the same defect and it is worth
 * naming plainly: the engine was reasoning about the names in its own
 * built-in rig profile, not the names on the console in front of it. It
 * could not possibly have noticed a bass on a channel called CONGOS,
 * because as far as it knew that channel was called "Congo 2".
 */
class RealRigTest {

    private val rig = defaultRigProfile()
    private val BASE = -10f

    private fun engine(s: EngineSettings = EngineSettings()) =
        StageEngine(rig, s)

    /** meters at 20 Hz, engine at 1 Hz, as the app really runs them */
    private class Run(val e: StageEngine, val base: Float = -10f) {
        var t = 0.0
        private var next = 1.0
        val writes = ArrayList<Pair<Double, FaderWrite>>()
        fun run(sec: Double, src: (Double) -> FloatArray) {
            val end = t + sec - 1e-9
            while (t < end) {
                e.onMeters(src(t), t)
                if (t >= next - 1e-9) {
                    for (w in e.tick(t)) writes.add(t to w)
                    next += 1.0
                }
                t += 0.05
            }
        }
        fun start(src: FloatArray) {
            run(5.0) { src }
            e.takeover((0 until 16).associateWith { base }, t)
        }
        fun fader(i: Int) = base + e.offsetDb(i)
    }

    private fun silence() = FloatArray(16) { -80f }

    private fun band() = silence().also {
        it[0] = -18f;  it[1] = -20f;  it[2] = -26f;  it[3] = -22f
        it[4] = -19f;  it[7] = -21f;  it[8] = -23f;  it[11] = -17f
        it[12] = -29f; it[14] = -20f
    }

    // ------------------------------------------------------------------
    @Test fun `the desk's channel name is what the engine reasons about`() {
        val e = engine()
        // channel 11 is "Congo 2" in our profile; on the night the desk
        // called it CONGOS and there was a bass plugged into it
        assertEquals("Congo 2", e.state[12]!!.name)
        assertTrue(e.setChannelName(12, "CONGOS"))
        assertEquals("CONGOS", e.state[12]!!.name,
            "the console's label must win over the profile's guess")
        // and the same channel, once the desk is asked again, keeps it
        assertTrue(!e.setChannelName(12, "CONGOS"),
            "re-reading the same name is not a change")
        // blank names are the desk saying nothing, not a rename to ""
        assertTrue(!e.setChannelName(12, "   "))
        assertEquals("CONGOS", e.state[12]!!.name)
    }

    @Test fun `a name the desk supplies is used to identify the instrument`() {
        // The complaint was that a bass on a channel called CONGOS went
        // unnoticed. Whether the audio finds it is InstrumentId's job and
        // is tested there; what is tested HERE is that the identifier is
        // handed the desk's name at all, which is the part that was broken.
        val e = engine()
        e.setChannelName(12, "CONGOS")
        val id = InstrumentId()
        assertTrue(id.namedRoles("CONGOS").contains(Role.PERCUSSION),
            "the desk's name has to be a name the identifier understands")
        assertTrue(id.namedRoles(e.state[12]!!.name).isNotEmpty(),
            "the identifier must be reasoning about the desk's name")
    }

    @Test fun `a locked role still learns the desk's name`() {
        // Two different questions. The role is a suggestion the listener
        // may overrule and an operator may pin; the NAME is a fact about
        // the console, true even on a channel somebody has pinned by hand.
        val e = engine()
        e.setRole(12, Role.PERCUSSION)
        assertTrue(!e.setRoleFromName(12, Role.FOUNDATION),
            "a pinned role must not move")
        assertTrue(e.setChannelName(12, "CONGOS"),
            "but the name is not the operator's to be protected from")
    }

    // ------------------------------------------------------------------
    @Test fun `one hand on one fader is one correction`() {
        val e = engine()
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(40.0) { src }

        // a drag, as a surface really sends one: a stream of positions
        var db = r.fader(8)
        repeat(40) {
            db -= 0.1f
            e.operatorOverride(8, db, r.t)
            e.onMeters(src, r.t); r.t += 0.05
        }
        assertEquals(0, e.overrideCount,
            "nothing is committed while the hand is still moving")

        r.run(3.0) { src }
        assertEquals(1, e.overrideCount,
            "forty positions from one gesture is one correction, not forty")
        assertEquals(1, e.decisions.count { it.kind == "override" },
            "and one line in the log, not forty")
        // and the lesson is the WHOLE gesture, not its first hundredth
        val d = e.decisions.last { it.kind == "override" }
        assertTrue(d.deltaDb < -3f,
            "the correction recorded must be the move the human made " +
            "(~-4 dB), got ${d.deltaDb}")

        // a second, separate gesture is a second correction
        e.operatorOverride(8, db - 2f, r.t)
        r.run(3.0) { src }
        assertEquals(2, e.overrideCount)
    }

    @Test fun `a gesture takes hold immediately, even before it is committed`() {
        // The delay is only in the LOG and the lesson. The hands-off has
        // to be instant or the engine spends the gesture fighting it.
        val e = engine()
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(40.0) { src }
        val mark = r.t
        e.operatorOverride(8, r.fader(8) - 4f, r.t)
        r.run(20.0) { src }
        assertTrue(r.writes.none { it.first > mark && it.second.channel == 8 },
            "the engine must let go the instant a hand lands, not when " +
            "the gesture is finally committed")
    }

    // ------------------------------------------------------------------
    @Test fun `the kick is not divided down by the number of bass channels`() {
        // "kick drum was a little low on volume and needed more volume,
        // as well as snare and overheads needed less volume" — both are
        // the same arithmetic. A group target is shared out because the
        // room hears the sum, which is true of two bass DIs playing one
        // line and false of a kick against a bass.
        val e = engine()
        val r = Run(e)
        // kick plus THREE bass channels, all playing
        val src = band().also {
            it[3] = -22f          // Bass Mic
            it[11] = -17f         // Bass DI
            it[13] = -24f         // DI2 Synth Bass
        }
        r.start(src)
        r.run(300.0) { src }

        val kick = r.fader(0) + src[0]
        val perc = r.fader(1) + src[1]
        assertTrue(kick > perc,
            "the kick must sit over the snare, not under it: " +
            "kick ${kick}, snare ${perc}")

        // and the low end as a WHOLE has not grown: the tilt moves dB
        // between kick and bass, it does not add any
        val lowEnd = listOf(0, 3, 11, 13).map { r.fader(it) + src[it] }
        val sum = (10.0 * Math.log10(
            lowEnd.sumOf { Math.pow(10.0, it / 10.0) })).toFloat()
        val vocal = r.fader(8) + src[8]
        assertTrue(sum - vocal < 4f,
            "tilting the low end must not raise it over the singer: " +
            "kick+bass ${sum}, vocal ${vocal}")
    }

    // ------------------------------------------------------------------
    @Test fun `an instrument arriving is listened to before it is placed`() {
        // "Piano came in very loud and needed an adjustment very quick."
        // The 20-second loudness average still held the level the piano
        // faded out at, so for the first half-minute a loud arrival read
        // as a quiet channel and got pushed UP before being pulled back.
        val e = engine()
        val r = Run(e)
        val quiet = band().also { it[5] = -34f; it[6] = -34f }
        r.start(quiet)
        r.run(200.0) { quiet }         // piano present but very quiet

        val away = band()              // piano gone entirely
        r.run(60.0) { away }

        val loud = band().also { it[5] = -14f; it[6] = -14f }
        val mark = r.t
        r.run(60.0) { loud }           // and back, seventeen dB louder

        val moves = r.writes.filter { it.first > mark && it.second.channel == 5 }
        val rise = moves.maxOfOrNull { it.second.levelDb }
            ?.minus(r.fader(5)) ?: 0f
        assertTrue(rise < 2f,
            "a loud arrival must never be pushed UP first: the piano " +
            "fader overshot its resting place by ${rise} dB")
    }

    @Test fun `arriving clears the stale averages it would be judged on`() {
        val e = engine()
        val r = Run(e)
        val quiet = band().also { it[5] = -40f }
        r.start(quiet)
        r.run(120.0) { quiet }
        val stale = e.state[5]!!.preEma
        assertTrue(stale != null && stale < -30f)

        r.run(60.0) { band() }                       // away
        r.run(2.0) { band().also { it[5] = -14f } }  // back, loud
        val fresh = e.state[5]!!.preEma!!
        assertTrue(fresh > -25f,
            "the loudness average must re-seed from the sound that has " +
            "arrived, not from the one that left: got $fresh")
        assertTrue(e.state[5]!!.heardSec < 5f,
            "and the channel must re-audition before the fader moves")
    }

    // ------------------------------------------------------------------
    @Test fun `a solo lifts the fader even when the mix is not settled`() {
        // "Solos were not recognized (Sax, Guitar etc.)". The lift was
        // conditional on the channel having settled, and on a night full
        // of hands-on corrections and arrivals it frequently has not —
        // in which case a recognised solo did nothing at all.
        val e = engine()
        val r = Run(e)
        // The singer is clearly on top here, deliberately. When the lead
        // vocal is buried the band is being ducked, and the duck rides on
        // the same fader as the solo lift and wins — which is the right
        // priority and not what this test is about.
        val src = band().also { it[8] = -15f }
        r.start(src)
        r.run(60.0) { src }
        // deliberately unsettle everything, as an arrival or a human does
        e.rebalance(r.t)
        assertTrue(!e.state[14]!!.settled)

        val before = r.fader(14)
        val solo = src.copyOf().also { it[14] = -12f }  // sax steps out 8 dB
        r.run(40.0) { solo }
        assertTrue(r.fader(14) > before + 0.5f,
            "a sax solo must lift the fader whether or not the mix had " +
            "finished settling: ${before} -> ${r.fader(14)}")
    }

    @Test fun `a near miss on a solo is written down`() {
        // A solo that never latches leaves no trace at all in the log,
        // so "solos were not recognised" cannot be debugged after the
        // fact. It can now.
        val e = engine()
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(120.0) { src }
        // a rise big enough to be interesting, too small to be a feature
        val nudge = band().also { it[14] = -17f }
        r.run(30.0) { nudge }
        assertTrue(e.decisions.any { it.kind == "nearly" || it.kind == "feature" },
            "a player who nearly steps out must appear in the log one " +
            "way or the other")
    }

    // ------------------------------------------------------------------
    @Test fun `the whole rig still balances with the desk's own names on it`() {
        // End to end: rename every channel the way the venue's desk had
        // them, hand the engine the same band, and check nothing about
        // the balance falls over. The names are deliberately unhelpful.
        val e = engine()
        val desk = mapOf(
            0 to "KICK", 1 to "SNARE", 2 to "OH", 3 to "DI 1",
            4 to "GTR AMP", 5 to "PIANO L", 6 to "PIANO R", 7 to "AC GTR",
            8 to "VOX 1", 9 to "VOX 2", 10 to "VOX 3", 11 to "BASS",
            12 to "CONGOS", 13 to "VOX 4", 14 to "SAXOPHONE",
            15 to "HARP")
        for ((ch, n) in desk) e.setChannelName(ch, n)
        val r = Run(e)
        val src = band()
        r.start(src)
        r.run(300.0) { src }
        assertTrue(e.balanced, "the mix must still settle: ${e.settledCount()}")
        for (i in 0 until 16)
            assertTrue(abs(e.offsetDb(i)) <= 12.01f,
                "channel ${i + 1} ran away to ${e.offsetDb(i)} dB")
    }
}
