package com.stagemix.engine

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * "the piano can also do solos."
 *
 * The piano is two channels. A solo that lifts one half of a stereo
 * pair and not the other drags the image to one side for the whole
 * solo — worse than not lifting it at all. RULEBOOK.md §2.
 */
class PianoSoloTest {

    private fun engine(): StageEngine {
        val e = StageEngine(defaultRigProfile(),
            EngineSettings(mode = BalanceMode.KEEP))
        val faders = HashMap<Int, Float>()
        for (i in 0 until 16) faders[i] = -6f
        e.takeover(faders, 0.0)
        return e
    }

    /** the band, with the piano playing at a steady level */
    private fun band(pianoDb: Float): FloatArray {
        val lv = FloatArray(16) { -70f }
        lv[0] = -14f; lv[1] = -16f          // kit
        lv[8] = -12f                         // lead vocal
        lv[11] = -14f; lv[13] = -15f         // both bass DIs
        lv[4] = -18f                         // guitar
        lv[5] = pianoDb; lv[6] = pianoDb     // the piano, both halves
        return lv
    }

    /**
     * The mate is latched with the same lift, from its own resting
     * position. Driven directly rather than through a synthetic band,
     * because what matters here is the latch itself: the feature branch
     * returns before the stereo-pair correction, so if the mate is not
     * latched at the same moment it simply never rises.
     */
    @Test
    fun `latching a feature on one half latches the other`() {
        val e = engine()
        var t = 0.0
        repeat(400) { e.onMeters(band(-20f), t); e.tick(t); t += 0.25 }
        e.adoptBalance(t)
        repeat(120) { e.onMeters(band(-20f), t); e.tick(t); t += 0.25 }

        // the pianist steps out: one half crosses the threshold first,
        // which is exactly what happens in the room
        repeat(240) {
            val lv = band(-20f)
            lv[5] = -10f          // left rises
            lv[6] = -12f          // right follows, quieter
            e.onMeters(lv, t); e.tick(t); t += 0.25
        }
        val l = e.state[5]!!
        val r = e.state[6]!!
        if (l.featureStart >= 0 || r.featureStart >= 0) {
            assertTrue(l.featureStart >= 0 && r.featureStart >= 0,
                "half the piano was featured and the other half was not " +
                "— the image would collapse for the whole solo")
            assertEquals(l.featureLift, r.featureLift, 0.01f,
                "the two halves were lifted by different amounts")
        }
        // and either way they must not have drifted apart
        assertTrue(kotlin.math.abs(l.offset - r.offset) < 1.5f,
            "the halves of the piano are ${l.offset} and ${r.offset}")
    }

    @Test
    fun `the pair stays together when nothing is soloing`() {
        val e = engine()
        var t = 0.0
        repeat(800) { e.onMeters(band(-20f), t); e.tick(t); t += 0.25 }
        val d = kotlin.math.abs(e.state[5]!!.offset - e.state[6]!!.offset)
        assertTrue(d < 1.0f, "the two halves of the piano drifted $d dB apart")
    }
}
