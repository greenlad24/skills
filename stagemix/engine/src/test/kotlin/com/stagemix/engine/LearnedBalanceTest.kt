package com.stagemix.engine

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The mix this engineer actually makes.
 *
 * "Every time I clicked on keep this balance — this is the balance I
 * want it to create automatically. That is the base scenario."
 *
 * The built-in pyramid is a guess about where instruments belong,
 * written by somebody who has never heard this band in this room, and
 * every night's log has said so. A balance the operator built and
 * pressed KEEP on is not a guess. It is the answer, stated — so every
 * KEEP is training data, and what the app builds on its own should
 * converge on what they would have built.
 */
class LearnedBalanceTest {

    @Test fun `it learns the shape of a balance, not its loudness`() {
        val lb = LearnedBalance()
        // the same mix, played quiet and then loud: the same shape
        lb.learn(mapOf(
            Instrument.KICK to -20f, Instrument.BASS to -21f,
            Instrument.VOICE to -16f, Instrument.GUITAR to -26f))
        val quiet = Instrument.values().associateWith { lb.heightOf(it, 1) }
        lb.learn(mapOf(
            Instrument.KICK to -8f, Instrument.BASS to -9f,
            Instrument.VOICE to -4f, Instrument.GUITAR to -14f))
        for (i in listOf(Instrument.KICK, Instrument.VOICE, Instrument.GUITAR))
            assertTrue(abs(lb.heightOf(i, 1)!! - quiet[i]!!) < 0.01f,
                "${i.label} moved when only the LEVEL changed: " +
                "${quiet[i]} -> ${lb.heightOf(i, 1)}")
    }

    @Test fun `the singer sits over the band, because that is what was kept`() {
        val lb = LearnedBalance()
        repeat(3) {
            lb.learn(mapOf(
                Instrument.KICK to -20f, Instrument.BASS to -21f,
                Instrument.SNARE to -24f, Instrument.VOICE to -15f,
                Instrument.GUITAR to -26f, Instrument.HORN to -28f))
        }
        val voice = lb.heightOf(Instrument.VOICE)!!
        val gtr = lb.heightOf(Instrument.GUITAR)!!
        val horn = lb.heightOf(Instrument.HORN)!!
        println("learned: " + lb.summary())
        assertTrue(voice > gtr && gtr > horn,
            "the order the operator kept must be the order it learns: " +
            "voice $voice, guitar $gtr, horn $horn")
        assertEquals(3, lb.kept)
    }

    @Test fun `it takes more than one night to be worth using`() {
        val lb = LearnedBalance()
        lb.learn(mapOf(Instrument.KICK to -20f, Instrument.VOICE to -15f))
        assertTrue(lb.heightOf(Instrument.KICK) == null,
            "one night is one room, one crowd and one mood")
        lb.learn(mapOf(Instrument.KICK to -20f, Instrument.VOICE to -15f))
        assertTrue(lb.heightOf(Instrument.KICK) != null,
            "a balance arrived at twice is worth reproducing")
    }

    @Test fun `it averages, so one odd night does not rewrite the mix`() {
        val lb = LearnedBalance()
        repeat(9) {
            lb.learn(mapOf(Instrument.KICK to -20f, Instrument.VOICE to -15f))
        }
        val before = lb.heightOf(Instrument.VOICE)!!
        // one night where the singer was ten dB too loud
        lb.learn(mapOf(Instrument.KICK to -20f, Instrument.VOICE to -5f))
        val after = lb.heightOf(Instrument.VOICE)!!
        assertTrue(after - before < 1.2f,
            "ten nights of agreement must outweigh one outlier: " +
            "$before -> $after")
    }

    @Test fun `a balance of one instrument teaches nothing`() {
        val lb = LearnedBalance()
        lb.learn(mapOf(Instrument.VOICE to -15f))
        assertEquals(0, lb.kept, "there is no balance in a single channel")
        lb.learn(mapOf(Instrument.UNKNOWN to -15f, Instrument.VOICE to -20f))
        assertEquals(0, lb.kept,
            "and a channel the app cannot name teaches nothing about " +
            "where that instrument belongs")
    }

    @Test fun `it survives the night, and rejects nonsense on the way back`() {
        val lb = LearnedBalance()
        repeat(2) {
            lb.learn(mapOf(
                Instrument.KICK to -20f, Instrument.VOICE to -15f,
                Instrument.CYMBALS to -27f))
        }
        val saved = lb.snapshot()
        val next = LearnedBalance()
        next.restore(saved)
        assertEquals(lb.heightOf(Instrument.VOICE), next.heightOf(Instrument.VOICE))
        assertEquals(2, next.kept)

        // stored preferences are not a trusted source
        val bad = LearnedBalance()
        bad.restore(mapOf(
            "NOT_AN_INSTRUMENT" to (1f to 2),
            "VOICE" to (Float.NaN to 2),
            "KICK" to (-8f to 0),
            "BASS" to (-9f to 3)))
        assertTrue(bad.heightOf(Instrument.VOICE) == null)
        assertTrue(bad.heightOf(Instrument.KICK) == null)
        assertEquals(-3f, bad.heightOf(Instrument.BASS))
    }

    // ------------------------------------------------------------------
    @Test fun `pressing KEEP teaches the engine the balance`() {
        val rig = listOf(
            ChannelConfig(0, "KICK", Role.FOUNDATION),
            ChannelConfig(1, "SNARE", Role.PERCUSSION),
            ChannelConfig(2, "OH", Role.PERCUSSION),
            ChannelConfig(3, "BASS", Role.FOUNDATION),
            ChannelConfig(4, "VOX", Role.VOCAL))
        val e = StageEngine(rig)
        var t = 0.0; var next = 1.0
        val beat = 0.5
        fun hit(tt: Double, per: Double, ph: Double, pk: Float, dec: Double) =
            maxOf(pk - (((tt - ph) % per + per) % per / dec).toFloat() * 40f, -100f)
        // Real instruments move. A channel whose level never changes is
        // hum as far as the engine is concerned, and it rightly refuses
        // to have an opinion about hum — which is what a fixture of
        // dead-flat tones gets.
        val rnd = java.util.Random(31337L)
        val walk = FloatArray(5)
        fun src(tt: Double) = FloatArray(5).also {
            it[0] = hit(tt, beat * 2, 0.0, -18f, 0.16)
            it[1] = hit(tt, beat * 2, beat, -21f, 0.14)
            it[2] = hit(tt, beat, 0.0, -27f, 0.30)
            it[3] = -22f
            it[4] = -20f
            for (i in 3..4) {
                walk[i] += -0.05f * walk[i] + rnd.nextGaussian().toFloat() * 0.8f
                it[i] += walk[i]
            }
        }
        fun run(sec: Double) {
            val end = t + sec - 1e-9
            while (t < end) {
                e.onMeters(src(t), t)
                if (t >= next - 1e-9) { e.tick(t); next += 1.0 }
                t += 0.05
            }
        }
        run(5.0)
        e.takeover(mapOf(0 to -8f, 1 to -14f, 2 to -18f, 3 to -9f, 4 to -4f), t)
        run(40.0)
        // Long enough for the app to know what it is listening to.
        //
        // Telling a singer from a horn takes several half-minute windows
        // of the night — over one song they are the same thing — so a
        // two-minute scenario cannot name enough instruments to describe
        // a balance, and rightly refuses to learn one.
        fun low() = FloatArray(100) { i -> if (i < 22) -12f else -70f }
        fun voice(k: Int) = FloatArray(100) { i ->
            if (i in (46 + k % 5 * 3)..(66 + k % 5 * 3)) -12f else -70f }
        repeat(80) { e.onRtaFor(0, low()) }        // kick
        repeat(80) { e.onRtaFor(3, low()) }        // bass
        repeat(80) { k -> e.onRtaFor(4, voice(k)) }
        run(500.0)
        repeat(40) { e.onRtaFor(0, low()) }
        repeat(40) { e.onRtaFor(3, low()) }
        repeat(40) { k -> e.onRtaFor(4, voice(k)) }
        run(200.0)
        println("recognised: " + (0 until 5).map {
            it to e.recognised[it]?.instrument })

        e.adoptBalance(t)
        println("after one KEEP: " + e.learned.summary())
        assertTrue(e.learned.kept >= 1,
            "pressing KEEP must teach it something: ${e.learned.kept}")
        assertTrue(e.decisions.any { it.kind == "learned" },
            "and say so: " + e.decisions.map { it.kind }.distinct())
    }
}
