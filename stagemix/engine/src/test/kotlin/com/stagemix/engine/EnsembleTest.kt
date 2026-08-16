package com.stagemix.engine

import kotlin.math.PI
import kotlin.math.sin
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Recognising instruments with no help from the channel names.
 *
 * "I want a smarter system that recognizes each channel — it doesn't
 * need to look at the name at all."
 *
 * The reason it could not before is worth stating precisely: one
 * channel's own spectrum and envelope top out at four families, and a
 * kick and a bass are the same family, and so are a saxophone and a
 * singer. Nothing about those two pairs is visible in one channel's
 * numbers. What IS visible — and what nothing was looking at — is that
 * the sixteen meters arrive together, twenty times a second, so what
 * every channel is doing relative to the other fifteen is measurable.
 *
 * These tests build a band out of that: a drummer playing a grid, a
 * bass locking to the kick, a piano on two channels, a singer who is
 * in most of the night and a horn that plays three solos. No names are
 * given to anything.
 */
class EnsembleTest {

    /** a stage, simulated at the meter rate */
    private class Band(val n: Int) {
        val ens = Ensemble(n)
        val id = InstrumentId()
        var t = 0.0
        private val db = FloatArray(n) { -100f }
        private val on = BooleanArray(n)

        fun frame(levels: FloatArray) {
            for (i in 0 until n) {
                db[i] = levels[i]
                on[i] = levels[i] > -55f
            }
            ens.onFrame(db, on, 0.05f)
            for (i in 0 until n) id.onLevel(i, db[i], 0.05f, on[i])
            t += 0.05
        }

        /**
         * Real instruments MOVE — a singer's formants shift with every
         * vowel, a horn bends its notes — and the identifier leans on
         * exactly that to tell something carrying a line from a held
         * chord. Pushing one frozen frame over and over describes a
         * synthesiser holding one note, which is not a scenario any of
         * these tests mean to be running.
         */
        fun spectrum(ch: Int, bins: FloatArray, times: Int = 20,
                     moveDb: Float = 0f) {
            val rnd = java.util.Random(ch.toLong() * 7 + 3)
            repeat(times) {
                val f = if (moveDb <= 0f) bins else FloatArray(bins.size) { i ->
                    bins[i] + rnd.nextGaussian().toFloat() * moveDb
                }
                id.onRta(ch, f, true)
            }
        }
    }

    /** a log-spaced RTA: [hz] to level, everything else at the floor */
    private fun rta(vararg peaks: Pair<Double, Float>): FloatArray {
        val b = FloatArray(100) { -70f }
        for ((hz, lvl) in peaks) {
            val i = (10.0 * kotlin.math.log2(hz / 20.0)).toInt()
            for (k in -3..3) {
                val j = i + k
                if (j in 0 until 100)
                    b[j] = maxOf(b[j], lvl - kotlin.math.abs(k) * 3f)
            }
        }
        return b
    }

    /** a struck source: hard rise, fast decay, on the beat */
    private fun hit(tSec: Double, period: Double, phase: Double,
                    peak: Float, decay: Double): Float {
        val since = ((tSec - phase) % period + period) % period
        return peak - (since / decay).toFloat() * 40f
    }

    // ------------------------------------------------------------------
    @Test fun `a drum kit is the only thing that fires together`() {
        val b = Band(6)
        // 0 kick (1 and 3), 1 snare (2 and 4), 2 overheads (every beat),
        // 3 bass (with the kick, sustaining), 4 a singer, 5 a horn
        val beat = 0.5                     // 120 bpm
        val lv = FloatArray(6)
        var i = 0
        while (b.t < 200.0) {
            val t = b.t
            lv[0] = hit(t, beat * 2, 0.0, -18f, 0.18)
            lv[1] = hit(t, beat * 2, beat, -20f, 0.15)
            lv[2] = hit(t, beat, 0.0, -26f, 0.30)
            // the bass moves with the kick but does not fall away
            lv[3] = -22f + 3f * sin(2 * PI * t / (beat * 8)).toFloat() +
                (if (((t / beat).toInt()) % 2 == 0) 1.5f else 0f)
            lv[4] = -23f + 5f * sin(2 * PI * t / 3.1).toFloat()
            lv[5] = if ((t % 120.0) < 25.0)
                -21f + 5f * sin(2 * PI * t / 2.3).toFloat() else -100f
            for (k in 0 until 6) lv[k] = maxOf(lv[k], -100f)
            b.frame(lv)
            i++
        }

        // the three kit channels fire with each other, and nothing else does
        val kitScores = (0..5).map { b.ens.kitAffinity(it) }
        println("kit affinity: " + kitScores.mapIndexed { c, v ->
            "ch" + c + " " + v }.joinToString("  "))
        for (drum in listOf(0, 1, 2))
            assertTrue(kitScores[drum] > kitScores[4],
                "drum ch$drum (${kitScores[drum]}) must fire with the kit " +
                "more than the singer does (${kitScores[4]})")
        assertTrue(b.ens.partners(2) >= 2,
            "the overheads hear the whole kit, so they coincide with " +
            "several channels: ${b.ens.partners(2)}")
    }

    @Test fun `two channels of one piano are recognised as one instrument`() {
        val b = Band(4)
        val lv = FloatArray(4)
        val rnd = java.util.Random(11)
        while (b.t < 60.0) {
            val t = b.t
            val piano = -24f + 4f * sin(2 * PI * t / 5.0).toFloat() +
                rnd.nextGaussian().toFloat() * 0.4f
            lv[0] = piano                       // piano L
            lv[1] = piano + 0.6f                // piano R: the same curve
            lv[2] = -20f + 5f * sin(2 * PI * t / 3.3).toFloat()
            lv[3] = -26f + 6f * sin(2 * PI * t / 1.7).toFloat()
            b.frame(lv)
        }
        assertEquals(1, b.ens.stereoMate(0),
            "two halves of one piano are one instrument measured twice")
        assertEquals(0, b.ens.stereoMate(1))
        assertTrue(b.ens.stereoMate(2) == null,
            "and two different instruments are not a pair")
    }

    @Test fun `a singer is in most of the night, a horn is in a few songs`() {
        val b = Band(3)
        val lv = FloatArray(3)
        while (b.t < 900.0) {                  // fifteen minutes
            val t = b.t
            lv[0] = -20f                        // the band, always there
            // the singer: sings in most songs, with phrase gaps
            lv[1] = if ((t % 200.0) < 160.0 && sin(2 * PI * t / 4.0) > -0.6)
                -22f else -100f
            // the horn: three solos, and nothing in between
            lv[2] = if ((t % 300.0) < 30.0) -21f else -100f
            b.frame(lv)
        }
        val singer = b.ens.setDuty(1); val horn = b.ens.setDuty(2)
        println("set duty: singer " + singer + " burst " + b.ens.burstiness(1) +
            " | horn " + horn + " burst " + b.ens.burstiness(2))
        assertTrue(singer > horn * 2f,
            "the singer is in far more of the night: $singer vs $horn")
        assertTrue(b.ens.burstiness(2) > b.ens.burstiness(1),
            "and the horn plays in bursts where the singer does not: " +
            "${b.ens.burstiness(2)} vs ${b.ens.burstiness(1)}")
    }

    // ------------------------------------------------------------------
    @Test fun `a kick and a bass are told apart without either name`() {
        val b = Band(4)
        val beat = 0.5
        val lv = FloatArray(4)
        while (b.t < 240.0) {
            val t = b.t
            lv[0] = maxOf(hit(t, beat * 2, 0.0, -18f, 0.16), -100f)   // kick
            lv[1] = maxOf(hit(t, beat * 2, beat, -21f, 0.14), -100f)  // snare
            lv[2] = maxOf(hit(t, beat, 0.0, -27f, 0.28), -100f)       // OH
            lv[3] = -22f + 2f * sin(2 * PI * t / (beat * 8)).toFloat() // bass
            b.frame(lv)
        }
        // a kick: almost all under 100 Hz with a little click
        b.spectrum(0, rta(60.0 to -12f, 3000.0 to -34f), 60)
        // a bass: under 200 Hz, nothing on top at all
        b.spectrum(3, rta(80.0 to -12f, 160.0 to -16f), 60)

        val kick = b.id.recognise(0, b.ens)
        val bass = b.id.recognise(3, b.ens)
        println("ch1 -> " + kick?.instrument + " conf " +
            kick?.confidence + "  " + kick?.why)
        println("ch4 -> " + bass?.instrument + " conf " +
            bass?.confidence + "  " + bass?.why)
        assertEquals(Instrument.KICK, kick?.instrument,
            "a struck low end that fires with the kit is a kick")
        assertEquals(Instrument.BASS, bass?.instrument,
            "a sustained low end that does not is a bass")
    }

    @Test fun `a channel that lands with the kit is never called a bass`() {
        // From a real night: the OVERHEADS were declared a bass — "60 %
        // under 200 Hz and it sustains" — and the engine moved them into
        // the low-end group and put a kick's chain on them. The kit term
        // was in the comment and missing from the arithmetic.
        val b = Band(4)
        val beat = 0.5
        val lv = FloatArray(4)
        while (b.t < 240.0) {
            val t = b.t
            lv[0] = maxOf(hit(t, beat * 2, 0.0, -18f, 0.16), -100f)   // kick
            lv[1] = maxOf(hit(t, beat * 2, beat, -21f, 0.14), -100f)  // snare
            // a badly placed overhead: bottom-heavy AND on the grid
            lv[2] = maxOf(hit(t, beat, 0.0, -24f, 0.45), -100f)
            lv[3] = -22f + 2f * sin(2 * PI * t / (beat * 8)).toFloat()
            b.frame(lv)
        }
        b.spectrum(2, rta(90.0 to -12f, 160.0 to -14f, 400.0 to -20f), 60)
        val oh = b.id.recognise(2, b.ens)
        println("bottom-heavy overhead -> " + oh?.instrument + "  " + oh?.why)
        assertTrue(oh?.instrument != Instrument.BASS,
            "a channel that lands with every other drum is part of the " +
            "kit, whatever its spectrum says: got ${oh?.instrument}")
    }

    @Test fun `overheads are the channel that hears everything`() {
        val b = Band(4)
        val beat = 0.5
        val lv = FloatArray(4)
        while (b.t < 240.0) {
            val t = b.t
            lv[0] = maxOf(hit(t, beat * 2, 0.0, -18f, 0.16), -100f)
            lv[1] = maxOf(hit(t, beat * 2, beat, -21f, 0.14), -100f)
            lv[2] = maxOf(hit(t, beat, 0.0, -27f, 0.28), -100f)
            lv[3] = -22f + 2f * sin(2 * PI * t / (beat * 8)).toFloat()
            b.frame(lv)
        }
        b.spectrum(2, rta(9000.0 to -12f, 13000.0 to -14f, 6000.0 to -18f), 60)
        val oh = b.id.recognise(2, b.ens)
        println("ch3 -> " + oh?.instrument + "  " + oh?.why)
        assertEquals(Instrument.CYMBALS, oh?.instrument,
            "all air, no bottom, and firing with every other drum")
    }

    @Test fun `it says UNKNOWN rather than guessing between a voice and a horn`() {
        // Twenty seconds of one melodic channel. Over that long the two
        // are the same thing and any confident answer would be a lie.
        val b = Band(2)
        val lv = FloatArray(2)
        while (b.t < 30.0) {
            lv[0] = -20f
            lv[1] = -22f + 5f * sin(2 * PI * b.t / 3.0).toFloat()
            b.frame(lv)
        }
        b.spectrum(1, rta(500.0 to -12f, 1200.0 to -14f, 3000.0 to -18f), 40,
            moveDb = 6f)
        val r = b.id.recognise(1, b.ens)
        println("after 30 s -> ${r?.instrument} conf ${r?.confidence}")
        assertTrue(r == null || r.instrument == Instrument.UNKNOWN ||
            r.confidence < 0.45f,
            "half a minute is not enough night to tell a singer from a " +
            "saxophone, and the honest answer is to say so: $r")
    }

    @Test fun `given a whole set, the singer and the horn separate`() {
        val b = Band(3)
        val lv = FloatArray(3)
        while (b.t < 1200.0) {                 // twenty minutes
            val t = b.t
            lv[0] = -20f
            lv[1] = if ((t % 210.0) < 175.0 && sin(2 * PI * t / 4.0) > -0.7)
                -22f + 4f * sin(2 * PI * t / 1.3).toFloat() else -100f
            lv[2] = if ((t % 400.0) < 40.0)
                -21f + 4f * sin(2 * PI * t / 1.1).toFloat() else -100f
            b.frame(lv)
        }
        val voiceish = rta(400.0 to -12f, 900.0 to -13f, 2200.0 to -16f,
            3500.0 to -20f)
        b.spectrum(1, voiceish, 60, moveDb = 6f)
        b.spectrum(2, voiceish, 60, moveDb = 6f)
        val singer = b.id.recognise(1, b.ens)
        val horn = b.id.recognise(2, b.ens)
        println("singer -> " + singer?.instrument + "  " + singer?.why)
        println("horn   -> " + horn?.instrument + "  " + horn?.why)
        assertTrue(singer?.instrument == Instrument.VOICE,
            "a channel carrying a line through most of the night is the " +
            "singer: got ${singer?.instrument}")
        assertTrue(horn?.instrument == Instrument.HORN ||
            horn?.instrument == Instrument.LEAD_GUITAR,
            "and one that appears for a few minutes of it is a guest — " +
            "a horn or a lead line: got ${horn?.instrument}")
    }

    @Test fun `identical spectra, opposite answers - only the set decides`() {
        // The point of the whole exercise, made explicit: the two
        // channels above were given the SAME spectrum. Nothing in what
        // they sound like separates them, and the app got it right
        // anyway, because it was not listening to them one at a time.
        val b = Band(3)
        val lv = FloatArray(3)
        while (b.t < 1200.0) {
            val t = b.t
            lv[0] = -20f
            lv[1] = if ((t % 210.0) < 175.0) -22f else -100f
            lv[2] = if ((t % 400.0) < 40.0) -21f else -100f
            b.frame(lv)
        }
        assertTrue(b.ens.setDuty(1) > 0.6f && b.ens.setDuty(2) < 0.2f,
            "the set duty is the whole difference: " +
            "${b.ens.setDuty(1)} vs ${b.ens.setDuty(2)}")
    }

    // ------------------------------------------------------------------
    @Test fun `a channel nobody has heard yet gets no opinion at all`() {
        val b = Band(3)
        assertTrue(b.id.recognise(0, b.ens) == null,
            "no evidence, no verdict")
        assertTrue(b.ens.kitAffinity(0) == 0f)
        assertTrue(b.ens.stereoMate(0) == null)
        assertTrue(b.ens.setDuty(0) == 0f)
    }

    @Test fun `nonsense in the meters cannot corrupt the ensemble`() {
        val b = Band(3)
        val bad = floatArrayOf(Float.NaN, Float.POSITIVE_INFINITY, -20f)
        repeat(200) { b.frame(bad) }
        assertTrue(b.ens.setDuty(0) in 0f..1f)
        assertTrue(b.ens.kitAffinity(1) in 0f..1f)
        assertTrue(b.ens.burstiness(2) in 0f..1f)
        assertTrue(b.ens.correlation(0, 1) in -1f..1f)
    }

    @Test fun `every instrument maps to a role the balance understands`() {
        for (i in Instrument.values())
            assertTrue(i.role in Role.values(),
                "${i.name} must land somewhere in the ladder")
        assertEquals(Role.FOUNDATION, Instrument.KICK.role)
        assertEquals(Role.FOUNDATION, Instrument.BASS.role)
        assertEquals(Role.DRUMS, Instrument.CYMBALS.role)
        assertEquals(Role.VOCAL, Instrument.VOICE.role)
        assertEquals(Role.COLOR, Instrument.HORN.role)
        assertEquals(Role.INSTRUMENT, Instrument.UNKNOWN.role)
    }
}
