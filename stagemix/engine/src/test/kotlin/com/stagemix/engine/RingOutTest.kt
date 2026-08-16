package com.stagemix.engine

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * "There were times in the night where a feedback was happening — on
 * the stage, in the monitors."
 *
 * The watchdog heard all of them: 196 Hz, 160 Hz, 226 Hz and 3377 Hz
 * over three nights. Its entire response was to freeze the engine's
 * boosts, which does nothing whatever for a wedge that is howling — the
 * loop is a microphone, a wedge and the air between them, and the mains
 * fader is not part of it.
 *
 * This is the move a human makes instead: find the frequency, find the
 * microphone it is living in, put a narrow cut there.
 */
class RingOutTest {

    /** a channel's spectrum: a flat stage with an optional ring in it */
    private fun spec(ringHz: Float?, ringDb: Float,
                     floorDb: Float = -55f): FloatArray {
        val out = FloatArray(FrequencyMap.BINS) { floorDb }
        ringHz?.let {
            val b = FrequencyMap.binOf(it)
            out[b] = ringDb
            if (b > 0) out[b - 1] = ringDb - 12f
            if (b < out.size - 1) out[b + 1] = ringDb - 12f
        }
        return out
    }

    /** the analyzer sweeping the stage, one channel at a time */
    private fun sweep(r: RingOut, t0: Double, hot: Int, hz: Float): Double {
        var t = t0
        for (ch in 0 until 16) {
            // every open mic hears a howl; the one in the loop hears it
            // twenty dB louder than the rest of the stage does
            val db = when (ch) {
                hot -> -8f
                in 1..3, 8, 9, 10 -> -30f    // the other microphones
                else -> -70f                  // the DIs cannot hear a room
            }
            r.onRta(ch, spec(hz, db), t)
            t += 0.5
        }
        return t
    }

    // ------------------------------------------------------------------
    @Test fun `the microphone in the loop is the one that gets cut`() {
        val r = RingOut()
        r.ringing(196, 0.0)
        assertTrue(r.hunting, "a ring is a reason to go looking")
        val t = sweep(r, 0.5, hot = 9, hz = 196f)
        val w = r.tick(t + 1.0)
        println(r.lastAction)
        assertTrue(w.isNotEmpty(), "nothing was written: ${r.lastAction}")

        val g = w.first { it.address.endsWith("/g") }
        assertEquals("/ch/10/eq/4/g", g.address,
            "the cut went on the wrong channel: " + w.map { it.address })
        val db = g.value * 30f - 15f
        assertTrue(db < -3f && db >= -9.01f,
            "a first ring is a few dB, not a hole: $db")
        val f = w.first { it.address.endsWith("/f") }
        val hz = 20f * Math.pow(1000.0, f.value.toDouble()).toFloat()
        assertTrue(abs(hz - 196f) < 20f, "cut at the wrong frequency: $hz")
        val q = w.first { it.address.endsWith("/q") }
        val qv = 10f / Math.pow(10.0 / 0.3, q.value.toDouble()).toFloat()
        assertTrue(qv >= 4f, "a ring-out is narrow: Q $qv")
    }

    @Test fun `a ring that comes back is cut deeper, to a limit`() {
        val r = RingOut()
        var t = 0.0
        r.ringing(196, t); t = sweep(r, t + 0.5, 9, 196f); r.tick(t + 1.0)
        val first = r.active().first().cutDb
        repeat(8) {
            t += 60.0
            r.ringing(196, t)
            r.tick(t + 1.0)
        }
        val deep = r.active().first().cutDb
        println("first cut %.1f dB, after eight more rings %.1f dB"
            .format(first, deep))
        assertTrue(deep > first, "it kept ringing and nothing more happened")
        assertTrue(deep <= r.maxCutDb + 0.01f,
            "a notch is not a mute: $deep dB")
        assertEquals(1, r.active().size,
            "the same ring is one cut, not eight")
    }

    @Test fun `nothing this writes can raise anything, anywhere`() {
        val r = RingOut()
        var t = 0.0
        for (hz in intArrayOf(196, 160, 226, 3377)) {
            r.ringing(hz, t)
            t = sweep(r, t + 0.5, hot = (hz % 7), hz = hz.toFloat())
            for (w in r.tick(t + 1.0)) {
                assertTrue(isSafeAddress(w.address),
                    "${w.address} is not ours to write")
                assertTrue(!isGainAdding(w.address, w.value),
                    "${w.address} = ${w.value} adds gain")
                assertTrue(!Regex("^/ch/\\d\\d/mix/0[1-6]/")
                    .containsMatchIn(w.address),
                    "a monitor send: ${w.address}")
                assertTrue(!w.address.startsWith("/bus/"),
                    "a monitor bus: ${w.address}")
            }
            t += 30.0
        }
    }

    @Test fun `a stage that stops ringing gets its tone back`() {
        val r = RingOut()
        var t = 0.0
        r.ringing(196, t); t = sweep(r, t + 0.5, 9, 196f); r.tick(t + 1.0)
        val cut = r.active().first().cutDb
        assertTrue(cut > 0f)

        // an hour of no rings at all
        repeat(12) { t += r.releaseAfterSec; r.tick(t) }
        println("after an hour of quiet: " + r.describe())
        assertTrue(r.active().isEmpty(),
            "the cut is still there long after the ring went: " + r.describe())
    }

    @Test fun `while it is only watching it says what it would have done`() {
        val r = RingOut()
        r.ringing(3377, 0.0)
        val t = sweep(r, 0.5, hot = 8, hz = 3377f)
        val w = r.tick(t + 1.0, mayWrite = false)
        assertTrue(w.isEmpty(), "shadow mode must write nothing")
        assertTrue(r.lastAction.contains("ch09"),
            "and still say which microphone it is: ${r.lastAction}")
    }

    @Test fun `the chain leaves the ring-out's band alone`() {
        // Otherwise the first re-treat flattens the notch and the stage
        // rings again at the same frequency for the same reason.
        val t = ChannelTreatment()
        for (role in Role.values()) {
            val w = t.consider(9, role,
                InstrumentId.Verdict(Family.VOICELIKE, 0.95f, "because"),
                1f, DoubleArray(100), 100.0,
                ChannelTreatment.Shape(lowEdgeHz = 90f, resonanceHz = 250f,
                    resonanceDb = 9f, resonanceQ = 4f))
            assertTrue(w.none {
                    it.address.startsWith("/ch/10/eq/${RingOut.RING_BAND}/") },
                "$role wrote band ${RingOut.RING_BAND}: " + w.map { it.address })
        }
    }

    /**
     * "Fix feedbacks as fast as it can." A microphone that is actually
     * in the loop is not marginally louder at the ringing frequency —
     * it is enormously louder, because every other mic is hearing the
     * same howl across a room. When that is true the sweep should stop
     * immediately rather than burn its full eight seconds while the
     * stage is howling.
     */
    @Test
    fun `an obvious culprit ends the sweep early`() {
        val r = RingOut()
        r.ringing(196, 0.0)
        val loud = FloatArray(100) { -80f }
        loud[FrequencyMap.binOf(196f)] = -8f
        val quiet = FloatArray(100) { -80f }
        quiet[FrequencyMap.binOf(196f)] = -40f
        for (ch in listOf(1, 2, 3)) r.onRta(ch, quiet, 0.5)
        r.onRta(8, loud, 1.0)
        // two seconds in, nowhere near the eight-second deadline
        val w = r.tick(2.0, mayWrite = true)
        assertFalse(r.hunting, "kept sweeping when the answer was obvious")
        assertTrue(w.any { it.address.startsWith("/ch/09/eq/") },
            "did not cut the microphone it had already identified: " +
            w.map { it.address })
    }

    /** and when it is a close call, it still takes the whole sweep */
    @Test
    fun `a close field runs the full sweep`() {
        val r = RingOut()
        r.ringing(196, 0.0)
        val a = FloatArray(100) { -80f }
        a[FrequencyMap.binOf(196f)] = -20f
        val b = FloatArray(100) { -80f }
        b[FrequencyMap.binOf(196f)] = -22f
        for (ch in listOf(1, 2, 3)) r.onRta(ch, b, 0.5)
        r.onRta(8, a, 1.0)
        r.tick(2.0, mayWrite = true)
        assertTrue(r.hunting, "called it early on a two dB difference")
    }
}
